"""培训学习:每个模块的学习视频与操作手册素材管理."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
import uuid
from datetime import datetime

from backend_v2.config import settings
from backend_v2.database import get_db
from backend_v2.models import TrainingMaterial
from backend_v2.auth import get_current_user, require_admin, verify_token

router = APIRouter(prefix="/api/training", tags=["training"])

ALLOWED_EXTS = {"mp4", "webm", "mov", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "md", "txt", "html"}

MEDIA_TYPES = {
    "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime",
    "pdf": "application/pdf", "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

VIDEO_EXTS = {"mp4", "webm", "mov"}


def _serialize(m: TrainingMaterial):
    return {
        "id": m.id,
        "category": m.category,
        "title": m.title,
        "description": m.description,
        "material_type": m.material_type,
        "file_path": m.file_path,
        "file_ext": m.file_ext,
        "file_size": m.file_size,
        "is_video": m.file_ext in VIDEO_EXTS if m.file_ext else False,
        "uploader": m.uploader,
        "created_at": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
    }


@router.get("/materials")
def list_materials(
    category: str = Query(None),
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(TrainingMaterial).filter(TrainingMaterial.is_active == True)
    if category:
        q = q.filter(TrainingMaterial.category == category)
    items = [m for m in q.order_by(TrainingMaterial.sort_order, TrainingMaterial.id.desc()).all()]
    return {"items": [_serialize(m) for m in items]}


@router.get("/categories")
def list_categories(_user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(TrainingMaterial.category, TrainingMaterial.material_type, TrainingMaterial.id).filter(
        TrainingMaterial.is_active == True).all()
    stats = {}
    for category, mtype, _ in rows:
        s = stats.setdefault(category, {"category": category, "count": 0, "videos": 0, "manuals": 0})
        s["count"] += 1
        if mtype == "video":
            s["videos"] += 1
        elif mtype == "manual":
            s["manuals"] += 1
    return {"items": sorted(stats.values(), key=lambda x: x["category"])}


@router.post("/materials")
async def upload_material(
    file: UploadFile = File(...),
    category: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    material_type: str = Form("video"),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")
    ext = Path(file.filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的素材格式: .{ext}(支持 {', '.join(sorted(ALLOWED_EXTS))})")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")

    upload_dir = Path(settings.UPLOAD_DIR) / "training"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:12]}_{Path(file.filename).name}"
    dest = upload_dir / safe_name
    with open(dest, "wb") as f:
        f.write(content)

    m = TrainingMaterial(
        category=category.strip(),
        title=title.strip(),
        description=description.strip(),
        material_type=material_type if material_type in ("video", "manual", "other") else "other",
        file_path=str(dest.relative_to(Path(settings.UPLOAD_DIR))),
        file_ext=ext,
        file_size=len(content),
        uploader=_admin.username if hasattr(_admin, "username") else str(_admin),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"message": "素材已上传", "material": _serialize(m)}


@router.delete("/materials/{material_id}")
def delete_material(
    material_id: int,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    m = db.query(TrainingMaterial).get(material_id)
    if not m:
        raise HTTPException(status_code=404, detail="素材不存在")
    if m.file_path:
        (Path(settings.UPLOAD_DIR) / m.file_path).unlink(missing_ok=True)
    db.delete(m)
    db.commit()
    return {"message": "素材已删除"}


def _resolve_user(authorization: str = None, token: str = None):
    """兼容 <video> 标签无法带 Authorization header 的情况:支持 ?token= 播放."""
    if authorization and authorization.lower().startswith("bearer "):
        return verify_token(authorization[7:])
    if token:
        return verify_token(token)
    raise HTTPException(status_code=401, detail="未认证")


@router.get("/file/{material_id}")
def get_material_file(
    material_id: int,
    request: Request,
    download: bool = False,
    token: str = Query(None),
    db: Session = Depends(get_db),
):
    _user = _resolve_user(request.headers.get("authorization"), token)
    m = db.query(TrainingMaterial).get(material_id)
    if not m or not m.file_path:
        raise HTTPException(status_code=404, detail="素材不存在")
    f = Path(settings.UPLOAD_DIR) / m.file_path
    if not f.exists():
        raise HTTPException(status_code=404, detail="文件缺失")
    media = MEDIA_TYPES.get(m.file_ext, "application/octet-stream")
    filename = f"{m.title}.{m.file_ext}" if not download else Path(f.name).name
    return FileResponse(str(f), media_type=media, filename=filename)
