"""Audit logging utility."""
import json
from flask import g
from backend.models import AuditLog, db


def get_username():
    """Safely get the current username from auth context, or 'system' if unauthenticated."""
    try:
        return g.current_user.username
    except Exception:
        return 'system'


def log_action(username, action, entity_type, entity_id=None,
               entity_name=None, project_id=None, summary=None, details=None):
    """Record an audit log entry. Safe to call from any route."""
    try:
        entry = AuditLog(
            username=username or 'unknown',
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            project_id=project_id,
            summary=summary,
            details=json.dumps(details, ensure_ascii=False) if isinstance(details, dict) else details,
        )
        db.session.add(entry)
    except Exception:
        pass  # never fail a business operation because of audit logging
