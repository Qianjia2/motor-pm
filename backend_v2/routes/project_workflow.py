"""项目工作流:把 PHASE_NODES 的步骤按项目渲染成一条有状态的流程。

与培训页的区别:培训页(process-flow)把同一份 PHASE_NODES 当静态教学图示,
这里按具体项目推导每一步的状态,并且能推进(线下确认、发起门禁签署、签署)。

状态从哪来,分三类,响应里用 state_source 标明,不冒充:
  - deliverable: 读该步骤对应的交付物标准在本项目里的批准状态
  - gate:        读该阶段的两级签核记录
  - manual:      线下步骤,平台没有数据源,由人在本平台确认留痕
  - none:        既无交付物也无签核可依据的步骤(软件阶段不存在,硬件阶段会有)

「能不能发起签核」直接复用 gate_reviews._missing_required_deliverables,
不另写一套口径——否则会出现界面说可以发起、一点就被 400。
"""
from copy import deepcopy
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend_v2.audit import log_audit
from backend_v2.auth import get_current_user, require_admin
from backend_v2.database import get_db
from backend_v2.models import (
    Deliverable, GateDeliverableStandard, GateSignoffRecord, Phase, Project,
    ProjectMember, ProjectPhaseGate, ProjectWorkflowStepConfirm, TeamMember,
)
from backend_v2.permissions import check_permission
from backend_v2.routes.gate_reviews import _missing_required_deliverables, signoff_to_dict
from backend_v2.routes.training_process import PHASE_NODES
from backend_v2.workflow_map import (
    STANDARDS_WITHOUT_NODE, WORKFLOW_NODE_STANDARDS, node_standards, not_in_seed,
    supports_workflow,
)

router = APIRouter(tags=["project-workflow"])

SUPPORTED_TYPES = ("software",)  # 软件项目全线开放;硬件另有白名单,见 workflow_map.WORKFLOW_OPT_IN_CODES

# 交付物状态优先级:命中多条时取最优的一条代表该标准(与 gate_reviews checklist 同序)
STATUS_PRIO = {"approved": 0, "submitted": 1, "reviewed": 2, "rejected": 3, "not_submitted": 4}
DONE_STATUSES = ("submitted", "reviewed", "approved")

STATE_LABELS = {
    "done": "已完成", "in_progress": "进行中", "pending_confirm": "待确认",
    "blocked": "有驳回", "not_started": "未开始",
}
GATE_STATE_LABELS = {
    "not_initiated": "未发起", "l1_pending": "一级待签", "l2_pending": "二级待签",
    "passed": "已放行", "waived": "已豁免", "rejected": "已驳回",
}


# ── 匹配与判定 ──

def _match_deliverables(dels, std_name):
    """名称双向子串匹配,按状态优先级排序。

    与 gate_reviews.deliverable_checklist / _missing_required_deliverables 同一套规则,
    保持一致才能保证「界面上的状态」和「门禁的判断」对得上。
    """
    if not std_name:
        return []
    hits = [d for d in dels if d.name and (d.name in std_name or std_name in d.name)]
    return sorted(hits, key=lambda d: STATUS_PRIO.get(d.status, 5))


def _satisfied(std, hit):
    """该标准是否算达标:必交必须 approved;非必交有提交记录即可。

    std 为 None 表示这条标准在本阶段的配置里不存在(定义与库不一致时会这样,
    见 workflow_map 模块开头的说明)。此时按「非必交」处理:一条本库没有的标准
    不应该把步骤永远钉在未开始。
    """
    if hit is None:
        return False
    if hit.status == "approved":
        return True
    return not (std.required if std else False) and hit.status in ("submitted", "reviewed")


def _derive_gate_state(pg, recs):
    """阶段门状态。白名单判定放行:只有 passed/waived 算放行。"""
    if pg.gate_status == "passed":
        return "passed"
    if pg.gate_status == "waived":
        return "waived"
    if pg.gate_status in ("failed", "rejected"):
        return "rejected"
    l1 = next((r for r in recs if r.level == 1), None)
    l2 = next((r for r in recs if r.level == 2), None)
    if (l1 and l1.status == "rejected") or (l2 and l2.status == "rejected"):
        return "rejected"
    if l1 and l1.status == "pending":
        return "l1_pending"
    if l2 and l2.status == "pending":
        return "l2_pending"
    if l2 and l2.status == "approved":
        return "passed"
    return "not_initiated"


