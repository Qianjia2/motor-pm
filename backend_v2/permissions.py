"""Module-level permission system for Motor PM.

权限格式：每模块 5 个布尔操作 {view, create, edit, delete, export}。
权限矩阵挂在部门（department.permissions）；角色（permission_role）仅作人员分组标签，
内置角色矩阵作为无部门账号的兜底，保证迁移期与旧账号平滑。
"""
import json

# 16 个模块 = 左侧侧边栏全部菜单项
MODULES = [
    "my_work",           # 我的工作台
    "dashboard",         # 项目驾驶舱
    "mgmt_weekly",       # 管理层周报
    "product_tech",      # 产品技术库
    "bom",               # BOM管理
    "projects",          # 项目台账
    "tasks_milestones",  # 任务与里程碑
    "issue_risks",       # 问题风险管理
    "phase_gate",        # 阶段门评审
    "reports",           # 报告中心
    "ai",                # AI 助手
    "knowledge",         # 知识库
    "clients",           # 客户管理
    "users",             # 资源管理（人员与账号）
    "audit_logs",        # 操作审计
    "settings",          # 系统设置
]

MODULE_LABELS = {
    "my_work": "我的工作台",
    "dashboard": "项目驾驶舱",
    "mgmt_weekly": "管理层周报",
    "product_tech": "产品技术库",
    "bom": "BOM管理",
    "projects": "项目台账",
    "tasks_milestones": "任务与里程碑",
    "issue_risks": "问题风险管理",
    "phase_gate": "阶段门评审",
    "reports": "报告中心",
    "ai": "AI 助手",
    "knowledge": "知识库",
    "clients": "客户管理",
    "users": "资源管理",
    "audit_logs": "操作审计",
    "settings": "系统设置",
}

# 旧 8 模块 → 新 16 模块展开（子模块继承父模块权限）
LEGACY_MODULE_MAP = {
    "projects": ["projects", "tasks_milestones", "issue_risks", "phase_gate"],
    "reports": ["reports", "ai"],
    "bom": ["bom"],
    "product_tech": ["product_tech"],
    "clients": ["clients"],
    "knowledge": ["knowledge"],
    "users": ["users"],
    "settings": ["settings"],
}

# 旧系统没有、需保守默认的模块
_PASSIVE_MODULES = ["my_work", "dashboard", "mgmt_weekly", "audit_logs"]

ACTIONS = ["view", "create", "edit", "delete", "export"]

ACTION_LABELS = {
    "view": "查看",
    "create": "新建",
    "edit": "编辑",
    "delete": "删除",
    "export": "导出",
}


def _all_true():
    return {a: True for a in ACTIONS}


def _none():
    return {a: False for a in ACTIONS}


def _view():
    m = _none()
    m["view"] = True
    return m


def _view_export():
    m = _view()
    m["export"] = True
    return m


def _edit():
    m = _view()
    m["create"] = True
    m["edit"] = True
    return m


# 内置角色默认矩阵（无部门账号兜底；内置角色不再出现在 UI）
BUILTIN_ROLE_DEFAULTS = {
    "admin": {m: _all_true() for m in MODULES},
    "editor": {
        m: _edit() for m in ("projects", "tasks_milestones", "issue_risks", "phase_gate", "bom", "product_tech", "clients", "knowledge", "reports", "ai")
    } | {m: _view() for m in ("my_work", "dashboard", "mgmt_weekly")}
      | {"users": _none(), "audit_logs": _none(), "settings": _none()},
    "viewer": {
        m: _view_export() for m in ("projects", "tasks_milestones", "issue_risks", "phase_gate", "bom", "product_tech", "clients", "knowledge", "reports", "ai")
    } | {m: _view() for m in ("my_work", "dashboard", "mgmt_weekly")}
      | {"users": _none(), "audit_logs": _none(), "settings": _none()},
    "member": {
        m: _view_export() for m in ("projects", "tasks_milestones", "issue_risks", "phase_gate", "bom", "product_tech", "clients", "knowledge", "reports", "ai")
    } | {m: _view() for m in ("my_work", "dashboard", "mgmt_weekly")}
      | {"users": _none(), "audit_logs": _none(), "settings": _none()},
}

BUILTIN_ROLE_DESC = {
    "admin": "全部权限：创建/编辑/删除项目、管理用户、系统设置",
    "editor": "可创建和编辑项目、报告、BOM、知识库，不可管理用户",
    "viewer": "只读：查看项目、报告、仪表盘，不可编辑",
    "member": "基础权限：查看参与的项目、填写周报",
}

