"""SQLite Backup — manual, scheduled, restore."""
import json, sqlite3 as _sqlite3, shutil, threading, time as _time
from datetime import datetime, timedelta
from pathlib import Path as _Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.config import settings

router = APIRouter(tags=["knowledge-backup"])

BACKUP_DIR = _Path(settings.UPLOAD_DIR).parent / "backups"
BACKUP_CONFIG_FILE = _Path(settings.UPLOAD_DIR).parent / "data" / "kb_backup_config.json"
_backup_timer = None


def _get_backup_config():
    try:
        if BACKUP_CONFIG_FILE.exists():
            return json.loads(BACKUP_CONFIG_FILE.read_text(encoding="utf-8"))
    except: pass
    return {"enabled": True, "interval_hours": 24, "retention_count": 7, "last_backup": None, "next_backup": None}


def _save_backup_config(cfg):
    BACKUP_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def do_backup():
    """Perform a single SQLite backup. Returns dict with result."""
    cfg = _get_backup_config()
    if not cfg.get("enabled", True):
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    db_path = str(_Path(settings.DATABASE_URL.replace("sqlite:///", "")))
    if not _Path(db_path).is_absolute():
        db_path = str(_Path(__file__).parent.parent.parent.parent / db_path)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"motor_pm_v2_{timestamp}.db"
    try:
        src = _sqlite3.connect(db_path)
        dst = _sqlite3.connect(str(backup_path))
        src.backup(dst)
        dst.close(); src.close()
        verify = _sqlite3.connect(str(backup_path))
        result = verify.execute("PRAGMA integrity_check").fetchone()
        verify.close()
        if result[0] != "ok":
            backup_path.unlink(missing_ok=True)
            return {"error": f"Integrity check failed: {result[0]}"}
        backups = sorted(BACKUP_DIR.glob("motor_pm_v2_*.db"), key=lambda p: p.stat().st_mtime)
        for old in backups[:-cfg.get("retention_count", 7)]:
            old.unlink(missing_ok=True)
        cfg["last_backup"] = timestamp
        cfg["next_backup"] = (datetime.utcnow() + timedelta(hours=cfg.get("interval_hours", 24))).isoformat()
        _save_backup_config(cfg)
        return {"file": backup_path.name, "size_mb": round(backup_path.stat().st_size/(1024*1024), 2), "timestamp": timestamp, "ok": True}
    except Exception as e:
        return {"error": str(e)}


def start_backup_scheduler():
    """Start periodic backup thread."""
    global _backup_timer
    cfg = _get_backup_config()
    if not cfg.get("enabled", True): return
    interval = cfg.get("interval_hours", 24) * 3600
    do_backup()
    _backup_timer = threading.Timer(interval, start_backup_scheduler)
    _backup_timer.daemon = True
    _backup_timer.start()


@router.get("/api/knowledge/backup/status")
def get_backup_status(_user=Depends(get_current_user)):
    cfg = _get_backup_config()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = [{"file": p.name, "size_mb": round(p.stat().st_size/(1024*1024),2), "created_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat()}
               for p in sorted(BACKUP_DIR.glob("motor_pm_v2_*.db"), reverse=True)]
    return {"config": cfg, "backups": backups, "dir": str(BACKUP_DIR)}


@router.post("/api/knowledge/backup/create")
def create_backup(_user=Depends(get_current_user)):
    result = do_backup()
    if result and result.get("ok"): return result
    raise HTTPException(500, result.get("error", "Backup failed") if result else "Backup failed")


@router.post("/api/knowledge/backup/restore")
def restore_backup(data: dict, _user=Depends(get_current_user)):
    filename = data.get("file", "")
    if not filename or ".." in filename: raise HTTPException(400, "Invalid backup file")
    backup_path = BACKUP_DIR / filename
    if not backup_path.exists(): raise HTTPException(404, "备份文件不存在")
    db_path = str(_Path(settings.DATABASE_URL.replace("sqlite:///", "")))
    if not _Path(db_path).is_absolute():
        db_path = str(_Path(__file__).parent.parent.parent.parent / db_path)
    emergency = BACKUP_DIR / f"pre_restore_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(db_path, emergency)
    try:
        shutil.copy2(str(backup_path), db_path)
        return {"restored": filename, "emergency_backup": emergency.name, "message": "恢复成功，请重启服务器"}
    except Exception as e:
        shutil.copy2(str(emergency), db_path)
        raise HTTPException(500, f"恢复失败，已回滚: {e}")


@router.put("/api/knowledge/backup/config")
def update_backup_config(data: dict, _user=Depends(get_current_user)):
    global _backup_timer
    cfg = _get_backup_config()
    for k in ("enabled", "interval_hours", "retention_count"):
        if k in data: cfg[k] = data[k]
    _save_backup_config(cfg)
    if _backup_timer: _backup_timer.cancel()
    if cfg.get("enabled", True): start_backup_scheduler()
    return cfg
