# -*- coding: utf-8 -*-
"""部门字典 CRUD（权限矩阵载体 + 角色分组）。"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend_v2.audit import log_audit
from backend_v2.auth import get_current_user
from backend_v2.database import get_db
from backend_v2.models import Department, PermissionRole, TeamMember, UserAuth
from backend_v2.permissions import normalize_legacy_permissions, require_permission, validate_matrix

router = APIRouter(prefix="/api/departments", tags=["departments"])


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
        d.permissions = json.dumps(validate_matrix(data["permissions"]), ensure_ascii=False)
    db.commit()
    return {"message": "已更新"}


@router.post("/{dept_id}/apply-to-members")
def apply_to_members(dept_id: int, data: dict, db: Session = Depends(get_db),
                     current_user=Depends(require_permission("users", "edit"))):
    """把权限矩阵下发到本部门所有人的账号（部门模板 → 个人矩阵）。

    个人矩阵是权威的，改部门矩阵不会自动影响任何人——这个接口就是那个「显式动作」。
    调用方先 dry_run 拿名单，确认框写清「将覆盖 N 人，其中 M 人已单独配置」，再正式下发。

    关联方式与 get_user_permissions 保持一致：team_member.department 文本 == 部门名。
    跳过 admin（他们恒为全开，写了是噪音）和已停用账号。
    """
    d = db.get(Department, dept_id)
    if not d:
        raise HTTPException(status_code=404, detail="部门不存在")
    matrix = validate_matrix(data.get("permissions", d.permissions))
    dry_run = bool(data.get("dry_run", False))

    rows = db.execute(
        select(UserAuth).join(TeamMember, TeamMember.id == UserAuth.member_id)
        .where(TeamMember.department == d.name, UserAuth.is_active == True,
               UserAuth.role != "admin")
        .order_by(UserAuth.id)
    ).scalars().all()

    users = [{
        "id": u.id, "username": u.username,
        "member_name": u.member.name if u.member else None,
        "customized": u.perm_source == "manual",
    } for u in rows]
    customized = sum(1 for x in users if x["customized"])

    if not dry_run:
        payload = json.dumps(matrix, ensure_ascii=False)
        for u in rows:
            u.permissions = payload
            u.perm_source = "dept"
        db.commit()
        log_audit(db, current_user.username, "下发部门权限", "department", d.id, d.name,
                  summary=f"向「{d.name}」的 {len(rows)} 个账号下发权限矩阵"
                          f"（其中 {customized} 人原为单独配置，已被覆盖）")

    return {"department": d.name, "affected": len(rows), "customized": customized,
            "users": users, "dry_run": dry_run}


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