# 旧 4 级 → 新矩阵映射
_LEGACY_LEVEL_MAP = {
    "none": lambda: _none(),
    "view": _view,
    "edit": _edit,
    "admin": _all_true,
}


def _parse_json(raw, default=None):
    """容忍 dict / JSON 字符串 / 双重编码字符串。"""
    if raw is None:
        return default if default is not None else {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return default if default is not None else {}
        try:
            return json.loads(s)
        except (json.JSONDecodeError, TypeError):
            return default if default is not None else {}
    return default if default is not None else {}


def normalize_legacy_permissions(raw) -> dict:
    """把任意历史格式统一为完整 16 模块 × 5 布尔矩阵。

    旧 8 模块按 LEGACY_MODULE_MAP 展开到新模块（子模块继承父模块值）；
    旧字符串值：none→全false, view→view, edit→view+create+edit, admin→全true；
    缺失模块/动作补 false。
    """
    data = _parse_json(raw, {})
    matrix = {}
    for m in MODULES:
        val = data.get(m)
        if val is None:
            # 旧 key 展开
            val = None
            for old, targets in LEGACY_MODULE_MAP.items():
                if m in targets:
                    val = data.get(old)
                    if val is not None:
                        break
        if isinstance(val, dict):
            actions = _none()
            for a in ACTIONS:
                if a in val:
                    actions[a] = bool(val[a])
            matrix[m] = actions
        elif isinstance(val, str):
            fn = _LEGACY_LEVEL_MAP.get(val)
            matrix[m] = fn() if fn else _none()
        else:
            matrix[m] = _none()
    return matrix


def get_user_permissions(user) -> dict:
    """获取用户有效权限矩阵（完整 16 模块）。

    优先级：admin 全开 → 所属部门矩阵（member.department 匹配部门表）→
    角色矩阵兜底（role_id）→ 内置默认（role 字符串）。
    """
    role = getattr(user, "role", "member")
    # 防锁死：admin 直接全开
    if role == "admin":
        return {m: _all_true() for m in MODULES}

    # 部门矩阵（权威）：人员资料的部门文本 → 部门表 → 部门权限矩阵
    try:
        member = getattr(user, "member", None)
        dept_name = getattr(member, "department", None)
        if dept_name:
            from sqlalchemy import select
            from backend_v2.models import Department
            from backend_v2.database import SessionLocal
            db = SessionLocal()
            try:
                dept = db.execute(
                    select(Department).where(Department.name == dept_name, Department.is_active == True)
                ).scalar_one_or_none()
                if dept and dept.permissions:
                    matrix = normalize_legacy_permissions(dept.permissions)
                    if any(any(v.values()) for v in matrix.values()):
                        return matrix
            finally:
                db.close()
    except Exception:
        pass

    matrix = None
    role_id = getattr(user, "role_id", None)
    if role_id:
        try:
            from backend_v2.models import PermissionRole
            from backend_v2.database import SessionLocal
            db = SessionLocal()
            try:
                pr = db.get(PermissionRole, role_id)
                if pr and pr.permissions:
                    matrix = normalize_legacy_permissions(pr.permissions)
            finally:
                db.close()
        except Exception:
            matrix = None
    if matrix is None:
        matrix = normalize_legacy_permissions(BUILTIN_ROLE_DEFAULTS.get(role, BUILTIN_ROLE_DEFAULTS["member"]))

    # 个人覆盖（兼容旧数据；新 UI 不再暴露）
    overrides = _parse_json(getattr(user, "permissions", None) or "{}", {})
    if isinstance(overrides, dict):
        for m, val in overrides.items():
            if m not in MODULES:
                continue
            if isinstance(val, dict):
                for a in ACTIONS:
                    if a in val:
                        matrix[m][a] = bool(val[a])
            elif isinstance(val, str):
                fn = _LEGACY_LEVEL_MAP.get(val)
                if fn:
                    matrix[m] = fn()
    return matrix


def check_permission(user, module: str, action: str = "view") -> bool:
    """Check if user has the action on module."""
    perms = get_user_permissions(user)
    module_perms = perms.get(module, {})
    return bool(module_perms.get(action, False))


def require_permission(module: str, action: str = "view"):
    """FastAPI dependency factory: require permission on a module."""
    from fastapi import Depends, HTTPException
    from backend_v2.auth import get_current_user

    def checker(current_user=Depends(get_current_user)):
        if not check_permission(current_user, module, action):
            raise HTTPException(status_code=403, detail=f"需要 {MODULE_LABELS.get(module, module)} 的 {ACTION_LABELS.get(action, action)} 权限")
        return current_user

    return checker
