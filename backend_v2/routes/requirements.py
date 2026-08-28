"""Requirement management CRUD + Excel import/export + image upload."""
import json as jsonlib
import uuid as _uuid
from pathlib import Path as FilePath
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.config import settings
from backend_v2.models import Requirement, Project, Deliverable
import openpyxl
from io import BytesIO

router = APIRouter(tags=["requirements"])

ALLOWED_ATTACHMENTS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "pdf", "doc", "docx", "xlsx", "xls", "zip", "pptx", "ppt", "txt", "csv", "dwg", "step", "stp", "stl", "igs", "iges", "dxf", "svg", "mp4", "avi", "mov", "mkv"}


def req_to_dict(r):
    d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
    for k in ("created_at", "updated_at"):
        d[k] = d[k].isoformat() if d.get(k) else None
    return d


@router.get("/api/projects/{project_id}/requirements")
def list_reqs(project_id: int, category: str = Query(None), priority: str = Query(None),
                    db: Session = Depends(get_db), _user=Depends(get_current_user)):
    q = select(Requirement).where(Requirement.project_id == project_id)
    if category: q = q.where(Requirement.category == category)
    if priority: q = q.where(Requirement.priority == priority)
    q = q.order_by(Requirement.priority, Requirement.created_at.desc())
    result = db.execute(q)
    return [req_to_dict(r) for r in result.scalars().all()]


