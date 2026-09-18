"""培训学习·项目管理流程:阶段内动作清单。

背景: 流程页原先只有前置商务(PRE)与收尾归档(POST)展开成详细步骤,中间的项目阶段
(P0-PP5 / S0-S3)只有一张交付物表,看不出这些交付物是"谁、按什么顺序做出来的"。
现给每个阶段补了动作清单(PHASE_NODES),本文件锁死它的四条性质:

  1. 每个阶段都有动作清单,节点字段完整(谁做/做什么/产出/交给谁/平台落点)、
     venue 合法、seq 在阶段内从 1 连续递增
  2. 有出口门禁的阶段以「发起 Gx 门禁签署」收尾;PP5 无门禁则没有这个节点
  3. 动作清单覆盖本阶段的必需交付物(合同/立项类由前置阶段产出,不计)
  4. 不出现已取消的「项目分级 / A·B·C 级」措辞

注意: 测试库的交付物标准不在播种范围内(见 test_training_process_flow.py 说明),
第 3 条由本文件自行插入受控数据来验证。
"""
from tests.conftest import auth_headers

# 前置商务阶段(PRE)产出的交付物,不该要求阶段动作清单里再出现一次
PRE_STAGE_DELIVERABLES = {"项目开发合同", "立项申请书"}

HARDWARE_GATE_PHASES = ["P0", "PP1", "PP2", "PP3", "PP4"]
SOFTWARE_GATE_PHASES = ["S0", "S1", "S2", "S3"]


def _norm(text: str) -> str:
    """比对交付物名称时抹掉全/半角括号、斜杠、空格这类排版差异。"""
    for ch in "（）()／/ 、,，:：":
        text = text.replace(ch, "")
    return text


