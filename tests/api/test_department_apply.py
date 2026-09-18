"""部门「一键下发」:改部门矩阵不会自动影响任何人,下发是那个显式动作。

个人矩阵是权威的（见 test_permission_source.py）,所以改了部门矩阵之后,除非
有人主动下发,否则谁的权限都不会变。这个接口就是干这个的,而且必须:
  - 先能 dry_run 预览,让确认框说清「将覆盖 N 人,其中 M 人已单独配置」
  - 只影响本部门,别把隔壁部门的人一起改了
  - 覆盖已单独配置的人（这是它的用途）,但要把人数报出来
  - 跳过 admin 和停用账号

顺带钉住新建人员的默认值:建号时没显式带 permissions → 套所属部门模板。

每个用例用独立 tag 造数据——测试库是整个会话共用的,名字撞了会 400。
"""
import pytest

from backend_v2.permissions import ACTIONS
from tests.conftest import auth_headers

DEPT_MATRIX = {"clients": {a: True for a in ACTIONS}}
OTHER_MATRIX = {"bom": {a: True for a in ACTIONS}}

PW = "pw12345"


@pytest.fixture(scope="module")
def admin(client):
    return auth_headers(client, "apply_admin_test", "admin")


def _mk_dept(client, admin, name, matrix):
    r = client.get("/api/departments", headers=admin)
    assert r.status_code == 200, r.text
    for d in r.json():
        if d["name"] == name:
            dept_id = d["id"]
            break
    else:
        r = client.post("/api/departments", json={"name": name}, headers=admin)
        assert r.status_code in (200, 201), r.text
        dept_id = r.json()["id"]
    r = client.put(f"/api/departments/{dept_id}", json={"permissions": matrix}, headers=admin)
    assert r.status_code == 200, r.text
    return dept_id


def _mk_member(client, admin, name, dept_name):
    r = client.post("/api/team-members",
                    json={"name": name, "department": dept_name}, headers=admin)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _mk_account(client, admin, uname, member_id, permissions=None, role="member"):
    body = {"username": uname, "password": PW, "member_id": member_id, "role": role}
    if permissions is not None:
        body["permissions"] = permissions
    r = client.post("/api/auth/users", json=body, headers=admin)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _acct(client, admin, uname):
    r = client.get("/api/auth/users", headers=admin)
    assert r.status_code == 200, r.text
    rows = [u for u in r.json() if u["username"] == uname]
    assert len(rows) == 1, rows
    return rows[0]


def _setup(client, admin, tag):
    """一个部门 + 两个成员账号 + 隔壁部门一个账号,名字带 tag 互不干扰。

    返回 (dept_id, uid_甲, uid_乙, uid_丙)。乙被改成单独配置。
    """
    dept_name = f"下发测试部门{tag}"
    other_name = f"下发测试别部门{tag}"
    dept_id = _mk_dept(client, admin, dept_name, DEPT_MATRIX)
    _mk_dept(client, admin, other_name, OTHER_MATRIX)
    m1 = _mk_member(client, admin, f"下发测试甲{tag}", dept_name)
    m2 = _mk_member(client, admin, f"下发测试乙{tag}", dept_name)
    m3 = _mk_member(client, admin, f"下发测试丙{tag}", other_name)
    uid1 = _mk_account(client, admin, f"apply_a_{tag}", m1)
    uid2 = _mk_account(client, admin, f"apply_b_{tag}", m2)
    uid3 = _mk_account(client, admin, f"apply_c_{tag}", m3)
    # 把乙改成单独配置,用来验「已单独配置会被覆盖且被报出来」
    r = client.put(f"/api/auth/users/{uid2}",
                   json={"permissions": {"bom": {a: True for a in ACTIONS}}},
                   headers=admin)
    assert r.status_code == 200, r.text
    return dept_id, uid1, uid2, uid3


def test_new_account_inherits_department_template(client, admin):
    """建号没带 permissions → 套部门模板;带了 → 算人工配置。"""
    _setup(client, admin, "t1")

    a = _acct(client, admin, "apply_a_t1")
    assert a["perm_source"] == "dept", a
    assert a["permissions"]["clients"]["view"] is True, "没有套到部门模板"

    b = _acct(client, admin, "apply_b_t1")
    assert b["perm_source"] == "manual", b
    assert b["permissions"]["bom"]["view"] is True


def test_dry_run_lists_targets_without_changing_anything(client, admin):
    """dry_run 只报名单,一个字都不改。"""
    dept_id, uid1, uid2, uid3 = _setup(client, admin, "t2")
    before = _acct(client, admin, "apply_b_t2")["permissions"]

    r = client.post(f"/api/departments/{dept_id}/apply-to-members",
                    json={"permissions": OTHER_MATRIX, "dry_run": True}, headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["affected"] == 2, body          # 甲、乙,不含隔壁部门的丙
    assert body["customized"] == 1, body        # 乙是单独配置的
    assert sorted(x["username"] for x in body["users"]) == ["apply_a_t2", "apply_b_t2"], body

    assert _acct(client, admin, "apply_b_t2")["permissions"] == before, "dry_run 改了数据"


def test_apply_only_touches_its_own_department(client, admin):
    """正式下发:本部门全改成新矩阵,隔壁部门一动不动。"""
    dept_id, uid1, uid2, uid3 = _setup(client, admin, "t3")
    other_before = _acct(client, admin, "apply_c_t3")["permissions"]

    r = client.post(f"/api/departments/{dept_id}/apply-to-members",
                    json={"permissions": OTHER_MATRIX}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == 2

    for uname in ("apply_a_t3", "apply_b_t3"):
        a = _acct(client, admin, uname)
        assert a["permissions"]["bom"]["view"] is True, f"{uname} 没收到下发"
        assert a["permissions"]["clients"]["view"] is False, f"{uname} 还留着旧权限"
        assert a["perm_source"] == "dept", f"{uname} 来源没回到 dept"

    assert _acct(client, admin, "apply_c_t3")["permissions"] == other_before, \
        "隔壁部门的账号被误改了"


def test_apply_skips_admin_and_inactive(client, admin):
    """admin 恒为全开、停用账号没人登,都不该出现在下发名单里。"""
    dept_id, uid1, uid2, uid3 = _setup(client, admin, "t4")
    m = _mk_member(client, admin, "下发测试管理员t4", f"下发测试部门t4")
    admin_uid = _mk_account(client, admin, "apply_admin_t4", m, role="admin")

    r = client.put(f"/api/auth/users/{uid2}", json={"is_active": False}, headers=admin)
    assert r.status_code == 200, r.text

    r = client.post(f"/api/departments/{dept_id}/apply-to-members",
                    json={"permissions": OTHER_MATRIX, "dry_run": True}, headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    usernames = {x["username"] for x in body["users"]}
    assert "apply_admin_t4" not in usernames, "admin 被列进下发名单了"
    assert "apply_b_t4" not in usernames, "停用账号被列进下发名单了"
    assert "apply_a_t4" in usernames
    assert admin_uid not in {x["id"] for x in body["users"]}
    assert body["affected"] == 1, body


def test_apply_rejects_unknown_department(client, admin):
    r = client.post("/api/departments/999999/apply-to-members",
                    json={"permissions": DEPT_MATRIX}, headers=admin)
    assert r.status_code == 404, r.text
