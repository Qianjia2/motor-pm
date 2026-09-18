"""Authentication routes — login, register, refresh, logout."""
import json
import secrets as _secrets
import time as _time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, verify_token, get_current_user,
)
from backend_v2.permissions import (
    ACTIONS, MODULES, MODULE_LABELS, normalize_legacy_permissions, require_permission,
    resolve_new_user_matrix, validate_matrix,
)
from backend_v2.schemas import LoginRequest, RegisterRequest, TokenResponse
from backend_v2.models import Department, PermissionRole, UserAuth
from backend_v2.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Login rate limiting (in-memory sliding window, per IP+username) ──
_attempts: dict[str, list[float]] = {}


def _record_failure(key: str):
    now = _time.time()
    lst = _attempts.setdefault(key, [])
    lst[:] = [t for t in lst if now - t < settings.LOGIN_RATE_WINDOW]
    lst.append(now)


def _check_rate_limit(key: str):
    now = _time.time()
    lst = _attempts.get(key, [])
    lst[:] = [t for t in lst if now - t < settings.LOGIN_RATE_WINDOW]
    if len(lst) >= settings.LOGIN_RATE_LIMIT:
        raise HTTPException(status_code=429, detail=f"尝试次数过多，请 {settings.LOGIN_RATE_WINDOW // 60} 分钟后再试")


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request and request.client else "unknown"
    key = f"{client_ip}:{data.username}"
    _check_rate_limit(key)
    result = db.execute(
        select(UserAuth).where(UserAuth.username == data.username)
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        _record_failure(key)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(data.password, user.password_hash):
        _record_failure(key)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    _attempts.pop(key, None)  # 成功后清空失败计数
    access_token = create_access_token(user.username, user.id, user.role, user.member_id)
    refresh_token = create_refresh_token(user.username, user.id)

    # Store refresh token
    db.execute(
        update(UserAuth)
        .where(UserAuth.id == user.id)
        .values(refresh_token=refresh_token, last_login=datetime.utcnow())
    )
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user.to_dict() if hasattr(user, 'to_dict') else {"id": user.id, "username": user.username, "role": user.role, "member_id": user.member_id, "kb_admin": bool(getattr(user, 'kb_admin', False))},
    )


