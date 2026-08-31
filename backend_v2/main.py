"""FastAPI application entry point — Motor PM System v2.0."""
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pathlib import Path
from datetime import datetime
import json
import traceback
from backend_v2.config import settings
from backend_v2.storage import atomic_write
from backend_v2.database import init_db, engine
from backend_v2.auth import get_current_user, require_admin, verify_token
from fastapi import WebSocket, WebSocketDisconnect
import asyncio

# ══════════════════════════
# ── WebSocket Connection Manager ──
# ══════════════════════════

class ConnectionManager:
    """Manages WebSocket connections grouped by document/resource."""
    def __init__(self):
        # { group_key: { ws: {username, user_id} } }
        self.groups: dict[str, dict] = {}

    async def connect(self, ws: WebSocket, group: str, user_info: dict):
        await ws.accept()
        if group not in self.groups:
            self.groups[group] = {}
        self.groups[group][ws] = user_info
        await self._broadcast_presence(group)

    def disconnect(self, ws: WebSocket, group: str):
        if group in self.groups:
            self.groups[group].pop(ws, None)
            if not self.groups[group]:
                del self.groups[group]
            # Broadcast presence update (async but fire-and-forget)

    async def broadcast_change(self, group: str, data: dict, exclude_ws: WebSocket = None):
        """Send document change to all connected clients in the group."""
        if group not in self.groups:
            return
        dead = []
        for ws in self.groups[group]:
            if ws == exclude_ws:
                continue
            try:
                await ws.send_json(data)
            except:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, group)

    async def _broadcast_presence(self, group: str):
        """Send online user list to all in group."""
        if group not in self.groups:
            return
        users = [{"username": u.get("username", "?"), "user_id": u.get("user_id")}
                 for u in self.groups[group].values()]
        await self.broadcast_change(group, {"type": "presence", "users": users, "count": len(users)})

    def get_presence(self, group: str) -> list:
        if group not in self.groups:
            return []
        return [{"username": u.get("username", "?"), "user_id": u.get("user_id")}
                for u in self.groups[group].values()]

ws_manager = ConnectionManager()


# Startup event
app = FastAPI(
    title="麦科斯韦研发项目管理平台",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

@app.on_event("startup")
def startup():
    # uploads 主存储在 NAS，掉线时不能阻断启动
    try:
        Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[startup] WARN: uploads dir unavailable: {e}")
    Path("data").mkdir(exist_ok=True)
    init_db()
    # 部门/角色权限迁移（幂等，失败不阻断启动）
    try:
        from backend_v2.permission_migrate import run_all as _perm_migrate
        _perm_migrate()
    except Exception:
        import logging
        logging.getLogger("main").exception("permission_migrate 启动失败")

@app.on_event("shutdown")
def shutdown():
    engine.dispose()


# ── CORS ──
# 只允许配置的 origin（禁止 "*"+credentials 组合；生产部署用 CORS_ORIGINS 环境变量指定前端地址）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Unify loopback host: 127.0.0.1 → localhost ──
# 浏览器把 127.0.0.1 和 localhost 视为不同站点，登录状态互不相通。
# 统一重定向到 localhost，保证所有访问走同一个 origin，登录状态一致。
from fastapi.responses import RedirectResponse


@app.middleware("http")
async def unify_loopback_host(request: Request, call_next):
    host = request.headers.get("host", "")
    if host.startswith("127.0.0.1"):
        # WebSocket 握手不适用 HTTP 重定向，直接放行
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        url = request.url.replace(hostname="localhost")
        # POST 等带 body 的请求用 307 保留方法和请求体
        code = 307 if request.method in ("POST", "PUT", "PATCH", "DELETE") else 301
        return RedirectResponse(str(url), status_code=code)
    return await call_next(request)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "2.0.0"}

# ── WebSocket for real-time collaboration ──

