"""Milestone CRUD + all-project view."""
from datetime import datetime, date as date_type
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import Session, selectinload
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.audit import log_audit
from backend_v2.schemas import MilestoneCreate, MilestoneUpdate, PaginatedResponse
from backend_v2.models import Milestone, Project, ProjectMember


def _fix_dates(data: dict):
    """Convert empty strings to None for optional date fields; keep planned_date as today if empty."""
    for f in ("actual_date", "planned_end_date", "actual_end_date"):
        if f in data and (data[f] == "" or data[f] is None):
            data[f] = None
        elif f in data and isinstance(data[f], str):
            try: data[f] = date_type.fromisoformat(data[f])
            except: pass
    # planned_date is required by DB - default to today
    if "planned_date" in data and (data["planned_date"] == "" or data["planned_date"] is None):
        data["planned_date"] = date_type.today()
    elif "planned_date" in data and isinstance(data["planned_date"], str):
        try: data["planned_date"] = date_type.fromisoformat(data["planned_date"])
        except: data["planned_date"] = date_type.today()

router = APIRouter(tags=["milestones"])


def ms_to_dict(m):
    d = {c.name: getattr(m, c.name) for c in m.__table__.columns}
    for df in ("planned_date", "actual_date", "planned_end_date", "actual_end_date"):
        d[df] = d[df].isoformat() if d.get(df) else None
    d["line"] = {"id": m.line.id, "name": m.line.name, "short_name": m.line.short_name} if m.line else None
    d["phase"] = {"id": m.phase.id, "name": m.phase.name} if m.phase else None
    d["phase_name"] = m.phase.name if m.phase else None
    d["phase_id"] = m.phase_id
    return d


@router.get("/api/projects/{project_id}/milestones")
def list_milestones(
    project_id: int,
    phase_id: int = Query(None),
    line_id: int = Query(None),
    status: str = Query(None),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    # Access check
    if _current_user.role != "admin" and _current_user.member_id:
        assigned = db.execute(
            select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.member_id == _current_user.member_id)
        ).scalar_one_or_none()
        if not assigned:
            raise HTTPException(status_code=403, detail="无权访问此项目")
    q = select(Milestone).where(Milestone.project_id == project_id)
    if phase_id:
        q = q.where(Milestone.phase_id == phase_id)
    if line_id:
        q = q.where(Milestone.line_id == line_id)
    if status:
        q = q.where(Milestone.status == status)
    q = q.order_by(Milestone.phase_id, Milestone.line_id, Milestone.planned_date)
    result = db.execute(q)
    return [ms_to_dict(m) for m in result.scalars().all()]


@router.post("/api/projects/{project_id}/milestones", status_code=201)
def create_milestone(
    project_id: int, data: MilestoneCreate,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    p = (db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    vals = data.model_dump()
    _fix_dates(vals)
    if not vals.get("planned_date"):
        vals["planned_date"] = date_type.today()
    m = Milestone(project_id=project_id, **vals)
    db.add(m)
    db.commit()
    db.refresh(m)

    log_audit(db, current_user.username, "create", "milestone", m.id, m.name, project_id, f"创建里程碑: {m.name}")
    db.commit()
    return ms_to_dict(m)


@router.put("/api/milestones/{milestone_id}")
def update_milestone(
    milestone_id: int, data: MilestoneUpdate,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    result = db.execute(select(Milestone).where(Milestone.id == milestone_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="里程碑不存在")

    upd = data.model_dump(exclude_unset=True)
    _fix_dates(upd)
    db.execute(update(Milestone).where(Milestone.id == milestone_id).values(**upd))
    db.commit()
    db.expire_all()  # Clear session cache so relationships reload from DB
    log_audit(db, current_user.username, "update", "milestone", milestone_id, m.name, m.project_id, f"更新里程碑")
    db.commit()
    return ms_to_dict((db.execute(select(Milestone).where(Milestone.id == milestone_id))).scalar_one())


@router.delete("/api/milestones/{milestone_id}")
def delete_milestone(
    milestone_id: int,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    result = db.execute(select(Milestone).where(Milestone.id == milestone_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="里程碑不存在")
    pid = m.project_id
    db.execute(delete(Milestone).where(Milestone.id == milestone_id))
    log_audit(db, current_user.username, "delete", "milestone", milestone_id, m.name, pid, f"删除里程碑: {m.name}")
    db.commit()
    return {"message": "已删除"}


@router.get("/api/milestones/all")
def all_milestones(
    project_id: int = Query(None),
    year: int = Query(None),
    month: int = Query(None),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """All-project milestone view for calendar."""
    q = select(Milestone).options(selectinload(Milestone.project)).join(Project).where(Project.is_active == True)

    # Non-admin: filter by assigned projects
    if _current_user.role != "admin":
        if not _current_user.member_id:
            return []
        assigned = db.execute(
            select(ProjectMember.project_id).where(ProjectMember.member_id == _current_user.member_id)
        ).scalars().all()
        if not assigned:
            return []
        q = q.where(Milestone.project_id.in_(assigned))

    if project_id:
        q = q.where(Milestone.project_id == project_id)
    q = q.order_by(Milestone.phase_id, Milestone.line_id, Milestone.planned_date)
    result = db.execute(q)
    milestones = result.scalars().all()
    return [
        {**ms_to_dict(m), "project_name": m.project.name, "project_code": m.project.code}
        for m in milestones
    ]
