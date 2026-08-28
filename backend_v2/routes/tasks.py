"""WBS Task management — tree-structured CRUD + Excel import."""
from datetime import datetime, date as date_type
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, update as up, delete as dl
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import Task, Project, TeamMember, TechnicalLine, Phase


def _fix_dates(data: dict):
    for f in ("start_date", "end_date"):
        if f in data and (data[f] == "" or data[f] is None):
            data[f] = None
        elif f in data and isinstance(data[f], str):
            try: data[f] = date_type.fromisoformat(data[f])
            except: data[f] = None

router = APIRouter(tags=["tasks"])


def task_to_dict(t):
    d = {c.name: getattr(t, c.name) for c in t.__table__.columns}
    for k in ("start_date", "end_date", "created_at"):
        d[k] = d[k].isoformat() if d.get(k) else None
    d["assignee"] = {"id": t.assignee.id, "name": t.assignee.name} if t.assignee else None
    d["line"] = {"id": t.line.id, "name": t.line.name, "short_name": t.line.short_name} if t.line else None
    d["phase"] = {"id": t.phase.id, "name": t.phase.name} if t.phase else None
    return d


def build_tree(tasks, parent_id=None):
    """Recursively build task tree."""
    children = [t for t in tasks if t.get("parent_id") == parent_id]
    children.sort(key=lambda x: (x.get("sort_order", 0), x.get("id", 0)))
    for child in children:
        child["children"] = build_tree(tasks, child["id"])
    return children


