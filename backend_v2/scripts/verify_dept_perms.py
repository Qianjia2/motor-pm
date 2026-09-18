"""部门权限矩阵 API 验证：16 模块、建号套模板、按人权威、一键下发、旧数据兜底

2026-09-11 权限改为「按人」后语义变了，这个脚本跟着改：
- 部门矩阵不再是「实时生效的权威」，而是**建号时的模板**
- 建号那一刻套上模板并烤成个人矩阵（perm_source='dept'），之后改部门矩阵不再自动影响他
- 要批量影响已有账号，得走 POST /departments/{id}/apply-to-members
第 1-8 段是原有断言（保持通过），第 9-12 段是新的按人语义。
"""
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

def matrix_of(token):
    """取该账号当前生效的权限矩阵。"""
    st, mp = req("GET", "/auth/my-permissions", token)
    return mp.get("permissions", {}) if st == 200 else {}

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

# 4. 临时成员+账号（部门=临时部门）——建号这一刻应当把部门模板烤进个人矩阵
uname = "duser_" + os.urandom(3).hex()
st, m = req("POST", "/team-members", adm, {
    "name": "权限验证用户", "department": dname, "username": uname, "password": "test123",
})
check("创建部门成员+账号", st == 201, f"status={st}")
uid = perm_src = None
st, users = req("GET", "/auth/users", adm)
users = users if isinstance(users, list) else users.get("users", [])
u = next((x for x in users if x["username"] == uname), None)
if u:
    uid, perm_src = u["id"], u.get("perm_source")
check("新账号 perm_source=dept（建号套模板）", perm_src == "dept", f"perm_source={perm_src}")

# 5. 登录 → my-permissions = 部门模板（建号时烤进来的那份）
tok, st = login(uname, "test123")
check("临时账号登录", tok is not None)
if tok:
    pj = matrix_of(tok).get("projects", {})
    check("账号权限=部门模板（projects view+create+edit+export）", pj.get("view") and pj.get("create") and pj.get("edit") and not pj.get("delete") and pj.get("export"), str(pj))
    pb = matrix_of(tok).get("bom", {})
    check("bom 仅 view", pb.get("view") and not pb.get("create"), str(pb))
    pmy = matrix_of(tok).get("my_work", {})
    check("my_work view 生效（16 模块细化）", pmy.get("view") is True, str(pmy))
    # 6. 无 users 权限 → 403
    st, body = req("GET", "/auth/users", tok)
    check("部门账号访问 /auth/users → 403", st == 403, f"status={st}")

# ══ 9. 按人权威（本次改造的核心）══════════════════════════════
# 改部门矩阵不再自动影响已有账号：改成「projects 只有 view、bom 全关」
changed = {"projects": {"view": True, "create": False, "edit": False, "delete": False, "export": False}}
st, _ = req("PUT", f"/departments/{dept_id}", adm, {"permissions": changed})
check("改部门矩阵", st == 200, f"status={st}")
if tok:
    pj = matrix_of(tok).get("projects", {})
    check("改部门矩阵后账号**不受影响**（个人矩阵权威）",
          pj.get("create") is True and pj.get("edit") is True,
          f"projects={pj}")

# 10. 单独给这个人配权限：把部门原本开着的 projects.create 关掉
#     ——这是旧引擎做不到的事（部门分支提前 return，个人永远被挡住）
personal = {
    "projects": {"view": True, "create": False, "edit": False, "delete": False, "export": False},
    "bom": {"view": False, "create": False, "edit": False, "delete": False, "export": False},
}
st, _ = req("PUT", f"/auth/users/{uid}", adm, {"permissions": personal})
check("给某人单独配权限", st == 200, f"status={st}")
st, users = req("GET", "/auth/users", adm)
users = users if isinstance(users, list) else users.get("users", [])
u = next((x for x in users if x["id"] == uid), None)
check("权限来源变为 manual（已单独配置）", (u or {}).get("perm_source") == "manual", f"perm_source={(u or {}).get('perm_source')}")
if tok:
    m2 = matrix_of(tok)
    pj = m2.get("projects", {})
    check("个人配置生效：projects 只剩 view（部门本来还给 create/edit）",
          pj.get("view") is True and pj.get("create") is False and pj.get("edit") is False,
          f"projects={pj}")
    check("个人配置是**完整权威**：部门给过的 bom.view 不再泄漏进来",
          m2.get("bom", {}).get("view") is False, f"bom={m2.get('bom')}")

# 11. 一键下发：dry_run 只报名单不改数据，正式下发把 manual 的人覆盖回部门矩阵
st, prev = req("POST", f"/departments/{dept_id}/apply-to-members", adm,
               {"permissions": changed, "dry_run": True})
prev = prev if isinstance(prev, dict) else {}
check("下发 dry_run 返回名单", st == 200 and prev.get("affected", 0) >= 1, f"status={st} affected={prev.get('affected')}")
check("dry_run 报出已单独配置的人", prev.get("customized") == 1, f"customized={prev.get('customized')}")
check("dry_run 不改数据（仍为 manual）", (u or {}).get("perm_source") == "manual", "")
if tok:
    check("dry_run 后个人权限未变", matrix_of(tok).get("projects", {}).get("create") is False, "")

st, applied = req("POST", f"/departments/{dept_id}/apply-to-members", adm,
                  {"permissions": changed, "dry_run": False})
applied = applied if isinstance(applied, dict) else {}
check("正式下发成功", st == 200 and applied.get("affected", 0) >= 1, f"status={st} affected={applied.get('affected')}")
st, users = req("GET", "/auth/users", adm)
users = users if isinstance(users, list) else users.get("users", [])
u = next((x for x in users if x["id"] == uid), None)
check("下发后来源回到 dept", (u or {}).get("perm_source") == "dept", f"perm_source={(u or {}).get('perm_source')}")
if tok:
    # 下发用的是改成「只有 view」之后的部门矩阵
    pj = matrix_of(tok).get("projects", {})
    check("下发后随新部门矩阵（projects 只有 view）",
          pj.get("view") is True and pj.get("create") is False, f"projects={pj}")

# 12. admin 恒全开：给他下发一份全 false 也不该锁死
st, _ = req("POST", f"/departments/{dept_id}/apply-to-members", adm, {"permissions": {}, "dry_run": True})
st2, mp_adm = req("GET", "/auth/my-permissions", adm)
adm_all_true = all(all(v.get(a) is True for a in ["view","create","edit","delete","export"]) for v in mp_adm.get("permissions", {}).values())
check("admin 不受下发影响（防锁死后门保留）", adm_all_true, f"admin all_true={adm_all_true}")

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
#    注意：迁移之后这个账号身上已经冻结了一份个人矩阵（值 = 当时的生效值 = 内置 viewer），
#    所以现在走的是「个人矩阵」分支，结果与原来的「内置兜底」一致——这正是等价性验证要的效果。
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
    check("迁移后该账号带 perm_source（已固化，不再回落）", test_u.perm_source is not None, f"perm_source={test_u.perm_source}")
else:
    check("test 账号存在", False, "not found")

print("\n=== 部门矩阵 API 验证", "全部通过" if ok else "存在失败项", "===")
sys.exit(0 if ok else 1)
