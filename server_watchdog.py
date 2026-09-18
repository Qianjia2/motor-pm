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

# 隧道地址**钉死**。这是本 ngrok 账号的保留域名，显式 --url 绑上之后，
# 无论 ngrok 重启多少次公网地址都不再变。
# 以前这里（以及 ngrok_watchdog/start_all/main.py 里）都是裸的 `ngrok http 5002`，
# 子域名由 ngrok 临时分配，重启一次就可能换一个——网址做不到"保证登录正常"。
NGROK_URL = "https://reformat-handbag-oil.ngrok-free.dev"
NGROK_BIN = "D:/AI/ngrok.exe"
NGROK_LOG = "data/ngrok.log"          # ngrok 自己的输出，绑域名失败时唯一的线索
TUNNEL_PUBLIC_FAIL_LIMIT = 3          # 公网探测连续失败几次才告警（**不重启**）

# 重启计数持久化（重启计数/最近告警时间）
STATE_FILE = "data/watchdog_state.json"

# 单例锁句柄。必须一直持有到进程结束——一放手内核就释放，别的看门狗就能进来。
_singleton_handle = None

server_process = None
tunnel_process = None


def _acquire_singleton(name="MotorPM_Watchdog"):
    """确保全机器只有一个看门狗。拿到锁返回 True，已经有别人在跑返回 False。

    用 Windows 内核具名互斥体，不用锁文件：进程无论怎么死（崩溃、被 taskkill、
    直接断电），内核都会自动释放，不会留下需要人工清理的死锁。锁文件做不到——
    残留的死锁会让看门狗再也起不来，那是比重复启动更糟的故障。

    这一条独立解决"开机起好几份"：注册表、启动文件夹、run_v2.py 内部 spawn
    这几条链都会拉起看门狗，但只有第一个能拿到锁，其余的自己干净退出。
    """
    global _singleton_handle
    if os.name != "nt":
        return True   # 非 Windows 不启用；本脚本本来就依赖 taskkill 等 Windows 行为
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE   # 不声明的话 64 位下句柄会被截断
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        logging.warning(f"创建单例互斥体失败(err={ctypes.get_last_error()})，按无锁继续")
        return True
    ERROR_ALREADY_EXISTS = 183
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        # 必须关掉这个句柄。CreateMutexW 即使"已存在"也会给我们一个句柄，
        # 放弃它而不关闭的话，这个句柄会一直吊住互斥体对象——持有者退出后
        # 对象仍然活着，于是**本进程以后再调本函数永远拿到 False**。
        # 实测过：不关的话，持有者已经死了，第二次尝试仍然返回 False。
        kernel32.CloseHandle(handle)
        return False
    _singleton_handle = handle   # 故意不 CloseHandle：进程活着期间一直持有这把锁
    return True


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


def _local_tunnel_url():
    """问 ngrok 本地 API 现在有没有隧道；有就返回公网地址，没有返回 None。

    这是本机查询：毫秒级、不依赖公网。所以它才是判断"隧道还在不在"的可靠依据。
    旧版的 is_tunnel_alive() 把"本地有没有隧道"和"公网通不通"混在一个布尔里，
    主循环只能拿到一个 False，分不清是隧道死了还是网络抖了，于是统统按"重启"处理
    ——日志里那 199 次 Tunnel DOWN 大多属于后者，重启既治不了病，还把好隧道打断了。
    """
    import urllib.request, json
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=3)
        tunnels = json.loads(resp.read()).get("tunnels", [])
        if tunnels:
            return tunnels[0].get("public_url", "") or None
    except Exception:
        pass
    return None


def _port_in_use(timeout=2):
    """5002 端口有没有人在听。

    区分"服务器死了"和"服务器正在启动"：刚开机时 run_v2.py 的 uvicorn 要几秒
    才 ready，这期间 /api/health 是连不上的，但端口已经占住了。旧版只看
    check_health()，于是把"正在启动"判成"没在跑"，又起一个 uvicorn —— 日志里
    08:16 那两次相隔 13 秒的 `Server started` 就是这么来的，两个 uvicorn 抢一个
    端口，活下来的那个是谁全看运气。
    """
    import socket
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except Exception:
        return False
    finally:
        s.close()


def _public_reachable(url, timeout=6):
    """从公网能不能真的访问到。失败**只用于告警**，不用来重启隧道。"""
    import urllib.request
    try:
        urllib.request.urlopen(f"{url}/api/health", timeout=timeout)
        return True
    except Exception:
        return False


def _stop_own_tunnel():
    """只停我们自己起的那个 ngrok 子进程。绝不 taskkill /IM ngrok.exe。"""
    global tunnel_process
    if tunnel_process is None:
        return
    try:
        if tunnel_process.poll() is None:
            tunnel_process.terminate()
            tunnel_process.wait(timeout=5)
    except Exception:
        try:
            tunnel_process.kill()
        except Exception:
            pass
    tunnel_process = None


