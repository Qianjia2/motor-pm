"""Space-level permission helpers for the Knowledge Base."""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import KbSpace, KbSpaceMember

ROLE_HIERARCHY = {"creator": 4, "admin": 3, "editor": 2, "viewer": 1}


def get_user_role(space_id: str, user, db: Session) -> str:
    """Get user's effective role in a space. Returns None if no access."""
    space = db.get(KbSpace, space_id)
    if not space:
        return None
    if str(space.creator_id) == str(getattr(user, 'id', '')):
        return "creator"
    if space.is_public:
        return "viewer"
    member = db.execute(
        select(KbSpaceMember).where(
            KbSpaceMember.space_id == space_id,
            KbSpaceMember.user_id == user.id
        )
    ).scalar_one_or_none()
    return member.role if member else None


def require_space_role(space_id: str, min_role: str = "viewer"):
    """FastAPI dependency: require at least `min_role` in a space."""
    def checker(db: Session = Depends(get_db), user=Depends(get_current_user)):
        role = get_user_role(space_id, user, db)
        if role is None or ROLE_HIERARCHY.get(role, 0) < ROLE_HIERARCHY.get(min_role, 0):
            raise HTTPException(403, f"需要 {min_role} 及以上权限访问此空间")
        return (user, role)
    return checker


def get_accessible_spaces(user, db: Session):
    """Get all spaces the user can access (for listing)."""
    from backend_v2.models import KbSpace
    spaces = db.execute(select(KbSpace)).scalars().all()
    result = []
    for s in spaces:
        role = get_user_role(s.id, user, db)
        if role:
            result.append({**{c.name: getattr(s, c.name) for c in s.__table__.columns}, "my_role": role})
    # Ensure "default" space always exists
    if not any(s.get("id") == "default" for s in result):
        result.insert(0, {"id": "default", "name": "通用知识库", "my_role": "editor" if user else "viewer",
                          "is_public": True, "creator_id": None, "doc_count": 0, "icon": "📁"})
    return result


def sync_spaces_from_json():
    """One-time migration: import spaces from kb_spaces.json into DB tables."""
    import json, os
    from backend_v2.database import SessionLocal
    from backend_v2.config import settings
    from pathlib import Path

    json_path = Path(settings.UPLOAD_DIR).parent / "data" / "kb_spaces.json"
    if not json_path.exists():
        return []

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except:
        return []

    db = SessionLocal()
    migrated = []
    for space_data in data if isinstance(data, list) else [data]:
        sid = space_data.get("id", "default")
        existing = db.get(KbSpace, sid)
        if not existing:
            s = KbSpace(
                id=sid, name=space_data.get("name", sid),
                description=space_data.get("description", ""),
                icon=space_data.get("icon", "📁"),
                creator_id=space_data.get("creator"),
                is_public=space_data.get("is_public", False),
            )
            db.add(s)
            db.flush()
        # Migrate members
        for role_name in ("admins", "collaborators", "viewers"):
            role_map = {"admins": "admin", "collaborators": "editor", "viewers": "viewer"}
            for uid in space_data.get(role_name, []) or []:
                existing_member = db.execute(
                    select(KbSpaceMember).where(
                        KbSpaceMember.space_id == sid,
                        KbSpaceMember.user_id == uid
                    )
                ).scalar_one_or_none()
                if not existing_member:
                    db.add(KbSpaceMember(space_id=sid, user_id=uid, role=role_map[role_name]))
        migrated.append(sid)
    db.commit()
    db.close()
    return migrated
