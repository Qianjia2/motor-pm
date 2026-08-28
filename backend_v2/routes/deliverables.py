"""Deliverable CRUD + phase-gate management."""
import uuid
from datetime import date, datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session, selectinload
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.audit import log_audit
from backend_v2.config import settings
from backend_v2.schemas import DeliverableCreate, DeliverableUpdate, PhaseGateUpdate, ActionItemCreate, ActionItemUpdate
from backend_v2.models import Deliverable, DeliverableAttachment, ProjectPhaseGate, ReviewActionItem, Project

router = APIRouter(tags=["deliverables"])

ALLOWED_DELIVERABLE_EXTS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "pdf", "doc", "docx", "xlsx", "xls", "pptx", "ppt", "txt", "csv", "zip", "dwg", "step", "stp", "stl", "igs", "iges", "dxf", "mp4", "avi", "mov", "mkv"}
MAX_DELIVERABLE_FILE_MB = 200  # 设计资料(三维模型/仿真视频)体积大,上限放宽到 200MB


def att_to_dict(a):
    return {
        "id": a.id, "deliverable_id": a.deliverable_id,
        "file_path": a.file_path, "file_name": a.file_name,
        "file_size": a.file_size, "uploaded_by": a.uploaded_by,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def deliv_to_dict(d):
    r = {c.name: getattr(d, c.name) for c in d.__table__.columns}
    if r.get("submitted_date"):
        r["submitted_date"] = r["submitted_date"].isoformat()
    r["phase"] = {"id": d.phase.id, "name": d.phase.name} if d.phase else None
    r["line"] = {"id": d.line.id, "name": d.line.name} if d.line else None
    r["owner"] = {"id": d.owner.id, "name": d.owner.name} if d.owner else None
    r["attachments"] = [att_to_dict(a) for a in (d.attachments or [])]
    return r


# ── Deliverables ──

@router.get("/api/projects/{project_id}/deliverables")
def list_deliverables(
    project_id: int,
    phase_id: int = Query(None),
    line_id: int = Query(None),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    q = select(Deliverable).where(Deliverable.project_id == project_id)
    if phase_id:
        q = q.where(Deliverable.phase_id == phase_id)
    if line_id:
        q = q.where(Deliverable.line_id == line_id)
    q = q.order_by(Deliverable.phase_id, Deliverable.line_id)
    result = db.execute(q.options(selectinload(Deliverable.attachments)))
    return [deliv_to_dict(d) for d in result.scalars().all()]


@router.post("/api/projects/{project_id}/deliverables", status_code=201)
def create_deliverable(
    project_id: int, data: DeliverableCreate,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    d = Deliverable(project_id=project_id, **data.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    log_audit(db, current_user.username, "create", "deliverable", d.id, d.name, project_id, f"创建交付物: {d.name}")
    db.commit()
    return deliv_to_dict(d)


@router.put("/api/deliverables/{deliverable_id}")
def update_deliverable(
    deliverable_id: int, data: DeliverableUpdate,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    result = db.execute(select(Deliverable).where(Deliverable.id == deliverable_id))
    d = result.scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="不存在")
    upd = data.model_dump(exclude_unset=True)
    db.execute(update(Deliverable).where(Deliverable.id == deliverable_id).values(**upd))
    log_audit(db, current_user.username, "update", "deliverable", deliverable_id, d.name, d.project_id, "更新交付物")
    db.commit()
    return deliv_to_dict((db.execute(select(Deliverable).where(Deliverable.id == deliverable_id))).scalar_one())


@router.post("/api/deliverables/{deliverable_id}/upload-file")
async def upload_deliverable_file(
    deliverable_id: int, file: UploadFile = File(...),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    """Upload a file for a deliverable; saved under UPLOAD_DIR/{project_id}/deliverables."""
    d = db.get(Deliverable, deliverable_id)
    if not d:
        raise HTTPException(status_code=404, detail="交付物不存在")
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else ""
    if ext not in ALLOWED_DELIVERABLE_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: .{ext}")

    upload_dir = Path(settings.UPLOAD_DIR) / str(d.project_id) / "deliverables"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    dest = upload_dir / safe_name

    content = await file.read()
    if len(content) > MAX_DELIVERABLE_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件不超过 {MAX_DELIVERABLE_FILE_MB}MB")
    with open(dest, "wb") as f:
        f.write(content)

    rel_path = str(dest.relative_to(Path(settings.UPLOAD_DIR)))
    db.execute(update(Deliverable).where(Deliverable.id == deliverable_id).values(file_path=rel_path))
    db.commit()
    return {"message": "文件已上传", "file_path": rel_path, "file_name": file.filename}


# ── 交付物多附件(设计资料:三维模型/仿真过程等) ──

@router.get("/api/deliverables/{deliverable_id}/attachments")
def list_deliverable_attachments(
    deliverable_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    result = db.execute(select(DeliverableAttachment).where(DeliverableAttachment.deliverable_id == deliverable_id).order_by(DeliverableAttachment.id))
    return [att_to_dict(a) for a in result.scalars().all()]


@router.post("/api/deliverables/{deliverable_id}/attachments", status_code=201)
async def upload_deliverable_attachment(
    deliverable_id: int, file: UploadFile = File(...),
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    """上传交付物附件(可多个),存 UPLOAD_DIR/{project_id}/deliverables."""
    d = db.get(Deliverable, deliverable_id)
    if not d:
        raise HTTPException(status_code=404, detail="交付物不存在")
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else ""
    if ext not in ALLOWED_DELIVERABLE_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: .{ext}")

    upload_dir = Path(settings.UPLOAD_DIR) / str(d.project_id) / "deliverables"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    dest = upload_dir / safe_name

    content = await file.read()
    if len(content) > MAX_DELIVERABLE_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件不超过 {MAX_DELIVERABLE_FILE_MB}MB")
    with open(dest, "wb") as f:
        f.write(content)

    rel_path = str(dest.relative_to(Path(settings.UPLOAD_DIR)))
    att = DeliverableAttachment(
        deliverable_id=deliverable_id, file_path=rel_path,
        file_name=file.filename, file_size=len(content),
        uploaded_by=current_user.username,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    log_audit(db, current_user.username, "create", "deliverable_attachment", att.id, att.file_name, d.project_id, f"上传交付物附件: {d.name} / {att.file_name}")
    db.commit()
    return att_to_dict(att)


@router.delete("/api/deliverables/{deliverable_id}/attachments/{att_id}")
def delete_deliverable_attachment(
    deliverable_id: int, att_id: int,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    att = db.get(DeliverableAttachment, att_id)
    if not att or att.deliverable_id != deliverable_id:
        raise HTTPException(status_code=404, detail="附件不存在")
    target = (Path(settings.UPLOAD_DIR) / att.file_path).resolve()
    base = Path(settings.UPLOAD_DIR).resolve()
    if str(target).startswith(str(base)):
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
    d = db.get(Deliverable, deliverable_id)
    db.execute(delete(DeliverableAttachment).where(DeliverableAttachment.id == att_id))
    log_audit(db, current_user.username, "delete", "deliverable_attachment", att_id, att.file_name, d.project_id if d else None, f"删除交付物附件: {att.file_name}")
    db.commit()
    return {"message": "附件已删除"}


@router.delete("/api/deliverables/{deliverable_id}/file")
def delete_deliverable_file(
    deliverable_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    """Delete the uploaded file (disk + DB reference)."""
    d = db.get(Deliverable, deliverable_id)
    if not d:
        raise HTTPException(status_code=404, detail="交付物不存在")
    if not d.file_path:
        raise HTTPException(status_code=400, detail="该交付物没有文件")
    target = (Path(settings.UPLOAD_DIR) / d.file_path).resolve()
    base = Path(settings.UPLOAD_DIR).resolve()
    if str(target).startswith(str(base)):
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
    db.execute(update(Deliverable).where(Deliverable.id == deliverable_id).values(file_path=None))
    log_audit(db, current_user.username, "delete", "deliverable_file", deliverable_id, d.name, d.project_id, f"删除交付物文件: {d.name}")
    db.commit()
    return {"message": "文件已删除"}


@router.delete("/api/deliverables/{deliverable_id}")
def delete_deliverable(
    deliverable_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    result = db.execute(select(Deliverable).where(Deliverable.id == deliverable_id))
    d = result.scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="不存在")
    base = Path(settings.UPLOAD_DIR).resolve()
    for f in [d.file_path] + [a.file_path for a in (d.attachments or [])]:  # 连带删除磁盘文件,避免残留孤儿文件
        if f:
            target = (Path(settings.UPLOAD_DIR) / f).resolve()
            if str(target).startswith(str(base)):
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
    db.execute(delete(Deliverable).where(Deliverable.id == deliverable_id))
    log_audit(db, current_user.username, "delete", "deliverable", deliverable_id, d.name, d.project_id, f"删除交付物: {d.name}")
    db.commit()
    return {"message": "已删除"}


# ── Phase Gates ──

def pg_to_dict(pg):
    d = {c.name: getattr(pg, c.name) for c in pg.__table__.columns}
    for df in ("planned_start_date", "planned_end_date", "actual_start_date", "actual_end_date", "gate_review_date"):
        d[df] = d[df].isoformat() if d.get(df) else None
    d["phase"] = {"id": pg.phase.id, "name": pg.phase.name, "code": pg.phase.code} if pg.phase else None
    d["gate"] = {"id": pg.gate.id, "name": pg.gate.name, "code": pg.gate.code} if pg.gate else None
    return d


@router.get("/api/projects/{project_id}/phase-gates")
def list_phase_gates(project_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    q = select(ProjectPhaseGate).options(selectinload(ProjectPhaseGate.phase), selectinload(ProjectPhaseGate.gate)).where(ProjectPhaseGate.project_id == project_id).order_by(ProjectPhaseGate.phase_id)
    result = db.execute(q)
    return [pg_to_dict(pg) for pg in result.scalars().all()]


@router.put("/api/phase-gates/{pg_id}")
def update_phase_gate(
    pg_id: int, data: dict,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    result = db.execute(select(ProjectPhaseGate).where(ProjectPhaseGate.id == pg_id))
    pg = result.scalar_one_or_none()
    if not pg:
        raise HTTPException(status_code=404, detail="不存在")
    # Filter to allowed fields only, strip extras like 'gate' object
    allowed = {"status", "gate_status", "gate_review_date", "gate_review_notes",
               "planned_start_date", "planned_end_date", "actual_start_date", "actual_end_date"}
    upd = {k: v for k, v in data.items() if k in allowed and v != ""}
    # 评审状态由两级签核流程驱动,禁止手动置为已通过/未通过
    gs_new = upd.get("gate_status")
    if gs_new in ("passed", "failed"):
        raise HTTPException(status_code=400, detail="评审状态由签核流程自动更新,不可手动修改")
    # 标记阶段完成需门径评审通过(或豁免),防止绕过审批把关
    if upd.get("status") == "completed":
        gate_ok = pg.gate_status in ("passed", "waived") or gs_new == "waived"
        if not gate_ok:
            raise HTTPException(status_code=400, detail="该阶段需门径评审通过后才能标记完成,请先在阶段门评审中发起并完成两级签核")
    # Convert empty strings to None for nullable fields
    for f in ("gate_review_date", "planned_start_date", "planned_end_date", "actual_start_date", "actual_end_date"):
        if f in upd and upd[f] == "":
            upd[f] = None
        elif f in upd and upd[f] and isinstance(upd[f], str):
            from datetime import date
            try: upd[f] = date.fromisoformat(upd[f])
            except: upd[f] = None
    db.execute(update(ProjectPhaseGate).where(ProjectPhaseGate.id == pg_id).values(**upd))
    log_audit(db, current_user.username, "update", "phase_gate", pg_id, f"阶段{pg.phase.name if pg.phase else pg.phase_id}", pg.project_id, "更新阶段门径")
    db.commit()
    return pg_to_dict((db.execute(select(ProjectPhaseGate).where(ProjectPhaseGate.id == pg_id))).scalar_one())


# ── Review Action Items ──

@router.get("/api/phase-gates/{pg_id}/action-items")
def list_action_items(pg_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    result = db.execute(
        select(ReviewActionItem).where(ReviewActionItem.project_phase_gate_id == pg_id).order_by(ReviewActionItem.sort_order)
    )
    items = result.scalars().all()
    return [{
        "id": ai.id, "project_phase_gate_id": ai.project_phase_gate_id,
        "title": ai.title, "description": ai.description,
        "assignee_id": ai.assignee_id,
        "assignee_name": ai.assignee.name if ai.assignee else None,
        "due_date": ai.due_date.isoformat() if ai.due_date else None,
        "status": ai.status, "resolution": ai.resolution,
        "sort_order": ai.sort_order,
        "created_at": ai.created_at.isoformat() if ai.created_at else None,
        "closed_at": ai.closed_at.isoformat() if ai.closed_at else None,
    } for ai in items]


@router.post("/api/phase-gates/{pg_id}/action-items", status_code=201)
def create_action_item(
    pg_id: int, data: ActionItemCreate,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    ai = ReviewActionItem(project_phase_gate_id=pg_id, created_at=datetime.utcnow(), **data.model_dump())
    db.add(ai)
    db.commit()
    db.refresh(ai)
    log_audit(db, current_user.username, "create", "action_item", ai.id, ai.title, None, f"创建评审待办: {ai.title}")
    db.commit()
    return {"id": ai.id, "title": ai.title, "status": ai.status}


@router.put("/api/action-items/{ai_id}")
def update_action_item(
    ai_id: int, data: ActionItemUpdate,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    result = db.execute(select(ReviewActionItem).where(ReviewActionItem.id == ai_id))
    ai = result.scalar_one_or_none()
    if not ai:
        raise HTTPException(status_code=404, detail="不存在")
    upd = data.model_dump(exclude_unset=True)
    if upd.get("status") == "closed" and not ai.closed_at:
        upd["closed_at"] = datetime.utcnow()
    db.execute(update(ReviewActionItem).where(ReviewActionItem.id == ai_id).values(**upd))
    db.commit()
    return {"message": "已更新"}


@router.delete("/api/action-items/{ai_id}")
def delete_action_item(
    ai_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    result = db.execute(select(ReviewActionItem).where(ReviewActionItem.id == ai_id))
    ai = result.scalar_one_or_none()
    if not ai:
        raise HTTPException(status_code=404, detail="不存在")
    db.execute(delete(ReviewActionItem).where(ReviewActionItem.id == ai_id))
    log_audit(db, current_user.username, "delete", "action_item", ai_id, ai.title, None, f"删除评审待办: {ai.title}")
    db.commit()
    return {"message": "已删除"}
