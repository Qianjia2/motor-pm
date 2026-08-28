"""管理层问题风险管理 — 自动汇总所有项目风险/问题 (SQLite)."""
import json, os, uuid
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select, func, case
from sqlalchemy.orm import Session
from backend_v2.database import get_db, SessionLocal
from backend_v2.storage import safe_load, safe_save
from backend_v2.auth import get_current_user
from backend_v2.models import RiskIssue, Project

router = APIRouter(tags=["issue_risks"])

# JSON fallback for standalone issues not tied to a specific project
DATA_FILE_STR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "issue_risks_standalone.json")
os.makedirs(os.path.dirname(DATA_FILE_STR), exist_ok=True)
DATA_FILE = Path(DATA_FILE_STR)  # Keep for compatibility if needed elsewhere

def _load_issues():
    return safe_load(DATA_FILE_STR, [])

def _save_issues(data):
    safe_save(DATA_FILE_STR, data)
if not DATA_FILE.exists():
    _save_issues([])

SEVERITY_ORDER = {"高": 3, "中": 2, "低": 1}

# ── Pydantic schemas ──

class IssueRiskCreate(BaseModel):
    title: str
    description: str = ""
    severity: str = "中"
    probability: str = "中"
    impact: str = "中"
    project_id: Optional[int] = None
    project_name: str = ""
    owner: str = ""
    status: str = "open"


class IssueRiskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    probability: Optional[str] = None
    impact: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = None


# ── Helpers ──

