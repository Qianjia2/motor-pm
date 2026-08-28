"""部门权限矩阵 API 验证：16 模块、部门矩阵生效、账号按部门取权限、旧数据兜底"""
import sys, os, json, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # D:\AI\motor-pm
if ROOT not in sys.path: sys.path.insert(0, ROOT)

BASE = "http://localhost:5002/api"
ok = True

def check(name, cond, detail=""):
    global ok
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond: ok = False

def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token: r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e:
        return -1, {"err": str(e)}

def login(username, password):
    st, b = req("POST", "/auth/login", body={"username": username, "password": password})
    return (b.get("access_token") if st == 200 else None), st

# 1. admin 登录 + 16 模块全 true
adm, st = login("admin", "admin123")
check("admin 登录", adm is not None)
st, mp = req("GET", "/auth/my-permissions", adm)
all_true = all(all(v.get(a) is True for a in ["view","create","edit","delete","export"]) for v in mp.get("permissions", {}).values())
check("admin 16 模块全 true", len(mp.get("permissions", {})) == 16 and all_true, f"modules={len(mp.get('permissions', {}))}")

# 2. GET /departments 返回 16 模块矩阵
st, depts = req("GET", "/departments", adm)
depts = depts if isinstance(depts, list) else depts.get("data", [])
check("departments 返回 permissions(16 模块)", st == 200 and len(depts) > 0 and len(depts[0].get("permissions", {})) == 16, f"depts={len(depts)}")

# 3. 临时部门 + 保存矩阵
dname = "权限验证部_" + os.urandom(3).hex()
st, d = req("POST", "/departments", adm, {"name": dname})
dept_id = d.get("id") if isinstance(d, dict) else None
check("创建临时部门", st == 200 and dept_id, f"status={st}")
matrix = {
    "projects": {"view": True, "create": True, "edit": True, "delete": False, "export": True},
    "bom": {"view": True, "create": False, "edit": False, "delete": False, "export": False},
    "users": {"view": False, "create": False, "edit": False, "delete": False, "export": False},
    "my_work": {"view": True, "create": False, "edit": False, "delete": False, "export": False},
    "dashboard": {"view": True, "create": False, "edit": False, "delete": False, "export": False},
    "settings": {"view": False, "create": False, "edit": False, "delete": False, "export": False},
}
st, _ = req("PUT", f"/departments/{dept_id}", adm, {"permissions": matrix})
check("保存部门矩阵", st == 200, f"status={st}")
st, depts = req("GET", "/departments", adm)
depts = depts if isinstance(depts, list) else depts.get("data", [])
d2 = next((x for x in depts if x["id"] == dept_id), None)
read_back = d2.get("permissions", {}) if d2 else {}
check("矩阵保存后可读回", d2 is not None and read_back.get("projects", {}).get("edit") is True, str(read_back.get("projects"))[:80])

# 4. 临时成员+账号（部门=临时部门）
uname = "duser_" + os.urandom(3).hex()
st, m = req("POST", "/team-members", adm, {
    "name": "权限验证用户", "department": dname, "username": uname, "password": "test123",
})
check("创建部门成员+账号", st == 201, f"status={st}")
uid = None
st, users = req("GET", "/auth/users", adm)
users = users if isinstance(users, list) else users.get("users", [])
u = next((x for x in users if x["username"] == uname), None)
if u: uid = u["id"]

# 5. 登录 → my-permissions = 部门矩阵
tok, st = login(uname, "test123")
check("临时账号登录", tok is not None)
if tok:
    st, mp = req("GET", "/auth/my-permissions", tok)
    pj = mp.get("permissions", {}).get("projects", {})
    check("账号权限=部门矩阵（projects view+create+edit+export）", pj.get("view") and pj.get("create") and pj.get("edit") and not pj.get("delete") and pj.get("export"), str(pj))
    pb = mp.get("permissions", {}).get("bom", {})
    check("bom 仅 view", pb.get("view") and not pb.get("create"), str(pb))
    pmy = mp.get("permissions", {}).get("my_work", {})
    check("my_work view 生效（16 模块细化）", pmy.get("view") is True, str(pmy))
    # 6. 无 users 权限 → 403
    st, body = req("GET", "/auth/users", tok)
    check("部门账号访问 /auth/users → 403", st == 403, f"status={st}")

# 7. 清理：删账号、删成员（DB）、删部门
if uid:
    req("DELETE", f"/auth/users/{uid}", adm)
from backend_v2.database import SessionLocal
from backend_v2.models import TeamMember
db = SessionLocal()
db.execute(TeamMember.__table__.delete().where(TeamMember.department == dname))
db.commit()
db.close()
st, _ = req("DELETE", f"/departments/{dept_id}", adm)
check("清理临时部门", st == 200, f"status={st}")

# 8. 旧数据兜底：无部门矩阵的账号（test，viewer 角色，role_id=3）→ 内置角色矩阵
from backend_v2.database import SessionLocal
from backend_v2.models import UserAuth
from backend_v2.permissions import get_user_permissions
from sqlalchemy import select as sa_select
db = SessionLocal()
test_u = db.execute(sa_select(UserAuth).where(UserAuth.username == "test")).scalar_one_or_none()
db.close()
if test_u:
    perms = get_user_permissions(test_u)
    pj = perms.get("projects", {})
    check("兜底=内置 viewer（projects view+export 无编辑）", pj.get("view") and not pj.get("create") and pj.get("export"), str(pj))
    check("兜底矩阵为 16 模块", len(perms) == 16, f"modules={len(perms)}")
else:
    check("test 账号存在", False, "not found")

print("\n=== 部门矩阵 API 验证", "全部通过" if ok else "存在失败项", "===")
sys.exit(0 if ok else 1)
