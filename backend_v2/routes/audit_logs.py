"""Audit log query endpoint."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user, require_admin
from backend_v2.schemas import PaginatedResponse
from backend_v2.models import AuditLog

router = APIRouter(prefix="/api/audit-logs", tags=["audit-logs"])


@router.get("")
def list_audit_logs(
    username: str = Query(None),
    action: str = Query(None),
    entity_type: str = Query(None),
    project_id: int = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    q = select(AuditLog)
    if username:
        q = q.where(AuditLog.username == username)
    if action:
        q = q.where(AuditLog.action == action)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if project_id:
        q = q.where(AuditLog.project_id == project_id)

    count_q = select(func.count()).select_from(q.subquery())
    total = (db.execute(count_q)).scalar()

    q = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = db.execute(q)
    logs = result.scalars().all()

    return PaginatedResponse(
        data=[{
            "id": l.id, "username": l.username, "action": l.action,
            "entity_type": l.entity_type, "entity_id": l.entity_id,
            "entity_name": l.entity_name, "project_id": l.project_id,
            "project_name": l.project.name if l.project else None,
            "summary": l.summary, "details": l.details,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in logs],
        total=total, page=page, page_size=page_size,
    )