def _db_risk_to_dict(r) -> dict:
    """Convert SQLAlchemy RiskIssue row to dict."""
    return {
        "id": str(r.id),  # use string id for consistency
        "source": r.source_type or "project",
        "title": r.title or "",
        "type": r.type or "issue",
        "description": r.description or "",
        "severity": r.severity or "中",
        "status": r.status or "open",
        "project_id": r.project_id,
        "project_name": r.project.name if r.project else "",
        "project_code": r.project.code if r.project else "",
        "owner": r.owner.name if r.owner else "",
        "probability": r.probability or "",
        "impact": r.impact or "",
        "risk_level": r.risk_level or "",
        "mitigation_plan": r.mitigation_plan or "",
        "source_quote": r.source_quote or "",
        "confidence": r.confidence or 0,
        "source_type": r.source_type or "manual",
        "identified_date": r.identified_date.isoformat() if r.identified_date else None,
        "target_resolve_date": r.target_resolve_date.isoformat() if r.target_resolve_date else None,
        "resolved_date": r.resolved_date.isoformat() if r.resolved_date else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _merge_all_risks(db: Session):
    """Collect all risks from SQLite + standalone JSON."""
    results = []

    # 1. From SQLite — all project-level risk_issue rows
    try:
        q = select(RiskIssue).order_by(RiskIssue.created_at.desc())
        rows = db.execute(q).scalars().all()
        for r in rows:
            results.append(_db_risk_to_dict(r))
    except Exception:
        pass

    # 2. From JSON — standalone issues (no project)
    try:
        standalone = _load_issues()
        for s in standalone:
            s["source"] = "standalone"
            results.append(s)
    except Exception:
        pass

    # Sort: by created_at descending
    results.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return results


# ── Endpoints ──

@router.get("/api/issue-risks/summary")
def get_summary(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Return aggregate statistics for the dashboard."""
    try:
        total = db.execute(select(func.count(RiskIssue.id))).scalar() or 0
        # By severity
        sev_rows = db.execute(
            select(RiskIssue.severity, func.count(RiskIssue.id))
            .group_by(RiskIssue.severity)
        ).all()
        severity_breakdown = {s or "未知": c for s, c in sev_rows}

        # By status
        status_rows = db.execute(
            select(RiskIssue.status, func.count(RiskIssue.id))
            .group_by(RiskIssue.status)
        ).all()
        status_breakdown = {s or "open": c for s, c in status_rows}

        high = sum(c for s, c in sev_rows if s == "高")
        open_count = sum(c for s, c in status_rows if s == "open")

        # By project (top 5)
        proj_rows = db.execute(
            select(Project.name, func.count(RiskIssue.id))
            .join(RiskIssue, RiskIssue.project_id == Project.id)
            .group_by(Project.name)
            .order_by(func.count(RiskIssue.id).desc())
            .limit(5)
        ).all()

        return {
            "total": total,
            "high": high,
            "open": open_count,
            "severity_breakdown": severity_breakdown,
            "status_breakdown": status_breakdown,
            "top_projects": [{"name": n, "count": c} for n, c in proj_rows],
        }
    except Exception as e:
        return {"total": 0, "high": 0, "open": 0, "error": str(e)}


@router.get("/api/issue-risks/matrix")
def get_risk_matrix(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Return all issues with probability/impact for the 5x5 risk matrix."""
    try:
        q = select(RiskIssue)
        rows = db.execute(q).scalars().all()
        items = []
        for r in rows:
            prob = r.probability or "中"
            imp = r.impact or "中"
            items.append({
                "id": str(r.id),
                "title": r.title or "",
                "severity": r.severity or "中",
                "probability": prob,
                "impact": imp,
                "status": r.status or "open",
                "project_name": r.project.name if r.project else "",
                "owner": r.owner.name if r.owner else "",
            })
        return items
    except Exception:
        return []


@router.get("/api/issue-risks")
def list_issue_risks(
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    project_id: Optional[int] = Query(None),
    type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: Optional[str] = Query("severity_desc"),  # severity_desc / created_desc / project
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """List all risks/issues across all projects, with filters and sorting."""
    try:
        q = select(RiskIssue)

        if severity:
            q = q.where(RiskIssue.severity == severity)
        if status:
            q = q.where(RiskIssue.status == status)
        if project_id:
            q = q.where(RiskIssue.project_id == project_id)
        if type:
            q = q.where(RiskIssue.type == type)

        rows = db.execute(q).scalars().all()
        results = [_db_risk_to_dict(r) for r in rows]

        # Text search filter (client-side since SQLite doesn't support great full-text)
        if search:
            s = search.lower()
            results = [r for r in results if s in r.get("title", "").lower() or s in r.get("description", "").lower()]

        # Sort
        if sort == "severity_desc":
            results.sort(key=lambda x: SEVERITY_ORDER.get(x.get("severity"), 0), reverse=True)
        elif sort == "created_desc":
            results.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        elif sort == "project":
            results.sort(key=lambda x: x.get("project_name", ""))

        return results
    except Exception as e:
        return []


@router.get("/api/issue-risks-projects")
def list_projects_for_dropdown():
    """Return active projects for the association dropdown."""
    try:
        from backend_v2.database import SessionLocal
        from backend_v2.models import Project
        db = SessionLocal()
        projects = db.query(Project).filter(Project.is_active == True).order_by(Project.name).all()
        return [{"id": p.id, "name": p.name, "code": p.code} for p in projects]
    except Exception:
        return []


@router.post("/api/issue-risks", status_code=201)
def create_issue_risk(
    data: IssueRiskCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new issue. If project_id is provided, write to SQLite. Otherwise JSON."""
    if data.project_id:
        # Write to SQLite as a project-level issue
        from backend_v2.audit import log_audit
        r = RiskIssue(
            project_id=data.project_id,
            type="issue",
            title=data.title,
            description=data.description,
            severity=data.severity,
            probability=data.probability,
            impact=data.impact,
            status=data.status or "open",
            created_at=datetime.utcnow(),
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        log_audit(db, current_user.username, "create", "risk", r.id, r.title, data.project_id, f"管理层创建问题: {r.title}")
        db.commit()
        return _db_risk_to_dict(r)
    else:
        # Store in JSON as standalone issue
        items = _load_issues()
        item = data.model_dump()
        item["id"] = uuid.uuid4().hex[:10]
        item["source"] = "standalone"
        item["created_at"] = datetime.utcnow().isoformat()
        items.append(item)
        _save_issues(items)
        return item


@router.put("/api/issue-risks/{item_id}")
def update_issue_risk(
    item_id: str,
    data: IssueRiskUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update an issue. Checks SQLite first, then JSON."""
    try:
        rid = int(item_id)
        r = db.execute(select(RiskIssue).where(RiskIssue.id == rid)).scalar_one_or_none()
        if r:
            from backend_v2.audit import log_audit
            valid_cols = {c.name for c in r.__table__.columns}
            upd = data.model_dump(exclude_unset=True)
            for k, v in upd.items():
                if k in valid_cols:
                    setattr(r, k, v)
            db.commit()
            log_audit(db, current_user.username, "update", "risk", rid, r.title, r.project_id, "管理层更新问题")
            db.commit()
            return _db_risk_to_dict(db.execute(select(RiskIssue).where(RiskIssue.id == rid)).scalar_one())
    except ValueError:
        pass

    # Check JSON standalone
    items = _load_issues()
    for i in items:
        if i["id"] == item_id:
            upd = data.model_dump(exclude_unset=True)
            i.update(upd)
            i["updated_at"] = datetime.utcnow().isoformat()
            _save_issues(items)
            return i
    raise HTTPException(status_code=404, detail="不存在")


@router.delete("/api/issue-risks/{item_id}")
def delete_issue_risk(
    item_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete an issue from SQLite or JSON."""
    try:
        rid = int(item_id)
        r = db.execute(select(RiskIssue).where(RiskIssue.id == rid)).scalar_one_or_none()
        if r:
            from backend_v2.audit import log_audit
            db.delete(r)
            log_audit(db, current_user.username, "delete", "risk", rid, r.title, r.project_id, "管理层删除问题")
            db.commit()
            return {"message": "已删除"}
    except ValueError:
        pass

    # Check JSON standalone
    items = _load_issues()
    filtered = [i for i in items if i["id"] != item_id]
    if len(filtered) == len(items):
        raise HTTPException(status_code=404, detail="不存在")
    _save_issues(filtered)
    return {"message": "已删除"}


@router.post("/api/issue-risks/extract")
async def extract_risks_from_reports(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """AI extracts risks/issues from weekly reports and auto-creates them."""
    from backend_v2.models import WeeklyReport
    from backend_v2.ai_service import extract_risks_from_reports as ai_extract
    from backend_v2.audit import log_audit

    # Collect weekly report text
    q = select(WeeklyReport)
    if project_id:
        q = q.where(WeeklyReport.project_id == project_id)
    reports = db.execute(q).scalars().all()

    if not reports:
        return {"extracted": 0, "items": [], "message": "没有找到周报"}

    # Batch all report texts into one prompt (avoids N slow sequential AI calls)
    all_reports = []
    for rpt in reports:
        pname = rpt.project.name if rpt.project else f"项目#{rpt.project_id}"
        parts = []
        if rpt.overall_progress:
            parts.append(f"进展: {rpt.overall_progress}")
        if rpt.key_accomplishments:
            parts.append(f"成果: {rpt.key_accomplishments}")
        if rpt.line_items:
            blockers = []
            for li in rpt.line_items:
                if li.blocker:
                    blockers.append(f"  [{li.line.name if li.line else '未知'}] {li.blocker}")
            if blockers:
                parts.append("阻塞项:\n" + "\n".join(blockers))
        if parts:
            all_reports.append(f"--- {pname} ({rpt.year}W{rpt.week_number}) ---\n" + "\n".join(parts))

    if not all_reports:
        return {"extracted": 0, "items": [], "message": "周报中无可分析内容"}

    combined_text = "\n\n".join(all_reports)
    try:
        risks = await ai_extract(combined_text, "多项目汇总")
    except Exception as e:
        return {"extracted": 0, "items": [], "message": f"AI分析失败: {str(e)[:200]}"}

    extracted_all = []
    proj_cache = {p.id: p.name for p in db.execute(select(Project)).scalars().all()}

    for risk in risks:
        if not risk.get("title"):
            continue
        title = risk["title"]
        # Determine which project the risk belongs to by matching project name in the risk text
        matched_pid = project_id
        if not matched_pid:
            desc = risk.get("description", "") + title
            for pid, pname in proj_cache.items():
                if pname in desc:
                    matched_pid = pid
                    break

        if not matched_pid:
            # Default to first available project
            matched_pid = reports[0].project_id if reports else None

        if not matched_pid:
            continue

        # Check for duplicate
        existing = db.execute(
            select(RiskIssue).where(
                RiskIssue.project_id == matched_pid,
                RiskIssue.title == title
            )
        ).scalar_one_or_none()
        if existing:
            continue

        pname = proj_cache.get(matched_pid, "")
        r = RiskIssue(
            project_id=matched_pid,
            type="risk" if risk.get("severity") == "高" else "issue",
            title=title,
            description=risk.get("description", ""),
            severity=risk.get("severity", "中"),
            probability=risk.get("probability", ""),
            impact=risk.get("impact", ""),
            status="open",
            created_at=datetime.utcnow(),
        )
        db.add(r)
        extracted_all.append({"title": title, "severity": risk.get("severity", "中"), "project": pname})
        log_audit(db, current_user.username, "create", "risk", None, title, matched_pid, "AI从周报提取")

    db.commit()
    return {
        "extracted": len(extracted_all),
        "items": extracted_all,
        "message": f"从 {len(reports)} 份周报中提取了 {len(extracted_all)} 条风险/问题",
    }
