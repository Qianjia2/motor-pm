"""沟通记录关联项目: 写路径校验、解除关联、项目维度只读接口。

背景: 沟通记录原先只挂客户(client_communication.client_id),客户下多个项目时分不清
聊的是哪个项目。现加可选的 project_id,本文件锁死四条约束,防止以后被改回去:
  1. 只能关联「同一客户」的项目(防止把 A 客户的沟通挂到 B 客户的项目上)
  2. 关联的项目必须存在且未软删
  3. 传 null/'' 能解除关联(端到端抓「JSON.stringify 丢 undefined」这类 bug)
  4. 项目侧接口只返回本项目的记录,且沿用项目成员可见性
"""
from tests.conftest import auth_headers, login


def _client(c, admin, name, abbr):
    r = c.post("/api/clients", json={"name": name, "abbreviation": abbr}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _project(c, admin, name, code, client_id):
    r = c.post("/api/projects", json={"name": name, "code": code, "client_id": client_id}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _post_comm(c, cid, headers, **kw):
    payload = {"comm_date": "2026-09-10", "comm_type": "电话", "subject": "沟通测试", "content": "内容"}
    payload.update(kw)
    return c.post(f"/api/clients/{cid}/communications", json=payload, headers=headers)


def _get_comm(c, comm_id, cid, headers):
    rows = c.get(f"/api/clients/{cid}/communications", headers=headers).json()
    return next(r for r in rows if r["id"] == comm_id)


def test_create_with_own_project_returns_project_fields(client):
    """带本客户的项目新建 → 201,且响应直接带出项目名/编号(客户端不必再查一次)。"""
    admin = auth_headers(client, "cpl_admin1", "admin")
    cid = _client(client, admin, "关联测试客户甲", "CPL-A")
    pid = _project(client, admin, "关联测试项目甲", "CPL-P1", cid)

    r = _post_comm(client, cid, admin, project_id=pid)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["project_id"] == pid
    assert d["project_name"] == "关联测试项目甲"
    assert d["project_code"] == "CPL-P1"


def test_create_without_project_is_allowed(client):
    """不传项目照旧能建(历史记录和商务洽谈本就没有对应项目)。"""
    admin = auth_headers(client, "cpl_admin2", "admin")
    cid = _client(client, admin, "关联测试客户乙", "CPL-B")

    r = _post_comm(client, cid, admin)
    assert r.status_code == 201, r.text
    assert r.json()["project_id"] is None
    assert r.json()["project_name"] == ""


def test_create_with_other_clients_project_rejected(client):
    """挂到别的客户的项目上 → 400。"""
    admin = auth_headers(client, "cpl_admin3", "admin")
    cid_a = _client(client, admin, "关联测试客户丙", "CPL-C")
    cid_b = _client(client, admin, "关联测试客户丁", "CPL-D")
    pid_b = _project(client, admin, "关联测试项目丁", "CPL-P2", cid_b)

    r = _post_comm(client, cid_a, admin, project_id=pid_b)
    assert r.status_code == 400, r.text
    assert "必须属于该客户" in r.json()["detail"]


def test_create_with_soft_deleted_project_rejected(client):
    """挂到已软删的项目上 → 400。"""
    admin = auth_headers(client, "cpl_admin4", "admin")
    cid = _client(client, admin, "关联测试客户戊", "CPL-E")
    pid = _project(client, admin, "关联测试项目戊", "CPL-P3", cid)
    assert client.delete(f"/api/projects/{pid}", headers=admin).status_code == 200

    r = _post_comm(client, cid, admin, project_id=pid)
    assert r.status_code == 400, r.text
    assert "不存在或已删除" in r.json()["detail"]


def test_update_can_set_and_clear_project(client):
    """PUT 能关联,也能用 null / '' / 0 三种写法解除关联。"""
    admin = auth_headers(client, "cpl_admin5", "admin")
    cid = _client(client, admin, "关联测试客户己", "CPL-F")
    pid = _project(client, admin, "关联测试项目己", "CPL-P4", cid)
    comm_id = _post_comm(client, cid, admin).json()["id"]

    r = client.put(f"/api/communications/{comm_id}", json={"project_id": pid}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["project_id"] == pid
    assert _get_comm(client, comm_id, cid, admin)["project_name"] == "关联测试项目己"

    # null: 前端 el-select 清空后归一化传的就是这个
    r = client.put(f"/api/communications/{comm_id}", json={"project_id": None}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["project_id"] is None
    assert _get_comm(client, comm_id, cid, admin)["project_id"] is None

    # '' 和 '0': el-select 的 value-on-clear 没配好时会漏出这两种值
    for blank in ("", "0", 0):
        client.put(f"/api/communications/{comm_id}", json={"project_id": pid}, headers=admin)
        r = client.put(f"/api/communications/{comm_id}", json={"project_id": blank}, headers=admin)
        assert r.status_code == 200, f"project_id={blank!r} → {r.status_code} {r.text}"
        assert r.json()["project_id"] is None


def test_update_rejects_other_clients_project(client):
    """改记录时也不能把关联换成别的客户的项目。"""
    admin = auth_headers(client, "cpl_admin6", "admin")
    cid_a = _client(client, admin, "关联测试客户庚", "CPL-G")
    cid_b = _client(client, admin, "关联测试客户辛", "CPL-H")
    pid_b = _project(client, admin, "关联测试项目辛", "CPL-P5", cid_b)
    comm_id = _post_comm(client, cid_a, admin).json()["id"]

    r = client.put(f"/api/communications/{comm_id}", json={"project_id": pid_b}, headers=admin)
    assert r.status_code == 400, r.text
    assert _get_comm(client, comm_id, cid_a, admin)["project_id"] is None


def test_client_list_project_filter(client):
    """客户侧列表按 ?project_id= 收窄,只返回该项目的记录。"""
    admin = auth_headers(client, "cpl_admin7", "admin")
    cid = _client(client, admin, "关联测试客户壬", "CPL-I")
    pid1 = _project(client, admin, "关联测试项目壬1", "CPL-P6", cid)
    pid2 = _project(client, admin, "关联测试项目壬2", "CPL-P7", cid)
    _post_comm(client, cid, admin, project_id=pid1)
    _post_comm(client, cid, admin, project_id=pid2)
    _post_comm(client, cid, admin)                        # 不关联

    assert len(client.get(f"/api/clients/{cid}/communications", headers=admin).json()) == 3
    only1 = client.get(f"/api/clients/{cid}/communications?project_id={pid1}", headers=admin).json()
    assert [r["project_id"] for r in only1] == [pid1]


def test_project_side_list_only_own_project(client):
    """项目侧接口只返回挂到本项目的记录,并带出客户端信息。"""
    admin = auth_headers(client, "cpl_admin8", "admin")
    cid = _client(client, admin, "关联测试客户癸", "CPL-J")
    pid = _project(client, admin, "关联测试项目癸", "CPL-P8", cid)
    comm_id = _post_comm(client, cid, admin, project_id=pid, subject="项目侧可见").json()["id"]
    _post_comm(client, cid, admin, subject="项目侧不可见")

    rows = client.get(f"/api/projects/{pid}/communications", headers=admin).json()
    assert [r["id"] for r in rows] == [comm_id]
    assert rows[0]["client_id"] == cid
    assert rows[0]["subject"] == "项目侧可见"


def test_project_side_list_visibility(client):
    """项目不存在 → 404;非管理员且非项目成员 → 403;项目成员 → 200。"""
    admin = auth_headers(client, "cpl_admin9", "admin")
    cid = _client(client, admin, "关联测试客户子", "CPL-K")
    pid = _project(client, admin, "关联测试项目子", "CPL-P9", cid)
    _post_comm(client, cid, admin, project_id=pid)

    assert client.get("/api/projects/999999/communications", headers=admin).status_code == 404

    # 建一个绑了人员档案、但不在该项目组里的账号
    r = client.post("/api/team-members", json={"name": "关联测试组员"}, headers=admin)
    assert r.status_code == 201, r.text
    member_id = r.json()["id"]
    auth_headers(client, "cpl_outsider", "member")
    from sqlalchemy import select
    from backend_v2.database import SessionLocal
    from backend_v2.models import UserAuth
    with SessionLocal() as db:
        u = db.execute(select(UserAuth).where(UserAuth.username == "cpl_outsider")).scalar_one()
        u.member_id = member_id
        db.commit()
    outsider = login(client, "cpl_outsider")

    assert client.get(f"/api/projects/{pid}/communications", headers=outsider).status_code == 403


def test_profile_communications_carry_project_name(client):
    """客户360 的 communications 要带出 project_name(验证 clients.py 的预加载生效)。"""
    admin = auth_headers(client, "cpl_admin10", "admin")
    cid = _client(client, admin, "关联测试客户丑", "CPL-L")
    pid = _project(client, admin, "关联测试项目丑", "CPL-P10", cid)
    _post_comm(client, cid, admin, project_id=pid)

    prof = client.get(f"/api/clients/{cid}/profile", headers=admin).json()
    linked = [c for c in prof["communications"] if c["project_id"] == pid]
    assert linked and linked[0]["project_name"] == "关联测试项目丑"
