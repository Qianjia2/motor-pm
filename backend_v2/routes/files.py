"""File upload and storage stats."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pathlib import Path
import aiofiles, uuid, os
from backend_v2.config import settings
from backend_v2.database import get_db
from backend_v2.auth import get_current_user

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    project_id: int = None,
    _current_user=Depends(get_current_user),
):
    """Generic file upload."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    ext = Path(file.filename).suffix.lstrip(".").lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: .{ext}")

    upload_dir = Path(settings.UPLOAD_DIR)
    if project_id:
        upload_dir = upload_dir / str(project_id) / "files"
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex[:12]}_{Path(file.filename).name}"
    dest = upload_dir / safe_name

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")

    with open(dest, "wb") as f:
        f.write(content)

    return {"file_path": str(dest.relative_to(Path(settings.UPLOAD_DIR).parent)), "file_size": len(content)}


@router.get("/storage-stats")
def storage_stats(_current_user=Depends(get_current_user)):
    """Return storage usage stats."""
    upload_dir = Path(settings.UPLOAD_DIR)
    total_size = 0
    file_count = 0
    by_type = {}

    if upload_dir.exists():
        for fp in upload_dir.rglob("*"):
            if fp.is_file():
                sz = fp.stat().st_size
                total_size += sz
                file_count += 1
                ext = fp.suffix.lstrip(".").lower() or "other"
                by_type[ext] = by_type.get(ext, 0) + sz

    # Disk free space
    try:
        stat = os.statvfs(upload_dir if upload_dir.exists() else Path("."))
        free = stat.f_bavail * stat.f_frsize
    except Exception:
        free = 0

    return {
        "total_bytes": total_size,
        "total_mb": round(total_size / (1024 * 1024), 2),
        "file_count": file_count,
        "by_type": {k: round(v / (1024 * 1024), 2) for k, v in sorted(by_type.items(), key=lambda x: -x[1])[:10]},
        "disk_free_mb": round(free / (1024 * 1024), 2),
        "max_file_mb": settings.MAX_UPLOAD_SIZE_MB,
        "upload_dir": str(upload_dir),
    }
