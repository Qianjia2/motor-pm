"""培训任务清单:按模块 x 基础/进阶/高级三档,账号使用者完成任务并由管理员审核."""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from backend_v2.database import get_db
from backend_v2.models import TrainingTask, TrainingTaskProgress, TrainingModuleVisit
from backend_v2.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/training/tasks", tags=["training-tasks"])

LEVEL_NAMES = {"basic": "基础", "intermediate": "进阶", "advanced": "高级"}
VALID_LEVELS = set(LEVEL_NAMES)

# 提交校验实操痕迹的有效窗口:7 天内访问过关联模块页面才允许提交
VISIT_WINDOW_DAYS = 7

# 可选关联模块(页面路径 -> 名称),供管理端配置;路径以 / 开头即可,不强制在本表内
MODULE_TARGETS = {
    "/projects": "项目列表",
    "/management-weekly": "管理层周报",
    "/tasks-milestones": "任务与里程碑",
    "/gantt": "甘特图",
    "/milestones": "里程碑",
    "/clients": "客户管理",
    "/bom": "BOM 管理",
    "/issue-risks": "问题风险管理",
    "/phase-gate-review": "阶段门评审",
    "/product-tech": "产品技术库",
    "/knowledge": "知识库",
    "/resources": "资源中心",
    "/training": "培训学习",
    "/reports": "报表中心",
    "/ai": "AI 助手",
}


def _serialize_task(t: TrainingTask, my: TrainingTaskProgress = None, visited_paths=frozenset()):
    return {
        "id": t.id,
        "category": t.category,
        "level": t.level,
        "level_name": LEVEL_NAMES.get(t.level, t.level),
        "title": t.title,
        "description": t.description,
        "points": t.points,
        "required_target": t.required_target or "",
        "required_target_name": MODULE_TARGETS.get(t.required_target, t.required_target or ""),
        "my_visited": bool(t.required_target and t.required_target in visited_paths),
        "my_status": my.status if my else "pending",
        "my_submit_note": my.submit_note if my else "",
        "my_review_note": my.review_note if my else "",
    }


def _get_progress(db: Session, task_id: int, user_id: int):
    return db.query(TrainingTaskProgress).filter(
        TrainingTaskProgress.task_id == task_id,
        TrainingTaskProgress.user_id == user_id,
    ).first()


