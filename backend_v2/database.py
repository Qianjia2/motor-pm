"""Synchronous SQLAlchemy 2.0 database setup."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from backend_v2.config import settings

# Convert async db URL to sync: sqlite+aiosqlite -> sqlite
sync_url = settings.DATABASE_URL.replace("+aiosqlite", "")

engine = create_engine(sync_url, echo=False, pool_size=5, max_overflow=10, pool_recycle=3600)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency: yield database session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Create all tables (dev convenience)."""
    import backend_v2.models  # noqa: F401  确保所有模型注册进 metadata,新表才能被 create_all 创建
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _seed_hardware_phases()
    _seed_software_phases()


def _ensure_columns():
    """SQLite 无自动列迁移:轻量补列,已存在则跳过。"""
    from sqlalchemy import text
    with engine.begin() as conn:
        for table, col, ddl in [
            ("gate_deliverable_standard", "template_path", "VARCHAR(512)"),
            ("client_communication", "images", "TEXT"),
            ("client_communication", "project_id", "INTEGER"),
            ("phase", "project_type", "VARCHAR(16) DEFAULT 'hardware'"),
            ("project", "project_type", "VARCHAR(16) DEFAULT 'hardware'"),
            ("project", "contract_amount_manual", "BOOLEAN DEFAULT 0"),
            ("change_request", "attachment_path", "VARCHAR(512)"),
            ("change_request", "attachment_name", "VARCHAR(256)"),
            ("change_request", "attachment_size", "INTEGER"),
            ("project_phase_gate", "signoff_initiated_by", "VARCHAR(64)"),
            ("user_auth", "kb_admin", "BOOLEAN DEFAULT 0"),
            ("training_task", "required_target", "VARCHAR(64)"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
            except Exception:
                pass


def _seed_hardware_phases():
    """幂等插入硬件(电机+控制器)项目的阶段与门。

    老库由 backend_v2/seed.py 一次性建过;这里补齐是为了让全新部署
    (以及测试用的临时库)不出现"硬件流程为空"的情况。
    """
    from sqlalchemy import text
    phases = [
        # name, code, sort_order, description
        ("概念需求阶段", "P0", 1, "需求分析、技术方案概念设计，门径G1"),
        ("方案设计阶段", "PP1", 2, "详细方案设计、仿真分析，门径G2"),
        ("样机试制阶段", "PP2", 3, "工程图纸、BOM、工艺设计、零部件加工、样机装配，门径G3"),
        ("验证阶段", "PP3", 4, "台架测试、DV/PV验证，门径G4"),
        ("设计定型阶段", "PP4", 5, "设计冻结、生产移交、项目结题，门径G5"),
        ("售后维护阶段", "PP5", 6, "量产支持、售后维护"),
    ]
    gates = [
        # name, code, sort_order, phase_code
        ("G1 概念评审", "G1", 1, "P0"),
        ("G2 方案评审", "G2", 2, "PP1"),
        ("G3 试制评审", "G3", 3, "PP2"),
        ("G4 验证评审", "G4", 4, "PP3"),
        ("G5 定型评审", "G5", 5, "PP4"),
    ]
    with engine.begin() as conn:
        # 阶段:按 code 去重,已存在则补 project_type(老库可能没有)
        for name, code, sort, desc in phases:
            row = conn.execute(text("SELECT id FROM phase WHERE code = :c"), {"c": code}).fetchone()
            if row:
                conn.execute(text("UPDATE phase SET project_type='hardware' WHERE code = :c"), {"c": code})
            else:
                conn.execute(text(
                    "INSERT INTO phase (name, code, sort_order, description, project_type) "
                    "VALUES (:n, :c, :s, :d, 'hardware')"
                ), {"n": name, "c": code, "s": sort, "d": desc})
        # 门:按 code 去重
        for name, code, sort, phase_code in gates:
            exists = conn.execute(text("SELECT id FROM gate WHERE code = :c"), {"c": code}).fetchone()
            if exists:
                continue
            pid = conn.execute(text("SELECT id FROM phase WHERE code = :c"), {"c": phase_code}).fetchone()
            if pid:
                conn.execute(text(
                    "INSERT INTO gate (name, code, sort_order, phase_id) VALUES (:n, :c, :s, :p)"
                ), {"n": name, "c": code, "s": sort, "p": pid[0]})
        _seed_hardware_standards(conn)


def _seed_hardware_standards(conn):
    """硬件项目交付物标准(P0-PP5),逐字照抄现网库的 38 行。

    为什么之前没有这个函数:硬件标准一直只存在于现网库,老库由 backend_v2/seed.py
    一次性建过。但 workflow_map.WORKFLOW_NODE_STANDARDS 的测试是拿这份定义当权威
    清单去比对映射的(AST 读它,不执行),缺了它硬件映射就没法被覆盖性断言管住。

    照抄而不是重写文案:现网那 38 条是业务上跑着的,文案必须一致,否则新环境建出来
    的和现网就是两套标准。对现网零影响——按 (phase_id, name) 去重,38 条全部命中
    已存在行,一条都不会插。
    """
    from sqlalchemy import text
    standards = [
        # phase_code, name, category, required, description, acceptance_criteria, responsible_role, sort_order
        # ── P0 概念需求阶段 ──
        ("P0", "项目开发合同", "document", 1, "与客户签订的项目开发合同，明确产品技术范围、交付物与节点计划、商务条款、知识产权归属及违约责任",
         "双方签字盖章生效，扫描件归档；技术附件（技术协议/规格书）随合同签署并覆盖全部关键指标；里程碑与交付物清单明确无歧义；无未决商务条款（付款、交付周期、质保）", "商务经理 + 项目经理", 0),
        ("P0", "客户技术协议/SOR", "approval", 1, "客户签署的技术规范确认书（Statement of Requirements）",
         "客户签字确认，关键指标无TBD项", "项目经理+商务经理", 1),
        ("P0", "产品需求规格书（PRD冻结版）", "document", 1, "完整性能指标、环境适应性、EMC要求、安全要求、寿命要求、接口协议",
         "所有性能指标有明确数值和验证方法，客户确认签字", "项目经理", 2),
        ("P0", "市场调研报告", "report", 0, "竞品分析、目标市场与规模、价格定位,论证产品立项价值",
         "调研数据标注来源与日期可核查,竞品与市场规模数据完整,结论明确支持立项决策,经评审确认", "", 2),
        ("P0", "立项申请书", "approval", 1, "项目背景、目标、范围、资源需求与成本预算,提交管理层审批立项",
         "预算与资源需求经评审核准,管理层审批签字,无未决立项条件", None, 3),
        ("P0", "技术可行性分析", "report", 0, "关键技术点与实现路径评估,识别技术与供应风险",
         "关键技术均有备选方案,风险清单评级完整,可行性结论经技术评审签字", "", 4),
        ("P0", "需求评审记录", "document", 1, "评审会议结论、遗留问题清单与关闭计划",
         "评审结论明确，遗留问题均有责任人、期限与关闭状态", "项目经理", 7),
        # ── PP1 方案设计阶段 ──
        ("PP1", "项目设计与开发计划书", "document", 1, "里程碑计划、资源计划、初步风险清单与应对措施",
         "里程碑可量化可跟踪,资源安排与计划匹配,经项目组与干系人评审确认", "", 0),
        ("PP1", "系统架构设计方案", "document", 0, "电机拓扑选型、控制策略框架、系统功能分解",
         "明确电机类型、控制方案、功能模块划分", "项目经理 + 各专业", 1),
        ("PP1", "电磁方案设计报告", "report", 1, "电机电磁计算书:极槽配合、绕组方案、磁路与性能仿真",
         "仿真结果满足性能指标且有校核依据,计算书版本受控,经设计评审通过", "", 2),
        ("PP1", "结构方案设计报告", "document", 1, "总装图与关键结构尺寸,散热/防护/安装接口设计",
         "关键尺寸与接口满足需求规格书要求,结构评审通过,无未关闭问题", "", 3),
        ("PP1", "系统原理图与框图", "document", 1, "电气原理图、系统框图,控制接口定义",
         "图纸与框图版本一致可追溯,接口定义经评审确认,设计评审无重大遗留", None, 4),
        ("PP1", "关键器件选型报告", "report", 0, "轴承、磁钢、绝缘材料、控制器等关键器件的选型与供应商评估",
         "关键器件均有2家以上供应商对比,样品验证完成,采购周期满足项目节点", "", 5),
        ("PP1", "设计风险评估", "report", 0, "方案级技术风险识别与缓解措施(可复用FMEA)",
         "风险识别覆盖主要技术点,高风险项均有缓解措施与责任人,评审通过", "", 6),
        ("PP1", "成本估算表", "report", 0, "基于BOM的物料成本估算与目标成本对比",
         "估算与目标成本偏差≤10%,超限项已有降本措施并落实责任人", "", 7),
        ("PP1", "设计方案评审记录", "approval", 1, "评审会议结论、遗留问题清单与关闭计划",
         "评审结论明确,遗留问题均有责任人、期限与关闭状态", None, 8),
        # ── PP2 样机试制阶段 ──
        ("PP2", "样机试制方案", "document", 1, "试制数量、批次与时间节点安排",
         "试制节点满足整体进度,资源与产能已确认,计划经批准发布", "", 1),
        ("PP2", "工艺方案", "report", 0, "绕组/装配/接线等关键工艺方案与工装需求",
         "关键工序工艺参数明确,工装到位计划满足试制节点,工艺评审通过", "", 2),
        ("PP2", "外购件清单", "document", 0, "外购零部件与材料明细、采购到位计划",
         "清单与BOM一致无遗漏,关键件交期已确认,到位计划满足试制节点", "", 3),
        ("PP2", "试制过程记录", "document", 0, "试制过程问题记录、异常处理与纠正措施",
         "异常均有记录与处理结论,纠正措施验证有效,记录完整可追溯", "", 5),
        ("PP2", "样机试制总结报告", "report", 1, "试制完成情况、合格率统计与遗留问题",
         "合格率达到计划目标,遗留问题有处理计划与责任人,报告经评审", None, 6),
        # ── PP3 验证阶段 ──
        ("PP3", "样机验证方案", "document", 1, "试制样机的检验项目、方法与判定标准",
         "检验项目覆盖关键性能与安全项,判定标准量化明确,方案经批准", "", 0),
        ("PP3", "型式试验报告", "report", 1, "性能测试(GB/T/企业标准):空载/负载/效率/温升等",
         "试验按标准方法执行,测试记录与报告数据一致,结果全部合格", None, 1),
        ("PP3", "可靠性试验报告", "report", 1, "寿命、耐久、振动冲击等可靠性验证结果",
         "试验样品与时长满足计划要求,结果达到设计寿命目标,失效件已分析", None, 2),
        ("PP3", "环境适应性试验报告", "report", 0, "高低温、湿度、盐雾、防护等级等环境试验",
         "试验条件符合产品环境等级,结果满足要求,超标项已整改复测", "", 3),
        ("PP3", "EMC测试报告", "report", 0, "电磁兼容测试(传导/辐射发射与抗扰度)结果",
         "发射与抗扰度全部通过,超标项整改后复测合格,报告有效", "", 4),
        ("PP3", "安规与认证资料", "approval", 0, "CE/UL/CCC等认证申请或合规性评估文件",
         "认证申请已受理或证书已取得,合规性评估结论明确", "", 5),
        ("PP3", "客户送样反馈", "document", 0, "客户对样机的测试评价与整改要求",
         "客户书面反馈已回收归档,整改要求逐项落实并验证", "", 6),
        ("PP3", "问题整改闭环记录", "document", 1, "测试与客户反馈问题的整改措施及关闭状态",
         "全部问题关闭或给出批准延期,整改措施经验证有效", None, 7),
        # ── PP4 设计定型阶段 ──
        ("PP4", "设计定型评审报告", "report", 1, "定型评审总体结论与批准意见",
         "评审结论为同意定型并签字,遗留问题关闭或获豁免批准", None, 1),
        ("PP4", "全套设计图纸定版", "document", 1, "产品与零部件图纸定版归档",
         "图纸齐全无缺漏,版本受控,经批准签字并完成归档", None, 2),
        ("PP4", "BOM清单定版", "document", 1, "物料清单定版(编码/版本/替代料)",
         "物料编码唯一,与定版图纸一致,替代料经批准,已归档受控", None, 3),
        ("PP4", "作业指导书", "document", 0, "装配/检验/包装作业指导书",
         "工序覆盖无遗漏,参数明确可操作,相关人员完成培训并确认", "", 5),
        ("PP4", "工程变更闭环记录", "approval", 1, "定型前ECN变更的批准与实施关闭情况",
         "ECN全部批准并实施,变更影响评估完成,无未关闭变更", None, 6),
        ("PP4", "产品规格书定版", "document", 0, "对外发布的产品规格书正式版本",
         "参数与型式试验实测一致,经审批发布并下发相关部门", "", 7),
        # ── PP5 售后维护阶段 ──
        ("PP5", "售后问题统计报告", "report", 0, "市场反馈故障类型、频次与趋势统计",
         "统计周期内数据完整,主要故障已定位原因,改进措施已立项", "", 1),
        ("PP5", "项目总结报告", "report", 1, "项目全过程总结:目标达成、经验教训、绩效评价",
         "目标达成有数据支撑,经验教训可复用,绩效评价完成,经评审", None, 4),
        ("PP5", "持续改进计划", "document", 0, "后续改进方向与行动计划",
         "改进项有量化目标与时限,责任明确,经评审确认实施", None, 5),
    ]
    for phase_code, name, cat, required, desc, crit, role, sort in standards:
        pid = conn.execute(text("SELECT id FROM phase WHERE code = :c"), {"c": phase_code}).fetchone()
        if not pid:
            continue
        exists = conn.execute(text(
            "SELECT id FROM gate_deliverable_standard WHERE phase_id = :p AND name = :n"
        ), {"p": pid[0], "n": name}).fetchone()
        if exists:
            continue
        conn.execute(text(
            "INSERT INTO gate_deliverable_standard "
            "(phase_id, name, category, required, description, acceptance_criteria, responsible_role, sort_order, is_active) "
            "VALUES (:p, :n, :c, :r, :d, :a, :o, :s, 1)"
        ), {"p": pid[0], "n": name, "c": cat, "r": required, "d": desc, "a": crit, "o": role, "s": sort})


def _seed_software_phases():
    """幂等插入软件研发项目的阶段与门(电机仿真设计软件纯开发,无样机试制)。"""
    from sqlalchemy import text
    phases = [
        # name, code, sort_order, description
        ("需求分析阶段", "S0", 101, "需求调研/需求评审/开发合同"),
        ("软件开发阶段", "S1", 102, "架构设计/接口定义/模块开发/单元测试"),
        ("测试验证阶段", "S2", 103, "集成测试/性能测试/验收测试"),
        ("发布交付阶段", "S3", 104, "版本发布/部署交付/验收归档"),
    ]
    gates = [
        # name, code, sort_order, phase_code
        ("S0 需求评审", "G-S0", 101, "S0"),
        ("S1 开发完成", "G-S1", 102, "S1"),
        ("S2 测试完成", "G-S2", 103, "S2"),
        ("S3 发布交付", "G-S3", 104, "S3"),
    ]
    with engine.begin() as conn:
        # 阶段:按 code 去重,已存在则补 project_type(老库可能没有)
        for name, code, sort, desc in phases:
            row = conn.execute(text("SELECT id FROM phase WHERE code = :c"), {"c": code}).fetchone()
            if row:
                conn.execute(text("UPDATE phase SET project_type='software' WHERE code = :c"), {"c": code})
            else:
                conn.execute(text(
                    "INSERT INTO phase (name, code, sort_order, description, project_type) "
                    "VALUES (:n, :c, :s, :d, 'software')"
                ), {"n": name, "c": code, "s": sort, "d": desc})
        # 门:按 code 去重
        for name, code, sort, phase_code in gates:
            exists = conn.execute(text("SELECT id FROM gate WHERE code = :c"), {"c": code}).fetchone()
            if exists:
                continue
            pid = conn.execute(text("SELECT id FROM phase WHERE code = :c"), {"c": phase_code}).fetchone()
            if pid:
                conn.execute(text(
                    "INSERT INTO gate (name, code, sort_order, phase_id) VALUES (:n, :c, :s, :p)"
                ), {"n": name, "c": code, "s": sort, "p": pid[0]})
        _seed_software_standards(conn)


def _seed_software_standards(conn):
    """软件研发项目交付物标准(S0-S3),与硬件项目一样逐阶段定义文档、解释与通过标准。"""
    from sqlalchemy import text
    standards = [
        # phase_code, name, category, required, description, acceptance_criteria, responsible_role, sort_order
        # ── S0 需求分析 ──
        ("S0", "项目开发合同", "document", 1, "双方签字盖章生效，扫描件归档；技术附件（技术协议/功能清单）随合同签署并覆盖全部功能与验收条款",
         "合同条款明确验收方式与付款节点，双方盖章签字，扫描件归档可查", "商务经理 + 项目经理", 1),
        ("S0", "软件需求规格说明书（SRS冻结版）", "document", 1, "覆盖全部功能需求与性能指标（仿真精度、计算速度、支持模型类型等），包含验收条款",
         "所有性能指标有明确数值和验证方法，客户确认签字", "项目经理+商务经理", 2),
        ("S0", "软件需求分析文档", "document", 1, "研发内部根据商务提供的软件需求规格说明书（SRS）整理成内部开发需求文档，作为架构设计与编码的直接输入",
         "内部开发需求与 SRS 逐条对应无遗漏，无 TBD 项，经技术评审确认可指导开发", "项目经理 + 软件工程师", 3),
        ("S0", "需求调研报告", "report", 0, "调研数据标注来源与日期可核查，用户需求完整，结论明确支持立项决策，经评审通过",
         "调研数据来源可核查，用户需求完整，结论支持立项", "", 4),
        ("S0", "立项申请书", "approval", 1, "预算与资源需求经评审核准，管理层审批签字，无未决立项条件",
         "预算与资源经评审批准，管理层签字，无未决立项条件", "", 5),
        ("S0", "技术可行性分析", "report", 0, "关键技术均有备选方案，风险清单评级完整，可行性结论经技术评审签字",
         "关键技术有备选方案，风险清单完整，结论经评审", "", 6),
        ("S0", "功能清单与验收条款", "approval", 0, "客户确认功能范围，验收条款覆盖全部交付内容",
         "客户签字确认功能范围，关键条款无TBD项", "项目经理", 7),
        ("S0", "需求评审记录", "document", 1, "评审结论明确，遗留问题均有责任人、期限与关闭状态",
         "评审结论明确，遗留问题有责任人/期限/关闭状态", "项目经理", 8),
        # ── S1 软件开发(架构设计 + 开发编码合并) ──
        ("S1", "项目开发计划书", "document", 0, "里程碑可量化可跟踪，资源安排与计划匹配，经项目组与干系人评审确认",
         "里程碑可量化，资源匹配，经评审确认", "", 1),
        ("S1", "软件架构设计文档（SAD）", "document", 1, "明确模块划分、技术栈、性能架构与扩展性设计",
         "模块划分与技术选型明确，架构评审通过，无未关闭问题", "项目经理", 2),
        ("S1", "软件设计说明书", "document", 1, "在架构设计基础上细化到模块级设计，含模块职责、接口、数据结构与关键流程",
         "模块级设计覆盖全部功能点，接口与数据结构定义明确，经设计评审通过", "软件工程师", 3),
        ("S1", "技术选型报告", "report", 0, "关键技术均有候选方案对比与评估数据，选型依据充分",
         "候选方案对比数据完整，选型依据充分，经设计评审通过", "", 4),
        ("S1", "接口设计文档（API/数据字典）", "document", 0, "内外接口定义完整，数据字典覆盖全部数据结构",
         "接口定义完整一致可追溯，评审确认无重大遗留", "", 5),
        ("S1", "数据库/数据模型设计", "document", 0, "数据模型满足需求，容量与性能满足要求",
         "数据模型评审通过，性能满足需求", "", 6),
        ("S1", "设计风险评估", "report", 0, "风险识别覆盖主要技术点，高风险项均有缓解措施与责任人",
         "高风险项有缓解措施与责任人，评审通过", "", 7),
        ("S1", "成本估算表", "report", 0, "估算与目标成本偏差≤10%，超限项已有降本措施并落实责任人",
         "估算偏差≤10%，超限项有降本措施", "", 8),
        ("S1", "架构评审记录", "approval", 1, "评审结论明确，遗留问题均有责任人、期限与关闭状态",
         "评审结论明确，遗留问题闭环", "", 9),
        ("S1", "代码版本管理", "document", 1, "分支与标签规范执行，版本可追溯可回滚",
         "版本管理规范执行，可追溯回滚", "软件工程师", 10),
        ("S1", "开发迭代计划", "document", 1, "迭代安排满足整体进度，任务拆分可跟踪，计划经批准发布",
         "迭代节点满足整体进度，任务拆分可跟踪，计划经批准", "", 11),
        ("S1", "单元测试报告", "report", 1, "核心模块覆盖率达标（≥80%），用例全部通过，测试记录完整",
         "覆盖率达标，用例通过，记录完整可追溯", "", 12),
        ("S1", "代码评审记录", "approval", 1, "评审覆盖全部关键模块，问题全部关闭或给出批准延期",
         "关键模块全覆盖，问题关闭或批准延期", "", 13),
        ("S1", "开发进度周报", "report", 0, "进度数据与计划一致可核查，偏差有说明与纠偏措施",
         "进度可核查，偏差有纠偏措施", "", 14),
        ("S1", "软件包提测说明", "document", 1, "提交测试时说明本次提测的软件包版本、功能范围、已知问题与测试环境要求",
         "提测版本可追溯、功能范围与已知问题列全，测试环境要求明确，经测试负责人确认接收", "软件工程师 + 测试工程师", 15),
        # ── S2 测试验证 ──
        ("S2", "软件测试计划", "document", 1, "测试项覆盖需求全部功能与性能指标，判定标准量化明确，方案经批准",
         "覆盖全部功能与性能项，判定标准量化，经批准", "", 1),
        ("S2", "集成测试报告", "report", 1, "模块集成无阻塞缺陷，测试记录与报告数据一致，结果合格",
         "集成无阻塞缺陷，记录与报告一致", "", 2),
        ("S2", "性能测试报告", "report", 0, "性能指标（仿真精度/计算速度/内存占用）达到需求规格书要求",
         "性能指标达到SRS要求，报告有效", "", 3),
        ("S2", "软件测试报告", "report", 1, "汇总本轮全部测试执行结果，含测试范围、用例执行统计、缺陷分布与结论",
         "测试范围覆盖 SRS 全部功能与性能指标，结论明确，遗留问题有责任人、期限与关闭状态", "测试工程师", 4),
        ("S2", "缺陷跟踪记录", "document", 1, "缺陷全部关闭或批准延期，修复后回归验证有效",
         "缺陷关闭或批准延期，回归验证有效", "", 5),
        ("S2", "用户验收测试（UAT）报告", "report", 1, "客户验收通过，遗留问题有处理计划与责任人",
         "客户验收通过，遗留问题有处理计划与责任人", "", 6),
        ("S2", "问题整改闭环记录", "document", 1, "全部问题关闭或给出批准延期，整改措施经验证有效",
         "问题全部闭环，整改措施验证有效", "", 7),
        ("S2", "客户试用反馈", "document", 0, "客户试用反馈已回收归档，整改要求逐项落实并验证",
         "反馈归档，整改要求逐项落实", "", 8),
        # ── S3 发布交付 ──
        ("S3", "发布评审记录", "approval", 1, "发布就绪评估完成，遗留问题风险可控，评审结论同意发布",
         "发布就绪评估完成，风险可控，结论同意发布", "", 1),
        ("S3", "版本发布说明（Release Notes）", "document", 1, "功能清单、已知问题、环境要求完整，与实际版本一致",
         "发布说明与实际版本一致，内容完整", "", 2),
        ("S3", "部署与安装手册", "document", 0, "部署步骤可操作无遗漏，环境要求明确，现场验证通过",
         "步骤可操作，环境要求明确，验证通过", "", 3),
        ("S3", "用户操作手册", "document", 1, "覆盖全部功能模块，与实际版本一致，经评审发布",
         "覆盖全部功能，与版本一致，经评审", "", 4),
        ("S3", "用户定制功能文档", "document", 1, "记录本项目为客户定制开发的功能说明、使用方式与配置方法，随版本交付",
         "定制功能逐项说明与实际版本一致，客户可据此独立使用与配置，经评审发布", "软件工程师", 5),
        ("S3", "客户培训记录", "document", 1, "客户培训的签到、培训内容、培训人与客户确认记录，作为交付完成的凭据之一",
         "培训内容覆盖全部交付功能，客户签到与确认签字齐全，记录归档可查", "项目经理 + 软件工程师", 6),
        ("S3", "技术文档归档", "document", 1, "归档清单与文件一一对应，版本正确，可随时检索调阅",
         "归档与清单一致，版本正确，可检索", "", 7),
        ("S3", "项目总结报告", "report", 1, "目标达成有数据支撑，经验教训可复用，绩效评价完成，经评审",
         "目标达成有数据支撑，经验教训可复用，经评审", "", 8),
        ("S3", "验收记录", "approval", 1, "客户签字确认验收，验收条款逐项关闭",
         "客户签字确认，验收条款逐项关闭", "项目经理", 9),
    ]
    for phase_code, name, cat, required, desc, crit, role, sort in standards:
        pid = conn.execute(text("SELECT id FROM phase WHERE code = :c"), {"c": phase_code}).fetchone()
        if not pid:
            continue
        exists = conn.execute(text(
            "SELECT id FROM gate_deliverable_standard WHERE phase_id = :p AND name = :n"
        ), {"p": pid[0], "n": name}).fetchone()
        if exists:
            continue
        conn.execute(text(
            "INSERT INTO gate_deliverable_standard "
            "(phase_id, name, category, required, description, acceptance_criteria, responsible_role, sort_order, is_active) "
            "VALUES (:p, :n, :c, :r, :d, :a, :o, :s, 1)"
        ), {"p": pid[0], "n": name, "c": cat, "r": required, "d": desc, "a": crit, "o": role, "s": sort})
