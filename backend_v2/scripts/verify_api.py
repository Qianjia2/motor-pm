"""API 验证清单（角色权限系统）"""
import sys, os, json
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path: sys.path.insert(0, ROOT)

import urllib.request, urllib.error

BASE = "http://localhost:5002/api"
ok = True
results = []

def check(name, cond, detail=""):
    global ok
    results.append((name, cond, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond: ok = False

def req(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token: r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try: detail = json.loads(e.read().decode())
        except Exception: detail = {}
        return e.code, detail
    except Exception as e:
        return -1, {"err": str(e)}

def login(username, password):
    st, body = req("POST", "/auth/login", body={"username": username, "password": password})
    if st == 200:
        return body.get("access_token")
    print(f"  ! login {username} failed: {st} {body}")
    return None

# 1. admin 登录
adm = login("admin", "admin123")
check("admin 登录", adm is not None)

# 2. GET /auth/roles
st, roles = req("GET", "/auth/roles", adm)
if st == 200:
    rl = roles if isinstance(roles, list) else (roles.get("roles") or roles.get("data") or [])
    names = [r.get("name") for r in rl] if isinstance(rl, list) else []
    check("roles 含 4 内置角色", st == 200 and len(names) >= 4, f"status={st} names={names}")
    has_label = all("label" in r or "value" in r for r in rl) if isinstance(rl, list) else False
    check("roles 含 value/label 兼容 key", has_label)
else:
    check("GET /auth/roles", False, f"status={st} {roles}")

# 3. admin my-permissions = all true
st, mp = req("GET", "/auth/my-permissions", adm)
if st == 200:
    perms = mp.get("permissions", {})
    all_true = all(
        all(v.get(a) is True for a in ["view","create","edit","delete","export"])
        for v in perms.values()
    ) if perms else False
    check("admin my-permissions 全 true", all_true, f"modules={list(perms.keys())}")
else:
    check("admin my-permissions", False, f"status={st}")

# 4. 无 users 权限的账号：用稍后创建的 vuser 测试 403（此处仅占位）
ed = None

# 7. 部门 CRUD
dname = "验证部_" + os.urandom(3).hex()
st, d = req("POST", "/departments", adm, {"name": dname})
check("创建部门", st == 200, f"status={st} {str(d)[:120]}")
dept_id = d.get("id") if st == 200 else None
if dept_id:
    st, d2 = req("PUT", f"/departments/{dept_id}", adm, {"name": dname + "改"})
    check("编辑部门", st == 200, f"status={st}")
    st, d3 = req("DELETE", f"/departments/{dept_id}", adm)
    check("删除部门", st == 200, f"status={st}")

# 8. 角色 CRUD + 矩阵保存
dname2 = "API验证部_" + os.urandom(3).hex()
st, d = req("POST", "/departments", adm, {"name": dname2})
check("创建部门（第2个）", st == 200, f"status={st} {str(d)[:100]}")
dept_id = d.get("id") if isinstance(d, dict) and st == 200 else None
rname = "验证角色_" + os.urandom(3).hex()
st, r = req("POST", "/auth/permission-roles", adm, {"name": rname, "dept_id": dept_id})
check("创建部门角色", st == 200 and r.get("id"), f"status={st} {str(r)[:120]}")
role_id = r.get("id") if st == 200 else None
if role_id:
    matrix = {
        "projects": {"view": True, "create": True, "edit": True, "delete": False, "export": True},
        "bom": {"view": True, "create": False, "edit": False, "delete": False, "export": False},
        "users": {"view": False, "create": False, "edit": False, "delete": False, "export": False},
    }
    st, r2 = req("PUT", f"/auth/permission-roles/{role_id}", adm, {"permissions": matrix})
    check("保存权限矩阵", st == 200, f"status={st}")
    st, r3 = req("GET", "/auth/permission-roles", adm)
    rl = r3 if isinstance(r3, list) else (r3.get("roles") or r3.get("data") or [])
    found = next((x for x in rl if x.get("id") == role_id), None)
    check("矩阵保存后可读回", found is not None and found.get("permissions", {}).get("projects", {}).get("create") is True, str(found.get("permissions", {}).get("projects")) if found else "not found")

    # 9. 用 role_id 创建账号
    uname = "vuser_" + os.urandom(3).hex()
    st, u = req("POST", "/auth/users", adm, {"username": uname, "password": "test123", "name": "验证用户", "role_id": role_id})
    check("用 role_id 创建账号", st == 200, f"status={st} {str(u)[:120]}")
    uid = u.get("id") if isinstance(u, dict) else None
    t2 = login(uname, "test123")
    check("新账号登录", t2 is not None)
    if t2:
        st, mp2 = req("GET", "/auth/my-permissions", t2)
        if st == 200:
            pj = mp2.get("permissions", {}).get("projects", {})
            check("新账号矩阵=角色矩阵", pj.get("view") and pj.get("create") and not pj.get("delete") and pj.get("export"), str(pj))
        else:
            check("新账号 my-permissions", False, f"status={st}")
        # 6. 无 users 权限账号调 GET /auth/users → 403
        st, body = req("GET", "/auth/users", t2)
        check("无 users 权限账号访问 /auth/users → 403", st == 403, f"status={st} {str(body)[:80]}")

    # 10. 删除有账号的角色 → 409
    st, body = req("DELETE", f"/auth/permission-roles/{role_id}", adm)
    check("删除有账号的角色 → 409", st == 409, f"status={st} {str(body)[:80]}")

    # 清理：删账号、删角色、删部门
    if uid:
        req("DELETE", f"/auth/users/{uid}", adm)
    st, body = req("DELETE", f"/auth/permission-roles/{role_id}", adm)
    check("删除空角色", st == 200, f"status={st}")
    req("DELETE", f"/departments/{dept_id}", adm)

# 11. 删除内置角色 → 400
st, body = req("GET", "/auth/permission-roles", adm)
rl = body if isinstance(body, list) else (body.get("roles") or body.get("data") or [])
builtin = next((x for x in rl if x.get("is_builtin") and x.get("code") == "viewer"), None)
if builtin:
    st, body = req("DELETE", f"/auth/permission-roles/{builtin['id']}", adm)
    check("删除内置角色 → 400", st == 400, f"status={st} {str(body)[:80]}")

# 12. 降级唯一 admin → 400
st, users_resp = req("GET", "/auth/users", adm)
users = users_resp if isinstance(users_resp, list) else (users_resp.get("users") or users_resp.get("data") or [])
admins = [u for u in users if u.get("role") == "admin"]
if len(admins) >= 2:
    # 先把多余 admin（zhangxiang）降级为 viewer
    extra = next(u for u in admins if u.get("username") != "admin")
    st, _ = req("PUT", f"/auth/users/{extra['id']}", adm, {"role": "viewer"})
    check("降级多余 admin 成功", st == 200, f"status={st}")
    # 现在唯一 admin 是自己，尝试降级 → 400
    me = next(u for u in admins if u.get("username") == "admin")
    st, body = req("PUT", f"/auth/users/{me['id']}", adm, {"role": "viewer"})
    detail = body.get("detail") if isinstance(body, dict) else str(body)
    check("降级唯一 admin → 400", st == 400, f"status={st} {detail}")
    # 恢复
    req("PUT", f"/auth/users/{extra['id']}", adm, {"role": "admin"})
else:
    check("跳过唯一 admin 测试（admin 数量 < 2）", False, f"admins={len(admins)}")

# 13. GET /auth/permissions（权限定义）
st, pdef = req("GET", "/auth/permissions", adm)
check("GET /auth/permissions", st == 200 and len(pdef.get("modules", [])) >= 8, f"status={st} modules={len(pdef.get('modules', []))}")

print("\n=== API 验证", "全部通过" if ok else "存在失败项", "===")
sys.exit(0 if ok else 1)