def _flow(client, headers, project_type="hardware"):
    resp = client.get("/api/training/process-flow",
                      params={"project_type": project_type}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _phases(data, kind="phase"):
    return {s["key"]: s for s in data["stages"] if s["kind"] == kind}


def _seed_standards(rows):
    """向测试库补交付物标准(幂等)。rows = [(阶段码, 名称, 是否必需), ...]"""
    from sqlalchemy import select
    from backend_v2.database import SessionLocal
    from backend_v2.models import Phase, GateDeliverableStandard

    with SessionLocal() as db:
        for code, name, required in rows:
            phase = db.execute(select(Phase).where(Phase.code == code)).scalar_one()
            # 必须按 (阶段, 名称) 查,不能只按名称:标准名只在阶段内唯一,
            # 跨阶段重名的有 8 条(如「问题整改闭环记录」PP3 与 S2 各一条),
            # 只按名称查会 MultipleResultsFound。
            exists = db.execute(
                select(GateDeliverableStandard)
                .where(GateDeliverableStandard.phase_id == phase.id,
                       GateDeliverableStandard.name == name)
            ).scalar_one_or_none()
            if exists:
                continue
            db.add(GateDeliverableStandard(
                phase_id=phase.id, name=name, category="document", required=required,
                responsible_role="", sort_order=1, is_active=True,
                acceptance_criteria="测试用验收要点",
            ))
        db.commit()


def _node_text(nodes):
    return _norm(" ".join(n["name"] + n["actions"] + n["output"] for n in nodes))


# ── 1. 结构 ──

def test_every_phase_has_action_list(client):
    """硬件与软件的每个项目阶段都要有动作清单,不能只剩一张交付物表。"""
    h = auth_headers(client, "tpn_user1", "member")
    for ptype, codes in (("hardware", HARDWARE_GATE_PHASES + ["PP5"]),
                         ("software", SOFTWARE_GATE_PHASES)):
        phases = _phases(_flow(client, h, ptype), kind="phase")
        assert list(phases) == codes, f"{ptype} 阶段不符: {list(phases)}"
        for code in codes:
            nodes = phases[code]["nodes"]
            assert nodes, f"{ptype} {code} 缺动作清单"
            assert len(nodes) >= 3, f"{code} 动作清单过短: {len(nodes)} 步"


def test_action_nodes_are_wellformed(client):
    """每个节点四要素齐全、venue 合法、seq 在阶段内从 1 连续递增。"""
    h = auth_headers(client, "tpn_user2", "member")
    checked = 0
    for ptype in ("hardware", "software"):
        for code, st in _phases(_flow(client, h, ptype), kind="phase").items():
            seqs = [n["seq"] for n in st["nodes"]]
            assert seqs == list(range(1, len(seqs) + 1)), f"{code} seq 不连续: {seqs}"
            for n in st["nodes"]:
                where = f"{code}「{n.get('name')}」"
                assert n["roles"], f"{where} 缺责任角色"
                assert n["actions"], f"{where} 缺动作说明"
                assert n["output"], f"{where} 缺产出"
                assert n["handoff"], f"{where} 缺交接对象"
                assert n["module"], f"{where} 缺平台落点"
                assert n.get("venue") in {"钉钉", "本平台", "线下"}, \
                    f"{where} venue 非法: {n.get('venue')}"
                checked += 1
    assert checked > 50, f"断言覆盖的节点太少: {checked}"


# ── 2. 收尾是门禁发起 ──

def test_gate_phases_end_with_signoff(client):
    """有门禁的阶段最后一步是发起门禁签署;PP5 无门禁,不应有这个节点。"""
    h = auth_headers(client, "tpn_user3", "member")
    phases = _phases(_flow(client, h, "hardware"), kind="phase")

    for code in HARDWARE_GATE_PHASES:
        st = phases[code]
        assert st["gate"], f"{code} 应有出口门禁"
        last = st["nodes"][-1]
        assert last["name"] == f"发起 {st['gate']['code']} 门禁签署", \
            f"{code} 收尾节点应为门禁发起,实际「{last['name']}」"
        assert last["module"] == "项目详情 → 阶段门径", last["module"]
        assert "项目经理" in last["roles"]

    pp5 = phases["PP5"]
    assert pp5["gate"] is None, "PP5 无出口门禁"
    assert not any("门禁签署" in n["name"] for n in pp5["nodes"]), \
        "PP5 无门禁,不应出现门禁发起节点"


def test_software_phases_end_with_signoff(client):
    h = auth_headers(client, "tpn_user4", "member")
    phases = _phases(_flow(client, h, "software"), kind="phase")
    for code in SOFTWARE_GATE_PHASES:
        st = phases[code]
        assert st["gate"], f"{code} 应有出口门禁"
        assert st["nodes"][-1]["name"] == f"发起 {st['gate']['code']} 门禁签署", \
            f"{code} 收尾节点: {st['nodes'][-1]['name']}"


# ── 3. 覆盖交付物 ──

def test_action_list_covers_required_deliverables(client):
    """阶段动作清单要能对上本阶段的必需交付物,不能只有交付物表、没有动作。"""
    # 名称与阶段归属照搬业务库(data/motor_pm_v2.db)里的真实配置;
    # 后两条同时被 test_training_process_flow.py 播种,一并列上以免依赖测试执行顺序
    _seed_standards([
        ("PP1", "结构方案设计报告", True),
        ("PP1", "系统架构设计方案", True),
        ("PP2", "样机试制总结报告", True),
        ("PP3", "样机验证方案", True),
        ("PP3", "问题整改闭环记录", True),
        ("PP4", "BOM清单定版", True),
        ("PP4", "产品规格书定版", True),
        ("PP5", "项目总结报告", True),
        ("S1", "软件架构设计文档（SAD）", True),
        ("S2", "用户验收测试（UAT）报告", True),
        ("S3", "客户培训记录", True),
    ])
    h = auth_headers(client, "tpn_user5", "member")

    gaps = []
    for ptype in ("hardware", "software"):
        for code, st in _phases(_flow(client, h, ptype), kind="phase").items():
            text = _node_text(st["nodes"])
            for d in st["deliverables"]:
                if not d["required"] or d["name"] in PRE_STAGE_DELIVERABLES:
                    continue
                if _norm(d["name"]) not in text:
                    gaps.append(f"{code}/{d['name']}")
    assert not gaps, f"这些必需交付物没有对应的动作: {gaps}"


# ── 4. 岗位与措辞 ──

def test_phase_roles_include_action_roles(client):
    """阶段涉及岗位要把动作清单的角色并进去,否则岗位筛选会漏掉这些阶段。

    测试库的交付物标准为空,阶段角色只能来自动作清单——正好验证合并逻辑。
    """
    h = auth_headers(client, "tpn_user6", "member")
    phases = _phases(_flow(client, h, "hardware"), kind="phase")

    for code, expect in (("PP1", "电磁工程师"), ("PP3", "测试工程师"),
                         ("PP2", "工艺工程师"), ("PP1", "技术负责人")):
        assert expect in phases[code]["roles"], \
            f"{code} 的涉及岗位缺少动作清单里的「{expect}」"


def test_no_project_grading_wording(client):
    """项目分级已取消,阶段动作清单里不得再出现相关措辞。

    前置/收尾节点的同类断言见 test_training_process_flow.py::test_flow_nodes_declare_venue。
    """
    h = auth_headers(client, "tpn_user7", "member")
    for ptype in ("hardware", "software"):
        for code, st in _phases(_flow(client, h, ptype), kind="phase").items():
            blob = " ".join(n["name"] + n["actions"] + n["output"] + n["tip"] + n["module"]
                            for n in st["nodes"])
            for kw in ("分级", "A 级", "B 级", "C 级"):
                assert kw not in blob, f"{ptype} {code} 动作清单残留: {kw}"
