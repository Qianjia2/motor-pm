# 电机项目管理平台 (motor-pm)

电机系统设计项目管理系统 v2.0 — FastAPI + Vue3，前后端分离。

## 运行

- 启动：`start_all.bat`；手动 `python run_v2.py` → http://localhost:5002
- 账号：admin / admin123；健康检查 `/api/health`，Swagger `/docs`

## 技术栈

- 后端：FastAPI + SQLAlchemy 2.0，SQLite（`data/motor_pm_v2.db`）；改模型后在 `database.py::_ensure_columns` 加 ALTER 补列
- 前端：Vue3 + Vite（`frontend/`），改前端后 `npm run build`（产物在 `frontend/dist`，backend 静态挂载）
- v1（`backend/`）已废弃，改动一律基于 `backend_v2/`

## 基础设施

- `server_watchdog.py` — 守护进程；改后端后 kill 5002 进程即自动重启新代码（约 1-2 分钟）
- `auto_backup.py` — 每 4 小时备份到 NAS
- `routes/` 约 37 个模块：projects/tasks/milestones/risks/gate_reviews/bom/my_work/knowledge/ai/report_gen/dashboard 等

## 常见操作

- 改后端：编辑 `backend_v2/`，kill 5002 等 watchdog 重启
- 改前端：`frontend/src`，开发 `npm run dev`，上线 `npm run build`
- 注意：本机有文件夹加密软件（effsoftecrypt），加密后的文件对 AI 不可读；不要用复制/cp 制作 PDF 副本（会带密文导致上传解析失败），须 Python 重写或 WPS 另存为
