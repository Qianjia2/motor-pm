"""「我的工作台」后端口径 + 软件工作流角色回归锁。

分两部分:

一、角色回归锁(不碰数据库)
    工作流节点的 roles 是**精确命中**项目角色名的(见 project_workflow._is_mine,
    刻意不做子串匹配)。节点里写一个 role 表里不存在的角色名,那一步不会报错、
    不会崩,只会静默匹配不到任何人。S2 第 7 步「问题整改闭环」原本写
    ``["责任工程师", "测试工程师"]``——role 表查无「责任工程师」,那个标签就是死的。
    这里把「软件 S0–S3 的节点角色必须是真实存在的角色」焊死。

    为什么不直接查测试库的 role 表:测试库角色表是空的,``_role_id`` 是按需现建的,
    拿它当基准的话,写任何幽灵角色都能"现建一个"从而测不出来。基准必须来自代码。

二、me 载荷(隔离库)
    前端 MyWorkbench.vue 的五种状态全部由 me 推导,这里逐态把后端口径验掉。
"""
import ast
import pathlib

import pytest

from tests.api.test_project_workflow import (
    SOFTWARE_PHASES, _bind_member, _role_id, _software_project, _workflow,
)
from tests.conftest import auth_headers

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SEED_PY = REPO_ROOT / "backend_v2" / "seed.py"


# ═══════════════ 一、角色回归锁 ═══════════════

