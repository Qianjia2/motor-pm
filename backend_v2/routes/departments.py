# -*- coding: utf-8 -*-
"""部门字典 CRUD（权限矩阵载体 + 角色分组）。"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend_v2.auth import get_current_user
from backend_v2.database import get_db
from backend_v2.models import Department, PermissionRole
from backend_v2.permissions import ACTIONS, MODULES, normalize_legacy_permissions, require_permission

router = APIRouter(prefix="/api/departments", tags=["departments"])


def _validate_matrix(raw) -> dict:
    """矩阵校验：normalize 补全为完整 16 模块布尔矩阵。"""
    matrix = normalize_legacy_permissions(raw)
    for m in MODULES:
        for a in ACTIONS:
            if not isinstance(matrix[m].get(a), bool):
                matrix[m][a] = bool(matrix[m].get(a, False))
    return matrix


@router.get("")
def list_departments(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """登录即可：人员/账号编辑的部门下拉也使用此接口。"""
    rows = db.execute(
        select(Department).order_by(Department.sort_order, Department.id)
    ).scalars().all()
    role_counts = dict(
        db.execute(
            select(PermissionRole.dept_id, func.count(PermissionRole.id))
            .where(PermissionRole.dept_id.isnot(None))
            .group_by(PermissionRole.dept_id)
        ).all()
    )
    return [{
        "id": d.id, "name": d.name, "sort_order": d.sort_order,
        "is_active": d.is_active, "role_count": role_counts.get(d.id, 0),
        "permissions": normalize_legacy_permissions(d.permissions),
    } for d in rows]


@router.post("")
def create_department(data: dict, db: Session = Depends(get_db), _user=Depends(require_permission("users", "create"))):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="部门名称不能为空")
    dup = db.execute(select(Department).where(Department.name == name)).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=400, detail="部门已存在")
    max_order = db.execute(select(func.coalesce(func.max(Department.sort_order), -1))).scalar_one()
    d = Department(name=name, sort_order=max_order + 1)
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"id": d.id, "name": d.name}


@router.put("/{dept_id}")
def update_department(dept_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(require_permission("users", "edit"))):
    d = db.get(Department, dept_id)
    if not d:
        raise HTTPException(status_code=404, detail="部门不存在")
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="部门名称不能为空")
        dup = db.execute(
            select(Department).where(Department.name == name, Department.id != dept_id)
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=400, detail="部门名称已存在")
        d.name = name
    if "sort_order" in data:
        d.sort_order = int(data["sort_order"])
    if "is_active" in data:
        d.is_active = bool(data["is_active"])
    if "permissions" in data:
        d.permissions = json.dumps(_validate_matrix(data["permissions"]), ensure_ascii=False)
    db.commit()
    return {"message": "已更新"}


@router.delete("/{dept_id}")
def delete_department(dept_id: int, db: Session = Depends(get_db), _user=Depends(require_permission("users", "delete"))):
    d = db.get(Department, dept_id)
    if not d:
        raise HTTPException(status_code=404, detail="部门不存在")
    role_count = db.execute(
        select(func.count(PermissionRole.id)).where(PermissionRole.dept_id == dept_id)
    ).scalar_one()
    if role_count:
        raise HTTPException(status_code=409, detail=f"该部门下还有 {role_count} 个角色，请先删除或转移角色")
    db.delete(d)
    db.commit()
    return {"message": "已删除"}
