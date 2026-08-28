from datetime import date
from flask import Blueprint, request, jsonify
from backend import db
from backend.models import Milestone
from backend.audit import log_action, get_username

bp = Blueprint('milestones', __name__)


@bp.route('/projects/<int:pid>/milestones', methods=['GET'])
def list_milestones(pid):
    milestones = Milestone.query.filter_by(project_id=pid).order_by(Milestone.sort_order).all()
    return jsonify([m.to_dict() for m in milestones])


@bp.route('/projects/<int:pid>/milestones', methods=['POST'])
def create_milestone(pid):
    data = request.get_json()
    m = Milestone(
        project_id=pid,
        name=data['name'],
        description=data.get('description', ''),
        planned_date=date.fromisoformat(data['planned_date']) if data.get('planned_date') else None,
        actual_date=date.fromisoformat(data['actual_date']) if data.get('actual_date') else None,
        line_id=data.get('line_id'),
        phase_id=data.get('phase_id'),
        status=data.get('status', 'pending'),
        is_key=data.get('is_key', False),
        sort_order=data.get('sort_order', 0),
    )
    db.session.add(m)
    db.session.commit()
    log_action(get_username(), 'create', 'milestone', m.id, m.name,
               project_id=pid, summary=f'创建里程碑 {m.name}')
    return jsonify(m.to_dict()), 201


@bp.route('/milestones/<int:id>', methods=['PUT'])
def update_milestone(id):
    m = Milestone.query.get_or_404(id)
    data = request.get_json()
    str_fields = ['name', 'description', 'status']
    for f in str_fields:
        if f in data:
            setattr(m, f, data[f])
    date_fields = ['planned_date', 'actual_date']
    for f in date_fields:
        if f in data and data[f]:
            setattr(m, f, date.fromisoformat(data[f]))
    int_fields = ['line_id', 'phase_id', 'sort_order']
    for f in int_fields:
        if f in data:
            setattr(m, f, data[f])
    if 'is_key' in data:
        m.is_key = data['is_key']
    db.session.commit()
    log_action(get_username(), 'update', 'milestone', m.id, m.name,
               project_id=m.project_id, summary=f'编辑里程碑 {m.name}')
    return jsonify(m.to_dict())


@bp.route('/milestones/<int:id>', methods=['DELETE'])
def delete_milestone(id):
    m = Milestone.query.get_or_404(id)
    pid = m.project_id
    db.session.delete(m)
    db.session.commit()
    log_action(get_username(), 'delete', 'milestone', id, m.name,
               project_id=pid, summary=f'删除里程碑 {m.name}')
    return jsonify({'message': 'deleted'})
