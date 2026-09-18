"""工作流步骤 → 阶段交付物标准的显式对应关系(软件 S0-S3 全线 + 硬件 P0-PP5)。

为什么要这张表:节点卡片的 output 文本与 gate_deliverable_standard.name 对不上
(节点写「软件需求规格说明书 SRS 冻结版」,标准是「软件需求规格说明书（SRS冻结版）」;
全角半角、多词少词都有)。项目里既有代码是靠双向子串匹配的(见 gate_reviews.py
的 checklist 与 _missing_required_deliverables),用来判断"门禁能不能过"尚可,
但用来显示"这一步做没做完"会静默显示错误状态:匹配不上就是永远未开始,
匹配过头就是交付物批了步骤还亮着。

所以这里写死对应关系,并由 tests/api/test_project_workflow.py 保证:
  1. 每个 seq 在 PHASE_NODES 里存在,且 node 名与节点名完全相等(节点改名会被抓出来);
  2. standards 里每个名字在该阶段的标准表里精确存在(标准改名会被抓出来);
  3. 映射 ∪ STANDARDS_WITHOUT_NODE == 该阶段全部有效标准,且两集合不相交
     (新增标准会让测试变红,逼人决定它归哪个步骤,而不是悄悄漏掉)。

键用 seq 而不是节点名:seq 是 PHASE_NODES 里的稳定身份,节点名是给人看的。
按阶段分组:因为 S1 和 S2 各有一条叫「单元测试报告」的标准,是不同的两条记录,
不能全局按名字查。

硬件侧(P0-PP5)按 backend_v2/database.py::_seed_hardware_standards 的定义写,
那份定义是从现网库逐字抄的,两边一致,没有下面软件那种漂移。

── 关于「库与定义不一致」(仅软件)──
本表按 backend_v2/database.py::_seed_software_standards 的定义写(那份是权威清单,
migrate_software_deliverables.py 也是用 AST 读它做迁移的)。现网 data/motor_pm_v2.db
与这份定义有 8 条对不上,成因已查明,两类性质完全不同:

  定义里有、库里没有(6 条)——用户在「标准维护」里主动停用,不是数据漂移:
    S0 需求调研报告 / S0 功能清单与验收条款 / S1 软件架构设计文档（SAD）
    S1 技术选型报告 / S1 接口设计文档（API/数据字典）/ S1 数据库/数据模型设计

  这 6 条一度被当成"库与定义漂移"来理解,其实是误读:它们被删掉后重启又会回来,
  看着像库和定义不一致。真实原因是当时删除走了硬删,而每次服务启动都会跑
  init_db() → _seed_software_phases() → _seed_software_standards(),播种按
  (phase_id, name)「查不到就插」,硬删掉的行在这一查里等于"从没存在过",于是被
  原样插回来。2026-09-11 已把删除改成软删(is_active=0),播种那句查重就能命中并
  跳过,删掉才真的留得住。这 6 条对应的步骤会如实变成「本库未配置」——即这一步不再
  有平台内置的交付物依据、退回人工确认,这正是删标准应有的语义。

  库里有、定义里没有(2 条)——老库既有的记录,与停用无关:
    S2 单元测试报告 / S3 用户验收记录

所以这里不做"库里没有就写成空映射"的处理——那会让新环境(按定义建的库)反而缺映射。
映射照定义写全,由接口在运行时用 definition_gap / configured 标出"这一步的标准在
本库中不存在"。两边要不要对齐(补齐 6 条 / 删掉 2 条)是业务决定,不在这轮试点里擅自改。
"""

