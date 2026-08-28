"""Audit logging middleware — records all CUD operations."""
from typing import Optional
from fastapi import Request
from sqlalchemy import insert
from datetime import datetime


def log_audit(
    db,
    username: str,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    entity_name: Optional[str] = None,
    project_id: Optional[int] = None,
    summary: Optional[str] = None,
    details: Optional[str] = None,
):
    """Write an audit log entry (async, fire-and-forget)."""
    from backend_v2.models import AuditLog  # noqa
    try:
        db.execute(
            insert(AuditLog).values(
                username=username,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                project_id=project_id,
                summary=summary or f"{action} {entity_type} #{entity_id}",
                details=details,
                created_at=datetime.utcnow(),
            )
        )
    except Exception:
        pass  # audit failure must not block the main operation