def _node_kind(node, std_names):
    """步骤类型。只看有没有数据源,不看在哪里办:

    - gate:        阶段门禁节点,状态由签核记录推导
    - deliverable: 有对应交付物标准,状态由交付物批准情况推导
    - manual:      没有对应标准,平台无从推导,只能由人确认

    线下但**有**标准的步骤(如 S2 的 UAT、S3 的客户培训)算 deliverable:
    报告就是证据,不用靠"我觉得做完了"来推进;线下属性照 node.venue 显示,
    人工确认也仍然可以做,只是作为补充留痕,不影响状态判定。
    """
    if (node.get("module") or "").endswith("阶段门径"):
        return "gate"
    return "deliverable" if std_names else "manual"


def _state_of(kind, std_names, hit_states, satisfied_all, has_material, confirm, gate_state):
    """推一个节点的状态。blocked 优先级最高:有驳回就先解决驳回。"""
    if any(s == "rejected" for s in hit_states):
        return "blocked"
    if kind == "gate":
        if gate_state in ("passed", "waived"):
            return "done"
        if gate_state in ("l1_pending", "l2_pending"):
            return "in_progress"
        return "not_started"
    if not std_names:
        # 无数据源:确认即完成,没确认就是等人确认(而不是"未开始"——平台根本无从开始)
        return "done" if confirm else "pending_confirm"
    if satisfied_all:
        return "done"
    return "in_progress" if has_material else "not_started"


def _node_roles(node):
    """步骤定义的执行角色,去掉空串,保持原顺序。"""
    return [r for r in (node.get("roles") or []) if r]


def _is_mine(node, my_roles):
    """这一步是不是我负责的。

    与 _can_confirm_node 的第三条同源:角色名精确命中。不做子串匹配——
    「软件工程师」和「高级软件工程师」是两个人,包含关系会认错。
    """
    return bool(set(_node_roles(node)) & set(my_roles))


def _can_confirm_node(user, my_roles, node):
    """谁能确认线下步骤:管理员 / 有项目编辑权限 / 项目角色命中该步骤的角色。"""
    if user.role == "admin":
        return True
    if check_permission(user, "projects", "edit"):
        return True
    return _is_mine(node, my_roles)


def _who_is_next(phases_out, my_roles):
    """把「现在轮到谁做什么」算出来。

    规则直接来自流程定义本身:同一阶段里步骤按 seq 顺序推进,前面没做完就轮不到后面。
    所以
      is_current       本阶段第一个还没完成的步骤(整个阶段当前就卡在这一步)
      blocked_by_prev  排在本步之前、还没完成的步骤
    只给「我负责 + 没完成 + 前面都完成了」的步骤才叫「该你做」。前面还没做完的
    只列出来并说清在等谁——报早了等于没说。
    """
    mine = []
    for ph in phases_out:
        for st in ph["steps"]:
            if st["assigned_to_me"]:
                mine.append({
                    "phase_code": ph["phase_code"], "phase_name": ph["phase_name"],
                    "seq": st["seq"],
                    "blocked_by_prev": st["blocked_by_prev"],
                    "blocked_by": st["blocked_by"],
                    "is_current": st["is_current"],
                })
    open_mine = [m for m in mine if _step_of(phases_out, m)["state"] != "done"]
    ready = next((m for m in open_mine if not m["blocked_by_prev"]), None)
    waiting = bool(open_mine) and ready is None
    nxt = ready or (open_mine[0] if open_mine else None)
    return {
        "roles": list(my_roles),
        "has_role": bool(my_roles),
        "mine_total": len(mine),
        "mine_done": len(mine) - len(open_mine),
        "mine_open": len(open_mine),
        "next": nxt,
        # 轮到我、但前面还没做完:界面要说"先等谁",不能催人开工
        "next_waiting_on_prev": waiting and nxt is not None,
        "pending": [{"phase_code": m["phase_code"], "phase_name": m["phase_name"],
                     "seq": m["seq"], "blocked_by_prev": m["blocked_by_prev"]}
                    for m in open_mine],
    }


def _step_of(phases_out, ref):
    ph = next(p for p in phases_out if p["phase_code"] == ref["phase_code"])
    return next(s for s in ph["steps"] if s["seq"] == ref["seq"])