@router.get("")
def list_tasks(_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """全部任务按模块分组,附带当前用户进度."""
    tasks = db.query(TrainingTask).filter(TrainingTask.is_active == True).order_by(
        TrainingTask.sort_order, TrainingTask.id).all()
    cutoff = datetime.utcnow() - timedelta(days=VISIT_WINDOW_DAYS)
    visited_paths = {v.module_path for v in db.query(TrainingModuleVisit).filter(
        TrainingModuleVisit.user_id == _user.id,
        TrainingModuleVisit.visited_at >= cutoff,
    ).all()}
    groups = {}
    for t in tasks:
        my = _get_progress(db, t.id, _user.id)
        g = groups.setdefault(t.category, {"category": t.category, "tasks": []})
        g["tasks"].append(_serialize_task(t, my, visited_paths))
    # 按模块字母序;每组内按基础->进阶->高级排序
    for g in groups.values():
        g["tasks"].sort(key=lambda x: list(LEVEL_NAMES).index(x["level"]))
    return {"items": sorted(groups.values(), key=lambda x: x["category"])}


@router.get("/stats")
def my_stats(_user=Depends(get_current_user), db: Session = Depends(get_db)):
    tasks = db.query(TrainingTask).filter(TrainingTask.is_active == True).all()
    pros = {p.task_id: p for p in db.query(TrainingTaskProgress).filter(
        TrainingTaskProgress.user_id == _user.id).all()}
    total = len(tasks)
    approved = sum(1 for t in tasks if pros.get(t.id) and pros[t.id].status == "approved")
    submitted = sum(1 for t in tasks if pros.get(t.id) and pros[t.id].status == "submitted")
    rejected = sum(1 for t in tasks if pros.get(t.id) and pros[t.id].status == "rejected")
    points_earned = sum(((pros.get(t.id) and pros[t.id].status == "approved") and t.points or 0) for t in tasks)
    points_total = sum(t.points for t in tasks)
    by_level = {}
    for t in tasks:
        lv = by_level.setdefault(LEVEL_NAMES.get(t.level, t.level),
                                 {"total": 0, "approved": 0})
        lv["total"] += 1
        p = pros.get(t.id)
        if p and p.status == "approved":
            lv["approved"] += 1
    return {
        "total": total, "approved": approved, "submitted": submitted, "rejected": rejected,
        "pending": total - approved - submitted,
        "points_earned": points_earned, "points_total": points_total,
        "progress_pct": round(approved * 100 / total) if total else 0,
        "by_level": [{"level": k, **v} for k, v in by_level.items()],
    }


@router.get("/reviews")
def list_reviews(_admin=Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(TrainingTaskProgress).filter(
        TrainingTaskProgress.status == "submitted").order_by(
        TrainingTaskProgress.submitted_at.desc()).all()
    out = []
    for p in rows:
        out.append({
            "progress_id": p.id,
            "task_id": p.task_id,
            "category": p.task.category if p.task else "",
            "level": p.task.level if p.task else "",
            "level_name": LEVEL_NAMES.get(p.task.level, "") if p.task else "",
            "title": p.task.title if p.task else "",
            "points": p.task.points if p.task else 0,
            "username": p.username,
            "submit_note": p.submit_note,
            "submitted_at": p.submitted_at.strftime("%Y-%m-%d %H:%M") if p.submitted_at else "",
        })
    return {"items": out}


@router.post("")
def create_task(payload: dict = Body(...), _admin=Depends(require_admin), db: Session = Depends(get_db)):
    category = (payload.get("category") or "").strip()
    level = (payload.get("level") or "").strip()
    title = (payload.get("title") or "").strip()
    if not category or not title:
        raise HTTPException(status_code=400, detail="请填写所属模块和任务标题")
    if level not in VALID_LEVELS:
        raise HTTPException(status_code=400, detail="等级必须是 基础/进阶/高级")
    t = TrainingTask(
        category=category, level=level, title=title,
        description=(payload.get("description") or "").strip(),
        points=int(payload.get("points") or 10),
        required_target=_clean_target(payload.get("required_target")),
        sort_order=int(payload.get("sort_order") or 0),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"message": "任务已创建", "task": _serialize_task(t)}


@router.put("/{task_id}")
def update_task(task_id: int, payload: dict = Body(...), _admin=Depends(require_admin), db: Session = Depends(get_db)):
    t = db.query(TrainingTask).get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if payload.get("category") is not None:
        t.category = payload["category"].strip()
    if payload.get("level") is not None:
        if payload["level"] not in VALID_LEVELS:
            raise HTTPException(status_code=400, detail="等级必须是 基础/进阶/高级")
        t.level = payload["level"]
    if payload.get("title") is not None:
        t.title = payload["title"].strip()
    if payload.get("description") is not None:
        t.description = payload["description"].strip()
    if payload.get("points") is not None:
        t.points = int(payload["points"])
    if payload.get("required_target") is not None:
        t.required_target = _clean_target(payload["required_target"])
    if payload.get("sort_order") is not None:
        t.sort_order = int(payload["sort_order"])
    db.commit()
    return {"message": "任务已更新"}


@router.delete("/{task_id}")
def delete_task(task_id: int, _admin=Depends(require_admin), db: Session = Depends(get_db)):
    t = db.query(TrainingTask).get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    db.query(TrainingTaskProgress).filter(TrainingTaskProgress.task_id == task_id).delete()
    db.delete(t)
    db.commit()
    return {"message": "任务已删除"}


def _clean_target(value):
    v = (value or "").strip()
    return v if v.startswith("/") else None


@router.post("/visit")
def report_visit(payload: dict = Body(...), _user=Depends(get_current_user), db: Session = Depends(get_db)):
    """前端进入模块页面时上报一次访问,作为任务提交前的实操痕迹。"""
    path = (payload.get("module_path") or "").strip()
    if not path.startswith("/") or len(path) > 128:
        raise HTTPException(status_code=400, detail="module_path 必须是 / 开头的页面路径")
    v = TrainingModuleVisit(user_id=_user.id, username=_user.username, module_path=path)
    db.add(v)
    db.commit()
    return {"message": "ok"}


@router.post("/{task_id}/submit")
def submit_task(task_id: int, payload: dict = Body(...), _user=Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(TrainingTask).filter(TrainingTask.id == task_id, TrainingTask.is_active == True).first()
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    p = _get_progress(db, task_id, _user.id)
    note = (payload.get("note") or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="请填写完成说明")
    if t.required_target:
        cutoff = datetime.utcnow() - timedelta(days=VISIT_WINDOW_DAYS)
        visited = db.query(TrainingModuleVisit).filter(
            TrainingModuleVisit.user_id == _user.id,
            TrainingModuleVisit.module_path == t.required_target,
            TrainingModuleVisit.visited_at >= cutoff,
        ).first()
        if not visited:
            raise HTTPException(status_code=400, detail={
                "message": f"该任务要求先在关联模块「{t.category}」中实际操作后才能提交,请先进入该页面完成操作",
                "target": t.required_target,
                "module": t.category,
            })
    if p is None:
        p = TrainingTaskProgress(task_id=task_id, user_id=_user.id, username=_user.username)
        db.add(p)
    p.status = "submitted"
    p.submit_note = note
    p.review_note = None
    p.reviewed_by = None
    p.submitted_at = datetime.utcnow()
    p.reviewed_at = None
    db.commit()
    return {"message": "已提交,等待管理员审核"}


@router.post("/progress/{progress_id}/review")
def review_progress(progress_id: int, payload: dict = Body(...), _admin=Depends(require_admin), db: Session = Depends(get_db)):
    p = db.query(TrainingTaskProgress).get(progress_id)
    if not p:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    action = payload.get("action")
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="审核动作必须是 approve/reject")
    p.status = "approved" if action == "approve" else "rejected"
    p.review_note = (payload.get("note") or "").strip()
    p.reviewed_by = _admin.username
    p.reviewed_at = datetime.utcnow()
    db.commit()
    return {"message": "已通过" if action == "approve" else "已驳回"}