@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if not settings.REGISTER_OPEN:
        raise HTTPException(status_code=403, detail="注册已关闭，请联系管理员创建账号")
    existing = db.execute(select(UserAuth).where(UserAuth.username == data.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = UserAuth(
        username=data.username,
        password_hash=hash_password(data.password),
        member_id=data.member_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user": {"id": user.id, "username": user.username, "role": user.role}}


@router.post("/refresh")
def refresh_token(data: dict = None, db: Session = Depends(get_db)):
    refresh_token_str = data.get("refresh_token") if data else None
    if not refresh_token_str:
        raise HTTPException(status_code=400, detail="缺少 refresh_token")
    payload = verify_token(refresh_token_str)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="请使用 refresh_token")

    result = db.execute(
        select(UserAuth).where(
            UserAuth.username == payload["sub"],
            UserAuth.refresh_token == refresh_token_str,
            UserAuth.is_active == True,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="refresh_token 无效")

    access_token = create_access_token(user.username, user.id, user.role, user.member_id)
    return {"access_token": access_token}


@router.post("/logout")
def logout(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(
        update(UserAuth).where(UserAuth.id == current_user.id).values(refresh_token=None)
    )
    db.commit()
    return {"message": "已登出"}


@router.get("/me")
def me(current_user=Depends(get_current_user)):
    return {"user": current_user.to_dict() if hasattr(current_user, 'to_dict') else {"id": current_user.id, "username": current_user.username, "role": current_user.role, "member_id": current_user.member_id, "kb_admin": bool(getattr(current_user, 'kb_admin', False))}}


@router.put("/password")
def change_password(
    data: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """改密参数走 body（query 参数会进访问日志，泄露密码）。"""
    old_password = (data or {}).get("old_password", "")
    new_password = (data or {}).get("new_password", "")
    if not verify_password(old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    if len(new_password) < 3:
        raise HTTPException(status_code=400, detail="新密码至少3位")
    db.execute(
        update(UserAuth)
        .where(UserAuth.id == current_user.id)
        .values(password_hash=hash_password(new_password))
    )
    db.commit()
    return {"message": "密码已修改"}


ROLE_OPTIONS = [
    {"value": "admin", "label": "管理员", "desc": "全部权限：创建/编辑/删除项目、管理用户、系统设置"},
    {"value": "editor", "label": "编辑者", "desc": "可创建和编辑项目、报告、BOM、知识库，不可管理用户"},
    {"value": "viewer", "label": "查看者", "desc": "只读：查看项目、报告、仪表盘，不可编辑"},
    {"value": "member", "label": "成员", "desc": "基础权限：查看参与的项目、填写周报"},
]


def _role_dict(pr: PermissionRole, user_count: int) -> dict:
    return {
        "id": pr.id, "name": pr.name, "code": pr.code,
        "dept_id": pr.dept_id, "dept_name": pr.department.name if pr.department else None,
        "is_builtin": pr.is_builtin, "desc": pr.desc,
        "permissions": normalize_legacy_permissions(pr.permissions),
        "user_count": user_count,
    }


@router.get("/users")
def list_users(db: Session = Depends(get_db), _user=Depends(require_permission("users", "view"))):
    rows = db.execute(select(UserAuth).order_by(UserAuth.id)).scalars().all()
    role_names = {r.id: r.name for r in db.execute(select(PermissionRole)).scalars().all()}
    return [{
        "id": u.id, "username": u.username, "role": u.role,
        "role_id": u.role_id, "role_name": role_names.get(u.role_id),
        "permissions": normalize_legacy_permissions(u.permissions),
        "perm_source": u.perm_source,
        "is_active": u.is_active, "kb_admin": bool(u.kb_admin),
        "last_login": (u.last_login.isoformat() + "Z") if u.last_login else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "member_name": u.member.name if u.member else None,
    } for u in rows]


@router.get("/name-map")
def user_name_map(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """账号→中文姓名映射,供全平台显示中文名。登录用户即可访问。"""
    from backend_v2.models import TeamMember
    rows = db.execute(
        select(UserAuth.username, TeamMember.name)
        .join(TeamMember, TeamMember.id == UserAuth.member_id)
    ).all()
    return {u: n for u, n in rows if n}


@router.post("/users")
def create_user(data: dict, db: Session = Depends(get_db), _user=Depends(require_permission("users", "create"))):
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    if len(password) < 3:
        raise HTTPException(status_code=400, detail="密码至少3位")
    role = data.get("role", "member")
    role_id = data.get("role_id")
    if role_id:
        pr = db.get(PermissionRole, int(role_id))
        if not pr:
            raise HTTPException(status_code=400, detail="角色不存在")
        role = pr.code
    elif role not in [r["value"] for r in ROLE_OPTIONS]:
        role = "member"
    if not role_id and role in ("admin", "editor", "viewer", "member"):
        # 只传内置角色 code 时,补上对应内置角色的 role_id
        pr = db.execute(
            select(PermissionRole).where(PermissionRole.code == role, PermissionRole.is_builtin == True)
        ).scalar_one_or_none()
        if pr:
            role_id = pr.id
    member_id = data.get("member_id")
    kb_admin = bool(data.get("kb_admin", False))
    # 个人权限：显式带了算人工配置，否则套所属部门模板（见 resolve_new_user_matrix）。
    # perm_source 一定要落值——启动回填靠 `perm_source IS NULL` 判断「早于本次改造、
    # 需要固化」,建号时不落值下次重启会把新账号也冻住,之后改角色就不生效了。
    perms, perm_source = resolve_new_user_matrix(db, member_id, data.get("permissions"))

    existing = db.execute(select(UserAuth).where(UserAuth.username == username)).scalar_one_or_none()
    member_holder = None
    if member_id:
        member_holder = db.execute(
            select(UserAuth).where(UserAuth.member_id == int(member_id))
        ).scalar_one_or_none()
    if existing and existing.is_active:
        raise HTTPException(status_code=400, detail="用户名已存在")
    if member_holder and member_holder.is_active and member_holder is not existing:
        raise HTTPException(status_code=400, detail="该人员已有账号")

    # 停用(is_active=0)≠删除:同名或同成员的停用账号可直接启用并覆盖为新账号信息
    candidate = existing or member_holder
    if candidate:
        candidate.username = username
        candidate.password_hash = hash_password(password)
        candidate.role = role
        candidate.role_id = int(role_id) if role_id else None
        candidate.permissions = perms
        candidate.perm_source = perm_source
        candidate.member_id = int(member_id) if member_id else None
        candidate.kb_admin = kb_admin
        candidate.is_active = True
        db.commit()
        return {"message": "已创建", "id": candidate.id, "reactivated": True}

    u = UserAuth(
        username=username, password_hash=hash_password(password),
        role=role, role_id=int(role_id) if role_id else None,
        permissions=perms, perm_source=perm_source,
        member_id=int(member_id) if member_id else None,
        kb_admin=kb_admin,
    )
    db.add(u)
    db.commit()
    return {"message": "已创建", "id": u.id}


@router.put("/users/{user_id}")
def update_user(user_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(require_permission("users", "edit"))):
    u = db.execute(select(UserAuth).where(UserAuth.id == user_id)).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    was_admin = u.role == "admin"
    if "role" in data and "role_id" not in data:
        # 旧前端兼容：按 code 分配
        role = data["role"]
        if role not in [r["value"] for r in ROLE_OPTIONS]:
            raise HTTPException(status_code=400, detail=f"无效角色: {role}")
        u.role = role
        pr = db.execute(
            select(PermissionRole).where(PermissionRole.code == role, PermissionRole.is_builtin == True)
        ).scalar_one_or_none()
        u.role_id = pr.id if pr else None
    elif "role_id" in data:
        role_id = data["role_id"]
        if role_id in (None, "", 0):
            u.role_id = None
        else:
            pr = db.get(PermissionRole, int(role_id))
            if not pr:
                raise HTTPException(status_code=400, detail="角色不存在")
            u.role_id = pr.id
            u.role = pr.code
    # 最后管理员保护
    if was_admin and u.role != "admin":
        remain = db.execute(
            select(func.count(UserAuth.id)).where(
                UserAuth.role == "admin", UserAuth.is_active == True, UserAuth.id != u.id
            )
        ).scalar_one()
        if remain == 0:
            raise HTTPException(status_code=400, detail="系统必须保留至少一名管理员")
    if "is_active" in data:
        u.is_active = bool(data["is_active"])
    if "password" in data and data["password"]:
        u.password_hash = hash_password(data["password"])
    if "permissions" in data:
        # 人工在 UI 里配的：校验成完整 16×5 矩阵并标记来源，
        # 免得下次启动回填把这份手改的权限当成改造前的旧数据覆盖掉。
        u.permissions = json.dumps(validate_matrix(data["permissions"]), ensure_ascii=False)
        u.perm_source = "manual"
    if "kb_admin" in data:
        u.kb_admin = bool(data["kb_admin"])
    db.commit()
    return {"message": "已更新"}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission("users", "delete"))):
    u = db.execute(select(UserAuth).where(UserAuth.id == user_id)).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    if u.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    db.delete(u)
    db.commit()
    return {"message": "已删除"}


@router.get("/permission-roles")
def list_permission_roles(db: Session = Depends(get_db), _user=Depends(require_permission("users", "view"))):
    rows = db.execute(
        select(PermissionRole).order_by(PermissionRole.is_builtin.desc(), PermissionRole.sort_order, PermissionRole.id)
    ).scalars().all()
    counts = dict(
        db.execute(
            select(UserAuth.role_id, func.count(UserAuth.id))
            .where(UserAuth.role_id.isnot(None))
            .group_by(UserAuth.role_id)
        ).all()
    )
    return [_role_dict(r, counts.get(r.id, 0)) for r in rows]


@router.post("/permission-roles")
def create_permission_role(data: dict, db: Session = Depends(get_db), _user=Depends(require_permission("users", "create"))):
    name = (data.get("name") or "").strip()
    dept_id = data.get("dept_id")
    if not name:
        raise HTTPException(status_code=400, detail="角色名称不能为空")
    if not dept_id:
        raise HTTPException(status_code=400, detail="自定义角色必须选择所属部门")
    dept = db.get(Department, int(dept_id))
    if not dept:
        raise HTTPException(status_code=404, detail="部门不存在")
    dup = db.execute(
        select(PermissionRole).where(PermissionRole.dept_id == int(dept_id), PermissionRole.name == name)
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=400, detail="该部门下已存在同名角色")
    matrix = validate_matrix(data.get("permissions"))
    code = f"c{int(dept_id)}_{_secrets.token_hex(3)}"
    pr = PermissionRole(
        name=name, code=code, dept_id=int(dept_id),
        permissions=json.dumps(matrix, ensure_ascii=False),
        desc=(data.get("desc") or "")[:256], is_builtin=False,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return {"id": pr.id, "message": "已创建"}


@router.put("/permission-roles/{role_id}")
def update_permission_role(role_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(require_permission("users", "edit"))):
    pr = db.get(PermissionRole, role_id)
    if not pr:
        raise HTTPException(status_code=404, detail="角色不存在")
    if pr.is_builtin:
        if "code" in data and data["code"] != pr.code:
            raise HTTPException(status_code=400, detail="内置角色不可修改角色编码")
        if "dept_id" in data:
            raise HTTPException(status_code=400, detail="内置角色不可修改所属部门")
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="角色名称不能为空")
        pr.name = name
    if "desc" in data:
        pr.desc = (data.get("desc") or "")[:256]
    if "permissions" in data:
        matrix = validate_matrix(data["permissions"])
        if pr.is_builtin and pr.code == "admin":
            # 防锁死：内置管理员的 users 模块强制全开
            matrix["users"] = {a: True for a in ACTIONS}
        pr.permissions = json.dumps(matrix, ensure_ascii=False)
    db.commit()
    return {"message": "已更新"}


@router.delete("/permission-roles/{role_id}")
def delete_permission_role(role_id: int, db: Session = Depends(get_db), _user=Depends(require_permission("users", "delete"))):
    pr = db.get(PermissionRole, role_id)
    if not pr:
        raise HTTPException(status_code=404, detail="角色不存在")
    if pr.is_builtin:
        raise HTTPException(status_code=400, detail="内置角色不可删除")
    count = db.execute(select(func.count(UserAuth.id)).where(UserAuth.role_id == role_id)).scalar_one()
    if count:
        raise HTTPException(status_code=409, detail=f"该角色下还有 {count} 个账号，请先调整账号角色")
    db.delete(pr)
    db.commit()
    return {"message": "已删除"}


@router.get("/roles")
def list_roles(db: Session = Depends(get_db), _user=Depends(require_permission("users", "view"))):
    """角色列表（内置组在前）：兼容键 value=code / label=name / desc 保留。"""
    roles = list_permission_roles(db=db, _user=_user)
    roles.sort(key=lambda r: (0 if r["is_builtin"] else 1, r["dept_name"] or "", r["name"]))
    return [{**r, "value": r["code"], "label": r["name"]} for r in roles]


@router.get("/permissions")
def get_permission_defs(db: Session = Depends(get_db), _user=Depends(require_permission("users", "view"))):
    """模块/动作定义 + 全部角色矩阵。"""
    return {
        "modules": MODULES,
        "module_labels": MODULE_LABELS,
        "actions": ACTIONS,
        "action_labels": {"view": "查看", "create": "新建", "edit": "编辑", "delete": "删除", "export": "导出"},
        "roles": list_permission_roles(db=db, _user=_user),
    }


@router.get("/my-permissions")
def my_permissions(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Return current user's effective permissions."""
    from backend_v2.permissions import get_user_permissions
    perms = get_user_permissions(current_user)
    role_name = None
    if current_user.role_id:
        pr = db.get(PermissionRole, current_user.role_id)
        if pr:
            role_name = pr.name
    return {
        "role": current_user.role,
        "role_id": current_user.role_id,
        "role_name": role_name,
        "permissions": perms,
        "labels": MODULE_LABELS,
        "actions": ACTIONS,
        "action_labels": {"view": "查看", "create": "新建", "edit": "编辑", "delete": "删除", "export": "导出"},
    }


@router.get("/dingtalk-login-url")
def dingtalk_login_url(current_user=None):
    """Return DingTalk QR-code login URL (old-style QR connect, works for all enterprise apps)."""
    import json, os
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "dingtalk_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        raise HTTPException(400, f"钉钉配置读取失败: {e}")

    app_key = cfg.get("app_key", "")
    if not app_key:
        raise HTTPException(400, "钉钉未配置：缺少app_key")
    redirect_uri = cfg.get("oauth_redirect", "http://127.0.0.1:5002/api/auth/dingtalk-callback")
    import secrets
    state = secrets.token_hex(8)
    url = (
        f"https://oapi.dingtalk.com/connect/qrconnect?"
        f"appid={app_key}&"
        f"response_type=code&"
        f"scope=snsapi_login&"
        f"state={state}&"
        f"redirect_uri={redirect_uri}"
    )
    return {"url": url, "state": state}


@router.get("/dingtalk-callback")
def dingtalk_callback(code: str = "", state: str = "", db: Session = Depends(get_db)):
    """Handle DingTalk OAuth QR connect callback — create or login user."""
    import json, os, requests as req, urllib.parse
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "dingtalk_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        raise HTTPException(400, "钉钉未配置")

    app_key = cfg.get("app_key", "")
    app_secret = cfg.get("app_secret", "")
    if not app_key or not app_secret:
        raise HTTPException(400, "钉钉未配置")
    if not code:
        raise HTTPException(400, "缺少授权码")

    # snsapi_login: exchange code via signed request
    import time as _time, hmac as _hmac, base64 as _b64
    try:
        timestamp = str(int(_time.time() * 1000))
        # HMAC-SHA256 signature: Base64(HmacSHA256(appSecret, timestamp))
        sig = _hmac.new(
            app_secret.encode("utf-8"),
            timestamp.encode("utf-8"),
            "sha256"
        ).digest()
        signature = _b64.b64encode(sig).decode("utf-8")

        r2 = req.post(
            f"https://oapi.dingtalk.com/sns/getuserinfo_bycode?"
            f"accessKey={app_key}&timestamp={timestamp}&signature={urllib.parse.quote(signature)}",
            json={"tmp_auth_code": code},
            timeout=10,
        )
        user_info = r2.json()
    except Exception as e:
        raise HTTPException(400, f"钉钉认证失败: {e}")

    if user_info.get("errcode") != 0:
        raise HTTPException(400, f"钉钉认证失败: {user_info.get('errmsg', user_info)}")

    user_result = user_info.get("user_info", {})
    dingtalk_userid = user_result.get("openid", "") or user_result.get("userid", "")
    nick = user_result.get("nick", "") or user_result.get("name", "")
    unionid = user_result.get("unionid", "")

    if not dingtalk_userid:
        raise HTTPException(400, "未获取到钉钉用户ID")

    # snsapi_login returns limited info; mobile/email require separate corp-level API
    mobile = ""
    email = ""

    # Find or create user by dingtalk_id (userid)
    u = db.execute(select(UserAuth).where(UserAuth.dingtalk_id == dingtalk_userid)).scalar_one_or_none()
    if not u:
        username = f"dt_{dingtalk_userid[:8]}"
        existing = db.execute(select(UserAuth).where(UserAuth.username == username)).scalar_one_or_none()
        if existing:
            username = f"dt_{dingtalk_userid[:12]}"
        member_role = db.execute(
            select(PermissionRole).where(PermissionRole.code == "member", PermissionRole.is_builtin == True)
        ).scalar_one_or_none()
        u = UserAuth(
            username=username,
            password_hash=hash_password(dingtalk_userid),
            role="member",
            role_id=member_role.id if member_role else None,
            dingtalk_id=dingtalk_userid,
        )
        db.add(u)
        db.commit()
        db.refresh(u)

        # Auto-create team member
        if not u.member_id:
            from backend_v2.models import TeamMember
            m = TeamMember(name=nick or username, phone=mobile, email=email)
            db.add(m)
            db.commit()
            db.refresh(m)
            u.member_id = m.id
            db.commit()

    if not u.is_active:
        raise HTTPException(400, "账号已被禁用")

    # Generate JWT and redirect to frontend
    access_token_jwt = create_access_token(u.username, u.id, u.role, u.member_id)
    refresh_token_jwt = create_refresh_token(u.username, u.id)
    u.refresh_token = refresh_token_jwt
    u.last_login = datetime.utcnow()
    db.commit()

    name_encoded = urllib.parse.quote(nick or '', safe='')
    redirect_url = f"/login?token={access_token_jwt}&refresh={refresh_token_jwt}&user={u.username}&role={u.role}&mid={u.member_id or 0}&name={name_encoded}"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=redirect_url)


# In-memory binding token store: {state: {"member_id": int, "expires": float}}
_bind_tokens = {}
import time as _time


@router.get("/bind-dingtalk-url")
def bind_dingtalk_url(member_id: int, current_user=Depends(get_current_user)):
    """Generate a DingTalk QR-code URL for binding an existing team member to DingTalk."""
    import json, os, secrets
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "dingtalk_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        raise HTTPException(400, "钉钉未配置")

    app_key = cfg.get("app_key", "")
    if not app_key:
        raise HTTPException(400, "钉钉未配置：缺少app_key")

    # Generate unique binding token
    bind_token = secrets.token_hex(16)
    _bind_tokens[bind_token] = {"member_id": member_id, "expires": _time.time() + 300}  # 5min expiry

    bind_redirect = cfg.get("oauth_redirect", "http://127.0.0.1:5002/api/auth/dingtalk-callback").replace(
        "dingtalk-callback", "dingtalk-bind-callback"
    )
    url = (
        f"https://oapi.dingtalk.com/connect/qrconnect?"
        f"appid={app_key}&"
        f"response_type=code&"
        f"scope=snsapi_login&"
        f"state=bind_{bind_token}&"
        f"redirect_uri={bind_redirect}"
    )
    return {"url": url, "state": bind_token}


@router.get("/dingtalk-bind-callback")
def dingtalk_bind_callback(code: str = "", state: str = "", db: Session = Depends(get_db)):
    """Handle DingTalk binding callback — link DingTalk openId to existing account."""
    import json, os, requests as req, urllib.parse, hmac as _hmac, base64 as _b64

    # Parse binding token from state
    if not state.startswith("bind_"):
        raise HTTPException(400, "无效的绑定请求")
    bind_token = state[5:]
    bind_data = _bind_tokens.pop(bind_token, None)
    if not bind_data or _time.time() > bind_data["expires"]:
        raise HTTPException(400, "绑定已过期，请重新发起")
    member_id = bind_data["member_id"]

    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "dingtalk_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        raise HTTPException(400, "钉钉未配置")

    app_key = cfg.get("app_key", "")
    app_secret = cfg.get("app_secret", "")
    if not app_key or not app_secret:
        raise HTTPException(400, "钉钉未配置")
    if not code:
        raise HTTPException(400, "缺少授权码")

    # Exchange snsapi code
    try:
        timestamp = str(int(_time.time() * 1000))
        sig = _hmac.new(app_secret.encode("utf-8"), timestamp.encode("utf-8"), "sha256").digest()
        signature = _b64.b64encode(sig).decode("utf-8")
        r = req.post(
            f"https://oapi.dingtalk.com/sns/getuserinfo_bycode?"
            f"accessKey={app_key}&timestamp={timestamp}&signature={urllib.parse.quote(signature)}",
            json={"tmp_auth_code": code},
            timeout=10,
        )
        user_info = r.json()
    except Exception as e:
        raise HTTPException(400, f"钉钉认证失败: {e}")

    if user_info.get("errcode") != 0:
        raise HTTPException(400, f"钉钉认证失败: {user_info.get('errmsg', user_info)}")

    user_result = user_info.get("user_info", {})
    dingtalk_openid = user_result.get("openid", "")

    if not dingtalk_openid:
        raise HTTPException(400, "未获取到钉钉用户ID")

    # Check if this dingtalk_id is already bound to someone else
    existing = db.execute(
        select(UserAuth).where(UserAuth.dingtalk_id == dingtalk_openid, UserAuth.member_id != member_id)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(400, f"该钉钉账号已绑定到其他人员: {existing.username}")

    # Find the user account by member_id
    from backend_v2.models import TeamMember
    u = db.execute(select(UserAuth).where(UserAuth.member_id == member_id)).scalar_one_or_none()
    member = db.execute(select(TeamMember).where(TeamMember.id == member_id)).scalar_one_or_none()

    if u:
        u.dingtalk_id = dingtalk_openid
        db.commit()
        name = member.name if member else u.username
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/?bind_ok=1&name={urllib.parse.quote(name)}")
    else:
        # Member exists but no account — create one
        member_name = member.name if member else f"用户{member_id}"
        username = f"dt_{dingtalk_openid[:8]}"
        existing_u = db.execute(select(UserAuth).where(UserAuth.username == username)).scalar_one_or_none()
        if existing_u:
            username = f"dt_{dingtalk_openid[:12]}"
        member_role = db.execute(
            select(PermissionRole).where(PermissionRole.code == "member", PermissionRole.is_builtin == True)
        ).scalar_one_or_none()
        new_u = UserAuth(
            username=username,
            password_hash=hash_password(dingtalk_openid),
            role="member",
            role_id=member_role.id if member_role else None,
            member_id=member_id,
            dingtalk_id=dingtalk_openid,
        )
        db.add(new_u)
        db.commit()
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/?bind_ok=1&name={urllib.parse.quote(member_name)}")


def reset_password(username: str, new_password: str):
    """CLI utility: reset a user password directly."""
    from backend_v2.database import SessionLocal
    from backend_v2.models import UserAuth
    from sqlalchemy import select
    db = SessionLocal()
    try:
        u = db.execute(select(UserAuth).where(UserAuth.username == username)).scalar_one_or_none()
        if not u:
            print(f"错误: 用户 {username} 不存在")
            return
        u.password_hash = hash_password(new_password)
        db.commit()
        print(f"密码已重置: {username} → {new_password}")
    finally:
        db.close()

