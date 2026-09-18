"""项目健康推导与异常原因测试。

驾驶舱的「异常项目」要直接显示原因。原因不能另算一遍——必须和状态标签同源,
否则会出现"标着阻塞、原因却写正常"这种自相矛盾的展示。所以这里锁三件事:

  1. health_reason_text 的措辞与边界;
  2. derive_project_health 仍只返回状态字符串(3 个调用方依赖这个形状);
  3. 端到端:造一条未关闭风险后,项目列表/详情接口确实带出 at_risk + 原因 + open_risks。
"""
import pytest
from sqlalchemy import select

from tests.conftest import auth_headers


@pytest.fixture(scope="module")
def admin(client):
    return auth_headers(client, "ph_admin", "admin")


# ═══════════════ 一、文案与形状 ═══════════════

def test_reason_text_wording_and_edges():
    from backend_v2.routes.projects import health_reason_text

    assert health_reason_text("blocked", 3, 2) == "3 个里程碑逾期、2 项风险未关闭"
    assert health_reason_text("at_risk", 1, 0) == "1 个里程碑逾期"
    assert health_reason_text("at_risk", 0, 1) == "1 项风险未关闭"

    # 正常/已完成不给原因,驾驶舱那边 v-if 就不会渲染这一行
    assert health_reason_text("normal", 0, 0) is None
    assert health_reason_text("completed", 5, 3) is None

    # 只有一项非零时不能出现多余的分隔符
    assert "、" not in health_reason_text("at_risk", 2, 0)


def test_abnormal_status_always_has_a_reason():
    """按判定阈值,异常项目不可能没有原因——否则驾驶舱会显示空原因。"""
    from backend_v2.routes.projects import health_reason_text

    for status, overdue, risks in [("blocked", 3, 0), ("blocked", 0, 2),
                                   ("at_risk", 1, 0), ("at_risk", 0, 1),
                                   ("at_risk", 2, 3)]:
        assert health_reason_text(status, overdue, risks), (status, overdue, risks)


def test_derive_project_health_shape_unchanged(client):
    """仍是 {pid: "状态字符串"} —— dashboard.py 直接 Counter(...).values() 数数。

    要带上 client:建表是 app 启动时做的,不请求一次的话这里连不上表。
    """
    from backend_v2.database import SessionLocal
    from backend_v2.models import Project
    from backend_v2.routes.projects import derive_project_health

    with SessionLocal() as db:
        projects = db.execute(select(Project).limit(5)).scalars().all()
        result = derive_project_health(db, projects)

    assert set(result) == {p.id for p in projects}
    assert all(isinstance(v, str) for v in result.values()), result
    assert set(result.values()) <= {"completed", "blocked", "at_risk", "normal"}


def test_empty_project_list_returns_empty(client):
    from backend_v2.database import SessionLocal
    from backend_v2.routes.projects import derive_project_health_detail

    with SessionLocal() as db:
        assert derive_project_health_detail(db, []) == {}


def _from_list(client, admin, code):
    """按编号检索,避开分页上限(page_size 最大 100)和排序差异。"""
    r = client.get("/api/projects", headers=admin, params={"search": code})
    assert r.status_code == 200, r.text
    rows = [p for p in r.json()["data"] if p["code"] == code]
    assert len(rows) == 1, rows
    return rows[0]


# ═══════════════ 二、接口行为 ═══════════════

def _new_project(client, admin, code):
    r = client.post("/api/projects", json={
        "name": f"健康推导测试{code}", "code": code, "project_type": "software",
    }, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_exception_reason_reaches_project_list(client, admin):
    """端到端:一条未关闭风险 → at_risk,且列表接口把原因带出来。"""
    pid = _new_project(client, admin, "PH-T1")

    r = client.post(f"/api/projects/{pid}/risks",
                    json={"title": "联调接口迟迟未就绪"}, headers=admin)
    assert r.status_code == 201, r.text

    row = _from_list(client, admin, "PH-T1")
    assert row["id"] == pid, row

    assert row["overall_status"] == "at_risk", row
    assert row["open_risks"] == 1, row
    assert "1 项风险未关闭" in (row["health_reason"] or ""), row


def test_reason_on_project_detail_too(client, admin):
    """详情接口口径要和列表一致,否则项目页和驾驶舱会各说各话。"""
    pid = _new_project(client, admin, "PH-T2")

    r = client.post(f"/api/projects/{pid}/risks",
                    json={"title": "关键器件交期不确定"}, headers=admin)
    assert r.status_code == 201, r.text

    r = client.get(f"/api/projects/{pid}", headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["overall_status"] == "at_risk", d
    assert d["open_risks"] == 1, d
    assert "1 项风险未关闭" in (d["health_reason"] or ""), d


def test_normal_project_has_no_reason(client, admin):
    """正常项目 health_reason 必须是 null,否则驾驶舱会给正常项目也画一行原因。"""
    pid = _new_project(client, admin, "PH-T3")

    r = client.get(f"/api/projects/{pid}", headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["overall_status"] == "normal", d
    assert d["health_reason"] is None, d
    assert d["open_risks"] == 0 and d["overdue_milestones"] == 0, d