def _seeded_roles():
    """从 seed.py 读角色清单(AST,不执行)。

    seed.py 是代码里唯一声明「系统有哪些角色」的地方,所以拿它当基准。
    """
    tree = ast.parse(SEED_PY.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "roles":
            try:
                rows = ast.literal_eval(n.value)
            except ValueError:
                continue
            if rows and isinstance(rows[0], tuple) and len(rows[0]) == 4:
                return {row[0] for row in rows}
    raise AssertionError("没从 seed.py 读到角色清单,基准没了")


# 现网 role 表比 seed.py 多出来的角色。
#
# ⚠ 这是个**已存在的缺口**,不是本测试想维护的清单:软件 S0 第 1、2 步
# 「需求调研与澄清」「编制软件需求规格说明书(SRS)」的 roles 里有「商务经理」,
# 而 seed.py 只播 7 个角色,不含「商务经理」——它在现网库里是手工建的(id=8)。
# 也就是说:拿 seed.py 装一套新库,这两步的商务经理角色是缺的。
# 测试跟着现网的实际角色集走,这个口径要在同步 seed.py 时一并收紧。
ROLES_NOT_IN_SEED = {"商务经理", "测试"}


def _software_role_usage():
    """软件 S0–S3 每个节点角色 -> 用到它的步骤清单。"""
    from backend_v2.routes.training_process import PHASE_NODES

    used = {}
    for code in SOFTWARE_PHASES:
        for n in PHASE_NODES[code]:
            for r in (n.get("roles") or []):
                if r:
                    used.setdefault(r, []).append(f"{code}-{n['seq']} {n['name']}")
    assert used, "没读到任何节点角色,用例前提不成立"
    return used


def test_software_node_roles_are_real_roles():
    """软件 S0–S3 的每个节点角色都必须是真实存在的角色。

    幽灵角色是静默失效:不报错,只是那个角色永远认领不到那一步。这里让它变红。
    """
    allowed = _seeded_roles() | ROLES_NOT_IN_SEED
    ghosts = {r: where for r, where in _software_role_usage().items() if r not in allowed}
    assert not ghosts, (
        "软件工作流里出现了 role 表里没有的角色(永远匹配不到人):\n"
        + "\n".join(f"  「{r}」 <- {', '.join(w)}" for r, w in ghosts.items())
        + f"\n当前可用角色: {sorted(allowed)}"
    )


def test_s2_step7_no_longer_names_the_ghost_role():
    """S2 第 7 步「问题整改闭环」的回归锁:幽灵角色「责任工程师」不许再出现。

    这一步原来写 ["责任工程师", "测试工程师"],「责任工程师」是死标签;实际干这活
    的是软件工程师,已按真实现状改掉。谁改回去这条就红。
    """
    from backend_v2.routes.training_process import PHASE_NODES, ROLE_FALLBACK

    node = next(n for n in PHASE_NODES["S2"] if n["seq"] == 7)
    assert "责任工程师" not in node["roles"], f"S2 第7步又写回幽灵角色了: {node['roles']}"
    assert "软件工程师" in node["roles"], f"S2 第7步丢了软件工程师: {node['roles']}"
    # 同名交付物的兜底角色也是软硬件共用的,一并锁上
    assert ROLE_FALLBACK["问题整改闭环记录"] == "软件工程师"


# ═══════════════ 二、me 载荷 ═══════════════

def _steps_of(role):
    """软件流程里某个角色负责的步骤 [(phase_code, seq)],按阶段+步序排列。"""
    from backend_v2.routes.training_process import PHASE_NODES

    out = []
    for code in SOFTWARE_PHASES:
        for n in PHASE_NODES[code]:
            if role in (n.get("roles") or []):
                out.append((code, n["seq"]))
    return out


def _first_step_seq(phase_code):
    from backend_v2.routes.training_process import PHASE_NODES

    return PHASE_NODES[phase_code][0]["seq"]


def _member_h(username, mid, client):
    """建登录账号并把它绑到人员档案上,返回该账号的请求头。

    member_id 非空才会参与项目角色校验——没绑档案的账号永远没有项目角色。
    """
    h = auth_headers(client, username, "member")
    _bind_member(username, mid)
    return h


def _add_member(client, admin, pid, name, dept, role_name):
    tm = client.post("/api/team-members", json={"name": name, "department": dept},
                     headers=admin)
    assert tm.status_code == 201, tm.text
    mid = tm.json()["id"]
    r = client.post(f"/api/projects/{pid}/members", headers=admin,
                    json={"member_id": mid, "role_id": _role_id(client, admin, role_name),
                          "allocation_pct": 100, "is_key": False, "phase_ids": "[]"})
    assert r.status_code in (200, 201), r.text
    return mid


@pytest.fixture(scope="module")
def admin(client):
    return auth_headers(client, "wb_admin", "admin")


@pytest.fixture(scope="module")
def project(client, admin):
    """一个全新的软件项目:所有步骤都还没做,便于验"轮到你了/先等前面"。"""
    return _software_project(client, admin, "WB-T1")


class TestMyWorkbench:
    """前端 MyWorkbench.vue 的五种状态,后端各给什么。"""

    def test_next_is_the_first_unblocked_step_mine(self, client, admin, project):
        """🟢 轮到你了:我负责的、前面都做完了的第一件事。

        全新项目里"前面都做完"只对每个阶段的第一步成立,所以期望值 = 我负责的
        步骤里第一个正好是所在阶段第一步的那个。
        """
        mid = _add_member(client, admin, project, "工作台软件", "研发部", "软件工程师")
        h = _member_h("wb_sw", mid, client)

        me = _workflow(client, h, project)["me"]
        assert me["has_role"] is True
        assert me["roles"] == ["软件工程师"]

        mine = _steps_of("软件工程师")
        assert me["mine_total"] == len(mine), f"我的步骤数对不上,期望 {len(mine)}"
        assert me["mine_done"] == 0, "全新项目不该有已完成的步骤"

        ready = next(((c, s) for c, s in mine if s == _first_step_seq(c)), None)
        assert ready is not None, "用例前提不成立:软件工程师没有「作为阶段第一步」的活"
        assert (me["next"]["phase_code"], me["next"]["seq"]) == ready
        assert me["next_waiting_on_prev"] is False, "前面是空的,不该说在等"

    def test_waiting_when_every_step_of_mine_is_blocked(self, client, admin, project):
        """🟡 先等前面:我负责的每件事都被前面的步骤挡着。

        算法工程师在软件流程里只有 S0 第 5 步「技术可行性分析」一处,而它前面还有
        S0 的 4 步没做——这就是"轮不到我,别催我开工"的样本。
        """
        mid = _add_member(client, admin, project, "工作台算法", "算法部", "算法工程师")
        h = _member_h("wb_algo", mid, client)

        me = _workflow(client, h, project)["me"]
        assert me["has_role"] is True
        assert me["next"] is not None, "有我的活,next 不能是空的"
        assert me["next_waiting_on_prev"] is True, "前面没做完,应报「先等前面」"
        assert me["next"]["blocked_by"], "说在等,就得列出来在等哪几步"
        assert me["mine_open"] == len(_steps_of("算法工程师"))

    def test_pending_covers_every_open_step_of_mine(self, client, admin, project):
        """pending 必须覆盖我所有未完成的步骤,不能只给"下一步"。"""
        mid = _add_member(client, admin, project, "工作台测试", "测试部", "测试工程师")
        h = _member_h("wb_tester", mid, client)

        me = _workflow(client, h, project)["me"]
        got = {(p["phase_code"], p["seq"]) for p in me["pending"]}
        assert got == set(_steps_of("测试工程师"))
        assert len(me["pending"]) == me["mine_open"] == me["mine_total"]

    def test_s2_step7_is_assigned_to_software_engineer(self, client, admin, project):
        """回归锁(走接口):修好角色后,S2 第 7 步对软件工程师 assigned_to_me 为真。

        修之前这一步的 roles 是 ["责任工程师","测试工程师"],软件工程师认领不到。
        """
        mid = _add_member(client, admin, project, "工作台整改", "研发部", "软件工程师")
        h = _member_h("wb_fix", mid, client)

        wf = _workflow(client, h, project)
        s2 = next(p for p in wf["phases"] if p["phase_code"] == "S2")
        step7 = next(s for s in s2["steps"] if s["seq"] == 7)
        assert step7["node"]["name"] == "问题整改闭环"
        assert step7["assigned_to_me"] is True, "软件工程师认领不到 S2 第 7 步,幽灵角色没修干净"
        assert any(p["phase_code"] == "S2" and p["seq"] == 7 for p in wf["me"]["pending"])

    def test_hint_when_account_has_no_member_record(self, client, admin, project):
        """⚪ 没角色:给的是 hint 原文,不是空对象。

        账号没绑人员档案的人压根进不了项目组,前端要能说清"为什么看不到我的事"。
        """
        h = auth_headers(client, "wb_nobody", "member")
        me = _workflow(client, h, project)["me"]
        assert me["has_role"] is False
        assert me["roles"] == []
        assert me["member_id"] is None
        assert me["mine_total"] == 0
        assert "项目团队" in me["hint"], f"hint 没指出去哪加人: {me['hint']!r}"
        assert me["username"] == "wb_nobody", "没档案时显示名应退回登录名"

    def test_member_of_other_project_sees_no_role_here(self, client, admin, project):
        """在别的项目有角色,不代表在这个项目有——角色按项目算。"""
        other = _software_project(client, admin, "WB-T2")
        mid = _add_member(client, admin, other, "工作台他人", "研发部", "软件工程师")
        h = _member_h("wb_other", mid, client)

        me = _workflow(client, h, project)["me"]
        assert me["has_role"] is False, "在别的项目有角色不该漏到本项目"
        assert me["mine_total"] == 0
        assert _workflow(client, h, other)["me"]["has_role"] is True
