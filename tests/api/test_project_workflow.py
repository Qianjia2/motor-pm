"""项目工作流接口测试:GET /api/projects/{pid}/workflow 与线下步骤确认。

分两部分:

一、映射忠实性(不碰数据库)
    workflow_map 的节点→标准映射必须与 PHASE_NODES 和 database.py 的
    交付物定义逐条对得上。这组断言的意义在于:映射写错不会报错,只会让界面
    静默显示错误状态(标准名对不上就是永远"未开始",对过头就是交付物批了
    步骤还亮着)。所以用测试把它焊死。

二、接口行为(隔离库)
    状态推导、口径一致(界面说能发起 == 接口真能发起)、确认的权限与幂等。
"""
import ast
import pathlib

import pytest

from tests.conftest import auth_headers

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DATABASE_PY = REPO_ROOT / "backend_v2" / "database.py"

SOFTWARE_PHASES = ("S0", "S1", "S2", "S3")
HARDWARE_PHASES = ("P0", "PP1", "PP2", "PP3", "PP4", "PP5")

# 权威清单散在两个函数里,都要读。硬件那份是后补的:在此之前硬件标准只存在于
# 现网库,没有代码定义,所以硬件的映射没有任何覆盖性断言管得住。
SEED_FNS = ("_seed_software_standards", "_seed_hardware_standards")


# ═══════════════ 一、映射忠实性 ═══════════════

def _seed_definitions():
    """从 database.py 的 _seed_*_standards 读交付物定义(AST,不 import 执行)。

    权威清单在代码里,迁移脚本 migrate_software_deliverables.py 也是这么读的。
    """
    tree = ast.parse(DATABASE_PY.read_text(encoding="utf-8"))
    out = {}
    for fn_name in SEED_FNS:
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == fn_name), None)
        assert fn is not None, f"database.py 里找不到 {fn_name}"
        assign = next(n for n in ast.walk(fn)
                      if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "standards")
        for e in assign.value.elts:
            phase_code, name = ast.literal_eval(e)[:2]
            out.setdefault(phase_code, set()).add(name)
    assert out, "未读到交付物定义"
    return out


def test_every_mapped_seq_exists_and_node_name_matches():
    """映射里的 seq 必须在 PHASE_NODES 里存在,且登记的节点名与实际完全相等。

    节点改名而映射没跟着改,是这张表最容易悄悄失效的方式。
    """
    from backend_v2.routes.training_process import PHASE_NODES
    from backend_v2.workflow_map import WORKFLOW_NODE_STANDARDS, expected_node_name

    for phase_code, entries in WORKFLOW_NODE_STANDARDS.items():
        nodes = {n["seq"]: n for n in PHASE_NODES.get(phase_code) or []}
        assert nodes, f"PHASE_NODES 里没有阶段 {phase_code}"
        for seq, entry in entries.items():
            assert seq in nodes, f"{phase_code} 第 {seq} 步在 PHASE_NODES 里不存在"
            assert entry["node"] == nodes[seq]["name"], (
                f"{phase_code} 第 {seq} 步节点名漂移: 映射写「{entry['node']}」,"
                f"实际是「{nodes[seq]['name']}」"
            )
            assert entry["node"] == expected_node_name(phase_code, seq)


def test_no_mapping_for_gate_nodes():
    """门禁节点不参与映射(它的状态由签核记录推导,不挂交付物)。"""
    from backend_v2.routes.training_process import PHASE_NODES
    from backend_v2.workflow_map import WORKFLOW_NODE_STANDARDS

    for phase_code, entries in WORKFLOW_NODE_STANDARDS.items():
        for node in PHASE_NODES[phase_code]:
            if (node.get("module") or "").endswith("阶段门径"):
                assert node["seq"] not in entries, (
                    f"{phase_code} 第 {node['seq']} 步是门禁节点,不该有交付物映射"
                )


