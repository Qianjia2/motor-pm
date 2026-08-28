"""External API: API Key management, webhooks, public endpoints."""
import hashlib, secrets, hmac, json as jsonlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import Session, selectinload
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import ApiKey, WebhookConfig, Project, Milestone, RiskIssue

router = APIRouter(tags=["external"])

# ═══════════════════════════════════════════
# API Key Auth dependency
# ═══════════════════════════════════════════

def verify_api_key(x_api_key: str = Header(None), db: Session = Depends(get_db)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    result = db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    if key.expires_at and key.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="API Key expired")
    # Update last_used_at
    db.execute(update(ApiKey).where(ApiKey.id == key.id).values(last_used_at=datetime.utcnow()))
    db.commit()
    return key


# ═══════════════════════════════════════════
# API Key Management (admin only)
# ═══════════════════════════════════════════

@router.get("/api/admin/api-keys")
def list_api_keys(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    return [{"id": k.id, "name": k.name, "key_prefix": k.key_prefix, "permissions": k.permissions,
             "is_active": k.is_active, "created_by": k.created_by, "created_at": k.created_at.isoformat() if k.created_at else None,
             "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
             "expires_at": k.expires_at.isoformat() if k.expires_at else None}
            for k in result.scalars().all()]


@router.post("/api/admin/api-keys", status_code=201)
def create_api_key(
    data: dict, db: Session = Depends(get_db), user=Depends(get_current_user),
):
    """Generate a new API key. Returns the full key ONCE — save it immediately."""
    raw_key = "pm_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:16]

    k = ApiKey(
        name=data.get("name", "Unnamed"),
        key_hash=key_hash,
        key_prefix=key_prefix,
        permissions=data.get("permissions", "read"),
        created_by=user.username,
        expires_at=datetime.utcnow() + timedelta(days=int(data.get("expire_days", 365))) if data.get("expire_days") else None,
    )
    db.add(k)
    db.commit()
    db.refresh(k)
    return {"id": k.id, "name": k.name, "api_key": raw_key, "key_prefix": key_prefix,
            "message": "此密钥仅显示一次，请立即保存"}


@router.put("/api/admin/api-keys/{key_id}")
def update_api_key(key_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    db.execute(update(ApiKey).where(ApiKey.id == key_id).values(
        name=data.get("name"), is_active=data.get("is_active"), permissions=data.get("permissions"),
    ))
    db.commit()
    return {"message": "已更新"}


@router.delete("/api/admin/api-keys/{key_id}")
def revoke_api_key(key_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    db.execute(update(ApiKey).where(ApiKey.id == key_id).values(is_active=False))
    db.commit()
    return {"message": "已吊销"}


# ═══════════════════════════════════════════
# Webhook Management
# ═══════════════════════════════════════════

@router.get("/api/admin/webhooks")
def list_webhooks(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = db.execute(select(WebhookConfig).order_by(WebhookConfig.created_at.desc()))
    return [{"id": w.id, "name": w.name, "url": w.url, "events": w.events, "is_active": w.is_active,
             "created_at": w.created_at.isoformat() if w.created_at else None,
             "last_triggered_at": w.last_triggered_at.isoformat() if w.last_triggered_at else None,
             "failure_count": w.failure_count}
            for w in result.scalars().all()]


@router.post("/api/admin/webhooks", status_code=201)
def create_webhook(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    w = WebhookConfig(
        name=data.get("name", "Webhook"),
        url=data["url"],
        secret=data.get("secret", secrets.token_hex(16)),
        events=data.get("events", "project.status_change,milestone.completed,risk.created"),
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return {"id": w.id, "name": w.name, "secret": w.secret, "message": "Webhook 已创建"}


@router.put("/api/admin/webhooks/{webhook_id}")
def update_webhook(webhook_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    upd = {k: v for k, v in data.items() if k in ("name", "url", "secret", "events", "is_active")}
    if upd:
        db.execute(update(WebhookConfig).where(WebhookConfig.id == webhook_id).values(**upd))
        db.commit()
    return {"message": "已更新"}


@router.delete("/api/admin/webhooks/{webhook_id}")
def delete_webhook(webhook_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    db.execute(delete(WebhookConfig).where(WebhookConfig.id == webhook_id))
    db.commit()
    return {"message": "已删除"}


@router.post("/api/admin/webhooks/{webhook_id}/test")
def test_webhook(webhook_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Send a test ping to the webhook URL."""
    import aiohttp
    result = db.execute(select(WebhookConfig).where(WebhookConfig.id == webhook_id))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Webhook不存在")
    payload = {"event": "test.ping", "timestamp": datetime.utcnow().isoformat(), "data": {"message": "测试消息"}}
    try:
        headers = {"Content-Type": "application/json"}
        if w.secret:
            sig = hmac.new(w.secret.encode(), jsonlib.dumps(payload).encode(), hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = sig
        with aiohttp.ClientSession() as session:
            with session.post(w.url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                db.execute(update(WebhookConfig).where(WebhookConfig.id == webhook_id).values(
                    last_triggered_at=datetime.utcnow(), failure_count=0))
                db.commit()
                return {"status": resp.status, "message": f"测试成功，响应 {resp.status}"}
    except Exception as e:
        db.execute(update(WebhookConfig).where(WebhookConfig.id == webhook_id).values(failure_count=w.failure_count + 1))
        db.commit()
        raise HTTPException(status_code=502, detail=f"测试失败: {str(e)}")


# ═══════════════════════════════════════════
# External Public API (API Key auth)
# ═══════════════════════════════════════════

@router.get("/api/external/projects")
def ext_list_projects(
    status: str = Query(None), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), api_key=Depends(verify_api_key),
):
    """[List] Get active projects. Use X-API-Key header for auth."""
    q = select(Project).options(selectinload(Project.current_phase), selectinload(Project.client)).where(Project.is_active == True)
    if status:
        q = q.where(Project.overall_status == status)
    q = q.order_by(Project.code).offset((page - 1) * page_size).limit(page_size)
    result = db.execute(q)
    projects_list = result.scalars().all()
    return {
        "data": [{"id": p.id, "name": p.name, "code": p.code, "phase": p.current_phase.name if p.current_phase else None,
                  "status": p.overall_status, "completion_pct": p.completion_pct,
                  "start_date": p.start_date.isoformat() if p.start_date else None,
                  "planned_end_date": p.planned_end_date.isoformat() if p.planned_end_date else None,
                  "contract_amount": p.contract_amount, "client": p.client.name if p.client else None}
                 for p in projects_list],
        "page": page, "page_size": page_size,
    }


@router.get("/api/external/projects/{project_id}")
def ext_get_project(project_id: int, db: Session = Depends(get_db), api_key=Depends(verify_api_key)):
    """[Detail] Get single project with milestones and risks."""
    result = db.execute(
        select(Project).where(Project.id == project_id, Project.is_active == True)
        .options(selectinload(Project.client), selectinload(Project.current_phase),
                 selectinload(Project.milestones), selectinload(Project.risks))
    )
    p = result.scalars().one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "id": p.id, "name": p.name, "code": p.code, "description": p.description,
        "phase": p.current_phase.name if p.current_phase else None,
        "status": p.overall_status, "completion_pct": p.completion_pct,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "planned_end_date": p.planned_end_date.isoformat() if p.planned_end_date else None,
        "actual_end_date": p.actual_end_date.isoformat() if p.actual_end_date else None,
        "contract_amount": p.contract_amount, "received_amount": p.received_amount,
        "budget": p.budget, "actual_cost": p.actual_cost,
        "client": {"name": p.client.name, "abbreviation": p.client.abbreviation} if p.client else None,
        "milestones": [{"id": m.id, "name": m.name, "planned_date": m.planned_date.isoformat() if m.planned_date else None,
                         "status": m.status, "is_key": m.is_key} for m in (p.milestones or [])[:50]],
        "risks": [{"id": r.id, "title": r.title, "severity": r.severity, "status": r.status}
                  for r in (p.risks or []) if r.status in ("open", "in_progress")][:20],
    }


@router.get("/api/external/milestones")
def ext_milestones(
    project_code: str = Query(None), days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db), api_key=Depends(verify_api_key),
):
    """[List] Upcoming milestones within N days. Filter by project_code optionally."""
    from datetime import date
    today = date.today()
    end = today + timedelta(days=days)
    q = select(Milestone).options(selectinload(Milestone.project)).join(Project).where(
        Project.is_active == True,
        Milestone.planned_date >= today,
        Milestone.planned_date <= end,
    )
    if project_code:
        q = q.where(Project.code == project_code)
    q = q.order_by(Milestone.planned_date).limit(100)
    result = db.execute(q)
    return {"data": [{"id": m.id, "name": m.name, "project_name": m.project.name, "project_code": m.project.code,
                      "planned_date": m.planned_date.isoformat() if m.planned_date else None,
                      "status": m.status, "is_key": m.is_key}
                     for m in result.scalars().all()]}


@router.get("/api/external/risks")
def ext_risks(
    project_code: str = Query(None), severity: str = Query(None),
    db: Session = Depends(get_db), api_key=Depends(verify_api_key),
):
    """[List] Open risks, filterable by project_code and severity."""
    q = select(RiskIssue).options(selectinload(RiskIssue.project)).join(Project).where(
        Project.is_active == True,
        RiskIssue.status.in_(["open", "in_progress"]),
    )
    if project_code:
        q = q.where(Project.code == project_code)
    if severity:
        q = q.where(RiskIssue.severity == severity)
    q = q.order_by(RiskIssue.severity.desc()).limit(100)
    result = db.execute(q)
    return {"data": [{"id": r.id, "title": r.title, "project_name": r.project.name, "project_code": r.project.code,
                      "severity": r.severity, "probability": r.probability, "impact": r.impact,
                      "status": r.status, "mitigation_plan": r.mitigation_plan}
                     for r in result.scalars().all()]}


@router.get("/api/external/health")
def ext_health(db: Session = Depends(get_db), api_key=Depends(verify_api_key)):
    """[Health] Quick status summary of all active projects."""
    result = db.execute(select(Project).where(Project.is_active == True))
    projects = result.scalars().all()
    total = len(projects)
    return {
        "total_projects": total,
        "status_breakdown": {
            "normal": sum(1 for p in projects if p.overall_status == "normal"),
            "at_risk": sum(1 for p in projects if p.overall_status == "at_risk"),
            "blocked": sum(1 for p in projects if p.overall_status == "blocked"),
        },
        "avg_completion_pct": round(sum(p.completion_pct or 0 for p in projects) / max(total, 1), 1),
        "total_contract_amount": sum(p.contract_amount or 0 for p in projects),
        "timestamp": datetime.utcnow().isoformat(),
    }
