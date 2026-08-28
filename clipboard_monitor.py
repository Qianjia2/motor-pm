"""
剪贴板变更监控 — 监控微信复制内容，自动提取变更请求录入平台。

用法：python clipboard_monitor.py

在微信中 Ctrl+C 复制包含变更讨论的对话 → 自动检测 → AI提取 → 弹出确认 → 自动录入平台
"""
import sys
import time
import json
import hashlib
import urllib.request
import urllib.error
import re
import threading
from pathlib import Path

try:
    import pyperclip
except ImportError:
    print("请先安装: pip install pyperclip")
    sys.exit(1)

# ── 配置 ──
API_BASE = "http://localhost:5002"
LOGIN_URL = f"{API_BASE}/api/auth/login"
CHANGE_URL = f"{API_BASE}/changes"
USERNAME = "admin"
PASSWORD = "admin123"

# 变更关键词（用于第一轮筛选，减少AI调用）
CHANGE_KEYWORDS = [
    "变更", "修改", "改一下", "调整", "改成", "换个", "需求变",
    "设计方案变", "参数改", "取消", "增加", "替换", "升级",
    "change", "modify", "update", "revise", "update request",
]

# 最多保留多少条已处理hash，防止重复处理
MAX_HISTORY = 200

# ── 全局状态 ──
last_text = ""
processed_hashes = set()
token = None
projects_cache = []


def login():
    global token
    try:
        data = json.dumps({"username": USERNAME, "password": PASSWORD}).encode()
        req = urllib.request.Request(LOGIN_URL, data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req)
        token = json.loads(resp.read())["access_token"]
        print(f"[OK] 已登录 MotorPM")
        return True
    except Exception as e:
        print(f"[ERR] 登录失败: {e}")
        return False


def ensure_login():
    global token
    if token:
        return True
    return login()


def load_projects():
    global projects_cache
    try:
        ensure_login()
        req = urllib.request.Request(
            f"{API_BASE}/api/projects?page_size=100",
            headers={"Authorization": f"Bearer {token}"}
        )
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        projects_cache = data.get("data", [])
        print(f"[OK] 加载 {len(projects_cache)} 个项目")
    except Exception as e:
        print(f"[WARN] 加载项目列表失败: {e}")


def ocr_parse_text(text: str) -> dict:
    """Call the existing OCR/AI parse endpoint with text directly."""
    try:
        ensure_login()
        # Use the existing AI service directly
        url = f"{API_BASE}/api/ai/query"
        prompt = f"""从以下微信对话中提取变更请求信息，按JSON返回：

对话内容：
{text[:4000]}

提取格式：
{{"has_change": true/false, "change": {{"title": "变更标题", "description": "变更描述", "reason": "变更原因", "impact": "影响评估", "project_hint": "客户名/产品名/项目代号/电机型号等能定位到具体项目的关键词，比如：客户简称、电机型号、产品类型等"}}, "summary": "一句话总结"}}

如果对话中没有明显变更内容，has_change返回false。只返回JSON。"""
        data = json.dumps({"prompt": prompt}).encode()
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        })
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        response_text = result.get("response", "")
        # Extract JSON
        s = response_text.find("{")
        e = response_text.rfind("}") + 1
        if s >= 0 and e > s:
            return json.loads(response_text[s:e])
        return {"has_change": False}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"has_change": False, "_note": "AI服务未启用"}
        return {"has_change": False, "_note": str(e)}
    except Exception as e:
        return {"has_change": False, "_note": str(e)}


_project_map = None
def load_project_map():
    global _project_map
    if _project_map is not None:
        return _project_map
    map_file = Path(__file__).parent / "clipboard_project_map.json"
    try:
        with open(map_file, "r", encoding="utf-8") as f:
            _project_map = json.load(f).get("mappings", [])
        print(f"[OK] 加载 {len(_project_map)} 条项目映射")
    except Exception:
        _project_map = []
    return _project_map


def match_project(hint: str) -> dict:
    """Match project by: 1) manual mapping  2) fuzzy search against name/code/client."""
    hint_lower = hint.lower().strip()
    if not hint_lower or not projects_cache:
        return None

    # 1) Check manual mapping first (most reliable)
    for m in load_project_map():
        for kw in m.get("keywords", []):
            if kw.lower() in hint_lower or kw.lower() in " ".join(
                [projects_cache[0].get("name","") for _ in [0] if projects_cache]
            ):
                pid = m["project_id"]
                for p in projects_cache:
                    if p["id"] == pid:
                        print(f"  → 映射匹配: {m.get('note','')} (关键词: {kw})")
                        return p

    # 2) Fuzzy scoring against all projects
    scores = []
    for p in projects_cache:
        score = 0
        fields = [
            p.get("name", ""),
            p.get("code", ""),
            (p.get("client") or {}).get("name", ""),
            (p.get("client") or {}).get("abbreviation", ""),
        ]
        hint_words = hint_lower.split()
        for f in fields:
            f_lower = f.lower()
            # Full match
            if hint_lower in f_lower:
                score += 10
            # Word match
            for w in hint_words:
                if len(w) >= 2 and w in f_lower:
                    score += 3
        if score > 0:
            scores.append((score, p))

    scores.sort(key=lambda x: x[0], reverse=True)
    if scores:
        best_score, best_proj = scores[0]
        print(f"  → 匹配项目: {best_proj['name']} (置信度={best_score})")
        if len(scores) > 1 and scores[1][0] > best_score * 0.7:
            print(f"  ⚠ 另有可能: {', '.join(p['name'] for _,p in scores[1:3])}")
        return best_proj

    print(f"  ⚠ 未匹配到项目，提示词: '{hint}'。请复制时确保对话包含项目名称。")
    return None


