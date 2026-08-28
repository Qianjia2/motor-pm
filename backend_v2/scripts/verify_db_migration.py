"""数据层验证：部门表、内置角色、role_id 回填、权限格式转换、biz->editor"""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # D:\AI\motor-pm
if ROOT not in sys.path: sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend_v2.database import SessionLocal
from backend_v2.models import UserAuth, Department, PermissionRole
from sqlalchemy import select, func, text

db = SessionLocal()
ok = True

def check(name, cond, detail=""):
    global ok
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond: ok = False

# 1. department 表
depts = db.execute(select(Department)).scalars().all()
check("department 表存在且有数据", len(depts) > 0, f"count={len(depts)}")
print("   部门列表:", [d.name for d in depts])

# 2. permission_role 内置角色
builtins = db.execute(select(PermissionRole).where(PermissionRole.is_builtin == True)).scalars().all()
check("4 个内置角色", len(builtins) == 4, f"count={len(builtins)}")
for r in builtins:
    print(f"   builtin: code={r.code} name={r.name} dept_id={r.dept_id} perms_parsed={len(r.permissions or '')>0}")
check("内置角色 dept_id 均为 NULL", all(r.dept_id is None for r in builtins))

# 3. user_auth 有 role_id 列且已回填
try:
    db.execute(text("SELECT role_id FROM user_auth LIMIT 1"))
    has_col = True
except Exception:
    has_col = False
check("user_auth 有 role_id 列", has_col)

users = db.execute(select(UserAuth)).scalars().all()
backfilled = [u for u in users if u.role_id is not None]
check("role_id 已回填", len(backfilled) == len(users), f"{len(backfilled)}/{len(users)}")
for u in users:
    print(f"   user: {u.username} role={u.role} role_id={u.role_id}")

# 4. biz -> editor
biz = [u for u in users if u.role == 'biz']
check("无 biz 角色残留", len(biz) == 0, f"biz count={len(biz)}")

# 5. 旧 permissions 已转换（无 string values）
import json
bad = []
for u in users:
    if not u.permissions: continue
    try:
        raw = u.permissions
        if isinstance(raw, str):
            # 可能是双层编码
            v = json.loads(raw)
            if isinstance(v, str):
                v = json.loads(v)
        else:
            v = raw
        for mod, perm in v.items():
            if isinstance(perm, str):
                bad.append((u.username, mod, perm))
    except Exception as e:
        bad.append((u.username, 'parse_error', str(e)))
check("所有 permissions 均为矩阵格式", len(bad) == 0, str(bad[:5]))

# 6. 部门角色表有数据
dept_roles = db.execute(select(PermissionRole).where(PermissionRole.dept_id.isnot(None))).scalars().all()
check("部门角色已创建（如有）", True, f"count={len(dept_roles)}")
for r in dept_roles:
    print(f"   dept role: code={r.code} name={r.name} dept_id={r.dept_id}")

db.close()
print("\n=== 数据层验证", "全部通过" if ok else "存在失败项", "===")
sys.exit(0 if ok else 1)