@router.get("/api/projects/{project_id}/tasks")
def list_tasks(project_id: int, flat: bool = Query(False),
                     db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = db.execute(
        select(Task).where(Task.project_id == project_id).order_by(Task.sort_order, Task.id)
    )
    tasks = [task_to_dict(t) for t in result.scalars().all()]
    if flat:
        return tasks
    return build_tree(tasks)


@router.post("/api/projects/{project_id}/tasks", status_code=201)
def create_task(project_id: int, data: dict,
                      db: Session = Depends(get_db), user=Depends(get_current_user)):
    allowed = {"name", "description", "parent_id", "assignee_id", "line_id", "phase_id",
               "start_date", "end_date", "progress_pct", "status", "priority", "sort_order", "milestone_id"}
    vals = {k: v for k, v in data.items() if k in allowed}
    _fix_dates(vals)
    t = Task(project_id=project_id, created_at=datetime.utcnow(), **vals)
    db.add(t)
    db.commit()
    db.refresh(t)
    return task_to_dict(t)


@router.put("/api/tasks/{task_id}")
def update_task(task_id: int, data: dict,
                      db: Session = Depends(get_db), user=Depends(get_current_user)):
    from sqlalchemy import update as up
    result = db.execute(select(Task).where(Task.id == task_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    allowed = {"name", "description", "parent_id", "assignee_id", "line_id", "phase_id",
               "start_date", "end_date", "progress_pct", "status", "priority", "sort_order", "milestone_id"}
    upd = {k: v for k, v in data.items() if k in allowed}
    _fix_dates(upd)
    if upd:
        db.execute(up(Task).where(Task.id == task_id).values(**upd))
        db.commit()
    return {"message": "已更新"}


@router.delete("/api/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import delete as dl
    result = db.execute(select(Task).where(Task.id == task_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    # Re-parent children to parent
    db.execute(up(Task).where(Task.parent_id == task_id).values(parent_id=t.parent_id))
    db.execute(dl(Task).where(Task.id == task_id))
    db.commit()
    return {"message": "已删除"}


@router.post("/api/projects/{project_id}/tasks/import")
async def import_tasks(project_id: int, file: UploadFile = File(...),
                       db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Import WBS tasks from Excel. Supports .xlsx / .xls.
    Headers are auto-detected. Common patterns:
    任务名称/WBS/工作内容/task, 父任务/上级, 负责人/责任人/assignee,
    开始日期/计划开始, 结束日期/计划结束, 进度/%, 状态, 技术线, 阶段
    """
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("xlsx", "xls"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 文件")

    import openpyxl
    wb = openpyxl.load_workbook(BytesIO(await file.read()))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Excel 至少需要表头+一行数据")

    headers = [str(h).strip().lower().replace('\n','').replace(' ','') if h else '' for h in rows[0]]
    # Map columns
    col_map = {}
    for i, h in enumerate(headers):
        hl = h.lower()
        if any(k in hl for k in ('任务名称', '任务名', 'wbs', '工作内容', 'task', 'name', '标题')):
            col_map['name'] = i
        elif any(k in hl for k in ('父任务', '上级', '父级', 'parent')):
            col_map['parent'] = i
        elif any(k in hl for k in ('负责人', '责任人', '执行人', 'assignee', 'owner')):
            col_map['assignee'] = i
        elif any(k in hl for k in ('技术线', '专业', 'line', 'discipline')):
            col_map['line'] = i
        elif any(k in hl for k in ('阶段', 'phase')):
            col_map['phase'] = i
        elif any(k in hl for k in ('开始日期', '计划开始', 'start')):
            col_map['start'] = i
        elif any(k in hl for k in ('结束日期', '计划结束', '截止', 'end', 'deadline', 'due')):
            col_map['end'] = i
        elif any(k in hl for k in ('进度', '完成', 'progress', '%', 'pct')):
            col_map['progress'] = i
        elif any(k in hl for k in ('状态', 'status')):
            col_map['status'] = i

    # Pre-load lookup tables
    members = {m.name.lower().strip(): m.id for m in (db.execute(select(TeamMember))).scalars().all()}
    lines = {l.name.lower().strip(): l.id for l in (db.execute(select(TechnicalLine))).scalars().all()}
    lines.update({(l.short_name or '').lower().strip(): l.id for l in (db.execute(select(TechnicalLine))).scalars().all()})
    phases = {p.name.lower().strip(): p.id for p in (db.execute(select(Phase))).scalars().all()}

    status_map = {
        '待开始': 'pending', '未开始': 'pending', 'pending': 'pending',
        '进行中': 'in_progress', '执行中': 'in_progress', 'inprogress': 'in_progress',
        '已完成': 'completed', '完成': 'completed', 'completed': 'completed',
        '阻塞': 'blocked', '受阻': 'blocked', 'blocked': 'blocked',
    }

    created = 0
    parent_names = {}  # track parent name → task id mapping for hierarchy

    for row in rows[1:]:
        if not row or all(c is None or str(c).strip() == '' for c in row):
            continue
        vals = [str(c).strip() if c is not None else '' for c in row]

        name = vals[col_map['name']] if 'name' in col_map and col_map['name'] < len(vals) else ''
        if not name:
            continue

        task_data = {'project_id': project_id, 'status': 'pending'}
        task_data['name'] = name

        # Parent task
        parent_name = ''
        if 'parent' in col_map and col_map['parent'] < len(vals):
            parent_name = vals[col_map['parent']].strip()
            if parent_name and parent_name in parent_names:
                task_data['parent_id'] = parent_names[parent_name]

        # Assignee
        if 'assignee' in col_map and col_map['assignee'] < len(vals):
            assignee_name = vals[col_map['assignee']].strip().lower()
            if assignee_name in members:
                task_data['assignee_id'] = members[assignee_name]

        # Technical line
        if 'line' in col_map and col_map['line'] < len(vals):
            line_name = vals[col_map['line']].strip().lower()
            if line_name in lines:
                task_data['line_id'] = lines[line_name]

        # Phase
        if 'phase' in col_map and col_map['phase'] < len(vals):
            phase_name = vals[col_map['phase']].strip().lower()
            if phase_name in phases:
                task_data['phase_id'] = phases[phase_name]

        # Dates
        if 'start' in col_map and col_map['start'] < len(vals):
            try:
                v = vals[col_map['start']]
                task_data['start_date'] = date_type.fromisoformat(v) if v else None
            except Exception:
                pass
        if 'end' in col_map and col_map['end'] < len(vals):
            try:
                v = vals[col_map['end']]
                task_data['end_date'] = date_type.fromisoformat(v) if v else None
            except Exception:
                pass

        # Progress
        if 'progress' in col_map and col_map['progress'] < len(vals):
            try:
                p = vals[col_map['progress']].replace('%', '').strip()
                task_data['progress_pct'] = int(float(p))
            except Exception:
                pass

        # Status
        if 'status' in col_map and col_map['status'] < len(vals):
            s = vals[col_map['status']].strip().lower()
            if s in status_map:
                task_data['status'] = status_map[s]

        t = Task(created_at=datetime.utcnow(), **task_data)
        db.add(t)
        db.flush()
        parent_names[name] = t.id
        created += 1

    db.commit()
    return {"message": f"成功导入 {created} 条WBS任务", "created": created}
