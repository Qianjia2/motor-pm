"""
AI Report Generator — 从项目散落信息自动生成各类报告
支持: 技术协议, 阶段报告, 结题报告, 验收报告, 项目周报汇总, 风险分析报告
"""
import json
import uuid as _uuid
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path as FilePath

BJT = timezone(timedelta(hours=8))
def _now():
    return datetime.now(BJT)
def _today():
    return _now().date()

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from pptx import Presentation
from pptx.util import Inches, Pt as Pt2

from backend_v2.database import get_db
from backend_v2.auth import get_current_user, require_admin
from backend_v2.config import settings
from backend_v2.models import (
    Project, Milestone, WeeklyReport, RiskIssue, ChangeRequest,
    ProjectDocument, Deliverable, TestPlan, BomItem, PrototypeBuild, Phase,
)

router = APIRouter(tags=["report-gen"])

REPORT_TYPES = {
    "tech_agreement": {
        "name": "技术协议",
        "sections": ["项目概述", "技术指标与参数", "系统方案", "接口定义", "交付物清单",
                     "验收标准", "里程碑计划", "双方责任"],
        "prompt_extra": "生成一份正式的技术协议文档。使用专业术语，参数用表格呈现。",
    },
    "stage_report": {
        "name": "阶段报告",
        "sections": ["阶段概述", "本阶段目标与完成情况", "关键技术成果", "里程碑状态",
                     "风险与问题", "变更记录", "下阶段计划"],
        "prompt_extra": "生成当前阶段的汇报文档，重点突出本阶段成果与下阶段计划。",
    },
    "final_report": {
        "name": "结题报告",
        "sections": ["项目概况", "研制过程回顾", "技术方案总结", "测试验证结果",
                     "关键技术突破", "项目成果与创新点", "经验教训", "后续建议"],
        "prompt_extra": "生成完整的项目结题报告，引用实际数据和测试结果，正式严谨。",
    },
    "acceptance": {
        "name": "验收报告",
        "sections": ["验收概述", "验收依据与标准", "交付物核查", "性能指标测试",
                     "验收结论", "遗留问题", "验收签字"],
        "prompt_extra": "按照验收流程生成验收报告，逐项对照验收标准。",
    },
    "risk_analysis": {
        "name": "风险分析报告",
        "sections": ["风险概述", "风险登记表", "高风险项详细分析", "缓解措施",
                     "风险趋势", "建议"],
        "prompt_extra": "汇总当前所有未关闭风险，按严重度排序，重点分析高风险项。",
    },
    "weekly_summary": {
        "name": "周报汇总",
        "sections": ["周期概述", "各技术线进展汇总", "关键节点状态", "突出问题",
                     "下周重点"],
        "prompt_extra": "汇总所有技术线本周工作，合并同类项，提炼关键信息。",
    },
    "requirements_report": {
        "name": "需求报告",
        "sections": ["需求概述", "需求清单明细", "优先级分布", "来源分析",
                     "关联交付物", "变更历史", "需求覆盖率"],
        "prompt_extra": "汇总项目全部需求条目，按类别和优先级组织，生成结构化的需求规格汇总报告。包含功能/性能/接口/安全/可靠性/成本各类需求。",
    },
}


