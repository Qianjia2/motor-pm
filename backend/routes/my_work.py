"""Personal workspace API — aggregates todos for the current user."""
from datetime import date, datetime
from flask import Blueprint, request, jsonify, g
from backend import db
from backend.models import (
    UserAuth, TeamMember, ProjectMember, Project,
    Milestone, RiskIssue, WeeklyReport, AuditLog
)
from backend.routes.auth import require_auth

bp = Blueprint('my_work', __name__)


def get_my_member_id():
    """Get the TeamMember id for the currently authenticated user."""
    try:
        return g.current_user.member_id
    except Exception:
        return None


@bp.route('/my-work', methods=['GET'])
@require_auth
def my_work():
    member_id = get_my_member_id()

    # For admin or users without team member link: show all active projects
    if not member_id or g.current_user.role == 'admin':
        my_projects = Project.query.filter(Project.is_active == True).all()
        my_project_ids = [p.id for p in my_projects]
    else:
        my_pm = ProjectMember.query.filter_by(member_id=member_id).all()
        my_project_ids = [pm.project_id for pm in my_pm]
        my_projects = Project.query.filter(
            Project.id.in_(my_project_ids),
            Project.is_active == True
        ).all()

    # 2. My upcoming milestones (next 30 days)
    today = date.today()
    my_milestones = Milestone.query.filter(
        Milestone.project_id.in_(my_project_ids),
        Milestone.status != 'completed',
        Milestone.planned_date >= today,
        Milestone.planned_date <= today.replace(day=28) + date.resolution * 3  # ~30 days
    ).order_by(Milestone.planned_date).all()

    # 3. My open risks/issues (admin sees all, others see their own)
    risk_q = RiskIssue.query.filter(
        RiskIssue.project_id.in_(my_project_ids),
        RiskIssue.status.in_(['open', 'in_progress'])
    )
    if member_id:
        risk_q = risk_q.filter(RiskIssue.owner_id == member_id)
    my_risks = risk_q.order_by(RiskIssue.created_at.desc()).all()

    # 4. Pending weekly reports (this week)
    from datetime import datetime as dt
    cal = today.isocalendar()
    this_year, this_week = cal[0], cal[1]
    submitted_reports = WeeklyReport.query.filter(
        WeeklyReport.project_id.in_(my_project_ids),
        WeeklyReport.year == this_year,
        WeeklyReport.week_number == this_week,
    ).all()
    submitted_pids = {r.project_id for r in submitted_reports}
    pending_report_projects = [p for p in my_projects if p.id not in submitted_pids]

    # 5. Recent activity
    recent_logs = AuditLog.query.filter(
        AuditLog.project_id.in_(my_project_ids)
    ).order_by(AuditLog.created_at.desc()).limit(20).all()

    # 6. Overdue milestones
    overdue_milestones = Milestone.query.filter(
        Milestone.project_id.in_(my_project_ids),
        Milestone.status != 'completed',
        Milestone.planned_date < today,
    ).order_by(Milestone.planned_date).all()

    return jsonify({
        'member_id': member_id,
        'my_projects': [p.to_dict() for p in my_projects],
        'upcoming_milestones': [m.to_dict() for m in my_milestones],
        'overdue_milestones': [m.to_dict() for m in overdue_milestones],
        'my_risks': [r.to_dict() for r in my_risks],
        'pending_reports': [p.to_dict() for p in pending_report_projects],
        'recent_logs': [l.to_dict() for l in recent_logs],
    })
