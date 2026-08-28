"""Generate the Motor PM Tool Requirements Document (Word)."""
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
import os

doc = Document()

# ── Page setup ──
for section in doc.sections:
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

style = doc.styles['Normal']
style.font.name = '微软雅黑'
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
style.paragraph_format.space_after = Pt(6)
style.paragraph_format.line_spacing = 1.35

# Helper functions
def heading(text, level=1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.name = '微软雅黑'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    return h

def para(text, bold=False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.font.name = '微软雅黑'
    run.font.size = Pt(10.5)
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    return p

def add_table(headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Light Grid Accent 1'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Header
    for i, h_text in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h_text
        for p in cell.paragraphs:
            for run in p.runs:
                run.bold = True
                run.font.size = Pt(9)
    # Data
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = table.rows[r + 1].cells[c]
            cell.text = str(val)
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)
    doc.add_paragraph()
    return table

# ══════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════
doc.add_paragraph()
doc.add_paragraph()
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('电机设计与控制项目管理工具')
run.bold = True
run.font.size = Pt(26)
run.font.name = '微软雅黑'
run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = sub.add_run('需求规格说明书')
run.font.size = Pt(16)
run.font.name = '微软雅黑'
run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')

doc.add_paragraph()
info = doc.add_paragraph()
info.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = info.add_run('版本：V1.0\n日期：2026-06-18\n行业领域：电机设计 + 电机控制设计')
run.font.size = Pt(11)
run.font.name = '微软雅黑'
run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')

doc.add_page_break()

# ══════════════════════════════════════════════
# 1. OVERVIEW
# ══════════════════════════════════════════════
heading('1 项目概述', 1)
heading('1.1 项目背景', 2)
para('公司从事电机设计与电机控制设计业务，涉及多条技术线并行协作。'
     '传统管理方式依赖Excel表格和钉钉群沟通，存在信息分散、版本混乱、'
     '进展不透明等问题。需要一个统一的Web端项目管理工具来支撑从立项到量产交付的全过程管理。')

heading('1.2 项目目标', 2)
para('构建一个面向电机设计+控制设计行业的专属项目管理平台，覆盖项目立项、'
     '阶段门径（Phase-Gate）管理、多技术线协同、周报跟踪、风险管理、变更管理、'
     '交付物追踪等全流程需求，支持多人协同使用、文件管理、自动化提醒等功能。')

heading('1.3 技术栈', 2)
add_table(
    ['层级', '技术选型', '说明'],
    [
        ['前端', 'Vue 3 + Element Plus', '组件化UI、中文生态完善'],
        ['后端', 'Python Flask', '轻量级REST API'],
        ['数据库', 'SQLite', '零配置、单文件部署、适合本地存储'],
        ['认证', 'JWT Token', '无状态登录、支持跨域'],
        ['公网访问', 'ngrok 隧道', '内网穿透、外网可访问'],
        ['文件存储', '本地文件系统', 'data/uploads/ 目录存储附件'],
        ['定时任务', 'Cron / Windows计划任务', '周报催办自动化'],
        ['消息推送', '钉钉机器人 Webhook', '群消息提醒'],
    ]
)

heading('1.4 部署架构', 2)
para('单机部署模式：Flask后端+SQLite+前端静态文件，运行在一台Windows电脑上。'
     '通过ngrok内网穿透实现外网访问。启动方式：python run.py 或双击 start_all.bat。')

doc.add_page_break()

# ══════════════════════════════════════════════
# 2. USER & AUTH
# ══════════════════════════════════════════════
heading('2 用户与权限管理', 1)

heading('2.1 用户角色', 2)
add_table(
    ['角色', '权限说明'],
    [
        ['管理员 (admin)', '查看所有项目、管理系统设置、管理用户'],
        ['项目经理 (PM)', '创建/编辑/删除项目、管理团队、审批变更'],
        ['团队成员 (member)', '填写周报、提交交付物、管理风险问题'],
    ]
)

heading('2.2 账号体系', 2)
para('用户名采用姓名全拼（全小写）格式，如 jinzhaohai、wangmingxuan。'
     '支持新用户自助注册，注册后默认角色为 member。')

heading('2.3 认证机制', 2)
para('采用JWT Token认证机制。登录后获取Token，前端存储在localStorage，'
     '后续API请求在Header中携带Token。Token有过期时间，过期后自动跳转登录页。')

doc.add_page_break()

# ══════════════════════════════════════════════
# 3. PROJECT MANAGEMENT
# ══════════════════════════════════════════════
heading('3 项目管理', 1)

heading('3.1 项目编号规则', 2)
para('统一格式：客户缩写-年份-序号。如 YPS-2026-001 表示优普森电气2026年第1个项目。'
     '客户缩写取公司名称拼音首字母大写。')

heading('3.2 项目基本信息', 2)
add_table(
    ['字段', '类型', '说明'],
    [
        ['项目编号', '文本', '按统一编号规则填入'],
        ['项目名称', '文本', '项目名称'],
        ['项目描述', '多行文本', '项目整体描述'],
        ['客户ID', '外键', '关联客户信息表'],
        ['优先级', '枚举', 'P0（最高）/ P1 / P2 / P3'],
        ['截止日期类型', '枚举', '硬性 / 柔性'],
        ['难度', '枚举', '低 / 中 / 高'],
        ['总预算', '数字', '项目总预算金额'],
        ['已花费预算', '数字', '已支出金额'],
        ['当前阶段', '外键', '关联6个标准阶段'],
        ['整体状态', '枚举', '正常 / 风险 / 阻塞'],
        ['主要阻塞项', '文本', '当前阻塞原因'],
        ['阻塞持续时间', '枚举', '<1周 / 1-4周 / >4周'],
        ['团队士气', '枚举', '高 / 中等 / 低'],
    ]
)

heading('3.3 项目目标四要素', 2)
para('每个项目必须明确以下四项（按显示顺序）：')
para('1) 最终交付物 —— 项目完成后输出的具体成果')
para('2) 验收标准 —— 量化的验收指标')
para('3) 要解决的问题 —— 项目要解决的业务/技术痛点')
para('4) 对齐目标 —— 与公司战略的关联')

heading('3.4 客户信息管理', 2)
para('独立客户信息表（Client），一个客户可关联多个项目。'
     '包括：客户名称、缩写、地址、电话、对接人、对接人职位、对接人联系方式、备注。'
     '在"系统设置 → 客户管理"中统一维护，项目创建时下拉选择已有客户。')

heading('3.5 删除机制', 2)
para('采用软删除：标记 is_active=False，数据保留在数据库中。'
     '项目列表默认只显示活跃项目。可通过修改数据库字段恢复。')

doc.add_page_break()

# ══════════════════════════════════════════════
# 4. PHASE-GATE MANAGEMENT
# ══════════════════════════════════════════════
heading('4 阶段门径管理', 1)

heading('4.1 六阶段模型', 2)
add_table(
    ['阶段', '编号', '说明', '对应门径'],
    [
        ['概念阶段', 'Phase 1', '确认要不要做、能不能做、划不划算', '-'],
        ['方案阶段', 'Phase 2', '方案设计、技术路线选定', 'G1 方案评审'],
        ['详细设计', 'Phase 3', '各专业详细设计、图纸、仿真', 'G2 设计评审'],
        ['样机试制', 'Phase 4', '样机制造、装配、调试', 'G3 试制评审'],
        ['测试验证', 'Phase 5', '部件测试、集成测试、型式试验', 'G4 测试评审'],
        ['量产交付', 'Phase 6', '量产准备、文件归档、项目移交', 'G5 量产评审'],
    ]
)

heading('4.2 步骤条视图', 2)
para('横向步骤条展示6个阶段，每个阶段用颜色标识状态：绿色=已完成、蓝色=进行中、灰色=未开始。'
     '点击阶段圆圈可弹窗编辑：日期、评审状态、门径负责人。')

heading('4.3 树状图视图', 2)
para('SVG流程图：6阶段主干用带箭头虚线串联，每个阶段右上角显示门径标签（G1~G5）。'
     '每个阶段下展开6条技术线作为分支叶子节点，方块颜色表示交付物状态：'
     '绿色=已批准、蓝色=已提交、橙色=未提交、灰色=无交付物。'
     '支持悬停显示提示、点击方块跳转到交付物Tab。')

heading('4.4 门径评审', 2)
para('每个阶段结束时需经过对应门径评审。支持：')
para('- 设定评审日期、评审人')
para('- 记录评审结论（通过/有条件通过/不通过/暂缓）')
para('- 记录评审意见和待办事项')

doc.add_page_break()

# ══════════════════════════════════════════════
# 5. SIX TECHNICAL LINES
# ══════════════════════════════════════════════
heading('5 技术线管理', 1)
para('电机项目6条标准技术线：')
add_table(
    ['技术线', '简称', '负责范围'],
    [
        ['电机电磁', '电磁', '电磁方案设计、磁路仿真、效率计算、绕组设计'],
        ['电机结构', '结构', '3D建模、结构强度分析、散热设计、装配工艺'],
        ['控制硬件', '硬件', '控制器硬件设计、原理图、PCB Layout、EMC'],
        ['控制算法', '算法', 'FOC算法、无感控制、参数辨识、仿真验证'],
        ['控制软件', '软件', '嵌入式代码、通信协议、上位机软件、刷写工具'],
        ['测试验证', '测试', '台架测试、型式试验、NVH测试、可靠性验证'],
    ]
)
para('每阶段有6×6=36个交付物节点，按"阶段×技术线"矩阵管理。')

# ══════════════════════════════════════════════
# 6. MILESTONE
# ══════════════════════════════════════════════
heading('6 里程碑管理', 1)
para('支持甘特图和表格双视图：')
para('- 甘特图：横向时间轴展示里程碑时间线和依赖关系')
para('- 表格：列表形式CRUD操作（添加/编辑/删除）')
para('- 关键里程碑标记（is_key），在仪表盘重点展示')
para('- 里程碑全景视图：跨项目甘特图，可按项目筛选')

doc.add_page_break()

# ══════════════════════════════════════════════
# 7. WEEKLY REPORT
# ══════════════════════════════════════════════
heading('7 周报系统', 1)

heading('7.1 6线填报机制', 2)
para('按6条技术线分别填写，每周一条记录（以周五为报告日期）。每行包含：')
add_table(
    ['字段', '说明'],
    [
        ['所属技术线', '电磁/结构/硬件/算法/软件/测试'],
        ['本周进展', '本周完成的工作内容'],
        ['进展状态', '正常/有风险/阻塞'],
        ['下周计划', '下周计划开展的工作'],
        ['风险/难点', '当前遇到的困难和风险'],
        ['需要支持', '需要协调的资源或帮助'],
    ]
)

heading('7.2 智能拆解', 2)
para('粘贴大段工作内容文字后，系统按关键词自动识别技术线并填入对应行。'
     '支持关键词映射：如"仿真"→电磁/算法、"PCB"→硬件、"代码"→软件、"3D"→结构、"台架"→测试等。'
     '未识别内容保留提示，可手动补充。')

heading('7.3 自动填充', 2)
para('新建周报时，自动将该项目的上一期周报"下周计划"填入当前"本周进展"中作为参考，'
     '减少重复填写工作量。')

heading('7.4 历史查看', 2)
para('周报按时间线展示，支持查看任一期周报详情。'
     '同一周重复提交自动转为更新（UPSERT机制）。')

heading('7.5 定期提醒', 2)
para('三层提醒机制：')
para('- 仪表盘告警：首页蓝色提醒条显示未填周报的项目清单及上次填写日期')
para('- 钉钉催办：每两周自动发送钉钉群消息提醒未填人员')
para('- 定时任务：支持Windows计划任务/Cron定时触发催办脚本')

doc.add_page_break()

# ══════════════════════════════════════════════
# 8. RISK & CHANGE
# ══════════════════════════════════════════════
heading('8 风险与变更管理', 1)

heading('8.1 风险/问题管理', 2)
para('风险登记表，支持以下功能：')
para('- 风险/问题分级：概率（低/中/高）× 影响（低/中/高）→ 风险等级矩阵')
para('- 状态流转：识别中 → 处理中 → 已缓解 / 已关闭 / 已接受')
para('- 风险负责人、计划关闭日期')
para('- 缓解措施、应急计划')

heading('8.2 关闭验证', 2)
para('关闭风险/问题时，必须填写验证结果（必填）和上传附件（可选）。'
     '支持格式：PDF、Word、Excel、图片、压缩包、CAD文件。'
     '关闭后记录 resolution 和 attachment_path 字段。')

heading('8.3 变更管理', 2)
para('项目变更申请管理：')
para('- 变更等级：A（重大）/ B（一般）/ C（轻微）')
para('- 审批工作流：提交→审核→批准/驳回')
para('- 影响分析：对进度/成本/质量的影响评估')
para('- 变更记录可追溯')

doc.add_page_break()

# ══════════════════════════════════════════════
# 9. DELIVERABLES & DOCUMENTS
# ══════════════════════════════════════════════
heading('9 交付物与文档管理', 1)

heading('9.1 交付物矩阵', 2)
para('6阶段×6技术线的36节点矩阵视图：')
para('- 每个节点显示该位置交付物状态（已批准/已提交/未提交/无）')
para('- 支持提交文件、编辑、删除')
para('- 状态流转：未提交 → 已提交 → 已批准（或打回）')
para('- 与阶段门径树状图联动')

heading('9.2 项目文档管理', 2)
para('独立于交付物矩阵，管理立项前和过程中的文档。按三个阶段分类：')
add_table(
    ['类别', '包含文档类型'],
    [
        ['P0 需求阶段', '开发合同、技术协议、需求规格书、立项报告'],
        ['PP1 研发阶段', '仿真模型、设计报告、工程图纸、测试方案'],
        ['PP2 验证阶段', '样机测试报告、数据回归分析、改进计划、改进方案和报告'],
    ]
)

heading('9.3 文档上传与管理', 2)
para('功能要点：')
para('- 上传流程：选阶段 → 选类型 → 填名称 → 拖拽文件 → 保存')
para('- 支持30+文件格式（PDF/Word/Excel/CAD/图片/压缩包等）')
para('- 单文件上限100MB，总存储仅受硬盘空间限制')
para('- 点击文件名直接下载/预览')

heading('9.4 文件生命周期管理', 2)
para('三种状态：有效（绿色标签）/ 已替代（橙色+删除线）/ 失效（红色+删除线）')
para('- 失效操作：一键标记为作废，不删除物理文件')
para('- 替换操作：上传新版本→自动创建新记录、旧版本自动标记"已替代"、备注追加被替代信息')
para('- 版本追踪：V1→V2→V3自动递增，完整版本链可追溯')
para('- 存储用量仪表盘：在系统设置页查看已用空间、文件数量、磁盘剩余')

doc.add_page_break()

# ══════════════════════════════════════════════
# 10. DASHBOARD
# ══════════════════════════════════════════════
heading('10 驾驶舱首页', 1)

heading('10.1 页面布局（按优先级排列）', 2)
para('首页设计原则：先看风险、再看进度、最后看细节。')

add_table(
    ['区域', '优先级', '展示内容'],
    [
        ['告警条', 'P1 最高', '阻塞项目名称+阻塞原因，红色脉动动画'],
        ['统计卡片', 'P1 最高', '项目总数/阻塞/风险/正常，一秒钟了解整体健康度'],
        ['周报待办', 'P1 最高', '本周未填周报项目清单+上次填写日期，点击直跳周报页'],
        ['项目列表', 'P2 重要', '按风险优先排序（阻塞的排最上面），卡片形式展示'],
        ['里程碑', 'P3 参考', '近期关键里程碑+逾期节点红色高亮'],
        ['资源负载', 'P3 参考', '团队成员过载告警'],
    ]
)

heading('10.2 汇总维度', 2)
para('驾驶舱五大汇总：')
para('- 汇总一：项目整体状态、数量分布')
para('- 汇总二：阶段分布、门径评审状态')
para('- 汇总三：风险问题统计、按等级/状态/项目分类')
para('- 汇总四：变更统计、按等级/审批状态分类')
para('- 汇总五：团队资源负载、分配率统计')

doc.add_page_break()

# ══════════════════════════════════════════════
# 11. ACCESS & NETWORK
# ══════════════════════════════════════════════
heading('11 网络访问', 1)

heading('11.1 双地址方案', 2)
add_table(
    ['场景', '地址', '说明'],
    [
        ['公司内网', 'http://10.136.101.192:5000', '局域网直连，速度快'],
        ['外网出差', 'https://xxx.ngrok-free.dev', 'ngrok内网穿透，任意网络可访问'],
    ]
)

heading('11.2 ngrok 隧道', 2)
para('通过ngrok将本地5000端口映射到公网HTTPS地址。'
     '免费版每次重启PC后URL可能变化（同一台机器重连复用相同URL）。'
     '注意：Cloudflare Tunnel在公司网络（防火墙限制7844端口）不可用，ngrok走443端口更可靠。')

heading('11.3 一键启动', 2)
para('提供 start_all.bat 脚本，双击即可同时启动Flask后端和ngrok隧道。'
     '电脑需保持开机，python run.py 和 ngrok 都在运行，外网才能访问。')

# ══════════════════════════════════════════════
# 12. DATA & STORAGE
# ══════════════════════════════════════════════
heading('12 数据与存储', 1)
para('- 数据库：SQLite单文件（instance/目录），无大小限制')
para('- 文件存储：data/uploads/ 目录，仅受本地硬盘空间限制')
para('- 单文件上传上限：100MB')
para('- 支持文件格式：PDF、Word(.doc/.docx)、Excel(.xls/.xlsx)、图片(.png/.jpg/.bmp)、'
     'CAD(.step/.stp/.dwg/.dxf)、压缩包(.zip/.rar/.7z)等30+格式')
para('- 存储用量：系统设置页可查看已用空间、文件数、磁盘剩余、按类型分布')

# ══════════════════════════════════════════════
# 13. INTEGRATION
# ══════════════════════════════════════════════
heading('13 外部集成', 1)
para('- 钉钉机器人：支持通过Webhook发送群消息提醒（催办周报、告警通知）')
para('- Excel导入：支持从Excel批量导入项目数据（import_excel.py脚本）')
para('- 数据导出：项目数据可通过API获取JSON格式，未来可扩展Excel导出')

doc.add_page_break()

# ══════════════════════════════════════════════
# 14. FUTURE
# ══════════════════════════════════════════════
heading('14 后续规划', 1)
add_table(
    ['优先级', '功能', '说明'],
    [
        ['P0', '权限细化', '按项目分配权限，PM只能看到自己负责的项目'],
        ['P0', '操作日志', '记录关键操作审计日志（谁在何时做了什么）'],
        ['P1', '工时填报', '按技术线填报实际工时，对比计划进度'],
        ['P1', 'Excel导出', '仪表盘/周报/风险等数据一键导出Excel'],
        ['P1', '通知中心', '系统内消息通知（催办/审批/状态变更）'],
        ['P2', '邮件通知', '除钉钉外，支持邮件发送周报/提醒'],
        ['P2', '移动端适配', '响应式布局，手机端查看和填报'],
        ['P2', '数据看板大屏', '全屏驾驶舱模式，适合会议室投屏'],
        ['P3', 'API开放', '提供标准REST API供外部系统对接'],
        ['P3', '数据备份', '定时自动备份数据库和文件到指定目录'],
    ]
)

# ══════════════════════════════════════════════
# 15. APPENDIX
# ══════════════════════════════════════════════
heading('15 附录', 1)

heading('15.1 项目文件结构', 2)
para('''motor-pm/
├── backend/
│   ├── __init__.py          # Flask应用工厂
│   ├── models.py            # 数据模型（15+表）
│   ├── seed.py              # 种子数据
│   ├── utils.py             # 工具函数
│   ├── import_excel.py      # Excel导入脚本
│   ├── remind_weekly.py     # 周报催办脚本
│   ├── routes/
│   │   ├── auth.py          # 登录/注册API
│   │   ├── projects.py      # 项目CRUD API
│   │   ├── phases.py        # 阶段门径API
│   │   ├── milestones.py    # 里程碑API
│   │   ├── reports.py       # 周报API
│   │   ├── risks.py         # 风险/变更API
│   │   ├── deliverables.py  # 交付物API
│   │   ├── project_docs.py  # 项目文档API
│   │   ├── dashboard.py     # 驾驶舱API
│   │   ├── clients.py       # 客户管理API
│   │   ├── files.py         # 文件上传/存储API
│   │   └── settings.py      # 系统设置API
│   └── uploads/             # 上传文件存储
├── frontend/
│   └── src/
│       ├── pages/           # 页面组件
│       ├── components/      # 业务组件
│       └── main.js          # 入口文件
├── data/
│   ├── motor_pm.db          # SQLite数据库
│   └── uploads/             # 上传文件存储
├── run.py                   # 启动入口
├── start_all.bat            # 一键启动脚本
└── config.py                # 配置文件''')

heading('15.2 API端点清单', 2)
add_table(
    ['模块', '端点', '方法', '说明'],
    [
        ['认证', '/api/auth/login', 'POST', '用户登录'],
        ['认证', '/api/auth/register', 'POST', '用户注册'],
        ['项目', '/api/projects', 'GET/POST', '项目列表/创建'],
        ['项目', '/api/projects/<id>', 'GET/PUT/DELETE', '项目详情/编辑/删除'],
        ['阶段门径', '/api/projects/<id>/phase-gates', 'GET/PUT', '阶段门径数据'],
        ['里程碑', '/api/projects/<id>/milestones', 'GET/POST', '里程碑列表/创建'],
        ['里程碑', '/api/milestones/<id>', 'PUT/DELETE', '里程碑编辑/删除'],
        ['周报', '/api/projects/<id>/reports', 'GET/POST', '周报列表/创建'],
        ['周报', '/api/reports/<id>', 'GET/PUT', '周报详情/编辑'],
        ['风险', '/api/projects/<id>/risks', 'GET/POST', '风险列表/创建'],
        ['风险', '/api/risks/<id>', 'PUT/DELETE', '风险编辑/删除'],
        ['风险', '/api/risks/<id>/close', 'POST', '关闭风险(验证+附件)'],
        ['变更', '/api/projects/<id>/changes', 'GET/POST', '变更列表/创建'],
        ['交付物', '/api/projects/<id>/deliverables', 'GET/POST', '交付物列表/创建'],
        ['项目文档', '/api/projects/<id>/documents', 'GET/POST', '文档列表/上传'],
        ['项目文档', '/api/documents/<id>', 'PUT/DELETE', '文档编辑/删除'],
        ['客户', '/api/clients', 'GET/POST', '客户列表/创建'],
        ['文件', '/api/files/upload', 'POST', '文件上传'],
        ['文件', '/api/files/stats', 'GET', '存储用量统计'],
        ['驾驶舱', '/api/dashboard/summary', 'GET', '驾驶舱汇总'],
        ['驾驶舱', '/api/dashboard/todos', 'GET', '周报待办提醒'],
    ]
)

# ── Save ──
output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '电机项目管理工具_需求规格说明书.docx')
doc.save(output_path)
print(f'Saved to: {output_path}')