# 阶段码 → {节点 seq: {"node": 节点名(漂移哨兵), "standards": [标准名, ...]}}
# 门禁节点(每阶段末位,由 _gate_node 生成)不在此表内,状态另由签核记录推导。
# standards 为空列表 = 该步骤暂无对应标准,见模块开头「定义缺口」。
WORKFLOW_NODE_STANDARDS = {
    "S0": {
        1: {"node": "需求调研与澄清", "standards": ["需求调研报告"]},
        2: {"node": "编制软件需求规格说明书(SRS)", "standards": ["软件需求规格说明书（SRS冻结版）"]},
        3: {"node": "软件需求分析文档", "standards": ["软件需求分析文档"]},
        4: {"node": "功能清单与验收条款", "standards": ["功能清单与验收条款"]},
        5: {"node": "技术可行性分析", "standards": ["技术可行性分析"]},
        6: {"node": "组织需求评审", "standards": ["需求评审记录"]},
    },
    "S1": {
        1: {"node": "软件架构设计", "standards": ["软件架构设计文档（SAD）"]},
        2: {"node": "软件设计说明书", "standards": ["软件设计说明书"]},
        # 一个步骤对多条标准:技术选型、接口设计、数据模型是同一件事的三份产出
        3: {"node": "技术选型与接口设计", "standards": [
            "技术选型报告", "接口设计文档（API/数据字典）", "数据库/数据模型设计"]},
        4: {"node": "组织架构评审", "standards": ["架构评审记录"]},
        5: {"node": "制定开发迭代计划", "standards": ["开发迭代计划"]},
        6: {"node": "编码与版本管理", "standards": ["代码版本管理"]},
        7: {"node": "代码评审", "standards": ["代码评审记录"]},
        8: {"node": "单元测试", "standards": ["单元测试报告"]},
        9: {"node": "软件包提测", "standards": ["软件包提测说明"]},
    },
    "S2": {
        1: {"node": "编制软件测试计划", "standards": ["软件测试计划"]},
        2: {"node": "集成测试", "standards": ["集成测试报告"]},
        3: {"node": "性能测试", "standards": ["性能测试报告"]},
        4: {"node": "缺陷跟踪与回归", "standards": ["缺陷跟踪记录"]},
        5: {"node": "软件测试报告", "standards": ["软件测试报告"]},
        6: {"node": "UAT 用户验收测试", "standards": ["用户验收测试（UAT）报告"]},
        7: {"node": "问题整改闭环", "standards": ["问题整改闭环记录"]},
        8: {"node": "客户试用反馈", "standards": ["客户试用反馈"]},
    },
    "S3": {
        1: {"node": "组织发布评审", "standards": ["发布评审记录"]},
        2: {"node": "版本发布说明", "standards": ["版本发布说明（Release Notes）"]},
        3: {"node": "现场部署验证", "standards": ["部署与安装手册"]},
        4: {"node": "用户定制功能文档", "standards": ["用户定制功能文档"]},
        5: {"node": "用户操作手册", "standards": ["用户操作手册"]},
        6: {"node": "客户培训", "standards": ["客户培训记录"]},
        # 客户验收会签两份记录,库里是两条标准,都挂到这一步
        7: {"node": "客户验收", "standards": ["验收记录", "用户验收记录"]},
        8: {"node": "技术文档归档", "standards": ["技术文档归档"]},
        9: {"node": "编写项目总结", "standards": ["项目总结报告"]},
    },
    # ══ 硬件(电机 + 控制器)P0-PP5 ══
    # 映射按全部硬件节点写全。WORKFLOW_OPT_IN_CODES 管的是「哪些项目能看工作流页」,
    # 不是「哪些节点有映射」——两件事,别把白名单写进映射里。
    "P0": {
        1: {"node": "需求澄清与技术协议确认", "standards": ["客户技术协议/SOR"]},
        # 节点产出写「产品需求规格书 PRD 冻结版」,标准是全角括号的
        # 「产品需求规格书（PRD冻结版）」,别按节点 output 抄
        2: {"node": "编制产品需求规格书(PRD)", "standards": ["产品需求规格书（PRD冻结版）"]},
        3: {"node": "技术可行性分析", "standards": ["技术可行性分析"]},
        4: {"node": "市场调研", "standards": ["市场调研报告"]},
        # 产出「计划基线(里程碑 / 甘特图)」,标准表里没有这一条,平台之外的事
        5: {"node": "里程碑初排与计划基线", "standards": []},
        6: {"node": "组织需求评审", "standards": ["需求评审记录"]},
    },
    "PP1": {
        1: {"node": "编制项目设计与开发计划书", "standards": ["项目设计与开发计划书"]},
        2: {"node": "系统架构设计方案", "standards": ["系统架构设计方案"]},
        3: {"node": "电磁方案设计与仿真", "standards": ["电磁方案设计报告"]},
        # 产出「结构方案设计报告 + 三维模型」,标准只管报告,模型是附带产物
        4: {"node": "结构方案设计与三维模型", "standards": ["结构方案设计报告"]},
        5: {"node": "系统原理图与框图", "standards": ["系统原理图与框图"]},
        6: {"node": "关键器件选型", "standards": ["关键器件选型报告"]},
        # 产出写「DFMEA 表」,标准名是「设计风险评估」——同一样东西两种叫法
        7: {"node": "设计风险评估(DFMEA)", "standards": ["设计风险评估"]},
        8: {"node": "成本估算", "standards": ["成本估算表"]},
        9: {"node": "组织方案评审", "standards": ["设计方案评审记录"]},
    },
    "PP2": {
        1: {"node": "编制样机试制方案", "standards": ["样机试制方案"]},
        2: {"node": "出工程图纸", "standards": []},          # 定版图纸在 PP4 才成为标准
        3: {"node": "建立 BOM", "standards": []},            # 同上,PP4 的「BOM清单定版」是另一阶段的标准
        4: {"node": "工艺方案", "standards": ["工艺方案"]},
        # 产出写「采购清单与到位计划」,标准名是「外购件清单」
        5: {"node": "外购件采购", "standards": ["外购件清单"]},
        6: {"node": "零部件加工与样机装配", "standards": []},   # 产出是实物样机,不是文档
        7: {"node": "试制过程记录", "standards": ["试制过程记录"]},
        8: {"node": "样机试制总结", "standards": ["样机试制总结报告"]},
    },
    "PP3": {
        1: {"node": "编制样机验证方案", "standards": ["样机验证方案"]},
        2: {"node": "执行型式试验", "standards": ["型式试验报告"]},
        3: {"node": "执行可靠性试验", "standards": ["可靠性试验报告"]},
        4: {"node": "执行环境适应性试验", "standards": ["环境适应性试验报告"]},
        # 产出写「EMC 测试报告」(中间有空格),标准无空格
        5: {"node": "EMC 测试", "standards": ["EMC测试报告"]},
        6: {"node": "安规与认证", "standards": ["安规与认证资料"]},
        7: {"node": "客户送样与反馈回收", "standards": ["客户送样反馈"]},
        # 与软件 S2 第 7 步同名,但是不同阶段的独立记录,不能全局按名字查
        8: {"node": "问题整改闭环", "standards": ["问题整改闭环记录"]},
        9: {"node": "组织验证评审", "standards": []},       # 产出「验证评审记录」,标准表里没有
    },
    "PP4": {
        1: {"node": "全套设计图纸定版", "standards": ["全套设计图纸定版"]},
        2: {"node": "BOM 清单定版", "standards": ["BOM清单定版"]},
        3: {"node": "产品规格书定版", "standards": ["产品规格书定版"]},
        # 产出写「作业指导书 + 培训确认记录」,标准只有作业指导书
        4: {"node": "作业指导书", "standards": ["作业指导书"]},
        5: {"node": "变更与 ECN 闭环", "standards": ["工程变更闭环记录"]},
        6: {"node": "组织定型评审", "standards": ["设计定型评审报告"]},
        7: {"node": "量产移交", "standards": []},           # 产出「移交清单 + 培训记录」,标准表里没有
    },
    "PP5": {
        1: {"node": "量产支持", "standards": []},           # 产出「问题记录与处理结论」
        2: {"node": "售后问题统计", "standards": ["售后问题统计报告"]},
        3: {"node": "编写项目总结", "standards": ["项目总结报告"]},
        4: {"node": "制定持续改进计划", "standards": ["持续改进计划"]},
        5: {"node": "项目文档归档", "standards": []},       # 产出「项目文档归档完整」,是状态不是文档
    },
}

