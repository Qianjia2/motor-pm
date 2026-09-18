"""验证 auto_backup.py 里的 NAS 路径能真正解析到文件。

起因：从 bash heredoc 传含中文的 UNC 路径给 Python 会静默乱码，
扫描不存在的路径返回空列表而不报错 —— 差点把"NAS 是空的"当成事实。
所以路径必须从真实 .py 文件里读（Python 源码默认 UTF-8），并显式断言。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import auto_backup as ab  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


print(f"NAS_BACKUP   = {ab.NAS_BACKUP}")
print(f"NAS_UPLOADS  = {ab.NAS_UPLOADS}")
print(f"NAS_KB_DATA  = {ab.NAS_KB_DATA}")
print(f"LOCAL_MIRROR = {ab.LOCAL_MIRROR}")
print()

check("NAS_BACKUP 存在", ab.NAS_BACKUP.exists())
check("NAS_UPLOADS 存在", ab.NAS_UPLOADS.exists())
check("NAS_KB_DATA 存在", ab.NAS_KB_DATA.exists())

# 路径里必须真的是中文，且能被系统解析（乱码的话这里会露馅）
check("NAS 路径含正确中文", "麦克斯韦" in str(ab.NAS_UPLOADS))

files = [f for f in ab.NAS_UPLOADS.rglob("*") if f.is_file()]
total = sum(f.stat().st_size for f in files)
print(f"\nNAS_UPLOADS: {len(files)} 个文件 / {total / 1024 / 1024 / 1024:.2f} GB")
check("扫描到上传文件（非空）", len(files) > 0, f"{len(files)} 个")
check("文件数与系统 find 一致（1073±20）", 1050 < len(files) < 1100, f"{len(files)} 个")

kb = [f for f in ab.NAS_KB_DATA.rglob("*") if f.is_file()]
print(f"NAS_KB_DATA: {len(kb)} 个文件")
check("知识库数据非空", len(kb) > 0, f"{len(kb)} 个")

print()
print(f"结果: {'全部通过' if not fails else '失败 ' + str(fails)}")
sys.exit(1 if fails else 0)
