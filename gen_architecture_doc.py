"""Generate the comprehensive architecture design document for Motor PM System v2.0 (FastAPI + PostgreSQL)."""
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from datetime import date
import os

doc = Document()

# ── Styles ──────────────────────────────────────────
style = doc.styles['Normal']
style.font.name = '微软雅黑'
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')

for level in range(1, 4):
    hs = doc.styles[f'Heading {level}']
    hs.font.name = '微软雅黑'
    hs.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    hs.font.color.rgb = RGBColor(0x1D, 0x4E, 0xD8)

def add_table(doc, headers, rows, col_widths=None):
    """Add a styled table."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Light Grid Accent 1'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Header
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.bold = True
                run.font.size = Pt(9)
    # Body
    for r, row in enumerate(rows, 1):
        for c, val in enumerate(row):
            cell = table.rows[r].cells[c]
            cell.text = str(val) if val is not None else '-'
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return table

def code_block(doc, text):
    """Add a code block paragraph."""
    p = doc.add_paragraph()
    p.style = doc.styles['Normal']
    run = p.add_run(text)
    run.font.name = 'Consolas'
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    return p

# ════════════════════════════════════════════════════
# 封面
# ════════════════════════════════════════════════════
doc.add_paragraph()
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('电机系统设计项目管理工具')
run.font.size = Pt(28)
run.font.color.rgb = RGBColor(0x1D, 0x4E, 0xD8)
run.bold = True

subtitle = doc.add_paragraph()
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = subtitle.add_run('架构设计说明书 v2.0')
run.font.size = Pt(18)
run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = meta.add_run(f'技术栈：FastAPI + PostgreSQL + SQLAlchemy 2.0 + Vue 3 + Element Plus\n'
                    f'业务领域：电机设计 · 电机控制器设计 · 样机制造 · 样机试验\n'
                    f'文档日期：{date.today().isoformat()}')
run.font.size = Pt(10)
run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

doc.add_page_break()

# ════════════════════════════════════════════════════
# 目录
# ════════════════════════════════════════════════════
doc.add_heading('目  录', level=1)
toc_items = [
    ('1', '项目背景与技术选型'),
    ('2', '数据模型设计'),
    ('  2.1', 'ER 实体关系总览'),
    ('  2.2', '字典/参考数据表 (4张)'),
    ('  2.3', '核心业务表 (10张)'),
    ('  2.4', '认证与审计表 (2张)'),
    ('  2.5', '索引策略 — 完整 DDL'),
    ('3', 'API 接口设计 (RESTful)'),
    ('  3.1', '认证模块 /api/auth'),
    ('  3.2', '项目管理 /api/projects'),
    ('  3.3', '里程碑 /api/milestones'),
    ('  3.4', '周报系统 /api/reports'),
    ('  3.5', '风险/问题 /api/risks'),
    ('  3.6', '变更请求 /api/changes'),
    ('  3.7', '交付物 /api/deliverables'),
    ('  3.8', '项目文档 /api/docs'),
    ('  3.9', '驾驶舱 /api/dashboard'),
    ('  3.10', '个人工作台 /api/my-work'),
    ('  3.11', '导出 /api/export'),
    ('  3.12', '文件上传 /api/files'),
    ('  3.13', '审计日志 /api/audit-logs'),
    ('4', '前端组件树与状态管理'),
    ('  4.1', '组件树全景图'),
    ('  4.2', 'Pinia Store 设计'),
    ('  4.3', '路由设计'),
    ('  4.4', 'API 层封装'),
    ('5', '边界条件与异常处理'),
    ('  5.1', '认证与鉴权边界'),
    ('  5.2', '并发写入冲突'),
    ('  5.3', '文件上传安全边界'),
    ('  5.4', '日期/周次计算边界'),
    ('  5.5', '级联删除与软删除'),
    ('  5.6', '网络断连与重试'),
    ('  5.7', '大数据量导出'),
    ('6', '数据一致性保障方案'),
    ('  6.1', '事务隔离级别'),
    ('  6.2', '乐观锁 (Optimistic Locking)'),
    ('  6.3', '唯一约束 + ON CONFLICT UPSERT'),
    ('  6.4', '健康快照一致性'),
    ('  6.5', '文件-数据库一致性'),
    ('  6.6', '备份策略'),
    ('7', '部署架构'),
    ('8', '迁移路线图 (Flask→FastAPI)'),
]
for num, title_text in toc_items:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run(f'{num}  {title_text}')
    run.font.size = Pt(10)
    if not num.startswith(' '):
        run.bold = True

doc.add_page_break()

# ════════════════════════════════════════════════════
# 1. 项目背景与技术选型
# ════════════════════════════════════════════════════
doc.add_heading('1  项目背景与技术选型', level=1)

doc.add_heading('1.1  业务背景', level=2)
doc.add_paragraph(
    '本系统服务于电机与控制器的全生命周期研发管理，覆盖4大业务场景：\n'
    '  • 电机设计：电磁方案、结构设计、散热分析、材料选型\n'
    '  • 电机控制器设计：控制算法、嵌入式软件、功率硬件、PCB Layout\n'
    '  • 样机制造：零部件加工跟进、BOM管理、装配工艺\n'
    '  • 样机试验：台架测试、NVH、效率MAP、环境耐久、DV/PV验证'
)

doc.add_heading('1.2  技术选型', level=2)
add_table(doc,
    ['层次', 'v1.x (当前)', 'v2.0 (目标)', '选型理由'],
    [
        ['后端框架', 'Flask 3.x (同步)', 'FastAPI 0.115+ (异步)', '原生 async/await，自动 OpenAPI 文档，Pydantic 验证'],
        ['ORM', 'Flask-SQLAlchemy', 'SQLAlchemy 2.0 (async)', '原生异步支持，2.0 语法更清晰，类型提示完整'],
        ['数据库', 'SQLite (文件)', 'PostgreSQL 16+', '并发写入、JSONB、全文搜索、行级安全、连接池'],
        ['迁移工具', '手动 ALTER', 'Alembic', '版本化迁移、自动生成、回滚支持'],
        ['认证', '自研 Token', 'JWT (python-jose)', '行业标准、过期控制、refresh token'],
        ['数据验证', '手动', 'Pydantic v2', '编译时验证、JSON Schema 自动生成、高性能'],
        ['前端框架', 'Vue 3 + Element Plus', '不变', 'CDN 外链，构建产物体积小'],
        ['状态管理', '组件内 ref/reactive', 'Pinia', '类型安全、devtools 支持、模块化'],
        ['HTTP 客户端', 'fetch', 'axios (拦截器+重试)', '统一错误处理、token 自动注入'],
        ['文件存储', '本地磁盘', '本地磁盘 + 可选 S3/MinIO', '过渡期本地优先，后续可扩展对象存储'],
    ],
    col_widths=[2.5, 3.5, 4, 5.5]
)

doc.add_heading('1.3  核心设计原则', level=2)
principles = [
    '异步优先：所有 I/O 操作 (DB查询、文件读写、外部通知) 使用 async/await',
    '类型安全：Pydantic 模型覆盖全部请求/响应，运行时自动校验',
    '幂等设计：周报同周重复提交 = UPSERT，文件替换 = 版本链，避免重复数据',
    '软删除为主：项目/成员标记 is_active=False，风险/变更保留完整历史',
    '审计不可变：audit_log 表只 INSERT 不 UPDATE/DELETE，保证追溯完整',
    '前后端分离：FastAPI 仅提供 JSON API，前端 SPA 独立部署或嵌入静态文件服务',
]
for i, p_text in enumerate(principles, 1):
    doc.add_paragraph(f'{i}. {p_text}')

doc.add_page_break()

# ════════════════════════════════════════════════════
# 2. 数据模型设计
# ════════════════════════════════════════════════════
doc.add_heading('2  数据模型设计', level=1)

doc.add_heading('2.1  ER 实体关系总览', level=2)
doc.add_paragraph(
    '核心关系链：\n'
    '  Client (1) ──< (N) Project (1) ──< (N) PhaseGate / Milestone / Report / Risk / Change / Deliverable / Document\n'
    '  Project (N) >── (N) TeamMember   through ProjectMember (allocation_pct, is_key)\n'
    '  WeeklyReport (1) ──< (N) WeeklyReportLine (6 rows per report, one per technical_line)\n'
    '  PhaseGate (1) ──< (N) ReviewActionItem (设计评审待办跟踪)\n'
    '  Document (1) ──< (N) Document (self-referencing version chain via replaced_by_id)\n'
    '  UserAuth (1) ── (1) TeamMember (登录账号绑定团队成员)\n'
    '  AuditLog: 独立审计表，外键关联 Project，只增不删'
)

doc.add_heading('2.2  字典/参考数据表 (4张)', level=2)

doc.add_heading('Phase (项目阶段)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '说明'],
    [
        ['id', 'SERIAL PK', '', '自增主键'],
        ['name', 'VARCHAR(32)', 'NOT NULL', '概念阶段 / 方案阶段 / 详细设计 / 样机试制 / 测试验证 / 设计定型'],
        ['code', 'VARCHAR(16)', 'NOT NULL', 'CONCEPT / SCHEME / DETAIL / PROTOTYPE / VERIFY / FINAL'],
        ['sort_order', 'INTEGER', 'NOT NULL', '排序 1-6'],
        ['description', 'TEXT', '', '阶段描述'],
    ]
)
doc.add_paragraph(
    '种子数据 (6行)：概念阶段(G1)→方案阶段(G2)→详细设计(G3)→样机试制(G4)→测试验证(G5)→设计定型(无门径)\n'
    '索引：UNIQUE(sort_order)，用于 ORDER BY 排序'
)

doc.add_heading('Gate (阶段门径)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '说明'],
    [
        ['id', 'SERIAL PK', '', ''],
        ['name', 'VARCHAR(64)', 'NOT NULL', 'G1概念评审 / G2方案评审 / G3试制评审 / G4验证评审 / G5定型评审'],
        ['code', 'VARCHAR(8)', 'NOT NULL', 'G1-G5'],
        ['sort_order', 'INTEGER', 'NOT NULL', '1-5'],
        ['phase_id', 'INTEGER FK', 'phase.id', '关联阶段'],
    ]
)

doc.add_heading('TechnicalLine (技术线)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '说明'],
    [
        ['id', 'SERIAL PK', '', ''],
        ['name', 'VARCHAR(32)', 'NOT NULL', '控制算法/控制软件/控制硬件/电机结构/电机电磁/测试验证'],
        ['short_name', 'VARCHAR(16)', '', '算法/软件/硬件/结构/电磁/测试'],
        ['sort_order', 'INTEGER', 'NOT NULL', '1-6'],
        ['icon', 'VARCHAR(32)', '', 'Element Plus 图标名'],
    ]
)

doc.add_heading('Role (项目角色)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '说明'],
    [
        ['id', 'SERIAL PK', '', ''],
        ['name', 'VARCHAR(32)', 'NOT NULL', '项目经理/算法工程师/软件工程师/硬件工程师/结构工程师/电磁工程师/测试工程师'],
        ['code', 'VARCHAR(16)', 'NOT NULL', 'PM/ALGO/SW/HW/STRUCT/EM/TEST'],
        ['sort_order', 'INTEGER', '', ''],
        ['is_core', 'BOOLEAN', 'DEFAULT TRUE', '是否关键角色'],
    ]
)

doc.add_heading('2.3  核心业务表 (10张)', level=2)

doc.add_heading('Client (客户信息)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['name', 'VARCHAR(128)', 'NOT NULL', '', '客户全称'],
        ['abbreviation', 'VARCHAR(16)', 'UNIQUE NOT NULL', 'UNIQUE', '客户缩写，如 YPS — 用于项目编号前缀'],
        ['address', 'VARCHAR(256)', '', '', '公司地址'],
        ['phone', 'VARCHAR(32)', '', '', '公司电话'],
        ['contact_person', 'VARCHAR(64)', '', '', '对接人姓名'],
        ['contact_phone', 'VARCHAR(32)', '', '', '对接人电话'],
        ['contact_email', 'VARCHAR(128)', '', '', '对接人邮箱'],
        ['notes', 'TEXT', '', '', '备注'],
        ['is_active', 'BOOLEAN', 'DEFAULT TRUE', '', ''],
        ['created_at', 'TIMESTAMPTZ', 'DEFAULT NOW()', '', ''],
    ]
)

doc.add_heading('Project (项目)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['name', 'VARCHAR(128)', 'NOT NULL', 'GIN (全文)', '项目名称'],
        ['code', 'VARCHAR(32)', 'UNIQUE', 'UNIQUE', '项目编号，如 YPS-2026-001'],
        ['description', 'TEXT', '', '', '项目描述'],
        ['current_phase_id', 'INT FK', 'phase.id', 'BTREE', '当前所处阶段'],
        ['client_id', 'INT FK', 'client.id', 'BTREE', '关联客户'],
        ['start_date', 'DATE', '', 'BTREE', '开始日期'],
        ['planned_end_date', 'DATE', '', '', '计划结束日期'],
        ['actual_end_date', 'DATE', '', '', '实际结束日期'],
        ['overall_status', 'VARCHAR(16)', "DEFAULT 'normal'", 'BTREE', 'blocked / at_risk / normal / completed'],
        ['completion_pct', 'INTEGER', 'DEFAULT 0', '', '完成百分比 0-100'],
        ['problem_statement', 'TEXT', '', '', '要解决的问题 (Section A-P1)'],
        ['final_deliverable', 'TEXT', '', '', '最终交付物 (Section A-P2)'],
        ['acceptance_criteria', 'TEXT', '', '', '验收标准 (Section A-P3)'],
        ['aligned_target', 'TEXT', '', '', '对齐目标 (Section A-P4)'],
        ['deadline_type', 'VARCHAR(16)', '', '', '硬性截止/弹性截止'],
        ['main_blocker', 'TEXT', '', '', '当前主要阻塞'],
        ['blocker_duration', 'VARCHAR(16)', '', '', '阻塞持续: <1周/1-2周/2-4周/>4周'],
        ['morale', 'VARCHAR(16)', '', '', '团队士气: 高/中/低'],
        ['common_complaint', 'TEXT', '', '', '团队普遍抱怨'],
        ['success_confidence', 'VARCHAR(16)', '', '', '成功信心: 高/中/低'],
        ['priority', 'VARCHAR(8)', "DEFAULT 'P1'", 'BTREE', 'P0/P1/P2/P3'],
        ['difficulty', 'VARCHAR(16)', '', '', '项目难度等级'],
        ['is_active', 'BOOLEAN', 'DEFAULT TRUE', 'BTREE', '软删除标记'],
        ['budget_total', 'NUMERIC(12,2)', '', '', '总预算(元)'],
        ['budget_spent', 'NUMERIC(12,2)', '', '', '已花费(元)'],
        ['created_at', 'TIMESTAMPTZ', 'DEFAULT NOW()', 'BTREE', ''],
        ['updated_at', 'TIMESTAMPTZ', 'DEFAULT NOW()', '', '自动更新'],
    ]
)
doc.add_paragraph(
    '关键索引策略：\n'
    '  • CREATE INDEX idx_project_status_priority ON project(overall_status, priority) WHERE is_active = TRUE;\n'
    '  • CREATE INDEX idx_project_client ON project(client_id);\n'
    '  • ALTER TABLE project ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (\n'
    "      to_tsvector('simple', coalesce(name,'') || ' ' || coalesce(code,''))\n"
    '    ) STORED;\n'
    '  • CREATE INDEX idx_project_search ON project USING GIN(search_vector);'
)

doc.add_heading('TeamMember (团队成员)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['name', 'VARCHAR(64)', 'NOT NULL', 'BTREE', '姓名'],
        ['department', 'VARCHAR(64)', '', '', '部门'],
        ['email', 'VARCHAR(128)', '', '', '邮箱'],
        ['phone', 'VARCHAR(32)', '', '', '电话'],
        ['title', 'VARCHAR(64)', '', '', '职位'],
        ['skills', 'VARCHAR(256)', '', '', '技能标签 (逗号分隔)'],
        ['is_active', 'BOOLEAN', 'DEFAULT TRUE', '', ''],
    ]
)

doc.add_heading('ProjectMember (项目-人员关联)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['project_id', 'INT FK', 'project.id NOT NULL', 'UNIQUE(pid,mid,rid)', '复合唯一约束：同一成员+角色不重复'],
        ['member_id', 'INT FK', 'team_member.id NOT NULL', '', ''],
        ['role_id', 'INT FK', 'role.id NOT NULL', '', ''],
        ['allocation_pct', 'INTEGER', 'DEFAULT 100', '', '投入比例 0-100'],
        ['is_key', 'BOOLEAN', 'DEFAULT FALSE', '', '是否关键人员'],
    ]
)
doc.add_paragraph('UNIQUE(project_id, member_id, role_id) 确保同一人在同一项目同一角色只能有一条记录')

doc.add_heading('ProjectPhaseGate (项目阶段门径)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['project_id', 'INT FK', 'NOT NULL', 'UNIQUE(pid,pid)', '每项目每阶段一条'],
        ['phase_id', 'INT FK', 'NOT NULL', '', ''],
        ['gate_id', 'INT FK', 'gate.id', '', '对应门径(可为NULL=未设置)'],
        ['planned_start_date', 'DATE', '', '', ''],
        ['planned_end_date', 'DATE', '', '', ''],
        ['actual_start_date', 'DATE', '', '', ''],
        ['actual_end_date', 'DATE', '', '', ''],
        ['status', 'VARCHAR(16)', "DEFAULT 'not_started'", '', 'not_started/in_progress/completed/blocked'],
        ['gate_status', 'VARCHAR(16)', '', '', 'gating: pending/passed/failed/waived'],
        ['gate_review_date', 'DATE', '', '', '评审会议日期'],
        ['gate_review_notes', 'TEXT', '', '', '评审结论'],
    ]
)

doc.add_heading('ReviewActionItem (评审待办)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '说明'],
    [
        ['id', 'SERIAL PK', '', ''],
        ['project_phase_gate_id', 'INT FK', 'NOT NULL', '关联哪个门径评审'],
        ['title', 'VARCHAR(256)', 'NOT NULL', '待办标题'],
        ['description', 'TEXT', '', ''],
        ['assignee_id', 'INT FK', 'team_member.id', '负责人'],
        ['due_date', 'DATE', '', '截至日期'],
        ['status', 'VARCHAR(16)', "DEFAULT 'open'", 'open/in_progress/closed'],
        ['resolution', 'TEXT', '', '关闭时的解决说明'],
        ['sort_order', 'INTEGER', 'DEFAULT 0', ''],
        ['created_at', 'TIMESTAMPTZ', 'DEFAULT NOW()', ''],
        ['closed_at', 'TIMESTAMPTZ', '', ''],
    ]
)

doc.add_heading('Milestone (里程碑)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['project_id', 'INT FK', 'NOT NULL', 'BTREE(pid,date)', '复合索引加速按项目+时间查询'],
        ['name', 'VARCHAR(128)', 'NOT NULL', '', '里程碑名称'],
        ['description', 'TEXT', '', '', ''],
        ['planned_date', 'DATE', 'NOT NULL', 'BTREE(pid,status,date)', '计划日期 — 驾驶舱"近期里程碑"查询'],
        ['actual_date', 'DATE', '', '', '实际完成日期'],
        ['line_id', 'INT FK', 'technical_line.id', '', '所属技术线'],
        ['phase_id', 'INT FK', 'phase.id', '', '所属阶段'],
        ['status', 'VARCHAR(16)', "DEFAULT 'pending'", '', 'pending/in_progress/completed/overdue'],
        ['is_key', 'BOOLEAN', 'DEFAULT FALSE', '', '是否关键里程碑'],
        ['sort_order', 'INTEGER', 'DEFAULT 0', '', ''],
    ]
)
doc.add_paragraph('关键索引: CREATE INDEX idx_ms_project_status_date ON milestone(project_id, status, planned_date) WHERE status != \'completed\';')

doc.add_heading('WeeklyReport (周报主表)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['project_id', 'INT FK', 'NOT NULL', 'UNIQUE(pid,year,wk)', '复合唯一：每项目每周仅一份周报'],
        ['week_number', 'INTEGER', 'NOT NULL', '', 'ISO 周数 1-53'],
        ['year', 'INTEGER', 'NOT NULL', '', 'ISO 年份'],
        ['report_date', 'DATE', '', '', '报告日期（默认该周周五）'],
        ['overall_progress', 'TEXT', '', '', '总体进展描述'],
        ['key_accomplishments', 'TEXT', '', '', '本周关键成果'],
        ['completion_rate', 'VARCHAR(16)', '', '', 'on_track/at_risk/behind/blcoked'],
        ['reporter_id', 'INT FK', 'team_member.id', '', '填报人'],
        ['created_at', 'TIMESTAMPTZ', 'DEFAULT NOW()', '', ''],
    ]
)

doc.add_heading('WeeklyReportLine (周报行 — 6技术线明细)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['report_id', 'INT FK', 'NOT NULL', 'UNIQUE(rid,lid)', '每报告每技术线一行'],
        ['line_id', 'INT FK', 'NOT NULL', '', 'technical_line.id'],
        ['this_week', 'TEXT', '', '', '本周进展'],
        ['next_week', 'TEXT', '', '', '下周计划'],
        ['status', 'VARCHAR(16)', '', '', 'on_track/at_risk/behind/blocked'],
        ['blocker', 'TEXT', '', '', '难点/阻塞'],
        ['coordinator', 'VARCHAR(64)', '', '', '协调人'],
        ['sort_order', 'INTEGER', 'DEFAULT 0', '', ''],
    ]
)

doc.add_heading('RiskIssue (风险/问题)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['project_id', 'INT FK', 'NOT NULL', 'BTREE(pid,status)', ''],
        ['type', 'VARCHAR(16)', "DEFAULT 'risk'", '', 'risk / issue'],
        ['title', 'VARCHAR(256)', 'NOT NULL', '', ''],
        ['description', 'TEXT', '', '', ''],
        ['probability', 'VARCHAR(16)', '', '', 'high/medium/low (风险概率)'],
        ['impact', 'VARCHAR(16)', '', '', 'high/medium/low (影响程度)'],
        ['risk_level', 'VARCHAR(16)', '', 'BTREE', 'critical/high/medium/low (综合等级)'],
        ['severity', 'VARCHAR(8)', '', '', 'S/A/B/C'],
        ['status', 'VARCHAR(16)', "DEFAULT 'open'", 'BTREE', 'open/in_progress/resolved/closed/wont_fix'],
        ['mitigation_plan', 'TEXT', '', '', '缓解措施'],
        ['owner_id', 'INT FK', 'team_member.id', '', '负责人'],
        ['line_id', 'INT FK', 'technical_line.id', '', '影响技术线'],
        ['phase_id', 'INT FK', 'phase.id', '', '发现阶段'],
        ['identified_date', 'DATE', '', '', '识别日期'],
        ['target_resolve_date', 'DATE', '', '', '目标解决日期'],
        ['resolved_date', 'DATE', '', '', '实际解决日期'],
        ['resolution', 'TEXT', '', '', '验证结果 (关闭必填)'],
        ['attachment_path', 'VARCHAR(512)', '', '', '验证附件路径'],
        ['created_at', 'TIMESTAMPTZ', 'DEFAULT NOW()', '', ''],
    ]
)

doc.add_heading('ChangeRequest (变更请求)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '说明'],
    [
        ['id', 'SERIAL PK', '', ''],
        ['project_id', 'INT FK', 'NOT NULL', ''],
        ['title', 'VARCHAR(256)', 'NOT NULL', '变更标题'],
        ['description', 'TEXT', '', '变更描述'],
        ['change_level', 'VARCHAR(16)', '', 'A级(重大)/B级(一般)/C级(微小)'],
        ['requester_id', 'INT FK', 'team_member.id', '申请人'],
        ['affected_lines', 'VARCHAR(256)', '', '影响的技术线 (逗号分隔)'],
        ['impact_scope', 'TEXT', '', '范围影响分析'],
        ['impact_schedule', 'TEXT', '', '进度影响分析'],
        ['impact_cost', 'TEXT', '', '成本影响分析'],
        ['status', 'VARCHAR(16)', "DEFAULT 'pending'", 'pending/approved/rejected/implemented'],
        ['reviewer_id', 'INT FK', 'team_member.id', '审批人'],
        ['review_notes', 'TEXT', '', '审批意见'],
        ['submitted_date', 'DATE', '', '提交日期'],
        ['decision_date', 'DATE', '', '决策日期'],
        ['created_at', 'TIMESTAMPTZ', 'DEFAULT NOW()', ''],
    ]
)

doc.add_heading('Deliverable (交付物)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['project_id', 'INT FK', 'NOT NULL', '', ''],
        ['phase_id', 'INT FK', 'NOT NULL', '', ''],
        ['line_id', 'INT FK', '', 'BTREE(pid,pid,lid)', '6阶段×6技术线 = 最多36项/项目'],
        ['name', 'VARCHAR(256)', 'NOT NULL', '', ''],
        ['description', 'TEXT', '', '', ''],
        ['file_path', 'VARCHAR(512)', '', '', '文件路径'],
        ['status', 'VARCHAR(16)', "DEFAULT 'not_submitted'", '', 'not_submitted/submitted/approved/rejected'],
        ['owner_id', 'INT FK', 'team_member.id', '', ''],
        ['submitted_date', 'DATE', '', '', ''],
    ]
)

doc.add_heading('ProjectDocument (项目文档 — P0/PP1/PP2)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '说明'],
    [
        ['id', 'SERIAL PK', '', ''],
        ['project_id', 'INT FK', 'NOT NULL', ''],
        ['name', 'VARCHAR(256)', 'NOT NULL', '文档名称'],
        ['doc_type', 'VARCHAR(32)', 'NOT NULL', 'contract/tech_protocol/requirement/project_approval/\n'
         'sim_model/design_report/drawing/test_plan/\n'
         'prototype_report/data_regression/improve_plan/improve_report/other'],
        ['file_path', 'VARCHAR(512)', '', ''],
        ['file_size', 'INTEGER', '', '字节数'],
        ['uploaded_by', 'VARCHAR(64)', '', '上传者'],
        ['upload_date', 'DATE', '', ''],
        ['notes', 'TEXT', '', ''],
        ['status', 'VARCHAR(16)', "DEFAULT 'active'", 'active/deprecated/superseded'],
        ['version', 'INTEGER', 'DEFAULT 1', '版本号 V1/V2/...'],
        ['replaced_by_id', 'INT FK (自引用)', 'project_document.id', '被哪个新版本替换'],
    ]
)

doc.add_heading('2.4  认证与审计表 (2张)', level=2)

doc.add_heading('UserAuth (用户认证)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['username', 'VARCHAR(64)', 'UNIQUE NOT NULL', 'UNIQUE', '登录名'],
        ['password_hash', 'VARCHAR(256)', 'NOT NULL', '', 'bcrypt hash (v2升级)'],
        ['member_id', 'INT FK', 'team_member.id', 'BTREE', '绑定团队成员'],
        ['role', 'VARCHAR(16)', "DEFAULT 'member'", '', 'admin/pm/member'],
        ['refresh_token', 'VARCHAR(256)', '', 'UNIQUE', 'JWT refresh token (v2新增)'],
        ['is_active', 'BOOLEAN', 'DEFAULT TRUE', '', ''],
        ['created_at', 'TIMESTAMPTZ', 'DEFAULT NOW()', '', ''],
        ['last_login', 'TIMESTAMPTZ', '', '', ''],
    ]
)
doc.add_paragraph(
    'v1.x→v2.0 升级要点：\n'
    '  • password_hash 从 SHA256+SALT 升级为 bcrypt (passlib[bcrypt])\n'
    '  • 新增 refresh_token 字段支持 JWT 双 token 机制\n'
    '  • access_token 有效期 30min，refresh_token 有效期 7d'
)

doc.add_heading('AuditLog (操作审计日志)', level=3)
add_table(doc,
    ['字段', '类型', '约束', '索引', '说明'],
    [
        ['id', 'SERIAL PK', '', '', ''],
        ['username', 'VARCHAR(64)', 'NOT NULL', 'BTREE', '操作人'],
        ['action', 'VARCHAR(16)', 'NOT NULL', '', 'create/update/delete/close/replace/deprecate/login/logout'],
        ['entity_type', 'VARCHAR(32)', 'NOT NULL', 'BTREE', 'project/milestone/risk/change/deliverable/report/document'],
        ['entity_id', 'INTEGER', '', '', '被操作实体ID'],
        ['entity_name', 'VARCHAR(256)', '', '', '被操作实体名称'],
        ['project_id', 'INT FK', 'project.id', 'BTREE', '归属项目 (可为空)'],
        ['summary', 'VARCHAR(512)', '', '', '操作摘要'],
        ['details', 'JSONB', '', 'GIN', '变更详情 (v2升级为JSONB) — 记录变更前后的字段差异'],
        ['created_at', 'TIMESTAMPTZ', 'DEFAULT NOW()', 'BTREE DESC', '操作时间'],
    ]
)
doc.add_paragraph(
    '设计原则：\n'
    '  • 只 INSERT，绝不 UPDATE/DELETE → 保证审计不可篡改\n'
    '  • 按 (created_at DESC) 分区查询，按 (project_id) 索引加速跨项目筛选\n'
    '  • details JSONB 存储 {"field": "status", "old": "open", "new": "closed"} 格式的变更记录\n'
    '  • 保留90天后自动归档到 audit_log_archive 表'
)

doc.add_page_break()

doc.add_heading('2.5  索引策略 — 完整 DDL', level=2)
code_block(doc, '''-- ============================================================
-- 高频查询索引
-- ============================================================

-- 项目列表：按状态+优先级排序（驾驶舱首页核心查询）
CREATE INDEX idx_project_active_priority ON project(overall_status, priority, created_at DESC)
    WHERE is_active = TRUE;

-- 项目全职搜索
ALTER TABLE project ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(name,'') || ' ' || coalesce(code,'') || ' ' || coalesce(description,''))
    ) STORED;
CREATE INDEX idx_project_fts ON project USING GIN(search_vector);

-- 里程碑：逾期+未完成（个人工作台核心查询）
CREATE INDEX idx_ms_overdue ON milestone(project_id, planned_date)
    WHERE status NOT IN ('completed', 'cancelled');

-- 里程碑全景视图
CREATE INDEX idx_ms_all_active ON milestone(planned_date, status)
    WHERE project_id IN (SELECT id FROM project WHERE is_active = TRUE);

-- 风险：未关闭（驾驶舱风险汇总）
CREATE INDEX idx_risk_open ON risk_issue(project_id, risk_level, status)
    WHERE status IN ('open', 'in_progress');

-- 周报：按项目+时间范围
CREATE INDEX idx_report_project_week ON weekly_report(project_id, year DESC, week_number DESC);

-- 交付物：按阶段+技术线矩阵查询
CREATE INDEX idx_deliverable_matrix ON deliverable(project_id, phase_id, line_id);

-- 审计日志：按时间倒序（分区查询优化）
CREATE INDEX idx_audit_time ON audit_log(created_at DESC);
CREATE INDEX idx_audit_project ON audit_log(project_id, created_at DESC);
CREATE INDEX idx_audit_user ON audit_log(username, created_at DESC);

-- 用户认证
CREATE INDEX idx_user_refresh_token ON user_auth(refresh_token) WHERE is_active = TRUE;

-- ============================================================
-- 外键索引（所有 FK 必须建索引，防止全表锁）
-- ============================================================
CREATE INDEX idx_pm_project ON project_member(project_id);
CREATE INDEX idx_pm_member ON project_member(member_id);
CREATE INDEX idx_pg_project ON project_phase_gate(project_id);
CREATE INDEX idx_rai_phasegate ON review_action_item(project_phase_gate_id);
CREATE INDEX idx_ms_project ON milestone(project_id);
CREATE INDEX idx_wr_project ON weekly_report(project_id);
CREATE INDEX idx_wrl_report ON weekly_report_line(report_id);
CREATE INDEX idx_risk_project ON risk_issue(project_id);
CREATE INDEX idx_risk_owner ON risk_issue(owner_id);
CREATE INDEX idx_change_project ON change_request(project_id);
CREATE INDEX idx_deliv_project ON deliverable(project_id);
CREATE INDEX idx_doc_project ON project_document(project_id);

-- ============================================================
-- 部分唯一索引（PostgreSQL 特性）
-- ============================================================
-- 保证同一 project+year+week 只有一份有效周报
CREATE UNIQUE INDEX idx_report_uniq ON weekly_report(project_id, year, week_number)
    WHERE is_active_placeholder; -- 这里用 WHERE 条件软删除需要另外设计，当前用 UNIQUE 约束即可
''')

doc.add_page_break()

# ════════════════════════════════════════════════════
# 3. API 接口设计
# ════════════════════════════════════════════════════
doc.add_heading('3  API 接口设计 (RESTful)', level=1)

doc.add_paragraph(
    '设计约定：\n'
    '  • Base URL: /api\n'
    '  • 认证头: Authorization: Bearer <access_token>\n'
    '  • 请求体: application/json (文件上传用 multipart/form-data)\n'
    '  • 响应体: {"data": ..., "message": "..."} 或 {"error": "...", "detail": "..."}\n'
    '  • 分页格式: {"data": [...], "total": N, "page": 1, "page_size": 20}\n'
    '  • 排序: ?sort_by=field&order=asc|desc\n'
    '  • OpenAPI 文档: /docs (Swagger UI) + /redoc (ReDoc) — FastAPI 自动生成'
)

doc.add_heading('3.1  认证模块', level=2)
add_table(doc,
    ['方法', '端点', '认证', '请求体', '响应体', '说明'],
    [
        ['POST', '/api/auth/login', '否', '{"username":"str","password":"str"}',
         '{"access_token":"str","refresh_token":"str","user":{...}}', '登录，返回双token'],
        ['POST', '/api/auth/refresh', '否', '{"refresh_token":"str"}',
         '{"access_token":"str"}', '刷新access_token (30min过期→用7天refresh换)'],
        ['POST', '/api/auth/register', '否', '{"username":"str","password":"str","member_id":int}',
         '{"user":{...}}', '注册（需管理员审批或开放注册）'],
        ['POST', '/api/auth/logout', '是', '',
         '{"message":"logged out"}', '注销refresh_token'],
        ['GET', '/api/auth/me', '是', '',
         '{"user":{...}}', '获取当前用户信息'],
        ['PUT', '/api/auth/password', '是', '{"old_password":"str","new_password":"str"}',
         '{"message":"updated"}', '修改密码'],
    ]
)

doc.add_heading('3.2  项目管理', level=2)
add_table(doc,
    ['方法', '端点', '请求体 / 查询参数', '说明'],
    [
        ['GET', '/api/projects', '?status=active&priority=P0&client_id=X&search=keyword&page=1&size=20&sort_by=priority',
         '列表查询：支持多条件筛选 + 分页 + 全文搜索'],
        ['POST', '/api/projects', 'ProjectCreate (Pydantic)', '新建项目（自动创建6条 phase_gate 记录）'],
        ['GET', '/api/projects/{id}', '', '项目详情（含 phase_gates, members, 统计）'],
        ['PUT', '/api/projects/{id}', 'ProjectUpdate (Pydantic)', '更新项目信息'],
        ['DELETE', '/api/projects/{id}', '', '软删除（设置 is_active=FALSE）'],
        ['POST', '/api/projects/{id}/copy', '{"new_code":"YPS-2026-005"}', '复制项目模板（来自 项目→复制 按钮）'],
        ['GET', '/api/projects/{id}/stats', '', '项目统计：里程碑完成率、风险数、周报提交率等'],
        ['GET', '/api/projects/{id}/health', '', '项目健康快照历史 (12周趋势)'],
    ]
)

doc.add_heading('ProjectCreate Pydantic Schema', level=3)
code_block(doc, '''from pydantic import BaseModel, Field
from datetime import date
from typing import Optional

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    code: str = Field(..., pattern=r'^[A-Z]{2,4}-\\d{4}-\\d{3}$')  # YPS-2026-001
    description: Optional[str] = None
    client_id: int
    start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    priority: str = Field(default='P1', pattern=r'^P[0-3]$')
    difficulty: Optional[str] = None
    budget_total: Optional[float] = Field(default=None, ge=0)
    final_deliverable: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    problem_statement: Optional[str] = None
    aligned_target: Optional[str] = None
    deadline_type: Optional[str] = None

class ProjectUpdate(ProjectCreate):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    code: Optional[str] = Field(None, pattern=r'^[A-Z]{2,4}-\\d{4}-\\d{3}$')
    overall_status: Optional[str] = None
    completion_pct: Optional[int] = Field(default=None, ge=0, le=100)
    current_phase_id: Optional[int] = None
    main_blocker: Optional[str] = None
    morale: Optional[str] = None
    success_confidence: Optional[str] = None
''')

doc.add_heading('3.3  里程碑', level=2)
add_table(doc,
    ['方法', '端点', '请求体', '说明'],
    [
        ['GET', '/api/projects/{pid}/milestones', '?phase_id=X&line_id=Y&status=Z', '按筛选条件获取里程碑列表'],
        ['POST', '/api/projects/{pid}/milestones', 'MilestoneCreate', '新建里程碑'],
        ['PUT', '/api/milestones/{id}', 'MilestoneUpdate', '更新里程碑'],
        ['DELETE', '/api/milestones/{id}', '', '删除里程碑'],
        ['GET', '/api/milestones/all', '?project_id=X&year=2026&month=6', '里程碑全景（日历用）'],
    ]
)

doc.add_heading('3.4  周报系统', level=2)
add_table(doc,
    ['方法', '端点', '请求体', '说明'],
    [
        ['GET', '/api/projects/{pid}/reports', '?year=2026&week=25', '获取周报列表（默认当前周）'],
        ['POST', '/api/projects/{pid}/reports', 'WeeklyReportCreate (含6条line_items)', '创建/更新周报（UPSERT语义）'],
        ['GET', '/api/reports/{id}', '', '周报详情（含6条line_items）'],
        ['PUT', '/api/reports/{id}', 'WeeklyReportUpdate', '更新周报（允许修改reporter_id和日期）'],
        ['GET', '/api/projects/{pid}/reports/latest', '', '获取最近一期周报（用于自动填充"上周计划"）'],
    ]
)

doc.add_heading('WeeklyReportCreate Pydantic Schema', level=3)
code_block(doc, '''class WeeklyReportLineItem(BaseModel):
    line_id: int
    this_week: Optional[str] = ''
    next_week: Optional[str] = ''
    status: Optional[str] = None       # on_track / at_risk / behind / blocked
    blocker: Optional[str] = ''
    coordinator: Optional[str] = ''

class WeeklyReportCreate(BaseModel):
    report_date: date                     # 默认本周五
    overall_progress: Optional[str] = ''
    key_accomplishments: Optional[str] = ''
    completion_rate: Optional[str] = None
    reporter_id: int
    line_items: list[WeeklyReportLineItem]  # 固定6条，按 line_id 1-6

    @field_validator('line_items')
    @classmethod
    def must_have_six_lines(cls, v):
        if len(v) != 6:
            raise ValueError('周报必须包含6条技术线')
        line_ids = {item.line_id for item in v}
        if line_ids != {1,2,3,4,5,6}:
            raise ValueError('line_id 必须是 1-6')
        return v
''')

doc.add_heading('3.5  风险/问题', level=2)
add_table(doc,
    ['方法', '端点', '请求体', '说明'],
    [
        ['GET', '/api/projects/{pid}/risks', '?type=risk|issue&status=open&risk_level=critical', '筛选查询'],
        ['POST', '/api/projects/{pid}/risks', 'RiskIssueCreate', '新建风险/问题'],
        ['PUT', '/api/risks/{id}', 'RiskIssueUpdate', '更新'],
        ['DELETE', '/api/risks/{id}', '', '删除'],
        ['POST', '/api/risks/{id}/close', 'CloseRiskRequest', '关闭（必填 resolution，可选附件）'],
    ]
)

doc.add_heading('RiskIssueCreate Schema', level=3)
code_block(doc, '''class RiskIssueCreate(BaseModel):
    type: Literal['risk', 'issue']
    title: str = Field(..., max_length=256)
    description: Optional[str] = None
    probability: Optional[Literal['high','medium','low']] = None
    impact: Optional[Literal['high','medium','low']] = None
    risk_level: Optional[Literal['critical','high','medium','low']] = None
    severity: Optional[Literal['S','A','B','C']] = None
    mitigation_plan: Optional[str] = None
    owner_id: Optional[int] = None
    line_id: Optional[int] = None
    phase_id: Optional[int] = None
    identified_date: Optional[date] = None
    target_resolve_date: Optional[date] = None

class CloseRiskRequest(BaseModel):
    resolution: str = Field(..., min_length=1, max_length=5000)
    # file 通过 FormData 单独上传（可选）
''')

doc.add_heading('3.6  变更请求', level=2)
add_table(doc,
    ['方法', '端点', '说明'],
    [
        ['GET', '/api/projects/{pid}/changes', '筛选查询'],
        ['POST', '/api/projects/{pid}/changes', '新建变更'],
        ['PUT', '/api/changes/{id}', '更新 (含审批)'],
        ['DELETE', '/api/changes/{id}', '删除变更'],
    ]
)

doc.add_heading('3.7  交付物', level=2)
add_table(doc,
    ['方法', '端点', '说明'],
    [
        ['GET', '/api/projects/{pid}/deliverables', '?phase_id=X&line_id=Y 矩阵查询'],
        ['POST', '/api/projects/{pid}/deliverables', '新建交付物'],
        ['PUT', '/api/deliverables/{id}', '更新（含文件上传）'],
        ['DELETE', '/api/deliverables/{id}', '删除'],
    ]
)

doc.add_heading('3.8  项目文档 (P0/PP1/PP2)', level=2)
add_table(doc,
    ['方法', '端点', '说明'],
    [
        ['GET', '/api/projects/{pid}/docs', '?doc_type=contract&status=active 筛选'],
        ['POST', '/api/projects/{pid}/docs', '新建文档 (含文件上传)'],
        ['PUT', '/api/docs/{id}', '更新'],
        ['DELETE', '/api/docs/{id}', '删除'],
        ['POST', '/api/docs/{id}/deprecate', '标记为失效'],
        ['POST', '/api/docs/{id}/replace', '上传新版本 → 旧版 auto superseded'],
        ['GET', '/api/doc-types', '返回 P0/PP1/PP2 三级分类结构'],
    ]
)

doc.add_heading('3.9  驾驶舱', level=2)
add_table(doc,
    ['方法', '端点', '说明'],
    [
        ['GET', '/api/dashboard', '汇总一~五: 项目健康度/阶段分布/里程碑/风险/资源'],
        ['GET', '/api/dashboard/alerts', '告警：阻塞项目/逾期里程碑/未填周报'],
        ['GET', '/api/dashboard/pending-reports', '本周待填周报清单'],
        ['POST', '/api/dashboard/health-snapshot', '手动触发健康快照生成'],
    ]
)

doc.add_heading('3.10  个人工作台', level=2)
add_table(doc,
    ['方法', '端点', '说明'],
    [
        ['GET', '/api/my-work', '聚合：我的项目+待办里程碑+我的风险+待填周报+最近动态'],
    ]
)

doc.add_heading('3.11  导出', level=2)
add_table(doc,
    ['方法', '端点', '说明'],
    [
        ['GET', '/api/export/projects', '导出所有活跃项目 → .xlsx'],
        ['GET', '/api/export/projects/{pid}/reports', '导出项目周报 → .xlsx'],
        ['GET', '/api/export/projects/{pid}/risks', '导出项目风险清单 → .xlsx'],
    ]
)

doc.add_heading('3.12  文件上传', level=2)
add_table(doc,
    ['方法', '端点', '说明'],
    [
        ['POST', '/api/files/upload', '通用文件上传 → 返回 {"file_path":"...","file_size":N}'],
        ['GET', '/api/files/storage-stats', '存储用量统计'],
    ]
)
doc.add_paragraph(
    '文件上传安全策略：\n'
    '  • 白名单扩展名校验：pdf,doc,docx,xls,xlsx,ppt,pptx,step,stp,dwg,dxf,igs,iges,stl,zip,rar,7z,jpg,jpeg,png,gif,bmp,svg,txt,csv,json,xml,py,ipynb,md\n'
    '  • 大小限制：单文件 ≤ 100MB (FastAPI UploadFile + Content-Length 头检查)\n'
    '  • MIME 校验：检查文件魔术字节 (magic bytes)，防止扩展名伪装\n'
    '  • 存储路径：{UPLOAD_DIR}/{project_id}/{entity_type}/{uuid}_{original_name}\n'
    '  • 文件名安全化：去除路径分隔符、特殊字符，限制长度 ≤ 255 字节'
)

doc.add_heading('3.13  审计日志', level=2)
add_table(doc,
    ['方法', '端点', '说明'],
    [
        ['GET', '/api/audit-logs', '?username=X&action=Y&entity_type=Z&project_id=W&from=...&to=...&page=1&size=50\n多条件筛选 + 分页'],
    ]
)

doc.add_page_break()

# ════════════════════════════════════════════════════
# 4. 前端组件树与状态管理
# ════════════════════════════════════════════════════
doc.add_heading('4  前端组件树与状态管理', level=1)

doc.add_heading('4.1  组件树全景图', level=2)
code_block(doc, '''App.vue
├── LayoutDefault.vue                    # 默认布局：侧边栏 + 顶栏 + 内容区
│   ├── SidebarNav.vue                   # 侧边导航（项目列表快捷入口 + 导航菜单）
│   └── UserAvatar.vue                   # 顶栏用户头像 + 退出
│
├── pages/
│   ├── LoginPage.vue                    # 登录/注册
│   ├── DashboardPage.vue                # 驾驶舱首页
│   │   ├── AlertBanner.vue              #   P0 告警条（阻塞项目×N + 逾期里程碑×N）
│   │   ├── HealthCards.vue              #   P1 健康快照卡片行（汇总4卡片）
│   │   ├── ProjectTable.vue             #   P2 项目列表（按风险优先排序）
│   │   ├── MilestoneTimeline.vue        #   P3 近期里程碑时间线
│   │   └── ResourceGauge.vue            #   P3 资源过载指示
│   │
│   ├── ProjectListPage.vue              # 项目列表（卡片视图）
│   │   └── ProjectCard.vue              #   单个项目卡片（含删除/复制按钮）
│   │
│   ├── ProjectCreatePage.vue            # 新建/编辑项目
│   │
│   ├── ProjectDetailPage.vue            # 项目详情（Tab容器）
│   │   ├── GoalSummary.vue              #   项目目标摘要
│   │   ├── PhaseGatePanel.vue           #   阶段门径面板
│   │   │   ├── PhaseStepper.vue         #     步骤条视图（可点击编辑）
│   │   │   └── PhaseTreeView.vue        #     树状图视图（可点击跳转交付物）
│   │   ├── MilestoneGantt.vue           #   里程碑甘特图 + 表格
│   │   ├── WeeklyReportForm.vue         #   周报填写表单（6线表格）
│   │   │   └── SmartSplitDialog.vue     #     智能拆解弹窗
│   │   ├── ReportHistory.vue            #   周报历史列表
│   │   ├── ReportDetail.vue             #   周报详情
│   │   ├── RiskTable.vue                #   风险/问题登记表（含关闭弹窗）
│   │   ├── ChangeList.vue               #   变更请求列表
│   │   ├── TeamPanel.vue                #   团队管理（成员+投入比例）
│   │   ├── DeliverableMatrix.vue        #   交付物矩阵 (6×6)
│   │   └── DocumentManager.vue          #   项目文档 (P0/PP1/PP2)
│   │
│   ├── MilestonePage.vue                # 里程碑全景（跨项目甘特图）
│   ├── MyWorkPage.vue                   # 我的工作台
│   ├── AuditLogPage.vue                 # 操作审计日志
│   ├── ResourcePage.vue                 # 资源管理
│   └── SettingsPage.vue                 # 系统设置（客户/参考数据/存储用量）
│
├── components/
│   └── common/
│       ├── ProgressBar.vue              # 进度条组件
│       ├── StatusTag.vue                # 状态标签（颜色映射）
│       ├── FileUpload.vue               # 文件上传组件（拖拽+进度条）
│       ├── ConfirmDialog.vue            # 确认弹窗
│       └── EmptyState.vue               # 空状态占位
│
├── stores/                              # Pinia 状态管理
│   ├── auth.ts                          #   认证状态
│   ├── project.ts                       #   项目数据 + 缓存
│   ├── dashboard.ts                     #   驾驶舱数据
│   └── lookup.ts                        #   参考数据缓存
│
├── api/                                 # API 层
│   ├── client.ts                        #   axios 实例（拦截器/重试/Token）
│   ├── auth.ts                          #   认证 API
│   ├── projects.ts                      #   项目 API
│   ├── milestones.ts                    #   里程碑 API
│   ├── reports.ts                       #   周报 API
│   ├── risks.ts                         #   风险 API
│   ├── changes.ts                       #   变更 API
│   ├── deliverables.ts                  #   交付物 API
│   ├── documents.ts                     #   文档 API
│   ├── dashboard.ts                     #   驾驶舱 API
│   ├── myWork.ts                        #   个人工作台 API
│   └── export.ts                        #   导出 API
│
├── router/
│   └── index.ts                         # Vue Router 配置 + 导航守卫
│
├── utils/
│   ├── date.ts                          #   日期工具（周五计算/周数/ISO周）
│   ├── format.ts                        #   格式化工具
│   └── validators.ts                    #   前端校验规则
│
└── types/
    └── index.ts                         # TypeScript 类型定义
''')

doc.add_heading('4.2  Pinia Store 设计', level=2)

doc.add_heading('authStore', level=3)
code_block(doc, '''// stores/auth.ts
interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
}

// Actions:
//   login(username, password)     → 存储双token到 localStorage + state
//   logout()                      → 清除 token，调用 /api/auth/logout
//   refreshAccessToken()          → 用 refresh_token 换新 access_token（axios 拦截器自动调用）
//   fetchMe()                     → 获取当前用户信息
//   register(username, pw, mid)   → 注册
//   changePassword(oldPw, newPw)  → 修改密码
''')

doc.add_heading('projectStore', level=3)
code_block(doc, '''// stores/project.ts
interface ProjectState {
  list: Project[]              // 项目列表（分页缓存）
  current: Project | null      // 当前详情项目
  total: number
  loading: boolean
  filters: ProjectFilters
}

// Actions:
//   fetchList(filters?)         → GET /api/projects（支持筛选+分页+搜索）
//   fetchDetail(id)             → GET /api/projects/{id}（缓存 current）
//   create(data)                → POST /api/projects
//   update(id, data)            → PUT /api/projects/{id}
//   softDelete(id)              → DELETE /api/projects/{id}
//   copyProject(id, newCode)    → POST /api/projects/{id}/copy
//   fetchStats(id)              → GET /api/projects/{id}/stats

// Getters:
//   blockedProjects             → list.filter(p => p.overall_status === 'blocked')
//   atRiskProjects              → list.filter(p => p.overall_status === 'at_risk')
//   projectsByPhase             → groupBy(list, 'current_phase_id')
''')

doc.add_heading('dashboardStore', level=3)
code_block(doc, '''// stores/dashboard.ts
interface DashboardState {
  summary: DashboardSummary | null      // 汇总数据
  alerts: Alert[]                       // 告警列表
  pendingReports: Project[]             // 待填周报项目
}

// Actions:
//   fetchDashboard()            → GET /api/dashboard
//   fetchAlerts()               → GET /api/dashboard/alerts
//   fetchPendingReports()       → GET /api/dashboard/pending-reports
//   takeSnapshot()              → POST /api/dashboard/health-snapshot
''')

doc.add_heading('lookupStore (参考数据缓存)', level=3)
code_block(doc, '''// stores/lookup.ts — 应用启动时加载一次，全局缓存
interface LookupState {
  phases: Phase[]
  gates: Gate[]
  technicalLines: TechnicalLine[]
  roles: Role[]
  docTypes: DocTypeGroup[]       // P0/PP1/PP2 三级分类
}

// Actions:
//   fetchAll()                  → 并行请求所有 /api/lookups/* 端点
// Getters:
//   phaseById(id)               → 快速查找
//   lineById(id)                → 快速查找
//   docTypeLabel(type)          → 根据 doc_type 返回中文标签
''')

doc.add_heading('4.3  路由设计', level=2)
code_block(doc, '''// router/index.ts
const routes = [
  { path: '/login',              component: LoginPage,        meta: { guest: true } },
  { path: '/',                   component: DashboardPage,    meta: { auth: true } },
  { path: '/projects',           component: ProjectListPage,  meta: { auth: true } },
  { path: '/projects/new',       component: ProjectCreatePage, meta: { auth: true } },
  { path: '/projects/:id',       component: ProjectDetailPage, meta: { auth: true } },
  { path: '/projects/:id/edit',  component: ProjectCreatePage, meta: { auth: true } },
  { path: '/milestones',         component: MilestonePage,    meta: { auth: true } },
  { path: '/my-work',            component: MyWorkPage,       meta: { auth: true } },
  { path: '/audit-logs',         component: AuditLogPage,     meta: { auth: true, role: 'admin' } },
  { path: '/resources',          component: ResourcePage,     meta: { auth: true } },
  { path: '/settings',           component: SettingsPage,     meta: { auth: true, role: 'admin' } },
]

// 导航守卫：
//   1. 未登录 → redirect /login
//   2. 已登录访问 /login → redirect /
//   3. role 校验（如 audit-logs 仅 admin）
//   4. 页面切换前自动 fetch lookupStore (仅首次)
''')

doc.add_heading('4.4  API 层封装 (axios)', level=2)
code_block(doc, '''// api/client.ts — axios 实例
const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截器：自动注入 access_token
apiClient.interceptors.request.use(config => {
  const token = authStore.accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截器：401 → 自动 refresh → 重试原请求（最多1次）
apiClient.interceptors.response.use(
  response => response,
  async error => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      await authStore.refreshAccessToken()        // 用 refresh_token 换新
      original.headers.Authorization = `Bearer ${authStore.accessToken}`
      return apiClient(original)                  // 重试
    }
    if (error.response?.status === 401 && original._retry) {
      authStore.logout()                          // refresh也失败 → 强制登出
      router.push('/login')
    }
    return Promise.reject(error)
  }
)

// 统一错误处理
function handleError(error: AxiosError): never {
  if (error.response?.status === 403) {
    ElMessage.error('权限不足')
  } else if (error.response?.status === 404) {
    ElMessage.error('资源不存在')
  } else if (error.response?.status === 422) {
    // Pydantic 验证错误 → 提取字段级错误信息
    const detail = error.response.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '数据验证失败')
  } else if (error.response?.status === 413) {
    ElMessage.error('文件过大，单文件上限 100MB')
  } else if (error.response?.status >= 500) {
    ElMessage.error('服务器错误，请稍后重试')
  } else if (error.code === 'ECONNABORTED') {
    ElMessage.error('请求超时')
  } else if (!error.response) {
    ElMessage.error('网络连接失败，请检查网络')
  }
  throw error
}
''')

doc.add_page_break()

# ════════════════════════════════════════════════════
# 5. 边界条件与异常处理
# ════════════════════════════════════════════════════
doc.add_heading('5  边界条件与异常处理', level=1)

doc.add_heading('5.1  认证与鉴权边界', level=2)
add_table(doc,
    ['场景', '处理方式'],
    [
        ['Token 过期 (30min)', 'axios 拦截器检测 401 → 自动用 refresh_token 换新 access_token → 重试原请求 → 用户无感知'],
        ['Refresh Token 也过期 (7d)', '清除所有 token → 跳转登录页 → 提示"登录已过期，请重新登录"'],
        ['Token 被篡改', 'jwt.decode() 抛出 InvalidSignatureError → 返回 401 → 前端走 refresh 流程'],
        ['并发请求同时触发 refresh', '用 Promise 锁：第一个 401 发起 refresh，后续 401 排队等待同一 Promise 结果'],
        ['无 token 访问受保护端点', '中间件返回 401 → 前端导航守卫已拦截，不会发起请求'],
        ['admin 专属端点 (如 /audit-logs)', '依赖注入 Depends(require_admin) 检查 user.role → 403 Forbidden'],
        ['账号被禁用 (is_active=False)', '登录时返回 403 "账号已被禁用" → 不生成 token'],
        ['密码暴力破解', '速率限制：同一 IP 5分钟内最多5次登录失败 → 429 Too Many Requests → 锁定15分钟'],
    ]
)

doc.add_heading('5.2  并发写入冲突', level=2)
add_table(doc,
    ['场景', '处理方式'],
    [
        ['两人同时编辑同一项目', '乐观锁：project 表增加 version 字段 (INTEGER)，每次 PUT 检查 version 匹配 → 不匹配返回 409 Conflict → 提示"数据已被他人修改，请刷新后重试"'],
        ['同周重复提交周报', 'DAO 层 ON CONFLICT (project_id, year, week_number) DO UPDATE → 自动转为更新 → 返回 200 + "已更新"'],
        ['同一文件被同时替换', '文档替换操作使用 SELECT ... FOR UPDATE 行锁 → 串行化执行 → 版本号正确递增'],
        ['批量导入时部分失败', '使用 PostgreSQL SAVEPOINT → 逐行处理 → 失败行记录到 error_log → 成功行提交'],
    ]
)

doc.add_heading('5.3  文件上传安全边界', level=2)
add_table(doc,
    ['场景', '处理方式'],
    [
        ['文件扩展名伪装 (.exe 改为 .pdf)', '用 python-magic 检查文件头魔术字节 → 不匹配返回 400 "文件类型不匹配"'],
        ['超大文件 (>100MB)', 'FastAPI Request 中间件检查 Content-Length → 超限返回 413 "文件过大" → 不读取文件体'],
        ['文件名包含路径穿越 (../../etc/passwd)', 'secure_filename() 处理：去除路径分隔符、只保留字母数字中文下划线点 → UUID前缀避免冲突'],
        ['空文件上传 (0字节)', '检查 file.size == 0 → 返回 400 "不允许空文件"'],
        ['并发上传同一文件', 'UUID 前缀保证文件名唯一 → 不会覆盖'],
        ['上传目录磁盘满', '捕获 OSError (ENOSPC) → 返回 507 "存储空间不足，请联系管理员"'],
        ['文件被删除后访问', '检查 os.path.exists() → 不存在返回 404 + "文件已被删除" → 数据库记录状态更新为失效'],
    ]
)

doc.add_heading('5.4  日期/周次计算边界', level=2)
add_table(doc,
    ['场景', '处理方式'],
    [
        ['跨年周 (如2025-12-29 ~ 2026-01-04)', '使用 Python datetime.isocalendar() → 返回 (2026, 1, 1) → 正确处理 ISO 8601 周历'],
        ['年初第一周可能属于上一年 (如2026-01-01)', "isocalendar() 返回 (2025, 53, 4) → year=2025, week=53 → 周报归属正确"],
        ['周五计算', "report_date = today + timedelta((4 - today.weekday()) % 7) → 周一~周日 都算出本周五"],
        ['里程碑逾期判定', "planned_date < date.today() AND status != 'completed' → overdue → 前端红色高亮"],
        ['阶段日期不合法 (结束早于开始)', 'Pydantic @model_validator → 检查 end >= start → 422 "结束日期不能早于开始日期"'],
    ]
)

doc.add_heading('5.5  级联删除与软删除', level=2)
add_table(doc,
    ['场景', '处理方式'],
    [
        ['删除项目', '软删除：设置 is_active=False → 关联数据保留 → 列表默认过滤 is_active=True'],
        ['恢复已删除项目', '手动 SQL: UPDATE project SET is_active=TRUE WHERE id=X → 暂无 UI（管理员通过数据库操作）'],
        ['删除里程碑', '硬删除 → PostgreSQL CASCADE: 仅删除该行，无级联子表 → 周报引用 milestone_id 设为 NULL (SET NULL)'],
        ['删除风险/问题', '硬删除 → 审计日志已有记录 → 可追溯"谁在何时删了什么"'],
        ['删除有版本的文档', '检查 replaced_by 链 → 如果是最新版，将其前一个版本标记为 active → 否则从链中移除并更新前后指针'],
        ['删除团队成员 (在项目中)', '检查是否有未关闭的风险/待办 → 有则提示"该成员有N个待处理项，请先转交" → 否则允许删除'],
    ]
)

doc.add_heading('5.6  网络断连与重试', level=2)
add_table(doc,
    ['场景', '处理方式'],
    [
        ['请求超时 (30s)', 'axios 超时返回 ECONNABORTED → 提示"请求超时" → 用户手动重试'],
        ['服务器宕机 (ECONNREFUSED)', '提示"服务暂不可用" → 每30s轮询一次健康检查 → 恢复后自动重连'],
        ['文件上传中断', '提示"上传中断，请重试" → 服务端清理已写入的部分文件 (try/finally)'],
        ['导出大文件超时', '改为异步：POST /api/export/async → 返回 task_id → 轮询 GET /api/export/status/{task_id} → 完成后返回下载链接'],
    ]
)

doc.add_heading('5.7  大数据量导出边界', level=2)
add_table(doc,
    ['场景', '处理方式'],
    [
        ['导出100+项目', '使用 openpyxl write_only 模式 → 流式写入 → 不在内存中构建整个 workbook'],
        ['导出52周周报 × 6技术线', '按周分批查询 (每次4周) → 流式写入 → 避免加载全部数据到内存'],
        ['导出文件过大 (>50MB)', '提示"导出数据量较大，可能需要1-2分钟" → 显示进度 → 完成后触发下载'],
    ]
)

doc.add_page_break()

# ════════════════════════════════════════════════════
# 6. 数据一致性保障
# ════════════════════════════════════════════════════
doc.add_heading('6  数据一致性保障方案', level=1)

doc.add_heading('6.1  事务隔离级别', level=2)
doc.add_paragraph(
    'PostgreSQL 默认隔离级别：READ COMMITTED（读已提交），满足绝大多数业务场景。\n\n'
    '升级为 REPEATABLE READ 的场景：\n'
    '  • 周报 UPSERT: 先 SELECT 检查是否存在 → 不存在则 INSERT → 并发下可能重复插入\n'
    '    → 解决方案：使用 ON CONFLICT ... DO UPDATE 原子操作，无需升级隔离级别\n'
    '  • 文档替换 (版本链): 先 UPDATE 旧文档 status → INSERT 新文档 → 两个操作必须原子\n'
    '    → 解决方案：包装在同一个 async session 事务中，commit() 时原子提交\n'
    '  • 项目复制: 批量 INSERT phase_gates + deliverables → 部分失败需全部回滚\n'
    '    → 解决方案：使用 SAVEPOINT 或整个操作在单一事务中，失败自动 ROLLBACK'
)

doc.add_heading('6.2  乐观锁 (Optimistic Locking)', level=2)
code_block(doc, '''# model: project 表增加 version 字段
class Project(Base):
    version = Column(Integer, default=1, nullable=False)

# service: update 时检查版本
async def update_project(db: AsyncSession, project_id: int, data: ProjectUpdate, expected_version: int):
    result = await db.execute(
        update(Project)
        .where(Project.id == project_id, Project.version == expected_version)
        .values(**data.model_dump(exclude_unset=True), version=Project.version + 1)
        .returning(Project.version)
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail="数据已被他人修改，请刷新页面后重试"
        )
    await db.commit()
    return {"new_version": row[0]}

# 前端使用：加载时记录 project.version，提交时发送
# 收到 409 → ElMessage.warning("数据已被他人修改") → 重新加载页面
''')

doc.add_heading('6.3  唯一约束 + ON CONFLICT UPSERT', level=2)
code_block(doc, '''# WeeklyReport: 每项目每周只有一份 → UPSERT 语义
async def upsert_weekly_report(db: AsyncSession, project_id: int, year: int, week: int, data: WeeklyReportCreate):
    stmt = insert(WeeklyReport).values(
        project_id=project_id,
        year=year,
        week_number=week,
        report_date=data.report_date,
        overall_progress=data.overall_progress,
        key_accomplishments=data.key_accomplishments,
        completion_rate=data.completion_rate,
        reporter_id=data.reporter_id,
    )
    stmt = stmt.on_conflict_do_update(
        constraint='uq_weekly_report_project_year_week',  # UNIQUE(project_id, year, week_number)
        set_={
            'report_date': stmt.excluded.report_date,
            'overall_progress': stmt.excluded.overall_progress,
            'key_accomplishments': stmt.excluded.key_accomplishments,
            'completion_rate': stmt.excluded.completion_rate,
            'reporter_id': stmt.excluded.reporter_id,
        }
    ).returning(WeeklyReport.id)

    result = await db.execute(stmt)
    report_id = result.scalar_one()
    await db.commit()

    # 然后 UPSERT line_items 同理
    for line_item in data.line_items:
        line_stmt = insert(WeeklyReportLine).values(
            report_id=report_id, line_id=line_item.line_id,
            this_week=line_item.this_week, next_week=line_item.next_week,
            status=line_item.status, blocker=line_item.blocker,
            coordinator=line_item.coordinator,
        )
        line_stmt = line_stmt.on_conflict_do_update(
            constraint='uq_report_line',  # UNIQUE(report_id, line_id)
            set_={...}
        )
        await db.execute(line_stmt)
    await db.commit()
    return report_id
''')

doc.add_heading('6.4  健康快照一致性', level=2)
doc.add_paragraph(
    '驾驶舱首页需要显示"新发风险数""本周完成里程碑"等聚合指标。计算方式：\n\n'
    '  方案A（当前）：每次请求时实时聚合查询 → 数据始终最新，但复杂查询可能慢\n'
    '  方案B（优化）：定时任务（每天凌晨2点）生成 ProjectHealthSnapshot → 首页读快照表 → 毫秒级响应\n\n'
    'v2.0 混合方案：\n'
    '  • 驾驶舱首页 → 读最新快照 + 实时补充今天的变化（增量 merge）\n'
    '  • 个人工作台 → 完全实时查询（数据量小，仅当前用户相关项目）\n'
    '  • 快照生成：Celery Beat 定时任务 / APScheduler + asyncpg\n'
    '  • 降级：如果快照表为空，fallback 到实时聚合查询'
)

doc.add_heading('6.5  文件-数据库一致性', level=2)
doc.add_paragraph(
    '文件上传操作涉及两阶段：写入磁盘 + 写入数据库。一致性保障：\n\n'
    '  1. 先写文件到磁盘（临时目录）\n'
    '  2. 数据库 INSERT document 记录（含 file_path）\n'
    '  3. 如果数据库写入失败 → 删除临时文件 (try/except/finally)\n'
    '  4. 将文件从临时目录移动到正式目录 (os.rename 原子操作)\n'
    '  5. 事务提交 → 如果提交失败，os.rename 可回滚（移回临时目录）\n\n'
    '定期一致性检查（每周日凌晨）：\n'
    '  • 扫描 project_document 表，检查每条记录对应的 file_path 是否存在\n'
    '  • 文件缺失 → 标记 status = "file_missing"\n'
    '  • 孤儿文件（磁盘有但数据库无记录）→ 移动到 orphan_files/ 目录，保留7天后删除\n'
)

doc.add_heading('6.6  备份策略', level=2)
add_table(doc,
    ['备份类型', '频率', '方式', '保留'],
    [
        ['全量备份 (pg_dump)', '每天凌晨3:00', 'pg_dump -Fc motor_pm > backup_$(date +%Y%m%d).dump', '最近7天'],
        ['WAL 归档', '持续（每5分钟）', 'archive_command = cp %p /backup/wal/%f', '最近3天'],
        ['文件备份', '每天凌晨4:00', 'rsync -a data/uploads/ /backup/uploads/', '最近7天'],
        ['异地备份', '每周日', 'rclone sync /backup/ s3:pm-backup/', '最近4周'],
        ['备份验证', '每天凌晨5:00', 'pg_restore --verify 验证最近备份完整性', '输出报告'],
    ]
)
doc.add_paragraph(
    '恢复流程：\n'
    '  1. 停止 FastAPI 服务\n'
    '  2. pg_restore -d motor_pm backup_YYYYMMDD.dump\n'
    '  3. 恢复 uploads/ 文件\n'
    '  4. 运行一致性检查脚本\n'
    '  5. 启动服务'
)

doc.add_page_break()

# ════════════════════════════════════════════════════
# 7. 部署架构
# ════════════════════════════════════════════════════
doc.add_heading('7  部署架构', level=1)

code_block(doc, '''┌─────────────────────────────────────────────────────────┐
│                    用户访问层                              │
│  浏览器 (Vue3 SPA)    钉钉/企业微信 (Webhook 通知)         │
└──────────┬──────────────────────┬───────────────────────-──┘
           │                      │
    内网直连                      │
    http://IP:5000         ngrok/Cloudflare Tunnel
           │                      │
┌──────────┴──────────────────────┴───────────────────────-──┐
│                    Nginx (反向代理)                         │
│  • 静态文件服务 (dist/)                                     │
│  • API 代理 → uvicorn (unix socket)                         │
│  • HTTPS 终结 (Let's Encrypt cert)                          │
│  • 请求限流 (limit_req_zone)                                │
│  • 最大上传体 client_max_body_size 100m                     │
└──────────────────────┬────────────────────────────────────-─┘
                       │
┌──────────────────────┴────────────────────────────────────-─┐
│              FastAPI (uvicorn workers=4)                     │
│  • 异步数据库查询 (asyncpg)                                  │
│  • Pydantic 请求验证                                        │
│  • JWT 认证中间件                                            │
│  • 审计日志中间件 (自动记录 CUD 操作)                        │
│  • 文件上传处理                                              │
│  • CORS 配置 (允许 ngrok/内网域名)                           │
└──────────────────────┬────────────────────────────────────-─┘
                       │
┌──────────────────────┴────────────────────────────────────-─┐
│              PostgreSQL 16 (本地 / 内网服务器)                │
│  • connection_pool_size = 20                                 │
│  • max_overflow = 10                                        │
│  • statement_timeout = 30s                                   │
│  • idle_in_transaction_timeout = 60s                        │
└────────────────────────────────────────────────────────────-─┘
''')

doc.add_heading('环境变量配置', level=2)
code_block(doc, '''# .env
DATABASE_URL=postgresql+asyncpg://motor_pm:password@localhost:5432/motor_pm
SECRET_KEY=<random-64-chars>
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
UPLOAD_DIR=D:/AI/motor-pm/data/uploads
MAX_UPLOAD_SIZE_MB=100
CORS_ORIGINS=http://localhost:5000,https://xxx.ngrok-free.dev
# 可选：钉钉 webhook
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxx
''')

doc.add_page_break()

# ════════════════════════════════════════════════════
# 8. 迁移路线图
# ════════════════════════════════════════════════════
doc.add_heading('8  迁移路线图 (Flask → FastAPI)', level=1)

add_table(doc,
    ['阶段', '内容', '工时(人天)', '风险'],
    [
        ['M1: 基础设施', 'FastAPI 项目骨架 + asyncpg + Alembic + Pydantic models + 配置管理', '2', '无，纯新代码'],
        ['M2: 数据迁移', 'SQLite → PostgreSQL 数据迁移脚本 + Alembic 初始迁移 + 种子数据', '1', '编码问题(UTF-8)，已处理过'],
        ['M3: 认证模块', 'JWT auth + refresh token + 中间件 + 速率限制', '1.5', '低，逻辑清晰'],
        ['M4: 核心API(上)', 'projects + milestones + weekly_reports + risks + changes', '3', '中，业务逻辑多'],
        ['M5: 核心API(下)', 'deliverables + documents + dashboard + my-work + export', '3', '中，聚合查询复杂'],
        ['M6: 审计+文件', 'audit middleware + file upload + storage stats', '1.5', '低'],
        ['M7: 前端适配', 'axios 拦截器 → Pinia → 适配新API响应格式 (Pydantic camelCase)', '2', '低，响应格式变化小'],
        ['M8: 测试+部署', 'pytest (async) + Nginx 配置 + 备份脚本 + 上线', '2', '低'],
    ]
)
doc.add_paragraph(
    '总工时估算：16 人天\n'
    '迁移策略：渐进式 → 新旧系统并行运行1周 → 确认稳定后切换 → 保留 Flask 代码作为回退\n'
    '前端兼容性：API 响应格式通过 Pydantic alias 保持与旧格式一致 → 前端改动最小化'
)

doc.add_page_break()

# ── 保存 ──────────────────────────────────────────
output_dir = os.path.dirname(os.path.abspath(__file__))
output_path = os.path.join(output_dir, '电机项目管理工具_架构设计说明书_v2.0.docx')
doc.save(output_path)
print(f'Document saved to: {output_path}')
print(f'File size: {os.path.getsize(output_path):,} bytes')
