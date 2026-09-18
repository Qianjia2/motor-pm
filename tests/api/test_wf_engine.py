"""工作流引擎（一期地基）测试。

分两半，同 test_project_workflow.py 的体例：
  第一部分「模板保真」不碰数据库，只比对引擎从 PHASE_NODES 导入的结果，
    保证节点改名/增删会被抓出来，而不是悄悄少几个状态。
  第二部分「引擎行为」在隔离临时库里跑真实流转、权限、强制拖拽与回退。

隔离由 tests/conftest.py 保证（DATABASE_URL 指向临时库），这里不做额外设置。
"""
import json

import pytest
from sqlalchemy import select, func

from tests.conftest import auth_headers as _auth_headers

from backend_v2 import workflow_engine as eng
from backend_v2.models import (
    Project, TeamMember, UserAuth, Role, ProjectMember,
    WfTemplate, WfTemplateVersion, WfStateDef, WfTransitionDef,
    WfNodeAclDef, ProjectWfInstance, ProjectWfState, WfForceDragLog,
)


# PHASE_NODES 用到但 role 表里**不存在**的 8 个角色名。这是本引擎按名字存
# subject_name 的直接原因，单独钉住：哪天这些角色被补进 role 表了，
# 这条测试会红，提醒去检查 subject_id 回填。
UNMAPPED_ROLE_NAMES = {
    "工艺工程师", "市场运营", "技术负责人", "管理层",
    "试制负责人", "财务", "责任工程师", "采购",
}


# ══════════════════════════════════════════════════════════════════
# 第一部分：模板保真（不碰数据库）
# ══════════════════════════════════════════════════════════════════

class TestTemplateFidelity:

    def test_every_phase_node_becomes_a_state(self):
        """PHASE_NODES 的每一个节点都要变成状态，一个不漏。"""
        from backend_v2.routes.training_process import PHASE_NODES
        for phases in (eng.HARDWARE_PHASES, eng.SOFTWARE_PHASES):
            states = eng.build_states_for_phases(phases)
            expect = sum(len(PHASE_NODES.get(p) or []) for p in phases)
            assert len(states) == expect, f"{phases} 导入 {len(states)} 个状态，PHASE_NODES 有 {expect} 个节点"

    def test_state_code_is_stable_identity(self):
        """state_code 形如 "<阶段码>-<序号>"，且唯一。

        用 code 不用自增 id：历史迁移改过 phase 的 id，code 不变。
        """
        states = eng.build_states_for_phases(eng.HARDWARE_PHASES)
        codes = [s["state_code"] for s in states]
        assert len(codes) == len(set(codes)), "state_code 有重复"
        assert all("-" in c for c in codes), codes[:5]
        assert "PP1-3" in codes, "PP1 第 3 个节点的 code 应该是 PP1-3"

    def test_gate_nodes_are_marked_and_pending_review(self):
        """门禁节点要标 is_gate，语义为待评审。

        判据是 module 含「阶段门径」而不是节点名——名字会改，module 表达的是
        "这步在平台哪个功能里做"。
        """
        states = eng.build_states_for_phases(eng.HARDWARE_PHASES)
        gates = [s for s in states if s["is_gate"]]
        # 硬件 P0/PP1/PP2/PP3/PP4 各有出口门禁，PP5 是收尾阶段没有
        assert len(gates) == 5, [s["state_code"] for s in gates]
        assert all(s["semantic_state"] == "pending_review" for s in gates)

    def test_every_state_has_a_valid_semantic(self):
        """语义只能是那七个之一，没有第八种。"""
        for phases in (eng.HARDWARE_PHASES, eng.SOFTWARE_PHASES):
            for s in eng.build_states_for_phases(phases):
                assert s["semantic_state"] in eng.SEMANTIC_STATES, s

    def test_exactly_one_initial_and_terminal(self):
        for phases in (eng.HARDWARE_PHASES, eng.SOFTWARE_PHASES):
            states = eng.build_states_for_phases(phases)
            assert sum(1 for s in states if s["is_initial"]) == 1
            assert sum(1 for s in states if s["is_terminal"]) == 1
            assert states[0]["is_initial"]
            assert states[-1]["is_terminal"]

    def test_transitions_form_a_single_chain(self):
        """一期主干是线性链：n 个状态恰好 n-1 条边，且每条都前进不回头。

        一旦有人给某个模板加了分叉，这条会红——那时应该改成"可达性校验"，
        而不是把分叉当 bug。测试红是在提醒做这个决定。
        """
        states = eng.build_states_for_phases(eng.SOFTWARE_PHASES)
        trans = eng.build_transitions(states)
        assert len(trans) == len(states) - 1
        for t in trans:
            assert t["from_state_code"] != t["to_state_code"]

    def test_acls_use_role_name_not_only_role_id(self):
        """ACL 主体按名字存，subject_id 允许为 NULL。

        这是 8 个角色名不在 role 表里的直接后果，也是本设计的要点：
        只按 id 存的话，那 8 个角色名覆盖的节点会变成"没人推得动"。
        """
        states = eng.build_states_for_phases(eng.HARDWARE_PHASES)
        acls = eng.build_acls(states)
        assert acls, "没生成任何 ACL"
        assert all(a["subject_type"] == "role_name" for a in acls)
        assert all(a["subject_name"] for a in acls)
        used = {a["subject_name"] for a in acls}
        assert UNMAPPED_ROLE_NAMES & used, "那 8 个未映射角色名应当真实出现在 ACL 里"

    def test_pm_gets_force_drag_in_template(self):
        """模板默认就给项目经理强制拖拽——需求里的"PM 超级权限"。"""
        states = eng.build_states_for_phases(eng.SOFTWARE_PHASES)
        acls = eng.build_acls(states)
        pm = [a for a in acls if a["subject_name"] == "项目经理"]
        assert pm and all(a["can_force_drag"] for a in pm)
        others = [a for a in acls if a["subject_name"] != "项目经理"]
        assert others and not any(a["can_force_drag"] for a in others)


