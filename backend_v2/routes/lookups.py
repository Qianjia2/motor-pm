"""Reference data endpoints — phases, gates, technical lines, roles, doc types (full CRUD)."""
import json, os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import Phase, Gate, TechnicalLine, Role
from backend_v2.storage import safe_load, safe_save

router = APIRouter(prefix="/api/lookups", tags=["lookups"])

DOC_TYPES_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "doc_types.json")

DEFAULT_DOC_TYPES = {
    "groups": [
        {"id": "P0", "name": "P0 需求阶段", "types": [
            {"value": "p0_contract", "label": "开发合同"},
            {"value": "p0_tech_agreement", "label": "技术协议"},
            {"value": "p0_requirement", "label": "需求规格书"},
            {"value": "p0_project_init", "label": "立项报告"}]},
        {"id": "PP1", "name": "PP1 研发阶段", "types": [
            {"value": "pp1_sim_model", "label": "仿真模型"},
            {"value": "pp1_design_report", "label": "设计报告"},
            {"value": "pp1_drawing", "label": "工程图纸"},
            {"value": "pp1_test_plan", "label": "测试方案"}]},
        {"id": "PP2", "name": "PP2 验证阶段", "types": [
            {"value": "pp2_prototype_report", "label": "样机测试报告"},
            {"value": "pp2_data_regression", "label": "数据回归分析"},
            {"value": "pp2_improve_plan", "label": "改进计划"},
            {"value": "pp2_improve_report", "label": "改进方案和报告"}]},
        {"id": "OTHER", "name": "其他", "types": [
            {"value": "other", "label": "其他文档"}]},
    ]
}

def _load_doc_types():
    return safe_load(DOC_TYPES_FILE, dict(DEFAULT_DOC_TYPES))

def _save_doc_types(data):
    safe_save(DOC_TYPES_FILE, data)

# ── Generic CRUD helper ──
def _crud_get(model, db, order_by="sort_order", extra_filter=None):
    q = select(model)
    if extra_filter is not None:
        q = q.where(extra_filter)
    result = db.execute(q.order_by(getattr(model, order_by)))
    rows = result.scalars().all()
    return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows]

def _crud_create(model, data, db, current_user):
    allowed = {c.name for c in model.__table__.columns if c.name != "id"}
    obj = model(**{k: v for k, v in data.items() if k in allowed})
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

