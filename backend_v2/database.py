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
    _seed_software_phases()


def _ensure_columns():
    """SQLite 无自动列迁移:轻量补列,已存在则跳过。"""
    from sqlalchemy import text
    with engine.begin() as conn:
        for table, col, ddl in [
            ("gate_deliverable_standard", "template_path", "VARCHAR(512)"),
            ("client_communication", "images", "TEXT"),
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


def _seed_software_phases():
    """幂等插入软件研发项目的阶段与门(电机仿真设计软件纯开发,无样机试制)。"""
    from sqlalchemy import text
    phases = [
        # name, code, sort_order, description
        ("需求分析阶段", "S0", 101, "需求调研/需求评审/开发合同"),
        ("架构设计阶段", "S1", 102, "架构设计/技术选型/接口定义"),
        ("开发编码阶段", "S2", 103, "模块开发/单元测试/代码评审"),
        ("测试验证阶段", "S3", 104, "集成测试/性能测试/验收测试"),
        ("发布交付阶段", "S4", 105, "版本发布/部署交付/验收归档"),
    ]
    gates = [
        # name, code, sort_order, phase_code
        ("S0 需求评审", "G-S0", 101, "S0"),
        ("S1 架构评审", "G-S1", 102, "S1"),
        ("S2 开发完成", "G-S2", 103, "S2"),
        ("S3 测试完成", "G-S3", 104, "S3"),
        ("S4 发布交付", "G-S4", 105, "S4"),
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
    """软件研发项目交付物标准(S0-S4),与硬件项目一样逐阶段定义文档、解释与通过标准。"""
    from sqlalchemy import text
    standards = [
        # phase_code, name, category, required, description, acceptance_criteria, responsible_role, sort_order
        # ── S0 需求分析 ──
        ("S0", "项目开发合同", "document", 1, "双方签字盖章生效，扫描件归档；技术附件（技术协议/功能清单）随合同签署并覆盖全部功能与验收条款",
         "合同条款明确验收方式与付款节点，双方盖章签字，扫描件归档可查", "商务经理 + 项目经理", 1),
        ("S0", "软件需求规格说明书（SRS冻结版）", "document", 1, "覆盖全部功能需求与性能指标（仿真精度、计算速度、支持模型类型等）",
         "所有性能指标有明确数值和验证方法，客户确认签字", "项目经理+商务经理", 2),
        ("S0", "需求调研报告", "report", 0, "调研数据标注来源与日期可核查，用户需求完整，结论明确支持立项决策，经评审通过",
         "调研数据来源可核查，用户需求完整，结论支持立项", "", 3),
        ("S0", "立项申请书", "approval", 1, "预算与资源需求经评审核准，管理层审批签字，无未决立项条件",
         "预算与资源经评审批准，管理层签字，无未决立项条件", "", 4),
        ("S0", "技术可行性分析", "report", 0, "关键技术均有备选方案，风险清单评级完整，可行性结论经技术评审签字",
         "关键技术有备选方案，风险清单完整，结论经评审", "", 5),
        ("S0", "功能清单与验收条款", "approval", 0, "客户确认功能范围，验收条款覆盖全部交付内容",
         "客户签字确认功能范围，关键条款无TBD项", "项目经理", 6),
        ("S0", "需求评审记录", "document", 1, "评审结论明确，遗留问题均有责任人、期限与关闭状态",
         "评审结论明确，遗留问题有责任人/期限/关闭状态", "项目经理", 7),
        # ── S1 架构设计 ──
        ("S1", "项目开发计划书", "document", 0, "里程碑可量化可跟踪，资源安排与计划匹配，经项目组与干系人评审确认",
         "里程碑可量化，资源匹配，经评审确认", "", 1),
        ("S1", "软件架构设计文档（SAD）", "document", 1, "明确模块划分、技术栈、性能架构与扩展性设计",
         "模块划分与技术选型明确，架构评审通过，无未关闭问题", "架构师/系统工程师", 2),
        ("S1", "技术选型报告", "report", 1, "关键技术均有候选方案对比与评估数据，选型依据充分",
         "候选方案对比数据完整，选型依据充分，经设计评审通过", "", 3),
        ("S1", "接口设计文档（API/数据字典）", "document", 1, "内外接口定义完整，数据字典覆盖全部数据结构",
         "接口定义完整一致可追溯，评审确认无重大遗留", "", 4),
        ("S1", "数据库/数据模型设计", "document", 0, "数据模型满足需求，容量与性能满足要求",
         "数据模型评审通过，性能满足需求", "", 5),
        ("S1", "设计风险评估", "report", 0, "风险识别覆盖主要技术点，高风险项均有缓解措施与责任人",
         "高风险项有缓解措施与责任人，评审通过", "", 6),
        ("S1", "成本估算表", "report", 0, "估算与目标成本偏差≤10%，超限项已有降本措施并落实责任人",
         "估算偏差≤10%，超限项有降本措施", "", 7),
        ("S1", "架构评审记录", "approval", 1, "评审结论明确，遗留问题均有责任人、期限与关闭状态",
         "评审结论明确，遗留问题闭环", "", 8),
        # ── S2 开发编码 ──
        ("S2", "开发迭代计划", "document", 1, "迭代安排满足整体进度，任务拆分可跟踪，计划经批准发布",
         "迭代节点满足整体进度，任务拆分可跟踪，计划经批准", "", 1),
        ("S2", "单元测试报告", "report", 1, "核心模块覆盖率达标（≥80%），用例全部通过，测试记录完整",
         "覆盖率达标，用例通过，记录完整可追溯", "", 2),
        ("S2", "代码评审记录", "approval", 1, "评审覆盖全部关键模块，问题全部关闭或给出批准延期",
         "关键模块全覆盖，问题关闭或批准延期", "", 3),
        ("S2", "开发进度周报", "report", 0, "进度数据与计划一致可核查，偏差有说明与纠偏措施",
         "进度可核查，偏差有纠偏措施", "", 4),
        ("S2", "代码版本管理记录", "document", 0, "分支与标签规范执行，版本可追溯可回滚",
         "版本管理规范执行，可追溯回滚", "", 5),
        # ── S3 测试验证 ──
        ("S3", "测试计划", "document", 1, "测试项覆盖需求全部功能与性能指标，判定标准量化明确，方案经批准",
         "覆盖全部功能与性能项，判定标准量化，经批准", "", 1),
        ("S3", "集成测试报告", "report", 1, "模块集成无阻塞缺陷，测试记录与报告数据一致，结果合格",
         "集成无阻塞缺陷，记录与报告一致", "", 2),
        ("S3", "性能测试报告", "report", 1, "性能指标（仿真精度/计算速度/内存占用）达到需求规格书要求",
         "性能指标达到SRS要求，报告有效", "", 3),
        ("S3", "缺陷跟踪记录", "document", 1, "缺陷全部关闭或批准延期，修复后回归验证有效",
         "缺陷关闭或批准延期，回归验证有效", "", 4),
        ("S3", "用户验收测试（UAT）报告", "report", 1, "客户验收通过，遗留问题有处理计划与责任人",
         "客户验收通过，遗留问题有处理计划与责任人", "", 5),
        ("S3", "问题整改闭环记录", "document", 1, "全部问题关闭或给出批准延期，整改措施经验证有效",
         "问题全部闭环，整改措施验证有效", "", 6),
        ("S3", "客户试用反馈", "document", 0, "客户试用反馈已回收归档，整改要求逐项落实并验证",
         "反馈归档，整改要求逐项落实", "", 7),
        # ── S4 发布交付 ──
        ("S4", "发布评审记录", "approval", 1, "发布就绪评估完成，遗留问题风险可控，评审结论同意发布",
         "发布就绪评估完成，风险可控，结论同意发布", "", 1),
        ("S4", "版本发布说明（Release Notes）", "document", 1, "功能清单、已知问题、环境要求完整，与实际版本一致",
         "发布说明与实际版本一致，内容完整", "", 2),
        ("S4", "部署与安装手册", "document", 1, "部署步骤可操作无遗漏，环境要求明确，现场验证通过",
         "步骤可操作，环境要求明确，验证通过", "", 3),
        ("S4", "用户操作手册", "document", 1, "覆盖全部功能模块，与实际版本一致，经评审发布",
         "覆盖全部功能，与版本一致，经评审", "", 4),
        ("S4", "技术文档归档", "document", 1, "归档清单与文件一一对应，版本正确，可随时检索调阅",
         "归档与清单一致，版本正确，可检索", "", 5),
        ("S4", "项目总结报告", "report", 1, "目标达成有数据支撑，经验教训可复用，绩效评价完成，经评审",
         "目标达成有数据支撑，经验教训可复用，经评审", "", 6),
        ("S4", "验收记录", "approval", 1, "客户签字确认验收，验收条款逐项关闭",
         "客户签字确认，验收条款逐项关闭", "项目经理", 7),
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