# ══════════════════════════════════════════════════════════════════
# 第二部分：引擎行为（隔离库）
# ══════════════════════════════════════════════════════════════════

def _role_id(db, name: str) -> int:
    r = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
    if r is None:
        r = Role(name=name, code=name[:12], sort_order=99)
        db.add(r)
        db.flush()
    return r.id


def _pm_user(db, uname: str):
    """建一个项目经理账号（TeamMember + UserAuth + 返回 UserAuth）。"""
    m = TeamMember(name=f"引擎测试{uname}")
    db.add(m)
    db.flush()
    u = UserAuth(username=uname, password_hash="x", member_id=m.id, role="member")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _project_with_pm(db, code: str, project_type: str, pm_username: str = None):
    """建项目 + 一个项目经理成员，返回 (project, pm_user)。"""
    p = Project(name=f"引擎测试项目{code}", code=code, project_type=project_type)
    db.add(p)
    db.flush()
    u = _pm_user(db, pm_username or f"wfpm_{code}")
    db.add(ProjectMember(project_id=p.id, member_id=u.member_id,
                         role_id=_role_id(db, "项目经理")))
    db.commit()
    db.refresh(p)
    return p, u


class TestSeedAndInstantiate:

    def test_templates_seeded(self, client):
        """启动时播种了 A/B 两个模板，各自一个已发布版本。"""
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            codes = {t.code: t for t in db.execute(select(WfTemplate)).scalars().all()}
            assert "A" in codes and "B" in codes
            assert codes["A"].project_type == "hardware"
            assert codes["B"].project_type == "software"
            for t in codes.values():
                n = db.execute(select(func.count()).select_from(WfTemplateVersion)
                               .where(WfTemplateVersion.template_id == t.id)).scalar()
                assert n >= 1
        finally:
            db.close()

    def test_instantiate_is_a_deep_copy_not_a_reference(self, client):
        """项目实例是模板的独立副本——改项目不该动模板。

        这是"项目层可自由调整"的前提：如果是引用，PM 改一个状态就会改到
        所有同模板的项目上。
        """
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-COPY", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            assert inst is not None

            # 改项目层第一个状态的名字与语义
            st = db.execute(select(ProjectWfState).where(
                ProjectWfState.instance_id == inst.id
            ).order_by(ProjectWfState.sort_order)).scalars().first()
            st.name = "被项目改过的名字"
            st.semantic_state = "blocked"
            db.commit()

            # 模板层对应状态必须原封不动
            d = db.execute(select(WfStateDef).where(
                WfStateDef.version_id == inst.current_version_id,
                WfStateDef.state_code == st.state_code,
            )).scalar_one()
            assert d.name != "被项目改过的名字"
            assert d.semantic_state != "blocked"
        finally:
            db.close()

    def test_instantiate_is_idempotent(self, client):
        """重复实例化不重建——重建会把运行态清掉。"""
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-IDEM", "hardware")
            a = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            b = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            assert a.id == b.id
            n = db.execute(select(func.count()).select_from(ProjectWfInstance)
                           .where(ProjectWfInstance.project_id == p.id)).scalar()
            assert n == 1
        finally:
            db.close()

    def test_initial_state_is_in_progress(self, client):
        """第一个节点开局就是进行中，其余未开始。"""
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-INIT", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            states = db.execute(select(ProjectWfState).where(
                ProjectWfState.instance_id == inst.id
            ).order_by(ProjectWfState.sort_order)).scalars().all()
            assert states[0].runtime_status == "in_progress"
            assert all(s.runtime_status == "not_started" for s in states[1:])
        finally:
            db.close()