def test_mapping_covers_all_defined_standards_exactly_once():
    """每个阶段:映射 ∪ 白名单 == 该阶段全部交付物定义,且两集合不相交。

    这条会在「新增/改名一条标准但没决定它归哪一步」时变红——正是想要的,
    否则新标准会静默地既不属于任何步骤、也不出现在"无对应步骤"清单里。
    """
    from backend_v2.workflow_map import (
        STANDARDS_NOT_IN_SEED, STANDARDS_WITHOUT_NODE, covered_standard_names,
        mapped_standard_names,
    )

    defined = _seed_definitions()
    for phase_code in SOFTWARE_PHASES + HARDWARE_PHASES:
        expect = set(defined.get(phase_code) or []) | set(STANDARDS_NOT_IN_SEED.get(phase_code) or [])
        covered = covered_standard_names(phase_code)
        assert covered == expect, (
            f"{phase_code} 覆盖不全。\n"
            f"  定义里有、映射没有: {sorted(expect - covered)}\n"
            f"  映射有、定义里没有: {sorted(covered - expect)}"
        )
        overlap = mapped_standard_names(phase_code) & set(STANDARDS_WITHOUT_NODE.get(phase_code) or [])
        assert not overlap, f"{phase_code} 有标准同时被挂到步骤又列进白名单: {sorted(overlap)}"


def test_mapped_names_not_in_seed_are_declared():
    """映射里引用的标准名,要么在交付物定义里,要么在 STANDARDS_NOT_IN_SEED 里声明过。

    防的是"映射写了个不存在的标准名"——那种情况下步骤会永远显示未开始。
    """
    from backend_v2.workflow_map import STANDARDS_NOT_IN_SEED, WORKFLOW_NODE_STANDARDS

    defined = _seed_definitions()
    for phase_code, entries in WORKFLOW_NODE_STANDARDS.items():
        known = set(defined.get(phase_code) or []) | set(STANDARDS_NOT_IN_SEED.get(phase_code) or [])
        for seq, entry in entries.items():
            unknown = set(entry["standards"]) - known
            assert not unknown, (
                f"{phase_code} 第 {seq} 步引用了不存在的交付物标准: {sorted(unknown)}"
            )


# ═══════════════ 二、接口行为 ═══════════════

