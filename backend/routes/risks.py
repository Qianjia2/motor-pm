from datetime import date
from flask import Blueprint, request, jsonify
from backend import db
from backend.models import RiskIssue
from backend.utils import compute_risk_level
from backend.audit import log_action, get_username

bp = Blueprint('risks', __name__)


@bp.route('/projects/<int:pid>/risks', methods=['GET'])
def list_risks(pid):
    risk_type = request.args.get('type')
    query = RiskIssue.query.filter_by(project_id=pid)
    if risk_type:
        query = query.filter_by(type=risk_type)
    risks = query.order_by(RiskIssue.created_at.desc()).all()
    return jsonify([r.to_dict() for r in risks])


@bp.route('/projects/<int:pid>/risks', methods=['POST'])
def create_risk(pid):
    data = request.get_json()
    probability = data.get('probability')
    impact = data.get('impact')
    risk = RiskIssue(
        project_id=pid,
        type=data.get('type', 'risk'),
        title=data['title'],
        description=data.get('description', ''),
        probability=probability,
        impact=impact,
        risk_level=compute_risk_level(probability, impact) if probability and impact else None,
        severity=data.get('severity'),
        status=data.get('status', 'open'),
        mitigation_plan=data.get('mitigation_plan', ''),
        owner_id=data.get('owner_id'),
        line_id=data.get('line_id'),
        phase_id=data.get('phase_id'),
        identified_date=date.fromisoformat(data['identified_date']) if data.get('identified_date') else None,
        target_resolve_date=date.fromisoformat(data['target_resolve_date']) if data.get('target_resolve_date') else None,
    )
    db.session.add(risk)
    db.session.commit()
    log_action(get_username(), 'create', 'risk', risk.id, risk.title,
               project_id=pid, summary=f'创建{risk.type}项 {risk.title}')
    return jsonify(risk.to_dict()), 201


@bp.route('/risks/<int:id>', methods=['PUT'])
def update_risk(id):
    r = RiskIssue.query.get_or_404(id)
    data = request.get_json()
    str_fields = ['title', 'description', 'probability', 'impact', 'severity', 'status',
                  'mitigation_plan', 'type', 'resolution', 'attachment_path']
    for f in str_fields:
        if f in data:
            setattr(r, f, data[f])

    if data.get('probability') and data.get('impact'):
        r.risk_level = compute_risk_level(r.probability, r.impact)

    int_fields = ['owner_id', 'line_id', 'phase_id']
    for f in int_fields:
        if f in data:
            setattr(r, f, data[f])

    date_fields = ['identified_date', 'target_resolve_date', 'resolved_date']
    for f in date_fields:
        if f in data and data[f]:
            setattr(r, f, date.fromisoformat(data[f]))

    db.session.commit()
    log_action(get_username(), 'update', 'risk', r.id, r.title,
               project_id=r.project_id, summary=f'编辑{getattr(r, "type", "risk")}项 {r.title}')
    return jsonify(r.to_dict())


@bp.route('/risks/<int:id>/close', methods=['POST'])
def close_risk(id):
    """Close a risk/issue with verification result and optional attachment."""
    r = RiskIssue.query.get_or_404(id)

    r.resolution = request.form.get('resolution', '')
    r.status = 'closed'
    r.resolved_date = date.today()

    # Handle file upload
    if 'file' in request.files:
        file = request.files['file']
        if file.filename:
            import uuid, os
            upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            safe_name = f"{uuid.uuid4().hex}_{file.filename}"
            filepath = os.path.join(upload_dir, safe_name)
            file.save(filepath)
            r.attachment_path = f'/api/files/download/{safe_name}'

    db.session.commit()
    log_action(get_username(), 'close', 'risk', r.id, r.title,
               project_id=r.project_id, summary=f'关闭{getattr(r, "type", "risk")}项 {r.title}（含验证）')
    return jsonify(r.to_dict())


@bp.route('/risks/<int:id>', methods=['DELETE'])
def delete_risk(id):
    r = RiskIssue.query.get_or_404(id)
    pid = r.project_id
    db.session.delete(r)
    db.session.commit()
    log_action(get_username(), 'delete', 'risk', id, r.title,
               project_id=pid, summary=f'删除{getattr(r, "type", "risk")}项 {r.title}')
    return jsonify({'message': 'deleted'})