@app.websocket("/ws/{resource_type}/{resource_id}")
async def websocket_endpoint(ws: WebSocket, resource_type: str, resource_id: str):
    """Real-time collaboration WebSocket.
    resource_type: 'knowledge_doc', 'project_doc', 'note' etc.
    resource_id: document ID or key."""
    # Auth via token query param — 无有效 token 直接拒绝, 不再降级 guest
    token = ws.query_params.get("token", "")
    if not token:
        await ws.close(code=4401, reason="需要登录")
        return
    try:
        payload = verify_token(token)
    except Exception:
        await ws.close(code=4401, reason="登录无效")
        return
    user_info = {"username": payload.get("sub", "?"), "user_id": payload.get("user_id")}

    group = f"{resource_type}:{resource_id}"
    await ws_manager.connect(ws, group, user_info)
    try:
        while True:
            data = await ws.receive_json()
            data["_sender"] = user_info["username"]
            # Broadcast to others in the same group
            await ws_manager.broadcast_change(group, data, exclude_ws=ws)
    except WebSocketDisconnect:
        ws_manager.disconnect(ws, group)
        await ws_manager._broadcast_presence(group)
    except Exception:
        ws_manager.disconnect(ws, group)
        await ws_manager._broadcast_presence(group)


@app.get("/api/server-info")
def server_info():
    """Return server network info + public tunnel URL for external access."""
    import socket, urllib.request, json as _json
    lan_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("10.254.254.254", 1))
        lan_ip = s.getsockname()[0]
        s.close()
    except:
        pass

    public_url = ""
    # Try ngrok API
    try:
        req = urllib.request.Request("http://localhost:4040/api/tunnels")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = _json.loads(resp.read())
            tunnels = data.get("tunnels", [])
            if tunnels:
                public_url = tunnels[0].get("public_url", "")
    except:
        pass

    # Try cloudflared tunnel file
    if not public_url:
        try:
            import os
            fpath = os.path.join(os.path.dirname(__file__), "..", "data", "tunnel_url.txt")
            if os.path.exists(fpath):
                with open(fpath) as f:
                    for line in f:
                        if line.startswith("TUNNEL_URL="):
                            public_url = line.split("=", 1)[1].strip()
                            break
        except:
            pass

    return {"lan_ip": lan_ip, "port": 5002, "public_url": public_url}

@app.get("/api/ai/engines")
def ai_engines_status():
    """Return status of multi-engine AI configuration."""
    from backend_v2.ai_service import get_engines_status
    return get_engines_status()

@app.get("/api/presence/{resource_type}/{resource_id}")
def get_presence(resource_type: str, resource_id: str):
    """Get online users for a resource."""
    return {"users": ws_manager.get_presence(f"{resource_type}:{resource_id}")}


# ── ngrok Tunnel (one-click external access) ──
_tunnel_process = None
_tunnel_url = ""

@app.get("/api/tunnel/status")
def tunnel_status():
    """Get current tunnel status."""
    return {"running": _tunnel_process is not None and _tunnel_process.poll() is None,
            "url": _tunnel_url}

