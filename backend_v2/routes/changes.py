"""Change request CRUD + 两级签核(1=项目负责人, 2=管理层复核)。"""
import os
import tempfile
import threading
import uuid
from datetime import date, datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Request
from fastapi.responses import FileResponse
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.audit import log_audit
from backend_v2.config import settings
from backend_v2.permissions import require_permission
from backend_v2.schemas import ChangeCreate, ChangeUpdate
from backend_v2.models import ChangeRequest, ChangeSignoffRecord, Project, TeamMember

ATTACH_DIR = Path(settings.UPLOAD_DIR) / "change_attachments"
ATTACH_EXTS = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "png", "jpg", "jpeg", "zip"}

router = APIRouter(tags=["changes"])


def signoff_to_dict(r):
    d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
    d["signer_name"] = r.signer.name if r.signer else None
    d["signed_at"] = r.signed_at.isoformat() if r.signed_at else None
    d["created_at"] = r.created_at.isoformat() if r.created_at else None
    return d


def _change_signoffs(db: Session, change_id: int):
    rows = db.execute(
        select(ChangeSignoffRecord).where(ChangeSignoffRecord.change_id == change_id)
        .order_by(ChangeSignoffRecord.level)
    ).scalars().all()
    return [signoff_to_dict(r) for r in rows]


def _signoff_permission_check(rec, current_user):
    """签核人本人或管理员可操作。"""
    if current_user.role == "admin":
        return
    if current_user.member_id and current_user.member_id == rec.signer_id:
        return
    raise HTTPException(status_code=403, detail="仅签核人本人或管理员可操作")


