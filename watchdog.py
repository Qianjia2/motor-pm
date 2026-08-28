"""Watchdog: auto-restart server if it crashes."""
import subprocess, time, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

while True:
    proc = subprocess.Popen([sys.executable, "run_v2.py"])
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        break
    # Log restart
    with open("data/data/watchdog.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} Server stopped (code={proc.returncode}), restarting...\n")
    time.sleep(3)
