from datetime import date
from flask import Blueprint, request, jsonify
from backend import db
from backend.models import ChangeRequest
from backend.audit import log_action, get_username

bp = Blueprint('changes', __name__)


@bp.route('/projects/<int:pid>/changes', methods=['GET'])
def list_changes(pid):
    changes = ChangeRequest.query.filter_by(project_id=pid).order_by(ChangeRequest.created_at.desc()).all()
    return jsonify([c.to_dict() for c in changes])


@bp.route('/projects/<int:pid>/changes', methods=['POST'])
def create_change(pid):
    data = request.get_json()
    c = ChangeRequest(
        project_id=pid,
        title=data['title'],
        description=data.get('description', ''),
        change_level=data.get('change_level', 'C'),
        requester_id=data.get('requester_id'),
        affected_lines=data.get('affected_lines', ''),
        impact_scope=data.get('impact_scope', ''),
        impact_schedule=data.get('impact_schedule', ''),
        impact_cost=data.get('impact_cost', ''),
        status=data.get('status', 'pending'),
        submitted_date=date.fromisoformat(data['submitted_date']) if data.get('submitted_date') else None,
    )
    db.session.add(c)
    db.session.commit()
    log_action(get_username(), 'create', 'change', c.id, c.title,
               project_id=pid, summary=f'创建变更 {c.title}')
    return jsonify(c.to_dict()), 201


@bp.route('/changes/<int:id>', methods=['PUT'])
def update_change(id):
    c = ChangeRequest.query.get_or_404(id)
    data = request.get_json()
    str_fields = ['title', 'description', 'change_level', 'affected_lines',
                  'impact_scope', 'impact_schedule', 'impact_cost', 'status', 'review_notes']
    for f in str_fields:
        if f in data:
            setattr(c, f, data[f])
    int_fields = ['requester_id', 'reviewer_id']
    for f in int_fields:
        if f in data:
            setattr(c, f, data[f])
    date_fields = ['submitted_date', 'decision_date']
    for f in date_fields:
        if f in data and data[f]:
            setattr(c, f, date.fromisoformat(data[f]))
    db.session.commit()
    log_action(get_username(), 'update', 'change', c.id, c.title,
               project_id=c.project_id, summary=f'编辑变更 {c.title}')
    return jsonify(c.to_dict())


@bp.route('/changes/<int:id>', methods=['GET'])
def get_change(id):
    c = ChangeRequest.query.get_or_404(id)
    return jsonify(c.to_dict())