# 不在任何步骤里产出的标准:要么由平台流程之外产生,要么产出于别的阶段。
# 这些不是"忘了映射",是明确不挂到步骤上的——界面会单列为「无对应步骤的交付物标准」,
# 不会被隐藏,也不会算进任何步骤的完成度。
STANDARDS_WITHOUT_NODE = {
    # 前置商务阶段(合同/立项)产出,见 PHASE_NODES 的 PRE_NODES
    "S0": ["项目开发合同", "立项申请书"],
    # 同上:合同与立项都在 P0 的节点开始之前就签掉了,不挂任何步骤
    "P0": ["项目开发合同", "立项申请书"],
    # PP1-PP5 无:硬件这 36 条标准全部能归到具体步骤上
    # 项目开发计划书在 PP0/前置阶段就已产出;其余为可选的过程性文档
    "S1": ["项目开发计划书", "设计风险评估", "成本估算表", "开发进度周报"],
    # 同名标准在 S1 已挂到「单元测试」步骤,S2 这条是非必交的重复项
    "S2": ["单元测试报告"],
    "S3": [],
}

# 库里比定义多出来的标准(仅现网库有,定义里没有)。列在这里是为了让测试知道
# 它们是"已知的存在",而不是映射漏了。对齐后应删掉这段。
STANDARDS_NOT_IN_SEED = {
    "S2": ["单元测试报告"],   # 与定义里的 S1 同名条目不冲突,是 S2 阶段独立的一条非必交
    "S3": ["用户验收记录"],   # 定义里 S3 客户验收只有「验收记录」一条
}