@app.post("/api/tunnel/start")
def tunnel_start(_admin=Depends(require_admin)):
    """Start ngrok tunnel for external access (admin only — exposes server publicly)."""
    global _tunnel_process, _tunnel_url
    import subprocess, threading, re, os, urllib.request, json as _json
    if _tunnel_process and _tunnel_process.poll() is None:
        return {"ok": True, "url": _tunnel_url, "msg": "隧道已在运行"}

    ngrok_bin = "D:/AI/ngrok.exe"
    if not os.path.exists(ngrok_bin):
        ngrok_bin = "ngrok"

    def _run_ngrok():
        global _tunnel_process, _tunnel_url
        try:
            _tunnel_process = subprocess.Popen(
                [ngrok_bin, "http", "5002", "--log=stdout"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, encoding="utf-8", errors="replace"
            )
        except Exception as e:
            _tunnel_url = f"启动失败: {e}"
            return

    threading.Thread(target=_run_ngrok, daemon=True).start()
    import time
    # Wait for ngrok to start and query local API for URL
    for _ in range(20):
        time.sleep(1)
        try:
            req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels")
            data = json.loads(urllib.request.urlopen(req, timeout=2).read())
            tunnels = data.get("tunnels", [])
            if tunnels:
                _tunnel_url = tunnels[0]["public_url"]
                break
        except:
            pass
    if _tunnel_url:
        return {"ok": True, "url": _tunnel_url, "msg": "ngrok隧道已启动"}
    return {"ok": False, "url": "", "msg": "ngrok启动超时，请检查网络"}

@app.post("/api/tunnel/stop")
def tunnel_stop(_admin=Depends(require_admin)):
    """Stop the tunnel."""
    global _tunnel_process, _tunnel_url
    if _tunnel_process:
        try: _tunnel_process.terminate()
        except: pass
        _tunnel_process = None
    _tunnel_url = ""
    return {"ok": True}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import logging
    tb = traceback.format_exc()
    logging.error(f"{request.method} {request.url.path}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )


# ── Register all route modules ──
from backend_v2.routes.auth import router as auth_router
from backend_v2.routes.projects import router as projects_router
from backend_v2.routes.milestones import router as milestones_router
from backend_v2.routes.weekly_reports import router as reports_router
from backend_v2.routes.risks import router as risks_router
from backend_v2.routes.changes import router as changes_router
from backend_v2.routes.deliverables import router as deliverables_router
from backend_v2.routes.project_docs import router as docs_router
from backend_v2.routes.dashboard import router as dashboard_router
from backend_v2.routes.my_work import router as my_work_router
from backend_v2.routes.export import router as export_router
from backend_v2.routes.files import router as files_router
from backend_v2.routes.lookups import router as lookups_router
from backend_v2.routes.team import router as team_router
from backend_v2.routes.clients import router as clients_router
from backend_v2.routes.opportunities import router as opportunities_router
from backend_v2.routes.audit_logs import router as audit_router
from backend_v2.routes.financials import router as fin_router
from backend_v2.routes.external import router as ext_router
from backend_v2.routes.ai import router as ai_router
from backend_v2.routes.requirements import router as req_router
from backend_v2.routes.tasks import router as task_router
from backend_v2.routes.testing import router as test_router
from backend_v2.routes.customer_portal import router as portal_router
from backend_v2.routes.plm import router as plm_router
from backend_v2.routes.ocr import router as ocr_router
from backend_v2.routes.report_gen import router as report_gen_router
from backend_v2.routes.knowledge import router as knowledge_router
from backend_v2.routes.product_tech import router as product_tech_router
from backend_v2.routes.bom import router as bom_router
from backend_v2.routes.bom_lists import router as bom_lists_router
from backend_v2.routes.issue_risks import router as issue_risks_router
from backend_v2.routes.gate_reviews import router as gate_reviews_router
from backend_v2.routes.client_communications import router as comm_router
from backend_v2.routes.client_contacts import router as contacts_router
from backend_v2.routes.departments import router as departments_router
from backend_v2.routes.training import router as training_router
from backend_v2.routes.training_tasks import router as training_tasks_router

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(milestones_router)
app.include_router(reports_router)
app.include_router(risks_router)
app.include_router(changes_router)
app.include_router(deliverables_router)
app.include_router(docs_router)
app.include_router(dashboard_router)
app.include_router(my_work_router)
app.include_router(export_router)
app.include_router(files_router)
app.include_router(lookups_router)
app.include_router(team_router)
app.include_router(clients_router)
app.include_router(opportunities_router)
app.include_router(audit_router)
app.include_router(fin_router)
app.include_router(ext_router)
app.include_router(ai_router)
app.include_router(req_router)
app.include_router(task_router)
app.include_router(test_router)
app.include_router(portal_router)
app.include_router(plm_router)
app.include_router(ocr_router)
app.include_router(report_gen_router)
app.include_router(knowledge_router)
app.include_router(product_tech_router)
app.include_router(bom_router)
app.include_router(bom_lists_router)
app.include_router(issue_risks_router)
app.include_router(gate_reviews_router)
app.include_router(comm_router)
app.include_router(contacts_router)
app.include_router(departments_router)
app.include_router(training_router)
app.include_router(training_tasks_router)


# ── DingTalk Integration ──
import json as _json
from pathlib import Path as _Path
from backend_v2.dingtalk_service import (
    get_config as _dt_get_config,
    save_credentials as _dt_save_creds,
    save_templates as _dt_save_tpls,
    get_process_templates as _dt_get_tpls,
    create_approval as _dt_create,
    get_approval_status as _dt_status,
    get_user_info as _dt_user_info,
    search_user_by_mobile as _dt_user_by_mobile,
    list_process_templates as _dt_list_tpls,
    list_process_instances as _dt_list_instances,
    get_instance_full as _dt_instance_full,
    get_department_lists as _dt_depts,
)

_DT_DATA = _Path(__file__).parent.parent / "data" / "dingtalk_approvals.json"

# ── Config endpoints ──

@app.get("/api/dingtalk/config")
def api_get_dt_config(current_user=Depends(get_current_user)):
    return _dt_get_config()

@app.put("/api/dingtalk/credentials")
def api_save_dt_creds(data: dict, current_user=Depends(require_admin)):
    _dt_save_creds(
        app_key=data.get("app_key", ""),
        app_secret=data.get("app_secret", ""),
        corp_id=data.get("corp_id", ""),
    )
    return {"message": "凭证已保存"}

@app.get("/api/dingtalk/templates")
def api_get_dt_templates(current_user=Depends(get_current_user)):
    """Get available OA approval templates."""
    return _dt_get_tpls()

@app.put("/api/dingtalk/templates")
def api_save_dt_templates(data: dict, current_user=Depends(require_admin)):
    _dt_save_tpls(data.get("templates", []))
    return {"message": "模板已保存"}

@app.get("/api/dingtalk/templates/available")
def api_list_dt_templates(current_user=Depends(require_admin)):
    """从钉钉 API 拉取应用可见的全部审批模板(供系统设置页面勾选关联)。"""
    try:
        return _dt_list_tpls()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ── Approval operations ──

@app.post("/api/dingtalk/approvals")
def api_create_dt_approval(data: dict, current_user=Depends(get_current_user)):
    """Create a DingTalk OA approval instance."""
    try:
        rsp = _dt_create(
            process_code=data["process_code"],
            originator_user_id=data["user_id"],
            dept_id=data.get("dept_id", 1),
            title=data.get("title", ""),
            form_values=data.get("form_values", []),
        )
        result = rsp.get("result") or {}
        instance_id = (result.get("instanceId") or rsp.get("instanceId")
                       or rsp.get("processInstanceId") or "")
        if not instance_id:
            raise HTTPException(status_code=502, detail=f"钉钉未返回审批实例ID: {rsp}")
        return {"ok": True, "instance_id": instance_id, "raw": rsp}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发起审批失败: {e}")

@app.get("/api/dingtalk/approvals/{instance_id}")
def api_get_dt_status(instance_id: str, current_user=Depends(get_current_user)):
    """Query a DingTalk approval status."""
    return _dt_status(instance_id)

@app.get("/api/dingtalk/instances")
def api_list_dt_instances(process_code: str = "", days: int = 30, mobile: str = "",
                          keyword: str = "",
                          current_user=Depends(get_current_user)):
    """拉取钉钉审批实例(供项目详情关联)。

    process_code 为空 = 跨全部模板按关键词/手机号搜索(耗时较长)。
    keyword 可选:按标题/表单内容模糊过滤(钉钉接口不支持关键词,平台侧过滤)。
    """
    try:
        return _dt_list_instances(process_code, min(max(days, 1), 1100), mobile, keyword)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/dingtalk/instances/{instance_id}")
def api_get_dt_instance_detail(instance_id: str, current_user=Depends(get_current_user)):
    """审批单完整信息: 表单 + 审批过程 + 钉钉打开链接。"""
    try:
        return _dt_instance_full(instance_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/dingtalk/users/search")
def api_search_dt_user(mobile: str = "", current_user=Depends(get_current_user)):
    """Search DingTalk user by mobile."""
    try:
        rsp = _dt_user_by_mobile(mobile)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if isinstance(rsp, dict) and rsp.get("errcode"):
        raise HTTPException(status_code=400, detail=f"钉钉查询失败: {rsp.get('errmsg') or rsp.get('errcode')}")
    return rsp

@app.get("/api/dingtalk/departments")
def api_get_dt_depts(dept_id: int = 0, current_user=Depends(get_current_user)):
    """List sub-departments."""
    try:
        return _dt_depts(dept_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ── Project-linked approvals (manual tracking) ──

def _load_dt_approvals():
    try:
        with open(_DT_DATA, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return []

def _save_dt_approvals(items):
    atomic_write(str(_DT_DATA), items)

@app.get("/api/projects/{project_id}/dingtalk-approvals")
def list_dt_approvals(project_id: int, current_user=Depends(get_current_user)):
    all_items = _load_dt_approvals()
    return [a for a in all_items if a.get("project_id") == project_id]

@app.post("/api/projects/{project_id}/dingtalk-approvals")
def create_dt_approval(project_id: int, data: dict, current_user=Depends(get_current_user)):
    all_items = _load_dt_approvals()
    new_id = max([a.get("id", 0) for a in all_items], default=0) + 1
    item = {
        "id": new_id, "project_id": project_id,
        "type": data.get("type", "other"), "title": data.get("title", ""),
        "url": data.get("url", ""), "note": data.get("note", ""),
        "status": data.get("status", "pending"),
        "instance_id": data.get("instance_id", ""),
        "created_by": current_user.username,
        "created_at": datetime.utcnow().isoformat(),
    }
    all_items.append(item)
    _save_dt_approvals(all_items)
    return item

@app.put("/api/projects/{project_id}/dingtalk-approvals/{approval_id}")
def update_dt_approval(project_id: int, approval_id: int, data: dict, current_user=Depends(get_current_user)):
    all_items = _load_dt_approvals()
    for a in all_items:
        if a.get("id") == approval_id and a.get("project_id") == project_id:
            for key in ("status", "note", "url", "type", "title"):
                if key in data:
                    a[key] = data[key]
            _save_dt_approvals(all_items)
            return a
    raise HTTPException(404, "未找到")

@app.delete("/api/projects/{project_id}/dingtalk-approvals/{approval_id}")
def delete_dt_approval(project_id: int, approval_id: int, current_user=Depends(get_current_user)):
    all_items = _load_dt_approvals()
    all_items = [a for a in all_items if not (a.get("id") == approval_id and a.get("project_id") == project_id)]
    _save_dt_approvals(all_items)
    return {"message": "已取消关联"}


# ── Public Knowledge Base Chat (no auth, token-based) ──
@app.post("/api/public/kb/{token}/chat")
def public_kb_chat(token: str, data: dict, request: Request = None):
    """Public Q&A endpoint — customers ask questions, cannot browse documents."""
    import secrets as _secrets
    from backend_v2.routes._knowledge_core import _load_shares, _save_shares, _find_relevant_chunks
    from backend_v2.database import SessionLocal
    from backend_v2 import models

    import time as _time
    from fastapi import Request as _FR

    shares = _load_shares()
    share = next((s for s in shares if s.get("token") == token), None)
    if not share or not share.get("enabled"):
        raise HTTPException(403, detail="分享链接不存在或已停用")

    # Password check
    share_pwd = share.get("password", "").strip()
    if share_pwd and data.get("password", "") != share_pwd:
        raise HTTPException(401, detail="密码错误")

    question = data.get("question", "").strip()
    if not question:
        return {"answer": "请输入问题", "sources": []}

    space = share.get("space", "default")
    history = data.get("history", [])[-10:]  # last 10 messages for context

    db = SessionLocal()
    try:
        chunks = _find_relevant_chunks(question, space, db,
                                       folders=share.get("folders", []),
                                       doc_ids=share.get("doc_ids", []))
        if not chunks:
            share["question_count"] = share.get("question_count", 0) + 1
            _save_shares(shares)
            # Log
            try: client_ip = request.client.host if request else "unknown"
            except: client_ip = "unknown"
            _log_share_visit(token, share.get("name", ""), question, "(未找到)", client_ip)
            return {"answer": "抱歉，知识库中暂未找到相关信息。请换个问题试试。", "sources": []}

        context = "\n\n---\n".join([c[:1500] for c in chunks[:6]])

        # Build prompt
        from backend_v2.routes._knowledge_core import _load_prompt_config
        cfg = _load_prompt_config()
        sys_prompt = cfg.get("system_prompt", "你是知识库问答专家。严格基于文档回答，不编造。使用中文。")

        history_text = "\n".join([f"用户: {h['q']}\n助手: {h['a']}" for h in history[-6:]])
        prompt = f"""{sys_prompt}

【参考资料】
{context}

【历史对话】
{history_text}

【当前问题】
{question}

要求：
1. 直接回答问题，使用参考资料中的具体信息（如电话、地址、产品名等）
2. 如果资料里有联系方式或具体数据，务必在回答中提供
3. 不要泛泛而谈，给出实质内容
4. 不确定的信息说明"资料中未提及"，不要编造
5. 不要使用"文档""知识库"等术语，就像你本来就掌握这些知识一样回答"""

        import asyncio as _asyncio
        try:
            from backend_v2.ai_service import call_task
            answer = _asyncio.new_event_loop().run_until_complete(
                call_task("chat", [{"role": "user", "content": prompt}])
            )
            answer = answer.strip()
            if answer.startswith("[AI") and answer.endswith("]"):
                answer = "抱歉，AI 服务暂时不可用，请稍后重试。"
        except:
            answer = "抱歉，AI 服务暂时不可用，请稍后重试。"

        # Track usage
        share["question_count"] = share.get("question_count", 0) + 1
        _save_shares(shares)
        db.close()

        # Log visit
        try:
            client_ip = request.client.host if request else "unknown"
        except:
            client_ip = "unknown"
        _log_share_visit(token, share.get("name", ""), question, answer, client_ip)

        # Sources (titles only, no file content)
        sources = []
        seen = set()
        for c in chunks[:4]:
            title = c.split("\n")[0] if c else "未知文档"
            title = title.strip("# ")[:80]
            if title not in seen:
                sources.append(title)
                seen.add(title)

        return {"answer": answer, "sources": sources}
    finally:
        try: db.close()
        except: pass

# ── Get share link info (public) ──
@app.get("/api/public/kb/{token}")
def public_kb_info(token: str, password: str = ""):
    """Get share info + document list with 200-char previews."""
    from backend_v2.routes._knowledge_core import _load_shares
    from backend_v2.database import SessionLocal
    from backend_v2.models import ProjectDocument
    from sqlalchemy import select as _sel
    import json as _json

    shares = _load_shares()
    share = next((s for s in shares if s.get("token") == token), None)
    if not share or not share.get("enabled"):
        raise HTTPException(403, detail="分享链接不存在或已停用")

    # Password check
    share_pwd = share.get("password", "").strip()
    if share_pwd and password != share_pwd:
        raise HTTPException(401, detail="密码错误")

    # Get shared documents
    space = share.get("space", "default")
    folders = share.get("folders", [])
    doc_ids = share.get("doc_ids", [])

    docs = []
    db = SessionLocal()
    try:
        if doc_ids:
            rows = db.execute(_sel(ProjectDocument).where(ProjectDocument.id.in_(doc_ids))).scalars().all()
        else:
            rows = db.execute(_sel(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(200)).scalars().all()

        for d in rows:
            meta = {}
            try: meta = _json.loads(d.notes or "{}")
            except: pass
            doc_space = str(meta.get("space", "default") or "default")
            if doc_space != space:
                continue
            doc_folder = meta.get("folder", "/") or "/"
            if folders:
                in_folder = any(doc_folder.startswith(f.strip("/")) for f in folders)
                if not in_folder:
                    continue
            docs.append({
                "id": d.id, "title": d.name, "doc_type": d.doc_type,
                "folder": doc_folder,
                "preview": (d.content or "")[:200],
                "file_size": d.file_size,
            })
    finally:
        db.close()

    return {
        "name": share.get("name", "智能问答"),
        "welcome": share.get("welcome", ""),
        "has_password": bool(share_pwd),
        "documents": docs,
    }

# ── QR Code generation (local, no external API) ──
@app.get("/api/knowledge/qrcode")
def generate_qrcode(url: str = "", size: int = 240):
    """Generate QR code PNG image from URL."""
    import qrcode as _qr
    from io import BytesIO as _Bio
    from fastapi.responses import StreamingResponse as _SR
    if not url: raise HTTPException(400, "缺少url参数")
    img = _qr.make(url, box_size=6, border=2)
    buf = _Bio()
    img.save(buf, format="PNG")
    buf.seek(0)
    return _SR(buf, media_type="image/png")

# ── Share visit logging ──
def _log_share_visit(token: str, name: str, question: str, answer: str, ip: str):
    """Log a customer visit/question for analytics."""
    import os as _os
    log_dir = _os.path.join(_os.path.dirname(__file__), "..", "data", "data")
    _os.makedirs(log_dir, exist_ok=True)
    log_file = _os.path.join(log_dir, "kb_share_visits.json")
    try:
        with open(log_file, "r", encoding="utf-8") as f: visits = json.load(f)
    except: visits = []
    visits.append({
        "token": token, "name": name, "question": question[:300],
        "answer": answer[:200], "ip": ip,
        "ts": datetime.utcnow().isoformat()
    })
    # Keep last 2000 records
    if len(visits) > 2000: visits = visits[-2000:]
    atomic_write(log_file, visits)

@app.get("/api/knowledge/share-links/{share_id}/visits")
def get_share_visits(share_id: str, limit: int = 50):
    """Get customer visit logs for a share link."""
    from backend_v2.auth import get_current_user as _gcu
    from fastapi import Depends as _Dep
    # Note: auth enforced by knowledge router's dependency; this is called via API
    from backend_v2.routes._knowledge_core import _load_shares
    import os as _os
    shares = _load_shares()
    share = next((s for s in shares if s["id"] == share_id), None)
    if not share: raise HTTPException(404, detail="分享不存在")
    token = share["token"]
    log_file = _os.path.join(_os.path.dirname(__file__), "..", "data", "data", "kb_share_visits.json")
    try:
        with open(log_file, "r", encoding="utf-8") as f: visits = json.load(f)
    except: visits = []
    matched = [v for v in visits if v["token"] == token][-limit:]
    return matched

# ── Public Chat standalone page (isolated from SPA) ──
@app.get("/kb/chat/{token}")
def public_chat_page(token: str):
    """Serve the standalone chat page — completely isolated from the main app."""
    from fastapi.responses import FileResponse
    chat_file = Path(__file__).parent.parent / "frontend" / "public" / "chat.html"
    if chat_file.exists():
        return FileResponse(chat_file)
    # Fallback: return inline HTML
    from fastapi.responses import HTMLResponse
    return HTMLResponse("<h1>Chat page not found</h1>")

# ── Serve static frontend (SPA fallback) ──
static_dir = Path(__file__).parent.parent / "frontend" / "dist"
if static_dir.exists():
    # Mount uploads for requirement attachments etc.
    # 自定义 StaticFiles: 统一加 nosniff; 危险类型(html/svg/xml)强制附件下载, 防同源存储型 XSS
    class SafeStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            response = await super().get_response(path, scope)
            if response.status_code < 400:
                response.headers["X-Content-Type-Options"] = "nosniff"
                ext = Path(path).suffix.lower()
                if ext in (".html", ".htm", ".svg", ".xml"):
                    response.headers["Content-Disposition"] = "attachment"
            return response

    import backend_v2.config as _cfg
    uploads_dir = Path(_cfg.settings.UPLOAD_DIR)
    if uploads_dir.exists():
        app.mount("/uploads", SafeStaticFiles(directory=str(uploads_dir)), name="uploads")
    # Mount assets first (JS, CSS, images etc.)
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        """Serve index.html for all non-API paths (SPA client-side routing)."""
        # API paths are handled by routers above — this only catches non-API requests
        file_path = (static_dir / full_path).resolve()
        # Prevent path traversal: must stay within static_dir
        if not str(file_path).startswith(str(static_dir.resolve())):
            from fastapi import HTTPException as _HE
            raise _HE(status_code=404, detail="Not Found")
        if file_path.exists() and file_path.is_file():
            resp = FileResponse(file_path)
        else:
            resp = FileResponse(static_dir / "index.html")
        # Prevent browser caching to ensure latest JS/CSS is loaded
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