@router.get("/api/changes")
def list_all_changes(limit: int = Query(20), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Get recent changes across all active projects."""
    q = select(ChangeRequest).join(Project).where(Project.is_active == True).order_by(ChangeRequest.created_at.desc()).limit(limit)
    results = []
    for c in db.execute(q).scalars().all():
        results.append({
            "id": c.id, "project_id": c.project_id, "title": c.title,
            "description": c.description, "status": c.status, "change_level": c.change_level,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "submitted_date": c.submitted_date.isoformat() if c.submitted_date else None,
        })
    return results


@router.get("/api/approvals/pending")
def pending_approvals(db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    """Get all pending approvals (change signoffs + gate review items)."""
    from sqlalchemy.orm import selectinload
    from backend_v2.models import ReviewActionItem

    items = []

    # Pending change signoff records (两级签核)
    change_result = db.execute(
        select(ChangeSignoffRecord).options(selectinload(ChangeSignoffRecord.change).selectinload(ChangeRequest.project))
        .where(ChangeSignoffRecord.status == "pending")
        .order_by(ChangeSignoffRecord.created_at.desc()).limit(20)
    )
    for s in change_result.scalars().all():
        c = s.change
        if not c or not c.project or not c.project.is_active:
            continue
        items.append({
            "type": "change_signoff", "id": s.id, "change_id": c.id,
            "title": c.title, "project_id": c.project_id,
            "project_name": c.project.name if c.project else None,
            "level": s.level, "reason": c.description, "signer_name": s.signer.name if s.signer else None,
            "submitted_date": c.submitted_date.isoformat() if c.submitted_date else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })

    # Pending review action items (from phase gates)
    rai_result = db.execute(
        select(ReviewActionItem).where(ReviewActionItem.status == "open").order_by(ReviewActionItem.due_date.asc()).limit(10)
    )
    for rai in rai_result.scalars().all():
        pg = rai.phase_gate
        items.append({
            "type": "review_action", "id": rai.id, "title": rai.title,
            "project_id": pg.project_id if pg else None,
            "project_name": pg.project.name if pg and pg.project else None,
            "phase_id": pg.phase_id if pg else None,
            "assigned_to": rai.assigned_to, "due_date": rai.due_date.isoformat() if rai.due_date else None,
        })

    return sorted(items, key=lambda x: x.get("created_at") or x.get("due_date") or "", reverse=True)


def change_to_dict(c):
    d = {k: getattr(c, k) for k in c.__table__.columns.keys()}
    for df in ("submitted_date", "decision_date"):
        d[df] = d[df].isoformat() if d.get(df) else None
    d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
    d["requester"] = {"id": c.requester.id, "name": c.requester.name} if c.requester else None
    d["reviewer"] = {"id": c.reviewer.id, "name": c.reviewer.name} if c.reviewer else None
    d["attachment"] = {
        "name": c.attachment_name,
        "size": c.attachment_size,
        "url": f"/api/changes/{c.id}/attachment" if c.attachment_path else None,
    } if c.attachment_path else None
    return d


@router.get("/api/projects/{project_id}/changes")
def list_changes(project_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    result = db.execute(
        select(ChangeRequest).where(ChangeRequest.project_id == project_id).order_by(ChangeRequest.created_at.desc())
    )
    rows = []
    for c in result.scalars().all():
        d = change_to_dict(c)
        d["signoffs"] = _change_signoffs(db, c.id)
        rows.append(d)
    return rows


@router.post("/api/projects/{project_id}/changes", status_code=201)
def create_change(
    project_id: int, data: dict,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    title = (data.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="变更标题不能为空")
    l1 = data.get("level1_signer_id")
    l2 = data.get("level2_signer_id")
    if not l1 or not l2:
        raise HTTPException(status_code=400, detail="请指定两级签核人")
    if not db.get(TeamMember, int(l1)) or not db.get(TeamMember, int(l2)):
        raise HTTPException(status_code=400, detail="签核人不存在")
    c = ChangeRequest(
        project_id=project_id,
        title=title,
        description=data.get("description") or None,
        change_level=data.get("change_level") or "C",
        requester_id=int(data["requester_id"]) if data.get("requester_id") else None,
        affected_lines=data.get("affected_lines") or None,
        impact_scope=data.get("impact_scope") or None,
        impact_schedule=data.get("impact_schedule") or None,
        impact_cost=data.get("impact_cost") or None,
        submitted_date=datetime.strptime(data["submitted_date"], "%Y-%m-%d").date()
        if data.get("submitted_date") else datetime.utcnow().date(),
        status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(c)
    db.flush()
    db.add_all([
        ChangeSignoffRecord(change_id=c.id, level=1, signer_id=int(l1)),
        ChangeSignoffRecord(change_id=c.id, level=2, signer_id=int(l2)),
    ])
    db.commit()
    db.refresh(c)
    log_audit(db, current_user.username, "create", "change", c.id, c.title, project_id, f"创建变更: {c.title}")
    db.commit()
    d = change_to_dict(c)
    d["signoffs"] = _change_signoffs(db, c.id)
    return d


def _requester_permission_check(c, current_user):
    """申请人本人或管理员可撤回/重新提交。"""
    if current_user.role == "admin":
        return
    if c.requester_id and current_user.member_id and current_user.member_id == c.requester_id:
        return
    raise HTTPException(status_code=403, detail="仅申请人本人或管理员可操作")


@router.post("/api/changes/{change_id}/withdraw")
def withdraw_change(change_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """申请人本人撤回已提交的变更:取消进行中的签核(保留已签核记录作为历史),状态改为已撤回。"""
    c = db.get(ChangeRequest, change_id)
    if not c:
        raise HTTPException(status_code=404, detail="变更不存在")
    _requester_permission_check(c, current_user)
    if c.status not in ("pending", "under_review"):
        raise HTTPException(status_code=400, detail="仅待审批/审批中的变更可撤回")
    c.status = "withdrawn"
    pending = db.execute(
        select(ChangeSignoffRecord).where(ChangeSignoffRecord.change_id == change_id,
                                          ChangeSignoffRecord.status == "pending")
    ).scalars().all()
    for rec in pending:
        db.delete(rec)
    db.commit()
    log_audit(db, current_user.username, "update", "change", c.id, c.title, c.project_id,
              f"撤回变更: {c.title}（取消待签核 {len(pending)} 条）")
    db.commit()
    d = change_to_dict(c)
    d["signoffs"] = _change_signoffs(db, c.id)
    return d


@router.post("/api/changes/{change_id}/resubmit")
def resubmit_change(change_id: int, data: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """撤回后重新提交:为缺失的签核级别重建待签核记录(已签核级别保留)。"""
    c = db.get(ChangeRequest, change_id)
    if not c:
        raise HTTPException(status_code=404, detail="变更不存在")
    _requester_permission_check(c, current_user)
    if c.status != "withdrawn":
        raise HTTPException(status_code=400, detail="仅已撤回的变更可重新提交")
    existing = db.execute(
        select(ChangeSignoffRecord).where(ChangeSignoffRecord.change_id == change_id)
    ).scalars().all()
    levels = {r.level for r in existing}
    new_records = []
    for level, key in ((1, "level1_signer_id"), (2, "level2_signer_id")):
        if level in levels:
            continue
        signer_id = data.get(key)
        if not signer_id or not db.get(TeamMember, int(signer_id)):
            raise HTTPException(status_code=400, detail=f"请指定{'一级' if level == 1 else '二级'}签核人")
        new_records.append(ChangeSignoffRecord(change_id=c.id, level=level, signer_id=int(signer_id)))
    if not new_records:
        raise HTTPException(status_code=400, detail="无需重建签核记录")
    db.add_all(new_records)
    l1 = next((r for r in existing if r.level == 1 and r.status == "approved"), None)
    c.status = "under_review" if l1 else "pending"
    db.commit()
    log_audit(db, current_user.username, "update", "change", c.id, c.title, c.project_id,
              f"重新提交变更: {c.title}（重建签核 {len(new_records)} 条）")
    db.commit()
    d = change_to_dict(c)
    d["signoffs"] = _change_signoffs(db, c.id)
    return d


@router.put("/api/changes/{change_id}")
def update_change(change_id: int, data: ChangeUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    result = db.execute(select(ChangeRequest).where(ChangeRequest.id == change_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="不存在")
    upd = data.model_dump(exclude_unset=True)
    db.execute(update(ChangeRequest).where(ChangeRequest.id == change_id).values(**upd))
    log_audit(db, current_user.username, "update", "change", change_id, c.title, c.project_id, "更新变更请求")
    db.commit()
    c2 = (db.execute(select(ChangeRequest).where(ChangeRequest.id == change_id))).scalar_one()
    d = change_to_dict(c2)
    d["signoffs"] = _change_signoffs(db, c2.id)
    return d


def _change_attachment_file(c: ChangeRequest) -> Path:
    if not c.attachment_path:
        raise HTTPException(status_code=404, detail="该变更无附件")
    f = ATTACH_DIR / Path(c.attachment_path).name
    if not f.exists():
        raise HTTPException(status_code=404, detail="附件文件缺失")
    return f


@router.post("/api/changes/{change_id}/attachment")
def upload_change_attachment(
    change_id: int, file: UploadFile = File(...),
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    c = db.get(ChangeRequest, change_id)
    if not c:
        raise HTTPException(status_code=404, detail="变更不存在")
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")
    ext = Path(file.filename).suffix.lstrip(".").lower()
    if ext not in ATTACH_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的附件格式: .{ext}（支持 pdf/doc/docx/xls/xlsx/ppt/pptx/图片/zip）")
    content = file.file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"附件超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")
    ATTACH_DIR.mkdir(parents=True, exist_ok=True)
    # 覆盖式:新附件替换旧附件(后台删除旧文件,避免 NAS 慢 IO 阻塞上传)
    if c.attachment_path:
        _unlink_async(ATTACH_DIR / Path(c.attachment_path).name)
    safe = f"{uuid.uuid4().hex[:12]}_{Path(file.filename).name}"
    dest = ATTACH_DIR / safe
    with open(dest, "wb") as f:
        f.write(content)
    c.attachment_path = str(dest.relative_to(Path(settings.UPLOAD_DIR)))
    c.attachment_name = file.filename
    c.attachment_size = len(content)
    log_audit(db, current_user.username, "update", "change", c.id, c.title, c.project_id, f"上传变更附件: {file.filename}")
    db.commit()
    return change_to_dict(c)


PREVIEW_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
}
OFFICE_PREVIEW_EXTS = {"xlsx", "xls", "docx", "pptx"}


def _sheet_html(rows, sheet_name=None):
    """二维行列表 → HTML 表格(单元格全部转义,防注入)。"""
    import html
    if not rows:
        return ""
    head = f"<div class='sheet-name'>📄 {html.escape(sheet_name)}</div>" if sheet_name else ""
    body = ""
    for row in rows:
        body += "<tr>" + "".join(f"<td>{html.escape(str(v)) if v is not None else ''}</td>" for v in row) + "</tr>"
    return head + f"<table>{body}</table>"


def _xlsx_to_html(content: bytes) -> str:
    import io
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    parts = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        parts.append(_sheet_html(rows, ws.title))
    return "".join(parts)


def _xls_to_html(content: bytes) -> str:
    import io
    import xlrd
    book = xlrd.open_workbook(file_contents=content)
    parts = []
    for sh in book.sheets():
        rows = [sh.row_values(i) for i in range(sh.nrows)]
        parts.append(_sheet_html(rows, sh.name))
    return "".join(parts)


def _docx_to_html(content: bytes) -> str:
    import io
    import html
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = docx.Document(io.BytesIO(content))
    parts = []
    for block in doc.element.body.iterchildren():
        if block.tag.endswith("}p"):
            t = Paragraph(block, doc).text.strip()
            if t:
                parts.append(f"<p>{html.escape(t)}</p>")
        elif block.tag.endswith("}tbl"):
            tb = Table(block, doc)
            parts.append(_sheet_html([[c.text.strip() for c in r.cells] for r in tb.rows]))
    return "".join(parts)


def _pptx_to_html(content: bytes) -> str:
    import io
    import html
    from pptx import Presentation
    prs = Presentation(io.BytesIO(content))
    parts = []
    for i, slide in enumerate(prs.slides, 1):
        texts = [sh.text.strip() for sh in slide.shapes if sh.has_text_frame and sh.text.strip()]
        if texts:
            parts.append(f"<div class='sheet-name'>第 {i} 页</div>" +
                         "".join(f"<p>{html.escape(t)}</p>" for t in texts))
    return "".join(parts)


def office_to_html_bytes(content: bytes, ext: str) -> str:
    """Office 附件内容 → HTML 预览页(纯内存解析,不落盘);失败或老格式返回提示页。"""
    ext = ext.lower().lstrip(".")
    try:
        if ext == "xlsx":
            body = _xlsx_to_html(content)
        elif ext == "xls":
            body = _xls_to_html(content)
        elif ext == "docx":
            body = _docx_to_html(content)
        elif ext == "pptx":
            body = _pptx_to_html(content)
        else:
            body = ""
    except Exception:
        body = ""
    if not body:
        body = "<div class='no-preview'>该文件格式暂不支持在线预览，请下载查看</div>"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>附件预览</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;margin:16px;color:#333;font-size:13px}}
table{{border-collapse:collapse;width:100%;margin-bottom:16px}}
td,th{{border:1px solid #d0d7de;padding:6px 8px;word-break:break-all;max-width:400px}}
th{{background:#f6f8fa;font-weight:600}}
p{{margin:4px 0;line-height:1.6}}
.sheet-name{{font-size:13px;font-weight:600;color:#1f3a5f;margin:12px 0 4px}}
.no-preview{{padding:40px;text-align:center;color:#909399}}
</style></head><body>{body}</body></html>"""


def office_to_html(f: Path) -> str:
    """文件路径版,供下载预览接口复用。"""
    return office_to_html_bytes(f.read_bytes(), f.suffix)


_LO_EXE = r"C:\Program Files\LibreOffice\program\soffice.exe"
_lo_lock = threading.Lock()
_lo_profile = None


def _lo_profile_path():
    global _lo_profile
    if _lo_profile is None:
        d = Path(tempfile.gettempdir()) / "motor_pm_lo_profile"
        d.mkdir(exist_ok=True)
        _lo_profile = str(d)
    return _lo_profile


def _set_xlsx_landscape_fit(path: Path):
    """宽表格转 PDF 前设为横向+适应页宽,避免列被拆分到多页导致预览内容不全。

    LibreOffice 默认按 A4 纵向分页,列多的表格会被拆到不同页,
    预览时看起来内容缺失;openpyxl 内嵌打印设置会被 LibreOffice 尊重。
    """
    try:
        import openpyxl
        from openpyxl.worksheet.properties import PageSetupProperties
        wb = openpyxl.load_workbook(path)
        for ws in wb.worksheets:
            ws.page_setup.orientation = "landscape"
            ws.page_setup.fitToWidth = 1
            ws.page_setup.fitToHeight = 0
            ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        wb.save(path)
    except Exception:
        pass


def office_to_pdf_bytes(content: bytes, ext: str):
    """Office 内容 → PDF 字节(LibreOffice headless,保持原始排版);失败返回 None。"""
    import subprocess
    import shutil
    ext = ext.lower().lstrip(".")
    if ext not in OFFICE_PREVIEW_EXTS:
        return None
    tmp = Path(tempfile.mkdtemp(prefix="lo_conv_"))
    try:
        src = tmp / f"doc.{ext}"
        src.write_bytes(content)
        if ext in ("xlsx", "xlsm"):
            _set_xlsx_landscape_fit(src)
        out = tmp / "out"
        out.mkdir()
        cmd = [_LO_EXE,
               f"-env:UserInstallation=file:///{_lo_profile_path().replace(os.sep, '/')}",
               "--headless", "--norestore", "--convert-to", "pdf",
               "--outdir", str(out), str(src)]
        with _lo_lock:
            r = subprocess.run(cmd, capture_output=True, timeout=90)
        pdf = out / "doc.pdf"
        if r.returncode != 0 or not pdf.exists():
            return None
        return pdf.read_bytes()
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@router.get("/api/changes/{change_id}/attachment")
def download_change_attachment(
    change_id: int, token: str = Query(None), view: int = Query(0),
    db: Session = Depends(get_db), request: Request = None,
):
    """兼容 <a href> 无法带 header 的场景:支持 ?token= 认证。
    ?view=1 时以正确 content-type 内联返回(pdf/图片可浏览器预览),默认强制下载。"""
    from backend_v2.auth import verify_token
    if request and request.headers.get("authorization", "").lower().startswith("bearer "):
        verify_token(request.headers["authorization"][7:])
    elif token:
        verify_token(token)
    else:
        raise HTTPException(status_code=401, detail="未认证")
    c = db.get(ChangeRequest, change_id)
    if not c:
        raise HTTPException(status_code=404, detail="变更不存在")
    f = _change_attachment_file(c)
    ext = f.suffix.lstrip(".").lower()
    if view and ext in PREVIEW_MEDIA_TYPES:
        # 不传 filename:Content-Disposition 保持 inline,浏览器直接渲染预览
        return FileResponse(str(f), media_type=PREVIEW_MEDIA_TYPES[ext])
    if view and ext in OFFICE_PREVIEW_EXTS:
        pdf = office_to_pdf_bytes(f.read_bytes(), ext)
        if pdf:
            from fastapi.responses import Response
            return Response(content=pdf, media_type="application/pdf")
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=office_to_html(f))
    return FileResponse(str(f), media_type="application/octet-stream", filename=c.attachment_name or f.name)


