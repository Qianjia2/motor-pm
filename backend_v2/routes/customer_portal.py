"""Customer collaboration portal — shareable project views."""
import hashlib, secrets
from datetime import datetime, date as date_type
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import CustomerAccess, Project, Client, Milestone, Deliverable, ProjectDocument

router = APIRouter(tags=["customer-portal"])


def _hash_pwd(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


@router.get("/api/admin/customer-access")
def list_access(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = db.execute(
        select(CustomerAccess).where(CustomerAccess.is_active == True).order_by(CustomerAccess.created_at.desc())
    )
    return [{"id": a.id, "client_name": a.client.name if a.client else None,
             "project_name": a.project.name if a.project else None,
             "access_code": a.access_code, "permissions": a.permissions,
             "last_accessed": a.last_accessed.isoformat() if a.last_accessed else None,
             "expires_at": a.expires_at.isoformat() if a.expires_at else None}
            for a in result.scalars().all()]


@router.post("/api/admin/customer-access", status_code=201)
def create_access(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Grant customer access to a project. Returns share URL."""
    code = "CLI" + secrets.token_urlsafe(8)[:12].replace("-", "x").replace("_", "y")
    a = CustomerAccess(
        client_id=data["client_id"], project_id=data["project_id"],
        access_code=code,
        password_hash=_hash_pwd(data["password"]) if data.get("password") else None,
        permissions=data.get("permissions", "view"),
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + __import__('datetime').timedelta(days=int(data.get("expire_days", 90))) if data.get("expire_days") else None,
    )
    db.add(a); db.commit(); db.refresh(a)
    return {"id": a.id, "access_code": a.access_code, "share_url": f"/portal/{a.access_code}"}


@router.delete("/api/admin/customer-access/{access_id}")
def revoke_access(access_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import update as up
    db.execute(up(CustomerAccess).where(CustomerAccess.id == access_id).values(is_active=False))
    db.commit()
    return {"message": "已撤销"}


# ═══════════════════════════════════════════
# Customer Portal (public — access_code auth)
# ═══════════════════════════════════════════

def _verify_access(access_code: str, db: Session) -> CustomerAccess:
    result = db.execute(
        select(CustomerAccess).where(CustomerAccess.access_code == access_code, CustomerAccess.is_active == True)
    )
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="无效的访问链接")
    if a.expires_at and a.expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="访问链接已过期")
    return a


@router.post("/api/portal/{access_code}/login")
def portal_login(access_code: str, data: dict, db: Session = Depends(get_db)):
    a = _verify_access(access_code, db)
    if a.password_hash:
        if not data.get("password"):
            raise HTTPException(status_code=401, detail="需要密码")
        if _hash_pwd(data["password"]) != a.password_hash:
            raise HTTPException(status_code=401, detail="密码错误")
    from sqlalchemy import update as up
    db.execute(up(CustomerAccess).where(CustomerAccess.id == a.id).values(last_accessed=datetime.utcnow()))
    db.commit()
    return {"token": a.access_code, "project_id": a.project_id, "permissions": a.permissions}


@router.get("/api/portal/{access_code}/project")
def portal_project(access_code: str, db: Session = Depends(get_db)):
    a = _verify_access(access_code, db)
    result = db.execute(
        select(Project).where(Project.id == a.project_id, Project.is_active == True)
        .options(selectinload(Project.current_phase), selectinload(Project.client))
    )
    p = result.scalars().one_or_none()
    if not p: raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "name": p.name, "code": p.code, "description": p.description,
        "phase": p.current_phase.name if p.current_phase else None,
        "status": p.overall_status, "completion_pct": p.completion_pct,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "planned_end_date": p.planned_end_date.isoformat() if p.planned_end_date else None,
        "client": p.client.name if p.client else None,
    }


@router.get("/api/portal/{access_code}/milestones")
def portal_milestones(access_code: str, db: Session = Depends(get_db)):
    a = _verify_access(access_code, db)
    result = db.execute(
        select(Milestone).where(Milestone.project_id == a.project_id).order_by(Milestone.planned_date)
    )
    return [{"id": m.id, "name": m.name, "planned_date": m.planned_date.isoformat() if m.planned_date else None,
             "status": m.status, "is_key": m.is_key} for m in result.scalars().all()]


@router.get("/api/portal/{access_code}/deliverables")
def portal_deliverables(access_code: str, db: Session = Depends(get_db)):
    a = _verify_access(access_code, db)
    result = db.execute(
        select(Deliverable).where(Deliverable.project_id == a.project_id).order_by(Deliverable.created_at.desc())
    )
    return [{"id": d.id, "name": d.name, "status": d.status,
             "phase": d.phase.name if d.phase else None,
             "line": d.line.name if d.line else None}
            for d in result.scalars().all()]


@router.get("/api/portal/{access_code}/documents")
def portal_documents(access_code: str, db: Session = Depends(get_db)):
    a = _verify_access(access_code, db)
    result = db.execute(
        select(ProjectDocument).where(ProjectDocument.project_id == a.project_id, ProjectDocument.status == "active")
        .order_by(ProjectDocument.upload_date.desc())
    )
    return [{"id": d.id, "name": d.name, "doc_type": d.doc_type, "file_size": d.file_size,
             "upload_date": d.upload_date.isoformat() if d.upload_date else None}
            for d in result.scalars().all()]
