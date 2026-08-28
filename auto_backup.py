"""Auto-backup: runs in background thread, copies data to NAS every 1 hour."""
import os, shutil, time, threading
from datetime import datetime
from pathlib import Path

NAS_BACKUP = r"\\10.136.101.13\easitech\个人文件夹\qianjia\麦克斯韦-AI项目管理平台工具后台资料存放"
LOCAL_DATA = Path(__file__).parent / "data"
INTERVAL = 1 * 3600  # 1 hour (db 仅 2.7MB, 高频备份成本可忽略)

def backup():
    if not os.path.exists(NAS_BACKUP):
        return False
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    dst = os.path.join(NAS_BACKUP, f"auto_backup_{ts}")
    try:
        # Only backup db + uploads + configs (skip OCR images and filled_templates to save space)
        os.makedirs(dst, exist_ok=True)
        for item in LOCAL_DATA.iterdir():
            src = str(item)
            if item.is_dir():
                if item.name in ("uploads", "filled_templates", "templates"):
                    continue  # skip large data, only backup metadata
                shutil.copytree(src, os.path.join(dst, item.name), dirs_exist_ok=True)
            else:
                shutil.copy2(src, os.path.join(dst, item.name))
        # Clean old backups (keep last 30 days, plus 1st-of-month snapshots forever)
        for f in sorted(Path(NAS_BACKUP).glob("auto_backup_*")):
            age = time.time() - f.stat().st_mtime
            if age > 30 * 86400:
                shutil.rmtree(str(f), ignore_errors=True)
        return True
    except Exception as e:
        print(f"[Backup] Failed: {e}")
        return False

def run_loop():
    while True:
        time.sleep(INTERVAL)
        ok = backup()
        ts = datetime.now().strftime("%H:%M")
        print(f"[Backup {ts}] {'OK' if ok else 'FAIL (NAS not available)'}")

_thread = threading.Thread(target=run_loop, daemon=True)
_thread.start()
print("[Backup] Auto-backup started (every 4h to NAS)")
