"""Financial management: transactions, budget tracking, revenue."""
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import Project, Transaction as Trans

router = APIRouter(tags=["financials"])


@router.get("/api/financials/overview")
def financial_overview(db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    """Portfolio-level financial summary."""
    result = db.execute(
        select(Project).where(Project.is_active == True)
    )
    projects = result.scalars().all()
    total_contract = sum(p.contract_amount or 0 for p in projects)
    total_received = sum(p.received_amount or 0 for p in projects)
    total_budget = sum(p.budget or 0 for p in projects)
    total_cost = sum(p.actual_cost or 0 for p in projects)
    return {
        "total_contract": round(total_contract, 1),
        "total_received": round(total_received, 1),
        "receivable": round(total_contract - total_received, 1),
        "receive_rate": round(total_received / total_contract * 100, 1) if total_contract > 0 else 0,
        "total_budget": round(total_budget, 1),
        "total_cost": round(total_cost, 1),
        "budget_remaining": round(total_budget - total_cost, 1),
        "cost_rate": round(total_cost / total_budget * 100, 1) if total_budget > 0 else 0,
        "profit": round(total_received - total_cost, 1),
        "margin": round((total_received - total_cost) / total_received * 100, 1) if total_received > 0 else 0,
        "project_count": len(projects),
    }


@router.get("/api/financials/projects")
def project_financials(db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    """Per-project financial data sorted by contract amount."""
    result = db.execute(
        select(Project).where(Project.is_active == True).order_by(Project.contract_amount.desc())
    )
    return [{
        "id": p.id, "name": p.name, "code": p.code,
        "contract_amount": p.contract_amount or 0,
        "received_amount": p.received_amount or 0,
        "receivable": round((p.contract_amount or 0) - (p.received_amount or 0), 1),
        "budget": p.budget or 0,
        "actual_cost": p.actual_cost or 0,
        "budget_remaining": round((p.budget or 0) - (p.actual_cost or 0), 1),
        "profit": round((p.received_amount or 0) - (p.actual_cost or 0), 1),
    } for p in result.scalars().all()]


@router.get("/api/projects/{project_id}/transactions")
def project_transactions(project_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    result = db.execute(
        select(Trans).where(Trans.project_id == project_id).order_by(Trans.trans_date.desc())
    )
    return [{
        "id": t.id, "type": t.type, "category": t.category,
        "amount": t.amount, "description": t.description,
        "trans_date": t.trans_date.isoformat() if t.trans_date else None,
        "recorded_by": t.recorded_by,
    } for t in result.scalars().all()]


@router.post("/api/projects/{project_id}/transactions", status_code=201)
def create_transaction(
    project_id: int, data: dict,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    data = dict(data)
    # SQLite Date 列只接受 date 对象:字符串需显式解析
    td = data.pop("trans_date", None)
    if isinstance(td, str):
        td = datetime.fromisoformat(td).date()
    t = Trans(project_id=project_id, trans_date=td or date.today(), **data)
    db.add(t)
    db.commit()
    db.refresh(t)

    # Update project financials
    totals = (db.execute(
        select(
            func.coalesce(func.sum(Trans.amount).filter(Trans.type == 'income', Trans.category == '合同回款'), 0),
            func.coalesce(func.sum(Trans.amount).filter(Trans.type == 'income'), 0),
            func.coalesce(func.sum(Trans.amount).filter(Trans.type == 'expense'), 0),
        ).where(Trans.project_id == project_id)
    )).one()
    from sqlalchemy import update as up
    vals = {"received_amount": totals[1], "actual_cost": totals[2]}
    proj = db.get(Project, project_id)
    # 合同总额手工填写过则保留,否则按「合同回款」记录累计
    if not (proj and proj.contract_amount_manual):
        vals["contract_amount"] = totals[0]
    db.execute(up(Project).where(Project.id == project_id).values(**vals))
    db.commit()
    return {"id": t.id}


@router.delete("/api/transactions/{trans_id}")
def delete_transaction(
    trans_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    result = db.execute(select(Trans).where(Trans.id == trans_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="不存在")
    pid = t.project_id
    db.delete(t)
    db.commit()

    # Recalculate project financials
    totals = (db.execute(
        select(
            func.coalesce(func.sum(Trans.amount).filter(Trans.type == 'income', Trans.category == '合同回款'), 0),
            func.coalesce(func.sum(Trans.amount).filter(Trans.type == 'income'), 0),
            func.coalesce(func.sum(Trans.amount).filter(Trans.type == 'expense'), 0),
        ).where(Trans.project_id == pid)
    )).one()
    from sqlalchemy import update as up
    vals = {"received_amount": totals[1], "actual_cost": totals[2]}
    proj = db.get(Project, pid)
    if not (proj and proj.contract_amount_manual):
        vals["contract_amount"] = totals[0]
    db.execute(up(Project).where(Project.id == pid).values(**vals))
    db.commit()
    return {"message": "已删除"}


@router.get("/api/report-center/{report_type}")
def generate_report(
    report_type: str,
    project_id: int = Query(None),
    year: int = Query(None),
    month: int = Query(None),
    db: Session = Depends(get_db), _current_user=Depends(get_current_user),
):
    """Report center: summary / weekly / risk / financial."""
    today = date.today()
    yr = year or today.year
    mo = month or today.month

    if report_type == "summary":
        result = db.execute(
            select(Project).options(selectinload(Project.current_phase))
            .where(Project.is_active == True).order_by(Project.code)
        )
        projects = []
        for p in result.scalars().all():
            projects.append({
                "name": p.name, "code": p.code, "phase": p.current_phase.name if p.current_phase else "-",
                "status": p.overall_status, "completion_pct": p.completion_pct or 0,
                "contract_amount": p.contract_amount or 0, "received_amount": p.received_amount or 0,
                "budget": p.budget or 0, "actual_cost": p.actual_cost or 0,
                "planned_end_date": p.planned_end_date.isoformat() if p.planned_end_date else None,
            })
        return {"title": f"项目汇总报告 ({today.isoformat()})", "projects": projects, "generated_at": today.isoformat()}

    elif report_type == "risk":
        from backend_v2.models import RiskIssue
        result = db.execute(
            select(RiskIssue).options(selectinload(RiskIssue.project))
            .join(Project).where(Project.is_active == True, RiskIssue.status.in_(["open", "in_progress"]))
            .order_by(RiskIssue.severity.desc()).limit(50)
        )
        risks = []
        for r in result.scalars().all():
            risks.append({
                "title": r.title, "project_name": r.project.name if r.project else None,
                "severity": r.severity, "probability": r.probability, "impact": r.impact,
                "status": r.status, "mitigation": r.mitigation_plan,
            })
        return {"title": f"风险登记报告 ({today.isoformat()})", "risks": risks, "count": len(risks), "generated_at": today.isoformat()}

    elif report_type == "financial":
        return financial_overview(db, _current_user)

    else:
        raise HTTPException(status_code=400, detail=f"未知报告类型: {report_type}")
