# 04 配置与安全

> 配置分层：**环境变量（/.env）→ `backend_v2/config.py`（pydantic-settings）** 控制运行参数；
> **`data/*.json` 业务配置文件**（AI、钉钉等）由页面/接口动态管理（实时读盘，保存即生效）。

## 1. 运行配置项（config.py，环境变量或 .env 覆盖）

`.env` 读取位置：**进程工作目录**（本地为仓库根 `D:\AI\motor-pm\.env`；容器内为 `/app`，可直接用 compose `environment:`/`env_file:` 注入）。环境变量优先级高于 `.env`。

| 变量 | 默认 | 说明 | 云端建议 |
|---|---|---|---|
| `SECRET_KEY` | **无（必填）** | JWT 签名密钥。缺失 → 拒绝启动。改动后全部令牌失效（重新登录），不影响数据 | `openssl rand -hex 32` 生成；compose env / .env，**勿入 git** |
| `DATABASE_URL` | `sqlite:///<仓库>/data/motor_pm_v2.db` | SQLAlchemy 连接串。保留默认即可（容器内自动落到 /app/data） | 不动 |
| `DATA_DIR` | 空（= 本地 `./data`） | 数据目录重定向（历史字段，一般不用） | 空 |
| `UPLOAD_DIR` | NAS UNC 路径（Windows 本地生产用） | 上传文件根目录 | **必改** `/app/uploads`（03 文档 compose 已设） |
| `MAX_UPLOAD_SIZE_MB` | 100 | 单文件上传上限 | 默认 |
| `ALLOWED_EXTENSIONS` | 长白名单（约 80 种） | 上传类型白名单；**svg/html/htm 已排除**（防 XSS/钓鱼托管） | 默认，勿放宽 |
| `CORS_ORIGINS` | localhost:5000/5173、127.0.0.1:5000 | 跨域白名单。**反代同源部署无需改**；仅独立前端域名时需要 | 见 §2 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 30 | access token 有效期 | 默认 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 7 | refresh token 有效期 | 默认 |
| `LOGIN_RATE_LIMIT` / `LOGIN_RATE_WINDOW` | 5 / 300 | 登录失败限流（次/秒窗口） | 默认 |
| `REGISTER_OPEN` | false | 自助注册开关（内部系统默认关闭，管理员建号） | **保持 false** |
| `AUDIT_RETENTION_DAYS` | 90 | 审计日志保留天数 | 默认 |
| `DINGTALK_WEBHOOK_URL` | 空 | 钉钉群机器人 Webhook（异常告警推送，可选） | 可选 |
| `INITIAL_ADMIN_PASSWORD` / `INITIAL_USER_PASSWORD` | 空 | 仅 seed 首次建号时用（CI 注入） | CI 专用 |

**密钥管理三条铁律**
1. `SECRET_KEY` 永不出现在代码/文档/git；本地 `.env` 不入库。
2. 轮换 `SECRET_KEY` = 全员强制下线重新登录（数据无损），可作应急手段。
3. JWT 由后端签名验证（无持久会话表），服务无状态——重启/重建容器不丢登录态。

## 2. CORS 与同源说明

- 生产同源部署（FastAPI 托管前端 + 反代）：浏览器请求全在同一 origin，**CORS 不生效，无需改配置**。
- 只有以下场景需在 `CORS_ORIGINS` 追加来源：本地开发（5173 已内置）、未来前端独立部署域名。
- 反代时设置 `X-Forwarded-Proto`（03 文档 Nginx 配置已含），保证后台生成的绝对链接为 https。

## 3. 认证与令牌机制

```
登录 POST /api/auth/login （限流：5 次/5 分钟/IP）
   └→ { access_token(30min), refresh_token(7d) }
前端 axios 拦截器：请求带 Bearer；收到 401 → 用 refresh_token 静默换新 → 重放原请求
refresh 也过期 → 跳登录页
```

- 除登录/注册/健康检查/知识库公开分享页等少数公开端点外，`/api/**` 均要求 `Authorization: Bearer <token>`。
- 权限模型：RBAC（role + permission_role），接口按角色/团队控制。
- 登录与关键写操作写入 `audit_log`（保留 90 天）；配置 `DINGTALK_WEBHOOK_URL` 可将异常推送到钉钉群。

## 4. 上传安全（已内置，勿削弱）

| 防线 | 实现 |
|---|---|
| 扩展名白名单 | `ALLOWED_EXTENSIONS`；svg/html/htm 排除（防存储型 XSS / 免登录钓鱼页） |
| 体积上限 | 100MB/文件（`MAX_UPLOAD_SIZE_MB`） |
| 下载安全 | 自定义 `SafeStaticFiles`：全局 `nosniff`；html/svg/xml 一律强制下载（`attachment`） |
| SPA fallback 防护 | 未知路径仅回落 index.html（GET-only，no-cache），带路径穿越防护 |

## 5. 启动、建表与结构变更

- 启动时 `Base.metadata.create_all` **自动补建缺失表**（无 Alembic 迁移框架）。
- **新增表/列**：改 model 后重启自动生效；生产库请先备份再升级（见 §6）。
- **删列/改类型**：SQLite 不支持 ALTER，需离线导出→重建→导入，建议联系开发者评估后操作。

## 6. 备份策略汇总

| 层 | 机制 | 触发 | 说明 |
|---|---|---|---|
| 本地（当前线上） | `auto_backup.py` 线程 | 每 1 小时 | db+配置→NAS `auto_backup_<ts>/`；>30 天清理、每月 1 号保留。**写死 NAS UNC，仅 Windows 本地模式** |
| 本地（页内） | 后台「数据备份」功能 | 手动 | 生成 `data/backup_motor_pm_v2_<date>.db` 可下载 |
| 云端 | cron + VACUUM INTO | 每日（03 文档 §9） | 一致性快照 + uploads 归档；建议再同步对象存储 |
| Docker 层 | 云磁盘快照 | 自行设置 | 兜底整个 `/opt/motorpm/data` |

**恢复演练**（每季度至少一次）：快照复制到临时目录 → 起临时容器挂新卷 → 登录核验数据。

## 7. 运行与排障

| 场景 | 位置 |
|---|---|
| 容器日志 | `docker compose logs -f`（stdout） |
| 本地文件日志 | `data/server.log`（run_v2.py 模式） |
| 健康检查 | `GET /api/health` → `{"status":"ok","version":"2.0.0"}`（Docker healthcheck 60s 轮询） |
| 接口总览 | 运行实例 `GET /openapi.json` |

常见现象与处理：

| 现象 | 原因与处理 |
|---|---|
| 启动即退 + 日志含 SECRET_KEY | 密钥未设置：注入 `SECRET_KEY` 后重启 |
| 页面 404/白屏 | `frontend/dist` 未构建或未复制进镜像：重建镜像 |
| 上传报「类型不允许」 | 扩展名不在白名单；确属业务必需才评估放宽（安全评估后） |
| 附件点击变下载而非预览 | 设计如此：html/svg/xml 强制下载防 XSS；pdf/jpg 正常内联 |
| 登录偶发限流 | 反代后全部请求显示为 127.0.0.1，多账号共享 5 次/5 分钟配额；影响明显可调大 `LOGIN_RATE_LIMIT` 或按 `X-Forwarded-For` 识别真实 IP |
| AI 长请求超时 | 同步生成最久可达分钟级：反代 `proxy_read_timeout` 已放宽 300s；进程内 easyocr 首次加载曾达 ~80s |
