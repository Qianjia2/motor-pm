"""启动回填:把「按部门算」切换成「按人算」时,谁都不许掉权限。

改造前账号权限是每次请求现算的（部门 → 角色 → 内置默认）。改造后认
user_auth.permissions 这一份固化值。切换那一刻必须保证每个人的有效矩阵
**逐格不变**,否则会有人登进来发现菜单少了。

所以本文件的核心是 test_backfill_preserves_effective_matrix:用**冻结的旧算法**
算一遍改造前的有效矩阵,跑回填,再用**新算法**算一遍,逐模块逐动作比对。

另外两条:
  - 幂等靠 perm_source IS NULL,而不是「值长得像」——「已回填」和「用户后来
    手改过」在数据上一模一样,用值判定会把用户手改的权限覆盖掉
  - 那 9 个账号存着从没生效过的旧矩阵,按「冻结现状」约定不进计算,但原值留痕
"""
import json

from sqlalchemy import select

from backend_v2.auth import hash_password
from backend_v2.permission_migrate import (
    _backfill_personal_permissions,
    _effective_matrix_legacy,
)
from backend_v2.permissions import ACTIONS, MODULES, check_permission

DEPT_MATRIX = {"clients": {"view": True, "create": True, "edit": False,
                           "delete": False, "export": False},
               "bom": {a: True for a in ACTIONS}}


def _mk_account(db, uname, dept_name, dept_matrix, raw_permissions, role="member"):
    """建 部门 / 人员 / 账号,账号故意不带 perm_source（模拟改造前的老数据）。"""
    from backend_v2.models import Department, TeamMember, UserAuth

    if dept_name:
        dept = db.execute(
            select(Department).where(Department.name == dept_name)
        ).scalar_one_or_none()
        if dept is None:
            dept = Department(name=dept_name,
                              permissions=json.dumps(dept_matrix) if dept_matrix else None)
            db.add(dept)
            db.flush()

    m = TeamMember(name=f"回填测试{uname}", department=dept_name or "")
    db.add(m)
    db.flush()

    u = UserAuth(username=uname, password_hash=hash_password("pw12345"),
                 member_id=m.id, role=role, perm_source=None,
                 permissions=raw_permissions if isinstance(raw_permissions, str)
                 else json.dumps(raw_permissions))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _snapshot(user):
    """整张有效矩阵的逐格快照。"""
    from backend_v2.permissions import get_user_permissions
    perms = get_user_permissions(user)
    return {(m, a): perms[m][a] for m in MODULES for a in ACTIONS}


def _diff(before, after):
    return [f"{m}.{a}: {before[(m, a)]} → {after[(m, a)]}"
            for m in MODULES for a in ACTIONS if before[(m, a)] != after[(m, a)]]


def test_backfill_preserves_effective_matrix(client):
    """回填前后有效矩阵逐格一致——这是「切换当天没人掉权限」的唯一证据。

    覆盖三种真实形态:
      A. 有部门矩阵、个人是 "{}"        → 改造前按部门算
      B. 有部门矩阵、个人存着旧 8 模块矩阵 → 改造前**部门赢**,旧值从没生效过
      C. 没部门、个人是 "{}"            → 改造前按内置角色兜底
    """
    from backend_v2.database import SessionLocal

    with SessionLocal() as db:
        cases = [
            _mk_account(db, "bf_a", "回填测试部门A", DEPT_MATRIX, {}),
            # 旧 8 模块矩阵:改造前它被部门分支挡掉,一次都没生效过
            _mk_account(db, "bf_b", "回填测试部门B", DEPT_MATRIX,
                        {"projects": {a: True for a in ACTIONS},
                         "bom": {"view": True, "create": False, "edit": False,
                                 "delete": False, "export": False}}),
            _mk_account(db, "bf_c", None, None, {}),
        ]
        before = {}
        for u in cases:
            # "改造前"必须用**冻结的旧算法**算。不能用 _snapshot()（新引擎）——
            # 新引擎读的是个人矩阵,B 那一行会读成那份从没生效过的休眠旧值,
            # 于是"改造前"变成了一个线上从未存在过的状态,比对就没意义了。
            legacy = _effective_matrix_legacy(db, u)
            assert isinstance(legacy, dict) and set(legacy) == set(MODULES)
            before[u.username] = {(m, a): legacy[m][a] for m in MODULES for a in ACTIONS}

        _backfill_personal_permissions()

        bad = []
        for u in cases:
            db.refresh(u)
            assert u.perm_source == "dept", f"{u.username} perm_source={u.perm_source}"
            after = _snapshot(u)
            d = _diff(before[u.username], after)
            if d:
                bad.append(f"{u.username}: " + "; ".join(d[:4]))
        assert not bad, "回填改变了有效权限:\n  " + "\n  ".join(bad)


def test_backfill_is_idempotent(client):
    """跑第二次匹配 0 行——靠 perm_source IS NULL,不是靠值比较。"""
    from backend_v2.database import SessionLocal
    from backend_v2.models import UserAuth

    with SessionLocal() as db:
        _mk_account(db, "bf_idem", "回填测试部门I", DEPT_MATRIX, {})

    _backfill_personal_permissions()

    with SessionLocal() as db:
        u = db.execute(select(UserAuth).where(UserAuth.username == "bf_idem")).scalar_one()
        first = u.permissions
        # 模拟用户在 UI 里手改了权限
        u.permissions = json.dumps({m: {a: True for a in ACTIONS} for m in MODULES})
        u.perm_source = "manual"
        db.commit()
        edited = u.permissions

    _backfill_personal_permissions()

    with SessionLocal() as db:
        u = db.execute(select(UserAuth).where(UserAuth.username == "bf_idem")).scalar_one()
        assert u.permissions != first
        assert u.permissions == edited, "回填覆盖了用户手改的权限——幂等标记失效了"


def test_backfill_records_dormant_value_in_audit(client):
    """旧矩阵的值进审计备查（「原值记审计」），但**不**参与权限计算。"""
    from backend_v2.database import SessionLocal
    from backend_v2.models import AuditLog, UserAuth

    dormant = {"projects": {a: True for a in ACTIONS}}
    with SessionLocal() as db:
        u = _mk_account(db, "bf_audit", "回填测试部门L", DEPT_MATRIX, dormant)
        uid = u.id

    _backfill_personal_permissions()

    with SessionLocal() as db:
        logs = db.execute(
            select(AuditLog).where(AuditLog.entity_id == uid,
                                   AuditLog.entity_type == "user_auth")
        ).scalars().all()
        assert logs, "旧矩阵没有留痕"
        assert any("projects" in (lg.details or "") for lg in logs), \
            f"审计里没有原值: {[lg.details for lg in logs]}"

        u = db.get(UserAuth, uid)
        # 冻结现状:生效的是部门矩阵,不是那份休眠的 projects 全开
        assert check_permission(u, "clients", "view") is True
        assert check_permission(u, "projects", "view") == DEPT_MATRIX.get(
            "projects", {}).get("view", False)


def test_backfill_leaves_admin_alone(client):
    """admin 恒为全开,回填跳过他们（写了也是噪音），但要落 perm_source 免得反复扫。"""
    from backend_v2.database import SessionLocal
    from backend_v2.models import UserAuth

    with SessionLocal() as db:
        _mk_account(db, "bf_admin", "回填测试部门M", DEPT_MATRIX, {}, role="admin")

    _backfill_personal_permissions()

    with SessionLocal() as db:
        u = db.execute(select(UserAuth).where(UserAuth.username == "bf_admin")).scalar_one()
        assert u.perm_source == "dept"
