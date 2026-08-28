"""E2E 一键运行入口: 顺序执行 4 个套件, 落盘完整日志, 输出汇总

用法:
    python e2e/run_all.py            # 默认 http://localhost:5002
    E2E_BASE=http://host:port python e2e/run_all.py

依赖: pip install -r e2e/requirements.txt  (playwright, xlrd, xlwt)
日志: e2e/output/log_suite_XX.txt
"""
import subprocess, sys, os, shutil

_DIR = os.path.dirname(os.path.abspath(__file__))
_OUT = os.path.join(_DIR, "output")
os.makedirs(_OUT, exist_ok=True)

SUITES = [
    ("suite_01_tpl_export.py", "模板1:1导出"),
    ("suite_02_21_items.py", "21项识别生成"),
    ("suite_03_multitpl.py", "多模板落位/回退"),
    ("suite_04_batch_bar.py", "批量操作条"),
]

def preflight():
    problems = []
    for mod in ("playwright", "xlrd", "xlwt"):
        try:
            __import__(mod)
        except ImportError:
            problems.append(mod)
    if problems:
        print("缺少依赖:", ", ".join(problems), "\n请执行: pip install -r e2e/requirements.txt")
        return False
    # 后端存活预检
    import urllib.request
    base = os.environ.get("E2E_BASE", "http://localhost:5002")
    try:
        urllib.request.urlopen(base + "/api/health", timeout=5)
    except Exception:
        try:
            urllib.request.urlopen(base + "/login", timeout=5)
        except Exception:
            print(f"后端不可达: {base} (先启动 backend_v2)")
            return False
    return True

def main():
    if not preflight():
        return 1
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    agg = []
    for name, label in SUITES:
        path = os.path.join(_DIR, name)
        log = os.path.join(_OUT, f"log_{name.replace('.py', '')}.txt")
        print(f"\n===== [{label}] {name} =====")
        with open(log, "w", encoding="utf-8") as f:
            p = subprocess.run([sys.executable, path], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            f.write(p.stdout.decode("utf-8", errors="replace"))
        tail = p.stdout.decode("utf-8", errors="replace").strip().splitlines()[-6:]
        print("\n".join(tail))
        agg.append((label, p.returncode == 0))
    print("\n" + "=" * 44)
    print("E2E 汇总")
    for label, ok in agg:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    npass = sum(1 for _, ok in agg if ok)
    print(f"  {npass}/{len(agg)} 套件通过  完整日志: {_OUT}")
    return 0 if npass == len(agg) else 1

if __name__ == "__main__":
    sys.exit(main())