class TestPermissionResolution:

    def test_pm_has_force_drag(self, client):
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-PM", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            roles = eng.my_roles(db, p.id, u)
            assert "项目经理" in roles
            perm = eng.resolve_permissions(db, inst.id, "S0-1", u, roles)
            assert perm["can_force_drag"] is True
        finally:
            db.close()

    def test_non_pm_member_gets_no_force_drag(self, client):
        """普通成员没有强制拖拽——哪怕他是模板 ACL 里的角色。"""
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-NOPM", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            # 加一个软件工程师
            m = TeamMember(name="引擎测试软件工程师")
            db.add(m)
            db.flush()
            u2 = UserAuth(username="wfe_sw", password_hash="x", member_id=m.id, role="member")
            db.add(u2)
            db.flush()
            db.add(ProjectMember(project_id=p.id, member_id=m.id,
                                 role_id=_role_id(db, "软件工程师")))
            db.commit()

            roles = eng.my_roles(db, p.id, u2)
            perm = eng.resolve_permissions(db, inst.id, "S0-1", u2, roles)
            assert perm["can_force_drag"] is False
        finally:
            db.close()

    def test_unmapped_role_name_still_matches(self, client):
        """role 表里不存在的角色名，按名字匹配照样生效。

        这是本引擎最关键的一条兼容性：PHASE_NODES 用了 8 个 role 表里没有的
        角色名，只按 subject_id 匹配的话这些节点会变成"没人推得动"。
        """
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-UNMAPPED", "hardware")
            inst = eng.instantiate(db, p, created_by=u.username)

            m = TeamMember(name="引擎测试技术负责人")
            db.add(m)
            db.flush()
            u2 = UserAuth(username="wfe_lead", password_hash="x", member_id=m.id, role="member")
            db.add(u2)
            db.flush()
            db.add(ProjectMember(project_id=p.id, member_id=m.id,
                                 role_id=_role_id(db, "技术负责人")))
            db.commit()

            roles = eng.my_roles(db, p.id, u2)
            assert "技术负责人" in roles
            # PP1-2「系统架构设计方案」的 roles 含技术负责人
            perm = eng.resolve_permissions(db, inst.id, "PP1-2", u2, roles)
            assert perm["can_exit"] is True, f"未映射角色名没匹配上: {perm}"
            assert "role_name:技术负责人" in perm["matched"]
        finally:
            db.close()

    def test_no_acl_match_means_no_permission(self, client):
        """一条 ACL 都没匹配上就是没权限——不回退到 projects.edit。

        既有 _can_confirm_node 有那个兜底，新引擎故意不继承：继承了的话
        权限矩阵怎么配都无所谓，等于没配。
        """
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-NONE", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            m = TeamMember(name="引擎测试无关人员")
            db.add(m)
            db.flush()
            u2 = UserAuth(username="wfe_nobody", password_hash="x", member_id=m.id, role="member")
            db.add(u2)
            db.flush()
            db.add(ProjectMember(project_id=p.id, member_id=m.id,
                                 role_id=_role_id(db, "商务经理")))
            db.commit()

            roles = eng.my_roles(db, p.id, u2)
            perm = eng.resolve_permissions(db, inst.id, "S1-3", u2, roles)
            assert perm["can_exit"] is False
            assert perm["can_force_drag"] is False
        finally:
            db.close()

    def test_admin_always_has_everything(self, client):
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, _ = _project_with_pm(db, "WFE-ADMIN", "software")
            m = TeamMember(name="引擎测试管理员")
            db.add(m)
            db.flush()
            adm = UserAuth(username="wfe_admin", password_hash="x",
                           member_id=m.id, role="admin")
            db.add(adm)
            db.commit()
            inst = eng.instantiate(db, p, created_by="x")
            db.commit()
            perm = eng.resolve_permissions(db, inst.id, "S2-5", adm, [])
            assert all(perm[a] is True for a in eng.PERM_ATOMS)
        finally:
            db.close()


