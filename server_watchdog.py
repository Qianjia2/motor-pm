"""
Server Watchdog — monitors and auto-restarts the MotorPM server.
Runs as a background process. Checks health every 30 seconds.
If server is down for 3 consecutive checks, restarts it.
"""
import subprocess, time, sys, os, logging
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))

LOG_FILE = "data/watchdog.log"
logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", encoding="utf-8",
)
console = logging.StreamHandler()
console.setLevel(logging.WARNING)
logging.getLogger().addHandler(console)

PORT = 5002
CHECK_INTERVAL = 30  # seconds
MAX_FAILURES = 3

server_process = None


def is_server_alive():
    """Check if the server responds to health check."""
    import urllib.request
    try:
        resp = urllib.request.urlopen(f"http://localhost:{PORT}/api/health", timeout=5)
        return resp.status == 200
    except Exception:
        return False


def is_tunnel_alive():
    """Quick check if ngrok tunnel is accessible from outside."""
    import urllib.request, json
    try:
        # Check ngrok local API
        resp = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=3)
        data = json.loads(resp.read())
        tunnels = data.get("tunnels", [])
        if tunnels:
            url = tunnels[0].get("public_url", "")
            if url:
                try:
                    urllib.request.urlopen(f"{url}/api/health", timeout=6)
                    return True
                except Exception:
                    pass
    except Exception:
        pass
    return False


def restart_tunnel():
    """Kill and restart ngrok tunnel as a subprocess."""
    global tunnel_process
    import subprocess as sp
    # Kill existing ngrok
    try:
        sp.run(["taskkill", "/F", "/IM", "ngrok.exe"], capture_output=True, timeout=5)
        time.sleep(2)
    except Exception:
        pass
    # Start new ngrok
    try:
        ngrok_bin = "D:/AI/ngrok.exe"
        if not os.path.exists(ngrok_bin):
            ngrok_bin = "ngrok"
        tunnel_process = sp.Popen(
            [ngrok_bin, "http", str(PORT), "--log=stdout"],
            stdout=sp.DEVNULL, stderr=sp.DEVNULL,
        )
        logging.info("ngrok tunnel started")
        time.sleep(5)
        return is_tunnel_alive()
    except Exception as e:
        logging.error(f"Failed to start ngrok: {e}")
        return False


tunnel_process = None


def start_server():
    """Start the uvicorn server process directly."""
    global server_process
    python = sys.executable
    try:
        server_process = subprocess.Popen(
            [python, "-m", "uvicorn", "backend_v2.main:app", "--host", "0.0.0.0", "--port", str(PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logging.info(f"Server started (PID {server_process.pid})")
        return True
    except Exception as e:
        logging.error(f"Failed to start server: {e}")
        return False


def stop_server():
    """Gracefully stop the server."""
    global server_process
    if server_process:
        try:
            server_process.terminate()
            server_process.wait(timeout=10)
            logging.info(f"Server stopped (PID {server_process.pid})")
        except Exception:
            server_process.kill()
            logging.warning("Server force-killed")
        server_process = None


def main():
    logging.info("=== Watchdog started ===")
    failures = 0
    start_time = datetime.now()

    # Start server immediately on first launch
    if not is_server_alive():
        logging.info("Server not running — starting now...")
        start_server()
        time.sleep(8)

    # Start ngrok tunnel
    if not is_tunnel_alive():
        logging.info("Starting ngrok tunnel...")
        restart_tunnel()

    while True:
        alive = is_server_alive()

        if alive:
            if failures > 0:
                logging.info(f"Server recovered after {failures} failures")
            failures = 0
        else:
            failures += 1
            logging.warning(f"Server DOWN ({failures}/{MAX_FAILURES})")

        if failures >= MAX_FAILURES:
            logging.error("Server unresponsive — restarting...")
            stop_server()
            time.sleep(3)
            if start_server():
                time.sleep(8)  # wait for server to initialize
                if is_server_alive():
                    failures = 0
                    logging.info("Restart successful")
                else:
                    logging.error("Restart failed — server not responding")
            else:
                logging.error("Restart failed — cannot start process")

        uptime = datetime.now() - start_time

        # Check tunnel every 5 min
        if int(uptime.total_seconds()) % 300 < CHECK_INTERVAL:
            if not is_tunnel_alive():
                logging.warning("Tunnel DOWN — restarting")
                restart_tunnel()

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