def restart_tunnel():
    """确保有一条隧道在用。已经有的就采用，不碰它。

    旧版第一件事是 `taskkill /F /IM ngrok.exe`——按进程名全局杀，不管这条隧道
    是谁起的。两个看门狗一起跑时就会互相打掉对方刚建好的隧道，而每打掉一次
    公网地址就可能换一个。现在只动自己起的子进程；别人起好的隧道直接采用，
    所以看门狗和 app 里的 /api/tunnel/start 也不再互殴。
    """
    global tunnel_process

    existing = _local_tunnel_url()
    if existing:
        logging.info(f"已有隧道在用，直接采用：{existing}")
        return True

    _stop_own_tunnel()   # 收掉自己上一轮起的那个（只动自己的子进程）

    import subprocess as sp
    ngrok_bin = NGROK_BIN
    if not os.path.exists(ngrok_bin):
        ngrok_bin = "ngrok"
    try:
        # ngrok 输出留档：绑域名失败时这是唯一能看出原因的线索（旧版丢进 DEVNULL，
        # 出了事什么都查不到）。
        os.makedirs(os.path.dirname(NGROK_LOG), exist_ok=True)
        logf = open(NGROK_LOG, "ab", buffering=0)
        tunnel_process = sp.Popen(
            [ngrok_bin, "http", str(PORT), f"--url={NGROK_URL}", "--log=stdout"],
            stdout=logf, stderr=sp.STDOUT,
        )
        logging.info(f"ngrok 已启动（绑定 {NGROK_URL}）")
    except Exception as e:
        logging.error(f"Failed to start ngrok: {e}")
        return False

    # 等隧道建起来（最多 15 秒），顺手核对地址对不对
    for _ in range(15):
        time.sleep(1)
        url = _local_tunnel_url()
        if url:
            if url.rstrip("/") != NGROK_URL.rstrip("/"):
                logging.warning(f"隧道地址与预期不符：拿到 {url}，期望 {NGROK_URL}"
                                f"——可能这个域名并非本账号的保留域名，详见 {NGROK_LOG}")
                send_alert(f"[MotorPM] 公网地址不是预期的 {NGROK_URL}，实际为 {url}",
                           "tunnel_url_mismatch")
            else:
                logging.info(f"隧道就绪：{url}")
            return True
    logging.error(f"ngrok 启动超时，详见 {NGROK_LOG}")
    return False


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
    # 单例闸门放在最前面：拿不到锁说明已经有看门狗在跑，自己干净退出。
    # 开机时几条自启链会同时拉起本脚本，这里是唯一一处拦住重复的地方——
    # 靠清理自启项是拦不住的（用户随时可能双击 run_v2.py，它内部又会 spawn 一个）。
    if not _acquire_singleton():
        logging.info("已有看门狗在运行，本进程退出")
        print("[Watchdog] 已有看门狗在运行，本进程退出")
        return

    state = _load_state()
    logging.info("=== Watchdog started ===")
    logging.info(f"Historical restarts: {state.get('restart_count', 0)}")
    failures = 0
    tunnel_public_fails = 0   # 公网探测连续失败次数（跨循环累计）
    start_time = datetime.now()

    # 开机第一次探活。这里最容易误判：run_v2.py 是先把我们 spawn 出来、
    # 自己再去起 uvicorn 的，所以本脚本的第一次 health check 几乎必然撞上
    # uvicorn 还没 ready 的窗口。端口有人在听就说明"正在启动"，等它，别抢。
    if not check_health()[0]:
        if _port_in_use():
            logging.info("5002 已被占用（另一个实例正在启动），等它就绪，不另起服务")
            for _ in range(12):          # 最多等 60 秒
                time.sleep(5)
                if check_health()[0]:
                    logging.info("已有实例就绪，接管监控")
                    break
            else:
                logging.warning("等了 60 秒仍未就绪，交给主循环的失败计数处理")
        else:
            # 端口还空着，但也可能只是 run_v2.py 的 uvicorn 还没 bind 到那一步
            # （它先 spawn 我们，再起 uvicorn）。给一段有界的宽限，反复探几次
            # 再下结论。代价顶多是"真的要起服务时慢 30 秒"——那本来就没人用；
            # 收益是不再出现两个 uvicorn 抢一个端口。
            for _ in range(10):              # 最多等 30 秒
                time.sleep(3)
                if check_health()[0]:
                    logging.info("等待期间检测到已有实例就绪，接管监控，不另起服务")
                    break
            else:
                if _port_in_use():
                    logging.info("端口已被占用，交由主循环判断，不另起服务")
                else:
                    logging.info("Server not running — starting now...")
                    start_server()
                    time.sleep(8)

    # 确保有隧道：没有才起，已经有（哪怕是别人起的）就采用，不碰
    if not _local_tunnel_url():
        logging.info("没有隧道，启动 ngrok...")
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

        # 隧道每 5 分钟查一次。三层判断，顺序不能反：
        #   1) 本地 API 说没隧道        → 真故障，重启
        #   2) 本地有隧道、公网也通      → 正常，计数清零
        #   3) 本地有隧道、公网不通      → 网络抖动，只计数告警，**绝不重启**
        # 第 3 条是这次改动的主因：旧版把 2 和 3 混成一个 False，公网一抖就重启隧道。
        # 日志里那 199 次 "Tunnel DOWN — restarting" 大多是这么来的——重启治不了
        # 公网抖动，只会白白丢掉刚建好的隧道和网址。
        if int(uptime.total_seconds()) % 300 < CHECK_INTERVAL:
            url = _local_tunnel_url()
            if not url:
                logging.warning("本地 API 显示没有隧道 — 重启")
                restart_tunnel()
                tunnel_public_fails = 0
            elif _public_reachable(url):
                if tunnel_public_fails:
                    logging.info(f"公网已恢复（此前连续 {tunnel_public_fails} 次探测失败）")
                tunnel_public_fails = 0
            else:
                tunnel_public_fails += 1
                logging.warning(f"隧道在、公网不通（{tunnel_public_fails}/{TUNNEL_PUBLIC_FAIL_LIMIT}）"
                                f"——只告警不重启")
                if tunnel_public_fails >= TUNNEL_PUBLIC_FAIL_LIMIT:
                    send_alert(
                        f"[MotorPM] 公网 {url} 连续 {tunnel_public_fails} 次探测失败，"
                        f"但本地隧道仍在（系统按设计未重启，避免丢网址），请检查网络出口",
                        "tunnel_public_unreachable")
                    tunnel_public_fails = 0   # 清零交给告警自身的 30 分钟限流去防刷屏

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