class TestTransitions:

    def test_advance_moves_the_pointer(self, client):
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-ADV", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            roles = eng.my_roles(db, p.id, u)
            eng.advance(db, p, inst, "S0-1", "S0-2", u, roles)
            db.commit()

            st = {s.state_code: s for s in db.execute(select(ProjectWfState).where(
                ProjectWfState.instance_id == inst.id)).scalars().all()}
            assert st["S0-1"].runtime_status == "completed"
            assert st["S0-2"].runtime_status == "in_progress"
            assert st["S0-3"].runtime_status == "not_started"
        finally:
            db.close()

    def test_advance_rejects_disallowed_edge(self, client):
        """不是一条允许的边 → 400。"""
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-BADEDGE", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            roles = eng.my_roles(db, p.id, u)
            with pytest.raises(eng.WfError) as ei:
                eng.advance(db, p, inst, "S0-1", "S2-3", u, roles)
            assert ei.value.status_code == 400
        finally:
            db.close()

    def test_advance_enforces_permission_server_side(self, client):
        """没权限的人推不动——这条是本次的核心承诺（服务端强制校验）。"""
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, pm = _project_with_pm(db, "WFE-ENFORCE", "software")
            inst = eng.instantiate(db, p, created_by=pm.username)
            m = TeamMember(name="引擎测试外包")
            db.add(m)
            db.flush()
            u2 = UserAuth(username="wfe_outsider", password_hash="x",
                          member_id=m.id, role="member")
            db.add(u2)
            db.flush()
            db.add(ProjectMember(project_id=p.id, member_id=m.id,
                                 role_id=_role_id(db, "商务经理")))
            db.commit()

            roles = eng.my_roles(db, p.id, u2)
            with pytest.raises(eng.WfError) as ei:
                eng.advance(db, p, inst, "S1-5", "S1-6", u2, roles)
            assert ei.value.status_code == 403
            assert "退出权限" in ei.value.detail
        finally:
            db.close()

    def test_set_status_requires_reason_for_blocked(self, client):
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-BLOCK", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            roles = eng.my_roles(db, p.id, u)
            with pytest.raises(eng.WfError) as ei:
                eng.set_status(db, p, inst, "S0-1", "blocked", u, roles)
            assert ei.value.status_code == 400
            eng.set_status(db, p, inst, "S0-1", "blocked", u, roles, "等客户确认接口")
            db.commit()
            st = db.execute(select(ProjectWfState).where(
                ProjectWfState.instance_id == inst.id,
                ProjectWfState.state_code == "S0-1")).scalar_one()
            assert st.runtime_status == "blocked"
        finally:
            db.close()


