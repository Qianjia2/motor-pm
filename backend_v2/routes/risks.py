"""Risk/Issue CRUD + close with verification attachment."""
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import Session
from pathlib import Path
import aiofiles, uuid
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.audit import log_audit
from backend_v2.config import settings
from backend_v2.schemas import RiskIssueCreate, RiskIssueUpdate, CloseRiskRequest
from backend_v2.models import RiskIssue, Project

router = APIRouter(tags=["risks"])


@router.get("/api/risks")
def list_all_risks(limit: int = Query(20), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Get recent risks/issues across all active projects."""
    q = select(RiskIssue).join(Project).where(Project.is_active == True).order_by(RiskIssue.created_at.desc()).limit(limit)
    return [risk_to_dict(r) for r in db.execute(q).scalars().all()]


def risk_to_dict(r):
    d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
    for df in ("identified_date", "target_resolve_date", "resolved_date"):
        d[df] = d[df].isoformat() if d.get(df) else None
    d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
    d["owner"] = {"id": r.owner.id, "name": r.owner.name} if r.owner else None
    d["line"] = {"id": r.line.id, "name": r.line.name} if r.line else None
    d["phase"] = {"id": r.phase.id, "name": r.phase.name} if r.phase else None
    return d


@router.get("/api/projects/{project_id}/risks")
def list_risks(
    project_id: int,
    type: str = Query(None),
    status: str = Query(None),
    risk_level: str = Query(None),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    q = select(RiskIssue).where(RiskIssue.project_id == project_id)
    if type:
        q = q.where(RiskIssue.type == type)
    if status:
        q = q.where(RiskIssue.status == status)
    if risk_level:
        q = q.where(RiskIssue.risk_level == risk_level)
    q = q.order_by(RiskIssue.created_at.desc())
    result = db.execute(q)
    return [risk_to_dict(r) for r in result.scalars().all()]


@router.post("/api/projects/{project_id}/risks", status_code=201)
def create_risk(
    project_id: int, data: RiskIssueCreate,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    r = RiskIssue(project_id=project_id, created_at=datetime.utcnow(), **data.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    log_audit(db, current_user.username, "create", "risk", r.id, r.title, project_id, f"创建{'风险' if r.type == 'risk' else '问题'}: {r.title}")
    db.commit()
    return risk_to_dict(r)


@router.put("/api/risks/{risk_id}")
def update_risk(risk_id: int, data: RiskIssueUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    result = db.execute(select(RiskIssue).where(RiskIssue.id == risk_id))
    r = result.scalars().one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="不存在")
    upd = data.model_dump(exclude_unset=True)
    db.execute(update(RiskIssue).where(RiskIssue.id == risk_id).values(**upd))
    log_audit(db, current_user.username, "update", "risk", risk_id, r.title, r.project_id, "更新风险/问题")
    db.commit()
    return risk_to_dict((db.execute(select(RiskIssue).where(RiskIssue.id == risk_id))).scalar_one())


@router.delete("/api/risks/{risk_id}")
def delete_risk(risk_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    result = db.execute(select(RiskIssue).where(RiskIssue.id == risk_id))
    r = result.scalars().one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="不存在")
    db.execute(delete(RiskIssue).where(RiskIssue.id == risk_id))
    log_audit(db, current_user.username, "delete", "risk", risk_id, r.title, r.project_id, f"删除风险/问题: {r.title}")
    db.commit()
    return {"message": "已删除"}


@router.post("/api/risks/{risk_id}/close")
async def close_risk(
    risk_id: int,
    resolution: str = Form(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Close a risk/issue with mandatory resolution and optional verification attachment."""
    result = db.execute(select(RiskIssue).where(RiskIssue.id == risk_id))
    r = result.scalars().one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="不存在")
    if not resolution.strip():
        raise HTTPException(status_code=400, detail="关闭时必须填写验证结果")

    attachment_path = None
    if file and file.filename:
        # Validate extension
        ext = Path(file.filename).suffix.lstrip(".").lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: .{ext}")

        upload_dir = Path(settings.UPLOAD_DIR) / str(r.project_id) / "risks"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex[:8]}_{Path(file.filename).name}"
        file_path = upload_dir / safe_name

        content = await file.read()
        if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")
        with open(file_path, "wb") as f:
            f.write(content)
        attachment_path = str(file_path.relative_to(Path(settings.UPLOAD_DIR).parent))

    db.execute(update(RiskIssue).where(RiskIssue.id == risk_id).values(
        status="closed", resolution=resolution,
        attachment_path=attachment_path,
        resolved_date=date.today(),
    ))
    log_audit(db, current_user.username, "close", "risk", risk_id, r.title, r.project_id, f"关闭{'风险' if r.type == 'risk' else '问题'}: {r.title}")
    db.commit()
    return risk_to_dict((db.execute(select(RiskIssue).where(RiskIssue.id == risk_id))).scalar_one())