# ── 组装 ──

def _phase_step_payload(phase, pg, nodes, stds, dels, confirms, recs, user, my_roles):
    """把一个阶段的所有步骤算出来。"""
    steps, mapped_names = [], set()
    for node in nodes:
        seq = node["seq"]
        std_names = node_standards(phase.code, seq)
        kind = _node_kind(node, std_names)
        mapped_names.update(std_names)

        std_entries, hit_statuses = [], []
        for sname in std_names:
            std = next((s for s in stds if s.name == sname), None)
            hits = _match_deliverables(dels, sname)
            hit = hits[0] if hits else None
            if hit:
                hit_statuses.append(hit.status)
            std_entries.append({
                "standard_name": sname,
                "required": bool(std.required) if std else None,
                "standard_id": std.id if std else None,
                "deliverable_id": hit.id if hit else None,
                "deliverable_name": hit.name if hit else None,
                "status": hit.status if hit else "missing",
                "owner_name": hit.owner.name if (hit and hit.owner) else None,
                "submitted_date": hit.submitted_date.isoformat() if (hit and hit.submitted_date) else None,
                "file_path": hit.file_path if hit else None,
                # 标准未配置(std=None)时 required 返回 None,界面据此提示"本库未配置该标准"
                "configured": bool(std),
                "satisfied": _satisfied(std, hit),
            })
        # 定义缺口:这一步的标准在本阶段的标准表里一条都没有(定义与库不一致)
        definition_gap = bool(std_names) and not any(e["configured"] for e in std_entries)

        confirm = next((c for c in confirms if c.node_seq == seq), None)
        has_material = any(e["deliverable_id"] for e in std_entries)
        satisfied_all = bool(std_entries) and all(e["satisfied"] for e in std_entries)

        if kind == "gate":
            gate_state = _derive_gate_state(pg, recs)
        else:
            gate_state = None

        state = _state_of(kind, std_names, hit_statuses, satisfied_all, has_material, confirm, gate_state)

        step = {
            "seq": seq,
            "kind": kind,
            "state": state,
            "state_label": STATE_LABELS.get(state, state),
            "state_source": kind,
            "definition_gap": definition_gap,
            # 这一步是不是当前登录人负责的(界面据此给「该你了」的入口)
            "assigned_to_me": _is_mine(node, my_roles),
            # 门禁节点状态由签核记录推导,不接受人工确认
            "confirmable": bool(kind != "gate" and (not std_names or node.get("venue") == "线下")),
            "node": deepcopy(node),
            "standards": std_entries,
            "unmatched_standards": [e["standard_name"] for e in std_entries if not e["deliverable_id"]],
            "confirm": {
                "confirmed_by": confirm.confirmed_by,
                "confirmed_at": confirm.confirmed_at.isoformat() if confirm.confirmed_at else None,
                "note": confirm.note,
            } if confirm else None,
            "gate_state": gate_state,
            "gate_state_label": GATE_STATE_LABELS.get(gate_state) if gate_state else None,
            # 确认了线下步骤、但该步骤的必交材料还没批完:界面要同时提示,别让人以为门禁能过
            "confirm_with_pending": bool(confirm and std_entries and not satisfied_all),
        }
        step["actions"] = {
            "can_confirm": (step["confirmable"] and not confirm
                            and _can_confirm_node(user, my_roles, node)),
            "can_unconfirm": bool(
                confirm and (user.role == "admin" or check_permission(user, "projects", "edit")
                             or confirm.confirmed_by == user.username)
            ),
        }
        steps.append(step)

    # 顺序推进:同一个阶段里前一步没完成,后一步就还没轮到。
    # 把「本阶段当前卡在哪一步」和「每步被前面的哪几步挡着」标出来,界面才好说人话。
    first_open = next((i for i, s in enumerate(steps) if s["state"] != "done"), None)
    for i, s in enumerate(steps):
        s["is_current"] = (i == first_open)
        s["blocked_by_prev"] = bool(first_open is not None and i > first_open)
        s["blocked_by"] = [{"seq": p["seq"], "name": p["node"]["name"], "state_label": p["state_label"]}
                           for p in steps[:i] if p["state"] != "done"] if s["blocked_by_prev"] else []

    unmapped = []
    for st in stds:
        if st.name in mapped_names:
            continue
        hit = (_match_deliverables(dels, st.name) or [None])[0]
        unmapped.append({
            "standard_id": st.id, "name": st.name, "required": bool(st.required),
            "deliverable_id": hit.id if hit else None,
            "deliverable_name": hit.name if hit else None,
            "status": hit.status if hit else "missing",
            # declared: 定义里就没打算挂到步骤上;extra: 库里有、定义里没有(见 workflow_map)
            "declared": st.name in (STANDARDS_WITHOUT_NODE.get(phase.code) or []),
            "extra": not_in_seed(phase.code, st.name),
            "satisfied": _satisfied(st, hit),
        })
    return steps, unmapped


