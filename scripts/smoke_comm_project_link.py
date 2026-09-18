"""线上冒烟: 沟通记录关联项目。只读为主,写入的临时记录最后删除,不留残留。

用法: python scripts/smoke_comm_project_link.py
"""
import sys
import requests

BASE = "http://127.0.0.1:5002/api"
ok = 0
fail = []


def check(name, cond, extra=""):
    global ok
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail.append(name)
        print(f"  FAIL  {name}  {extra}")


s = requests.Session()
r = s.post(f"{BASE}/auth/login", json={"username": "admin", "password": "admin123"})
check("登录", r.status_code == 200, r.text[:200])
if r.status_code != 200:
    sys.exit(1)
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

# ── 页签配置回读(验证 project_tabs.json 与 _software_tabs 已生效) ──
tabs = s.get(f"{BASE}/lookups/admin/project-tabs-config", headers=H).json()
names = [t["name"] for t in tabs]
check("硬件页签含 comms", "comms" in names, str(names))
check("comms 排在 reports 之后", names.index("comms") > names.index("reports"), str(names))
sw = s.get(f"{BASE}/lookups/admin/project-tabs-config",
           params={"project_type": "software"}, headers=H).json()
check("软件页签含 comms", "comms" in [t["name"] for t in sw])

# ── 找一个「有客户且有项目」的真实客户 ──
clients = s.get(f"{BASE}/clients", headers=H).json()
projects = s.get(f"{BASE}/projects", params={"page_size": 100}, headers=H).json()
projects = projects if isinstance(projects, list) else (projects.get("data") or projects.get("items") or [])
pairs = [(p["client"]["id"], p["id"], p["name"]) for p in projects
         if p.get("client") and p.get("is_active")]
check("存在可用的客户+项目组合", bool(pairs), f"{len(projects)} 个项目")
cid, pid, pname = pairs[0]
print(f"        使用客户 #{cid} / 项目 #{pid} {pname}")

# ── 只读: 项目侧列表 ──
r = s.get(f"{BASE}/projects/{pid}/communications", headers=H)
check("GET 项目沟通列表 200", r.status_code == 200, r.text[:200])
check("GET 项目沟通列表返回数组", isinstance(r.json(), list), r.text[:120])

# ── 只读: 客户 360 带出 project_name ──
prof = s.get(f"{BASE}/clients/{cid}/profile", headers=H).json()
comm_keys = set(prof["communications"][0].keys()) if prof.get("communications") else set()
check("profile.communications 含 project_name",
      "project_name" in comm_keys and "project_code" in comm_keys, str(comm_keys))

# ── 只读: 客户列表 ?project_id= 过滤 ──
a = s.get(f"{BASE}/clients/{cid}/communications", headers=H).json()
b = s.get(f"{BASE}/clients/{cid}/communications", params={"project_id": pid}, headers=H).json()
check("?project_id= 返回子集", len(b) <= len(a), f"{len(b)} vs {len(a)}")
check("?project_id= 每条都挂在该项目", all(x["project_id"] == pid for x in b), str(b)[:200])

created = []
try:
    # ── 写: 建一条带项目的沟通 ──
    r = s.post(f"{BASE}/clients/{cid}/communications", headers=H, json={
        "comm_date": "2026-09-10", "comm_type": "电话", "subject": "冒烟-关联项目",
        "content": "自动冒烟脚本创建,结束即删除", "project_id": pid})
    check("POST 关联本项目 201", r.status_code == 201, r.text[:200])
    if r.status_code == 201:
        d = r.json()
        created.append(d["id"])
        check("响应带 project_id", d["project_id"] == pid, str(d.get("project_id")))
        check("响应带 project_name", d["project_name"] == pname, f"{d.get('project_name')!r} vs {pname!r}")

        # 项目侧能查到
        rows = s.get(f"{BASE}/projects/{pid}/communications", headers=H).json()
        check("项目侧能查到新记录", d["id"] in [x["id"] for x in rows])

        # 解除关联: null
        r = s.put(f"{BASE}/communications/{d['id']}", headers=H, json={"project_id": None})
        check("PUT project_id=null → 200", r.status_code == 200, r.text[:200])
        check("PUT null 后已解除", r.json()["project_id"] is None, str(r.json().get("project_id")))
        again = [x for x in s.get(f"{BASE}/clients/{cid}/communications", headers=H).json()
                 if x["id"] == d["id"]][0]
        check("重新 GET 确已解除", again["project_id"] is None and again["project_name"] == "")

        # 解除关联: ''
        s.put(f"{BASE}/communications/{d['id']}", headers=H, json={"project_id": pid})
        r = s.put(f"{BASE}/communications/{d['id']}", headers=H, json={"project_id": ""})
        check("PUT project_id='' → 200 且解除",
              r.status_code == 200 and r.json()["project_id"] is None, r.text[:200])

        # 重新关联
        r = s.put(f"{BASE}/communications/{d['id']}", headers=H, json={"project_id": pid})
        check("PUT 重新关联 → 200", r.status_code == 200 and r.json()["project_id"] == pid, r.text[:200])

        # 别的客户的项目 → 400
        other = [c["id"] for c in clients if c["id"] != cid]
        if other:
            r = s.post(f"{BASE}/clients/{other[0]}/communications", headers=H, json={
                "subject": "冒烟-越权关联", "project_id": pid})
            check("跨客户关联 → 400", r.status_code == 400, f"{r.status_code} {r.text[:150]}")
            if r.status_code == 201:
                created.append(r.json()["id"])

    # 不存在的项目 → 400
    r = s.post(f"{BASE}/clients/{cid}/communications", headers=H, json={
        "subject": "冒烟-坏项目", "project_id": 99999999})
    check("不存在的项目 → 400", r.status_code == 400, f"{r.status_code} {r.text[:150]}")
    if r.status_code == 201:
        created.append(r.json()["id"])

    # 不存在的项目 → 项目侧 404
    r = s.get(f"{BASE}/projects/99999999/communications", headers=H)
    check("项目侧不存在项目 → 404", r.status_code == 404, str(r.status_code))
finally:
    for comm_id in created:
        dr = s.delete(f"{BASE}/communications/{comm_id}", headers=H)
        print(f"        清理沟通记录 #{comm_id} → {dr.status_code}")

print(f"\n{ok} passed, {len(fail)} failed" + (f" → {fail}" if fail else ""))
sys.exit(1 if fail else 0)
