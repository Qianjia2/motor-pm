"""Start the Motor PM v2.0 server (FastAPI + uvicorn)."""
import os, sys, logging

# Force CWD to project root — critical for database path resolution
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

# Setup file logging for debugging
log_file = os.path.join(os.getcwd(), "data", "server.log")
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
# Also log to console
console = logging.StreamHandler()
console.setLevel(logging.WARNING)
logging.getLogger().addHandler(console)

# 防重复启动：服务器已经在跑就干净退出，不抢端口、不重复起看门狗和备份线程。
# 备份线程现在是**显式**启动（auto_backup.start()）—— 不再在 import 时自动起，
# 所以这段守卫放哪都不会误起线程；仍放最前面只是为了尽早退出、不做无用功。
import urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:5002/api/health", timeout=3) as _r:
        if _r.status == 200:
            _msg = "服务器已在运行（127.0.0.1:5002 健康检查通过），本进程退出，不做任何事。"
            print(_msg)
            logging.info(_msg)
            sys.exit(0)
except Exception:
    pass  # 连不上 = 确实没在跑，按正常流程启动

# 启动自动备份（后台线程：启动后 60s 首次，之后每小时一次）
try:
    from auto_backup import start as _start_backup
    _start_backup()
except Exception as e:
    print(f"[Backup] Auto-backup not started: {e}")

# Start watchdog (monitors and auto-restarts server if it crashes)
try:
    import subprocess, sys
    subprocess.Popen(
        [sys.executable, "server_watchdog.py"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print("[Watchdog] Server guardian started (auto-restart on crash)")
except Exception as e:
    print(f"[Watchdog] Not started: {e}")

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend_v2.main:app",
        host="0.0.0.0",
        port=5002,
        reload=False,
        log_level="info",
    )
