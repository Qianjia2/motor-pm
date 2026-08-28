"""Audit log query API."""
from flask import Blueprint, request, jsonify

audit_bp = Blueprint('audit', __name__)


@audit_bp.route('/api/audit-logs', methods=['GET'])
def list_logs():
    from backend.models import AuditLog
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    entity_type = request.args.get('entity_type')
    project_id = request.args.get('project_id', type=int)
    username = request.args.get('username')

    q = AuditLog.query
    if entity_type:
        q = q.filter_by(entity_type=entity_type)
    if project_id:
        q = q.filter_by(project_id=project_id)
    if username:
        q = q.filter_by(username=username)

    q = q.order_by(AuditLog.created_at.desc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'logs': [e.to_dict() for e in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    })