@router.get("/api/workflow/projects")
def list_workflow_projects(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """支持工作流的项目清单,给独立页面的项目选择器用。

    判定只在这里和 get_project_workflow 两处,都问 supports_workflow。
    前端不复制白名单——否则加一个试点项目要改两边,迟早对不上。

    不带分页:项目总量是几十的量级,而"支持工作流的"永远是个小集合。
    """
    rows = db.execute(select(Project).order_by(Project.id)).scalars().all()
    return [
        {"id": p.id, "code": p.code, "name": p.name, "project_type": p.project_type}
        for p in rows
        if supports_workflow(p.project_type, p.code)
    ]


@router.get("/api/projects/{project_id}/workflow")
def get_project_workflow(
    project_id: int,
    phase_code: str = Query(None, description="只取某一阶段,如 S0"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    pgs = db.execute(
        select(ProjectPhaseGate)
        .join(Phase, Phase.id == ProjectPhaseGate.phase_id)
        .where(ProjectPhaseGate.project_id == project_id)
        .order_by(Phase.sort_order)
    ).scalars().all()

    supported = supports_workflow(project.project_type, project.code)
    # 在 if 之前算好:不支持的项目类型也要返回 me(否则 return 时未定义)
    my_roles = _my_roles(db, project_id, user)
    phases_out = []
    summary = {"phases_total": 0, "phases_passed": 0, "steps_total": 0, "steps_done": 0,
               "required_total": 0, "required_approved": 0}

    if supported and pgs:
        pg_ids = [pg.id for pg in pgs]
        phase_ids = [pg.phase_id for pg in pgs]

        all_dels = db.execute(select(Deliverable).where(
            Deliverable.project_id == project_id, Deliverable.phase_id.in_(phase_ids)
        )).scalars().all()
        all_stds = db.execute(select(GateDeliverableStandard).where(
            GateDeliverableStandard.phase_id.in_(phase_ids),
            GateDeliverableStandard.is_active == True,
        ).order_by(GateDeliverableStandard.sort_order, GateDeliverableStandard.id)).scalars().all()
        all_recs = db.execute(
            select(GateSignoffRecord).options(selectinload(GateSignoffRecord.phase_gate))
            .where(GateSignoffRecord.project_phase_gate_id.in_(pg_ids))
        ).scalars().all()
        all_confirms = db.execute(select(ProjectWorkflowStepConfirm).where(
            ProjectWorkflowStepConfirm.project_id == project_id
        )).scalars().all()

        for pg in pgs:
            phase = pg.phase
            if phase_code and phase.code != phase_code:
                continue
            nodes = PHASE_NODES.get(phase.code) or []
            if not nodes:
                continue
            stds = [s for s in all_stds if s.phase_id == pg.phase_id]
            dels = [d for d in all_dels if d.phase_id == pg.phase_id]
            recs = [r for r in all_recs if r.project_phase_gate_id == pg.id]
            confirms = [c for c in all_confirms if c.phase_code == phase.code]

            steps, unmapped = _phase_step_payload(
                phase, pg, nodes, stds, dels, confirms, recs, user, my_roles)

            # 缺件列表用门禁那套口径算,保证「界面说能发起」== 「接口真的能发起」。
            # 三个条件逐条对齐 initiate_signoff 的拦截逻辑(已放行 / 有进行中的签核 / 缺必交),
            # 不额外多加条件——界面比接口更严会让人以为不能发起,其实能。
            missing = _missing_required_deliverables(db, pg)
            gate_state = _derive_gate_state(pg, recs)
            has_pending_signoff = any(r.status == "pending" for r in recs)
            can_initiate = (
                check_permission(user, "projects", "edit")
                and pg.gate_status != "passed"
                and not has_pending_signoff
                and not missing
            )
            l1 = next((r for r in recs if r.level == 1), None)
            l2 = next((r for r in recs if r.level == 2), None)

            def _sign_level(rec):
                if not rec or rec.status != "pending":
                    return None
                if user.role == "admin":
                    return rec.level
                return rec.level if (user.member_id and rec.signer_id == user.member_id) else None

            for st in steps:
                if st["kind"] == "gate":
                    st["actions"]["can_initiate_signoff"] = can_initiate
                    st["actions"]["can_sign_level"] = _sign_level(l1) or _sign_level(l2)
                    st["actions"]["missing_required"] = missing

            done_steps = sum(1 for s in steps if s["state"] == "done")
            required = [s for s in stds if s.required]
            approved = sum(1 for s in required if _satisfied(s, (_match_deliverables(dels, s.name) or [None])[0]))
            current_seq = next((s["seq"] for s in steps if s["state"] != "done"), None)

            phases_out.append({
                "phase_id": pg.phase_id,
                "phase_code": phase.code,
                "phase_name": phase.name,
                "phase_gate_id": pg.id,
                "gate": {"id": pg.gate.id, "code": pg.gate.code, "name": pg.gate.name} if pg.gate else None,
                "pg_status": pg.status,
                "gate_status": pg.gate_status,
                "gate_state": gate_state,
                "gate_state_label": GATE_STATE_LABELS.get(gate_state, gate_state),
                "gate_review_date": pg.gate_review_date.isoformat() if pg.gate_review_date else None,
                "signoff": {
                    "initiated_by": pg.signoff_initiated_by,
                    "l1": signoff_to_dict(l1) if l1 else None,
                    "l2": signoff_to_dict(l2) if l2 else None,
                },
                "progress": {
                    "steps_total": len(steps), "steps_done": done_steps,
                    "current_step_seq": current_seq,
                    "standards_total": len(stds),
                    "required_total": len(required), "required_approved": approved,
                    "missing_required": missing,
                    "can_initiate_signoff": can_initiate,
                    "percent": round(done_steps * 100 / len(steps)) if steps else 0,
                },
                "steps": steps,
                "unmapped_standards": unmapped,
            })

            summary["phases_total"] += 1
            summary["phases_passed"] += 1 if gate_state in ("passed", "waived") else 0
            summary["steps_total"] += len(steps)
            summary["steps_done"] += done_steps
            summary["required_total"] += len(required)
            summary["required_approved"] += approved

    return {
        "project_id": project_id,
        "project_name": project.name,
        "project_type": project.project_type,
        "supported": supported,
        # 「我的下一步」:进项目第一眼要知道自己该干什么,不能让人自己在 36 步里找
        "me": _me_payload(db, project_id, user, my_roles, phases_out),
        "phases": phases_out,
        "summary": summary,
    }


def _me_payload(db, project_id, user, my_roles, phases_out):
    """当前登录人在本项目的工作台信息。

    没有项目角色时不留空白:明确说"没给你分配角色",并告诉你去哪确认,
    否则用户只会看到一片和自己无关的步骤,以为系统坏了。
    """
    me = _who_is_next(phases_out, my_roles)
    me["member_id"] = user.member_id
    me["username"] = user.username
    me["name"] = _my_display_name(db, user)
    if not me["has_role"]:
        # 「团队」页签已并入概览,别再指一个不存在的地方
        me["hint"] = ("你在本项目还没有分配角色,所以看不到「该我做什么」。"
                      "请联系项目经理在「概览 → 项目团队」里把你加进来并指定角色。")
    return me


def _my_display_name(db, user):
    """界面上叫得出名字:优先人员档案的姓名,没有就退回登录名。"""
    if not user.member_id:
        return user.username
    m = db.get(TeamMember, user.member_id)
    return (m.name or user.username) if m else user.username


# ── 线下步骤的人工确认 ──

def _confirm_target(db, project_id, phase_code, node_seq, user):
    """校验路径参数并返回 (phase, node, 已有的确认记录)。"""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    phase = db.execute(select(Phase).where(
        Phase.code == phase_code, Phase.project_type == project.project_type
    )).scalar_one_or_none()
    if not phase:
        raise HTTPException(status_code=404, detail=f"项目类型下没有阶段 {phase_code}")
    node = next((n for n in (PHASE_NODES.get(phase.code) or []) if n["seq"] == node_seq), None)
    if not node:
        raise HTTPException(status_code=404, detail=f"阶段 {phase_code} 没有第 {node_seq} 步")
    std_names = node_standards(phase_code, node_seq)
    if _node_kind(node, std_names) != "manual" and node.get("venue") != "线下":
        raise HTTPException(status_code=400, detail="该步骤由交付物状态自动推导,无需人工确认")
    if not _can_confirm_node(user, _my_roles(db, project_id, user), node):
        raise HTTPException(status_code=403, detail="仅项目成员或管理员可确认该步骤")
    pg = db.execute(select(ProjectPhaseGate).where(
        ProjectPhaseGate.project_id == project_id, ProjectPhaseGate.phase_id == phase.id
    )).scalar_one_or_none()
    if not pg:
        raise HTTPException(status_code=404, detail="该项目的阶段门记录不存在")
    rec = db.execute(select(ProjectWorkflowStepConfirm).where(
        ProjectWorkflowStepConfirm.project_id == project_id,
        ProjectWorkflowStepConfirm.phase_code == phase_code,
        ProjectWorkflowStepConfirm.node_seq == node_seq,
    )).scalar_one_or_none()
    return project, phase, node, rec


def _my_roles(db, project_id, user):
    if not user.member_id:
        return []
    return [pm.role.name for pm in db.execute(select(ProjectMember).where(
        ProjectMember.project_id == project_id, ProjectMember.member_id == user.member_id
    )).scalars().all() if pm.role]


@router.post("/api/projects/{project_id}/workflow/steps/{phase_code}/{node_seq}/confirm")
def confirm_step(
    project_id: int, phase_code: str, node_seq: int,
    data: Optional[dict] = Body(None),
    db: Session = Depends(get_db), user=Depends(get_current_user),
):
    """确认线下步骤已完成。幂等:重复确认只更新确认人与时间。"""
    project, phase, node, rec = _confirm_target(db, project_id, phase_code, node_seq, user)
    note = (data or {}).get("note") or None
    if rec:
        rec.confirmed_by = user.username
        rec.confirmed_at = datetime.utcnow()
        rec.note = note or rec.note
        rec.node_name = node["name"]
        action, detail = "update", f"重新确认线下步骤: {node['name']}"
    else:
        rec = ProjectWorkflowStepConfirm(
            project_id=project_id, phase_id=phase.id, phase_code=phase_code,
            node_seq=node_seq, node_name=node["name"],
            confirmed_by=user.username, note=note,
        )
        db.add(rec)
        action, detail = "create", f"确认线下步骤完成: {node['name']}"
    db.commit()
    db.refresh(rec)
    log_audit(db, user.username, action, "project_workflow_step_confirm", rec.id,
              node["name"], project_id, detail)
    return {
        "message": "已确认",
        "confirm": {
            "phase_code": phase_code, "node_seq": node_seq, "node_name": node["name"],
            "confirmed_by": rec.confirmed_by,
            "confirmed_at": rec.confirmed_at.isoformat() if rec.confirmed_at else None,
            "note": rec.note,
        },
    }


@router.delete("/api/projects/{project_id}/workflow/steps/{phase_code}/{node_seq}/confirm")
def unconfirm_step(
    project_id: int, phase_code: str, node_seq: int,
    db: Session = Depends(get_db), user=Depends(get_current_user),
):
    """取消确认。本人、管理员或有项目编辑权限的人可以撤销。"""
    project, phase, node, rec = _confirm_target(db, project_id, phase_code, node_seq, user)
    if not rec:
        raise HTTPException(status_code=404, detail="该步骤尚未确认")
    if not (user.role == "admin" or check_permission(user, "projects", "edit")
            or rec.confirmed_by == user.username):
        raise HTTPException(status_code=403, detail="只能撤销本人的确认")
    db.delete(rec)
    db.commit()
    log_audit(db, user.username, "delete", "project_workflow_step_confirm", rec.id,
              node["name"], project_id, f"撤销线下步骤确认: {node['name']}")
    return {"message": "已取消确认"}
