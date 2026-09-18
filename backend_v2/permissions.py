"""Module-level permission system for Motor PM.

权限格式：每模块 5 个布尔操作 {view, create, edit, delete, export}。

权限**按人**：账号自己的 user_auth.permissions 就是权威矩阵（见 get_user_permissions）。
部门（department.permissions）退居为模板——只在「这个人还没配过」时提供默认值，
改完部门矩阵不会自动生效到任何人，要用「应用到本部门所有人」显式下发。
角色（permission_role）仅作人员分组标签；内置角色矩阵是无部门账号的兜底。

注意：本模块只回答「这个人有没有某个模块的某个动作」。接口层是否真的校验，
取决于各路由有没有挂 require_permission —— 目前只有资源管理和项目签核挂了，
其余模块是「前端按矩阵隐藏菜单、接口不拦」，详见交付说明。
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


def matrix_has_any(matrix) -> bool:
    """矩阵里是否有任何一个动作被开过（部门矩阵的空判定沿用此语义）。"""
    return any(any(v.values()) for v in matrix.values())


def is_configured(raw) -> bool:
    """个人权限是否「已配置」——必须在 normalize 之前判断。

    normalize_legacy_permissions 总是返回完整 16 模块矩阵，拿它的结果判会永远为真。
    这里直接看原始数据里出现过哪些模块键：只要出现过就说明有人给这个人配过，
    哪怕全配成 false 那也是刻意的决定，不再回落到部门模板。

    旧 8 模块的键（projects/reports/bom/...）全部包含在新 16 模块里，所以旧格式
    同样能识别出来。
    """
    data = _parse_json(raw, {})
    if not isinstance(data, dict):
        return False
    return any(m in data for m in MODULES)


def validate_matrix(raw) -> dict:
    """把任意历史格式校验成完整 16 模块 × 5 布尔矩阵（所有写入点的统一出口）。"""
    matrix = normalize_legacy_permissions(raw)
    for m in MODULES:
        for a in ACTIONS:
            if not isinstance(matrix[m].get(a), bool):
                matrix[m][a] = bool(matrix[m].get(a, False))
    return matrix


def dept_matrix_by_name(db, dept_name):
    """按部门名取权限矩阵（模板用途）。部门不存在/停用/没配矩阵/矩阵全 false → None。"""
    if not dept_name or not str(dept_name).strip():
        return None
    from sqlalchemy import select

    from backend_v2.models import Department
    dept = db.execute(
        select(Department).where(
            Department.name == str(dept_name).strip(), Department.is_active == True
        )
    ).scalar_one_or_none()
    if not dept or not dept.permissions:
        return None
    matrix = normalize_legacy_permissions(dept.permissions)
    return matrix if matrix_has_any(matrix) else None


def dept_matrix_for_member(db, member_id):
    """按人员取其所部门的权限矩阵（模板用途）。"""
    if not member_id:
        return None
    from backend_v2.models import TeamMember
    m = db.get(TeamMember, int(member_id))
    return dept_matrix_by_name(db, m.department) if m else None


def resolve_new_user_matrix(db, member_id, raw_permissions):
    """新建 / 绑定账号时决定个人矩阵与来源，返回 (permissions_json, perm_source)。

    - 请求显式带了 permissions → 人工配置，来源 'manual'
    - 否则套所属部门模板 → 来源 'dept'
    - 既没带、所属部门也没模板 → 'dept' + "{}"（= 没配过，继续按角色矩阵/内置默认兜底）

    最后那种情况**不能**把内置角色矩阵烤进去：烤进去这个人就变成「已配置」了，
    以后管理员改他的角色（role_id）不会再影响权限——而那是今天正常能用的行为，
    这里必须保持不动。

    perm_source 一定要落值（哪怕权限是空的）：启动回填靠 `perm_source IS NULL`
    判断「这行早于改造、需要固化」，建号时不落值的话下次重启会把新账号也冻住，
    之后改角色同样失效。
    """
    # 「带没带权限」只认真正的 dict / 非空 JSON 字符串；其他类型（列表、数字等垃圾输入）
    # 一律当没带，免得被 validate_matrix 静默转成一份全 false 矩阵，把人权限清空。
    provided = False
    if isinstance(raw_permissions, dict):
        provided = bool(raw_permissions)
    elif isinstance(raw_permissions, str):
        provided = raw_permissions.strip() not in ("", "{}")
    if provided:
        return json.dumps(validate_matrix(raw_permissions), ensure_ascii=False), "manual"
    tmpl = dept_matrix_for_member(db, member_id)
    if tmpl:
        return json.dumps(tmpl, ensure_ascii=False), "dept"
    # 必须是字面 "{}"（空=没配过），不能写 validate_matrix({}) 那份 16×5 全 false 矩阵——
    # 后者会被 is_configured 判成「已配置」，这个人就变成没有任何权限了。
    return "{}", "dept"


def get_user_permissions(user) -> dict:
    """获取用户有效权限矩阵（完整 16 模块）。

    优先级：admin 全开 → 本人矩阵（已配置即权威）→ 所属部门矩阵 →
    角色矩阵兜底（role_id）→ 内置默认（role 字符串）。

    个人矩阵**不自动跟随部门**：部门矩阵只在「这个人还没配过」时提供默认值。
    改完部门矩阵要生效，得走「应用到本部门所有人」显式下发——否则改一个部门
    会静默改掉下面所有人的权限，在运行中的系统上太危险。
    """
    role = getattr(user, "role", "member")
    # 防锁死：admin 直接全开
    if role == "admin":
        return {m: _all_true() for m in MODULES}

    # 本人矩阵（权威）：配过就认这一份，包括被刻意收成全 false 的情况。
    # 判定在打开任何 DB session 之前完成——已配置的人省掉下面两次 SessionLocal。
    personal = getattr(user, "permissions", None)
    if is_configured(personal):
        return validate_matrix(personal)

    # 部门矩阵（模板）：人员资料的部门文本 → 部门表 → 部门权限矩阵
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
                    if matrix_has_any(matrix):
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