class TestForceDrag:

    def test_force_drag_requires_reason_when_skipping_required(self, client):
        """跳过必经验证节点必须填原因——需求第 5 项的第一条。"""
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-FD-REASON", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            roles = eng.my_roles(db, p.id, u)
            with pytest.raises(eng.WfError) as ei:
                eng.force_drag(db, p, inst, "S1-5", u, roles)
            assert ei.value.status_code == 400
            assert "原因" in ei.value.detail
        finally:
            db.close()

    def test_force_drag_records_audit_snapshot(self, client):
        """审计字段要能独立复述当时发生了什么，不靠 join 现算。"""
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-FD-AUDIT", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            roles = eng.my_roles(db, p.id, u)
            r = eng.force_drag(db, p, inst, "S1-5", u, roles, "客户催进度，先过")
            db.commit()

            log = db.get(WfForceDragLog, r["force_drag_log_id"])
            assert log is not None
            assert log.operator == u.username
            assert log.reason == "客户催进度，先过"
            assert log.reason_required is True
            assert log.to_state_code == "S1-5"
            assert log.from_state_code == "S0-1"
            skipped = json.loads(log.skipped_states)
            codes = [s["state_code"] for s in skipped]
            # S0-1 之后到 S1-5 之间：S0 剩余 + S1 前 4 个
            assert "S0-2" in codes and "S1-4" in codes
            assert log.auto_backlog_created is True
        finally:
            db.close()

    def test_force_drag_denied_for_non_pm(self, client):
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, pm = _project_with_pm(db, "WFE-FD-DENY", "software")
            inst = eng.instantiate(db, p, created_by=pm.username)
            m = TeamMember(name="引擎测试普通成员")
            db.add(m)
            db.flush()
            u2 = UserAuth(username="wfe_fd_nobody", password_hash="x",
                          member_id=m.id, role="member")
            db.add(u2)
            db.flush()
            db.add(ProjectMember(project_id=p.id, member_id=m.id,
                                 role_id=_role_id(db, "软件工程师")))
            db.commit()
            roles = eng.my_roles(db, p.id, u2)
            with pytest.raises(eng.WfError) as ei:
                eng.force_drag(db, p, inst, "S1-5", u2, roles, "我就是想跳")
            assert ei.value.status_code == 403
            assert "项目经理" in ei.value.detail
        finally:
            db.close()

    def test_force_drag_does_not_fake_verification(self, client):
        """被跳过的验证节点不能置成 completed——那是撒谎，补验证待办也没了对象。"""
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-FD-NOFAKE", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            roles = eng.my_roles(db, p.id, u)
            r = eng.force_drag(db, p, inst, "S1-5", u, roles, "先过")
            db.commit()

            st = {s.state_code: s for s in db.execute(select(ProjectWfState).where(
                ProjectWfState.instance_id == inst.id)).scalars().all()}
            skipped = json.loads(db.get(WfForceDragLog, r["force_drag_log_id"]).skipped_states)
            assert skipped, "这次拖拽应当跳过了节点"

            # 不变量（不猜具体节点，逐条按语义校验）：
            #   执行类被跳过 → 算做过了，置 completed
            #   验证/评审类被跳过 → **绝不能**是 completed，否则就是撒谎，
            #     补验证待办也没了对象
            saw_exec, saw_verify = False, False
            for item in skipped:
                s = st[item["state_code"]]
                if s.semantic_state == "in_progress":
                    assert s.runtime_status == "completed", \
                        f"{s.state_code} 是执行类，跳过它应当置完成"
                    saw_exec = True
                elif s.semantic_state in ("pending_verify", "pending_review"):
                    assert s.runtime_status != "completed", \
                        f"{s.state_code} 是{s.semantic_state}，被跳过却置成了完成"
                    saw_verify = True
            # 两类的样本都要出现过，否则这条测试可能什么都没验到
            assert saw_exec and saw_verify, f"样本不足: exec={saw_exec} verify={saw_verify}"
        finally:
            db.close()

    def test_revert_restores_previous_position(self, client):
        """回退把位置还原，且不能重复回退。"""
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-REVERT", "software")
            inst = eng.instantiate(db, p, created_by=u.username)
            db.commit()
            roles = eng.my_roles(db, p.id, u)
            r = eng.force_drag(db, p, inst, "S1-5", u, roles, "先过")
            db.commit()

            eng.revert_force_drag(db, p, inst, r["force_drag_log_id"], u, roles, "拖错了")
            db.commit()

            st = {s.state_code: s for s in db.execute(select(ProjectWfState).where(
                ProjectWfState.instance_id == inst.id)).scalars().all()}
            assert st["S0-1"].runtime_status == "in_progress"
            assert st["S1-5"].runtime_status == "not_started"

            log = db.get(WfForceDragLog, r["force_drag_log_id"])
            assert log.is_reverted is True
            assert log.reverted_by == u.username

            with pytest.raises(eng.WfError) as ei:
                eng.revert_force_drag(db, p, inst, r["force_drag_log_id"], u, roles, "再退一次")
            assert ei.value.status_code == 409
        finally:
            db.close()

    def test_revert_denied_for_non_pm(self, client):
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, pm = _project_with_pm(db, "WFE-REV-DENY", "hardware")
            inst = eng.instantiate(db, p, created_by=pm.username)
            db.commit()
            pm_roles = eng.my_roles(db, p.id, pm)
            r = eng.force_drag(db, p, inst, "PP1-3", pm, pm_roles, "先过")
            db.commit()

            m = TeamMember(name="引擎测试路人")
            db.add(m)
            db.flush()
            u2 = UserAuth(username="wfe_rev_nobody", password_hash="x",
                          member_id=m.id, role="member")
            db.add(u2)
            db.flush()
            db.add(ProjectMember(project_id=p.id, member_id=m.id,
                                 role_id=_role_id(db, "结构工程师")))
            db.commit()
            roles = eng.my_roles(db, p.id, u2)
            with pytest.raises(eng.WfError) as ei:
                eng.revert_force_drag(db, p, inst, r["force_drag_log_id"], u2, roles, "我也要退")
            assert ei.value.status_code == 403
        finally:
            db.close()


