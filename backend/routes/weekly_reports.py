from datetime import date, datetime
from flask import Blueprint, request, jsonify
from backend import db
from backend.models import WeeklyReport, WeeklyReportLine, TechnicalLine
from backend.audit import log_action, get_username

bp = Blueprint('weekly_reports', __name__)


@bp.route('/projects/<int:pid>/reports', methods=['GET'])
def list_reports(pid):
    reports = WeeklyReport.query.filter_by(project_id=pid).order_by(WeeklyReport.year.desc(), WeeklyReport.week_number.desc()).all()
    return jsonify([r.to_dict() for r in reports])


@bp.route('/projects/<int:pid>/reports/latest', methods=['GET'])
def latest_report(pid):
    r = WeeklyReport.query.filter_by(project_id=pid).order_by(WeeklyReport.year.desc(), WeeklyReport.week_number.desc()).first()
    return jsonify(r.to_dict()) if r else jsonify(None)


@bp.route('/projects/<int:pid>/reports', methods=['POST'])
def create_report(pid):
    data = request.get_json()

    existing = WeeklyReport.query.filter_by(
        project_id=pid, year=data['year'], week_number=data['week_number']
    ).first()

    if existing:
        # Update existing report for this week
        for f in ['overall_progress', 'key_accomplishments', 'completion_rate', 'reporter_id']:
            if f in data:
                setattr(existing, f, data[f])
        if data.get('report_date'):
            existing.report_date = date.fromisoformat(data['report_date'])

        if 'line_items' in data:
            for item in data['line_items']:
                li = WeeklyReportLine.query.filter_by(report_id=existing.id, line_id=item['line_id']).first()
                if li:
                    for f in ['this_week', 'next_week', 'status', 'blocker', 'coordinator']:
                        if f in item:
                            setattr(li, f, item[f])

        db.session.commit()
        log_action(get_username(), 'update', 'report', existing.id,
                   f'W{existing.year}-{existing.week_number}',
                   project_id=pid, summary=f'更新周报 W{existing.year}-W{existing.week_number}')
        return jsonify(existing.to_dict()), 200

    report = WeeklyReport(
        project_id=pid,
        week_number=data['week_number'],
        year=data['year'],
        report_date=date.fromisoformat(data['report_date']) if data.get('report_date') else None,
        overall_progress=data.get('overall_progress', ''),
        key_accomplishments=data.get('key_accomplishments', ''),
        completion_rate=data.get('completion_rate', ''),
        reporter_id=data.get('reporter_id'),
    )
    db.session.add(report)
    db.session.flush()

    line_items = data.get('line_items', [])
    for item in line_items:
        li = WeeklyReportLine(
            report_id=report.id,
            line_id=item['line_id'],
            this_week=item.get('this_week', ''),
            next_week=item.get('next_week', ''),
            status=item.get('status', 'normal'),
            blocker=item.get('blocker', ''),
            coordinator=item.get('coordinator', ''),
            sort_order=item.get('sort_order', 0),
        )
        db.session.add(li)

    db.session.commit()
    log_action(get_username(), 'create', 'report', report.id,
               f'W{report.year}-{report.week_number}',
               project_id=pid, summary=f'提交周报 W{report.year}-W{report.week_number}')
    return jsonify(report.to_dict()), 201


@bp.route('/reports/<int:id>', methods=['GET'])
def get_report(id):
    r = WeeklyReport.query.get_or_404(id)
    return jsonify(r.to_dict())


@bp.route('/reports/<int:id>', methods=['PUT'])
def update_report(id):
    r = WeeklyReport.query.get_or_404(id)
    data = request.get_json()
    str_fields = ['overall_progress', 'key_accomplishments', 'completion_rate']
    for f in str_fields:
        if f in data:
            setattr(r, f, data[f])
    if 'reporter_id' in data:
        r.reporter_id = data['reporter_id']
    if data.get('report_date'):
        r.report_date = date.fromisoformat(data['report_date'])

    # Update line items
    if 'line_items' in data:
        for item in data['line_items']:
            li = WeeklyReportLine.query.filter_by(report_id=id, line_id=item['line_id']).first()
            if li:
                for f in ['this_week', 'next_week', 'status', 'blocker', 'coordinator']:
                    if f in item:
                        setattr(li, f, item[f])

    db.session.commit()
    return jsonify(r.to_dict())
