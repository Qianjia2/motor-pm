# 01 软件架构总览

> 描述对象：仓库 `main` 分支当前实现 + 本地线上运行实例（2026-09-08 核验）。

## 1. 系统定位

电机/项目管理平台：以**项目生命周期（立项 P0 → 样机 PP1–PP5 → 验证 → 量产）**为核心，覆盖研发进度、任务、里程碑与门禁评审、周报、BOM/图纸、测试、知识库、培训实操、钉钉审批、客户门户与商机管理的内部管理系统。自带「AI 助手」：智能问答、周报/报告自动生成、图片转报告（OCR）。

## 2. 技术栈与组件图

```
┌──────────────────────────── 单进程容器 / 单机 ────────────────────────────┐
│  Browser (桌面/移动)                                                        │
│     │ HTTPS(云端) / HTTP(内网)                                              │
│     ▼                                                                      │
│  [Nginx / Caddy] ─ 可选：云端反向代理 + TLS/域名 ──                        │
│     │ 80/443 → 127.0.0.1:5002                                              │
│     ▼                                                                      │
│  ┌─────────────────────── FastAPI (uvicorn, 端口 5002) ──────────────────┐ │
│  │  前端静态资源 (frontend/dist)                                          │ │
│  │    /            → SPA index.html（GET-only，no-cache）                 │ │
│  │    /assets/*    → Vite 构建产物                                        │ │
│  │    /uploads/*   → SafeStaticFiles（html/svg/xml 强制下载）              │ │
│  │    /kb/chat/{token} → 公开知识库分享页（免登录）                        │ │
│  │  业务 API /api/**（521 端点 / 39 模块，见 api-reference-full.md）       │ │
│  │    auth → JWT 下发/刷新 ｜ projects/tasks/milestones/gates/周报        │ │
│  │    knowledge(112) testing(26) bom(21+31) report-gen(17) …              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│     │  SQLAlchemy                                                │         │
│  data/motor_pm_v2.db (SQLite, 54 表)   data/*.json (业务配置)              │
│  data/backups/*                       uploads/ (附件/OCR/导出产物)         │
└────────────────────────────────────────────────────────────────────────────┘
     │
     ├── [Windows 本地模式] auto_backup 线程(1h→NAS UNC) + server_watchdog
     └── [云端模式] 无 watchdog；依赖 Docker restart；备份走 cron + 卷快照
```

关键架构事实：

- **前后端同源**：Vite 构建后由 FastAPI 托管静态文件，浏览器只有一个 origin（部署简化，天然规避大部分 CORS 问题）。CORS 白名单仅用于开发端口（5173/5000）或独立前端域名场景。
- **数据库为 SQLite 单文件**：写并发受单进程限制 → **生产只跑一个应用副本**，不要横向多副本（会撞写锁）。
- 静态托管含 SPA fallback：非 `/api`、非真实文件的 GET 回落 `index.html`（带路径穿越防护与 no-cache 头）。

## 3. 进程与启动链路

| 场景 | 启动方式 | 进程构成 |
|---|---|---|
| 本地/内网生产（当前线上） | `python run_v2.py` | ① watchdog 子进程（崩溃自动拉起）② auto_backup 线程（每 1h 备份到 NAS）③ uvicorn `backend_v2.main:app` 0.0.0.0:5002 |
| Docker（群晖/云端） | 镜像 CMD uvicorn | 仅 uvicorn；重启交给 `restart: unless-stopped`；日志走 stdout（`docker logs`） |
| CI（GitHub Actions） | `python -m uvicorn` + 健康轮询 | `.github/workflows/e2e.yml`：seed → 启动 → 4 套 E2E 套件 |

> 云端部署**不要**把 watchdog/auto_backup 带进容器（Docker 镜像不导入它们，见 03 文档）。

## 4. 数据存储清单

| 存储 | 位置（本地线上） | 容器内 | 内容 |
|---|---|---|---|
| SQLite 主库 | `data/motor_pm_v2.db`（约 3MB） | `/app/data/motor_pm_v2.db` | 54 张业务表 |
| 业务 JSON 配置 | `data/*.json` | `/app/data/*.json` | 见下 |
| 上传文件 | `UPLOAD_DIR`（默认 NAS UNC 路径，Windows 专用） | `/app/uploads` | 附件、文档、图纸、OCR 图片、导出产物 |
| 本地备份 | `data/backups/`、`data/backup_motor_pm_v2_*.db` | `/app/data/backups/` | 数据库定时快照 |
| NAS 异地备份 | `NAS 个人文件夹/auto_backup_<ts>/` | 不适用（云端自行配置） | db + 配置 + 元数据，保留 30 天 + 每月首日永久 |
| 日志 | `data/server.log`（run_v2 模式）+ stdout | stdout（docker logs） | 运行日志 |

