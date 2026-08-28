"""AI endpoints: weekly report generation, risk analysis, project diagnosis, Q&A."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.ai_service import (
    generate_weekly_report, analyze_risk, diagnose_project, chat_about_projects,
    load_config, save_config,
)
from backend_v2.models import Project, Milestone, RiskIssue
from backend_v2.schemas import AIChatRequest

router = APIRouter(prefix="/api/ai", tags=["AI"])


@router.get("/config")
def get_ai_config(_user=Depends(get_current_user)):
    cfg = load_config()
    return {k: v for k, v in cfg.items() if k != "api_key"}


@router.put("/config")
def update_ai_config(data: dict, _user=Depends(get_current_user)):
    save_config(data)
    return {"message": "AI配置已更新"}


@router.post("/weekly-report")
async def ai_weekly_report(data: dict, _user=Depends(get_current_user)):
    """Generate weekly report content. Send {project_name, lines: [{line, progress, status, next_plan}]}."""
    return {"content": await generate_weekly_report(
        data.get("project_name", ""), data.get("lines", []))}


@router.post("/analyze-risk")
async def ai_analyze_risk(data: dict, _user=Depends(get_current_user)):
    """Analyze a risk item. Send {title, description, project_context}."""
    return {"content": await analyze_risk(
        data.get("title", ""), data.get("description", ""), data.get("project_context", ""))}


@router.get("/diagnose/{project_id}")
async def ai_diagnose(project_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """AI project health diagnosis."""
    result = db.execute(
        select(Project).where(Project.id == project_id, Project.is_active == True)
        .options(selectinload(Project.current_phase), selectinload(Project.milestones), selectinload(Project.risks))
    )
    p = result.scalars().one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    project_data = {
        "name": p.name, "code": p.code, "phase": p.current_phase.name if p.current_phase else None,
        "completion_pct": p.completion_pct or 0, "status": p.overall_status,
        "planned_end_date": p.planned_end_date.isoformat() if p.planned_end_date else None,
        "milestones": [{"name": m.name, "planned_date": m.planned_date.isoformat() if m.planned_date else None,
                         "status": m.status} for m in (p.milestones or [])[:15]],
        "risks": [{"title": r.title, "severity": r.severity, "status": r.status}
                  for r in (p.risks or []) if r.status in ("open", "in_progress")][:10],
    }
    return {"content": await diagnose_project(project_data)}


@router.post("/chat")
async def ai_chat(data: AIChatRequest, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """AI chat with mode support: auto/project/general."""
    from backend_v2.ai_service import _call_llm, load_config

    # Determine mode
    mode = data.mode
    if mode == "auto":
        proj_keywords = ['项目','风险','里程碑','周报','进度','阶段','客户','合同','需求','任务','变更','交付','电机']
        mode = "project" if any(k in data.question for k in proj_keywords) else "general"

    if mode == "general":
        cfg = load_config()
        messages = [
            {"role": "system", "content": "你是一个智能AI助手，可以回答各类问题。请用中文回复，简洁专业。"},
            {"role": "user", "content": data.question},
        ]
        return {"reply": await _call_llm(messages)}

    # Project mode: gather context
    result = db.execute(
        select(Project).where(Project.is_active == True)
        .options(selectinload(Project.current_phase), selectinload(Project.client)).limit(12)
    )
    projects = result.scalars().all()
    context = "\n".join([
        f"项目: {p.name}({p.code}) 阶段={p.current_phase.name if p.current_phase else '?'} "
        f"状态={p.overall_status} 完成率={p.completion_pct}% "
        f"客户={p.client.name if p.client else '?'} "
        f"合同额={p.contract_amount or 0}万 截止={p.planned_end_date}"
        for p in projects
    ])
    return {"reply": await chat_about_projects(data.question, context)}
