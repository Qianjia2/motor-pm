"""交付物标准维护接口:删除必须是「停用」,不能被启动播种复活。

用户报的 bug:在「标准维护」里删掉软件项目的交付物标准,重启后又回来了。

根因是删除走了硬删,而 main.py startup → init_db() → _seed_software_phases()
→ _seed_software_standards() 每次启动都会按 (phase_id, name)「查不到就插」。
硬删掉的行在这一查里等于"从没存在过",于是被原样插回来。

所以这里锁两件事:
  1. 删除后列表里立刻消失(列表接口必须过滤 is_active,否则软删等于白做);
  2. 再跑一次 init_db()(等价于重启)不能被插回来。

第 2 条才是根因的锁。这条测试在本修复之前必须先是红的。
"""
import pytest

from tests.conftest import auth_headers


@pytest.fixture(scope="module")
def admin(client):
    return auth_headers(client, "gr_admin", "admin")


def _standards(client, headers, **params):
    r = client.get("/api/gate-deliverable-standards", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _find(client, headers, phase_code, name):
    rows = [s for s in _standards(client, headers, project_type="software")
            if s["phase_code"] == phase_code and s["name"] == name]
    assert len(rows) == 1, f"{phase_code}「{name}」应恰好一条,实际: {[r['id'] for r in rows]}"
    return rows[0]


def _rows_in_db(phase_id, name):
    """直查库(绕开接口),用于判断播种到底有没有插回来。"""
    from sqlalchemy import select

    from backend_v2.database import SessionLocal
    from backend_v2.models import GateDeliverableStandard

    with SessionLocal() as db:
        return db.execute(
            select(GateDeliverableStandard).where(
                GateDeliverableStandard.phase_id == phase_id,
                GateDeliverableStandard.name == name,
            )
        ).scalars().all()


def _restore(phase_id, name):
    """还原为启用,不影响同会话其它测试。按 (phase_id, name) 找,不认 id。"""
    from sqlalchemy import select

    from backend_v2.database import SessionLocal
    from backend_v2.models import GateDeliverableStandard

    with SessionLocal() as db:
        for row in db.execute(
            select(GateDeliverableStandard).where(
                GateDeliverableStandard.phase_id == phase_id,
                GateDeliverableStandard.name == name,
            )
        ).scalars().all():
            row.is_active = True
        db.commit()


def test_deleted_standard_is_not_resurrected_by_reseed(client, admin):
    """停用一条播种标准 → 列表消失 → 再播种不能复活。"""
    target = _find(client, admin, "S1", "技术选型报告")
    sid, phase_id, name = target["id"], target["phase_id"], target["name"]

    try:
        # 1. 删除:接口应返回 ok,且列表里立刻消失
        r = client.delete(f"/api/gate-deliverable-standards/{sid}", headers=admin)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}
        visible = [s["id"] for s in _standards(client, admin, project_type="software")]
        assert sid not in visible, "删除后列表里还看得见——列表接口没有过滤 is_active"

        # 2. 重跑播种(等价于重启服务):不能被插回来
        from backend_v2.database import init_db
        init_db()

        rows = _rows_in_db(phase_id, name)
        assert len(rows) == 1, (
            f"播种把删掉的标准又插回来了: {[(r.id, r.is_active) for r in rows]}。"
            "删除必须走软删(is_active=False),(phase_id, name) 查重才会命中并跳过"
        )
        assert rows[0].is_active is False, "库里的行还在,但必须处于停用态"
        assert rows[0].id == sid, "应当复用原行,而不是新插一行"
        assert sid not in [s["id"] for s in _standards(client, admin, project_type="software")], \
            "重新播种后列表里又出现了"
    finally:
        _restore(phase_id, name)
