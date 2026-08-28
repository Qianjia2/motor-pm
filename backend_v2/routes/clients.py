"""Client CRUD."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update, delete, func, case
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user, require_admin
from backend_v2.schemas import ClientCreate, ClientUpdate
from backend_v2.models import Client, Project, Opportunity, ClientCommunication, ClientContact, ProjectMember

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("/stats")
def client_stats(db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    clients = db.execute(select(Client).where(Client.is_active == True)).scalars().all()
    total = len(clients)
    by_status: dict = {}
    by_industry: dict = {}
    by_region: dict = {}
    for c in clients:
        st = c.cooperation_status or "潜在"
        by_status[st] = by_status.get(st, 0) + 1
        ind = (c.industry or "未分类").strip() or "未分类"
        by_industry[ind] = by_industry.get(ind, 0) + 1
        reg = (c.address or "未填写").strip() or "未填写"
        by_region[reg] = by_region.get(reg, 0) + 1

    # 每个客户关联的项目数（仅统计未删除项目）
    rows = (db.execute(
        select(Project.client_id, func.count(Project.id))
        .where(Project.client_id.isnot(None), Project.is_active == True)
        .group_by(Project.client_id)
    )).all()
    proj_map = {client_id: total_count for client_id, total_count in rows}
    proj_map = {client_id: (total_count, active_count or 0) for client_id, total_count, active_count in rows}

    # 本月新增：按本地时区的月初换算为 UTC，避免月初 8 小时统计偏差
    utc_offset = datetime.now() - datetime.utcnow()
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0) - utc_offset

    monthly_new = db.execute(
        select(func.count(Client.id)).where(Client.is_active == True, Client.created_at >= month_start)
    ).scalar_one()

    client_projects = [
        {"client_id": c.id, "name": c.name, "abbreviation": c.abbreviation,
         "status": c.cooperation_status or "潜在",
         "project_count": proj_map.get(c.id, 0),
         "active_count": proj_map.get(c.id, 0)}
        for c in clients
    ]
    client_projects.sort(key=lambda x: -x["project_count"])

    return {
        "total": total,
        "monthly_new": monthly_new,
        "by_status": by_status,
        "by_industry": dict(sorted(by_industry.items(), key=lambda x: -x[1])),
        "by_region": dict(sorted(by_region.items(), key=lambda x: -x[1])),
        "client_projects": client_projects,
    }


@router.get("")
def list_clients(
    is_active: bool = Query(True),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    q = select(Client)
    if is_active:
        q = q.where(Client.is_active == True)
    q = q.order_by(Client.name)
    result = db.execute(q)
    return [{"id": c.id, "name": c.name, "abbreviation": c.abbreviation,
             "industry": c.industry, "address": c.address, "cooperation_status": c.cooperation_status or "潜在",
             "phone": c.phone,
             "contact_person": c.contact_person, "contact_phone": c.contact_phone,
             "contact_email": c.contact_email, "notes": c.notes,
             "is_active": c.is_active}
            for c in result.scalars().all()]


@router.get("/{client_id}/profile")
def client_profile(client_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    """客户360视图：客户信息 + 商机 + 关联项目."""
    c = db.execute(select(Client).where(Client.id == client_id)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    from backend_v2.routes.opportunities import opp_to_dict
    opps = db.execute(select(__import__("backend_v2.models", fromlist=["Opportunity"]).Opportunity)
                      .where(__import__("backend_v2.models", fromlist=["Opportunity"]).Opportunity.client_id == client_id)) \
        .scalars().all()
    projs = db.execute(select(Project).where(Project.client_id == client_id, Project.is_active == True)).scalars().all()
    won_opps = [o for o in opps if o.status == "won"]
    # 进度口径与项目列表一致：按里程碑完成率，无里程碑时用字段值
    from backend_v2.models import Milestone
    pids = [p.id for p in projs]
    pct_map = {}
    if pids:
        ms_rows = db.execute(
            select(Milestone.project_id, func.count(Milestone.id),
                   func.sum(case((Milestone.status == "completed", 1), else_=0)))
            .where(Milestone.project_id.in_(pids)).group_by(Milestone.project_id)
        ).all()
        for pid, total_ms, done_ms in ms_rows:
            total_ms = total_ms or 0
            done_ms = done_ms or 0
            pct_map[pid] = round(done_ms / total_ms * 100) if total_ms > 0 else None
    # 沟通记录（最近 50 条）
    comms = db.execute(
        select(ClientCommunication).where(ClientCommunication.client_id == client_id)
        .order_by(ClientCommunication.comm_date.desc(), ClientCommunication.id.desc()).limit(50)
    ).scalars().all()
    # 关系图谱数据：项目-成员（项目经理/角色）、商机负责人
    from backend_v2.routes.client_communications import comm_to_dict
    graph_projects = []
    if pids:
        # member/role 为 lazy="joined"，随行加载，直接读属性
        pm_rows = db.execute(
            select(ProjectMember).where(ProjectMember.project_id.in_(pids))
        ).scalars().all()
        members_by_pid: dict = {}
        for pm in pm_rows:
            members_by_pid.setdefault(pm.project_id, []).append({
                "id": pm.member_id, "name": pm.member.name, "role": pm.role.name or "",
            })
        for p in projs:
            ms = members_by_pid.get(p.id, [])
            graph_projects.append({
                "id": p.id, "name": p.name, "code": p.code,
                "pm": [m["name"] for m in ms if m["role"] == "项目经理"],
                "members": ms,
            })
    graph_opps = [{"id": o.id, "name": o.name, "stage": o.stage or "线索",
                   "status": o.status or "open", "amount": o.amount or 0, "owner": o.owner or ""}
                  for o in opps]
    contacts = db.execute(
        select(ClientContact).where(ClientContact.client_id == client_id)
        .order_by(ClientContact.is_primary.desc(), ClientContact.id.asc())
    ).scalars().all()
    return {
        "client": {
            "id": c.id, "name": c.name, "abbreviation": c.abbreviation,
            "industry": c.industry, "address": c.address,
            "cooperation_status": c.cooperation_status or "潜在",
            "contact_person": c.contact_person, "contact_phone": c.contact_phone,
            "contact_email": c.contact_email, "notes": c.notes,
        },
        "opportunities": [opp_to_dict(o) for o in opps],
        "projects": [{
            "id": p.id, "name": p.name, "code": p.code,
            "overall_status": p.overall_status,
            "completion_pct": pct_map.get(p.id, p.completion_pct) or 0,
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "planned_end_date": p.planned_end_date.isoformat() if p.planned_end_date else None,
        } for p in projs],
        "stats": {
            "opportunity_count": len(opps),
            "won_count": len(won_opps),
            "won_amount": round(sum(o.amount or 0 for o in won_opps), 2),
            "project_count": len(projs),
            "active_project_count": sum(1 for p in projs if p.is_active),
        },
        "communications": [comm_to_dict(c) for c in comms],
        "graph": {"projects": graph_projects, "opportunities": graph_opps},
        "contacts": [{"id": k.id, "name": k.name, "title": k.title or "",
                      "phone": k.phone or "", "email": k.email or "",
                      "is_primary": bool(k.is_primary), "notes": k.notes or ""}
                     for k in contacts],
    }


@router.post("", status_code=201)
def create_client(
    data: ClientCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    existing = (db.execute(select(Client).where(Client.abbreviation == data.abbreviation,
                                                 Client.is_active == True))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"客户缩写 {data.abbreviation} 已存在")
    # 软删除的同缩写客户：直接恢复并更新，避免 DB unique 约束冲突
    deleted = (db.execute(select(Client).where(Client.abbreviation == data.abbreviation,
                                               Client.is_active == False))).scalar_one_or_none()
    if deleted:
        for k, v in data.model_dump().items():
            setattr(deleted, k, v)
        deleted.is_active = True
        db.commit()
        return {"id": deleted.id, "name": deleted.name, "abbreviation": deleted.abbreviation}
    c = Client(**data.model_dump(), created_at=datetime.utcnow())
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "name": c.name, "abbreviation": c.abbreviation}


@router.put("/{client_id}")
def update_client(client_id: int, data: ClientUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = (db.execute(select(Client).where(Client.id == client_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="不存在")
    upd = data.model_dump(exclude_unset=True)
    db.execute(update(Client).where(Client.id == client_id).values(**upd))
    db.commit()
    return {"message": "已更新"}


@router.delete("/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = (db.execute(select(Client).where(Client.id == client_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="不存在")
    db.execute(update(Client).where(Client.id == client_id).values(is_active=False))
    db.commit()
    return {"message": "已删除"}