def node_standards(phase_code: str, seq: int) -> list:
    """该节点对应的标准名列表;无映射或无标准返回空列表。"""
    entry = WORKFLOW_NODE_STANDARDS.get(phase_code, {}).get(seq)
    return list(entry["standards"]) if entry else []


def expected_node_name(phase_code: str, seq: int):
    """映射里登记的节点名(用于测试比对,防止节点改名后映射悄悄失效)。"""
    entry = WORKFLOW_NODE_STANDARDS.get(phase_code, {}).get(seq)
    return entry["node"] if entry else None


def mapped_standard_names(phase_code: str) -> set:
    """该阶段所有挂在步骤上的标准名。"""
    out = set()
    for entry in WORKFLOW_NODE_STANDARDS.get(phase_code, {}).values():
        out.update(entry["standards"])
    return out


def covered_standard_names(phase_code: str) -> set:
    """映射 ∪ 白名单:该阶段定义里被显式处理过的标准名。测试用它做全覆盖断言。"""
    return mapped_standard_names(phase_code) | set(STANDARDS_WITHOUT_NODE.get(phase_code) or [])


def not_in_seed(phase_code: str, std_name: str) -> bool:
    """该标准是否属于「库里比定义多出来」的那几条。"""
    return std_name in (STANDARDS_NOT_IN_SEED.get(phase_code) or [])


# ── 哪些项目开放工作流页 ──
# 软件全线开放;硬件逐个开,目前只开金浪试点。
# 按项目编号(project.code)而不是自增 id:id 换个环境就错位了。
WORKFLOW_OPT_IN_CODES = {
    "hardware": {"JL-2025-001"},
}


def supports_workflow(project_type: str, project_code: str) -> bool:
    """该项目是否能看工作流页。

    硬件没开放的项目连页签都不该出现——挂一个点进去 supported=false 的空页,
    比没有这个页签更糟。所以判定放在这一处,接口和页签配置都问它。
    """
    if project_type == "software":
        return True
    return (project_code or "") in WORKFLOW_OPT_IN_CODES.get(project_type or "", set())
