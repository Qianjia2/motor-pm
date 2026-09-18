"""权限来源:平台权限到底按什么算。

2026-09-11 改造前:账号权限 = 所属部门的权限矩阵,角色只是兜底标签,
`UserAuth.permissions` 是「个人覆盖」。但 get_user_permissions 里部门分支是
**提前 return** 的,个人覆盖的代码在它之后,只要部门配了矩阵就永远走不到——
结果是没有任何办法给某一个人单独调权限,除非给他单开一个部门。

改造后:**个人矩阵权威**。它不再是「部门之上的部分合并」,而是一份完整矩阵:
配过（permissions 里出现过任意模块键）就完全按它算,没配过（"{}"）才回落到部门。

    部分合并 → 只能给人「加」权限,永远没法「减」
    完整权威 → 才能表达「这个人关掉 BOM」

这条语义差异是本文件的重点,也是 test_personal_matrix_is_complete 存在的理由。
"""
import json

import pytest
from sqlalchemy import select

from backend_v2.auth import hash_password
from backend_v2.permissions import ACTIONS, MODULES

DEPT_CLIENTS_ONLY = {"clients": {"view": True, "create": False, "edit": False,
                                 "delete": False, "export": False}}


def _mk_user(db, uname, dept_name, personal_perms, role="member", perm_source=None,
             dept_perms=None):
    """建 部门 / 人员 / 账号 三件套,返回 UserAuth。"""
    from backend_v2.models import Department, TeamMember, UserAuth

    dept = db.execute(select(Department).where(Department.name == dept_name)).scalar_one_or_none()
    if dept is None:
        dept = Department(name=dept_name,
                          permissions=json.dumps(dept_perms or DEPT_CLIENTS_ONLY))
        db.add(dept)
        db.flush()

    m = TeamMember(name=f"权限来源测试{uname}", department=dept_name)
    db.add(m)
    db.flush()

    u = UserAuth(username=uname, password_hash=hash_password("pw12345"),
                 member_id=m.id, role=role, perm_source=perm_source,
                 permissions=json.dumps(personal_perms))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _all_false():
    return {m: {a: False for a in ACTIONS} for m in MODULES}


def test_department_matrix_wins_when_personal_is_empty(client):
    """没配过个人矩阵（"{}"）→ 部门矩阵生效。部门退居模板后仍然是新人默认值。"""
    from backend_v2.database import SessionLocal
    from backend_v2.permissions import check_permission

    with SessionLocal() as db:
        u = _mk_user(db, "perm_dept", "权限来源测试部门A", {}, perm_source="dept")
        assert check_permission(u, "clients", "view") is True
        # 部门矩阵里没开的模块,应当没有权限
        assert check_permission(u, "bom", "create") is False


def test_personal_matrix_wins_over_department(client):
    """配过个人矩阵 → 个人说了算。这是改造的核心目的。"""
    from backend_v2.database import SessionLocal
    from backend_v2.permissions import check_permission

    with SessionLocal() as db:
        u = _mk_user(db, "perm_override", "权限来源测试部门B",
                     {"bom": {"view": True, "create": True, "edit": True,
                              "delete": False, "export": False}},
                     perm_source="manual")
        assert check_permission(u, "bom", "view") is True, "个人矩阵没生效"
        assert check_permission(u, "bom", "create") is True
        assert check_permission(u, "bom", "delete") is False


def test_personal_matrix_is_complete_not_a_merge(client):
    """个人矩阵是**完整**矩阵,不是「部门之上的部分合并」。

    这条是本文件最关键的一条:上面那个人只配了 bom,部门给的 clients.view
    **不该**漏进来。如果哪天有人把它改回「部门 + 个人叠加」,这里会立刻红:
    叠加语义下只能给人加权限,没法减——「把某人的某个模块关掉」就永远做不到。
    """
    from backend_v2.database import SessionLocal
    from backend_v2.permissions import check_permission

    with SessionLocal() as db:
        u = _mk_user(db, "perm_complete", "权限来源测试部门D",
                     {"bom": {"view": True, "create": False, "edit": False,
                              "delete": False, "export": False}},
                     perm_source="manual")
        assert check_permission(u, "bom", "view") is True
        assert check_permission(u, "clients", "view") is False, (
            "部门矩阵漏进了个人矩阵——个人矩阵必须是完整的,否则没法用它收权")


def test_personal_all_false_stays_all_false(client):
    """被刻意收成全 false 的人,不该回落到部门矩阵。

    区分「没配过」和「配了但全是 false」靠的是矩阵里有没有出现过模块键:
    "{}" 是没配过,一份 16×5 全 false 是配过。否则把某人权限全关掉之后,
    他会悄悄拿回部门那一份——收权动作静默失效。
    """
    from backend_v2.database import SessionLocal
    from backend_v2.permissions import check_permission

    with SessionLocal() as db:
        u = _mk_user(db, "perm_allfalse", "权限来源测试部门E", _all_false(),
                     perm_source="manual")
        assert check_permission(u, "clients", "view") is False, (
            "全 false 的个人矩阵回落到了部门矩阵,收权静默失效")
        assert check_permission(u, "bom", "view") is False


def test_admin_is_always_all_true(client):
    """admin 硬编码全开是防锁死后门,改造必须保留。"""
    from backend_v2.database import SessionLocal
    from backend_v2.permissions import check_permission

    with SessionLocal() as db:
        # 故意给 admin 一份全 false 的个人矩阵 + 一个没权限的部门,后门仍应生效
        u = _mk_user(db, "perm_admin", "权限来源测试部门F", _all_false(),
                     role="admin", perm_source="manual")
        assert check_permission(u, "clients", "delete") is True
        assert check_permission(u, "settings", "delete") is True


def test_department_is_a_single_value_per_person(client):
    """一人只能属于一个部门——所以「按部门给权限」无法表达"这个人特殊"。

    TeamMember.department 是 String(64) 单值,不是多选、也不是关联表。
    """
    from backend_v2.database import SessionLocal
    from backend_v2.models import TeamMember

    with SessionLocal() as db:
        u = _mk_user(db, "perm_single", "权限来源测试部门C", {})
        m = db.get(TeamMember, u.member_id)
        assert isinstance(m.department, str), f"department 是 {type(m.department)},不是单值文本"
        assert m.department == "权限来源测试部门C"
