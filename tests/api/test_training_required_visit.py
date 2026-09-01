"""培训任务提交前必须实操(进入关联模块页面)的校验测试。

流程:管理员给任务配置 required_target 关联模块;成员进入该模块页面时前端
上报 /visit;未上报(或 7 天窗口外)直接提交会被 400 拒绝并返回跳转目标。
"""
import uuid

from tests.conftest import auth_headers


def _mk(client, admin, category, required_target=None, **kw):
    payload = {
        "category": category,
        "level": kw.get("level", "basic"),
        "title": kw.get("title", f"任务{uuid.uuid4().hex[:6]}"),
        "description": kw.get("description", "完成实际操练"),
        "points": kw.get("points", 10),
    }
    if required_target is not None:
        payload["required_target"] = required_target
    resp = client.post("/api/training/tasks", json=payload, headers=admin)
    assert resp.status_code == 200, resp.text
    return resp.json()["task"]


def test_submit_requires_visit_to_required_target(client):
    admin = auth_headers(client, "tt_admin1", "admin")
    task = _mk(client, admin, "产品技术库", required_target="/product-tech")

    # 未上报访问 → 提交被拒,并返回跳转目标
    resp = client.post(f"/api/training/tasks/{task['id']}/submit",
                       json={"note": "我完成了"}, headers=auth_headers(client, "tt_mem1"))
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["target"] == "/product-tech"
    assert "实际操作" in detail["message"]

    # 上报关联模块访问后提交成功
    assert client.post("/api/training/tasks/visit",
                       json={"module_path": "/product-tech"},
                       headers=auth_headers(client, "tt_mem1")).status_code == 200
    resp = client.post(f"/api/training/tasks/{task['id']}/submit",
                       json={"note": "我完成了"}, headers=auth_headers(client, "tt_mem1"))
    assert resp.status_code == 200, resp.text


def test_visit_to_other_module_does_not_count(client):
    admin = auth_headers(client, "tt_admin2", "admin")
    task = _mk(client, admin, "客户管理", required_target="/clients")

    # 只访问了别的模块 → 仍被拒
    auth_headers(client, "tt_mem2")
    client.post("/api/training/tasks/visit", json={"module_path": "/product-tech"},
                headers=auth_headers(client, "tt_mem2"))
    resp = client.post(f"/api/training/tasks/{task['id']}/submit",
                       json={"note": "我完成了"}, headers=auth_headers(client, "tt_mem2"))
    assert resp.status_code == 400
    assert resp.json()["detail"]["target"] == "/clients"


def test_task_without_required_target_submits_directly(client):
    admin = auth_headers(client, "tt_admin3", "admin")
    task = _mk(client, admin, "知识库", required_target="")

    resp = client.post(f"/api/training/tasks/{task['id']}/submit",
                       json={"note": "我完成了"}, headers=auth_headers(client, "tt_mem3"))
    assert resp.status_code == 200


def test_list_exposes_required_target_and_my_visited(client):
    admin = auth_headers(client, "tt_admin4", "admin")
    task = _mk(client, admin, "阶段门评审", required_target="/phase-gate-review")

    mem = auth_headers(client, "tt_mem4")
    items = client.get("/api/training/tasks", headers=mem).json()["items"]
    row = next(t for g in items for t in g["tasks"] if t["id"] == task["id"])
    assert row["required_target"] == "/phase-gate-review"
    assert row["my_visited"] is False

    client.post("/api/training/tasks/visit", json={"module_path": "/phase-gate-review"}, headers=mem)
    items = client.get("/api/training/tasks", headers=mem).json()["items"]
    row = next(t for g in items for t in g["tasks"] if t["id"] == task["id"])
    assert row["my_visited"] is True


def test_visit_endpoint_validates_and_requires_auth(client):
    admin = auth_headers(client, "tt_admin5", "admin")
    # 未登录 → 401
    assert client.post("/api/training/tasks/visit", json={"module_path": "/clients"}).status_code == 401
    # 非法路径 → 400
    assert client.post("/api/training/tasks/visit", json={"module_path": "clients"},
                       headers=admin).status_code == 400


def test_update_task_required_target(client):
    admin = auth_headers(client, "tt_admin6", "admin")
    task = _mk(client, admin, "BOM 管理", required_target="")

    resp = client.put(f"/api/training/tasks/{task['id']}", json={"required_target": "/bom"},
                      headers=admin)
    assert resp.status_code == 200
    items = client.get("/api/training/tasks", headers=admin).json()["items"]
    row = next(t for g in items for t in g["tasks"] if t["id"] == task["id"])
    assert row["required_target"] == "/bom"

    # 清空关联模块
    client.put(f"/api/training/tasks/{task['id']}", json={"required_target": ""}, headers=admin)
    items = client.get("/api/training/tasks", headers=admin).json()["items"]
    row = next(t for g in items for t in g["tasks"] if t["id"] == task["id"])
    assert row["required_target"] == ""
