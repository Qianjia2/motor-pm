# -*- coding: utf-8 -*-
"""API 验证：变更两级签核（创建→一级通过→二级通过→批准；驳回路径）。"""
import json, sys, urllib.request, urllib.error

BASE = "http://localhost:5002"

def call(method, path, body=None, tok=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {tok}"} if tok else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}

def login():
    _, d = call("POST", "/api/auth/login", {"username": "admin", "password": "admin123"})
    return d["access_token"]

def main():
    tok = login()
    h = {"tok": tok}
    # 项目与成员
    _, projs = call("GET", "/api/projects", tok=tok)
    projs = projs.get("data", []) if isinstance(projs, dict) else projs
    proj = next((p for p in projs if p.get("is_active", True)), None)
    if not proj:
        print("NO PROJECT"); sys.exit(1)
    pid = proj["id"]
    _, members = call("GET", "/api/team-members", tok=tok)
    l1 = members[0]["id"]; l2 = members[-1]["id"]
    print(f"project={pid} l1={l1} l2={l2}")

    # 创建变更（缺签核人 → 400）
    code, d = call("POST", f"/api/projects/{pid}/changes", {"title": "t"}, tok=tok)
    print("缺签核人:", code, d.get("detail"))

    # 创建变更（两级签核人）
    code, c = call("POST", f"/api/projects/{pid}/changes",
        {"title": "验证-二级签核", "change_level": "B", "description": "测试",
         "requester_id": l1, "submitted_date": "2026-08-12",
         "level1_signer_id": l1, "level2_signer_id": l2}, tok=tok)
    cid = c.get("id")
    print("创建:", code, "cid=", cid, "status=", c.get("status"),
          "signoffs=", [(s["level"], s["status"]) for s in c.get("signoffs", [])])
    assert code == 201 and c["status"] == "pending" and len(c["signoffs"]) == 2

    # 二级先签 → 400
    s2 = next(s for s in c["signoffs"] if s["level"] == 2)
    code, d = call("POST", f"/api/changes/signoffs/{s2['id']}/approve", {"comment": "x"}, tok=tok)
    print("二级先行:", code, d.get("detail"))

    # 一级通过 → under_review
    s1 = next(s for s in c["signoffs"] if s["level"] == 1)
    code, r1 = call("POST", f"/api/changes/signoffs/{s1['id']}/approve", {"comment": "一级OK"}, tok=tok)
    print("一级通过:", code, r1.get("status"))
    _, lst = call("GET", f"/api/projects/{pid}/changes", tok=tok)
    row = next(x for x in lst if x["id"] == cid)
    print("一级后 status:", row["status"], [(s["level"], s["status"]) for s in row["signoffs"]])

    # 重复处理一级 → 400
    code, d = call("POST", f"/api/changes/signoffs/{s1['id']}/approve", {}, tok=tok)
    print("重复一级:", code, d.get("detail"))

    # 二级通过 → approved
    code, r2 = call("POST", f"/api/changes/signoffs/{s2['id']}/approve", {"comment": "二级OK"}, tok=tok)
    print("二级通过:", code, r2.get("status"))
    _, lst = call("GET", f"/api/projects/{pid}/changes", tok=tok)
    row = next(x for x in lst if x["id"] == cid)
    print("最终 status:", row["status"], "decision_date:", row.get("decision_date"),
          [(s["level"], s["status"], s.get("signed_at") is not None) for s in row["signoffs"]])
    assert row["status"] == "approved"

    # 标记已实施
    code, d = call("PUT", f"/api/changes/{cid}", {"status": "implemented"}, tok=tok)
    print("标记实施:", code)

    # 驳回路径
    code, c2 = call("POST", f"/api/projects/{pid}/changes",
        {"title": "验证-驳回", "change_level": "C", "level1_signer_id": l1, "level2_signer_id": l2}, tok=tok)
    c2id = c2["id"]
    s1b = next(s for s in c2["signoffs"] if s["level"] == 1)
    code, d = call("POST", f"/api/changes/signoffs/{s1b['id']}/reject", {"comment": "不符合要求"}, tok=tok)
    print("驳回:", code, d.get("status"))
    _, lst = call("GET", f"/api/projects/{pid}/changes", tok=tok)
    row = next(x for x in lst if x["id"] == c2id)
    print("驳回后 status:", row["status"], [(s["level"], s["status"]) for s in row["signoffs"]])
    assert row["status"] == "rejected"

    # 清理测试数据
    call("DELETE", f"/api/changes/{cid}", tok=tok)
    call("DELETE", f"/api/changes/{c2id}", tok=tok)
    print("清理完成")
    print("PASS")

if __name__ == "__main__":
    main()