def create_change_request(change_data: dict) -> bool:
    """Create a change request in the platform."""
    try:
        ensure_login()
        # Find matching project
        project_id = None
        hint = change_data.get("project_hint") or ""
        project_name = ""

        proj = match_project(hint)
        if proj:
            project_id = proj["id"]
            project_name = proj["name"]

        if not project_id:
            # Create without project — user can assign later in the platform
            print("[WARN] 未关联项目，变更将创建为'未分配'状态，请手动关联")
            # Use first project as container, mark in description
            if projects_cache:
                project_id = projects_cache[0]["id"]
                project_name = "（待分配）"

        if not project_id:
            print("[ERR] 无可用项目")
            return False

        payload = {
            "title": change_data.get("title", "未命名变更"),
            "description": (change_data.get("description", "") +
                            f"\n\n---\n来源: 微信自动提取\n项目提示: {hint}"),
            "impact_scope": change_data.get("reason", ""),
            "impact_schedule": change_data.get("impact", ""),
            "status": "pending",
            "change_level": "C",
            "affected_lines": project_name,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/projects/{project_id}/changes",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            },
            method="POST"
        )
        urllib.request.urlopen(req)
        print(f"  ✅ 变更已创建 → {project_name}")
        return True
    except urllib.error.HTTPError as e:
        print(f"[ERR] 创建变更失败 (HTTP {e.code}):", e.read().decode()[:200])
        return False
    except Exception as e:
        print(f"[ERR] 创建变更失败: {e}")
        return False


TRIGGER_PREFIXES = ["##", "变更:", "变更：", "##变更", "!!", "录入:", "录入："]
TRIGGER_MIN_LENGTH = 30  # text must be at least this long

def is_wechat_message(text: str) -> bool:
    """Detect if text looks like a WeChat chat message."""
    if not text or len(text) < 20:
        return False
    patterns = [
        r'[一-鿿\w]{2,6}\s*\d{1,2}:\d{2}',
        r'[一-鿿\w]{2,6}[：:]',
    ]
    score = sum(1 for p in patterns if re.search(p, text))
    return score >= 1


def has_change_keywords(text: str) -> bool:
    """Quick keyword filter to avoid unnecessary AI calls."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in CHANGE_KEYWORDS)


def has_trigger_prefix(text: str) -> bool:
    """Check if text starts with a manual trigger prefix like ## or 变更:"""
    stripped = text.strip()
    for p in TRIGGER_PREFIXES:
        if stripped.startswith(p):
            return True
    return False


def strip_trigger_prefix(text: str) -> str:
    """Remove the trigger prefix from text before processing."""
    stripped = text.strip()
    for p in TRIGGER_PREFIXES:
        if stripped.startswith(p):
            return stripped[len(p):].strip()
    return text


def should_process(text: str) -> bool:
    """Decide whether to process this clipboard text.

    Two modes:
    1) Manual trigger: text starts with '##' or '变更:' → always process
    2) Auto detect: looks like WeChat + contains change keywords → process
    """
    if len(text) < TRIGGER_MIN_LENGTH:
        return False
    # Manual trigger always wins
    if has_trigger_prefix(text):
        print("  [手动触发]")
        return True
    # Auto detect needs both WeChat pattern AND change keywords
    if is_wechat_message(text) and has_change_keywords(text):
        return True
    return False


def show_notification(title: str, body: str):
    """Show Windows notification."""
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, body, duration=5, threaded=True)
    except ImportError:
        pass
    # Also print to console
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"  {body}")
    print(f"{'='*50}\n")


def process_text(text: str):
    """Process a clipboard text for change extraction."""
    global last_text
    if text == last_text:
        return
    last_text = text

    text_hash = hashlib.md5(text.encode()).hexdigest()
    if text_hash in processed_hashes:
        return

    # Smart filter
    if not should_process(text):
        return

    # Strip trigger prefix if present
    text = strip_trigger_prefix(text)

    print(f"\n[{time.strftime('%H:%M:%S')}] 检测到变更相关对话...")

    # AI parse
    result = ocr_parse_text(text)
    processed_hashes.add(text_hash)
    if len(processed_hashes) > MAX_HISTORY:
        processed_hashes.clear()

    if not result.get("has_change"):
        print("  → AI判断: 无明确变更内容")
        note = result.get("_note", "")
        if note:
            print(f"  → 备注: {note}")
        return

    change = result.get("change", {})
    title = change.get("title", "未命名")
    print(f"  → ✅ 发现变更: {title}")

    # Create change request
    ok = create_change_request(change)
    if ok:
        show_notification(
            "MotorPM 变更已录入",
            f"{title}\n\n{change.get('description', '')[:100]}"
        )
    else:
        print("  → ❌ 自动录入失败，请手动添加")


def monitor_loop():
    """Main clipboard monitoring loop."""
    print("=" * 50)
    print("  MotorPM 剪贴板变更监控")
    print("  在微信中 Ctrl+C 复制含变更讨论的对话")
    print("  平台自动检测并提取到变更管理")
    print("=" * 50)
    print()

    load_projects()

    print("[运行中] 等待复制微信对话... (Ctrl+C 退出)\n")

    while True:
        try:
            text = pyperclip.paste()
            if text and text != last_text:
                process_text(text)
            time.sleep(1.5)  # Poll every 1.5s
        except KeyboardInterrupt:
            print("\n[退出] 监控已停止")
            break
        except Exception as e:
            print(f"[ERR] {e}")
            time.sleep(3)


if __name__ == "__main__":
    monitor_loop()