def _gather_project_data(db: Session, project_id: int) -> dict:
    """Collect all project data needed for report generation."""
    p = (db.execute(
        select(Project).where(Project.id == project_id).options(
            selectinload(Project.client),
            selectinload(Project.current_phase),
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    # Milestones
    milestones = (db.execute(
        select(Milestone).where(Milestone.project_id == project_id)
        .order_by(Milestone.phase_id, Milestone.planned_date)
    )).scalars().all()

    # Latest 5 weekly reports
    reports = (db.execute(
        select(WeeklyReport).where(WeeklyReport.project_id == project_id)
        .order_by(WeeklyReport.year.desc(), WeeklyReport.week_number.desc()).limit(5)
        .options(selectinload(WeeklyReport.line_items))
    )).scalars().all()

    # Risks
    risks = (db.execute(
        select(RiskIssue).where(RiskIssue.project_id == project_id)
        .order_by(RiskIssue.created_at.desc())
    )).scalars().all()

    # Changes
    changes = (db.execute(
        select(ChangeRequest).where(ChangeRequest.project_id == project_id)
        .order_by(ChangeRequest.submitted_date.desc())
    )).scalars().all()

    # Documents
    docs = (db.execute(
        select(ProjectDocument).where(ProjectDocument.project_id == project_id)
        .order_by(ProjectDocument.upload_date.desc())
    )).scalars().all()

    # Deliverables
    deliverables = (db.execute(
        select(Deliverable).where(Deliverable.project_id == project_id)
    )).scalars().all()

    # BOM items
    bom_items = (db.execute(
        select(BomItem).where(BomItem.project_id == project_id)
        .order_by(BomItem.level, BomItem.sort_order)
    )).scalars().all()

    # Test plans
    test_plans = (db.execute(
        select(TestPlan).where(TestPlan.project_id == project_id)
    )).scalars().all()

    # Prototype builds
    builds = (db.execute(
        select(PrototypeBuild).where(PrototypeBuild.project_id == project_id)
    )).scalars().all()

    # Requirements
    from backend_v2.models import Requirement as ReqModel
    requirements = (db.execute(
        select(ReqModel).where(ReqModel.project_id == project_id).order_by(ReqModel.priority, ReqModel.category)
    )).scalars().all()

    return {
        "project": {
            "name": p.name, "code": p.code, "description": p.description,
            "client": p.client.name if p.client else "",
            "phase": p.current_phase.name if p.current_phase else "",
            "priority": p.priority, "status": p.overall_status,
            "start_date": str(p.start_date) if p.start_date else "",
            "planned_end": str(p.planned_end_date) if p.planned_end_date else "",
        },
        "milestones": [
            {"name": m.name, "planned_date": str(m.planned_date) if m.planned_date else "",
             "status": m.status, "is_key": m.is_key, "phase": m.phase.name if m.phase else ""}
            for m in milestones
        ],
        "weekly_reports": [
            {"year": r.year, "week": r.week_number, "overall": r.overall_progress,
             "accomplishments": r.key_accomplishments,
             "lines": [{"line": li.line.name if li.line else "", "this_week": li.this_week,
                        "next_week": li.next_week, "blocker": li.blocker, "status": li.status}
                       for li in (r.line_items or [])]}
            for r in reports
        ],
        "risks": [
            {"title": r.title, "type": r.type, "severity": r.severity, "status": r.status,
             "mitigation": r.mitigation_plan}
            for r in risks if r.status != "closed"
        ],
        "changes": [
            {"title": c.title, "level": c.change_level, "status": c.status,
             "description": c.description, "impact": c.impact_scope}
            for c in changes
        ],
        "documents": [
            {"name": d.name, "type": d.doc_type, "status": d.status, "version": d.version}
            for d in docs
        ],
        "deliverables": [
            {"name": d.name, "phase": d.phase.name if d.phase else "", "status": d.status,
             "owner": d.owner.name if d.owner else "",
             "submitted_date": str(d.submitted_date) if d.submitted_date else "",
             "description": (d.description or "")[:200]}
            for d in deliverables
        ],
        "bom_summary": f"{len(bom_items)} 条BOM物料" if bom_items else "",
        "test_plans": [
            {"name": tp.name, "type": tp.test_type, "status": tp.status}
            for tp in test_plans
        ],
        "builds": [
            {"name": b.batch_name, "qty": f"{b.actual_qty}/{b.planned_qty}", "status": b.status}
            for b in builds
        ],
        "requirements": [
            {"title": r.title, "category": r.category, "priority": r.priority,
             "source": r.source, "status": r.status, "description": (r.description or "")[:400]}
            for r in requirements
        ],
        "requirements_count": len(requirements),
    }


def _build_prompt(report_type: str, context: str, data: dict, template: str = "") -> str:
    """Build the AI prompt for report generation."""
    rt = REPORT_TYPES[report_type]
    info = json.dumps(data, ensure_ascii=False, indent=2)

    template_instruction = ""
    if template:
        template_instruction = f"""
用户提供了自有模板，请严格按照此模板的章节结构、编号方式、表格格式来生成报告：
```
{template[:4000]}
```
"""

    return f"""{rt['prompt_extra']}
{template_instruction}
报告类型：{rt['name']}
项目名称：{data['project']['name']}

项目数据（JSON格式）：
{info[:8000]}

用户补充说明：
{context or '无'}

请按以下章节生成报告（Markdown格式）：
{', '.join(rt['sections'])}

要求：
1. 使用专业正式的语言
2. 从项目数据中提取实际内容填充各章节
3. 数据缺失的章节标注"（待补充）"
4. 技术参数用表格呈现
5. 标题用 ## 开头，子标题用 ###

只输出报告正文，无需额外说明。"""


def _call_ai(prompt: str) -> str:
    """Call Ollama directly to generate report."""
    try:
        from backend_v2.ai_service import CONFIG_PATH
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        if not cfg.get("enabled", True):
            return _template_report(prompt)

        model = cfg.get("model", "qwen2.5:0.5b")  # fast model for reports
        base_url = cfg.get("base_url", "http://localhost:11434/v1").rstrip("/")
        temperature = cfg.get("temperature", 0.7)
        max_tokens = cfg.get("max_tokens", 1024)

        import urllib.request as _ur
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个专业的电机设计项目管理报告撰写助手。请用中文生成正式的项目报告文档。严格按照用户要求的结构生成。只输出报告正文，不要写额外说明。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }).encode("utf-8")

        req = _ur.Request(
            f"{base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        with _ur.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]

    except Exception as e:
        print(f"[report-gen] AI error: {e}")
        return _template_report(prompt)


def _template_report(prompt: str) -> str:
    """Generate a template-based report when AI is unavailable."""
    lines = prompt.split("\n")
    proj_line = [l for l in lines if "项目名称" in l]
    proj_name = proj_line[0].split("：")[-1].strip() if proj_line else "未知项目"

    import traceback
    return f"""## AI 服务未启用

> 当前未连接到 AI 模型（Ollama），以下为项目数据汇总。

### 项目信息
- **项目名称**：{proj_name}
- **数据已就绪**：可预览下方 JSON 数据，安装 Ollama 后自动生成正式报告。

### 建议
1. 安装 Ollama：下载并安装后运行 `ollama pull qwen2.5:3b`
2. 在系统设置中配置 AI 模型
3. 重新生成报告即可获得正式文档

---

### 原始项目数据
```json
{prompt[:3000]}
```
"""


FILLED_TEMPLATE_RETENTION = 200  # 最多保留最新 200 个已填充模板，防 NAS 目录无限增长


def _prune_filled_templates(upload_dir):
    """删除最旧的填充模板，仅保留最新 FILLED_TEMPLATE_RETENTION 个。"""
    files = sorted(upload_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[FILLED_TEMPLATE_RETENTION:]:
        try:
            old.unlink()
        except Exception:
            pass


# Report type → template filename keywords for auto-matching
TYPE_TEMPLATE_KEYWORDS = {
    "tech_agreement": ["技术协议", "tech", "agreement"],
    "stage_report": ["阶段报告", "阶段", "stage"],
    "final_report": ["结题报告", "结题", "final"],
    "acceptance": ["验收报告", "验收", "acceptance"],
    "risk_analysis": ["风险分析", "风险", "risk"],
    "weekly_summary": ["周报汇总", "周报", "weekly"],
    "requirements_report": ["需求报告", "需求", "requirement"],
}


def _find_matching_template(report_type: str) -> str | None:
    """Find a template in the library that matches the report type."""
    if not TEMPLATE_DIR.exists():
        return None
    keywords = TYPE_TEMPLATE_KEYWORDS.get(report_type, [])
    for f in sorted(TEMPLATE_DIR.glob("*.docx"), key=lambda x: x.stat().st_mtime, reverse=True):
        fname_lower = f.stem.lower()
        for kw in keywords:
            if kw.lower() in fname_lower:
                return str(f)
    return None


@router.get("/api/report-gen/generate/{project_id}")
def generate_report(
    project_id: int,
    type: str = Query("stage_report", description="报告类型"),
    context: str = Query("", description="用户补充说明/特殊要求"),
    template: str = Query("", description="用户粘贴的模板文本"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Generate an AI-powered report from all project data.
    Priority: 1) template library match  2) user-pasted template  3) AI free-form
    """
    if type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的报��类型: {type}。可选: {', '.join(REPORT_TYPES.keys())}")

    # Gather project data
    data = _gather_project_data(db, project_id)

    # Step 1: Check template library first
    matched_template_path = _find_matching_template(type)
    template_used = None

    if matched_template_path:
        # Use the matched template — fill with AI-enhanced content
        with open(matched_template_path, "rb") as fh:
            template_content = fh.read()
        try:
            doc = Document(BytesIO(template_content))
            template_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            template_used = FilePath(matched_template_path).name
        except Exception:
            template_text = ""

        if template_text:
            # Build prompt with template structure + project data
            prompt = _build_prompt(type, context, data, template_text)
            report_content = _call_ai(prompt)
            return {
                "ok": True,
                "type": type,
                "type_name": REPORT_TYPES[type]["name"],
                "project_name": data["project"]["name"],
                "content": report_content,
                "template_used": template_used,
                "source": "library",
                "generated_at": _now().isoformat(),
            }

    # Step 2: Use user-pasted template if provided
    if template and len(template) > 50:
        template_used = "用户提供"
        prompt = _build_prompt(type, context, data, template)
        report_content = _call_ai(prompt)
        return {
            "ok": True,
            "type": type,
            "type_name": REPORT_TYPES[type]["name"],
            "project_name": data["project"]["name"],
            "content": report_content,
            "template_used": template_used,
            "source": "user",
            "generated_at": _now().isoformat(),
        }

    # Step 3: Fallback — AI free-form generation
    prompt = _build_prompt(type, context, data, "")
    report_content = _call_ai(prompt)

    return {
        "ok": True,
        "type": type,
        "type_name": REPORT_TYPES[type]["name"],
        "project_name": data["project"]["name"],
        "content": report_content,
        "template_used": None,
        "source": "ai_freeform",
        "generated_at": _now().isoformat(),
    }


@router.get("/api/report-gen/types")
def list_report_types():
    """List available report types."""
    return [
        {"key": k, "name": v["name"], "sections": v["sections"]}
        for k, v in REPORT_TYPES.items()
    ]


@router.post("/api/report-gen/export/docx")
async def export_docx(request: Request, _user=Depends(get_current_user)):
    """Convert markdown content to Word document (.docx)."""
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    import re as _re

    import json as _json
    raw = await request.body()
    try: data = _json.loads(raw)
    except: data = _json.loads(raw.decode("utf-8", errors="replace"))
    content = data.get("content", "")
    title = data.get("title", "报告")

    import re as _re
    from urllib.parse import quote
    from docx.shared import Inches as DocxInches

    doc = Document()
    doc.styles["Normal"].font.name = "SimSun"
    doc.styles["Normal"].font.size = Pt(11)

    # Parse content into blocks: text lines and images
    img_pattern = _re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

    # First, find all image references and replace them with placeholders
    # This handles both standalone and inline images
    img_refs = list(img_pattern.finditer(content))
    segments = []
    last_end = 0
    for m in img_refs:
        # Text before this image
        text_before = content[last_end:m.start()]
        if text_before.strip():
            segments.append(("text", text_before))
        # Image
        segments.append(("image", (m.group(1), m.group(2))))
        last_end = m.end()
    # Remaining text
    text_after = content[last_end:]
    if text_after.strip():
        segments.append(("text", text_after))

    if not segments:
        segments.append(("text", content))

    for seg_type, seg_data in segments:
        if seg_type == "image":
            alt, img_path = seg_data
            img_path_clean = img_path.split("?")[0]
            if img_path_clean.startswith("/uploads/"):
                # Try to locate the actual file on disk
                rel_part = img_path_clean[len("/uploads/"):]
                found = None
                local_path = FilePath(settings.UPLOAD_DIR)

                # Walk the relative path to find the file (handle encoding issues)
                parts = rel_part.replace("\\", "/").split("/")
                for part in parts:
                    if not part: continue
                    # URL-decode the filename part
                    from urllib.parse import unquote
                    decoded = unquote(part)
                    local_path = local_path / decoded
                if local_path.exists():
                    found = local_path
                else:
                    # Fallback: scan parent directory for matching file
                    parent = local_path.parent
                    if parent.exists():
                        for f in parent.iterdir():
                            if f.name == local_path.name or unquote(f.name) == local_path.name:
                                found = f
                                break

                if found and found.exists():
                    try:
                        doc.add_paragraph(f"[{alt}]")
                        doc.add_picture(str(found), width=DocxInches(5.5))
                        last_para = doc.paragraphs[-1]
                        last_para.alignment = 1
                    except Exception as e:
                        doc.add_paragraph(f"[图片: {alt} — 加载失败: {str(e)[:100]}]")
                else:
                    doc.add_paragraph(f"[图片: {alt}]")
            else:
                doc.add_paragraph(f"[图片: {alt}]")
            continue

        # Text segment: process line by line
        for line in seg_data.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("## "):
                doc.add_heading(line[3:], level=1)
            elif line.startswith("### "):
                doc.add_heading(line[4:], level=2)
            elif line.startswith("- "):
                doc.add_paragraph(line[2:], style="List Bullet")
            elif line.startswith("```"):
                continue
            elif line.startswith("*") and line.endswith("*") and len(line) > 2:
                p = doc.add_paragraph()
                run = p.add_run(line.strip("* "))
                run.bold = True
            elif line.startswith("> "):
                p = doc.add_paragraph(line[2:])
                p.paragraph_format.left_indent = Cm(1)
                if p.runs:
                    p.runs[0].font.color.rgb = RGBColor(100, 100, 100)
            else:
                doc.add_paragraph(line)

    output = BytesIO()
    doc.save(output)
    output.seek(0)

    safe_name = f"{title}_{_now().strftime('%Y%m%d')}.docx"
    encoded_name = quote(safe_name)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


import re as _re
_HEAD_RE = _re.compile(r'^(第[一二三四五六七八九十百千\d]+[章节条款部分]|[一二三四五六七八九十]+[、．.]|\d+(\.\d+)*[、.．\s])')


def _is_short_title(txt: str) -> bool:
    """无编号的独立短标题行(合同/计划模板常见,如「设计开发目标和内容」)。"""
    if not (2 <= len(txt) <= 16):
        return False
    if _re.search(r"[。，；：？！、,;.!?]", txt):
        return False
    if _re.fullmatch(r"[\s年月至日\-\d]*", txt):
        return False
    if txt.startswith(("（", "(", "①", "②", "③", "④", "⑤", "【")):
        return False
    if _re.search(r"\d", txt):
        return False
    if any(k in txt for k in ("一式", "仲裁", "印制", "之", "由", "自", "在", "为", "将")):
        return False
    return True


def _extract_template_structure(content: bytes) -> tuple:
    """提取 docx 模板结构: (headings: [(level, text)], body: [str], fields: [str])。
    headings: 标题样式/全加粗短句/序号标题/独立短标题行; fields: 短字段行(如"合同编号："); body: 正文段落+表格行。"""
    headings, body, fields = [], [], []
    try:
        doc = Document(BytesIO(content))
        for para in doc.paragraphs:
            txt = para.text.strip()
            if not txt:
                continue
            style = (para.style.name or "").lower()
            if "heading" in style or "标题" in style:
                lvl = 1
                for c in style:
                    if c.isdigit():
                        lvl = int(c)
                        break
                headings.append((lvl, txt))
            elif para.runs and all(r.bold for r in para.runs if r.text.strip()) and len(txt) < 60:
                headings.append((1, txt))
            elif len(txt) <= 40 and (txt.endswith("：") or txt.endswith(":")):
                fields.append(txt)
            elif len(txt) <= 50 and _HEAD_RE.match(txt):
                headings.append((2, txt))
            elif _is_short_title(txt):
                headings.append((2, txt))
            else:
                body.append(txt)
        for table in doc.tables:
            for row in table.rows:
                texts = [c.text.strip() for c in row.cells if c.text.strip()]
                if texts:
                    body.append(" | ".join(texts))
    except Exception:
        pass
    return headings, body, fields


def _build_std_report_prompt(std, dv, data, project_id: int) -> tuple:
    """构建交付物/标准 AI 报告 prompt: 模板大纲严格约束 + 细化项目数据。
    返回 (prompt, template_used)。"""
    template_text, template_used, outline = "", None, None
    if std and std.template_path:
        tpl_file = FilePath(settings.UPLOAD_DIR) / str(std.template_path).replace("\\", "/")
        if tpl_file.is_file():
            try:
                headings, body, fields = _extract_template_structure(tpl_file.read_bytes())
                template_used = str(std.template_path).replace("\\", "/").split("/")[-1]
                if headings:
                    outline = headings
                    template_text = "\n".join(body + fields)[:3000]
                else:
                    template_text = "\n".join(_extract_text(tpl_file.read_bytes(), tpl_file.name))[:4000]
            except Exception:
                pass
    if not template_text and std and getattr(std, "acceptance_criteria", None):
        template_text = f"验收标准：\n{std.acceptance_criteria}"

    phase_name = ""
    if dv and dv.phase:
        phase_name = dv.phase.name
    elif std and std.phase_id:
        ph = db_phase_name(std.phase_id)
        phase_name = ph

    dv_info = f"""标准名称：{std.name if std else '—'}
所属阶段：{phase_name or '—'}
分类：{getattr(std, 'category', '') or '—'}
必需：{'是' if std and std.required else '否'}
责任角色：{getattr(std, 'responsible_role', '') or '—'}
描述：{getattr(std, 'description', '') or '无'}
验收标准：{getattr(std, 'acceptance_criteria', '') or '无'}
{("项目交付物：" + dv.name + f"（状态 {dv.status}，负责人 {dv.owner.name if dv.owner else '—'}，提交日期 {dv.submitted_date or '—'}）") if dv else "（该项目尚未添加此交付物）"}"""

    if outline:
        outline_lines = []
        for lvl, t in outline:
            indent = "  " * min(lvl - 1, 3)
            outline_lines.append(f"{indent}{lvl}. {t}")
        template_instruction = (
            "交付物标准模板的大纲（请严格按此章节顺序输出报告，章节标题与层级保持完全一致，不得增删章节；"
            "带模板原文提示的章节须按提示内容填写）：\n```\n" + "\n".join(outline_lines) + "\n```\n"
            + ("\n模板正文提示（各章节需要覆盖的内容）：\n```\n" + template_text + "\n```" if template_text else "")
        )
    elif template_text:
        template_instruction = (
            "交付物标准模板内容（请尽量按照模板的章节结构和编号方式组织报告）：\n```\n" + template_text + "\n```"
        )
    else:
        template_instruction = "（该标准没有可用的模板文件，请按专业报告结构组织：报告概述 / 详细内容 / 结论与建议）"

    info = json.dumps(data, ensure_ascii=False, indent=2)

    prompt = f"""你是电机行业项目管理报告撰写助手。请根据交付物标准的模板结构和项目历史数据，生成该交付物的正式报告（Markdown格式）。

{template_instruction}

【标准与交付物信息】
{dv_info}

【项目历史数据（JSON）】
{info[:20000]}

要求：
1. 严格按照模板大纲的章节顺序生成，章节标题必须与模板一致，不得增删章节
2. 必须从项目历史数据中提取具体内容填充各章节——引用真实日期、数值、状态、名称、负责人等细节，数据越细化越好
3. 数据不足的章节标注「（待补充）」，并写明需要补充什么
4. 正式专业语言，技术参数用表格呈现
5. 避免空泛套话，每个结论尽量附上数据依据
6. 报告不少于 800 字
7. 只输出报告正文，标题用 ## 开头，子标题用 ###"""

    return prompt, template_used


def db_phase_name(phase_id: int) -> str:
    try:
        from backend_v2.database import SessionLocal
        with SessionLocal() as s:
            ph = s.execute(select(Phase).where(Phase.id == phase_id)).scalar_one_or_none()
            return ph.name if ph else ""
    except Exception:
        return ""


def _extract_text(content: bytes, filename: str) -> list:
    """Extract text from uploaded file — tries python-docx, ZIP XML, plain text."""
    result = []
    # Method 1: python-docx
    try:
        doc = Document(BytesIO(content))
        for para in doc.paragraphs:
            if para.text.strip():
                result.append(para.text.strip())
        for table in doc.tables:
            for row in table.rows:
                texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if texts:
                    result.append(" | ".join(texts))
        if result:
            return result
    except Exception:
        pass
    # Method 2: Parse ZIP XML directly (handles non-standard .docx)
    try:
        from zipfile import ZipFile
        from xml.etree import ElementTree as ET
        zf = ZipFile(BytesIO(content))
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        for name in zf.namelist():
            if "document" in name.lower() and name.endswith(".xml"):
                root = ET.fromstring(zf.read(name))
                for p in root.iter(f"{{{ns}}}p"):
                    texts = [t.text or "" for t in p.iter(f"{{{ns}}}t")]
                    line = "".join(texts).strip()
                    if line:
                        result.append(line)
        if result:
            return result
    except Exception:
        pass
    # Method 3: Plain text
    for enc in ["utf-8", "gbk", "latin-1"]:
        try:
            text = content.decode(enc).strip()
            if len(text) > 50:
                return text.split("\n")[:100]
        except Exception:
            continue
    return []


@router.post("/api/report-gen/fill-template")
async def fill_template(
    file: UploadFile = File(...),
    token: str = Form(""),
    project_id: str = Form("0"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Upload a .docx template via form POST — AI fills it with project data."""
    # Auth via form token（iframe 嵌入用）或 Authorization 头；两者都没有则拒绝
    if not token:
        auth = request.headers.get("Authorization", "") if request else ""
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="需要登录")
        token = auth[7:]
    try:
        from backend_v2.auth import verify_token
        verify_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="登录已过期")

    pid = int(project_id) if project_id and project_id.isdigit() else 0
    content = await file.read()

    if not content or len(content) < 100:
        raise HTTPException(status_code=400, detail="上传的文件为空或太小")

    # Try to extract text from the uploaded file
    template_text = _extract_text(content, file.filename or "upload.docx")
    if not template_text or len(template_text) < 10:
        raise HTTPException(status_code=400, detail="无法从文件中提取文字。文件可能为加密、图片扫描件或旧版 .doc 格式。建议另存为 .docx 后再试。")

    template_structure = "\n".join(template_text[:50])

    # Find project
    if pid:
        proj = (db.execute(select(Project).where(Project.id == pid).options(
            selectinload(Project.client), selectinload(Project.current_phase)
        ))).scalar_one_or_none()
    else:
        proj = (db.execute(
            select(Project).where(Project.is_active == True).options(
                selectinload(Project.client), selectinload(Project.current_phase)
            ).order_by(Project.id)
        )).scalars().first()

    if not proj:
        raise HTTPException(status_code=404, detail="没有可用的项目")

    data = _gather_project_data(db, proj.id)

    # Parse the original template
    try:
        doc = Document(BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法打开文档: {str(e)[:100]}")

    # Strategy: replace patterns in the original template paragraphs with project data
    proj_name = data["project"]["name"]
    client_name = data["project"]["client"]

    # Create replacement map
    replacements = {
        "甲方：": f"甲方：{client_name}",
        "甲方: ": f"甲方: {client_name}",
        "甲方 :": f"甲方 : {client_name}",
        "甲方：___": f"甲方：{client_name}",
        "甲方法人": "",
        "甲方（盖章）": "",
        "乙方：___": f"乙方：麦科斯韦动力科技",
        "乙方：": f"乙方：麦科斯韦动力科技有限公司",
        "乙方: ": f"乙方: 麦科斯韦动力科技有限公司",
        "项目名称：___": f"项目名称：{proj_name}",
        "项目名称：": f"项目名称：{proj_name}",
        "联系电话：": f"联系电话：0571-85464125",
        "日期：": f"日期：{_now().strftime('%Y年%m月%d日')}",
    }

    # Build new doc from original template, replacing text
    new_doc = Document()
    for para in doc.paragraphs:
        text = para.text
        # Apply replacements
        for old, new in replacements.items():
            if old in text:
                text = text.replace(old, new)
        # Add paragraph
        if text.strip():
            p = new_doc.add_paragraph(text)
        else:
            new_doc.add_paragraph()

    # Add project data summary at the end
    new_doc.add_paragraph()
    new_doc.add_heading("项目数据参考（由 AI 辅助填充）", level=2)
    new_doc.add_paragraph(f"项目名称：{proj_name}")
    new_doc.add_paragraph(f"项目编号：{data['project']['code']}")
    new_doc.add_paragraph(f"客户名称：{client_name}")
    new_doc.add_paragraph(f"当前阶段：{data['project']['phase']}")
    new_doc.add_paragraph(f"项目周期：{data['project']['start_date']} ~ {data['project']['planned_end']}")
    new_doc.add_paragraph("里程碑进度：")
    for m in data["milestones"][:20]:
        status_map = {"completed": "已完成", "in_progress": "进行中", "pending": "待开始"}
        st = status_map.get(m["status"], m["status"])
        new_doc.add_paragraph(f"  {st}  {m['name']}  ({m['planned_date']})", style="List Bullet")

    output = BytesIO()
    new_doc.save(output)
    output.seek(0)

    safe_name = f"{data['project']['name']}_模板填充.docx"
    upload_dir = FilePath(settings.UPLOAD_DIR) / "filled_templates"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / safe_name
    with open(dest, "wb") as f:
        f.write(output.getvalue())
    _prune_filled_templates(upload_dir)

    from fastapi.responses import FileResponse
    full_path = upload_dir / safe_name
    return FileResponse(
        full_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=safe_name,
    )


# ── 交付物 AI 报告生成 ──

@router.get("/api/report-gen/deliverable/{deliverable_id}")
async def generate_deliverable_report(
    deliverable_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """按交付物生成 AI 报告: 交付物匹配的标准模板结构 + 项目历史数据。"""
    dv = db.execute(
        select(Deliverable).where(Deliverable.id == deliverable_id).options(
            selectinload(Deliverable.phase), selectinload(Deliverable.line), selectinload(Deliverable.owner)
        )
    ).scalar_one_or_none()
    if not dv:
        raise HTTPException(status_code=404, detail="交付物不存在")

    data = _gather_project_data(db, dv.project_id)

    # 匹配标准(同阶段 + 名称双向包含),取模板
    from backend_v2.models import GateDeliverableStandard as StdModel
    stds = (db.execute(
        select(StdModel).where(
            StdModel.phase_id == dv.phase_id, StdModel.is_active == True)
    )).scalars().all()
    matched = next(
        (s for s in stds if s.name and dv.name and (s.name in dv.name or dv.name in s.name)),
        None,
    )

    prompt, template_used = _build_std_report_prompt(matched, dv, data, dv.project_id)

    report_content = None
    try:
        from backend_v2.ai_service import call_task
        report_content = await call_task("report", [
            {"role": "system", "content": "你是专业的电机设计项目管理报告撰写助手，用中文输出正式报告，只输出报告正文。"},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        print(f"[report-gen] deliverable AI error: {e}")

    if not report_content or not (report_content or "").strip() or (report_content or "").startswith("[AI"):
        # 降级: 用项目数据拼一份基础报告
        proj = data["project"]
        lines = [
            f"## {proj['name']} — {dv.name} 报告",
            "",
            f"> 交付物状态：{dv.status} | 阶段：{dv.phase.name if dv.phase else '—'} | 生成时间：{_now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "### 一、项目概况",
            f"- 项目名称：{proj['name']}（{proj.get('code') or ''}）",
            f"- 客户：{proj['client'] or '—'} | 当前阶段：{proj['phase'] or '—'}",
            f"- 周期：{proj['start_date'] or '—'} ~ {proj['planned_end'] or '—'}",
            "",
            "### 二、交付物说明",
            f"- 名称：{dv.name}",
            f"- 状态：{dv.status}",
            f"- 描述：{dv.description or '（待补充）'}",
            f"- 关联标准：{matched.name if matched else '（未匹配）'}",
            "",
            "### 三、相关项目数据",
            f"- 里程碑：{len(data['milestones'])} 个",
            f"- 需求：{data['requirements_count']} 条",
            f"- 未关闭风险：{len(data['risks'])} 项",
            f"- 变更：{len(data['changes'])} 项",
            f"- 交付物：{len(data['deliverables'])} 项",
            "",
            "### 四、结论与建议",
            "（AI 引擎暂不可用，以上为项目数据自动汇总，请检查 AI 配置后重新生成）",
        ]
        report_content = "\n".join(lines)

    return {
        "ok": True,
        "content": report_content,
        "deliverable_name": dv.name,
        "deliverable_id": dv.id,
        "std_name": matched.name if matched else None,
        "template_used": template_used,
        "generated_at": _now().isoformat(),
    }


@router.get("/api/report-gen/standard-report/{std_id}")
async def generate_standard_report(
    std_id: int,
    project_id: int = Query(0, description="项目ID"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """按交付物标准生成 AI 报告: 标准模板结构 + 项目历史数据。
    未添加交付物的标准也可生成(空白结构报告)。
    """
    from backend_v2.models import GateDeliverableStandard as StdModel
    std = db.execute(select(StdModel).where(StdModel.id == std_id)).scalar_one_or_none()
    if not std:
        raise HTTPException(status_code=404, detail="标准不存在")

    data = _gather_project_data(db, project_id)

    # 该标准在项目中的交付物(同阶段+名称双向包含)
    dv = None
    if project_id:
        dvs = (db.execute(
            select(Deliverable).where(Deliverable.project_id == project_id)
        )).scalars().all()
        dv = next(
            (d for d in dvs if d.phase_id == std.phase_id and std.name and d.name and (std.name in d.name or d.name in std.name)),
            None,
        )

    prompt, template_used = _build_std_report_prompt(std, dv, data, project_id)

    report_content = None
    try:
        from backend_v2.ai_service import call_task
        report_content = await call_task("report", [
            {"role": "system", "content": "你是专业的电机设计项目管理报告撰写助手，用中文输出正式报告，只输出报告正文。"},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        print(f"[report-gen] standard AI error: {e}")

    if not report_content or not (report_content or "").strip() or (report_content or "").startswith("[AI"):
        proj = data["project"]
        lines = [
            f"## {proj['name']} — {std.name} 报告",
            "",
            f"> 标准：{std.name} | 阶段：{db_phase_name(std.phase_id) or '—'} | 生成时间：{_now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "### 一、项目概况",
            f"- 项目名称：{proj['name']}（{proj.get('code') or ''}）",
            f"- 客户：{proj['client'] or '—'} | 当前阶段：{proj['phase'] or '—'}",
            f"- 周期：{proj['start_date'] or '—'} ~ {proj['planned_end'] or '—'}",
            "",
            "### 二、标准说明",
            f"- 名称：{std.name}",
            f"- 描述：{std.description or '（待补充）'}",
            f"- 验收标准：{std.acceptance_criteria or '（待补充）'}",
            f"- 项目交付物：{dv.name + '（' + dv.status + '）' if dv else '尚未添加'}",
            "",
            "### 三、相关项目数据",
            f"- 里程碑：{len(data['milestones'])} 个",
            f"- 需求：{data['requirements_count']} 条",
            f"- 未关闭风险：{len(data['risks'])} 项",
            f"- 变更：{len(data['changes'])} 项",
            f"- 交付物：{len(data['deliverables'])} 项",
            "",
            "### 四、结论与建议",
            "（AI 引擎暂不可用，以上为项目数据自动汇总，请检查 AI 配置后重新生成）",
        ]
        report_content = "\n".join(lines)

    return {
        "ok": True,
        "content": report_content,
        "std_name": std.name,
        "std_id": std.id,
        "deliverable_name": dv.name if dv else None,
        "deliverable_id": dv.id if dv else None,
        "template_used": template_used,
        "generated_at": _now().isoformat(),
    }


# ── 模板填充: 把项目数据 + AI 章节内容填进模板 docx 本身 ──

def _fmt_cn_date(s: str) -> str:
    """「2026-12-31」→「2026年12月31日」。"""
    parts = [p for p in _re.split(r"[^\d]+", (s or "").strip()) if p]
    if len(parts) >= 3 and all(len(p) <= 4 for p in parts[:3]):
        return f"{parts[0]}年{int(parts[1])}月{int(parts[2])}日"
    return (s or "").strip()


FIELD_RULES = [
    (("合同编号", "合同号", "项目编号", "项目代码"), lambda d: d["project"].get("code") or ""),
    (("项目名称",), lambda d: d["project"].get("name") or ""),
    (("委托方", "甲方"), lambda d: d["project"].get("client") or ""),
    (("联系电话", "电话"), lambda d: "0571-85464125"),
    (("签订日期", "签订时间", "签署日期", "签定日期"), lambda d: _fmt_cn_date(str(_today()))),
    (("有效期限", "合同期限", "履行期限", "服务期限"), lambda d: _fmt_cn_date(d["project"].get("planned_end") or "")),
]


def _fill_fields_in_text(text: str, data: dict) -> str:
    """填充字段行: 「合同编号：＿＿＿」/「项目名称：」→ 项目数据。
    仅当字段关键词出现在行首冒号之前(字段行特征)才填充,不覆盖已有内容。"""
    if not text or ("：" not in text and ":" not in text):
        return text
    if any(k in text for k in ("盖章", "签字", "签名", "签章")):
        return text
    c = text.find("：")
    if c == -1:
        c = text.find(":")
    if c == -1 or c > 12:
        return text  # 冒号太靠后 → 正文句子,不是字段行
    head = text[:c]
    seg = text[c + 1:]
    for kws, val_fn in FIELD_RULES:
        if not any(k in head for k in kws):
            continue
        val = val_fn(data)
        if not val:
            return text
        m = _re.search(r"[＿_]{2,}", seg)  # 下划线占位
        if m:
            return text[: c + 1] + val + seg[m.end():].rstrip()
        if _re.fullmatch(r"\s*[＿_]*\s*年\s*月\s*日\s*", seg):  # 「：  年 月 日」占位
            return text[: c + 1] + val
        if not seg.strip():  # 冒号后为空 → 追加值
            return text[: c + 1] + val
        if len(seg.strip()) <= 4 and "：" not in seg and ":" not in seg:  # 同行的下一字段(如 电话：＿＿ 传真：)
            return text[: c + 1] + val + " " + seg.lstrip()
    return text


def _set_para_text(para, text: str):
    if para.runs:
        para.runs[0].text = text
        for r in para.runs[1:]:
            r.text = ""
    else:
        para.add_run(text)


def _fill_fields_in_doc(doc: Document, data: dict):
    for para in doc.paragraphs:
        new = _fill_fields_in_text(para.text, data)
        if new != para.text:
            _set_para_text(para, new)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    new = _fill_fields_in_text(para.text, data)
                    if new != para.text:
                        _set_para_text(para, new)


def _common_prefix(a: str, b: str) -> str:
    out = []
    for x, y in zip(a, b):
        if x != y:
            break
        out.append(x)
    return "".join(out)


def _norm_heading(t: str) -> str:
    t = (t or "").strip()
    # 循环剥离序号: AI 键可能带双重序号(如 "25. 7. 因乙方原因…")
    while True:
        prev = t
        t = _re.sub(r"^第[一二三四五六七八九十百千\d]+[章节条款部分]\s*", "", t)
        t = _re.sub(r"^[一二三四五六七八九十]+[、．.]\s*", "", t)
        t = _re.sub(r"^\d+(\.\d+)*[、.．\s]\s*", "", t)
        t = _re.sub(r"^[.．·、\s]+", "", t)
        if t == prev:
            break
    return t.strip()


def _insert_para_after(paragraph, text: str, is_bullet: bool = False, fmt_para=None):
    """在 paragraph 后插入新段落。fmt_para 提供格式参考: 深拷贝其段落属性(样式/缩进/行距/对齐)与首个 run 的字体格式,
    使 AI 内容与模板正文视觉一致, 不再割裂。"""
    from docx.oxml import OxmlElement as _Ox
    from docx.oxml.ns import qn as _qn
    from docx.text.paragraph import Paragraph as _Para
    import copy as _copy
    src_p = fmt_para._p if fmt_para is not None else None
    new_p = _Ox("w:p")
    if src_p is not None and src_p.pPr is not None:
        ppr = _copy.deepcopy(src_p.pPr)
        num = ppr.find(_qn('w:numPr'))
        if num is not None:
            ppr.remove(num)
        new_p.append(ppr)
    paragraph._p.addnext(new_p)
    new_para = _Para(new_p, paragraph._parent)
    run = new_para.add_run(text)
    if src_p is not None:
        for r in fmt_para.runs:
            if r._r.rPr is not None:
                run._r.insert(0, _copy.deepcopy(r._r.rPr))
                break
    elif is_bullet:
        try:
            new_para.style = new_para._parent.styles["List Bullet"]
        except Exception:
            pass
    return new_para


def _strip_md(line: str) -> str:
    line = (line or "").strip()
    line = _re.sub(r"^\s*[-*]\s+", "", line)          # 列表符号
    line = _re.sub(r"^\s*\|\s*|\|\s*$", "", line)     # 表格边界
    line = line.replace("|", "\t")                     # 表格单元格 → Tab 分隔
    line = _re.sub(r"\*\*(.+?)\*\*", r"\1", line)      # 加粗标记
    return line


def _parse_ai_sections(content: str) -> dict:
    """解析 AI 章节内容 → {章节标题: 正文}。优先 JSON,失败则按 Markdown 标题切分。"""
    content = (content or "").strip()
    if content.startswith("{"):
        try:
            obj = json.loads(content)
            if isinstance(obj, dict):
                out = {}
                for k, v in obj.items():
                    if isinstance(v, list):
                        v = "\n".join(str(x) for x in v)
                    if str(v or "").strip():
                        out[str(k).strip()] = str(v)
                return out
        except Exception:
            pass
    sections, current = {}, None
    for line in content.split("\n"):
        m = _re.match(r"^#{1,6}\s+(.+)$", line.strip())
        if m:
            current = m.group(1).strip()
            sections.setdefault(current, [])
        elif current and line.strip():
            sections[current].append(line.strip())
    return {k: v for k, v in sections.items() if v}


def _insert_sections_into_doc(doc: Document, sections: dict, outline_norms=None) -> int:
    """把 AI 章节内容插到模板中标题一致的段落之后。返回插入的章节数。
    outline_norms: 模板标题的归一化集合, 用于避开把标题段当作正文格式参考。"""
    outline_norms = outline_norms or set()
    paras = list(doc.paragraphs)
    norm_pool = {}
    for k, v in sections.items():
        nk = _norm_heading(k)
        if nk:
            body = v.split("\n") if isinstance(v, str) else v
            norm_pool.setdefault(nk, [l for l in body if (l or "").strip()])
    if not norm_pool:
        return 0
    inserted, used = 0, set()
    for idx, para in enumerate(paras):
        n = _norm_heading(para.text)
        if not n or n in used:
            continue
        key = n if n in norm_pool else None
        if key is None:
            # 二级模糊匹配: 短键包含(如「1.背景知识产权」vs「背景知识产权」);
            # 长键包含仅限标题特征段落,防止正文长句误吞短章节
            for cand in norm_pool:
                if cand in used:
                    continue
                if n in cand and len(cand) <= 40:
                    key = cand
                    break
                if cand in n and ((len(cand) <= 20 and len(n) <= 20) or (len(cand) >= 20 and len(n) <= 50)):
                    key = cand
                    break
            # 长标题前缀匹配: AI 键与模板标题头部一致但尾部措辞略异
            if key is None and len(n) >= 10:
                best, best_len = None, 0
                for cand in norm_pool:
                    if cand in used:
                        continue
                    common = len(_common_prefix(n, cand))
                    if common >= 10 and common > best_len:
                        best, best_len = cand, common
                if best:
                    key = best
        if key is None:
            continue
        used.add(key)
        anchor = para
        # 格式参考: 标题后最近的非空正文段(跳过其他标题)
        fmt_para = None
        for p2 in paras[idx + 1:]:
            if not p2.text.strip():
                continue
            if _norm_heading(p2.text) in outline_norms:
                break
            fmt_para = p2
            break
        for line in norm_pool[key]:
            anchor = _insert_para_after(anchor, _strip_md(line), is_bullet=line.startswith("-"), fmt_para=fmt_para)
        inserted += 1
    rest = {k: v for k, v in norm_pool.items() if k not in used}
    if rest:
        body_paras = [p for p in doc.paragraphs if p.text.strip()]
        anchor = body_paras[-1] if body_paras else doc.add_paragraph()
        fmt_para = body_paras[-1] if body_paras else None
        for k, v in rest.items():
            anchor = _insert_para_after(anchor, k)
            for line in v:
                anchor = _insert_para_after(anchor, _strip_md(line), is_bullet=line.startswith("-"), fmt_para=fmt_para)
        inserted += len(rest)
    return inserted


def _build_fill_prompt(std, dv, data: dict, outline_titles: list) -> str:
    info = json.dumps(data, ensure_ascii=False, indent=2)
    titles = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(outline_titles))
    dv_name = dv.name if dv else (std.name if std else "")
    return f"""你是电机行业项目管理报告撰写助手。请根据模板章节标题和项目历史数据，为交付物《{dv_name}》填写模板各章节内容。

【模板章节标题（JSON键必须严格使用这些标题，一个都不能少）】
{titles}

【项目历史数据（JSON）】
{info[:20000]}

要求：
1. 输出一个 JSON 对象：键 = 上面列出的模板章节标题（完全一致），值 = 该章节正文（Markdown）
2. 正文必须引用项目数据中的真实日期、数值、状态、名称、负责人，越细化越好
3. 正文格式规范：开头用 1-2 句总起段落（完整句子），要点条目用「- 」短句列表（每条一行、不超过40字），不要整章堆列表；金额、日期、参数等用中文书面表达
4. 数据不足的章节写「（待补充）：需要补充的具体信息」
5. 正式专业语言，避免空泛套话
6. 只输出 JSON 对象本身，不要任何其他文字或代码块标记"""


async def _build_filled_docx(std, dv, data: dict, tpl_file: FilePath) -> BytesIO:
    """核心: 打开模板 docx → 字段行填项目数据 → AI 生成各章节内容插到对应标题后 → 返回流。"""
    tpl_bytes = tpl_file.read_bytes()
    try:
        doc = Document(BytesIO(tpl_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法打开模板文件: {str(e)[:100]}")

    # 1) 字段行填充(合同编号/项目名称/甲方/乙方/日期/期限)
    _fill_fields_in_doc(doc, data)

    # 2) 提取模板大纲
    headings, _body, _fields = _extract_template_structure(tpl_bytes)
    outline_titles = [t for _lvl, t in headings]

    # 3) AI 生成各章节内容
    sections, ai_note = {}, None
    if outline_titles:
        try:
            prompt = _build_fill_prompt(std, dv, data, outline_titles)
            from backend_v2.ai_service import call_task
            content = await call_task("report", [
                {"role": "system", "content": "你是专业的电机设计项目管理报告撰写助手，严格输出JSON对象。"},
                {"role": "user", "content": prompt},
            ])
            sections = _parse_ai_sections(content or "")
        except Exception as e:
            print(f"[report-gen] fill AI error: {e}")
            ai_note = f"AI 章节内容生成失败：{str(e)[:100]}。以下文件已填充合同字段，章节内容请手工补充。"

    if sections:
        outline_norms = {_norm_heading(t) for t in outline_titles}
        inserted = _insert_sections_into_doc(doc, sections, outline_norms)
        if not inserted:
            ai_note = f"AI 内容未能匹配模板章节，已追加到文末。共生成 {len(sections)} 个章节。"
    elif outline_titles:
        ai_note = f"AI 内容生成失败或为空，模板仅完成字段填充。共 {len(outline_titles)} 个章节待补充。"

    if ai_note:
        body_paras = [p for p in doc.paragraphs if p.text.strip()]
        anchor = body_paras[-1] if body_paras else doc.add_paragraph()
        _insert_para_after(anchor, ai_note)

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output


def _std_template_path(std) -> FilePath | None:
    if not std or not std.template_path:
        return None
    f = FilePath(settings.UPLOAD_DIR) / str(std.template_path).replace("\\", "/")
    return f if f.is_file() else None


@router.get("/api/report-gen/fill-deliverable/{deliverable_id}")
async def fill_deliverable_template(
    deliverable_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """把项目数据 + AI 章节内容填进交付物模板 docx 本身，返回填好的 docx 下载。"""
    dv = db.execute(
        select(Deliverable).where(Deliverable.id == deliverable_id).options(
            selectinload(Deliverable.phase), selectinload(Deliverable.line), selectinload(Deliverable.owner)
        )
    ).scalar_one_or_none()
    if not dv:
        raise HTTPException(status_code=404, detail="交付物不存在")

    from backend_v2.models import GateDeliverableStandard as StdModel
    stds = (db.execute(select(StdModel).where(
        StdModel.phase_id == dv.phase_id, StdModel.is_active == True))).scalars().all()
    std = next((s for s in stds if s.name and dv.name and (s.name in dv.name or dv.name in s.name)), None)
    if not std:
        raise HTTPException(status_code=400, detail="该交付物未匹配到标准，无法获取模板。请先在「标准维护」中创建同名标准并上传模板")
    tpl_file = _std_template_path(std)
    if not tpl_file:
        raise HTTPException(status_code=400, detail="该交付物关联的标准没有模板文件，请先在「标准维护」中上传 .docx 模板")

    data = _gather_project_data(db, dv.project_id)
    filled = await _build_filled_docx(std, dv, data, tpl_file)

    from urllib.parse import quote
    safe_name = f"{std.name}_{data['project']['name']}_模板填充版.docx"
    return StreamingResponse(
        filled,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}"},
    )


@router.get("/api/report-gen/fill-standard/{std_id}")
async def fill_standard_template(
    std_id: int,
    project_id: int = Query(0, description="项目ID"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """按标准(未添加交付物也可)填充模板 docx，返回填好的 docx 下载。"""
    from backend_v2.models import GateDeliverableStandard as StdModel
    std = db.execute(select(StdModel).where(StdModel.id == std_id)).scalar_one_or_none()
    if not std:
        raise HTTPException(status_code=404, detail="标准不存在")
    tpl_file = _std_template_path(std)
    if not tpl_file:
        raise HTTPException(status_code=400, detail="该标准没有模板文件，请先在「标准维护」中上传 .docx 模板")

    data = _gather_project_data(db, project_id)

    dv = None
    if project_id:
        dvs = (db.execute(select(Deliverable).where(Deliverable.project_id == project_id))).scalars().all()
        dv = next((d for d in dvs if d.phase_id == std.phase_id and std.name and d.name and (std.name in d.name or d.name in std.name)), None)

    filled = await _build_filled_docx(std, dv, data, tpl_file)

    from urllib.parse import quote
    safe_name = f"{std.name}_{data['project']['name']}_模板填充版.docx"
    return StreamingResponse(
        filled,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}"},
    )


# ── Template Library ──

TEMPLATE_DIR = FilePath(__file__).parent.parent.parent / "data" / "templates"
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/api/report-gen/templates")
def list_templates(_user=Depends(get_current_user)):
    """List all saved templates in the library."""
    templates = []
    for f in sorted(TEMPLATE_DIR.glob("*.docx"), key=lambda x: x.stat().st_mtime, reverse=True):
        templates.append({
            "id": f.stem,
            "name": f.name,
            "size": f.stat().st_size,
            "updated": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return templates


@router.post("/api/report-gen/templates/upload", status_code=201)
async def upload_template_to_library(
    file: UploadFile = File(...),
    _user=Depends(require_admin),
):
    """Save a .docx template to the library for all projects."""
    from pathlib import Path as _Path
    fname = _Path(file.filename or "").name
    if not fname.endswith(".docx"):
        raise HTTPException(status_code=400, detail="仅支持 .docx 文件")
    safe_name = fname
    dest = TEMPLATE_DIR / safe_name
    content = await file.read()
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="文件为空")
    with open(dest, "wb") as f:
        f.write(content)
    return {"message": f"模板 {safe_name} 已保存到模版库", "name": safe_name}


@router.delete("/api/report-gen/templates/{name}")
def delete_template(name: str, _user=Depends(require_admin)):
    """Remove a template from the library."""
    f = TEMPLATE_DIR / (name + ".docx")
    if not f.exists():
        f = TEMPLATE_DIR / name
    if not f.exists():
        raise HTTPException(status_code=404, detail="模板不存在")
    f.unlink()
    return {"message": "已删除"}


@router.post("/api/report-gen/fill-from-library")
async def fill_from_library(
    template_name: str = Form(...),
    project_id: str = Form("0"),
    token: str = Form(""),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Fill a saved template with project data."""
    if not token:
        auth = request.headers.get("Authorization", "") if request else ""
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="需要登录")
        token = auth[7:]
    try:
        from backend_v2.auth import verify_token
        verify_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="登录已过期")

    f = TEMPLATE_DIR / (template_name + ".docx")
    if not f.exists():
        f = TEMPLATE_DIR / template_name
    if not f.exists():
        raise HTTPException(status_code=404, detail="模板不存在")

    with open(f, "rb") as fh:
        content = fh.read()

    pid = int(project_id) if project_id and project_id.isdigit() else 0
    # Reuse the fill logic from fill_template
    try:
        doc = Document(BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法打开模板: {str(e)[:100]}")

    # Find project
    if pid:
        proj = (db.execute(select(Project).where(Project.id == pid).options(
            selectinload(Project.client), selectinload(Project.current_phase)
        ))).scalar_one_or_none()
    else:
        proj = (db.execute(select(Project).where(Project.is_active == True).options(
            selectinload(Project.client), selectinload(Project.current_phase)
        ).order_by(Project.id))).scalars().first()

    if not proj:
        raise HTTPException(status_code=404, detail="没有可用的项目")

    data = _gather_project_data(db, proj.id)

    # Fetch requirements
    from backend_v2.models import Requirement as ReqModel
    reqs = (db.execute(
        select(ReqModel).where(ReqModel.project_id == proj.id).order_by(ReqModel.priority, ReqModel.category)
    )).scalars().all()

    proj_name = data["project"]["name"]
    client_name = data["project"]["client"]

    replacements = {
        "甲方：": f"甲方：{client_name}",
        "甲方: ": f"甲方: {client_name}",
        "甲方：___": f"甲方：{client_name}",
        "乙方：": f"乙方：麦科斯韦动力科技有限公司",
        "乙方: ": f"乙方: 麦科斯韦动力科技有限公司",
        "乙方：___": f"乙方：麦科斯韦动力科技",
        "项目名称：___": f"项目名称：{proj_name}",
        "项目名称：": f"项目名称：{proj_name}",
        "日期：": f"日期：{_now().strftime('%Y年%m月%d日')}",
        "联系电话：": "联系电话：0571-85464125",
    }

    new_doc = Document()
    for para in doc.paragraphs:
        text = para.text
        for old, new in replacements.items():
            if old in text:
                text = text.replace(old, new)
        if text.strip():
            new_doc.add_paragraph(text)
        else:
            new_doc.add_paragraph()

    new_doc.add_paragraph()
    new_doc.add_heading("项目数据参考", level=2)
    new_doc.add_paragraph(f"项目名称：{proj_name}")
    new_doc.add_paragraph(f"项目编号：{data['project']['code']}")
    new_doc.add_paragraph(f"客户名称：{client_name}")
    new_doc.add_paragraph(f"当前阶段：{data['project']['phase']}")

    # Add requirements section
    if reqs:
        new_doc.add_heading("需求规格明细", level=3)
        cat_map = {"functional": "功能", "performance": "性能", "interface": "接口", "safety": "安全", "reliability": "可靠性", "cost": "成本"}
        # Add requirements as a table
        table = new_doc.add_table(rows=1, cols=5)
        table.style = "Light Grid Accent 1"
        hdr = table.rows[0].cells
        hdr[0].text = "分类"; hdr[1].text = "需求标题"
        hdr[2].text = "优先级"; hdr[3].text = "来源"; hdr[4].text = "详细描述"
        for req in reqs:
            row = table.add_row().cells
            row[0].text = cat_map.get(req.category, req.category)
            row[1].text = req.title or ""
            row[2].text = req.priority or ""
            row[3].text = req.source or ""
            row[4].text = (req.description or "")[:200]

    # Add milestones
    new_doc.add_heading("里程碑进度", level=3)
    for m in data["milestones"][:20]:
        sm = {"completed": "已完成", "in_progress": "进行中", "pending": "待开始"}
        st = sm.get(m["status"], m["status"])
        new_doc.add_paragraph(f"  {st}  {m['name']}  ({m['planned_date']})", style="List Bullet")

    output = BytesIO()
    new_doc.save(output)
    output.seek(0)

    safe_name = f"{proj_name}_模板填充.docx"
    from fastapi.responses import FileResponse
    upload_dir = FilePath(settings.UPLOAD_DIR) / "filled_templates"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / safe_name
    with open(dest, "wb") as fw:
        fw.write(output.getvalue())
    _prune_filled_templates(upload_dir)

    return FileResponse(
        dest,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=safe_name,
    )


@router.post("/api/report-gen/export/pptx")
async def export_pptx(request: Request, _user=Depends(get_current_user)):
    """Convert markdown content to PowerPoint (.pptx)."""
    from io import BytesIO
    from fastapi.responses import StreamingResponse

    import json as _json
    raw = await request.body()
    try: data = _json.loads(raw)
    except: data = _json.loads(raw.decode("utf-8", errors="replace"))
    content = data.get("content", "")
    title = data.get("title", "报告")

    prs = Presentation()
    # Split by ## headings into slides
    slides_data = []
    current_title = title
    current_bullets = []

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            if current_bullets:
                slides_data.append((current_title, current_bullets))
            current_title = line[3:]
            current_bullets = []
        elif line.startswith("### "):
            current_bullets.append(("h3", line[4:]))
        elif line.startswith("- "):
            current_bullets.append(("bullet", line[2:]))
        elif line.startswith("```"):
            continue
        else:
            current_bullets.append(("text", line))

    if current_bullets:
        slides_data.append((current_title, current_bullets))

    if not slides_data:
        slides_data = [(title, [("text", "无内容")])]

    for slide_title, bullets in slides_data:
        slide = prs.slides.add_slide(prs.slide_layouts[1])  # Title + Content
        slide.shapes.title.text = slide_title
        body = slide.shapes.placeholders[1].text_frame
        body.clear()

        for btype, btext in bullets[:15]:  # Limit bullets per slide
            if btype == "h3":
                p = body.add_paragraph()
                run = p.add_run(btext)
                run.bold = True
                run.font.size = Pt(16)
                p.level = 0
            else:
                p = body.add_paragraph()
                p.text = btext
                p.level = 0 if btype == "text" else 1

    output = BytesIO()
    prs.save(output)
    output.seek(0)

    from urllib.parse import quote
    safe_name = f"{title}_{_now().strftime('%Y%m%d')}.pptx"
    encoded_name = quote(safe_name)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.post("/api/report-gen/image-to-report")
async def image_to_report(
    files: list[UploadFile] = File(...),
    report_type: str = Form("stage_report"),
    context: str = Form(""),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Upload one or more images → OCR extract text → AI formats into report.
    Supports: screenshots, whiteboard photos, document scans, meeting notes, etc.
    """
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一张图片")

    # Initialize OCR reader (lazy, once)
    try:
        import easyocr
        _ocr_reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
        import numpy as np
        from PIL import Image
    except ImportError:
        raise HTTPException(status_code=500, detail="OCR 引擎未安装，请运行: pip install easyocr")

    # Save uploaded images to disk
    upload_dir = FilePath(settings.UPLOAD_DIR) / "ocr_images" / _now().strftime("%Y%m%d")
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_image_paths = []

    ocr_parts = []
    ocr_errors = []
    failed_count = 0
    empty_count = 0

    for file in files:
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        if ext not in ("png", "jpg", "jpeg", "gif", "bmp", "webp"):
            failed_count += 1
            ocr_errors.append(f"{file.filename}: 不支持的格式 .{ext}")
            continue
        content = await file.read()
        if len(content) > 20 * 1024 * 1024:
            failed_count += 1
            ocr_errors.append(f"{file.filename}: 文件超过20MB")
            continue
        if len(content) < 100:
            failed_count += 1
            ocr_errors.append(f"{file.filename}: 文件过小，可能不是有效图片")
            continue

        # Save image
        safe_img_name = f"{_uuid.uuid4().hex[:8]}_{file.filename}"
        img_dest = upload_dir / safe_img_name
        with open(img_dest, "wb") as imgf:
            imgf.write(content)
        rel_path = str(img_dest.relative_to(FilePath(settings.UPLOAD_DIR))).replace("\\", "/")
        saved_image_paths.append(rel_path)

        try:
            img = Image.open(BytesIO(content))
            w, h = img.size
            if w < 50 or h < 50:
                empty_count += 1
                ocr_errors.append(f"{file.filename}: 图片尺寸过小({w}x{h})，无法识别")
                continue
            # Convert to RGB if needed (e.g., PNG with alpha channel)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            img_np = np.array(img)
            results = _ocr_reader.readtext(img_np)
            text = "\n".join([r[1] for r in results])
            if text.strip():
                ocr_parts.append(f"[图片 {file.filename}]:\n{text}")
            else:
                empty_count += 1
                ocr_errors.append(f"{file.filename}: 未检测到文字（检查图片是否清晰、含中文）")
        except Exception as e:
            failed_count += 1
            ocr_errors.append(f"{file.filename}: 识别失败 - {str(e)[:80]}")

    # Return detailed error if all images failed
    if not ocr_parts:
        tips = []
        if empty_count > 0: tips.append(f"{empty_count}张图片无文字，请确认包含清晰中文内容")
        if failed_count > 0: tips.append(f"{failed_count}张无法处理")
        return {
            "ok": False,
            "error": "图片内容分解失败",
            "detail": "所有图片均无法识别",
            "ocr_errors": ocr_errors,
            "tips": ["建议：确保图片清晰、光线充足、文字正向", "支持格式：PNG/JPG/BMP，建议分辨率 > 200x200", "微信截图通常效果最佳"] + tips,
            "source": "ocr",
        }

    ocr_text = "\n\n".join(ocr_parts)[:12000]  # limit total OCR text across all images

    # Collect project data for context (try to match project from conversation)
    projects = (db.execute(
        select(Project).where(Project.is_active == True).order_by(Project.id).limit(10)
    )).scalars().all()
    project_context = "\n".join([
        f"- {p.name}({p.code}): 客户={p.client.name if p.client else '?'}"
        for p in projects
    ])

    # Build AI prompt
    prompt = f"""以下是从图片中 OCR 提取的文字内容：

---图片OCR文字---
{ocr_text}
---

请根据以上内容生成一份{REPORT_TYPES.get(report_type, REPORT_TYPES['stage_report'])['name']}。

可用的项目上下文（供参考）：
{project_context}

用户补充说明：{context or '无'}

输出要求：
1. 识别并分类图片中的关键信息（需求变更、技术参数、问题描述、会议记录等）
2. 按标准报告结构组织内容（{', '.join(REPORT_TYPES[report_type]['sections'])}）
3. 用专业、正式的语气撰写
4. 对于无法从图片确定的信息，标注「待确认」
5. 在报告末尾附上「图片来源：OCR识别」标注"""

    ai_failed = False
    try:
        report_content = _call_ai(prompt)
    except Exception as e:
        ai_failed = True
        report_content = f"[AI 生成失败: {str(e)[:200]}]\n\n--- 原始 OCR 文字（可手动整理） ---\n\n{ocr_text}"

    # Phase classification (only if OCR succeeded)
    suggested_phase = None
    if not ai_failed:
        phases = (db.execute(select(Phase))).scalars().all()
        phase_names = "\n".join([f"- id={p.id} name={p.name} code={p.code}" for p in phases])
        class_prompt = f"""请判断以下内容属于哪个项目阶段，只输出阶段ID数字。

项目阶段列表：
{phase_names}

内容摘要（前500字）：
{ocr_text[:500]}

请只回复阶段ID数字（如 1 或 2），不要输出其他内容。"""
        try:
            phase_result = _call_ai(class_prompt).strip()
            suggested_phase_id = int(''.join(c for c in phase_result if c.isdigit()) or '1')
            sp = (db.execute(select(Phase).where(Phase.id == suggested_phase_id))).scalar_one_or_none()
            if sp:
                suggested_phase = {"id": sp.id, "name": sp.name, "code": sp.code}
        except Exception:
            pass

    # Build image gallery in content
    image_gallery = ""
    if saved_image_paths:
        image_gallery = "\n\n## 原始图片\n\n"
        for p in saved_image_paths:
            image_gallery += f"![图片](/uploads/{p})\n\n"

    return {
        "ok": True,
        "type": report_type,
        "type_name": REPORT_TYPES.get(report_type, REPORT_TYPES['stage_report'])['name'],
        "content": report_content + image_gallery,
        "ocr_text": ocr_text,
        "saved_images": saved_image_paths,
        "source": "ocr_image",
        "suggested_phase": suggested_phase,
        "ocr_stats": {
            "total": len(files),
            "recognized": len(ocr_parts),
            "empty": empty_count,
            "failed": failed_count,
        },
        "ocr_errors": ocr_errors if ocr_errors else None,
        "ai_failed": ai_failed,
        "generated_at": _now().isoformat(),
    }


@router.post("/api/report-gen/save-image-report")
async def save_image_report(request: Request, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Save an image-generated report as a project document under a specific phase."""
    import json as _json
    raw = await request.body()
    try:
        data = _json.loads(raw)
    except Exception:
        raw_str = raw.decode("utf-8", errors="replace")
        data = _json.loads(raw_str)
    project_id = data.get("project_id")
    phase_id = data.get("phase_id")
    content = data.get("content", "")
    title = data.get("title", "图片识别报告")
    report_type = data.get("report_type", "stage_report")

    if not project_id or not phase_id:
        raise HTTPException(status_code=400, detail="缺少 project_id 或 phase_id")

    # Get phase name safely (handle encoding issues)
    phase = (db.execute(select(Phase).where(Phase.id == phase_id))).scalar_one_or_none()
    try:
        phase_name = phase.name if phase else ""
        phase_code = phase.code if phase else ""
    except Exception:
        phase_name = f"Phase-{phase_id}"
        phase_code = f"P{phase_id}"

    # Save as a project document — visible in "项目文档" tab
    # Use phase-appropriate doc_type prefix so the UI shows the correct phase
    phase_doc_prefix = {"P0": "p0", "PP1": "pp1", "PP2": "pp2", "PP3": "pp3", "PP4": "pp4"}.get(phase_code, "other")
    doc_name = f"[AI报告] {title}"
    doc_notes = f"由AI从图片OCR识别自动生成"
    try:
        doc = ProjectDocument(
            project_id=project_id,
            phase_id=phase_id,
            name=doc_name,
            doc_type=f"{phase_doc_prefix}_ai_{report_type}",
            content=content, folder="/",
            notes=doc_notes,
            created_by=_user.username,
            upload_date=_today(),
        )
    except Exception:
        # Encoding issues with some fields, try without notes/created_by
        doc = ProjectDocument(
            project_id=project_id,
            phase_id=phase_id,
            name=doc_name,
            doc_type=f"ai_{report_type}",
            content=content, folder="/",
            upload_date=_today(),
        )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    safe_phase = str(phase_id)
    try:
        pn = phase_name.encode('utf-8', errors='replace').decode('utf-8')
        safe_phase = pn
    except: pass

    return {"ok": True, "message": f"报告已保存 → 查看路径：项目文档Tab", "doc_id": doc.id, "phase_name": safe_phase}


@router.get("/api/report-gen/management-weekly")
def management_weekly_summary(
    year: int = Query(None),
    week: int = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Generate a management-level weekly report aggregating all active projects.
    Includes: overall status, per-project progress, key risks, late milestones, action items.
    """
    # Default to current week
    today = _today()
    if not year:
        year = today.isocalendar()[0]
    if not week:
        week = today.isocalendar()[1]

    # Get all active projects
    projects = (db.execute(
        select(Project).where(Project.is_active == True).options(
            selectinload(Project.client),
            selectinload(Project.current_phase),
        )
    )).scalars().all()

    project_summaries = []
    all_risks = []
    total_milestones = 0
    completed_milestones = 0

    for p in projects:
        # Milestones
        milestones = (db.execute(
            select(Milestone).where(Milestone.project_id == p.id)
        )).scalars().all()
        ms_total = len(milestones)
        ms_done = len([m for m in milestones if m.status == "completed"])
        ms_late = len([m for m in milestones
                       if m.status in ("pending", "in_progress")
                       and m.planned_date and m.planned_date < today])

        total_milestones += ms_total
        completed_milestones += ms_done

        # Latest weekly report
        latest_report = (db.execute(
            select(WeeklyReport).where(WeeklyReport.project_id == p.id)
            .order_by(WeeklyReport.year.desc(), WeeklyReport.week_number.desc()).limit(1)
            .options(selectinload(WeeklyReport.line_items))
        )).scalar_one_or_none()

        report_text = ""
        if latest_report:
            report_text = latest_report.overall_progress or ""
            if latest_report.line_items:
                lines_text = "; ".join([
                    f"{li.line.name if li.line else '?'}: {li.this_week or '无'}"
                    for li in latest_report.line_items[:6]
                ])
                report_text += " | " + lines_text

        # Risks
        risks = (db.execute(
            select(RiskIssue).where(RiskIssue.project_id == p.id, RiskIssue.status.in_(["open", "in_progress"]))
        )).scalars().all()
        def is_high_severity(s):
            try: return int(s) >= 3
            except: return s and s.lower() in ("high", "critical", "严重")
        high_risks = [r for r in risks if is_high_severity(r.severity)]

        for r in high_risks:
            all_risks.append({"project": p.name, "title": r.title, "severity": r.severity})

        project_summaries.append({
            "name": p.name,
            "code": p.code,
            "phase": p.current_phase.name if p.current_phase else "",
            "status": p.overall_status or "normal",
            "completion_pct": round(ms_done / ms_total * 100) if ms_total > 0 else 0,
            "milestones_total": ms_total,
            "milestones_done": ms_done,
            "milestones_late": ms_late,
            "risks_open": len(risks),
            "high_risks": len(high_risks),
            "latest_report": report_text[:300],
        })

    # Sort: projects with issues first (late milestones or high risks)
    project_summaries.sort(key=lambda x: -(x["milestones_late"] * 10 + x["high_risks"] * 5))

    # Build AI prompt
    context_json = json.dumps(project_summaries, ensure_ascii=False, indent=2)
    prompt = f"""你是一位项目管理总监，请基于以下数据生成一份《管理层周报》。

当前周期：{year}年第{week}周
项目总数：{len(projects)}
总里程碑完成率：{round(completed_milestones/max(1,total_milestones)*100)}%

各项目数据：
{context_json}

请按以下结构输出：
## 一、本周整体态势
（2-3句话概括整体情况）

## 二、需重点关注项目
（列出有逾期里程碑或高风险的项目，每个2-3句说明问题和建议）

## 三、关键风险汇总
（列出所有高风险项，注明所属项目和严重度）

## 四、各项目进展一览
（表格形式：项目 | 阶段 | 完成率 | 逾期 | 风险 | 本周动向）

## 五、下周管理建议
（3-5条具体可执行的建议）

要求：简洁专业，突出问题，给建议。总计800字以内。"""
    # Skip AI for now — build data-driven report directly
    lines = [
        f"# 管理层周报 — {year}年第{week}周",
        "",
        f"**项目总数**: {len(projects)} | **里程碑完成率**: {round(completed_milestones/max(1,total_milestones)*100)}% | **高风险**: {len(all_risks)}",
        "",
    ]
    attention = [ps for ps in project_summaries if ps["milestones_late"] > 0 or ps["high_risks"] > 0]
    if attention:
        lines.append("## 需重点关注")
        for ps in attention:
            flags = []
            if ps["milestones_late"] > 0: flags.append(f"{ps['milestones_late']}个逾期")
            if ps["high_risks"] > 0: flags.append(f"{ps['high_risks']}个高风险")
            lines.append(f"- **{ps['name']}** ({ps.get('phase','') or ps.get('stage','') or '未知阶段'}): {', '.join(flags)}")
        lines.append("")
    lines.append("## 各项目进展一览")
    lines.append("")
    lines.append("| 项目 | 阶段 | 完成率 | 逾期 | 风险 | 本周动向 |")
    lines.append("|------|------|--------|------|------|----------|")
    for ps in project_summaries:
        rpt = (ps.get("latest_report") or "")[:60]
        lines.append(f"| {ps['name']} | {ps.get('phase','') or ps.get('stage','') or '-'} | {ps['completion_pct']}% | {ps['milestones_late']} | {ps['risks_open']} | {rpt} |")
    lines.append("")
    if all_risks:
        lines.append("## 风险列表")
        for r in all_risks[:10]:
            lines.append(f"- [{r.get('project','')}] {r.get('title','')} — 严重度:{r.get('severity','')} 状态:{r.get('status','')}")
    ai_content = "\n".join(lines)

    return {
        "ok": True,
        "year": year,
        "week": week,
        "title": f"管理层周报 — {year}年第{week}周",
        "report": ai_content,
        "content": ai_content,
        "project_count": len(projects),
        "completion_pct": round(completed_milestones / max(1, total_milestones) * 100),
        "high_risk_count": len(all_risks),
        "late_milestones": sum(1 for ps in project_summaries if ps.get("late_milestones", 0)),
        "attention_count": len([ps for ps in project_summaries if ps.get("risks")]),
        "projects": project_summaries,
        "stats": {
            "total_projects": len(projects),
            "total_milestones": total_milestones,
            "completed_milestones": completed_milestones,
            "completion_pct": round(completed_milestones / max(1, total_milestones) * 100),
            "high_risks": len(all_risks),
        },
        "generated_at": _now().isoformat(),
    }


@router.post("/api/report-gen/ai-fill-baseline")

@router.post("/api/report-gen/ai-fill-baseline")
async def ai_fill_baseline(data: dict, current_user=Depends(get_current_user)):
    """AI auto-fill project baseline from line items."""
    from backend_v2.ai_service import call_task
    lines = data.get("lines", "")
    if not lines:
        return {}

    prompt = (
        "从以下项目各技术线的周进展中，提取项目基线摘要。返回纯JSON: "
        + chr(10) + "{" + chr(10)
        + '  "overall": "本周围绕目标（30字以内）",' + chr(10)
        + '  "accomplishments": "关键成果（50字以内）",' + chr(10)
        + '  "completion_rate": "预计完成率",' + chr(10)
        + '  "stage": "当前阶段",' + chr(10)
        + '  "status": "normal/risk/delayed"' + chr(10)
        + "}" + chr(10) + chr(10)
        + "各技术线进展:" + chr(10)
        + lines
    )

    import asyncio
    try:
        rsp = asyncio.new_event_loop().run_until_complete(
            call_task("summary", [{"role": "user", "content": prompt}])
        )
    except RuntimeError:
        rsp = await call_task("summary", [{"role": "user", "content": prompt}])
    raw = (rsp or "").strip()
    if raw.startswith("`"):
        raw = raw.split(chr(10), 1)[-1]
        if raw.rstrip().endswith("`"):
            raw = raw.rsplit(chr(10), 1)[0]
    import json as _j
    try:
        return _j.loads(raw)
    except:
        return {"overall": "", "accomplishments": "", "completion_rate": "", "stage": "", "status": "normal"}
    # Data-driven template report
    pct = round(completed_milestones/max(1,total_milestones)*100)
    attention = [ps for ps in project_summaries if ps["milestones_late"] > 0 or ps["high_risks"] > 0]

    lines = [
        f"## {year}年第{week}周 · 管理层周报",
        "",
        f"**{len(projects)}** 个活跃项目 &nbsp;|&nbsp; 里程碑完成率 **{pct}%** &nbsp;|&nbsp; 高风险 **{len(all_risks)}** &nbsp;|&nbsp; 逾期里程碑 **{sum(ps['milestones_late'] for ps in project_summaries)}**",
        "",
    ]

    if attention:
        lines.append("### 需关注")
        for ps in attention:
            flags = []
            if ps["milestones_late"] > 0: flags.append(f"{ps['milestones_late']}个逾期")
            if ps["high_risks"] > 0: flags.append(f"{ps['high_risks']}个高风险")
            pct_bar = chr(9608) * max(1, ps["completion_pct"] // 10) + chr(9617) * (10 - max(1, ps["completion_pct"] // 10))
            lines.append(f"- **{ps['name']}** {pct_bar} {ps['completion_pct']}% &nbsp; {', '.join(flags)}")
        lines.append("")

    lines.append("### 项目进展一览")
    lines.append("| 项目 | 阶段 | 完成率 | 逾期 | 本周动向 |")
    lines.append("|------|------|--------|------|----------|")
    for ps in project_summaries:
        rpt = (ps.get("latest_report") or "")[:80]
        late_flag = f" **{ps['milestones_late']}**" if ps["milestones_late"] > 0 else " 0"
        lines.append(f"| **{ps['name']}** | {ps.get('phase','') or '-'} | {ps['completion_pct']}% |{late_flag} | {rpt} |")

    ai_content = chr(10).join(lines)