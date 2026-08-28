"""Personal workspace — todos aggregated for current user."""
from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import (
    Project, ProjectMember, Milestone, RiskIssue, WeeklyReport, AuditLog, Task, UserAuth,
    GateSignoffRecord, ChangeSignoffRecord, ReviewActionItem, ProjectPhaseGate, ChangeRequest,
    Deliverable,
)

router = APIRouter(prefix="/api/my-work", tags=["my-work"])


@router.get("")
def my_work(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    member_id = current_user.member_id
    is_admin = current_user.role == "admin"

    # 管理员默认可见全部项目;普通成员按项目成员关系过滤
    if not is_admin and not member_id:
        return {"my_projects": [], "upcoming_milestones": [], "overdue_milestones": [],
                "completed_milestones": [], "milestones": [],
                "my_risks": [], "pending_reports": [], "my_tasks": [], "recent_logs": [],
                "error": "用户未关联团队成员"}

    today = date.today()
    cal = today.isocalendar()
    this_year, this_week = cal[0], cal[1]

    if is_admin:
        my_pids = None  # 不过滤
    else:
        pm_result = db.execute(select(ProjectMember).where(ProjectMember.member_id == member_id))
        my_pids = [pm.project_id for pm in pm_result.scalars().all()]
        if not my_pids:
            return {"my_projects": [], "upcoming_milestones": [], "overdue_milestones": [],
                    "completed_milestones": [], "milestones": [],
                    "my_risks": [], "pending_reports": [], "my_tasks": [], "recent_logs": []}

    def _scoped(q, col):
        if my_pids is not None:
            q = q.where(col.in_(my_pids))
        return q

    # My projects
    projects_result = db.execute(
        _scoped(select(Project).where(Project.is_active == True), Project.id)
    )
    my_projects = [{"id": p.id, "code": p.code, "name": p.name, "overall_status": p.overall_status,
                    "completion_pct": p.completion_pct, "priority": p.priority} for p in projects_result.scalars().all()]

    # Upcoming milestones (30 days)
    upcoming = db.execute(
        _scoped(
            select(Milestone).where(
                Milestone.status != "completed",
                Milestone.planned_date >= today,
                Milestone.planned_date <= today + timedelta(days=30),
            ).order_by(Milestone.planned_date),
            Milestone.project_id,
        )
    )
    upcoming_ms = [{"id": m.id, "name": m.name, "phase_id": m.phase_id,
                    "planned_date": m.planned_date.isoformat() if m.planned_date else None,
                    "project_id": m.project_id, "project_name": m.project.name, "status": m.status,
                    "phase_name": m.phase.name if m.phase else None} for m in upcoming.scalars().all()]

    # Overdue milestones
    overdue_result = db.execute(
        _scoped(
            select(Milestone).where(
                Milestone.status != "completed",
                Milestone.planned_date < today,
            ).order_by(Milestone.planned_date),
            Milestone.project_id,
        )
    )
    overdue_ms = [{"id": m.id, "name": m.name, "planned_date": m.planned_date.isoformat() if m.planned_date else None,
                   "project_id": m.project_id, "project_name": m.project.name, "status": m.status,
                   "phase_name": m.phase.name if m.phase else None} for m in overdue_result.scalars().all()]

    # Recently completed milestones (30 days)
    cutoff = today - timedelta(days=30)
    done_date = func.coalesce(Milestone.actual_date, Milestone.planned_date)
    completed_result = db.execute(
        _scoped(
            select(Milestone).where(
                Milestone.status == "completed",
                done_date >= cutoff,
                done_date <= today,
            ).order_by(done_date.desc()),
            Milestone.project_id,
        ).limit(10)
    )
    completed_ms = [{"id": m.id, "name": m.name, "phase_id": m.phase_id,
                     "actual_date": done.isoformat() if (done := m.actual_date or m.planned_date) else None,
                     "project_id": m.project_id, "project_name": m.project.name,
                     "phase_name": m.phase.name if m.phase else None} for m in completed_result.scalars().all()]

    # 交付成果:里程碑所属阶段已提交/已批准的交付物
    def _deliverables(pid, phase_id):
        if not phase_id:
            return []
        rows = db.execute(
            select(Deliverable.name).where(
                Deliverable.project_id == pid,
                Deliverable.phase_id == phase_id,
                Deliverable.status.in_(["submitted", "reviewed", "approved"]),
            ).limit(5)
        ).scalars().all()
        return list(rows)

    # 近期里程碑:刚完成(近30天,按完成日期倒序)在前 + 未来30天要完成(按计划日期升序)在后
    milestones = []
    for m in completed_ms:
        milestones.append({"id": m["id"], "name": m["name"], "date": m["actual_date"],
                           "phase_name": m["phase_name"], "status": "completed", "kind": "completed",
                           "deliverables": _deliverables(m["project_id"], m["phase_id"]),
                           "project_id": m["project_id"], "project_name": m["project_name"]})
    for m in upcoming_ms:
        milestones.append({"id": m["id"], "name": m["name"], "date": m["planned_date"],
                           "phase_name": m["phase_name"], "status": m["status"], "kind": "upcoming",
                           "deliverables": _deliverables(m["project_id"], m["phase_id"]),
                           "project_id": m["project_id"], "project_name": m["project_name"]})

    # Open risks(管理员看全部,普通成员看自己负责的)
    risks_q = select(RiskIssue).where(RiskIssue.status.in_(["open", "in_progress"]))
    risks_q = _scoped(risks_q, RiskIssue.project_id)
    if not is_admin:
        risks_q = risks_q.where(RiskIssue.owner_id == member_id)
    risks_result = db.execute(risks_q.order_by(RiskIssue.created_at.desc()))
    my_risks = [{"id": r.id, "title": r.title, "risk_level": r.risk_level, "status": r.status,
                 "project_id": r.project_id, "project_name": r.project.name} for r in risks_result.scalars().all()]

    # Pending reports
    submitted = {row[0] for row in (
        db.execute(select(WeeklyReport.project_id).where(WeeklyReport.year == this_year, WeeklyReport.week_number == this_week))
    )}
    pending_ids = [pid for pid in my_projects if pid["id"] not in submitted]
    pending = [{"id": p["id"], "code": p["code"], "name": p["name"]} for p in pending_ids]

    # This week's tasks (WBS)
    week_start = today - timedelta(days=today.weekday())
    tasks_q = select(Task).where(
        Task.status.in_(["pending", "in_progress", "blocked"]),
        Task.end_date >= week_start,
    )
    tasks_q = _scoped(tasks_q, Task.project_id)
    if not is_admin:
        tasks_q = tasks_q.where(Task.assignee_id == member_id)
    tasks_result = db.execute(tasks_q.order_by(Task.status, Task.end_date))
    my_tasks = [{"id": t.id, "name": t.name, "status": t.status, "progress_pct": t.progress_pct or 0,
                 "end_date": t.end_date.isoformat() if t.end_date else None,
                 "project_name": t.project.name if t.project else None, "project_id": t.project_id}
                for t in tasks_result.scalars().all()]

    # Recent activity — non-admin users don't see admin actions
    log_q = _scoped(select(AuditLog), AuditLog.project_id)
    if current_user.role != "admin":
        # Exclude audit logs from admin users
        admin_usernames = [r[0] for r in db.execute(
            select(UserAuth.username).where(UserAuth.role == "admin")
        ).all()]
        if admin_usernames:
            log_q = log_q.where(AuditLog.username.notin_(admin_usernames))
    logs_result = db.execute(
        log_q.order_by(AuditLog.created_at.desc()).limit(20)
    )
    recent = [{"id": l.id, "username": l.username, "action": l.action, "entity_type": l.entity_type,
               "summary": l.summary, "created_at": l.created_at.isoformat() if l.created_at else None}
              for l in logs_result.scalars().all()]

    # 待办任务:阶段门放行签核 / 变更签核 / 评审整改行动项(管理员可处理全部,成员只看自己的)
    pending_tasks = []
    signoff_q = select(GateSignoffRecord).options(
        selectinload(GateSignoffRecord.phase_gate).selectinload(ProjectPhaseGate.project),
        selectinload(GateSignoffRecord.phase_gate).selectinload(ProjectPhaseGate.phase),
        selectinload(GateSignoffRecord.phase_gate).selectinload(ProjectPhaseGate.gate),
    ).where(GateSignoffRecord.status == "pending")
    if not is_admin:
        signoff_q = signoff_q.where(GateSignoffRecord.signer_id == member_id)
    for r in db.execute(signoff_q.order_by(GateSignoffRecord.created_at.desc())).scalars().all():
        pg = r.phase_gate
        pending_tasks.append({
            "type": "gate_signoff", "id": r.id, "level": r.level,
            "title": f"{pg.phase.name if pg.phase else ''}·{pg.gate.name if pg.gate else ''} 门放行签核",
            "project_id": pg.project_id if pg else None,
            "project_name": pg.project.name if pg and pg.project else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    change_q = select(ChangeSignoffRecord).options(
        selectinload(ChangeSignoffRecord.change).selectinload(ChangeRequest.project),
    ).where(ChangeSignoffRecord.status == "pending")
    if not is_admin:
        change_q = change_q.where(ChangeSignoffRecord.signer_id == member_id)
    for r in db.execute(change_q.order_by(ChangeSignoffRecord.created_at.desc())).scalars().all():
        c = r.change
        if not c or not c.project or not c.project.is_active:
            continue
        pending_tasks.append({
            "type": "change_signoff", "id": r.id, "level": r.level,
            "title": f"变更签核(L{r.level}): {c.title}",
            "project_id": c.project_id,
            "project_name": c.project.name if c.project else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    if member_id:
        rai_q = select(ReviewActionItem).options(
            selectinload(ReviewActionItem.phase_gate).selectinload(ProjectPhaseGate.project),
        ).where(ReviewActionItem.status == "open", ReviewActionItem.assignee_id == member_id)
        for r in db.execute(rai_q.order_by(ReviewActionItem.due_date.asc())).scalars().all():
            pg = r.phase_gate
            pending_tasks.append({
                "type": "review_action", "id": r.id, "title": r.title,
                "project_id": pg.project_id if pg else None,
                "project_name": pg.project.name if pg and pg.project else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

    pending_tasks.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    return {
        "my_projects": my_projects,
        "upcoming_milestones": upcoming_ms,
        "overdue_milestones": overdue_ms,
        "completed_milestones": completed_ms,
        "milestones": milestones,
        "my_risks": my_risks,
        "pending_reports": pending,
        "my_tasks": my_tasks,
        "recent_logs": recent,
        "pending_tasks": pending_tasks[:30],
    }
