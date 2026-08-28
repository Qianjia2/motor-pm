"""商机管理：从线索到量产的全流程商机管理与看板."""
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import Opportunity, Client, Project

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

STAGES = ["线索", "需求确认", "方案报价", "合同签订", "样机试制", "量产"]


def parse_date(v):
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def opp_to_dict(o: Opportunity):
    return {
        "id": o.id, "name": o.name, "client_id": o.client_id,
        "client_name": o.client.name if o.client else "",
        "project_id": o.project_id,
        "project_name": o.project.name if o.project else "",
        "project_code": o.project.code if o.project else "",
        "lead_source": o.lead_source, "amount": o.amount or 0,
        "stage": o.stage, "probability": o.probability or 0,
        "expected_close": o.expected_close.isoformat() if o.expected_close else None,
        "owner": o.owner, "description": o.description,
        "status": o.status, "created_at": o.created_at.isoformat() if o.created_at else None,
    }


@router.get("")
def list_opportunities(db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    result = db.execute(select(Opportunity).order_by(Opportunity.updated_at.desc()))
    return [opp_to_dict(o) for o in result.scalars().all()]


@router.get("/board")
def opportunity_board(db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    """看板聚合：按阶段分列 + 统计."""
    opps = db.execute(select(Opportunity)).scalars().all()
    columns = []
    total_amount = 0.0
    won_count = 0
    won_amount = 0.0
    for st in STAGES:
        items = [opp_to_dict(o) for o in opps if o.stage == st and o.status == "open"]
        amount = sum(i["amount"] for i in items)
        total_amount += amount
        columns.append({"stage": st, "items": items, "count": len(items), "amount": round(amount, 2)})
    won = [opp_to_dict(o) for o in opps if o.status == "won"]
    lost = [opp_to_dict(o) for o in opps if o.status == "lost"]
    won_count = len(won)
    won_amount = round(sum(i["amount"] for i in won), 2)
    return {
        "columns": columns,
        "won": {"items": won, "count": won_count, "amount": won_amount},
        "lost": {"items": lost, "count": len(lost)},
        "total_count": len(opps),
        "open_amount": round(total_amount, 2),
        "conversion_rate": round(won_count / len(opps) * 100, 1) if opps else 0,
    }


@router.post("", status_code=201)
def create_opportunity(data: dict, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="商机名称不能为空")
    client_id = data.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="请选择关联客户")
    client = db.execute(select(Client).where(Client.id == client_id)).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=400, detail="关联客户不存在")
    project_id = data.get("project_id")
    if project_id:
        proj = db.execute(select(Project).where(Project.id == project_id, Project.is_active == True)).scalar_one_or_none()
        if not proj:
            raise HTTPException(status_code=400, detail="关联项目不存在或已删除")
        if proj.client_id != client_id:
            raise HTTPException(status_code=400, detail="关联项目必须属于所选客户")
    stage = data.get("stage") or "线索"
    if stage not in STAGES + ["won", "lost"]:
        raise HTTPException(status_code=400, detail=f"无效阶段: {stage}")
    status = data.get("status") or "open"
    if stage == "won":
        status = "won"
    elif stage == "lost":
        status = "lost"
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="金额必须是数字")
    try:
        probability = int(data.get("probability") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="成交概率必须是整数")
    o = Opportunity(
        name=data["name"].strip(),
        client_id=client_id,
        project_id=project_id,
        lead_source=data.get("lead_source") or "",
        amount=amount,
        stage=stage,
        probability=probability,
        expected_close=parse_date(data.get("expected_close")),
        owner=data.get("owner") or "",
        description=data.get("description") or "",
        status=status,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return opp_to_dict(o)


@router.put("/{opp_id}")
def update_opportunity(opp_id: int, data: dict, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    o = db.execute(select(Opportunity).where(Opportunity.id == opp_id)).scalar_one_or_none()
    if not o:
        raise HTTPException(status_code=404, detail="商机不存在")
    if "stage" in data and data["stage"] and data["stage"] not in STAGES + ["won", "lost"]:
        raise HTTPException(status_code=400, detail=f"无效阶段: {data['stage']}")
    allowed = ["name", "client_id", "lead_source", "amount", "stage", "probability",
               "expected_close", "owner", "description", "status"]
    for k in allowed:
        if k not in data:
            continue
        if k == "expected_close":
            setattr(o, k, parse_date(data[k]))
        elif k == "amount":
            try:
                setattr(o, k, float(data[k]))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="金额必须是数字")
        elif k == "probability":
            try:
                setattr(o, k, int(data[k]))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="成交概率必须是整数")
        else:
            setattr(o, k, data[k])
    # stage 与 status 联动，避免看板中商机"消失"
    if o.stage == "won":
        o.status = "won"
    elif o.stage == "lost":
        o.status = "lost"
    elif o.stage in STAGES and o.status in ("won", "lost"):
        o.status = "open"
    if "project_id" in data:
        pid = data["project_id"]
        if pid:
            proj = db.execute(select(Project).where(Project.id == pid, Project.is_active == True)).scalar_one_or_none()
            if not proj:
                raise HTTPException(status_code=400, detail="关联项目不存在或已删除")
            if proj.client_id != o.client_id:
                raise HTTPException(status_code=400, detail="关联项目必须属于所选客户")
        o.project_id = pid
    o.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(o)
    return opp_to_dict(o)


@router.delete("/{opp_id}")
def delete_opportunity(opp_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    o = db.execute(select(Opportunity).where(Opportunity.id == opp_id)).scalar_one_or_none()
    if not o:
        raise HTTPException(status_code=404, detail="商机不存在")
    db.delete(o)
    db.commit()
    return {"message": "已删除"}