def _crud_update(model, item_id, data, db):
    result = db.execute(select(model).where(model.id == item_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="不存在")
    allowed = {c.name for c in model.__table__.columns if c.name != "id"}
    for k, v in data.items():
        if k in allowed:
            setattr(obj, k, v)
    db.commit()
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

def _crud_delete(model, item_id, db):
    result = db.execute(select(model).where(model.id == item_id))
    obj = result.scalar_one_or_none()
    if not obj: raise HTTPException(status_code=404, detail="不存在")
    db.delete(obj)
    db.commit()
    return {"message": "已删除"}

# ── Phases ────────────────
@router.get("/phases")
def get_phases(project_type: str = None, db: Session = Depends(get_db)):
    """project_type=hardware/software 时只返回该类型的阶段;省略返回全部。"""
    if project_type in ("hardware", "software"):
        return _crud_get(Phase, db, extra_filter=(Phase.project_type == project_type))
    return _crud_get(Phase, db)

@router.post("/phases", status_code=201)
def create_phase(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_create(Phase, data, db, user)

@router.put("/phases/{item_id}")
def update_phase(item_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_update(Phase, item_id, data, db)

@router.delete("/phases/{item_id}")
def delete_phase(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_delete(Phase, item_id, db)

# ── Gates ────────────────
@router.get("/gates")
def get_gates(db: Session = Depends(get_db)):
    return _crud_get(Gate, db)

@router.post("/gates", status_code=201)
def create_gate(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_create(Gate, data, db, user)

@router.put("/gates/{item_id}")
def update_gate(item_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_update(Gate, item_id, data, db)

@router.delete("/gates/{item_id}")
def delete_gate(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_delete(Gate, item_id, db)

# ── Technical Lines ────────────────
@router.get("/technical-lines")
def get_lines(db: Session = Depends(get_db)):
    return _crud_get(TechnicalLine, db)

@router.post("/technical-lines", status_code=201)
def create_line(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_create(TechnicalLine, data, db, user)

@router.put("/technical-lines/{item_id}")
def update_line(item_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_update(TechnicalLine, item_id, data, db)

@router.delete("/technical-lines/{item_id}")
def delete_line(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_delete(TechnicalLine, item_id, db)

# ── Roles ────────────────
@router.get("/roles")
def get_roles(db: Session = Depends(get_db)):
    return _crud_get(Role, db)

@router.post("/roles", status_code=201)
def create_role(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_create(Role, data, db, user)

@router.put("/roles/{item_id}")
def update_role(item_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_update(Role, item_id, data, db)

@router.delete("/roles/{item_id}")
def delete_role(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if getattr(user, 'role', '') != 'admin': raise HTTPException(status_code=403, detail="仅管理员可操作")
    return _crud_delete(Role, item_id, db)

# ── Document Types (JSON-backed) ────────────────
@router.get("/doc-types")
def get_doc_types():
    return _load_doc_types()

@router.put("/doc-types")
def save_doc_types(data: dict, _user=Depends(get_current_user)):
    if not data.get("groups"):
        raise HTTPException(status_code=400, detail="缺少 groups 字段")
    _save_doc_types(data)
    return {"message": "文档类型已保存"}


# ── Project Tabs Config ──
TABS_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "project_tabs.json")

DEFAULT_TABS = [
    # phase: P0=需求阶段, PP1=设计阶段, PP2=验证阶段, PP3=试制阶段, PP4=交付阶段, all=全程通用
    {"name": "overview", "label": "概览", "icon": "InfoFilled", "visible": True, "phase": "all"},
    {"name": "phases", "label": "阶段门径", "icon": "Timer", "visible": True, "phase": "all"},
    {"name": "risks", "label": "风险/问题", "icon": "Warning", "visible": True, "phase": "all"},
    {"name": "changes", "label": "变更管理(含ECN)", "icon": "Document", "visible": True, "phase": "all"},
    {"name": "reports", "label": "周报", "icon": "Edit", "visible": True, "phase": "all"},
    {"name": "finance", "label": "财务", "icon": "Money", "visible": True, "phase": "all"},
    {"name": "analytics", "label": "分析", "icon": "DataAnalysis", "visible": True, "phase": "all"},
    {"name": "requirements", "label": "需求管理", "icon": "List", "visible": True, "phase": "P0"},
    {"name": "docs", "label": "项目文档", "icon": "Folder", "visible": True, "phase": "all"},
    {"name": "tasks", "label": "WBS任务分解", "icon": "List", "visible": True, "phase": "PP1"},
    {"name": "team", "label": "团队", "icon": "User", "visible": True, "phase": "PP1"},
    {"name": "milestones", "label": "里程碑", "icon": "Timer", "visible": True, "phase": "all"},
    {"name": "prototype", "label": "样机试制(含BOM)", "icon": "Setting", "visible": True, "phase": "PP2"},
    {"name": "deliverables", "label": "阶段交付物矩阵", "icon": "FolderOpened", "visible": True, "phase": "PP3"},
    {"name": "testing", "label": "测试验证", "icon": "CircleCheck", "visible": True, "phase": "PP3"},
]

PHASE_GROUPS = [
    {"id": "all", "name": "全程管控", "desc": "概览/门径/风险/变更/周报/财务", "color": "#6b7280", "children": []},
    {"id": "deliverables", "name": "阶段交付物矩阵", "desc": "各阶段交付物标准与状态", "color": "#0ea5e9", "children": [
        {"id": "P0", "name": "概念需求阶段", "desc": "需求/文档/合同/协议", "color": "#3b82f6", "children": []},
        {"id": "PP1", "name": "方案设计阶段", "desc": "任务/团队/里程碑", "color": "#8b5cf6", "children": []},
        {"id": "PP2", "name": "样机试制阶段", "desc": "BOM/物料齐套/样机装配", "color": "#f59e0b", "children": []},
        {"id": "PP3", "name": "验证阶段", "desc": "DV/PV/台架/耐久/环境测试", "color": "#10b981", "children": []},
        {"id": "PP4", "name": "设计定型阶段", "desc": "设计冻结/量产移交/验收归档", "color": "#06b6d4", "children": []},
    ]},
]

# 软件研发项目:纯软件性能模块开发,无硬件/样机试制
SOFTWARE_PHASE_GROUPS = [
    {"id": "all", "name": "全程管控", "desc": "概览/门径/风险/变更/周报/财务", "color": "#6b7280", "children": []},
    {"id": "deliverables", "name": "阶段交付物矩阵", "desc": "各阶段交付物标准与状态", "color": "#0ea5e9", "children": [
        {"id": "S0", "name": "需求分析阶段", "desc": "需求调研/需求评审", "color": "#3b82f6", "children": []},
        {"id": "S1", "name": "架构设计阶段", "desc": "架构/技术选型/接口", "color": "#8b5cf6", "children": []},
        {"id": "S2", "name": "开发编码阶段", "desc": "模块开发/单元测试", "color": "#f59e0b", "children": []},
        {"id": "S3", "name": "测试验证阶段", "desc": "集成/性能/验收测试", "color": "#10b981", "children": []},
        {"id": "S4", "name": "发布交付阶段", "desc": "版本发布/部署交付", "color": "#06b6d4", "children": []},
    ]},
]


@router.get("/admin/project-phase-groups")
def get_phase_groups(project_type: str = None):
    if project_type == "software":
        return SOFTWARE_PHASE_GROUPS
    return PHASE_GROUPS


@router.get("/admin/project-tabs-config")
def get_tabs_config(project_type: str = None, _user=Depends(get_current_user)):
    if project_type == "software":
        return _software_tabs()
    data = safe_load(TABS_CONFIG_FILE, None)
    return data if data is not None else DEFAULT_TABS


def _software_tabs():
    """软件项目 tab:保留通用模块;阶段模块映射到 S0-S4,去掉样机试制。"""
    return [
        {"name": "overview", "label": "概览", "icon": "InfoFilled", "visible": True, "phase": "all"},
        {"name": "phases", "label": "阶段门径", "icon": "Timer", "visible": True, "phase": "all"},
        {"name": "risks", "label": "风险/问题", "icon": "Warning", "visible": True, "phase": "all"},
        {"name": "changes", "label": "变更管理(含ECN)", "icon": "Document", "visible": True, "phase": "all"},
        {"name": "reports", "label": "周报", "icon": "Edit", "visible": True, "phase": "all"},
        {"name": "finance", "label": "财务", "icon": "Money", "visible": True, "phase": "all"},
        {"name": "analytics", "label": "分析", "icon": "DataAnalysis", "visible": True, "phase": "all"},
        {"name": "docs", "label": "项目文档", "icon": "Folder", "visible": True, "phase": "all"},
        {"name": "milestones", "label": "里程碑", "icon": "Timer", "visible": True, "phase": "all"},
        {"name": "gantt", "label": "甘特图", "icon": "Timer", "visible": True, "phase": "all"},
        {"name": "requirements", "label": "需求管理", "icon": "List", "visible": True, "phase": "S0"},
        {"name": "tasks", "label": "WBS任务分解", "icon": "List", "visible": True, "phase": "S1"},
        {"name": "team", "label": "团队", "icon": "User", "visible": True, "phase": "S1"},
        {"name": "testing", "label": "测试验证", "icon": "CircleCheck", "visible": True, "phase": "S3"},
        {"name": "deliverables", "label": "阶段交付物矩阵", "icon": "FolderOpened", "visible": True, "phase": "S4"},
    ]


@router.put("/admin/project-tabs-config")
def save_tabs_config(data: dict, _user=Depends(get_current_user)):
    tabs = data.get("tabs", data.get("data", []))
    safe_save(TABS_CONFIG_FILE, tabs)
    return {"message": "Tab配置已保存", "count": len(tabs)}


# ── Data backup management ──
@router.get("/admin/data-files")
def list_data_files(_user=Depends(get_current_user)):
    """List all data files with backup status."""
    from backend_v2.storage import file_info, restore_from_backup
    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
    files = []
    for f in sorted(os.listdir(data_dir)):
        if f.endswith('.json') and not f.endswith('.bak'):
            path = os.path.join(data_dir, f)
            info = file_info(path)
            info["name"] = f
            del info["file"]
            files.append(info)
    return {"files": files, "total": len(files)}


@router.post("/admin/data-files/restore")
def restore_data_file(body: dict, _user=Depends(get_current_user)):
    """Restore a data file from its latest backup."""
    from backend_v2.storage import restore_from_backup
    name = body.get("file", "")
    if not name or "/" in name or "\\" in name:
        raise HTTPException(400, "无效文件名")
    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
    path = os.path.join(data_dir, name)
    if not os.path.exists(path + ".bak") and not os.path.exists(path + ".2"):
        raise HTTPException(404, "无可用备份")
    data = restore_from_backup(path)
    if data is None:
        raise HTTPException(500, "恢复失败")
    count = len(data) if isinstance(data, (list, dict)) else 1
    return {"message": f"已从备份恢复 {name} ({count} 条记录)", "count": count}