@router.post("/api/risks/extract-from-reports")
async def extract_from_weekly_reports(
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    """AI reads all weekly reports and extracts risk/issue items."""
    from backend_v2.models import WeeklyReport
    from backend_v2.ai_service import extract_risks_from_reports as ai_extract

    # Build text with numeric project IDs for AI to reference
    all_reports = []
    reports = db.execute(select(WeeklyReport)).scalars().all()
    proj_map = {p.id: p.name for p in db.execute(select(Project)).scalars().all()}
    proj_index = {p.name: p.id for p in db.execute(select(Project)).scalars().all()}

    # Also build short-name index for fuzzy matching
    proj_short = {}
    for pname, pid in proj_index.items():
        # Extract key parts: e.g. "五星-新型ebike集成式电机研发项目--CM02" → also match "ebike" or "CM02"
        proj_short[pname] = pid

    SIGNAL_KW = ("未实现","未达到","不满足","不符合","无法","不能","跑不上",
                 "超标","不达标","不理想","延迟","缺货","断裂","烧毁","击穿","失效",
                 "退磁","损坏","停线","漏油","短路","卡死","退化","劣化","退不出",
                 "噪音","振动","温升","发热","损耗","干涉","异常","故障","问题",
                 "风险","隐患","难点","受阻","严重","待解决","跑不到","偏低","偏大")

    for rpt in reports:
        pname = proj_map.get(rpt.project_id, f"项目#{rpt.project_id}")
        content_parts = []
        has_line_data = False

        if rpt.line_items:
            for li in rpt.line_items:
                bk = (li.blocker or "").strip()
                tw = (li.this_week or "").strip()
                if bk and bk not in ("/", "无", "-", "无异常", ".", "。", ""):
                    content_parts.append(f"[阻塞] {bk}")
                    has_line_data = True
                elif tw and any(kw in tw for kw in SIGNAL_KW):
                    content_parts.append(f"[异常] {tw[:200]}")
                    has_line_data = True

        if not has_line_data and rpt.overall_progress:
            import re as _re2
            text_val = rpt.overall_progress.strip()
            # Split on period, bullet, newlines, semicolons
            delim = chr(10) + chr(13) + "。●;；"
            sentences = _re2.split("[" + delim + "]+", text_val)
            for s in sentences:
                s = s.strip()
                if s and any(kw in s for kw in SIGNAL_KW) and len(s) > 5:
                    content_parts.append(f"[总进展] {s[:200]}")

        if content_parts:
            header = f"--- [ID:{rpt.project_id}] {pname} (W{rpt.week_number}) ---"
            all_reports.append(chr(10).join([header] + content_parts))
    if not all_reports:
        return {"extracted": 0, "items": [], "message": "周报中无可分析内容"}

    # Prompt with project mapping table
    project_table = chr(10).join([f"  ID={pid}: {pname}" for pid, pname in proj_map.items()])
    combined = f"项目列表：{chr(10)}{project_table}{chr(10)}{chr(10)}周报内容：{chr(10)}" + chr(10).join(all_reports)

    try:
        risks = await ai_extract(combined, "多项目汇总")
    except Exception as e:
        return {"extracted": 0, "items": [], "message": f"AI分析失败: {str(e)[:200]}"}


    if not isinstance(risks, list):
        return {"extracted": 0, "items": [], "message": f"AI返回非列表: {str(risks)[:300]}"}

    extracted = []
    for risk in risks:
        title = risk.get("title", "").strip()
        if not title:
            continue

        # Match to project: AI returns project_id or project name
        matched_pid = risk.get("project_id")
        if matched_pid and matched_pid in proj_map:
            pass  # AI returned exact project_id
        else:
            ai_pname = risk.get("project_name", "") or risk.get("project", "")
            # Try exact match first
            matched_pid = proj_index.get(ai_pname)
            if not matched_pid:
                # Fuzzy: check if any project name contains the AI-returned name or vice versa
                for pname, pid in proj_index.items():
                    if ai_pname and (ai_pname in pname or pname in ai_pname):
                        matched_pid = pid
                        break
            if not matched_pid:
                # Try matching from report blocks: each block has [ID:N] marker
                desc = risk.get("description", "") or ""
                import re
                id_match = re.search(r'ID:(\d+)', title + desc)
                if id_match:
                    matched_pid = int(id_match.group(1))
            if not matched_pid:
                # Last resort: keyword match — but be strict to avoid misattribution
                import re
                desc = risk.get("description", "") or ""
                found_scores = {}
                for pname, pid in proj_index.items():
                    # Split on common delimiters, filter short/generic words
                    keywords = [kw for kw in re.split(r'[-—\s()+（）、，。]', pname) if len(kw) >= 3 and not kw.isdigit()]
                    score = 0
                    for kw in keywords:
                        if kw in title:
                            score += 3  # title match = strong
                        elif kw in desc:
                            score += 1  # description match = weak
                    if score >= 3:  # require at least one keyword IN title
                        found_scores[pid] = score
                # Only assign if exactly ONE project strongly matches
                if len(found_scores) == 1:
                    matched_pid = list(found_scores.keys())[0]
        if not matched_pid:
            # Don't guess — skip items we can't confidently associate
            continue

        # Dedup: exact match only across ALL projects (global dedup)
        existing = db.execute(
            select(RiskIssue).where(RiskIssue.title == title)
        ).scalars().all()
        skipped = False
        for ex in existing:
            if ex.title == title:
                skipped = True
                break
            # Char overlap >70% in title → near-duplicate
            kw_new = set(title.replace(' ',''))
            kw_old = set(ex.title.replace(' ',''))
            if len(kw_new) > 0 and len(kw_new & kw_old) / len(kw_new) > 0.7:
                skipped = True
                break
        if skipped:
            continue

        r = RiskIssue(
            project_id=matched_pid,
            type="risk" if risk.get("severity") == "高" else "issue",
            title=title,
            description=risk.get("description", ""),
            severity=risk.get("severity", "中"),
            probability=risk.get("probability", ""),
            impact=risk.get("impact", ""),
            source_quote=risk.get("source_quote", ""),
            confidence=risk.get("confidence", 0),
            source_type="ai",
            status="pending_review",  # AI提取的默认待审核
            created_at=datetime.utcnow(),
        )
        db.add(r)
        extracted.append({"title": title, "severity": risk.get("severity", "中"), "project": proj_map.get(matched_pid, "")})
        log_audit(db, current_user.username, "create", "risk", None, title, matched_pid, "AI周报提取")

    db.commit()
    return {"extracted": len(extracted), "items": extracted, "message": f"从{len(reports)}份周报提取了{len(extracted)}条风险/问题"}
