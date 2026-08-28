"""Folder tree builder and batch document operations — DB only, no JSON registry."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import ProjectDocument, Project

router = APIRouter(tags=["knowledge-folders"])


def _build_folder_tree_from_db(db, personal=False):
    """Build hierarchical folder tree directly from DB documents."""
    kb_proj = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    kb_proj_id = kb_proj.id if kb_proj else None

    docs = db.execute(select(ProjectDocument.folder, ProjectDocument.project_id, ProjectDocument.notes)).all()
    all_folders = {}
    for folder_col, proj_id, notes in docs:
        f = folder_col
        if (not f or f == "/") and proj_id and proj_id != kb_proj_id:
            proj = db.get(Project, proj_id)
            if proj and proj.name: f = proj.name
        f = (f or "").strip("/")
        if f: all_folders[f] = all_folders.get(f, 0) + 1

    root = {"path": "/", "name": "根目录", "count": sum(all_folders.values()), "children": []}
    node_map = {"/": root}
    for fpath, count in sorted(all_folders.items()):
        fp = "/" + fpath
        parts = fp.split("/")
        parent_path = "/"
        for i in range(1, len(parts)):
            seg = parts[i]
            cur_path = "/".join(parts[:i+1])
            if cur_path not in node_map:
                node_map[cur_path] = {"path": cur_path, "name": seg, "count": 0, "children": []}
                node_map[parent_path]["children"].append(node_map[cur_path])
            if i == len(parts) - 1:
                node_map[cur_path]["count"] = (node_map[cur_path].get("count", 0) or 0) + count
            parent_path = cur_path
    return [root]


@router.post("/api/knowledge/documents/batch-tag")
def batch_tag(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Batch add/remove tags on documents."""
    doc_ids = data.get("ids", [])
    tags = data.get("tags", [])
    action = data.get("action", "set")
    if not doc_ids: raise HTTPException(400, "缺少文档ID")
    docs = db.execute(select(ProjectDocument).where(ProjectDocument.id.in_(doc_ids))).scalars().all()
    updated = 0
    for d in docs:
        current = json.loads(d.tags or "[]")
        if action == "set": new_tags = tags
        elif action == "add": new_tags = list(set(current + tags))
        elif action == "remove": new_tags = [t for t in current if t not in tags]
        else: new_tags = current
        d.tags = json.dumps(new_tags, ensure_ascii=False)
        updated += 1
    db.commit()
    return {"updated": updated}


@router.post("/api/knowledge/documents/batch-type")
def batch_type(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Batch change document type/category."""
    doc_ids = data.get("ids", [])
    doc_type = data.get("doc_type", "")
    if not doc_ids or not doc_type: raise HTTPException(400, "参数错误")
    db.execute(update(ProjectDocument).where(ProjectDocument.id.in_(doc_ids)).values(doc_type=doc_type))
    db.commit()
    return {"updated": len(doc_ids)}