class TestApi:

    def test_engine_view_payload(self, client):
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-API", "software", pm_username="wfapi_pm")
            pid = p.id
        finally:
            db.close()

        h = _auth_headers(client,"wfapi_pm", "member")
        r = client.get(f"/api/projects/{pid}/wf-engine", headers=h)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["supported"] is True
        assert data["template"]["code"] == "B"
        assert data["template"]["is_migrated"] is False
        assert data["summary"]["total"] == len(data["states"])
        # 泳道覆盖 S0-S3 四段
        assert [l["lane"] for l in data["lanes"]] == ["S0", "S1", "S2", "S3"]
        # 每个状态都带四类权限原子
        for s in data["states"]:
            assert set(s["can"]) == set(eng.PERM_ATOMS)
        assert data["me"]["roles"] == ["项目经理"]
        assert data["me"]["is_pm"] is True

    def test_transition_endpoint_enforces_permission(self, client):
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, pm = _project_with_pm(db, "WFE-API-403", "software", pm_username="wfapi_pm2")
            pid = p.id
            m = TeamMember(name="引擎测试无权限者")
            db.add(m)
            db.flush()
            u2 = UserAuth(username="wfapi_nobody", password_hash="x",
                          member_id=m.id, role="member")
            db.add(u2)
            db.flush()
            db.add(ProjectMember(project_id=p.id, member_id=m.id,
                                 role_id=_role_id(db, "商务经理")))
            db.commit()
        finally:
            db.close()

        h = _auth_headers(client,"wfapi_nobody", "member")
        r = client.post(f"/api/projects/{pid}/wf-engine/states/S1-5/transition",
                        json={"to_state_code": "S1-6"}, headers=h)
        assert r.status_code == 403, r.text
        assert "退出权限" in r.json()["detail"]

    def test_non_member_cannot_view_engine_even_with_projects_view(self, client):
        """回归：非项目成员不能看别人项目的状态机——哪怕权限矩阵里有 projects.view。

        这个洞是活体验证脚本发现的，当时的单测漏了：老的越权测试用裸 UserAuth 行
        造人，permissions 是空的，走不到 check_permission 那条分支；而**真实建号**
        （POST /api/team-members）会经 resolve_new_user_matrix 拿到一份默认 member
        矩阵，里面含 projects.view。于是 _ensure_access 早期多写的那条
        check_permission("projects","view") 会让任何登录用户看到任意项目的状态机，
        比它所在的项目详情页 GET /api/projects/{id}（projects.py:396-400，只认
        项目成员）还宽。这里用真实建号接口复现那条路径。
        """
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, _ = _project_with_pm(db, "WFE-API-LEAK", "software", pm_username="wfleak_pm")
            pid = p.id
        finally:
            db.close()

        admin_h = _auth_headers(client, "wfleak_admin", "admin")
        r = client.post("/api/team-members", headers=admin_h, json={
            "name": "引擎测试越权者", "username": "wfleak_nobody",
            "password": "pw12345", "accRole": "member",
        })
        assert r.status_code == 201, r.text
        assert r.json()["account_created"] is True, r.text

        # 前提校验：这个人必须真的拿到了含 projects.view 的矩阵，否则本测试是空的
        # ——没复现出当年的条件，绿了也说明不了问题。所以这里主动断言前提。
        from backend_v2.permissions import check_permission as _cp
        with SessionLocal() as db2:
            u = db2.execute(
                select(UserAuth).where(UserAuth.username == "wfleak_nobody")
            ).scalar_one()
            assert u.member_id is not None, "建号应绑定人员"
            assert _cp(u, "projects", "view") is True, \
                "前提不成立：该账号没有 projects.view，本测试测不到当初那条分支"

        # make_user 只重置 password/role，不动 permissions/member_id，
        # 所以这里登录到的仍是「有 projects.view、但不属于该项目」的那个人。
        h = _auth_headers(client, "wfleak_nobody", "member")
        r = client.get(f"/api/projects/{pid}/wf-engine", headers=h)
        assert r.status_code == 403, f"非项目成员看到了状态机: {r.status_code} {r.text}"

        r = client.post(f"/api/projects/{pid}/wf-engine/states/S0-1/transition",
                        json={"to_state_code": "S0-2"}, headers=h)
        assert r.status_code == 403, r.text

    def test_force_drag_endpoint_and_log_listing(self, client):
        from backend_v2.database import SessionLocal
        db = SessionLocal()
        try:
            p, u = _project_with_pm(db, "WFE-API-FD", "software", pm_username="wfapi_pm3")
            pid = p.id
        finally:
            db.close()

        h = _auth_headers(client,"wfapi_pm3", "member")
        # 缺原因 → 400
        r = client.post(f"/api/projects/{pid}/wf-engine/force-drag",
                        json={"to_state_code": "S1-5"}, headers=h)
        assert r.status_code == 400, r.text

        r = client.post(f"/api/projects/{pid}/wf-engine/force-drag",
                        json={"to_state_code": "S1-5", "reason": "客户催"}, headers=h)
        assert r.status_code == 200, r.text
        log_id = r.json()["force_drag_log_id"]

        r = client.get(f"/api/projects/{pid}/wf-engine/force-drag-logs", headers=h)
        assert r.status_code == 200
        logs = r.json()
        assert logs and logs[0]["id"] == log_id
        assert logs[0]["reason"] == "客户催"
        assert logs[0]["is_reverted"] is False

        r = client.post(f"/api/projects/{pid}/wf-engine/force-drag/{log_id}/revert",
                        json={"reason": "拖错了"}, headers=h)
        assert r.status_code == 200, r.text

    def test_templates_endpoint(self, client):
        h = _auth_headers(client,"wfapi_tpl", "member")
        r = client.get("/api/wf-engine/templates", headers=h)
        assert r.status_code == 200
        codes = {t["code"] for t in r.json()}
        assert {"A", "B"} <= codes

    def test_backfill_requires_admin(self, client):
        h = _auth_headers(client,"wfapi_member", "member")
        r = client.post("/api/wf-engine/backfill", headers=h)
        assert r.status_code == 403

    def test_backfill_is_idempotent(self, client):
        h = _auth_headers(client,"wfapi_admin", "admin")
        r = client.post("/api/wf-engine/backfill", headers=h)
        assert r.status_code == 200, r.text
        first = r.json()
        r2 = client.post("/api/wf-engine/backfill", headers=h)
        assert r2.status_code == 200
        # 第二次不该再新建任何实例
        assert r2.json()["created"] == []
        assert set(r2.json()["skipped"]) >= set(first["created"])