def _software_project(client, admin, code):
    r = client.post("/api/projects", json={
        "name": f"工作流测试{code}", "code": code, "project_type": "software",
    }, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def admin(client):
    return auth_headers(client, "wf_admin", "admin")


@pytest.fixture(scope="module")
def workflow_project(client, admin):
    return _software_project(client, admin, "WF-T1")


def _workflow(client, headers, pid, **params):
    r = client.get(f"/api/projects/{pid}/workflow", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _phase(wf, code):
    return next(p for p in wf["phases"] if p["phase_code"] == code)


def _std_ids(pid, phase_code, names):
    """取该阶段这些标准 id(用于后续 upsert 交付物时对齐)。"""
    from sqlalchemy import select
    from backend_v2.database import SessionLocal
    from backend_v2.models import GateDeliverableStandard, Phase

    with SessionLocal() as db:
        phase_id = db.execute(select(Phase.id).where(Phase.code == phase_code)).scalar_one()
        rows = db.execute(select(GateDeliverableStandard.id, GateDeliverableStandard.name).where(
            GateDeliverableStandard.phase_id == phase_id,
            GateDeliverableStandard.name.in_(names),
        )).all()
    return {name: sid for sid, name in rows}


def _set_deliverable(pid, phase_code, name, status):
    """直接写库把某个交付物置为指定状态(走 API 要传文件,这里只验状态推导)。"""
    from sqlalchemy import select
    from backend_v2.database import SessionLocal
    from backend_v2.models import Deliverable, Phase

    with SessionLocal() as db:
        phase_id = db.execute(select(Phase.id).where(Phase.code == phase_code)).scalar_one()
        d = db.execute(select(Deliverable).where(
            Deliverable.project_id == pid, Deliverable.phase_id == phase_id,
            Deliverable.name == name,
        )).scalar_one_or_none()
        if d is None:
            d = Deliverable(project_id=pid, phase_id=phase_id, name=name, status=status)
            db.add(d)
        else:
            d.status = status
        db.commit()
        return d.id


def _hardware_project(client, admin, code):
    r = client.post("/api/projects", json={
        "name": f"工作流硬件{code}", "code": code, "project_type": "hardware",
    }, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()["id"]


JINLIANG_CODE = "JL-2025-001"   # 硬件试点就这一个,写死是为了改动白名单时这里必须有人来改


@pytest.fixture(scope="module")
def jinliang(client, admin):
    """金浪的真实项目在现网库里,测试库没有——按编号现建一个。

    等价性成立:判定看的是项目编号(project.code)不是自增 id,所以测试库里建一个
    同编号的项目,与现网那个金浪走的是同一条判定路径。
    """
    return _hardware_project(client, admin, JINLIANG_CODE)


@pytest.fixture(scope="module")
def closed_hardware(client, admin):
    """一个没开放的硬件项目,用来证明"关着"这条也真的关着。"""
    return _hardware_project(client, admin, "WF-HW-CLOSED")


class TestWorkflowOptIn:
    """工作流是一项目一开放,不是按 project_type 一刀切。

    金浪是硬件里唯一开放的试点(见 workflow_map.WORKFLOW_OPT_IN_CODES)。这组断言
    钉住两件事:金浪必须开着(掉了试点就白做了),别的硬件项目必须关着(放开了
    会有一堆点进去空白的页签)。
    """

    def test_software_is_always_supported(self):
        from backend_v2.workflow_map import supports_workflow
        for code in ("BJJD-2026-001", "SW-WF-DEMO", "", None):
            assert supports_workflow("software", code) is True

    def test_only_jinliang_hardware_is_supported(self):
        from backend_v2.workflow_map import supports_workflow
        assert supports_workflow("hardware", JINLIANG_CODE) is True, (
            f"金浪({JINLIANG_CODE})是硬件唯一试点,被关掉了整个硬件方向就没案例了"
        )
        # 大小写不同、前后有空格都算不同项目——白名单是精确匹配,不是"像就行"
        for code in ("SS-2023-001", "BJ-001", "jl-2025-001", " JL-2025-001", "", None):
            assert supports_workflow("hardware", code) is False, (
                f"硬件项目 {code!r} 不该开放工作流"
            )

    def test_jinliang_project_gets_supported_payload(self, client, admin, jinliang):
        wf = _workflow(client, admin, jinliang)
        assert wf["supported"] is True, "白名单说开放,接口却说 supported=False"
        assert [p["phase_code"] for p in wf["phases"]] == list(HARDWARE_PHASES), (
            f"硬件阶段清单不对:{[p['phase_code'] for p in wf['phases']]}"
        )

    def test_other_hardware_project_is_not_supported(self, client, admin, closed_hardware):
        """接口层的门与白名单同真同假。白名单改了但接口没跟上,这里会红。"""
        wf = _workflow(client, admin, closed_hardware)
        assert wf["supported"] is False
        assert wf["phases"] == []

    def test_hardware_steps_declare_a_state_source(self, client, admin, jinliang):
        """硬件也要走同一套状态口径,不能因为是新接进来的就漏掉 state_source。

        与 TestWorkflowPayload 那条同名断言的区别:那条只跑软件项目,这条跑硬件,
        而硬件是后接进来的那一半,最容易在口径上被漏掉。
        """
        wf = _workflow(client, admin, jinliang)
        allowed = {"deliverable", "gate", "manual"}
        for ph in wf["phases"]:
            for step in ph["steps"]:
                assert step["state_source"] in allowed, step
                if step["kind"] == "gate":
                    assert step["state_source"] == "gate"
                if step["kind"] == "deliverable":
                    assert step["standards"], f"{ph['phase_code']}#{step['seq']} 无标准却算交付物步骤"

    def test_hardware_map_covers_every_working_node(self, client, admin, jinliang):
        """44 个工作节点一个都不能少:漏挂的节点在界面上是永久的"未开始"。

        8 个空挂是明确的(见 workflow_map 的注释),所以钉住的是总数而不是"每步都有"。
        """
        wf = _workflow(client, admin, jinliang)
        work = [s for ph in wf["phases"] for s in ph["steps"] if s["kind"] != "gate"]
        with_std = [s for s in work if s["standards"]]
        assert len(work) == 44, f"硬件工作节点数变了: {len(work)}"
        assert len(with_std) == 36, f"挂了标准的节点数变了: {len(with_std)}"

    def test_project_list_only_returns_open_projects(self, client, admin, jinliang,
                                                     closed_hardware, workflow_project):
        r = client.get("/api/workflow/projects", headers=admin)
        assert r.status_code == 200, r.text
        codes = {p["code"] for p in r.json()}
        assert closed_hardware and "WF-HW-CLOSED" not in codes, (
            "没开放的硬件项目出现在项目列表里了"
        )
        assert JINLIANG_CODE in codes
        assert "WF-T1" in codes, "软件项目应该都在列表里"


class TestWorkflowPayload:
    def test_software_project_has_four_phases(self, client, admin, workflow_project):
        wf = _workflow(client, admin, workflow_project)
        assert wf["supported"] is True
        assert [p["phase_code"] for p in wf["phases"]] == list(SOFTWARE_PHASES)

    def test_hardware_project_is_not_supported(self, client, admin):
        r = client.post("/api/projects", json={
            "name": "工作流测试硬件", "code": "WF-HW", "project_type": "hardware",
        }, headers=admin)
        assert r.status_code == 201, r.text
        wf = _workflow(client, admin, r.json()["id"])
        assert wf["supported"] is False
        assert wf["phases"] == []

    def test_unknown_project_404(self, client, admin):
        assert client.get("/api/projects/999999/workflow", headers=admin).status_code == 404

    def test_phase_code_filter(self, client, admin, workflow_project):
        wf = _workflow(client, admin, workflow_project, phase_code="S1")
        assert [p["phase_code"] for p in wf["phases"]] == ["S1"]

    def test_steps_match_training_process_flow(self, client, admin, workflow_project):
        """同一个 PHASE_NODES,两处渲染必须逐字段一致(工作流页不是另一套定义)。"""
        flow = client.get("/api/training/process-flow",
                          params={"project_type": "software"}, headers=admin).json()
        flow_nodes = {}
        for st in flow["stages"]:
            for n in st.get("nodes") or []:
                flow_nodes[(st.get("phase_code"), n["seq"])] = n
        assert flow_nodes, "流程页没返回任何节点"

        wf = _workflow(client, admin, workflow_project)
        checked = 0
        for ph in wf["phases"]:
            for step in ph["steps"]:
                key = (ph["phase_code"], step["seq"])
                if key not in flow_nodes:
                    continue
                ref, got = flow_nodes[key], step["node"]
                for field in ("seq", "name", "venue", "roles", "actions", "output",
                              "handoff", "module", "tip"):
                    assert got.get(field) == ref.get(field), (
                        f"{key} 字段 {field} 不一致: 工作流={got.get(field)!r} 流程页={ref.get(field)!r}"
                    )
                checked += 1
        assert checked >= 30, f"只比对了 {checked} 个节点,流程页可能没返回节点"

    def test_every_step_declares_a_state_source(self, client, admin, workflow_project):
        """每一步都要说得出状态从哪来,且四种来源都是已知值。

        state_source 是这张页面的诚实性所在:平台没数据的步骤必须自认是人工确认,
        不能假装有推导依据。
        """
        wf = _workflow(client, admin, workflow_project)
        allowed = {"deliverable", "gate", "manual"}
        for ph in wf["phases"]:
            for step in ph["steps"]:
                assert step["state_source"] in allowed, step
                assert step["state"] in {
                    "done", "in_progress", "pending_confirm", "blocked", "not_started"}
                if step["kind"] == "gate":
                    assert step["state_source"] == "gate"
                    assert step["confirmable"] is False
                if step["kind"] == "deliverable":
                    assert step["standards"], f"{ph['phase_code']}#{step['seq']} 无标准却算交付物步骤"


class TestStateDerivation:
    def test_approving_deliverable_completes_step(self, client, admin):
        pid = _software_project(client, admin, "WF-T2")
        before = _phase(_workflow(client, admin, pid), "S2")
        step = next(s for s in before["steps"] if s["seq"] == 1)
        assert step["standards"][0]["standard_name"] == "软件测试计划"
        assert step["state"] == "not_started"

        _set_deliverable(pid, "S2", "软件测试计划", "submitted")
        step = next(s for s in _phase(_workflow(client, admin, pid), "S2")["steps"] if s["seq"] == 1)
        assert step["state"] == "in_progress", "已提交(未批)应是在进行中"
        assert step["standards"][0]["satisfied"] is False  # 必交,必须 approved

        _set_deliverable(pid, "S2", "软件测试计划", "approved")
        step = next(s for s in _phase(_workflow(client, admin, pid), "S2")["steps"] if s["seq"] == 1)
        assert step["state"] == "done"
        assert step["standards"][0]["satisfied"] is True

    def test_rejected_deliverable_blocks_step(self, client, admin):
        pid = _software_project(client, admin, "WF-T3")
        _set_deliverable(pid, "S1", "代码评审记录", "rejected")
        step = next(s for s in _phase(_workflow(client, admin, pid), "S1")["steps"] if s["seq"] == 7)
        assert step["state"] == "blocked"

    def test_multi_standard_step_needs_all(self, client, admin):
        """一个步骤对多条标准时,全部达标才算完成。

        用 S1 第 3 步(技术选型报告/接口设计文档/数据库设计)——这三条名字互不包含,
        不会被下面的子串匹配兜住,能真正验出"少一条不算完成"。
        """
        pid = _software_project(client, admin, "WF-T4")
        step3 = lambda: next(s for s in _phase(_workflow(client, admin, pid), "S1")["steps"]
                             if s["seq"] == 3)
        assert len(step3()["standards"]) == 3

        _set_deliverable(pid, "S1", "技术选型报告", "approved")
        assert step3()["state"] != "done", "只批了一条标准就算完成是错的"

        _set_deliverable(pid, "S1", "接口设计文档（API/数据字典）", "approved")
        assert step3()["state"] != "done", "三条标准只批两条就算完成是错的"

        _set_deliverable(pid, "S1", "数据库/数据模型设计", "approved")
        assert step3()["state"] == "done"

    def test_substring_overlap_is_intentional_and_shared_with_gate(self, client, admin):
        """名称互相包含的标准会互相兜底——这是既有匹配规则的特性,不是本页引入的。

        例:S3「客户验收」同时挂「验收记录」和「用户验收记录」,而"验收记录"是
        "用户验收记录"的子串,所以批一份「验收记录」两条标准都算达标。门禁那边
        (_missing_required_deliverables)用的是同一套规则,所以本页显示"已完成"
        与门禁真的能过是一致的。这里把它钉住:一旦有人改了匹配规则,这条会红,
        提醒同步改门禁,避免两边口径分叉。
        """
        pid = _software_project(client, admin, "WF-T6")
        _set_deliverable(pid, "S3", "验收记录", "approved")
        step = next(s for s in _phase(_workflow(client, admin, pid), "S3")["steps"] if s["seq"] == 7)
        by_name = {s["standard_name"]: s for s in step["standards"]}
        assert by_name["验收记录"]["satisfied"] is True
        assert by_name["用户验收记录"]["satisfied"] is True, (
            "子串匹配规则变了:请同步确认 gate_reviews 的匹配逻辑是否也变了"
        )

    def test_progress_counts_move_with_deliverables(self, client, admin):
        pid = _software_project(client, admin, "WF-T5")
        before = _phase(_workflow(client, admin, pid), "S0")["progress"]
        _set_deliverable(pid, "S0", "软件需求分析文档", "approved")
        after = _phase(_workflow(client, admin, pid), "S0")["progress"]
        assert after["required_approved"] == before["required_approved"] + 1
        assert after["steps_done"] == before["steps_done"] + 1


def _signers(client, admin, tag):
    """建两个签核人并返回 id。门禁发起接口强制要求两级签核人,不传会 400。"""
    out = {}
    for i in (1, 2):
        r = client.post("/api/team-members",
                        json={"name": f"签核人{tag}{i}", "department": "项目部"}, headers=admin)
        assert r.status_code == 201, r.text
        out[f"l{i}"] = r.json()["id"]
    return out


def _required_stds(wf, phase_code):
    """该阶段全部必交标准(含无对应步骤的那些)。

    必须把 ph["unmapped_standards"] 也算进来:S0 的「项目开发合同」「立项申请书」
    是必交的,但不在任何步骤上,门禁照样拿它们卡人。只看步骤会以为批完就能过。
    """
    ph = _phase(wf, phase_code)
    from_steps = [s for st in ph["steps"] for s in st["standards"] if s["required"]]
    from_unmapped = [u for u in ph["unmapped_standards"] if u["required"]]
    return from_steps + from_unmapped


def _std_name(s):
    """步骤上的标准用 standard_name,清单里的用 name。"""
    return s.get("standard_name") or s.get("name")


class TestGateHandoff:
    """口径一致:界面上的 missing_required / can_initiate_signoff 必须与门禁接口同真同假。

    断言精确到失败原因(detail 文本),否则"恰好因为没传签核人而 400"会被误判成
    "因为缺件被拦",测试就成了假的绿灯。
    """

    @pytest.mark.parametrize("phase_code", ["S0", "S1", "S2", "S3"])
    def test_missing_required_matches_initiate_signoff(self, client, admin, phase_code):
        pid = _software_project(client, admin, f"WF-G{phase_code}")
        signers = _signers(client, admin, phase_code)
        payload = {"level1_signer_id": signers["l1"], "level2_signer_id": signers["l2"],
                   "comment": "测试"}

        ph = _phase(_workflow(client, admin, pid), phase_code)
        assert ph["progress"]["missing_required"], "新项目该有缺件"
        assert ph["progress"]["can_initiate_signoff"] is False
        r = client.post(f"/api/gate-reviews/{ph['phase_gate_id']}/initiate-signoff",
                        json=payload, headers=admin)
        assert r.status_code == 400
        assert "必需交付物未批准" in r.json()["detail"], (
            f"400 的原因不是缺件,而是「{r.json()['detail']}」——本用例没验到该验的东西"
        )

        # 把必交标准全部批掉后:接口必须放行,界面也必须说可以发起
        need = _required_stds(_workflow(client, admin, pid), phase_code)
        assert need, f"{phase_code} 没有必交标准,用例前提不成立"
        for s in need:
            _set_deliverable(pid, phase_code, _std_name(s), "approved")

        ph = _phase(_workflow(client, admin, pid), phase_code)
        assert ph["progress"]["missing_required"] == [], "必交都批了还报缺件"
        assert ph["progress"]["can_initiate_signoff"] is True
        r = client.post(f"/api/gate-reviews/{ph['phase_gate_id']}/initiate-signoff",
                        json=payload, headers=admin)
        assert r.status_code == 201, f"界面说可以发起,接口却拒绝: {r.text}"

    def test_partial_required_still_blocks(self, client, admin):
        """必交批了一部分,界面和接口都必须说不能发起。"""
        pid = _software_project(client, admin, "WF-G9")
        signers = _signers(client, admin, "G9")
        need = _required_stds(_workflow(client, admin, pid), "S1")
        assert len(need) >= 2, "S1 必交标准不足 2 条,用例前提不成立"
        for s in need[:-1]:
            _set_deliverable(pid, "S1", _std_name(s), "approved")

        ph = _phase(_workflow(client, admin, pid), "S1")
        assert ph["progress"]["missing_required"] == [_std_name(need[-1])]
        assert ph["progress"]["can_initiate_signoff"] is False
        r = client.post(f"/api/gate-reviews/{ph['phase_gate_id']}/initiate-signoff",
                        json={"level1_signer_id": signers["l1"],
                              "level2_signer_id": signers["l2"]}, headers=admin)
        assert r.status_code == 400
        assert "必需交付物未批准" in r.json()["detail"]

    def test_initiated_gate_reports_l1_pending(self, client, admin):
        pid = _software_project(client, admin, "WF-G5")
        signers = _signers(client, admin, "G5")
        for s in _required_stds(_workflow(client, admin, pid), "S0"):
            _set_deliverable(pid, "S0", _std_name(s), "approved")
        ph = _phase(_workflow(client, admin, pid), "S0")
        r = client.post(f"/api/gate-reviews/{ph['phase_gate_id']}/initiate-signoff",
                        json={"level1_signer_id": signers["l1"],
                              "level2_signer_id": signers["l2"]}, headers=admin)
        assert r.status_code == 201, r.text

        ph = _phase(_workflow(client, admin, pid), "S0")
        assert ph["gate_state"] == "l1_pending"
        assert ph["progress"]["can_initiate_signoff"] is False, "已发起的门不该能再发起"
        gate_step = next(s for s in ph["steps"] if s["kind"] == "gate")
        assert gate_step["state"] == "in_progress"
        assert gate_step["actions"]["missing_required"] == []
        assert gate_step["actions"]["can_initiate_signoff"] is False


def _confirmable_step(wf, code):
    """该阶段里可人工确认、且不是门禁的一步。

    测试库的交付物定义是完整的(每个步骤都有标准),所以「无标准的步骤」在这里
    不存在,只能挑线下办理的步骤(UAT、客户培训、客户验收…)。无标准那种情形
    由 TestDriftTolerance 的单元测试覆盖。
    """
    ph = _phase(wf, code)
    for s in ph["steps"]:
        if s["confirmable"] and s["kind"] != "gate":
            return ph, s
    raise AssertionError(f"{code} 没有可确认的步骤")


def _confirm_url(pid, code, seq):
    return f"/api/projects/{pid}/workflow/steps/{code}/{seq}/confirm"


class TestConfirm:
    """线下步骤的人工确认。

    注意语义:线下但**有**交付物标准的步骤(如 UAT),完成与否仍以交付物为准,
    确认只是留痕,不会把步骤刷成已完成——否则会出现"点一下门禁就过了"。
    """

    def test_confirm_records_but_does_not_fake_completion(self, client, admin):
        pid = _software_project(client, admin, "WF-C1")
        _, step = _confirmable_step(_workflow(client, admin, pid), "S2")
        assert step["standards"], "该步骤应挂着交付物标准"

        r = client.post(_confirm_url(pid, "S2", step["seq"]),
                        json={"note": "现场已做"}, headers=admin)
        assert r.status_code == 200, r.text

        step2 = next(s for s in _phase(_workflow(client, admin, pid), "S2")["steps"]
                     if s["seq"] == step["seq"])
        assert step2["confirm"]["confirmed_by"] == "wf_admin"
        assert step2["confirm"]["note"] == "现场已做"
        assert step2["actions"]["can_unconfirm"] is True
        assert step2["state"] != "done", "交付物没批,人工确认不能把步骤刷成已完成"
        assert step2["confirm_with_pending"] is True, "确认了但材料没交齐,界面要能提示"

    def test_confirm_is_idempotent(self, client, admin):
        pid = _software_project(client, admin, "WF-C2")
        _, step = _confirmable_step(_workflow(client, admin, pid), "S2")
        url = _confirm_url(pid, "S2", step["seq"])
        assert client.post(url, json={}, headers=admin).status_code == 200
        assert client.post(url, json={"note": "再确认一次"}, headers=admin).status_code == 200
        step2 = next(s for s in _phase(_workflow(client, admin, pid), "S2")["steps"]
                     if s["seq"] == step["seq"])
        assert step2["confirm"]["note"] == "再确认一次"

    def test_unconfirm_then_confirm_again(self, client, admin):
        pid = _software_project(client, admin, "WF-C3")
        _, step = _confirmable_step(_workflow(client, admin, pid), "S3")
        url = _confirm_url(pid, "S3", step["seq"])
        client.post(url, json={}, headers=admin)
        assert client.delete(url, headers=admin).status_code == 200
        step2 = next(s for s in _phase(_workflow(client, admin, pid), "S3")["steps"]
                     if s["seq"] == step["seq"])
        assert step2["confirm"] is None
        assert client.delete(url, headers=admin).status_code == 404, "没确认过还撤销,应 404"

    def test_cannot_confirm_deliverable_driven_step(self, client, admin):
        """由交付物自动推导的步骤不接受人工确认,否则会出现"点一下就算完成"。"""
        pid = _software_project(client, admin, "WF-C4")
        r = client.post(_confirm_url(pid, "S2", 1), json={}, headers=admin)
        assert r.status_code == 400
        assert "自动推导" in r.json()["detail"]

    def test_cannot_confirm_gate_step(self, client, admin):
        pid = _software_project(client, admin, "WF-C5")
        ph = _phase(_workflow(client, admin, pid), "S0")
        gate_seq = next(s["seq"] for s in ph["steps"] if s["kind"] == "gate")
        r = client.post(_confirm_url(pid, "S0", gate_seq), json={}, headers=admin)
        assert r.status_code == 400
        assert "自动推导" in r.json()["detail"]

    def test_unknown_node_404(self, client, admin):
        pid = _software_project(client, admin, "WF-C6")
        assert client.post(_confirm_url(pid, "S0", 99), json={},
                           headers=admin).status_code == 404

    def test_outsider_forbidden(self, client, admin):
        pid = _software_project(client, admin, "WF-C7")
        _, step = _confirmable_step(_workflow(client, admin, pid), "S3")
        outsider = auth_headers(client, "wf_outsider", "member")
        r = client.post(_confirm_url(pid, "S3", step["seq"]), json={}, headers=outsider)
        assert r.status_code == 403

    def test_project_member_can_confirm(self, client, admin):
        """项目成员(角色命中该步骤的 roles)可以确认,不必是管理员。"""
        pid = _software_project(client, admin, "WF-C8")
        _, step = _confirmable_step(_workflow(client, admin, pid), "S3")
        roles = step["node"].get("roles") or []
        assert roles, "该步骤没有登记角色,用例前提不成立"

        tm = client.post("/api/team-members",
                         json={"name": "工作流成员", "department": "项目部"}, headers=admin)
        assert tm.status_code == 201, tm.text
        mid = tm.json()["id"]
        rid = _role_id(client, admin, roles[0])
        r = client.post(f"/api/projects/{pid}/members", headers=admin,
                        json={"member_id": mid, "role_id": rid, "allocation_pct": 100,
                              "is_key": False, "phase_ids": "[]"})
        assert r.status_code in (200, 201), r.text

        member = auth_headers(client, "wf_member", "member")
        _bind_member("wf_member", mid)
        r = client.post(_confirm_url(pid, "S3", step["seq"]),
                        json={"note": "成员确认"}, headers=member)
        assert r.status_code == 200, r.text

    def test_member_with_wrong_role_forbidden(self, client, admin):
        """挂了个不相干的角色(非该步骤 roles)就不能确认。"""
        pid = _software_project(client, admin, "WF-C9")
        _, step = _confirmable_step(_workflow(client, admin, pid), "S3")
        tm = client.post("/api/team-members",
                         json={"name": "无关成员", "department": "财务部"}, headers=admin)
        mid = tm.json()["id"]
        rid = _role_id(client, admin, "财务专员")
        r = client.post(f"/api/projects/{pid}/members", headers=admin,
                        json={"member_id": mid, "role_id": rid, "allocation_pct": 100,
                              "is_key": False, "phase_ids": "[]"})
        assert r.status_code in (200, 201), r.text

        member = auth_headers(client, "wf_member2", "member")
        _bind_member("wf_member2", mid)
        r = client.post(_confirm_url(pid, "S3", step["seq"]), json={}, headers=member)
        assert r.status_code == 403


def _role_id(client, admin, name):
    """取角色 id,测试库角色表为空时现场建一个。"""
    roles = client.get("/api/lookups/roles", headers=admin).json()
    for r in roles:
        if r["name"] == name:
            return r["id"]
    resp = client.post("/api/lookups/roles",
                       json={"name": name, "code": f"R{abs(hash(name)) % 100000}",
                             "sort_order": 99}, headers=admin)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _bind_member(username, member_id):
    """把账号绑到人员档案上——member_id 非空才会参与项目角色校验。"""
    from sqlalchemy import select
    from backend_v2.database import SessionLocal
    from backend_v2.models import UserAuth
    with SessionLocal() as db:
        u = db.execute(select(UserAuth).where(UserAuth.username == username)).scalar_one()
        u.member_id = member_id
        db.commit()


class TestDriftTolerance:
    """交付物定义与库不一致时的兜底行为。

    现网库比定义少 6 条标准(见 workflow_map 模块开头),那些步骤在本库中没有
    可用的数据源。直接改库会让整套用例互相干扰,所以这里测函数本身。
    """

    def test_node_without_standard_is_manual(self):
        from backend_v2.routes.project_workflow import _node_kind

        node = {"seq": 1, "name": "需求调研与澄清", "venue": "线下"}
        assert _node_kind(node, []) == "manual", "没有标准可依据的步骤必须走人工确认"
        assert _node_kind(node, ["需求调研报告"]) == "deliverable"
        assert _node_kind({**node, "module": "项目详情 → 阶段门径"}, []) == "gate"

    def test_unconfigured_standard_counts_as_non_required(self):
        """标准在本库没配置时按非必交处理,不能把步骤永远钉在未开始。"""
        from backend_v2.routes.project_workflow import _satisfied

        class Hit:
            status = "submitted"
        assert _satisfied(None, Hit()) is True, "未配置的标准不该把已提交的步骤判为未完成"
        assert _satisfied(None, None) is False, "没有交付物就是没完成"

        class Req:
            required = True

        class Opt:
            required = False

        assert _satisfied(Req(), Hit()) is False, "必交标准提交了但没批,不算达标"
        assert _satisfied(Opt(), Hit()) is True

    def test_unconfigured_standard_marked_in_payload(self, client, admin):
        """库里没有的标准要在响应里标出来,界面据此提示「本库未配置」而不是假装未开始。

        S3「客户验收」同时挂「验收记录」和「用户验收记录」,而定义里只有前者,
        所以这条正好是现成的漂移样本:一条配了、一条没配。
        """
        pid = _software_project(client, admin, "WF-D1")
        wf = _workflow(client, admin, pid)
        flags = [(ph["phase_code"], s["seq"], st["standard_name"], st["required"])
                 for ph in wf["phases"] for s in ph["steps"] for st in s["standards"]
                 if not st["configured"]]
        assert flags == [("S3", 7, "用户验收记录", None)], (
            f"未配置标准的清单变了: {flags}。"
            "如果是对齐了库与定义,请同步删掉 workflow_map.STANDARDS_NOT_IN_SEED 里的条目"
        )
        step = next(s for s in _phase(wf, "S3")["steps"] if s["seq"] == 7)
        assert step["definition_gap"] is False, "该步骤还有一条配了的标准,不算完全没依据"
        assert step["kind"] == "deliverable"

        # 完全没依据的步骤(现网库有 4 个)才标 definition_gap,并退回人工确认
        from backend_v2.routes.project_workflow import _node_kind
        assert _node_kind({"seq": 1, "venue": "本平台"}, []) == "manual"
