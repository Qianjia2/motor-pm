"""Ngrok auto-restart watchdog — restarts tunnel every 6 hours."""
import subprocess
import time
import sys

NGROK_EXE = r"D:\AI\ngrok.exe"
PORT = 5002
INTERVAL = 6 * 3600  # 6 hours

def start_ngrok():
    """Kill existing ngrok and start a new one."""
    subprocess.run("taskkill /F /IM ngrok.exe >nul 2>&1", shell=True)
    time.sleep(2)
    return subprocess.Popen(
        [NGROK_EXE, "http", str(PORT), "--log=stdout"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

if __name__ == "__main__":
    print(f"[ngrok-watchdog] Starting, refresh every {INTERVAL//3600}h")
    proc = start_ngrok()
    print("[ngrok-watchdog] Ngrok started")
    while True:
        time.sleep(INTERVAL)
        print(f"[ngrok-watchdog] Restarting ngrok...")
        proc.terminate()
        proc = start_ngrok()
        print(f"[ngrok-watchdog] Done")
