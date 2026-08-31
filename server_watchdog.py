"""
Server Watchdog — monitors and auto-restarts the MotorPM server.
Runs as a background process. Checks health every 30 seconds.
If server is down for 3 consecutive checks, restarts it.
"""
import subprocess, time, sys, os, logging, json, tempfile
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
SLOW_RESPONSE_SECONDS = 5.0
ALERT_COOLDOWN_SECONDS = 1800  # 同类型钉钉告警 30 分钟内只发一次

# 重启计数持久化（重启计数/最近告警时间）
STATE_FILE = "data/watchdog_state.json"

server_process = None


def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"restart_count": 0, "last_restart": None, "last_alert": {}}


def _save_state(state):
    """原子写状态文件（tmp + os.replace，防写一半被杀留下半截 JSON）。"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=os.path.dirname(STATE_FILE))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def _dingtalk_webhook_url():
    """环境变量优先，其次取 backend_v2 配置的 DINGTALK_WEBHOOK_URL。"""
    url = os.environ.get("DINGTALK_WEBHOOK_URL", "")
    if url:
        return url
    try:
        from backend_v2.config import settings
        return settings.DINGTALK_WEBHOOK_URL
    except Exception:
        return ""


def send_alert(text, alert_type="default"):
    """发送钉钉机器人告警。同类型 30 分钟限流一次，防止刷屏。"""
    url = _dingtalk_webhook_url()
    if not url:
        return False
    state = _load_state()
    now = time.time()
    last = state.setdefault("last_alert", {}).get(alert_type, 0)
    if now - last < ALERT_COOLDOWN_SECONDS:
        return False
    try:
        import requests
        resp = requests.post(url, json={"msgtype": "text", "text": {"content": text}}, timeout=5)
        if resp.status_code == 200:
            state["last_alert"][alert_type] = now
            _save_state(state)
            logging.info(f"DingTalk alert sent ({alert_type})")
            return True
        logging.error(f"DingTalk alert HTTP {resp.status_code}")
    except Exception as e:
        logging.error(f"DingTalk alert failed: {e}")
    return False


def check_health():
    """检查服务器健康，返回 (存活, 响应时间ms)。响应 >5s 视为慢。"""
    import urllib.request
    try:
        t0 = time.time()
        resp = urllib.request.urlopen(f"http://localhost:{PORT}/api/health", timeout=8)
        latency_ms = int((time.time() - t0) * 1000)
        return resp.status == 200, latency_ms
    except Exception:
        return False, 0


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
    state = _load_state()
    logging.info("=== Watchdog started ===")
    logging.info(f"Historical restarts: {state.get('restart_count', 0)}")
    failures = 0
    start_time = datetime.now()

    # Start server immediately on first launch
    if not check_health()[0]:
        logging.info("Server not running — starting now...")
        start_server()
        time.sleep(8)

    # Start ngrok tunnel
    if not is_tunnel_alive():
        logging.info("Starting ngrok tunnel...")
        restart_tunnel()

    while True:
        alive, latency_ms = check_health()

        if alive:
            if failures > 0:
                logging.info(f"Server recovered after {failures} failures")
            failures = 0
            if latency_ms > SLOW_RESPONSE_SECONDS * 1000:
                logging.warning(f"Slow response: {latency_ms}ms (> {SLOW_RESPONSE_SECONDS}s)")
                send_alert(f"[MotorPM] 服务器响应缓慢: {latency_ms}ms（阈值 {SLOW_RESPONSE_SECONDS}s）", "slow_response")
        else:
            failures += 1
            logging.warning(f"Server DOWN ({failures}/{MAX_FAILURES})")

        if failures >= MAX_FAILURES:
            logging.error("Server unresponsive — restarting...")
            stop_server()
            time.sleep(3)
            if start_server():
                time.sleep(8)  # wait for server to initialize
                if check_health()[0]:
                    failures = 0
                    state = _load_state()
                    state["restart_count"] = state.get("restart_count", 0) + 1
                    state["last_restart"] = datetime.now().isoformat()
                    _save_state(state)
                    logging.info(f"Restart successful (total: {state['restart_count']})")
                    send_alert(f"[MotorPM] 服务器自动重启 #{state['restart_count']}（{datetime.now().strftime('%H:%M:%S')}）", "restart")
                else:
                    logging.error("Restart failed — server not responding")
                    send_alert("[MotorPM] 服务器重启失败，请人工介入", "restart_failed")
            else:
                logging.error("Restart failed — cannot start process")
                send_alert("[MotorPM] 无法启动服务器进程，请人工介入", "restart_failed")

        uptime = datetime.now() - start_time

        # Check tunnel every 5 min
        if int(uptime.total_seconds()) % 300 < CHECK_INTERVAL:
            if not is_tunnel_alive():
                logging.warning("Tunnel DOWN — restarting")
                restart_tunnel()

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