`data/` 下配置类 JSON（**必须随数据卷持久化**）：

| 文件 | 用途 | 敏感 |
|---|---|---|
| `ai_config.json` | AI 引擎与路由配置 | 含第三方 API Key |
| `dingtalk_config.json` | 钉钉应用凭证、审批模板映射 | 含 app_secret |
| `dingtalk_approvals.json` | 审批发起记录缓存 | 一般 |
| `bom*.json` 等 | BOM 字典 / 物料 / 清单元数据 | — |

## 5. 模块地图（规模视角）

- **API**：521 端点 / 39 模块（完整清单见 api-reference-full.md）。体量最大：knowledge（知识库 112）、bom-lists（31）、testing（26）、lookups（23）、auth（22）、bom（21）。
- **数据表**：54 张，覆盖：用户与权限（user_auth/role/permission_role/team_member…）、项目域（project/project_member/phase/gate/里程碑/任务…）、流程域（ECN/变更/评审 action/门禁签署…）、周报、测试、培训、知识库（kb_* + 向量）、客户门户、钉钉审批（transaction）、审计（audit_log）、Webhook 等。
- **后台作业**：仅线程级（auto_backup/watchdog）；无 Celery/Redis。长任务（OCR、AI 报告）为请求内同步执行（前端 loading 等待）。

## 6. 认证与安全模型（概要，细节见 04）

- JWT 双令牌：access 30 分钟 / refresh 7 天；前端 axios 拦截器 401 自动刷新续期
- `SECRET_KEY` 必填：缺失启动直接失败（防默认密钥伪造令牌）
- 登录限流 5 次/5 分钟（IP）；自助注册默认关闭（`REGISTER_OPEN=false`）
- 上传：扩展名白名单（svg/html/htm **排除**）、100MB 上限；SafeStaticFiles 加 nosniff、html/svg/xml 强制下载
- 审计日志保留 90 天（audit_log 表）

## 7. 外部依赖清单

| 依赖 | 用途 | 出网 | 说明 |
|---|---|---|---|
| Ollama (localhost:11434) | 本地 LLM（qwen2.5 系列） | 模型下载时 | 本地/内网模式；云端不推荐 |
| 阿里云百炼 dashscope（qwen-turbo/qwen-plus） | 问答/总结/报告（**当前线上路由**） | 是 | 云端主力 LLM |
| DeepSeek API | 备选 LLM | 是 | platform.deepseek.com |
| easyocr（本地推理） | 图片转报告 OCR | 首次模型下载 | Docker 默认禁用（体积 +2GB） |
| 钉钉开放平台 | 审批发起/查询（拉式 v1.0） | 是 | 免费层限额约 5000 次/月 |
| 局域网 NAS (UNC) | 数据与备份主存储 | — | **仅 Windows 本地模式**，云端忽略 |

## 8. 部署形态对比

| | 本地线上（现状） | 群晖 Container Manager | **云端（目标）** |
|---|---|---|---|
| 系统 | Windows + NAS 共享盘 | DSM + Docker | Ubuntu 22.04/24.04 + Docker |
| 数据库 | 本机 SQLite + NAS 备份 | ./data 卷 | 数据卷 + cron/对象存储备份 |
| 上传 | NAS UNC 目录 | ./uploads 卷 | 数据卷（后续可迁对象存储） |
| HTTPS | 无（内网） | 无 | **必须**（Caddy / Nginx+certbot） |
| 进程守护 | watchdog 脚本 | restart 策略 | restart 策略 |
| LLM | 本机 Ollama + 云 API | 同左 | 全云 API |
| OCR | easyocr 本地 | 默认关闭 | 默认关闭 → 按需接云 OCR |

## 9. 云端部署前必须知道的三个约束

1. **SQLite 单写进程**：只部署 1 个后端副本；可加 CPU/内存，不要多容器挂同一数据卷跑应用。
2. **数据要整体搬迁**：`data/`（db + 配置 + 备份）与 `uploads/` 是全部业务状态，两个目录必须完整进卷。
3. **OCR 与本地模型**：Docker 镜像不含 easyocr 与 Ollama——OCR 需额外方案（启用 easyocr 重做镜像 +2GB；或接云端 OCR），问答/报告类 AI 走云端引擎（配置已支持，数据带 Key 即用）。
