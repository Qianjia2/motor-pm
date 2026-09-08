# MotorPM 云部署文档集

> 面向「云端部署 MotorPM 项目管理平台」的完整资料包：架构、API、Docker 部署、配置安全、外部集成。
> 所有内容以 **2026-09-08 仓库实际代码与线上数据为准**（非早期架构设计文档中的理想描述）。

## 文档清单

| 文件 | 内容 | 读者 |
|---|---|---|
| [01-architecture.md](./01-architecture.md) | 系统架构总览：技术栈、进程、数据存储、模块地图、部署模式对比与云端约束 | 所有人 |
| [api-reference-full.md](./api-reference-full.md) | **521 个 API 端点 / 39 个模块** 全量参考（由线上 OpenAPI 自动生成） | 对接开发、联调 |
| [03-cloud-deployment.md](./03-cloud-deployment.md) | 云服务器 Docker 部署 + HTTPS/域名（Caddy / Nginx + certbot）完整步骤 | 运维 |
| [04-config-and-security.md](./04-config-and-security.md) | 配置项说明（.env / JSON）、密钥管理、上传安全、限流、备份策略 | 运维 |
| [05-external-integrations.md](./05-external-integrations.md) | 钉钉审批、AI 多引擎（Ollama/通义/DeepSeek…）、OCR 的外部依赖与云端建议 | 运维 + 开发 |

## 快速导航

- **只想尽快在云上跑起来** → [03-cloud-deployment.md](./03-cloud-deployment.md)（含完整命令与配置文件模板）
- **需要对接接口** → [api-reference-full.md](./api-reference-full.md)，认证先看 [04-config-and-security.md](./04-config-and-security.md#3-认证与令牌机制)
- **想理解这套系统到底是什么** → [01-architecture.md](./01-architecture.md)

## 核心事实速览（诚实声明）

本资料刻意反映**真实实现**，与某些早期架构文档宣称的有所不同，请以此为准：

- 后端 FastAPI（Python 3.12 本地 / 3.11 Docker 与 CI），**SQLite 单文件数据库**（`data/motor_pm_v2.db`，54 张表），**非 PostgreSQL**
- 前端 Vue 3 + Element Plus，构建产物由后端 FastAPI 同源托管（单进程即可完整运行，**无独立前端服务器**）
- 服务端口 **5002**，健康检查 `GET /api/health` → `{"status":"ok","version":"2.0.0"}`
- 认证：JWT（access 30 分钟 + refresh 7 天）；登录限流（5 次/5 分钟）；自助注册默认关闭
- 上传白名单禁止 svg/html 等可执行类型；100MB 上限；文件经安全静态服务下发
- 当前线上 AI 问答/总结/报告已路由到**云端大模型**（阿里云通义 qwen，配置实时读盘、改即生效）；Ollama 仅本地模式使用；OCR 为本地 easyocr（Docker 镜像默认不含）
- 钉钉审批为**发起 + 主动查状态**模式（v1.0 拉式 API），不需要配置回调地址
- 云端部署的三个硬约束，详见 [01-architecture.md](./01-architecture.md#9-云端部署前必须知道的三个约束)

## 版本与更新

本文档目录随 `docs/cloud-deploy/` 提交在仓库 `main` 分支；接口清单可在任意运行实例执行 `GET /openapi.json` 后重新生成（生成方式见 api-reference-full.md 文件头注释）。
