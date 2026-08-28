"""清理前端回归测试遗留数据（回归部门/回归角色）"""
import json, urllib.request, urllib.error

BASE = "http://localhost:5002/api"

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

st, b = req("POST", "/auth/login", body={"username": "admin", "password": "admin123"})
adm = b["access_token"]

st, rl = req("GET", "/auth/permission-roles", adm)
rl = rl if isinstance(rl, list) else rl.get("roles", [])
for r in rl:
    if r["name"].startswith("回归角色"):
        s, _ = req("DELETE", "/auth/permission-roles/%d" % r["id"], adm)
        print("role", r["id"], r["name"], s)

st, ds = req("GET", "/departments", adm)
ds = ds if isinstance(ds, list) else ds.get("data", [])
for d in ds:
    if d["name"].startswith("回归部门"):
        s, _ = req("DELETE", "/departments/%d" % d["id"], adm)
        print("dept", d["id"], d["name"], s)

st, rl = req("GET", "/auth/permission-roles", adm)
rl = rl if isinstance(rl, list) else rl.get("roles", [])
print("final roles:", [(r["id"], r["name"], r["is_builtin"]) for r in rl])
st, ds = req("GET", "/departments", adm)
ds = ds if isinstance(ds, list) else ds.get("data", [])
print("final depts:", len(ds), [d["name"] for d in ds])