@router.post("/api/projects/{project_id}/requirements", status_code=201)
def create_req(project_id: int, data: dict,
                     db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = Requirement(project_id=project_id, created_at=datetime.utcnow(), **{k: v for k, v in data.items()
                     if k in ("title", "description", "category", "priority", "source", "status", "deliverable_id")})
    db.add(r)
    db.commit()
    db.refresh(r)
    return req_to_dict(r)


@router.put("/api/requirements/{req_id}")
def update_req(req_id: int, data: dict,
                     db: Session = Depends(get_db), user=Depends(get_current_user)):
    from sqlalchemy import update as up
    result = db.execute(select(Requirement).where(Requirement.id == req_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="需求不存在")

    allowed = {"title", "description", "category", "priority", "source", "status", "deliverable_id", "attachment_path"}
    upd = {k: v for k, v in data.items() if k in allowed}
    if upd:
        # Version tracking
        ver = r.version or 1
        hist = jsonlib.loads(r.change_history or "[]")
        hist.append({"version": ver + 1, "date": datetime.utcnow().isoformat()[:10], "changes": list(upd.keys()), "author": user.username})
        upd["version"] = ver + 1
        upd["change_history"] = jsonlib.dumps(hist, ensure_ascii=False)
        upd["updated_at"] = datetime.utcnow()
        db.execute(up(Requirement).where(Requirement.id == req_id).values(**upd))
        db.commit()
    return {"message": "已更新"}


@router.delete("/api/requirements/{req_id}")
def delete_req(req_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import delete as dl
    result = db.execute(select(Requirement).where(Requirement.id == req_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="需求不存在")
    db.execute(dl(Requirement).where(Requirement.id == req_id))
    db.commit()
    return {"message": "已删除"}


# ═══════════════════ Excel Upload ═══════════════════

REQ_HEADERS = ["标题", "分类", "优先级", "来源", "描述", "状态"]
CATEGORY_MAP = {"功能": "functional", "性能": "performance", "接口": "interface", "安全": "safety", "可靠性": "reliability", "成本": "cost"}


@router.post("/api/requirements/{req_id}/upload-attachment", status_code=201)
async def upload_req_attachment(req_id: int, file: UploadFile = File(...),
                                db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Upload an image or document attachment to a requirement."""
    r = (db.execute(select(Requirement).where(Requirement.id == req_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="需求不存在")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else ""
    if ext not in ALLOWED_ATTACHMENTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: .{ext}")

    upload_dir = FilePath(settings.UPLOAD_DIR) / str(r.project_id) / "requirements"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{_uuid.uuid4().hex[:8]}_{file.filename}"
    dest = upload_dir / safe_name

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不超过 20MB")
    with open(dest, "wb") as f:
        f.write(content)

    rel_path = str(dest.relative_to(FilePath(settings.UPLOAD_DIR).parent))
    from sqlalchemy import update as up
    db.execute(up(Requirement).where(Requirement.id == req_id).values(attachment_path=rel_path))
    db.commit()
    return {"message": "附件已上传", "attachment_path": rel_path, "file_name": file.filename}


@router.delete("/api/requirements/{req_id}/attachment")
def delete_req_attachment(req_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Remove attachment from a requirement."""
    r = (db.execute(select(Requirement).where(Requirement.id == req_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="需求不存在")
    from sqlalchemy import update as up
    db.execute(up(Requirement).where(Requirement.id == req_id).values(attachment_path=None))
    db.commit()
    return {"message": "附件已清除"}


@router.post("/api/projects/{project_id}/requirements/upload")
async def upload_reqs(project_id: int, file: UploadFile = File(...),
                      db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Upload requirements from Excel. Headers: 标题 | 分类 | 优先级 | 来源 | 描述 | 状态"""
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else ""
    if ext not in ("xlsx", "xls"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls")

    wb = openpyxl.load_workbook(BytesIO(await file.read()))
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    created = 0

    for row in rows:
        if not row or not any(c for c in row): continue
        vals = [str(c).strip() if c is not None else "" for c in row]
        title = vals[0] if len(vals) > 0 else ""
        if not title: continue
        cat_raw = vals[1] if len(vals) > 1 else ""
        category = CATEGORY_MAP.get(cat_raw, "functional")
        priority = vals[2] if len(vals) > 2 and vals[2] else "P1"
        source = vals[3] if len(vals) > 3 else ""
        desc = vals[4] if len(vals) > 4 else ""
        status = vals[5] if len(vals) > 5 and vals[5] else "draft"

        req = Requirement(project_id=project_id, title=title, category=category,
                          priority=priority, source=source, description=desc,
                          status=status, created_at=datetime.utcnow())
        db.add(req)
        created += 1

    db.commit()
    return {"message": f"导入完成", "created": created}


@router.get("/api/projects/{project_id}/requirements/template")
def download_template(project_id: int):
    """Download an Excel template for requirements import."""
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "需求清单"
    ws.append(REQ_HEADERS)
    # Add example row
    ws.append(["额定功率≥200kW@800VDC", "性能", "P0", "技术协议", "在额定工况下持续输出≥200kW", "已批准"])
    ws.column_dimensions['A'].width = 35; ws.column_dimensions['B'].width = 10
    ws.column_dimensions['C'].width = 8; ws.column_dimensions['D'].width = 12
    ws.column_dimensions['E'].width = 40; ws.column_dimensions['F'].width = 10

    output = BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=Requirements-Template-{project_id}.xlsx"})


@router.get("/api/projects/{project_id}/requirements/export")
def export_reqs(project_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Export requirements to Excel."""
    result = db.execute(select(Requirement).where(Requirement.project_id == project_id).order_by(Requirement.priority, Requirement.created_at))
    reqs = result.scalars().all()

    cat_rev = {v: k for k, v in CATEGORY_MAP.items()}
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "需求清单"
    ws.append(REQ_HEADERS)
    for r in reqs:
        ws.append([r.title, cat_rev.get(r.category, r.category or ""), r.priority or "",
                    r.source or "", r.description or "", r.status or ""])

    output = BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=Requirements-List-{project_id}.xlsx"})


@router.post("/api/projects/{project_id}/requirements/ai-parse")
async def ai_parse_requirements(project_id: int, data: dict, _user=Depends(get_current_user)):
    """AI-assisted requirement extraction from raw text (SOR/emails/chat)."""
    raw_text = data.get("text", "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="请输入文本内容")

    from backend_v2.ai_service import _call_llm, load_config

    prompt = f"""你是需求工程师。从以下原始文本中提取需求条目。每条需求包含4个字段。

原始文本：
{raw_text[:4000]}

请以JSON格式输出（只输出JSON，不要其他文字）：
[
  {{"title": "需求标题（简洁，15字以内）", "description": "需求描述（1-2句话）", "category": "functional/performance/interface/safety/reliability/cost", "priority": "P0/P1/P2/P3", "source": "来源（客户/技术协议/标准规范/内部）"}}
]

分类判定：
- functional=功能需求, performance=性能指标, interface=接口要求
- safety=安全要求, reliability=可靠性, cost=成本/预算

优先级判定：
- P0=必须满足, P1=重要, P2=一般, P3=建议

提取3-8条最主要的需求，省略明显不重要的内容。"""

    messages = [
        {"role": "system", "content": "你是需求分析专家，从文档中提取结构化需求。只输出JSON数组。"},
        {"role": "user", "content": prompt},
    ]

    try:
        reply = await _call_llm(messages)
        # Extract JSON from reply
        import re, json
        match = re.search(r'\[[\s\S]*\]', reply)
        if match:
            items = json.loads(match.group())
        else:
            items = []
        return {"ok": True, "items": items, "raw": reply[:300]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI解析失败: {str(e)[:200]}")