@router.post("/api/changes/preview-attachment")
def preview_attachment_upload(
    file: UploadFile = File(...),
    _current_user=Depends(get_current_user),
):
    """选完附件立即预览:Office 文件内存解析转 HTML(不落盘);pdf/图片返回 raw 由前端本地渲染。"""
    name = file.filename or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    content = file.file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"附件超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")
    if ext in PREVIEW_MEDIA_TYPES:
        return {"kind": "raw"}
    if ext in OFFICE_PREVIEW_EXTS:
        pdf = office_to_pdf_bytes(content, ext)
        if pdf:
            from fastapi.responses import Response
            return Response(content=pdf, media_type="application/pdf")
        return {"kind": "html", "html": office_to_html_bytes(content, ext)}
    return {"kind": "unsupported"}


def _unlink_async(path: Path):
    """NAS 上 unlink 可能耗时数秒(网络+加密驱动),后台线程删除避免阻塞接口响应。"""
    import threading
    threading.Thread(target=lambda: path.unlink(missing_ok=True), daemon=True).start()


@router.delete("/api/changes/{change_id}/attachment")
def delete_change_attachment(change_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = db.get(ChangeRequest, change_id)
    if not c:
        raise HTTPException(status_code=404, detail="变更不存在")
    f = _change_attachment_file(c)
    _unlink_async(f)
    c.attachment_path = None
    c.attachment_name = None
    c.attachment_size = None
    log_audit(db, current_user.username, "update", "change", c.id, c.title, c.project_id, "删除变更附件")
    db.commit()
    return change_to_dict(c)


@router.delete("/api/changes/{change_id}")
def delete_change(change_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    result = db.execute(select(ChangeRequest).where(ChangeRequest.id == change_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="不存在")
    if c.attachment_path:
        _unlink_async(ATTACH_DIR / Path(c.attachment_path).name)
    db.execute(delete(ChangeSignoffRecord).where(ChangeSignoffRecord.change_id == change_id))
    db.execute(delete(ChangeRequest).where(ChangeRequest.id == change_id))
    log_audit(db, current_user.username, "delete", "change", change_id, c.title, c.project_id, f"删除变更: {c.title}")
    db.commit()
    return {"message": "已删除"}


# ── 两级签核 ──

@router.post("/api/changes/signoffs/{signoff_id}/approve")
def approve_change_signoff(
    signoff_id: int, data: dict,
    db: Session = Depends(get_db), current_user=Depends(require_permission("projects", "edit")),
):
    rec = db.get(ChangeSignoffRecord, signoff_id)
    if not rec:
        raise HTTPException(status_code=404, detail="签核记录不存在")
    _signoff_permission_check(rec, current_user)
    if rec.status != "pending":
        raise HTTPException(status_code=400, detail="该记录已处理")
    c = db.get(ChangeRequest, rec.change_id)
    if not c:
        raise HTTPException(status_code=404, detail="变更不存在")
    if rec.level == 2:
        l1 = db.execute(
            select(ChangeSignoffRecord).where(ChangeSignoffRecord.change_id == c.id,
                                              ChangeSignoffRecord.level == 1)
        ).scalar_one_or_none()
        if not l1 or l1.status != "approved":
            raise HTTPException(status_code=400, detail="需先完成一级签核")
        c.status = "approved"
        c.decision_date = date.today()
    else:
        c.status = "under_review"
    rec.status = "approved"
    rec.comment = (data.get("comment") or "").strip() or None
    rec.signed_by_username = current_user.username
    rec.signed_at = datetime.utcnow()
    db.commit()
    log_audit(db, current_user.username, "update", "change", c.id, c.title, c.project_id,
              f"变更签核通过(L{rec.level})" + (f":{rec.comment}" if rec.comment else ""))
    return signoff_to_dict(rec)


@router.post("/api/changes/signoffs/{signoff_id}/reject")
def reject_change_signoff(
    signoff_id: int, data: dict,
    db: Session = Depends(get_db), current_user=Depends(require_permission("projects", "edit")),
):
    rec = db.get(ChangeSignoffRecord, signoff_id)
    if not rec:
        raise HTTPException(status_code=404, detail="签核记录不存在")
    _signoff_permission_check(rec, current_user)
    if rec.status != "pending":
        raise HTTPException(status_code=400, detail="该记录已处理")
    c = db.get(ChangeRequest, rec.change_id)
    if not c:
        raise HTTPException(status_code=404, detail="变更不存在")
    rec.status = "rejected"
    rec.comment = (data.get("comment") or "").strip() or "驳回"
    rec.signed_by_username = current_user.username
    rec.signed_at = datetime.utcnow()
    c.status = "rejected"
    c.decision_date = date.today()
    db.commit()
    log_audit(db, current_user.username, "update", "change", c.id, c.title, c.project_id,
              f"变更签核驳回(L{rec.level}):{rec.comment}")
    return signoff_to_dict(rec)
