from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify
from backend.models import (
    Project, Milestone, RiskIssue, ProjectMember, TeamMember,
    ProjectPhaseGate, Phase, ChangeRequest, WeeklyReport
)
from backend import db
from sqlalchemy import func

bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard/overview')
def overview():
    total = Project.query.filter_by(is_active=True).count()
    normal = Project.query.filter_by(is_active=True, overall_status='normal').count()
    risk = Project.query.filter_by(is_active=True, overall_status='risk').count()
    blocked = Project.query.filter_by(is_active=True, overall_status='blocked').count()
    avg_pct = db.session.query(func.avg(Project.completion_pct)).filter_by(is_active=True).scalar() or 0

    open_risks = RiskIssue.query.filter_by(status='open').count()
    open_issues = RiskIssue.query.filter_by(status='open', type='issue').count()
    pending_changes = ChangeRequest.query.filter_by(status='pending').count()
    total_members = TeamMember.query.filter_by(is_active=True).count()

    # Count overloaded members
    overloaded = 0
    for m in TeamMember.query.filter_by(is_active=True).all():
        total_alloc = db.session.query(func.sum(ProjectMember.allocation_pct)).filter_by(member_id=m.id).scalar() or 0
        if total_alloc > 100:
            overloaded += 1

    # Schedule health
    today = date.today()
    behind_count = Project.query.filter(
        Project.is_active == True,
        Project.planned_end_date < today,
        Project.overall_status != 'completed'
    ).count()

    return jsonify({
        'total': total, 'normal': normal, 'risk': risk, 'blocked': blocked,
        'avg_completion': round(float(avg_pct), 1),
        'open_risks': open_risks, 'open_issues': open_issues,
        'pending_changes': pending_changes, 'total_members': total_members,
        'overloaded': overloaded, 'behind_schedule': behind_count,
    })


@bp.route('/dashboard/overall-assessment')
def overall_assessment():
    """汇总五：整体判断与建议"""
    projects = Project.query.filter_by(is_active=True).all()

    # Identify most at-risk project
    at_risk = sorted(projects, key=lambda p: (
        0 if p.overall_status == 'blocked' else 1 if p.overall_status == 'risk' else 2,
        -(p.completion_pct or 0)
    ))[:1]

    # Identify nearest deliverable
    nearest = sorted(
        [p for p in projects if p.overall_status != 'blocked'],
        key=lambda p: (p.planned_end_date or date(2099, 1, 1))
    )[:1]

    # Collect common issues
    all_blockers = [p.main_blocker for p in projects if p.main_blocker]
    all_risks = RiskIssue.query.filter_by(status='open').all()
    risk_categories = {}
    for r in all_risks:
        cat = r.line.name if r.line else '其他'
        risk_categories[cat] = risk_categories.get(cat, 0) + 1

    top_risks = sorted(risk_categories.items(), key=lambda x: -x[1])[:3]

    return jsonify({
        'most_at_risk': {
            'name': at_risk[0].name if at_risk else None,
            'status': at_risk[0].overall_status if at_risk else None,
            'reason': at_risk[0].main_blocker if at_risk else None,
        } if at_risk else None,
        'nearest_deliverable': {
            'name': nearest[0].name if nearest else None,
            'date': nearest[0].planned_end_date.isoformat() if nearest and nearest[0].planned_end_date else None,
        } if nearest else None,
        'top_risk_areas': [{'area': k, 'count': v} for k, v in top_risks],
        'total_blockers': len(all_blockers),
        'low_morale_count': len([p for p in projects if p.morale in ('低',)]),
    })


@bp.route('/dashboard/health-grid')
def health_grid():
    projects = Project.query.filter_by(is_active=True).order_by(Project.priority.asc()).all()
    grid = []
    for p in projects:
        pm = ProjectMember.query.filter_by(project_id=p.id, is_key=True).first()
        pm_name = pm.member.name if pm and pm.member else '-'
        block_count = RiskIssue.query.filter_by(project_id=p.id, status='open').count()
        grid.append({
            'id': p.id, 'name': p.name, 'code': p.code,
            'manager': pm_name,
            'phase': p.current_phase.name if p.current_phase else '-',
            'completion_pct': p.completion_pct,
            'status': p.overall_status,
            'planned_end_date': p.planned_end_date.isoformat() if p.planned_end_date else None,
            'member_count': ProjectMember.query.filter_by(project_id=p.id).count(),
            'open_issues': block_count,
            'priority': p.priority,
        })
    return jsonify(grid)


@bp.route('/dashboard/milestone-timeline')
def milestone_timeline():
    milestones = Milestone.query.join(Project).filter(
        Project.is_active == True,
        Milestone.is_key == True,
    ).order_by(Milestone.planned_date).all()
    return jsonify([m.to_dict() for m in milestones])


@bp.route('/dashboard/resource-matrix')
def resource_matrix():
    members = TeamMember.query.filter_by(is_active=True).all()
    result = []
    for m in members:
        pms = ProjectMember.query.filter_by(member_id=m.id).join(Project).filter(Project.is_active == True).all()
        total_alloc = sum(pm.allocation_pct for pm in pms)
        projects = []
        for pm in pms:
            projects.append({
                'project_id': pm.project_id,
                'project_name': pm.project.name,
                'role': pm.role.name if pm.role else '',
                'allocation_pct': pm.allocation_pct,
            })
        result.append({
            'member_id': m.id,
            'name': m.name,
            'department': m.department,
            'total_allocation': total_alloc,
            'is_overloaded': total_alloc > 100,
            'projects': projects,
        })
    return jsonify(result)


@bp.route('/dashboard/blocker-summary')
def blocker_summary():
    risks = RiskIssue.query.filter_by(status='open').all()
    cats = {}
    for r in risks:
        cat = r.line.name if r.line else '其他'
        if cat not in cats:
            cats[cat] = {'count': 0, 'critical': 0, 'high': 0}
        cats[cat]['count'] += 1
        if r.risk_level == 'critical':
            cats[cat]['critical'] += 1
        elif r.risk_level == 'high':
            cats[cat]['high'] += 1
    return jsonify([{'category': k, **v} for k, v in cats.items()])


@bp.route('/dashboard/pending-reports')
def pending_reports():
    """Check which active projects have no weekly report for the current week."""
    today = date.today()
    week_num = today.isocalendar()[1]
    year = today.year

    active_projects = Project.query.filter_by(is_active=True).all()
    pending = []

    for p in active_projects:
        # Check if report exists for this week
        report = WeeklyReport.query.filter_by(
            project_id=p.id, year=year, week_number=week_num
        ).first()

        if not report:
            # Check last report date
            last_report = WeeklyReport.query.filter_by(project_id=p.id).order_by(
                WeeklyReport.year.desc(), WeeklyReport.week_number.desc()
            ).first()

            last_week = None
            if last_report:
                # Calculate the Monday of last report's week
                import datetime as dt
                d = f"{last_report.year}-W{last_report.week_number:02d}-1"
                try:
                    last_week = dt.datetime.strptime(d, "%Y-W%W-%w").date().isoformat()
                except ValueError:
                    last_week = f"{last_report.year}-W{last_report.week_number}"

            pending.append({
                'project_id': p.id,
                'project_name': p.name,
                'project_code': p.code,
                'pm_name': p.members[0].member.name if p.members and p.members[0].member else '-',
                'phase': p.current_phase.name if p.current_phase else '-',
                'last_report_week': last_week,
                'weeks_without_report': 0 if last_report else None,
            })

    return jsonify(pending)
