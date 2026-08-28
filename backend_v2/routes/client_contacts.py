"""客户联系人 CRUD."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import Client, ClientContact

router = APIRouter(prefix="/api", tags=["client-contacts"])


def contact_to_dict(c: ClientContact):
    return {
        "id": c.id, "client_id": c.client_id,
        "name": c.name or "", "title": c.title or "",
        "phone": c.phone or "", "email": c.email or "",
        "is_primary": bool(c.is_primary), "notes": c.notes or "",
    }


def _get_client_or_404(db: Session, client_id: int) -> Client:
    c = db.execute(select(Client).where(Client.id == client_id, Client.is_active == True)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    return c


def _sync_client_fields(db: Session, client: Client):
    """把主要联系人（无则第一个）同步到客户记录字段，保持列表页展示一致."""
    first = db.execute(
        select(ClientContact).where(ClientContact.client_id == client.id)
        .order_by(ClientContact.is_primary.desc(), ClientContact.id.asc())
    ).scalars().first()
    if first:
        client.contact_person = first.name
        client.contact_phone = first.phone
        client.contact_email = first.email
    else:
        client.contact_person = ""
        client.contact_phone = ""
        client.contact_email = ""


@router.get("/clients/{client_id}/contacts")
def list_contacts(client_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    _get_client_or_404(db, client_id)
    rows = db.execute(
        select(ClientContact).where(ClientContact.client_id == client_id)
        .order_by(ClientContact.is_primary.desc(), ClientContact.id.asc())
    ).scalars().all()
    return [contact_to_dict(c) for c in rows]


@router.post("/clients/{client_id}/contacts", status_code=201)
def create_contact(client_id: int, data: dict, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    client = _get_client_or_404(db, client_id)
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="联系人姓名不能为空")
    total = db.execute(select(ClientContact.id).where(ClientContact.client_id == client_id)).scalars().all()
    is_primary = bool(data.get("is_primary")) or len(total) == 0  # 首个联系人自动设为主要
    if is_primary:
        db.execute(ClientContact.__table__.update().where(
            ClientContact.client_id == client_id).values(is_primary=False))
    c = ClientContact(
        client_id=client_id, name=name,
        title=(data.get("title") or "").strip(),
        phone=(data.get("phone") or "").strip(),
        email=(data.get("email") or "").strip(),
        is_primary=is_primary,
        notes=(data.get("notes") or "").strip(),
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(c)
    db.flush()
    _sync_client_fields(db, client)
    db.commit()
    db.refresh(c)
    return contact_to_dict(c)


@router.put("/contacts/{contact_id}")
def update_contact(contact_id: int, data: dict, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    c = db.execute(select(ClientContact).where(ClientContact.id == contact_id)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="联系人不存在")
    name = data.get("name")
    if name is not None and not str(name).strip():
        raise HTTPException(status_code=400, detail="联系人姓名不能为空")
    for k in ("name", "title", "phone", "email", "notes"):
        if k in data:
            setattr(c, k, str(data[k] or "").strip())
    if "is_primary" in data and bool(data["is_primary"]) and not c.is_primary:
        db.execute(ClientContact.__table__.update().where(
            ClientContact.client_id == c.client_id).values(is_primary=False))
        c.is_primary = True
    c.updated_at = datetime.utcnow()
    client = db.execute(select(Client).where(Client.id == c.client_id)).scalar_one_or_none()
    if client:
        _sync_client_fields(db, client)
    db.commit()
    db.refresh(c)
    return contact_to_dict(c)


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    c = db.execute(select(ClientContact).where(ClientContact.id == contact_id)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="联系人不存在")
    client = db.execute(select(Client).where(Client.id == c.client_id)).scalar_one_or_none()
    db.delete(c)
    db.flush()  # 确保删除生效，后续查询能拿到最新状态
    if client:
        _sync_client_fields(db, client)
    db.commit()
    return {"message": "已删除"}
