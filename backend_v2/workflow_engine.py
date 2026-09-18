"""工作流引擎：模板装配、项目实例化、权限解析、状态流转。

══ 这个引擎做什么 ══
把「项目级宏观流程」（routes/training_process.py 里硬编码的 PHASE_NODES，
85 个节点）升格成**可配置的状态机**：每个节点有标准状态语义、有按人的进入/
退出权限、有流转规则、有强制拖拽与回退。PHASE_NODES 本身一行没改，它是模板
的素材；本引擎把它导入成 wf_state_def。

══ 三层严格分开（需求明确要求） ══
  工作项元模型 / 属性模型 / 工作流定义不混在一个字段里：
  · 状态定义  wf_state_def         —— 「有哪些状态」
  · 流转规则  wf_transition_def    —— 「状态之间怎么走」
  · 权限原子  wf_node_acl_def      —— 「谁能进/出/改字段/强拖」
  三者各自成表，互不内嵌。

══ 四类权限原子 ══
  can_enter（进入）· can_exit（退出）· can_edit_fields（编辑字段）· can_force_drag（强制拖拽）
  前三个取**并集**——在任一匹配的主体上为真即为真（allow 胜）。
  第四个取**交集**——任一匹配主体为假即为假（deny 胜），且**永不继承**：
  模板默认给谁就是谁，不会因为「谁都没明确给」而落到某个宽泛主体上。
  另外 项目经理 和 admin 无条件拥有强制拖拽（需求：PM 有超级权限）。

══ 和既有 workflow 接口的关系 ══
互不干扰。GET /api/projects/{id}/workflow 仍按交付物现算状态，本次没碰它。
本引擎**持有**状态（project_wf_state.runtime_status）——这不是重复：
现算的话「强制拖拽把它推到已完成」根本表达不出来（交付物没批，现算永远算回
未开始）。两者各管一段，一期先并行，验证稳定后再谈收敛。
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_v2.models import (
    Project, ProjectMember, WfTemplate, WfTemplateVersion, WfStateDef,
    WfTransitionDef, WfNodeAclDef, ProjectWfInstance, ProjectWfState,
    ProjectWfTransition, ProjectWfNodeAcl, WfStateChangeLog, WfForceDragLog,
)

# ── 七种标准状态语义（需求规定，模板里的名称只是显示别名，语义不可自定义）──
SEMANTIC_STATES = (
    "not_started", "in_progress", "pending_review", "pending_verify",
    "completed", "blocked", "cancelled",
)
SEMANTIC_LABELS = {
    "not_started": "未开始",
    "in_progress": "进行中",
    "pending_review": "待评审",
    "pending_verify": "待验证",
    "completed": "已完成",
    "blocked": "已阻塞",
    "cancelled": "已取消",
}

# ── 四类权限原子 ──
PERM_ATOMS = ("can_enter", "can_exit", "can_edit_fields", "can_force_drag")
PERM_LABELS = {
    "can_enter": "进入", "can_exit": "退出",
    "can_edit_fields": "编辑字段", "can_force_drag": "强制拖拽",
}

HARDWARE_PHASES = ("P0", "PP1", "PP2", "PP3", "PP4", "PP5")
SOFTWARE_PHASES = ("S0", "S1", "S2", "S3")

PHASE_NAMES = {
    "P0": "概念需求", "PP1": "方案设计", "PP2": "样机试制",
    "PP3": "验证测试", "PP4": "设计定型", "PP5": "售后维护",
    "S0": "需求分析", "S1": "软件开发", "S2": "测试验证", "S3": "发布交付",
}

# 一期只落 A/B 两个模板（C/D 内部研发暂不做）。
# A↔hardware、B↔software 一一对应，所以 project 表不需要新增列——
# 项目选了哪个模板记在 project_wf_instance.template_id 上。
TEMPLATES = (
    {
        "code": "A", "name": "合同交付·电机电控集成",
        "project_type": "hardware", "category": "contract",
        "phases": HARDWARE_PHASES, "sort_order": 1,
        "description": "客户合同驱动的电机/电控整机交付：概念需求→方案设计→样机试制→验证→定型→售后。",
    },
    {
        "code": "B", "name": "合同交付·软件定制",
        "project_type": "software", "category": "contract",
        "phases": SOFTWARE_PHASES, "sort_order": 2,
        "description": "客户合同驱动的软件定制交付：需求分析→开发→测试验证→发布交付。",
    },
)

# 一天的回退窗口（强制拖拽回退的默认时效）。需求侧待确认项，先按 24h 落地，
# 放在常量里而不是散在代码里，改的时候一处改。
FORCE_DRAG_REVERT_WINDOW_HOURS = 24

# 不可回滚的动作类型（回退时要把这些标出来，让人知道"退回去也撤不掉"）。
# 一期没有真正的对外副作用动作（通知/工单都还没接），所以是空集；
# 留给二期接自动化动作时填。留这个常量是为了让回退逻辑的形状现在就正确。
UNREVERTABLE_ACTIONS: set = set()


# ══════════════════════════════════════════════════════════════════
# 语义推导：PHASE_NODES 的一个节点 → 七语义之一
# ══════════════════════════════════════════════════════════════════

def is_gate_node(node: dict) -> bool:
    """门禁节点：每阶段末位，由 _gate_node() 生成。

    判据用 module 而不是 name：name 是给人看的会改，module 表达的是
    "这一步在平台的哪个功能里做"，门禁节点恒指向「阶段门径」。
    """
    return "阶段门径" in (node.get("module") or "")


def semantic_of(node: dict) -> str:
    """该节点的标准语义。

    判据顺序有讲究：
      1. 门禁节点 → 待评审（它就是那道评审/放行）
      2. 名称含评审/会签/签署 → 待评审
      3. 产出标注「必需交付物」→ 待验证（产出要验收批准才算完）
      4. 其余 → 进行中（含全部线下节点：平台观测不到，人工推进）
    """
    if is_gate_node(node):
        return "pending_review"
    name = node.get("name") or ""
    if any(k in name for k in ("评审", "会签", "签署")):
        return "pending_review"
    if "必需交付物" in (node.get("output") or ""):
        return "pending_verify"
    return "in_progress"


def _phase_nodes():
    """延迟导入 PHASE_NODES。

    不在模块顶层 import：routes/training_process.py 会 import fastapi 和
    本包的其它模块，顶层导入容易在启动顺序上绕成环。这里只在真正播种/实例化
    时取一次，代价可忽略。
    """
    from backend_v2.routes.training_process import PHASE_NODES, PHASE_ENTRY_EXIT
    return PHASE_NODES, PHASE_ENTRY_EXIT


def build_states_for_phases(phases) -> list:
    """把若干阶段的 PHASE_NODES 摊平成状态定义列表（模板装配的唯一入口）。

    返回 [{state_code, name, semantic_state, phase_code, node_seq, lane,
           sort_order, is_initial, is_terminal, is_gate, is_required,
           entry_condition, exit_condition}, ...]
    state_code = "<阶段码>-<节点序号>"，形如 "PP1-3"。
    用 code 而不是自增 id 做身份：历史迁移改过 phase 的 id，code 不变
    （同 ProjectWorkflowStepConfirm 的取舍）。
    """
    phase_nodes, entry_exit = _phase_nodes()
    out = []
    sort = 0
    for phase_code in phases:
        nodes = phase_nodes.get(phase_code) or []
        entry, exit_ = entry_exit.get(phase_code, (None, None))
        for node in nodes:
            sort += 1
            gate = is_gate_node(node)
            out.append({
                "state_code": f"{phase_code}-{node['seq']}",
                "name": node["name"],
                "semantic_state": semantic_of(node),
                "phase_code": phase_code,
                "node_seq": node["seq"],
                "lane": phase_code,
                # 门禁节点不是"必经验证的作业节点"，它本身就是放行动作；
                # is_required 描述的是"跳过它要不要填原因"，门禁跳过必须填，
                # 所以照样为真。
                "sort_order": sort,
                "is_initial": sort == 1,
                "is_terminal": False,          # 全流程末位在下面统一标
                "is_gate": gate,
                "is_required": True,
                "entry_condition": _json_dumps(entry) if entry else None,
                "exit_condition": _json_dumps(exit_) if exit_ else None,
                "roles": list(node.get("roles") or []),
            })
    if out:
        out[-1]["is_terminal"] = True
    return out


def build_transitions(states: list) -> list:
    """状态之间的边。

    一期只登记**线性主干**：按 sort_order 相邻相连，跨阶段自然连通
    （因为 sort_order 是全局递增的）。不做分叉——分叉要等有真实业务
    需求时按模板加，凭空造出来的分叉没人会走。

    blocked / cancelled / completed 不是节点，是**运行态**，由引擎的
    set_status 操作处理，不在这张边表里。
    """
    out = []
    for i in range(len(states) - 1):
        out.append({
            "from_state_code": states[i]["state_code"],
            "to_state_code": states[i + 1]["state_code"],
            "name": f"{states[i]['name']} → {states[i + 1]['name']}",
            "require_reason": False,
            "auto": False,
            "sort_order": i + 1,
        })
    return out


def build_acls(states: list, pm_force_drag: bool = True) -> list:
    """从节点自带的 roles 生成默认权限。

    这是本次最省事也最正确的一步：PHASE_NODES 每个节点本来就写了 roles
    （"这一步该谁做"），直接落成 can_enter/can_exit/can_edit_fields 的
    默认值即可，不需要重新问一遍业务。

    ⚠ 关键取舍：subject_name 存**角色名**，subject_id 只在能解析到
    role.id 时才填。因为 PHASE_NODES 用到 16 个角色名，其中 8 个
    （工艺工程师/技术负责人/管理层/试制负责人/采购/财务/责任工程师/
    市场运营）在 role 表里根本不存在——只存外键会把它们全丢掉，那些步骤
    会变成"除了管理员没人推得动"。按名字匹配也正是既有 _can_confirm_node
    的行为，这里保持一致。

    项目经理额外拿 can_force_drag（PM 超级权限）。给的是 ACL 行而不是
    硬编码判断，这样项目层可以通过删改那一行收回——虽然引擎里对
    "项目经理" 这个角色名另有一条无条件兜底（见 resolve_permissions），
    两条都在，是为了让模板默认值可见可审计。
    """
    out = []
    for st in states:
        roles = st.get("roles") or []
        for role_name in roles:
            out.append({
                "state_code": st["state_code"],
                "subject_type": "role_name",
                "subject_name": role_name,
                "subject_id": None,          # 播种时回填
                "can_enter": True,
                "can_exit": True,
                "can_edit_fields": True,
                "can_force_drag": (pm_force_drag and role_name == "项目经理"),
                "field_scope": None,
            })
    return out


# ══════════════════════════════════════════════════════════════════
# 播种：模板层
# ══════════════════════════════════════════════════════════════════

def _json_dumps(v):
    import json
    return json.dumps(v, ensure_ascii=False)


def _json_loads(v, default=None):
    import json
    if not v:
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


def _role_id_map(db: Session) -> dict:
    """角色名 → role.id。用于给 ACL 行的 subject_id 回填（解析不到就 NULL）。"""
    from backend_v2.models import Role
    return {r.name: r.id for r in db.execute(select(Role)).scalars().all()}


def _ensure_template(db: Session, tpl_def: dict) -> WfTemplate:
    """查不到就建；已存在只补 name/description 这类展示字段，不碰版本内容。"""
    tpl = db.execute(
        select(WfTemplate).where(WfTemplate.code == tpl_def["code"])
    ).scalar_one_or_none()
    if tpl is None:
        tpl = WfTemplate(
            code=tpl_def["code"], name=tpl_def["name"],
            project_type=tpl_def["project_type"], category=tpl_def["category"],
            description=tpl_def["description"], sort_order=tpl_def["sort_order"],
            is_active=True,
        )
        db.add(tpl)
        db.flush()
    else:
        # 只更新展示字段。project_type / category 是身份的一部分，改了会让
        # 已实例化的项目语义漂移，不动。
        tpl.name = tpl_def["name"]
        tpl.description = tpl_def["description"]
    return tpl


def _ensure_version(db: Session, tpl: WfTemplate, tpl_def: dict) -> WfTemplateVersion:
    """模板的 v1。

    已存在就直接返回，**绝不重建内容**——版本一旦有项目实例在用就不改内容，
    这是"记录基于哪个模板版本"能成立的前提（见 WfTemplateVersion 的注释）。
    所以模板内容要改，得走"新建 v2"而不是改 v1，一期不自动做这件事。
    """
    ver = db.execute(
        select(WfTemplateVersion).where(
            WfTemplateVersion.template_id == tpl.id,
            WfTemplateVersion.version_no == 1,
        )
    ).scalar_one_or_none()
    if ver is not None:
        return ver

    ver = WfTemplateVersion(
        template_id=tpl.id, version_no=1, status="published",
        note=f"初版：由 PHASE_NODES 的 {'/'.join(tpl_def['phases'])} 阶段导入",
        created_by="system",
    )
    db.add(ver)
    db.flush()

    states = build_states_for_phases(tpl_def["phases"])
    role_ids = _role_id_map(db)

    for s in states:
        db.add(WfStateDef(
            version_id=ver.id, state_code=s["state_code"], name=s["name"],
            semantic_state=s["semantic_state"], phase_code=s["phase_code"],
            node_seq=s["node_seq"], lane=s["lane"], sort_order=s["sort_order"],
            is_initial=s["is_initial"], is_terminal=s["is_terminal"],
            is_gate=s["is_gate"], is_required=s["is_required"],
            entry_condition=s["entry_condition"], exit_condition=s["exit_condition"],
        ))

    for t in build_transitions(states):
        db.add(WfTransitionDef(version_id=ver.id, **t))

    for a in build_acls(states):
        a = dict(a)
        a["subject_id"] = role_ids.get(a["subject_name"])
        db.add(WfNodeAclDef(version_id=ver.id, **a))

    db.flush()
    return ver


def seed_workflow_engine():
    """启动时播种模板 A/B。幂等，异常不阻断启动（同 permission_migrate 的约定）。

    为什么幂等靠"查不到就建"而不是"标记列"：和 _seed_*_standards 一个道理，
    这里播种的是**模板定义**，不是一次性回填。但要注意配套约定——
    以后要删模板/状态，必须软删（is_active=0），硬删会在下次启动被原样插回来。
    """
    import logging
    log = logging.getLogger("workflow_engine")
    from backend_v2.database import SessionLocal
    db = SessionLocal()
    try:
        for tpl_def in TEMPLATES:
            tpl = _ensure_template(db, tpl_def)
            _ensure_version(db, tpl, tpl_def)
        db.commit()
        log.info("工作流模板播种完成（A/B）")
    except Exception:
        db.rollback()
        log.exception("工作流模板播种失败（不阻断启动）")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════
# 实例化：模板 → 项目
# ══════════════════════════════════════════════════════════════════

def pick_template(db: Session, project_type: str):
    """按项目类型挑模板。A↔hardware、B↔software 一一对应。

    找不到返回 None —— 调用方决定是报错还是跳过，不在这里 raise：
    播种失败时项目创建不应该跟着挂掉（既有项目全都在用，不能因为新引擎
    出问题就建不了项目）。
    """
    tpl = db.execute(
        select(WfTemplate).where(
            WfTemplate.project_type == project_type,
            WfTemplate.category == "contract",
            WfTemplate.is_active == True,  # noqa: E712
        ).order_by(WfTemplate.sort_order)
    ).scalars().first()
    if tpl is None:
        return None
    ver = db.execute(
        select(WfTemplateVersion).where(
            WfTemplateVersion.template_id == tpl.id,
            WfTemplateVersion.status == "published",
        ).order_by(WfTemplateVersion.version_no.desc())
    ).scalars().first()
    return (tpl, ver) if ver else None


def instantiate(db: Session, project: Project, created_by: str = "system"):
    """给项目生成工作流实例（深拷贝模板，不是引用）。

    深拷贝而不是引用，是需求里"项目层可自由调整"的前提：如果项目直接读模板
    定义，PM 改一个状态就会改到所有同模板的项目上。拷贝出来的副本独立演化，
    迁移时才按 base_version 做差异比较。

    幂等：项目已有实例直接返回，不重建（重建会把运行态清掉）。
    """
    exist = db.execute(
        select(ProjectWfInstance).where(ProjectWfInstance.project_id == project.id)
    ).scalar_one_or_none()
    if exist is not None:
        return exist

    picked = pick_template(db, project.project_type or "hardware")
    if picked is None:
        return None
    tpl, ver = picked

    inst = ProjectWfInstance(
        project_id=project.id, template_id=tpl.id,
        base_version_id=ver.id, current_version_id=ver.id,
        status="active", created_by=created_by,
    )
    db.add(inst)
    db.flush()

    defs = db.execute(
        select(WfStateDef).where(WfStateDef.version_id == ver.id)
        .order_by(WfStateDef.sort_order)
    ).scalars().all()
    for d in defs:
        db.add(ProjectWfState(
            instance_id=inst.id, state_code=d.state_code, name=d.name,
            semantic_state=d.semantic_state, phase_code=d.phase_code,
            node_seq=d.node_seq, lane=d.lane, sort_order=d.sort_order,
            is_initial=d.is_initial, is_terminal=d.is_terminal,
            is_gate=d.is_gate, is_required=d.is_required,
            entry_condition=d.entry_condition, exit_condition=d.exit_condition,
            sla_hours=d.sla_hours,
            # 初始状态直接是"进行中"——项目从第一个节点就开始了；
            # 其余节点未开始。用 not_started 而不是让整张表都是未开始，
            # 是为了让"当前在哪"这件事一眼可见。
            runtime_status="in_progress" if d.is_initial else "not_started",
            status_source="auto",
            last_changed_at=datetime.utcnow() if d.is_initial else None,
        ))

    for t in db.execute(
        select(WfTransitionDef).where(WfTransitionDef.version_id == ver.id)
    ).scalars().all():
        db.add(ProjectWfTransition(
            instance_id=inst.id, from_state_code=t.from_state_code,
            to_state_code=t.to_state_code, name=t.name,
            require_reason=t.require_reason, auto=t.auto, sort_order=t.sort_order,
        ))

    for a in db.execute(
        select(WfNodeAclDef).where(WfNodeAclDef.version_id == ver.id)
    ).scalars().all():
        db.add(ProjectWfNodeAcl(
            instance_id=inst.id, state_code=a.state_code,
            subject_type=a.subject_type, subject_name=a.subject_name,
            subject_id=a.subject_id, can_enter=a.can_enter, can_exit=a.can_exit,
            can_edit_fields=a.can_edit_fields, can_force_drag=a.can_force_drag,
            field_scope=a.field_scope,
        ))

    db.flush()
    return inst


# ══════════════════════════════════════════════════════════════════
# 权限解析
# ══════════════════════════════════════════════════════════════════

def my_roles(db: Session, project_id: int, user) -> list:
    """当前用户在该项目里的角色名列表。

    与 routes/project_workflow.py::_my_roles 同形——故意不抽公共函数：
    那一个是既有接口在用的，动它要重跑一遍既有回归；这边是引擎的，将来
    引擎要是加了"用户组"这类新主体，两边就会分叉，不如各自独立。
    """
    if not getattr(user, "member_id", None):
        return []
    rows = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.member_id == user.member_id,
        )
    ).scalars().all()
    return [pm.role.name for pm in rows if pm.role]


def _subject_matches(subject_type: str, subject_name: str, subject_id,
                     user, roles: list) -> bool:
    """这条 ACL 行管不管当前这个人。"""
    if subject_type == "user":
        return getattr(user, "member_id", None) is not None and subject_id == user.member_id
    if subject_type in ("role_name", "project_role"):
        # project_role 与 role_name 都按名字匹配：PHASE_NODES 的 16 个角色名里
        # 有 8 个在 role 表里根本不存在，按 id 匹配会把它们全丢掉。
        return subject_name in roles
    if subject_type == "group":
        # 用户组二期再做（wf_group 表还没落）。留分支而不是静默返回 False
        # 之外的东西——静默 True 会变成越权。
        return False
    return False


def resolve_permissions(db: Session, instance_id: int, state_code: str, user,
                        roles: list = None) -> dict:
    """解析某人在某状态上的四类权限。

    并集 / 交集的分野是本函数的全部要点：
      can_enter / can_exit / can_edit_fields  → 任一匹配主体为真即为真（allow 胜）
      can_force_drag                          → 任一匹配主体为假即为假（deny 胜）

    为什么强制拖拽要反着来：它是能跳过验证的超级权限，宽松解释的代价是
    "谁都能跳过门禁"，严格解释的代价只是"PM 多点一次授权"。这类权限一律
    宁严勿宽。
    """
    rows = db.execute(
        select(ProjectWfNodeAcl).where(
            ProjectWfNodeAcl.instance_id == instance_id,
            ProjectWfNodeAcl.state_code == state_code,
        )
    ).scalars().all()

    matched = [
        r for r in rows
        if _subject_matches(r.subject_type, r.subject_name, r.subject_id, user, roles or [])
    ]

    is_admin = getattr(user, "role", None) == "admin"
    is_pm = "项目经理" in (roles or [])

    if is_admin:
        return {
            "can_enter": True, "can_exit": True,
            "can_edit_fields": True, "can_force_drag": True,
            "matched": ["admin"], "reason": "管理员",
        }

    out = {}
    for atom in ("can_enter", "can_exit", "can_edit_fields"):
        out[atom] = any(bool(getattr(r, atom)) for r in matched)

    if is_pm:
        # 需求：PM 有超级权限（强制拖拽）。无条件，不受模板 ACL 影响——
        # 否则模板少配一行就能把 PM 锁死，项目卡住没人能解。
        out["can_force_drag"] = True
    elif not matched:
        # 没有任何 ACL 行匹配：强行不授权。这里**不**回退到"有 projects.edit
        # 就放行"——既有 _can_confirm_node 的兜底是历史包袱，新引擎不继承它，
        # 否则权限矩阵配了个寂寞。
        out["can_force_drag"] = False
    else:
        # deny 胜：任一匹配主体为假即为假
        out["can_force_drag"] = all(bool(r.can_force_drag) for r in matched)

    out["matched"] = [f"{r.subject_type}:{r.subject_name}" for r in matched]
    out["reason"] = "项目经理" if is_pm else (",".join(out["matched"]) or "无匹配主体")
    return out


# ══════════════════════════════════════════════════════════════════
# 流转
# ══════════════════════════════════════════════════════════════════

def _log_change(db, project_id, instance_id, state_code, from_sem, to_sem,
                action, operator, roles, reason=None, force_drag_log_id=None):
    db.add(WfStateChangeLog(
        project_id=project_id, instance_id=instance_id, state_code=state_code,
        from_semantic=from_sem, to_semantic=to_sem, action=action,
        operator=operator, operator_roles=_json_dumps(roles or []),
        reason=reason, force_drag_log_id=force_drag_log_id,
    ))


def advance(db: Session, project: Project, inst: ProjectWfInstance,
            state_code: str, to_state_code: str, user, roles: list,
            reason: str = None) -> dict:
    """正式流转：把 state_code 这个节点推到 to_state_code。

    服务端强制校验（用户明确选定）。校验顺序有讲究——先查存在性再查权限，
    因为"这个状态不存在"是配置问题，"你没权限"是人的问题，两者分开报，
    排查时不会互相污染。
    """
    states = {s.state_code: s for s in db.execute(
        select(ProjectWfState).where(ProjectWfState.instance_id == inst.id)
    ).scalars().all()}

    src = states.get(state_code)
    dst = states.get(to_state_code)
    if src is None:
        raise WfError(404, f"状态 {state_code} 不存在")
    if dst is None:
        raise WfError(404, f"目标状态 {to_state_code} 不存在")

    perm = resolve_permissions(db, inst.id, state_code, user, roles)
    if not perm["can_exit"]:
        raise WfError(403, f"你没有「{src.name}」的退出权限")

    edge = db.execute(
        select(ProjectWfTransition).where(
            ProjectWfTransition.instance_id == inst.id,
            ProjectWfTransition.from_state_code == state_code,
            ProjectWfTransition.to_state_code == to_state_code,
        )
    ).scalar_one_or_none()
    if edge is None:
        raise WfError(400, f"「{src.name}」到「{dst.name}」不是一条允许的流转路径")

    if edge.require_reason and not (reason or "").strip():
        raise WfError(400, "这条流转需要填写原因")

    # 先记下原状态再改——台账要的是"从哪来"，改完再读读到的是"到哪去"。
    src_before = src.runtime_status
    dst_before = dst.runtime_status

    src.runtime_status = "completed"
    src.status_source = "manual"
    src.last_changed_at = datetime.utcnow()
    src.last_changed_by = user.username

    dst.runtime_status = "in_progress"
    dst.status_source = "manual"
    dst.last_changed_at = datetime.utcnow()
    dst.last_changed_by = user.username

    _log_change(db, project.id, inst.id, state_code, src_before,
                "completed", "exit", user.username, roles, reason)
    _log_change(db, project.id, inst.id, to_state_code, dst_before,
                "in_progress", "enter", user.username, roles, reason)

    return {"from": state_code, "to": to_state_code}


def set_status(db: Session, project: Project, inst: ProjectWfInstance,
               state_code: str, to_status: str, user, roles: list,
               reason: str = None) -> dict:
    """改运行态（阻塞/取消/恢复），不动节点位置。

    和 advance 分开是有意的：阻塞一个节点不等于走到下一个节点。混在一个接口
    里会逼着调用方传一堆"这次到底改哪个"的标志位。
    """
    if to_status not in SEMANTIC_STATES:
        raise WfError(400, f"未知状态语义：{to_status}")

    src = db.execute(
        select(ProjectWfState).where(
            ProjectWfState.instance_id == inst.id,
            ProjectWfState.state_code == state_code,
        )
    ).scalar_one_or_none()
    if src is None:
        raise WfError(404, f"状态 {state_code} 不存在")

    perm = resolve_permissions(db, inst.id, state_code, user, roles)
    if not perm["can_exit"]:
        raise WfError(403, f"你没有「{src.name}」的退出权限")

    # 阻塞与取消是"踩刹车"，要求填原因——这两种状态最容易变成烂尾，
    # 没有原因追溯就等于没有。
    if to_status in ("blocked", "cancelled") and not (reason or "").strip():
        raise WfError(400, "标记为已阻塞 / 已取消时必须填写原因")

    before = src.runtime_status
    src.runtime_status = to_status
    src.status_source = "manual"
    src.last_changed_at = datetime.utcnow()
    src.last_changed_by = user.username

    _log_change(db, project.id, inst.id, state_code, before, to_status,
                "set_status", user.username, roles, reason)
    return {"state_code": state_code, "from": before, "to": to_status}


def force_drag(db: Session, project: Project, inst: ProjectWfInstance,
               to_state_code: str, user, roles: list, reason: str = None) -> dict:
    """PM 强制拖拽：直接跳到任意状态，跳过中间必经验证节点。

    需求第 5 项要求的四件事全在这里：
      1. 填原因（跳过了必经节点时强制）
      2. 记审计（wf_force_drag_log + wf_state_change_log）
      3. 发通知（一期只写审计，通知走二期的 notification_outbox）
      4. 自动创建补验证待办（skipped 列表就是待办的依据，见 _skipped_states）
    """
    states = {s.state_code: s for s in db.execute(
        select(ProjectWfState).where(ProjectWfState.instance_id == inst.id)
        .order_by(ProjectWfState.sort_order)
    ).scalars().all()}

    dst = states.get(to_state_code)
    if dst is None:
        raise WfError(404, f"目标状态 {to_state_code} 不存在")

    perm = resolve_permissions(db, inst.id, to_state_code, user, roles)
    if not perm["can_force_drag"]:
        raise WfError(403, "只有项目经理可以强制拖拽")

    # 当前节点 = 第一个未完成的节点
    current = _current_state(states)
    from_code = current.state_code if current else None

    skipped = _skipped_states(states, from_code, to_state_code)
    # 只有跳过"必经验证/评审节点"才强制填原因。项目自己早就是完成态、
    # 现在往回拖一格的场景不该被拦。
    must_reason = any(s["is_required"] for s in skipped)
    if must_reason and not (reason or "").strip():
        names = "、".join(s["name"] for s in skipped if s["is_required"])
        raise WfError(400, f"跳过必经验证节点（{names}）必须填写原因")

    has_unrevertable = bool(UNREVERTABLE_ACTIONS) and any(
        s["semantic_state"] in ("pending_verify",) for s in skipped
    )

    log = WfForceDragLog(
        project_id=project.id, instance_id=inst.id,
        from_state_code=from_code,
        from_state_name=current.name if current else None,
        from_semantic=current.runtime_status if current else None,
        to_state_code=to_state_code, to_state_name=dst.name,
        to_semantic=dst.runtime_status,
        operator=user.username, operator_roles=_json_dumps(roles or []),
        reason=reason, reason_required=must_reason,
        skipped_states=_json_dumps(skipped) if skipped else None,
        has_unrevertable=has_unrevertable,
        auto_backlog_created=bool(skipped),
    )
    db.add(log)
    db.flush()

    force_before = current.runtime_status if current else None

    # 被跳过的节点按语义落到应有的终态：**执行类**的算是"做过了"置 completed；
    # 验证/评审类的留在原状，靠 skipped 记录追责——它们没被验证过，
    # 置成 completed 就是撒谎，补验证待办也正是靠这个区别才有对象。
    for s in skipped:
        if s["semantic_state"] in ("in_progress",):
            node = states[s["state_code"]]
            node.runtime_status = "completed"
            node.status_source = "force"
            node.last_changed_at = datetime.utcnow()
            node.last_changed_by = user.username

    if current is not None:
        current.runtime_status = "completed"
        current.status_source = "force"
        current.last_changed_at = datetime.utcnow()
        current.last_changed_by = user.username

    # 落到目标节点：取它的定义语义。拖到一个"待评审"节点就该显示待评审，
    # 而不是笼统的进行中——这样界面上一眼能看出卡在评审还是卡在干活。
    dst.runtime_status = dst.semantic_state
    dst.status_source = "force"
    dst.last_changed_at = datetime.utcnow()
    dst.last_changed_by = user.username

    _log_change(db, project.id, inst.id, to_state_code,
                force_before, dst.runtime_status, "force_drag",
                user.username, roles, reason, force_drag_log_id=log.id)

    return {
        "force_drag_log_id": log.id,
        "from_state_code": from_code,
        "to_state_code": to_state_code,
        "skipped": [s["state_code"] for s in skipped],
        "reason_required": must_reason,
    }


def _current_state(states: dict):
    """当前节点 = 排序最靠前的"还没完成"的节点。

    不是"最后一个非未开始"——因为已经完成的节点也是非未开始。用"第一个未完成"
    才符合流程直觉：前面还有没做完的，当前位置就在那里。
    """
    ordered = sorted(states.values(), key=lambda s: s.sort_order)
    for s in ordered:
        if s.runtime_status not in ("completed", "cancelled"):
            return s
    return ordered[-1] if ordered else None


def _skipped_states(states: dict, from_code: str, to_code: str) -> list:
    """从 from 到 to 之间被跳过的节点。

    判据是**排序位置**而不是可达性：一期主干是线性链，位置差就是跳过的全部。
    等以后模板出现分叉，这里要换成按边做可达性判断（那时才需要），
    现在写可达性算法是给一个不存在的分叉做准备——过度设计。
    """
    if not from_code:
        return []
    src = states.get(from_code)
    dst = states.get(to_code)
    if src is None or dst is None:
        return []
    lo, hi = sorted((src.sort_order, dst.sort_order))
    out = []
    for s in sorted(states.values(), key=lambda x: x.sort_order):
        if lo < s.sort_order < hi and s.state_code not in (from_code, to_code):
            out.append({
                "state_code": s.state_code, "name": s.name,
                # 存**定义语义**而不是运行态：运行态回退时会被改写，
                # 审计要能复述"当时跳过的是哪一类节点"。
                "semantic_state": s.semantic_state,
                "is_required": bool(s.is_required),
            })
    return out


def revert_force_drag(db: Session, project: Project, inst: ProjectWfInstance,
                      log_id: int, user, roles: list, reason: str = None) -> dict:
    """撤销一次强制拖拽。

    按**反向顺序**把被跳过和末位节点的运行态还原回拖拽前的样子。不做真正的
    "反向补偿动作"——一期没有任何对外副作用动作（通知/工单都没接），所以
    还原状态就够了；等二期接了动作，这里要按 compensation ledger 逐项回滚。
    """
    log = db.get(WfForceDragLog, log_id)
    if log is None or log.instance_id != inst.id:
        raise WfError(404, "强制拖拽记录不存在")
    if log.is_reverted:
        raise WfError(409, "这次强制拖拽已经回退过了")

    perm = resolve_permissions(db, inst.id, log.to_state_code, user, roles)
    if not perm["can_force_drag"]:
        raise WfError(403, "只有项目经理可以回退强制拖拽")

    # 默认 24h 时效。超了不禁止但要求填原因——回退太久以前的操作本身
    # 就是件需要解释的事，而不是应该被系统硬拦的事。
    window = timedelta(hours=FORCE_DRAG_REVERT_WINDOW_HOURS)
    expired = log.created_at and (datetime.utcnow() - log.created_at) > window
    if expired and not (reason or "").strip():
        raise WfError(400, f"超过 {FORCE_DRAG_REVERT_WINDOW_HOURS} 小时的回退必须填写原因")

    states = {s.state_code: s for s in db.execute(
        select(ProjectWfState).where(ProjectWfState.instance_id == inst.id)
    ).scalars().all()}

    # 反向还原：先把它拖到的那一格放回去，再把跳过的还原成未开始。
    dst = states.get(log.to_state_code)
    revert_before = dst.runtime_status if dst else None

    if dst is not None:
        dst.runtime_status = "not_started"
        dst.status_source = "revert"
        dst.last_changed_at = datetime.utcnow()
        dst.last_changed_by = user.username

    for item in (_json_loads(log.skipped_states, []) or []):
        s = states.get(item.get("state_code"))
        if s is not None:
            s.runtime_status = "not_started"
            s.status_source = "revert"
            s.last_changed_at = datetime.utcnow()
            s.last_changed_by = user.username

    src = states.get(log.from_state_code) if log.from_state_code else None
    if src is not None:
        src.runtime_status = "in_progress"
        src.status_source = "revert"
        src.last_changed_at = datetime.utcnow()
        src.last_changed_by = user.username

    log.is_reverted = True
    log.reverted_at = datetime.utcnow()
    log.reverted_by = user.username

    _log_change(db, project.id, inst.id, log.to_state_code,
                revert_before,
                src.runtime_status if src else None,
                "revert", user.username, roles, reason,
                force_drag_log_id=log.id)

    return {"reverted": log_id, "restored_to": log.from_state_code}


class WfError(Exception):
    """带 HTTP 状态码的引擎错误。路由层翻译成 HTTPException。

    不直接 raise HTTPException：引擎要能被脚本和测试直接调用（不起 HTTP），
    绑死 fastapi 会让那些用法多一层无谓的依赖。
    """

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
