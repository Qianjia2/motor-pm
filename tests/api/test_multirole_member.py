"""一人一项目多角色:能不能加、加了之后访问控制会不会崩。

模型的唯一约束是 (project_id, member_id, role_id) 三元组,所以"同一个人在同一个
项目里担任多个角色"在数据层是合法的。这个文件把"合法"是否等于"能用"验一遍。

重点在第二个用例:多处访问控制按 (project, member) 查并且用了
scalar_one_or_none(),一人多角色时会查出多行。用管理员跑是查不出来的——
那些判定都写成 `if current_user.role != "admin" and current_user.member_id`,
管理员一律被短路。必须拿"非管理员 + 本人就是这个成员"的账号去踩。
"""
import pytest

from tests.conftest import auth_headers, login

PW = "pw12345"


@pytest.fixture(scope="module")
def admin(client):
    return auth_headers(client, "mr_admin", "admin")


def _setup(client, admin, code, uname):
    """建项目 + 建带账号的成员 + 两个角色。

    成员必须自带登录账号(POST 时传 username/password):访问控制的 member_id
    分支才可能走到,否则只能验到管理员短路。
    """
    r = client.post("/api/projects", json={
        "name": f"多角色测试项目{code}", "code": code, "project_type": "software",
    }, headers=admin)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    r = client.post("/api/team-members", json={
        "name": f"多角色测试员{code}", "username": uname,
        "password": PW, "accRole": "member"}, headers=admin)
    assert r.status_code in (200, 201), r.text
    mid = r.json()["id"]

    # 角色字典在 lookups 下,不是 /api/roles(那个会掉进 SPA 兜底返回 HTML)。
    # 测试库不播种角色,所以自己建——顺便证明 Role 是可增的。
    roles = _roles(client, admin)
    while len(roles) < 2:
        i = len(roles) + 1
        r = client.post("/api/lookups/roles",
                        json={"name": f"多角色测试角色{code}-{i}",
                              "code": f"MR{code[-1]}{i}", "sort_order": 90 + i},
                        headers=admin)
        assert r.status_code in (200, 201), r.text
        roles = _roles(client, admin)
    return pid, mid, roles[0], roles[1]


def _roles(client, admin):
    r = client.get("/api/lookups/roles", headers=admin).json()
    return r if isinstance(r, list) else r.get("data") or []


def _add(client, admin, pid, mid, role_id):
    return client.post(f"/api/projects/{pid}/members",
                       json={"member_id": mid, "role_id": role_id}, headers=admin)


def test_same_person_can_hold_two_roles_in_one_project(client, admin):
    """同一人在同一项目里加第二个角色,应当成功(唯一约束是三元组)。"""
    pid, mid, ra, rb = _setup(client, admin, "MR-T1", "mr_u1")

    assert _add(client, admin, pid, mid, ra["id"]).status_code == 201

    r2 = _add(client, admin, pid, mid, rb["id"])
    assert r2.status_code == 201, f"第二个角色被拒: {r2.status_code} {r2.text}"

    # 完全相同的三元组才该 409
    r3 = _add(client, admin, pid, mid, ra["id"])
    assert r3.status_code == 409, f"重复三元组应 409,实得 {r3.status_code}"

    rows = client.get(f"/api/projects/{pid}/members", headers=admin).json()
    rows = rows if isinstance(rows, list) else rows.get("data") or []
    mine = [x for x in rows if x["member_id"] == mid]
    assert len(mine) == 2, mine


@pytest.mark.xfail(strict=True, reason=(
    "已知缺陷(2026-09-11 实测):成员在本项目持有 2 个角色时,"
    "milestones.py:55 与 client_communications.py:103 按 (project,member) 查"
    "却用 scalar_one_or_none(),多行触发 MultipleResultsFound → 500。"
    "修好后本用例会意外通过,strict=True 会提醒去掉这个标记。"
    "team.py:205 同一写法,但只在无项目台账编辑权限的成员添加人员时才会走到,"
    "本次未复现。"))
def test_access_checks_survive_second_role(client, admin):
    """本人持有 2 个角色时,按 (project,member) 查的访问控制不该炸。

    这些判定用 scalar_one_or_none(),一人多角色时同一 (project,member) 有 2 行,
    会 MultipleResultsFound → 500。用 admin 跑会被 role!="admin" 短路,所以
    这里换成该成员自己的账号登录。
    """
    pid, mid, ra, rb = _setup(client, admin, "MR-T2", "mr_u2")
    for rid in (ra["id"], rb["id"]):
        rr = _add(client, admin, pid, mid, rid)
        assert rr.status_code == 201, rr.text

    h = login(client, "mr_u2", PW)

    # 先确认他确实能看见这个项目(否则 403 是权限问题,不是我们要验的崩溃)
    mine = client.get("/api/projects", headers=h).json()["data"]
    assert any(p["id"] == pid for p in mine), "该成员看不到自己的项目,前提不成立"

    # 逐个探:未捕获的异常会直接把测试炸掉,不隔离的话只能看到第一个雷,
    # 后面几处还得再来一轮才知道。
    probes = {
        "里程碑列表 milestones.py:55": f"/api/projects/{pid}/milestones",
        "客户沟通列表 client_communications.py:103": f"/api/projects/{pid}/communications",
    }
    blown = []
    for name, path in probes.items():
        try:
            resp = client.get(path, headers=h)
            if resp.status_code >= 500:
                blown.append(f"{name} → {resp.status_code}")
        except Exception as e:
            blown.append(f"{name} → {type(e).__name__}")

    assert not blown, "成员持有 2 个角色时这些接口炸了:\n  " + "\n  ".join(blown)
