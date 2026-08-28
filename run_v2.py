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

# Start auto-backup to NAS (runs in background thread, every 4 hours)
try:
    from auto_backup import _thread
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
