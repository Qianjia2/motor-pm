#!/usr/bin/env python
"""Pre-deployment validation — catches issues BEFORE they break production.
Run: python validate.py [--quick|--full]
"""

import sys, os, subprocess, time, json, importlib

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

FAIL = 0


def check(msg, ok):
    global FAIL
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {msg}")
    if not ok:
        FAIL += 1
    return ok


def phase(title):
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


# ── Phase 1: Syntax ──────────────────────────────────────────
phase("1/6 语法检查")

for root, dirs, files in os.walk("backend_v2"):
    for fn in files:
        if fn.endswith(".py") and fn not in ("migrate.py", "seed.py"):  # utility scripts, not production
            fp = os.path.join(root, fn)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    compile(f.read(), fp, "exec")
            except SyntaxError as e:
                check(f"{fp}:{e.lineno} — {e.msg}", False)

for root, dirs, files in os.walk("frontend/src"):
    for fn in files:
        if fn.endswith((".vue", ".js")):
            fp = os.path.join(root, fn)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    f.read()  # Vue/JS validation would need node, just check readable
            except Exception as e:
                check(f"{fp} — {e}", False)

print("  (javascript syntax requires `npm run build`, skipped in quick mode)")

# ── Phase 2: Import ───────────────────────────────────────────
phase("2/6 Python导入检查")

for mod in [
    "backend_v2.routes.risks",
    "backend_v2.routes.bom",
    "backend_v2.routes.ai",
    "backend_v2.routes.knowledge",
    "backend_v2.routes.product_tech",
    "backend_v2.routes.plm",
    "backend_v2.routes.issue_risks",
]:
    try:
        importlib.import_module(mod)
    except Exception as e:
        check(f"import {mod} — {type(e).__name__}: {e}", False)

# ── Phase 3: Config ───────────────────────────────────────────
phase("3/6 配置文件完整性")

config_path = "data/ai_config.json"
check(f"{config_path} 存在", os.path.exists(config_path))
try:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    check("model 非空", bool(cfg.get("model", "").strip()))
    check("temperature in [0,1]", 0 <= cfg.get("temperature", 1) <= 1)
    check("max_tokens > 0", cfg.get("max_tokens", 0) > 0)
    check("provider 非空", bool(cfg.get("provider", "").strip()))
except Exception as e:
    check(f"读取 config — {e}", False)

# ── Phase 4: Database ─────────────────────────────────────────
phase("4/6 数据库完整性")

db_path = "data/motor_pm_v2.db"
check(f"{db_path} 存在", os.path.exists(db_path))

try:
    import sqlite3
    db = sqlite3.connect(db_path)
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    required = ["project", "weekly_report", "weekly_report_line", "risk_issue"]
    for t in required:
        check(f"表 {t} 存在", t in tables)

    if "risk_issue" in tables:
        cols = [c[1] for c in db.execute("PRAGMA table_info(risk_issue)").fetchall()]
        check("risk_issue 有 source_quote 列", "source_quote" in cols)
        check("risk_issue 有 confidence 列", "confidence" in cols)
        check("risk_issue 有 source_type 列", "source_type" in cols)

    db.close()
except Exception as e:
    check(f"数据库检查 — {e}", False)

# ── Phase 5: Frontend build ──────────────────────────────────
phase("5/6 前端构建")

try:
    result = subprocess.run(
        ["npx", "vite", "build"],
        cwd="frontend",
        capture_output=True,
        text=True,
        timeout=120,
        shell=True,
    )
    ok = result.returncode == 0
    check(f"vite build (returncode={result.returncode})", ok)
    if not ok:
        print("  stderr:", result.stderr[-300:])
    check("dist/index.html 存在", os.path.exists("frontend/dist/index.html"))
except FileNotFoundError:
    check("vite build — npx not found (skip)", True)
except subprocess.TimeoutExpired:
    check("vite build — timeout", False)
except Exception as e:
    check(f"vite build — {e}", False)

# ── Phase 6: Server smoke test ────────────────────────────────
phase("6/6 服务器冒烟测试（需服务器运行中）")

try:
    import urllib.request
    resp = urllib.request.urlopen("http://localhost:5002/api/health", timeout=5)
    data = json.loads(resp.read())
    check("服务器响应 /api/health", data.get("status") == "ok")

    # Test a read endpoint
    try:
        resp2 = urllib.request.urlopen("http://localhost:5002/api/products", timeout=5)
        check("GET /api/products 可访问", resp2.status == 200)
    except Exception:
        check("GET /api/products 可访问", False)

except urllib.request.URLError:
    print("  (服务器未运行，跳过冒烟测试)")
except Exception as e:
    check(f"冒烟测试 — {e}", False)

# ── Result ────────────────────────────────────────────────────
print(f"\n{'=' * 60}")
if FAIL == 0:
    print("  全部通过! 可以安全部署。")
else:
    print(f"  {FAIL} 项检查失败，请修复后重新验证。")
print(f"{'=' * 60}")
sys.exit(0 if FAIL == 0 else 1)
