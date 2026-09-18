"""培训学习·项目管理流程可视化接口测试。

/api/training/process-flow 需返回:
- 前置商务节点(客户对接→合同→立项→启动会) + 数据库真实阶段 + 收尾归档节点
- 每个阶段带门禁、涉及角色;阶段内交付物带责任角色与模板名
- 前置/收尾节点标注「在哪办」:合同审批、立项审批在钉钉,平台只做阶段门把关

注意: 测试库是 init_db() 建出来的全新库(见 conftest 的 DATABASE_URL 重定向),
阶段与门由 _seed_hardware_phases/_seed_software_phases 播种,交付物标准由
_seed_*_standards 播种(硬件那 38 条是从现网库逐字抄的)。本文件仍要用受控值
覆盖其中两条的 responsible_role/criteria——现网那两条角色是空的,直接断言会
验到 ROLE_FALLBACK 兜底上,而不是"库里填了角色就原样透出"。
"""
from tests.conftest import auth_headers


def _flow(client, headers, project_type="hardware"):
    resp = client.get("/api/training/process-flow",
                      params={"project_type": project_type}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ensure_standards():
    """向测试库补两条硬件交付物标准(幂等)。

    - 「结构方案设计报告」: 数据库已填 responsible_role → 应原样透出
    - 「样机验证方案」: responsible_role 留空 → 应走 ROLE_FALLBACK 兜底
    """
    from sqlalchemy import select
    from backend_v2.database import SessionLocal
    from backend_v2.models import Phase, GateDeliverableStandard

    rows = [
        ("PP1", "结构方案设计报告", "document", True, "结构工程师", 1),
        ("PP3", "样机验证方案", "document", True, "", 1),
    ]
    with SessionLocal() as db:
        for code, name, cat, req, role, sort in rows:
            phase = db.execute(select(Phase).where(Phase.code == code)).scalar_one()
            # 按 (阶段, 名称) 查:标准名只在阶段内唯一,跨阶段重名的有 8 条。
            row = db.execute(
                select(GateDeliverableStandard)
                .where(GateDeliverableStandard.phase_id == phase.id,
                       GateDeliverableStandard.name == name)
            ).scalar_one_or_none()
            if row is None:
                row = GateDeliverableStandard(phase_id=phase.id, name=name, is_active=True)
                db.add(row)
            # 这里必须显式赋值,不能"已存在就跳过"。这两个名字在
            # database.py::_seed_hardware_standards 播种后就已存在(且 responsible_role
            # 是空的),跳过的话下面两条断言会落到别的分支上:role 走 ROLE_FALLBACK
            # 兜底恰好也得出「结构工程师」、criteria 读到现网文案——测试照样绿,
            # 但"库里填了角色就原样透出"这条就没人验了。
            row.category, row.required = cat, req
            row.responsible_role = role
            row.sort_order = sort
            row.acceptance_criteria = "测试用验收要点"
        db.commit()


def test_flow_has_pre_and_post_stages(client):
    """流程必须从商务对接开始,以结题归档结束。"""
    h = auth_headers(client, "tp_user1", "member")
    data = _flow(client, h)

    keys = [s["key"] for s in data["stages"]]
    assert keys[0] == "PRE", f"首个阶段应为前置商务节点,实际 {keys[0]}"
    assert keys[-1] == "POST", f"末个阶段应为结题归档,实际 {keys[-1]}"

    pre = data["stages"][0]
    assert len(pre["nodes"]) >= 5
    # 合同签订与立项必须在其中
    names = " ".join(n["name"] for n in pre["nodes"])
    assert "合同" in names
    assert "立项" in names
    # 每个前置节点都要有 谁做/做什么/产出/交给谁
    for n in pre["nodes"]:
        assert n["roles"], f"节点「{n['name']}」缺责任角色"
        assert n["actions"], f"节点「{n['name']}」缺动作说明"
        assert n["output"], f"节点「{n['name']}」缺产出"
        assert n["handoff"], f"节点「{n['name']}」缺交接对象"


def test_flow_contains_all_hardware_phases_with_gates(client):
    """硬件流程应包含 P0-PP5 六个阶段,前五个各带门禁。"""
    h = auth_headers(client, "tp_user2", "member")
    data = _flow(client, h, "hardware")

    phases = [s for s in data["stages"] if s["kind"] == "phase"]
    assert [p["key"] for p in phases] == ["P0", "PP1", "PP2", "PP3", "PP4", "PP5"]

    for p in phases[:5]:
        assert p["gate"], f"{p['key']} 应有出口门禁"
        assert p["gate"]["code"].startswith("G")
    # PP5 无门禁
    assert phases[5]["gate"] is None


def test_flow_deliverables_have_roles_and_templates(client):
    """交付物要带责任角色:数据库已填的透出,留空的由兜底表补齐。"""
    _ensure_standards()
    h = auth_headers(client, "tp_user3", "member")
    data = _flow(client, h, "hardware")

    by_key = {s["key"]: s for s in data["stages"] if s["kind"] == "phase"}

    # 数据库已填 responsible_role → 原样透出
    pp1 = by_key["PP1"]["deliverables"]
    struct = next(d for d in pp1 if d["name"] == "结构方案设计报告")
    assert struct["role"] == "结构工程师"
    assert struct["required"] is True
    assert struct["criteria"] == "测试用验收要点"

    # responsible_role 为空 → ROLE_FALLBACK 补出「测试工程师」
    pp3 = by_key["PP3"]["deliverables"]
    verify = next(d for d in pp3 if d["name"] == "样机验证方案")
    assert verify["role"] == "测试工程师", "留空责任角色应由兜底表补齐"

    # 有交付物的阶段都必须推导出涉及角色(供前端岗位筛选)
    for key in ("PP1", "PP3"):
        assert by_key[key]["roles"], f"{key} 未推导出涉及角色"


def test_flow_phase_roles_cover_key_positions(client):
    """岗位筛选要可用:关键岗位应能在流程中被找到。"""
    _ensure_standards()
    h = auth_headers(client, "tp_user4", "member")
    data = _flow(client, h, "hardware")

    roles = data["roles"]
    for expect in ["商务经理", "项目经理", "测试工程师", "结构工程师"]:
        assert expect in roles, f"角色列表缺少 {expect}"

    # 这些岗位必须真的能在某个阶段被匹配到
    seen = {r for s in data["stages"] for r in s["roles"]}
    for expect in ["商务经理", "项目经理", "测试工程师"]:
        assert expect in seen, f"{expect} 未出现在任何阶段"


def test_flow_software_project_type(client):
    """软件项目走 S0-S3,且不与硬件阶段串台。"""
    h = auth_headers(client, "tp_user5", "member")
    data = _flow(client, h, "software")

    phases = [s for s in data["stages"] if s["kind"] == "phase"]
    assert [p["key"] for p in phases] == ["S0", "S1", "S2", "S3"]
    for p in phases:
        assert p["gate"], f"{p['key']} 应有出口门禁"


def test_flow_nodes_declare_venue(client):
    """每个前置/收尾节点都要说清「在哪办」,且审批类节点必须归到钉钉。

    业务事实:合同审批、立项审批、需求审批都在钉钉办公平台,
    本平台不做这些审批,只做阶段门把关。配置若把这些节点标成本平台,
    员工会以为在平台上走审批,因此这里逐节点断言。
    """
    h = auth_headers(client, "tp_user7", "member")
    data = _flow(client, h)

    allowed = {"钉钉", "本平台", "线下"}
    nodes = [n for s in data["stages"] if s["kind"] in ("pre", "post") for n in s["nodes"]]
    assert nodes, "应有前置/收尾节点"
    for n in nodes:
        assert n.get("venue") in allowed, f"节点「{n['name']}」的 venue 非法: {n.get('venue')}"

    by_name = {n["name"]: n for n in nodes}

    # 审批类节点:在钉钉,且平台落点要写明平台不做该审批
    for name in ("合同评审与签订", "发起立项申请", "立项审批"):
        n = by_name[name]
        assert n["venue"] == "钉钉", f"「{name}」应在钉钉办理,实际 {n['venue']}"
        assert "钉钉" in n["module"], f"「{name}」的平台落点应注明审批在钉钉,实际 {n['module']}"

    # 交接点:建项目/组建项目组 在本平台,且要点明这是钉钉→平台的唯一交接点
    join = next(n for n in nodes if "建项目" in n["name"])
    assert join["venue"] == "本平台"
    assert "团队" in join["module"]

    # 项目分级已取消:流程里不应再出现「立项审查与分级」或 A/B/C 措辞
    assert "立项审查与分级" not in by_name, "分级节点应已取消"
    blob = " ".join(n["name"] + n["actions"] + n["output"] + n["tip"] for n in nodes)
    for kw in ("分级", "A 级", "B 级", "C 级"):
        assert kw not in blob, f"取消分级后流程里仍有残留: {kw}"


def test_flow_notes_explain_dingtalk_boundary(client):
    """顶部说明必须把「钉钉审批 / 平台门禁」的分工讲清楚。"""
    h = auth_headers(client, "tp_user8", "member")
    data = _flow(client, h)

    notes = data["notes"]
    assert len(notes) >= 3, "平台边界说明过少"
    blob = "".join(notes)
    for kw in ("钉钉", "阶段门", "交付物", "交接点"):
        assert kw in blob, f"边界说明缺少关键点: {kw}"


def test_flow_rejects_unknown_project_type(client):
    h = auth_headers(client, "tp_user6", "member")
    resp = client.get("/api/training/process-flow",
                      params={"project_type": "bogus"}, headers=h)
    assert resp.status_code == 422


def test_flow_requires_auth(client):
    resp = client.get("/api/training/process-flow")
    assert resp.status_code in (401, 403)
