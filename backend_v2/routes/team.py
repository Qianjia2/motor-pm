"""Team member & project member management."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.audit import log_audit
from backend_v2.schemas import ProjectMemberCreate, ProjectMemberUpdate
from backend_v2.models import TeamMember, ProjectMember, Project, Role, WeeklyReport, WeeklyReportLine, Task

router = APIRouter(tags=["team"])


def _sync_department(db: Session, name):
    """人员部门文本同步进部门字典（幂等）。"""
    name = (name or "").strip()
    if not name:
        return
    from backend_v2.models import Department
    exists = db.execute(select(Department).where(Department.name == name)).scalar_one_or_none()
    if exists:
        return
    max_sort = db.execute(select(func.coalesce(func.max(Department.sort_order), -1))).scalar_one()
    db.add(Department(name=name, sort_order=max_sort + 1))
    db.commit()


def _ensure_role(db: Session, name: str):
    """人员保存职务时，若角色表无此角色则自动补充，供项目详情添加成员时选用。"""
    name = (name or "").strip()
    if not name:
        return
    exists = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
    if exists:
        return
    max_sort = db.execute(select(func.max(Role.sort_order))).scalar() or 0
    db.add(Role(name=name, code=name, sort_order=max_sort + 1))
    db.commit()


# ── Team Members ──

@router.get("/api/team-members")
def list_members(
    is_active: bool = Query(True),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    q = select(TeamMember)
    if is_active:
        q = q.where(TeamMember.is_active == True)
    result = db.execute(q.order_by(TeamMember.name))
    return [{"id": m.id, "name": m.name, "department": m.department, "title": m.title,
             "email": m.email, "phone": m.phone, "skills": m.skills, "is_active": m.is_active}
            for m in result.scalars().all()]


@router.post("/api/team-members", status_code=201)
def create_member(
    member: dict,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    # Extract account fields if provided
    username = member.pop("username", "").strip() if "username" in member else ""
    password = member.pop("password", "").strip() if "password" in member else ""
    role = member.pop("accRole", "member") if "accRole" in member else "member"
    # 新 UI：按权限角色 ID 分配（role_id 权威，role 同步为兼容视图）
    acc_role_id = member.pop("accRoleId", None) if "accRoleId" in member else None
    # 模块权限随账号保存（旧 UI 的个人覆盖，新 UI 不再使用）
    import json as _json
    perms_raw = member.pop("permissions", None) if "permissions" in member else None
    permissions = _json.dumps(perms_raw, ensure_ascii=False) if perms_raw else "{}"

    from backend_v2.models import Department, PermissionRole, UserAuth
    from backend_v2.auth import hash_password

    _sync_department(db, member.get("department"))

    role_id = None
    if acc_role_id:
        pr = db.get(PermissionRole, int(acc_role_id))
        if pr:
            role_id = pr.id
            role = pr.code
    elif role in ("admin", "editor", "viewer", "member"):
        # 前端只传内置角色 code 时,补上对应内置角色的 role_id
        pr = db.execute(
            select(PermissionRole).where(PermissionRole.code == role, PermissionRole.is_builtin == True)
        ).scalar_one_or_none()
        if pr:
            role_id = pr.id

    m = TeamMember(**member)
    db.add(m)
    db.flush()
    db.refresh(m)

    # Auto-create user account if username provided
    account_created = False
    if username and password:
        existing = db.execute(select(UserAuth).where(UserAuth.username == username)).scalar_one_or_none()
        if existing:
            # 停用(is_active=False)≠删除:同名停用账号可直接启用并绑定新成员
            if not existing.is_active:
                existing.password_hash = hash_password(password)
                existing.role = role
                existing.role_id = role_id
                existing.permissions = permissions
                existing.member_id = m.id
                existing.is_active = True
                db.commit()
                account_created = True
            # If the existing account has no member linked, link it to this new member
            elif existing.member_id is None:
                existing.password_hash = hash_password(password)
                existing.role = role
                existing.role_id = role_id
                existing.permissions = permissions
                existing.member_id = m.id
                existing.is_active = True
                db.commit()
                account_created = True
            # If this account belongs to this member (含停用后重新创建), update it
            elif existing.member_id == m.id:
                existing.password_hash = hash_password(password)
                existing.role = role
                existing.role_id = role_id
                existing.permissions = permissions
                existing.is_active = True
                db.commit()
                account_created = True
            # else: username taken by another person
        else:
            u = UserAuth(username=username, password_hash=hash_password(password), role=role,
                         role_id=role_id, permissions=permissions, member_id=m.id)
            db.add(u)
            db.commit()
            account_created = True
    else:
        db.commit()

    _ensure_role(db, m.title)
    msg = "人员和账号已创建" if account_created else ("人员已创建（账号" + username + "已被占用）" if username else "人员已创建")
    return {"id": m.id, "name": m.name, "account_created": account_created, "message": msg}


@router.put("/api/team-members/{member_id}")
def update_member(
    member_id: int, data: dict,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    result = db.execute(select(TeamMember).where(TeamMember.id == member_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="不存在")
    # Only allow whitelisted fields to prevent accidental deactivation
    safe = {k: v for k, v in data.items() if k in ("name", "department", "title", "email", "phone", "skills", "bg_color", "notes", "is_active")}
    db.execute(update(TeamMember).where(TeamMember.id == member_id).values(**safe))
    db.commit()
    if "title" in safe:
        _ensure_role(db, safe["title"])
    if "department" in safe:
        _sync_department(db, safe["department"])
    return {"message": "已更新"}


# ── Project Members ──

@router.get("/api/projects/{project_id}/members")
def list_project_members(
    project_id: int,
    db: Session = Depends(get_db), _current_user=Depends(get_current_user),
):
    result = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id
        )
    )
    pms = result.scalars().all()
    return [{
        "id": pm.id, "project_id": pm.project_id, "member_id": pm.member_id,
        "role_id": pm.role_id, "allocation_pct": pm.allocation_pct, "is_key": pm.is_key,
        "member": {"id": pm.member.id, "name": pm.member.name, "department": pm.member.department, "title": pm.member.title or ""} if pm.member else None,
        "role": {"id": pm.role.id, "name": pm.role.name} if pm.role else None,
    } for pm in pms]


@router.post("/api/projects/{project_id}/members", status_code=201)
def add_project_member(
    project_id: int, data: ProjectMemberCreate,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    # Access control: only admin or project team members can add members
    if current_user.role != "admin" and current_user.member_id:
        is_project_member = db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.member_id == current_user.member_id,
            )
        ).scalar_one_or_none()
        if not is_project_member:
            raise HTTPException(status_code=403, detail="只有项目成员或管理员才能添加人员")

    # Check duplicate
    existing = (db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.member_id == data.member_id,
            ProjectMember.role_id == data.role_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="该成员已在此项目担任此角色")

    pm = ProjectMember(project_id=project_id, **data.model_dump())
    db.add(pm)
    db.commit()
    db.refresh(pm)
    log_audit(db, current_user.username, "create", "member", pm.id, f"添加成员", project_id, f"添加项目成员")
    db.commit()
    return {"id": pm.id}


@router.put("/api/project-members/{pm_id}")
def update_project_member(
    pm_id: int, data: ProjectMemberUpdate,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    result = db.execute(select(ProjectMember).where(ProjectMember.id == pm_id))
    pm = result.scalar_one_or_none()
    if not pm:
        raise HTTPException(status_code=404, detail="不存在")
    upd = data.model_dump(exclude_unset=True)
    db.execute(update(ProjectMember).where(ProjectMember.id == pm_id).values(**upd))
    db.commit()
    return {"message": "已更新"}


@router.delete("/api/project-members/{pm_id}")
def remove_project_member(
    pm_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    result = db.execute(select(ProjectMember).where(ProjectMember.id == pm_id))
    pm = result.scalar_one_or_none()
    if not pm:
        raise HTTPException(status_code=404, detail="不存在")
    # Check if member has open risks
    open_count = (db.execute(
        select(ProjectMember).where(ProjectMember.member_id == pm.member_id, ProjectMember.project_id == pm.project_id)
    )).scalar_one_or_none()
    db.execute(delete(ProjectMember).where(ProjectMember.id == pm_id))
    log_audit(db, current_user.username, "delete", "member", pm_id, f"移除成员", pm.project_id, f"移除项目成员")
    db.commit()
    return {"message": "已移除"}


@router.get("/api/resource-matrix")
def resource_matrix(db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    """Resource load: auto-calculated from weekly report activity + project assignments."""
    from datetime import date, timedelta

    today = date.today()
    four_weeks_ago = today - timedelta(weeks=4)

    result = db.execute(
        select(TeamMember).where(TeamMember.is_active == True).order_by(TeamMember.name)
    )
    members = result.scalars().all()

    # Recent weekly report activity → project participation
    recent_reports = db.execute(
        select(WeeklyReport.id, WeeklyReport.project_id)
        .where(WeeklyReport.created_at >= four_weeks_ago)
    ).all()
    recent_rpt_map = {r[0]: r[1] for r in recent_reports}
    recent_ids = list(recent_rpt_map.keys())

    activity = {}  # member_id -> set(project_ids)
    if recent_ids:
        lines = db.execute(
            select(WeeklyReportLine).where(WeeklyReportLine.report_id.in_(recent_ids))
        ).scalars().all()
        for line in lines:
            pid = recent_rpt_map.get(line.report_id)
            if not pid: continue
            pms = db.execute(select(ProjectMember).where(ProjectMember.project_id == pid)).scalars().all()
            for pm in pms:
                activity.setdefault(pm.member_id, set()).add(pid)

    resource_list = []
    for tm in members:
        pms = db.execute(select(ProjectMember).where(ProjectMember.member_id == tm.id)).scalars().all()
        assigned = {pm.project_id: pm for pm in pms}
        active_ids = activity.get(tm.id, set())
        all_ids = set(assigned.keys()) | active_ids

        projects = []
        active_count = 0
        assigned_pct_sum = 0
        for pid in all_ids:
            proj = db.get(Project, pid)
            if not proj or not proj.is_active: continue
            pm = assigned.get(pid)
            is_active = pid in active_ids
            if is_active: active_count += 1
            if pm is not None:
                assigned_pct_sum += pm.allocation_pct or 0
            projects.append({
                "project_id": pid, "project_name": proj.name, "project_code": proj.code,
                "allocation_pct": pm.allocation_pct if pm else 0,
                "role": pm.role.name if pm and pm.role else None,
                "has_recent_activity": is_active,
            })

        # 总负荷 = 各项目投入比例加总（仅统计有分配记录的项目）
        load = assigned_pct_sum

        resource_list.append({
            "member_id": tm.id, "name": tm.name,
            "department": tm.department or "", "title": tm.title or "",
            "total_allocation": load,
            "is_overloaded": load > 100,
            "active_projects": active_count,
            "projects": projects,
        })

    return sorted(resource_list, key=lambda x: x["total_allocation"], reverse=True)
