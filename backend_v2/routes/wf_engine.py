"""工作流引擎接口。

与既有 routes/project_workflow.py 的分工：
  那个是**只读视图**（按交付物现算状态 + 线下步骤人工确认），本次没碰。
  这个是**状态机**（引擎持有状态、服务端强制校验权限、支持强制拖拽与回退）。

路径统一挂在 /api/projects/{pid}/wf-engine 下，和既有 /workflow 并列不重叠，
前端可以在同一页里两个都要，也可以只要一个。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_v2.auth import get_current_user
from backend_v2.database import get_db
from backend_v2.models import (
    Project, ProjectMember, WfTemplate, WfTemplateVersion,
    ProjectWfInstance, ProjectWfState, ProjectWfNodeAcl,
    WfForceDragLog, WfStateChangeLog,
)
from backend_v2.audit import log_audit
from backend_v2 import workflow_engine as eng

router = APIRouter(tags=["wf-engine"])


def _translate(e: eng.WfError):
    """引擎错误 → HTTP 错误。引擎不依赖 fastapi，翻译在路由层做。"""
    raise HTTPException(status_code=e.status_code, detail=e.detail)


def _get_project(db: Session, pid: int) -> Project:
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(404, "项目不存在")
    return p


def _ensure_access(db: Session, project: Project, user):
    """能看这个项目才给用引擎。

    判据与既有 `GET /api/projects/{id}`（projects.py:396-400）逐条对齐：
    admin，或该项目的成员。**故意不写 `check_permission(user,"projects","view")`** ——
    加那一条会让任何拿到默认 member 矩阵的人绕过成员校验，看到不属于自己的项目的
    状态机，比它所在的项目详情页还宽。权限只能平移，不能放宽。

    注意这里**只**管能不能看；能不能流转由引擎按节点 ACL 单独判——
    两件事分开，不把查看权当操作权。
    """
    if user.role == "admin":
        return
    if getattr(user, "member_id", None):
        hit = db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.member_id == user.member_id,
            )
        ).scalars().first()
        if hit is not None:
            return
    raise HTTPException(403, "你不是该项目成员，无权查看工作流")


def _instance_or_create(db: Session, project: Project, user) -> ProjectWfInstance:
    """拿到实例；没有就按项目类型现场实例化一个。

    故意做成"懒实例化"而不是在项目创建接口里挂钩子：这样**存量项目**第一次
    被打开时自动获得实例，不需要写一次性迁移脚本去补历史数据，也不用改
    projects.py（那是最多人用的接口，动它的风险远大于收益）。
    """
    inst = db.execute(
        select(ProjectWfInstance).where(ProjectWfInstance.project_id == project.id)
    ).scalar_one_or_none()
    if inst is not None:
        return inst
    inst = eng.instantiate(db, project, created_by=user.username)
    if inst is None:
        raise HTTPException(404, "该项目类型暂无可用工作流模板（一期只开放 A/B 两个合同交付模板）")
    db.flush()
    return inst


def _template_info(db: Session, inst: ProjectWfInstance) -> dict:
    tpl = db.get(WfTemplate, inst.template_id)
    cur = db.get(WfTemplateVersion, inst.current_version_id)
    base = db.get(WfTemplateVersion, inst.base_version_id)
    return {
        "code": tpl.code if tpl else None,
        "name": tpl.name if tpl else None,
        "category": tpl.category if tpl else None,
        "base_version_no": base.version_no if base else None,
        "current_version_no": cur.version_no if cur else None,
        # 基于的版本 ≠ 当前版本 = 迁移过。一期还没有迁移入口，
        # 这个字段先恒为 False，等二期做迁移时它就是判据。
        "is_migrated": inst.base_version_id != inst.current_version_id,
        "migrated_at": inst.migrated_at.isoformat() if inst.migrated_at else None,
    }


def _state_payload(db, inst, states, roles, user):
    """组装每个状态的权限视图。

    对每个状态调一次 resolve_permissions —— N 个状态 N 次查询，看起来笨。
    但状态数在百量级、且这是按项目打开的页面，一次请求几百次 SQLite 主键
    查询比引入一套批量解析+缓存失效逻辑便宜得多。等真的有性能问题再说，
    现在优化是猜。
    """
    acl_rows = db.execute(
        select(ProjectWfNodeAcl).where(ProjectWfNodeAcl.instance_id == inst.id)
    ).scalars().all()
    roles_by_state = {}
    for r in acl_rows:
        if r.subject_type in ("role_name", "project_role"):
            roles_by_state.setdefault(r.state_code, []).append(r.subject_name)

    out = []
    for s in states:
        perm = eng.resolve_permissions(db, inst.id, s.state_code, user, roles)
        out.append({
            "state_code": s.state_code,
            "name": s.name,
            "semantic_state": s.semantic_state,
            "semantic_label": eng.SEMANTIC_LABELS.get(s.semantic_state, s.semantic_state),
            "runtime_status": s.runtime_status,
            "runtime_label": eng.SEMANTIC_LABELS.get(s.runtime_status, s.runtime_status),
            "status_source": s.status_source,
            "phase_code": s.phase_code,
            "lane": s.lane,
            "node_seq": s.node_seq,
            "sort_order": s.sort_order,
            "is_gate": bool(s.is_gate),
            "is_required": bool(s.is_required),
            "is_initial": bool(s.is_initial),
            "is_terminal": bool(s.is_terminal),
            "assigned_roles": roles_by_state.get(s.state_code, []),
            "last_changed_at": s.last_changed_at.isoformat() if s.last_changed_at else None,
            "last_changed_by": s.last_changed_by,
            "can": {a: perm[a] for a in eng.PERM_ATOMS},
            "perm_reason": perm.get("reason"),
        })
    return out


@router.get("/api/projects/{pid}/wf-engine")
def get_engine_view(pid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """项目的工作流状态机视图。"""
    project = _get_project(db, pid)
    _ensure_access(db, project, user)
    inst = _instance_or_create(db, project, user)

    roles = eng.my_roles(db, project.id, user)
    states = db.execute(
        select(ProjectWfState).where(ProjectWfState.instance_id == inst.id)
        .order_by(ProjectWfState.sort_order)
    ).scalars().all()

    payload = _state_payload(db, inst, states, roles, user)

    # 按泳道（阶段）分组。泳道名取阶段中文名，前端直接显示。
    lanes = []
    for item in payload:
        if not lanes or lanes[-1]["lane"] != item["lane"]:
            lanes.append({
                "lane": item["lane"],
                "lane_name": eng.PHASE_NAMES.get(item["lane"], item["lane"]),
                "states": [],
            })
        lanes[-1]["states"].append(item)

    done = sum(1 for s in states if s.runtime_status == "completed")
    current = eng._current_state({s.state_code: s for s in states})

    return {
        "supported": True,
        "project_id": project.id,
        "template": _template_info(db, inst),
        "current_state_code": current.state_code if current else None,
        "semantic_labels": eng.SEMANTIC_LABELS,
        "perm_labels": eng.PERM_LABELS,
        "lanes": lanes,
        "states": payload,
        "summary": {
            "total": len(states), "completed": done,
            "blocked": sum(1 for s in states if s.runtime_status == "blocked"),
            "percent": round(done * 100 / len(states)) if states else 0,
        },
        "me": {
            "username": user.username,
            "roles": roles,
            "is_admin": user.role == "admin",
            # 与引擎一致：项目经理或管理员才有强制拖拽
            "is_pm": ("项目经理" in roles) or user.role == "admin",
        },
    }


@router.post("/api/projects/{pid}/wf-engine/states/{state_code}/transition")
def post_transition(pid: int, state_code: str, data: dict,
                    db: Session = Depends(get_db), user=Depends(get_current_user)):
    """正式流转到下一个状态。服务端强制校验退出权限与路径合法性。"""
    project = _get_project(db, pid)
    _ensure_access(db, project, user)
    inst = _instance_or_create(db, project, user)
    roles = eng.my_roles(db, project.id, user)

    to_state_code = (data or {}).get("to_state_code")
    if not to_state_code:
        raise HTTPException(400, "缺少 to_state_code")

    try:
        result = eng.advance(db, project, inst, state_code, to_state_code,
                             user, roles, (data or {}).get("reason"))
    except eng.WfError as e:
        _translate(e)

    db.commit()
    log_audit(db, user.username, "update", "project_wf_state", inst.id,
              f"{state_code} → {to_state_code}", project.id, "工作流状态流转")
    return {"ok": True, **result}


@router.post("/api/projects/{pid}/wf-engine/states/{state_code}/status")
def post_status(pid: int, state_code: str, data: dict,
                db: Session = Depends(get_db), user=Depends(get_current_user)):
    """改运行态（阻塞/取消/恢复），不移动位置。"""
    project = _get_project(db, pid)
    _ensure_access(db, project, user)
    inst = _instance_or_create(db, project, user)
    roles = eng.my_roles(db, project.id, user)

    to_status = (data or {}).get("to_status")
    if not to_status:
        raise HTTPException(400, "缺少 to_status")

    try:
        result = eng.set_status(db, project, inst, state_code, to_status,
                                user, roles, (data or {}).get("reason"))
    except eng.WfError as e:
        _translate(e)

    db.commit()
    log_audit(db, user.username, "update", "project_wf_state", inst.id,
              f"{state_code} → {to_status}", project.id, "工作流运行态变更")
    return {"ok": True, **result}


@router.post("/api/projects/{pid}/wf-engine/force-drag")
def post_force_drag(pid: int, data: dict,
                    db: Session = Depends(get_db), user=Depends(get_current_user)):
    """PM 强制拖拽：跳到任意状态，跳过必经节点要填原因，全程留痕。"""
    project = _get_project(db, pid)
    _ensure_access(db, project, user)
    inst = _instance_or_create(db, project, user)
    roles = eng.my_roles(db, project.id, user)

    to_state_code = (data or {}).get("to_state_code")
    if not to_state_code:
        raise HTTPException(400, "缺少 to_state_code")

    try:
        result = eng.force_drag(db, project, inst, to_state_code, user, roles,
                                (data or {}).get("reason"))
    except eng.WfError as e:
        _translate(e)

    db.commit()
    # 强制拖拽是能跳过门禁的操作，除了引擎自己的台账，也写一条全局审计——
    # 审计页的读者不一定知道 wf_force_drag_log 在哪。
    log_audit(db, user.username, "force_drag", "project_wf_state", inst.id,
              f"强制拖拽至 {to_state_code}", project.id,
              f"跳过 {len(result.get('skipped') or [])} 个节点：{(data or {}).get('reason') or '（未填）'}")
    return {"ok": True, **result}


@router.post("/api/projects/{pid}/wf-engine/force-drag/{log_id}/revert")
def post_revert(pid: int, log_id: int, data: dict = None,
                db: Session = Depends(get_db), user=Depends(get_current_user)):
    """回退一次强制拖拽。"""
    project = _get_project(db, pid)
    _ensure_access(db, project, user)
    inst = _instance_or_create(db, project, user)
    roles = eng.my_roles(db, project.id, user)

    try:
        result = eng.revert_force_drag(db, project, inst, log_id, user, roles,
                                       (data or {}).get("reason"))
    except eng.WfError as e:
        _translate(e)

    db.commit()
    log_audit(db, user.username, "revert", "project_wf_state", inst.id,
              f"回退强制拖拽 #{log_id}", project.id, "工作流强制拖拽回退")
    return {"ok": True, **result}


@router.get("/api/projects/{pid}/wf-engine/force-drag-logs")
def list_force_drag_logs(pid: int, limit: int = Query(50, ge=1, le=200),
                         db: Session = Depends(get_db), user=Depends(get_current_user)):
    """强制拖拽台账。审计字段全部来自当时的快照，不 join 现算。"""
    project = _get_project(db, pid)
    _ensure_access(db, project, user)
    inst = db.execute(
        select(ProjectWfInstance).where(ProjectWfInstance.project_id == project.id)
    ).scalar_one_or_none()
    if inst is None:
        return []

    rows = db.execute(
        select(WfForceDragLog).where(WfForceDragLog.instance_id == inst.id)
        .order_by(WfForceDragLog.created_at.desc()).limit(limit)
    ).scalars().all()

    return [{
        "id": r.id,
        "from_state_code": r.from_state_code,
        "from_state_name": r.from_state_name,
        "to_state_code": r.to_state_code,
        "to_state_name": r.to_state_name,
        "operator": r.operator,
        "operator_roles": eng._json_loads(r.operator_roles, []),
        "reason": r.reason,
        "reason_required": bool(r.reason_required),
        "skipped_states": eng._json_loads(r.skipped_states, []),
        "has_unrevertable": bool(r.has_unrevertable),
        "is_reverted": bool(r.is_reverted),
        "reverted_at": r.reverted_at.isoformat() if r.reverted_at else None,
        "reverted_by": r.reverted_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.get("/api/projects/{pid}/wf-engine/change-log")
def list_change_log(pid: int, limit: int = Query(100, ge=1, le=500),
                    db: Session = Depends(get_db), user=Depends(get_current_user)):
    """状态流转台账。"""
    project = _get_project(db, pid)
    _ensure_access(db, project, user)
    inst = db.execute(
        select(ProjectWfInstance).where(ProjectWfInstance.project_id == project.id)
    ).scalar_one_or_none()
    if inst is None:
        return []

    rows = db.execute(
        select(WfStateChangeLog).where(WfStateChangeLog.instance_id == inst.id)
        .order_by(WfStateChangeLog.created_at.desc()).limit(limit)
    ).scalars().all()

    return [{
        "id": r.id, "state_code": r.state_code,
        "from_semantic": r.from_semantic,
        "from_label": eng.SEMANTIC_LABELS.get(r.from_semantic, r.from_semantic),
        "to_semantic": r.to_semantic,
        "to_label": eng.SEMANTIC_LABELS.get(r.to_semantic, r.to_semantic),
        "action": r.action, "operator": r.operator,
        "operator_roles": eng._json_loads(r.operator_roles, []),
        "reason": r.reason,
        "force_drag_log_id": r.force_drag_log_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.get("/api/wf-engine/templates")
def list_templates(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """可用模板清单（给"新建项目选模板"和运维排查用）。"""
    rows = db.execute(
        select(WfTemplate).order_by(WfTemplate.sort_order)
    ).scalars().all()
    out = []
    for t in rows:
        vers = db.execute(
            select(WfTemplateVersion).where(WfTemplateVersion.template_id == t.id)
            .order_by(WfTemplateVersion.version_no)
        ).scalars().all()
        out.append({
            "id": t.id, "code": t.code, "name": t.name,
            "project_type": t.project_type, "category": t.category,
            "description": t.description, "is_active": bool(t.is_active),
            "versions": [{"id": v.id, "version_no": v.version_no, "status": v.status} for v in vers],
            # 用了这个模板的项目实例数——判断"能不能改模板内容"的依据
            "instance_count": db.query(ProjectWfInstance).filter(
                ProjectWfInstance.template_id == t.id).count(),
        })
    return out


@router.post("/api/wf-engine/backfill")
def backfill_instances(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """给存量项目批量建实例（懒实例化之外的一条明路）。

    懒实例化让项目被打开时才建；这个接口给运维一个"一次性全建好"的手段，
    需要管理员。幂等：已有实例的项目跳过。
    """
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")

    projects = db.execute(
        select(Project).where(Project.is_active == True)  # noqa: E712
    ).scalars().all()

    created, skipped, no_template = [], [], []
    for p in projects:
        exist = db.execute(
            select(ProjectWfInstance).where(ProjectWfInstance.project_id == p.id)
        ).scalar_one_or_none()
        if exist is not None:
            skipped.append(p.code)
            continue
        inst = eng.instantiate(db, p, created_by=user.username)
        if inst is None:
            no_template.append(p.code)
        else:
            created.append(p.code)

    db.commit()
    return {"created": created, "skipped": skipped, "no_template": no_template}
