"""Cross-project dashboard — cockpit view."""
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import (
    Project, Milestone, RiskIssue, WeeklyReport, ProjectMember,
    ProjectPhaseGate, TeamMember, Phase,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _user_project_ids(db, user):
    """Get project IDs visible to this user. Admin sees all."""
    if user.role == "admin":
        return None  # no filter
    if not user.member_id:
        return [-1]  # no projects
    ids = db.execute(
        select(ProjectMember.project_id).where(ProjectMember.member_id == user.member_id)
    ).scalars().all()
    return ids or [-1]


def _apply_user_filter(query, project_col, db, user):
    """Apply project-level access filter to a query."""
    ids = _user_project_ids(db, user)
    if ids is None:
        return query  # admin: no filter
    return query.where(project_col.in_(ids))


@router.get("")
def dashboard(db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    today = date.today()
    cal = today.isocalendar()
    this_year, this_week = cal[0], cal[1]
    user_pids = _user_project_ids(db, _current_user)

    # ── Summary 1: Project health (按健康信号实时推导,不落库) ──
    from collections import Counter
    from backend_v2.routes.projects import derive_project_health
    health_q = select(Project).where(Project.is_active == True)
    if user_pids is not None:
        health_q = health_q.where(Project.id.in_(user_pids))
    health_projects = db.execute(health_q).scalars().all()
    counts = Counter(derive_project_health(db, health_projects).values())

    blocked = counts.get("blocked", 0)
    at_risk = counts.get("at_risk", 0)
    normal = counts.get("normal", 0)
    total = len(health_projects)

    # ── Summary 2: Phase distribution ──
    phase_q = select(
        Phase.name, func.count(Project.id)
    ).join(Project.current_phase).where(Project.is_active == True)
    if user_pids is not None:
        phase_q = phase_q.where(Project.id.in_(user_pids))
    phase_q = phase_q.group_by(Phase.name)
    phase_result = db.execute(phase_q)
    phase_dist = [{"phase": row[0], "count": row[1]} for row in phase_result]

    # ── Summary 3: Overdue milestones ──
    # ── Summary 3: Overdue milestones ──
    overdue_q = select(func.count()).select_from(Milestone).join(Project).where(
        Project.is_active == True, Milestone.status != "completed", Milestone.planned_date < today)
    if user_pids is not None:
        overdue_q = overdue_q.where(Project.id.in_(user_pids))
    overdue = (db.execute(overdue_q)).scalar()

    # ── Summary 4: Open risks (含 AI 待审核) ──
    risks_q = select(func.count()).select_from(RiskIssue).join(Project).where(
        Project.is_active == True, RiskIssue.status.in_(["open", "in_progress", "pending_review"]))
    if user_pids is not None:
        risks_q = risks_q.where(Project.id.in_(user_pids))
    open_risks = (db.execute(risks_q)).scalar()

    # ── Summary 5: Pending reports (this week) ──
    submitted_q = select(WeeklyReport.project_id).where(WeeklyReport.year == this_year, WeeklyReport.week_number == this_week)
    if user_pids is not None:
        submitted_q = submitted_q.where(WeeklyReport.project_id.in_(user_pids))
    submitted_pid_set = {row[0] for row in db.execute(submitted_q)}
    active_q = select(func.count()).select_from(Project).where(Project.is_active == True)
    if user_pids is not None:
        active_q = active_q.where(Project.id.in_(user_pids))
    active_count = (db.execute(active_q)).scalar()
    pending_reports = active_count - len(submitted_pid_set)

    return {
        "summary": {
            "total": total, "blocked": blocked, "at_risk": at_risk, "normal": normal,
            "overdue_milestones": overdue, "open_risks": open_risks,
            "pending_reports": pending_reports,
        },
        "phase_distribution": phase_dist,
    }


@router.get("/alerts")
def alerts(db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    today = date.today()
    cal = today.isocalendar()
    this_year, this_week = cal[0], cal[1]
    user_pids = _user_project_ids(db, _current_user)

    from backend_v2.routes.projects import derive_project_health
    health_q = select(Project).where(Project.is_active == True)
    if user_pids is not None: health_q = health_q.where(Project.id.in_(user_pids))
    health_projects = db.execute(health_q).scalars().all()
    health_map = derive_project_health(db, health_projects)
    blocked = [p for p in health_projects if health_map.get(p.id) == "blocked"]

    overdue_q = select(Milestone).join(Project).where(
        Project.is_active == True, Milestone.status != "completed", Milestone.planned_date < today)
    if user_pids is not None: overdue_q = overdue_q.where(Project.id.in_(user_pids))
    overdue_ms = (db.execute(overdue_q.order_by(Milestone.planned_date).limit(10))).scalars().all()

    submitted_pids = {row[0] for row in (
        db.execute(select(WeeklyReport.project_id).where(WeeklyReport.year == this_year, WeeklyReport.week_number == this_week))
    )}
    pending_q = select(Project).where(Project.is_active == True, Project.id.notin_(submitted_pids or [-1]))
    if user_pids is not None: pending_q = pending_q.where(Project.id.in_(user_pids))
    pending = (db.execute(pending_q)).scalars().all()

    def _mini(p):
        return {"id": p.id, "code": p.code, "name": p.name, "overall_status": p.overall_status, "main_blocker": p.main_blocker}

    return {
        "blocked_projects": [_mini(p) for p in blocked],
        "overdue_milestones": [
            {"id": m.id, "name": m.name, "planned_date": m.planned_date.isoformat() if m.planned_date else None,
             "project_name": m.project.name, "project_id": m.project_id}
            for m in overdue_ms
        ],
        "pending_reports": [_mini(p) for p in pending],
    }


@router.get("/pending-reports")
def pending_reports(db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    today = date.today()
    cal = today.isocalendar()
    this_year, this_week = cal[0], cal[1]
    user_pids = _user_project_ids(db, _current_user)

    submitted_pids = {row[0] for row in (
        db.execute(select(WeeklyReport.project_id).where(WeeklyReport.year == this_year, WeeklyReport.week_number == this_week))
    )}
    pending_q = select(Project).where(Project.is_active == True, Project.id.notin_(submitted_pids or [-1]))
    if user_pids is not None: pending_q = pending_q.where(Project.id.in_(user_pids))
    pending = (db.execute(pending_q)).scalars().all()

    cal2 = (today + timedelta(days=7)).isocalendar()
    last_week_pids = {row[0] for row in (
        db.execute(select(WeeklyReport.project_id).where(WeeklyReport.year == this_year, WeeklyReport.week_number == this_week - 1))
    )}

    return [{
        "id": p.id, "code": p.code, "name": p.name,
        "had_report_last_week": p.id in last_week_pids,
        "current_phase": p.current_phase.name if p.current_phase else None,
    } for p in pending]
