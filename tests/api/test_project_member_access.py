"""项目成员添加权限: 建项目的人要能一次把项目组配齐。

背景: 建项目接口允许 admin/editor/pm/biz 四种角色，但添加成员原先只允许
「admin 或该项目已有成员」，导致刚建好的空项目连第一个成员都加不进去
(非管理员建项目 → 组不了队)。现放宽为「admin / 有项目台账编辑权限 /
项目现有成员」,本文件锁死该行为,防止以后被改回去。
"""
from tests.conftest import auth_headers, login


def _bind_member(username, member_id):
    """把账号绑到人员档案上——member_id 非空才会触发成员添加的权限校验。"""
    from sqlalchemy import select
    from backend_v2.database import SessionLocal
    from backend_v2.models import UserAuth
    with SessionLocal() as db:
        u = db.execute(select(UserAuth).where(UserAuth.username == username)).scalar_one()
        u.member_id = member_id
        db.commit()


def _setup(client, admin, code, people):
    """建项目 + 建人员档案，返回 (project_id, {姓名: member_id})。"""
    r = client.post("/api/projects", json={"name": f"成员权限测试{code}", "code": code}, headers=admin)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    ids = {}
    for name in people:
        rr = client.post("/api/team-members", json={"name": name, "department": "项目部"}, headers=admin)
        assert rr.status_code == 201, rr.text
        ids[name] = rr.json()["id"]
    return pid, ids


def _pm_role_id(client, admin):
    """取「项目经理」角色 id。测试库不走 seed,角色表是空的,缺了就现场建一个。"""
    roles = client.get("/api/lookups/roles", headers=admin).json()
    for r in roles:
        if r["name"] == "项目经理":
            return r["id"]
    resp = client.post("/api/lookups/roles",
                       json={"name": "项目经理", "code": "PM", "sort_order": 1}, headers=admin)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _add(client, pid, headers, member_id, role_id, expect):
    resp = client.post(
        f"/api/projects/{pid}/members", headers=headers,
        json={"member_id": member_id, "role_id": role_id,
              "allocation_pct": 100, "is_key": False, "phase_ids": "[]"},
    )
    assert resp.status_code == expect, f"期望 {expect} 实际 {resp.status_code}: {resp.text}"
    return resp


def test_project_editor_can_staff_empty_project(client):
    """有项目台账编辑权限者(editor)建完项目后，能立即加上第一个成员。"""
    admin = auth_headers(client, "pma_admin1", "admin")
    pid, ids = _setup(client, admin, "TP-PERM-1", ["组员甲", "组员乙"])
    role_id = _pm_role_id(client, admin)

    auth_headers(client, "pma_editor", "editor")
    _bind_member("pma_editor", ids["组员甲"])       # 绑了档案,但不在该项目组里
    editor = login(client, "pma_editor")

    _add(client, pid, editor, ids["组员甲"], role_id, 201)


def test_plain_member_still_blocked(client):
    """无项目台账编辑权限的普通成员，仍不能往别人的项目里塞人。"""
    admin = auth_headers(client, "pma_admin2", "admin")
    pid, ids = _setup(client, admin, "TP-PERM-2", ["组员丙", "组员丁"])
    role_id = _pm_role_id(client, admin)

    auth_headers(client, "pma_member", "member")
    _bind_member("pma_member", ids["组员丙"])
    plain = login(client, "pma_member")

    _add(client, pid, plain, ids["组员丁"], role_id, 403)


def test_existing_project_member_can_add(client):
    """项目现有成员仍可加人(放宽前的原有路径,不能被改坏)。"""
    admin = auth_headers(client, "pma_admin3", "admin")
    pid, ids = _setup(client, admin, "TP-PERM-3", ["组员戊", "组员己"])
    role_id = _pm_role_id(client, admin)

    _add(client, pid, admin, ids["组员戊"], role_id, 201)   # 先让戊进入项目

    auth_headers(client, "pma_insider", "member")
    _bind_member("pma_insider", ids["组员戊"])              # 与项目内成员同一档案
    insider = login(client, "pma_insider")

    _add(client, pid, insider, ids["组员己"], role_id, 201)


def test_account_without_member_profile_not_blocked(client):
    """未绑定人员档案的账号维持原行为(不能因为改权限把老账号拦死)。"""
    admin = auth_headers(client, "pma_admin4", "admin")
    pid, ids = _setup(client, admin, "TP-PERM-4", ["组员庚"])
    role_id = _pm_role_id(client, admin)

    # member 角色、member_id 为空 → 校验直接跳过
    loose = auth_headers(client, "pma_noprofile", "member")
    _add(client, pid, loose, ids["组员庚"], role_id, 201)
