from datetime import date
from flask import Blueprint, request, jsonify
from backend import db
from backend.models import Deliverable
from backend.audit import log_action, get_username

bp = Blueprint('deliverables', __name__)


@bp.route('/projects/<int:pid>/deliverables', methods=['GET'])
def list_deliverables(pid):
    phase_id = request.args.get('phase_id', type=int)
    line_id = request.args.get('line_id', type=int)
    query = Deliverable.query.filter_by(project_id=pid)
    if phase_id:
        query = query.filter_by(phase_id=phase_id)
    if line_id:
        query = query.filter_by(line_id=line_id)
    results = query.order_by(Deliverable.phase_id, Deliverable.line_id).all()
    return jsonify([d.to_dict() for d in results])


@bp.route('/projects/<int:pid>/deliverables', methods=['POST'])
def create_deliverable(pid):
    data = request.get_json()
    d = Deliverable(
        project_id=pid,
        phase_id=data['phase_id'],
        line_id=data.get('line_id'),
        name=data['name'],
        description=data.get('description', ''),
        file_path=data.get('file_path', ''),
        status=data.get('status', 'not_submitted'),
        owner_id=data.get('owner_id'),
    )
    db.session.add(d)
    db.session.commit()
    log_action(get_username(), 'create', 'deliverable', d.id, d.name,
               project_id=pid, summary=f'创建交付物 {d.name}')
    return jsonify(d.to_dict()), 201


@bp.route('/deliverables/<int:id>', methods=['PUT'])
def update_deliverable(id):
    d = Deliverable.query.get_or_404(id)
    data = request.get_json()
    str_fields = ['name', 'description', 'file_path', 'status']
    for f in str_fields:
        if f in data:
            setattr(d, f, data[f])
    if 'owner_id' in data:
        d.owner_id = data['owner_id']
    if data.get('submitted_date'):
        d.submitted_date = date.fromisoformat(data['submitted_date'])
    db.session.commit()
    log_action(get_username(), 'update', 'deliverable', d.id, d.name,
               project_id=d.project_id, summary=f'编辑交付物 {d.name}')
    return jsonify(d.to_dict())


@bp.route('/deliverables/<int:id>', methods=['DELETE'])
def delete_deliverable(id):
    d = Deliverable.query.get_or_404(id)
    pid = d.project_id
    db.session.delete(d)
    db.session.commit()
    log_action(get_username(), 'delete', 'deliverable', id, d.name,
               project_id=pid, summary=f'删除交付物 {d.name}')
    return jsonify({'message': 'deleted'})
