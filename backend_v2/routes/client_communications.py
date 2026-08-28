"""客户沟通记录 CRUD + 微信图片上传/AI识别汇总."""
import json
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.config import settings
from backend_v2.models import Client, ClientCommunication

router = APIRouter(prefix="/api", tags=["client-communications"])

COMM_TYPES = ["电话", "邮件", "拜访", "微信", "会议", "其他"]

IMG_EXTS = ("png", "jpg", "jpeg", "gif", "bmp", "webp")


def comm_to_dict(c: ClientCommunication):
    return {
        "id": c.id, "client_id": c.client_id,
        "comm_date": c.comm_date.isoformat() if c.comm_date else None,
        "comm_type": c.comm_type or "其他",
        "subject": c.subject or "",
        "content": c.content or "",
        "images": json.loads(c.images) if c.images else [],
        "owner": c.owner or "",
        "contact_person": c.contact_person or "",
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _dump_images(data: dict):
    """images 字段: list -> JSON 字符串,其余直接返回。"""
    if isinstance(data.get("images"), list):
        return json.dumps(data["images"], ensure_ascii=False)
    return data.get("images")


def _get_client_or_404(db: Session, client_id: int) -> Client:
    c = db.execute(select(Client).where(Client.id == client_id, Client.is_active == True)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    return c


@router.get("/clients/{client_id}/communications")
def list_communications(client_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    _get_client_or_404(db, client_id)
    rows = db.execute(
        select(ClientCommunication).where(ClientCommunication.client_id == client_id)
        .order_by(ClientCommunication.comm_date.desc(), ClientCommunication.id.desc())
    ).scalars().all()
    return [comm_to_dict(c) for c in rows]


@router.post("/clients/{client_id}/communications", status_code=201)
def create_communication(client_id: int, data: dict, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    _get_client_or_404(db, client_id)
    comm_type = data.get("comm_type") or "其他"
    if comm_type not in COMM_TYPES:
        raise HTTPException(status_code=400, detail=f"无效沟通类型: {comm_type}")
    comm_date = data.get("comm_date")
    if comm_date:
        try:
            comm_date = date.fromisoformat(str(comm_date)[:10])
        except ValueError:
            raise HTTPException(status_code=400, detail="沟通日期格式无效")
    c = ClientCommunication(
        client_id=client_id,
        comm_date=comm_date,
        comm_type=comm_type,
        subject=(data.get("subject") or "").strip(),
        content=data.get("content") or "",
        images=_dump_images(data),
        owner=data.get("owner") or "",
        contact_person=data.get("contact_person") or "",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return comm_to_dict(c)


@router.put("/communications/{comm_id}")
def update_communication(comm_id: int, data: dict, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    c = db.execute(select(ClientCommunication).where(ClientCommunication.id == comm_id)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="沟通记录不存在")
    allowed = ["comm_date", "comm_type", "subject", "content", "owner", "contact_person", "images"]
    for k in allowed:
        if k not in data:
            continue
        if k == "comm_type":
            if data[k] not in COMM_TYPES:
                raise HTTPException(status_code=400, detail=f"无效沟通类型: {data[k]}")
            setattr(c, k, data[k])
        elif k == "comm_date":
            v = data[k]
            if v:
                try:
                    setattr(c, k, date.fromisoformat(str(v)[:10]))
                except ValueError:
                    raise HTTPException(status_code=400, detail="沟通日期格式无效")
            else:
                setattr(c, k, None)
        elif k == "images":
            setattr(c, k, _dump_images(data))
        else:
            setattr(c, k, data[k])
    c.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(c)
    return comm_to_dict(c)


@router.delete("/communications/remove-image")
def delete_comm_image(path: str = Query(...), _user=Depends(get_current_user)):
    """删除沟通记录中的一张图片文件(编辑时移除图片用)。"""
    base = Path(settings.UPLOAD_DIR).resolve()
    f = (base / path).resolve()
    if not str(f).startswith(str(base)) or not f.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    f.unlink(missing_ok=True)
    return {"ok": True}


@router.delete("/communications/{comm_id}")
def delete_communication(comm_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    c = db.execute(select(ClientCommunication).where(ClientCommunication.id == comm_id)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="沟通记录不存在")
    if c.images:  # 删除记录时同步清理图片文件
        try:
            base = Path(settings.UPLOAD_DIR).resolve()
            for p in json.loads(c.images):
                f = (base / p).resolve()
                if str(f).startswith(str(base)) and f.is_file():
                    f.unlink(missing_ok=True)
        except Exception:
            pass
    db.delete(c)
    db.commit()
    return {"message": "已删除"}


# ── 微信图片上传 + OCR + AI 识别汇总 ──

async def _ai_summarize_comm(text: str) -> str:
    """AI 汇总沟通纪要,失败时回退规则提取。"""
    try:
        from backend_v2.ai_service import call_task
        resp = await call_task("summary", [
            {"role": "system", "content": "你是电机行业项目管理助手,输出简洁专业。"},
            {"role": "user", "content": f"""你是客户管理助手。以下是客户沟通(微信)图片识别出的文本,请整理成一条结构清晰的客户沟通纪要。

识别文本：
{text[:4000]}

请按以下结构输出(无信息则省略该项)：
1. 沟通主题（一句话）
2. 客户关注点/需求
3. 我方承诺/行动项
4. 下一步安排
5. 一句话总结"""},
        ])
        resp = (resp or "").strip()
        if resp and not resp.startswith("[AI"):
            return resp
    except Exception:
        pass
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "（AI引擎暂不可用，以下为图片识别原文摘录）\n" + "；".join(lines[:8])[:500]


@router.post("/clients/{client_id}/communications/upload-images")
async def upload_comm_images(
    client_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    """上传微信图片(可多张) -> OCR 识别 -> AI 汇总为沟通纪要。"""
    _get_client_or_404(db, client_id)
    if not files:
        raise HTTPException(status_code=400, detail="未选择图片")
    from backend_v2.routes.ocr import get_reader
    reader = get_reader()

    comm_dir = Path(settings.UPLOAD_DIR) / "communications" / str(client_id)
    comm_dir.mkdir(parents=True, exist_ok=True)
    saved, texts = [], []
    for f in files:
        ext = f.filename.rsplit(".", 1)[-1].lower() if f.filename else ""
        if ext not in IMG_EXTS:
            raise HTTPException(status_code=400, detail=f"仅支持图片格式: {f.filename}")
        content = await f.read()
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"图片超过 20MB: {f.filename}")
        dest = comm_dir / f"{uuid.uuid4().hex[:8]}_{f.filename}"
        with open(dest, "wb") as fp:
            fp.write(content)
        saved.append(str(dest.relative_to(Path(settings.UPLOAD_DIR))))
        try:
            # OpenCV 读不了 UNC 网络路径,须用 PIL 读入转 numpy 数组
            from PIL import Image
            import numpy as np
            arr = np.array(Image.open(dest).convert("RGB"))
            texts.append("\n".join(reader.readtext(arr, detail=0)))
        except Exception:
            texts.append("")

    full_text = "\n\n".join(t for t in texts if t.strip())
    if not full_text.strip():
        return {"ok": False, "message": "未能从图片中识别到文字，请确认图片清晰且包含对话内容", "images": saved, "text": "", "summary": ""}
    summary = await _ai_summarize_comm(full_text)
    return {"ok": True, "message": f"识别 {len(saved)} 张图片", "images": saved, "text": full_text, "summary": summary}
