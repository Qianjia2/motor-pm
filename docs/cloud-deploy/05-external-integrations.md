# 05 外部集成（钉钉 / AI 引擎 / OCR）

三类外部集成均在**服务端出网**调用；凭证与路由存于 `data/*.json`（实时读盘，**保存即生效，无需重启**）。**不要把真实凭证提交进 git**（仓库为公开备份源）。

## 1. AI 多引擎（`data/ai_config.json`）

页面入口：管理后台 → AI 设置（`GET/PUT /api/ai/config`），也可直接编辑容器内 `/app/data/ai_config.json`（宿主机 `/opt/motorpm/data/ai_config.json`）。

### 结构

```jsonc
{
  "provider": "tongyi",        // 主模型标识
  "model": "qwen-turbo",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "api_key": "sk-...",         // 敏感：仅存 data 卷，不进 git
  "temperature": 0.1,
  "max_tokens": 16384,
  "enabled": true,
  "system_prompt": "...",      // 全局人设（电机研发项目管理场景）
  "timeout": 300,
  "engines": {                 // 各厂商凭证与模型
    "deepseek": { "api_key": "", "model": "deepseek-chat", "base_url": "https://api.deepseek.com/v1" },
    "tongyi":   { "api_key": "sk-...", "model": "qwen-turbo", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1" }
    // kimi / baidu_ocr 等按需追加（ai_service.py 引擎骨架内置）
  },
  "routing": {                 // 任务类型 → 实际引擎
    "chat": "tongyi", "qa": "tongyi",
    "summary": "tongyi", "report": "tongyi", "report_model": "qwen-plus"
  }
}
```

### 路由语义

| 任务类型 | 用途 | 当前线上引擎 |
|---|---|---|
| `qa` / `chat` | 智能问答（AI 助手） | 通义 qwen（云端） |
| `summary` | 周报摘要等文本提炼 | 通义 qwen |
| `report` | AI 生成报告（模板+数据） | 通义（`report_model` 可单独指定更大模型） |
| OCR（图片转报告） | 不走本配置路由：由 report-gen 模块调用本地 easyocr | easyocr 本地 |

### 各引擎接入要点

| 引擎 | 接入 | 云端适用 |
|---|---|---|
| **阿里云百炼 tongyi** | 百炼控制台创建 API-KEY（`sk-` 开头）；OpenAI 兼容端点 `dashscope.aliyuncs.com/compatible-mode/v1`；模型 qwen-turbo（快）/ qwen-plus（强） | ✅ **推荐主力**（当前线上已启用；Key 随数据迁移，核验未过期即可） |
| DeepSeek | platform.deepseek.com 创建 key；`api.deepseek.com/v1`；模型 `deepseek-chat` | ✅ 备选 |
| Ollama | 本机 `localhost:11434`，模型 qwen2.5 系列；**云端容器内无 Ollama**，如坚持本地模型需自部署 sidecar 并改 `base_url` | ⚠️ 不推荐 |
| Kimi / 百度千帆 | 引擎骨架内置，按各厂商 OpenAI 兼容端点填入 engines | 可选 |

### 排障速查

- 问答返回「AI调用失败 / 401」→ `engines.<name>.api_key` 失效或额度耗尽。
- 「连接失败」→ 服务器出网受限，确认能直连 `dashscope.aliyuncs.com` / `api.deepseek.com`。
- 长时间「思考中…」→ AI 报告为**同步长请求**（分钟级），反代 read_timeout 需放宽（03 文档已设 300s）。

## 2. 钉钉审批（`data/dingtalk_config.json`）

功能：系统内发起钉钉 OA 审批（表单按审批模板映射），审批状态/实例列表通过钉钉 API **主动查询**回显（拉式 v1.0：发起 + 查状态 + 按手机号/关键词拉实例与项目关联）。**无回调订阅，云端不需要任何入站回调地址**。

### 结构（真实值勿入 git）

```jsonc
{
  "enabled": true,
  "corp_id": "ding...",         // 企业 corpId
  "app_key": "ding...",         // 企业内部应用 AppKey
  "app_secret": "...",          // AppSecret（敏感）
  "templates": [                // 系统功能 → 钉钉审批模板
    { "name": "...", "process_code": "PROC-..." }
  ],
  "approval_templates": [ ... ]
}
```

相关端点（均需登录）：`GET/PUT /api/dingtalk/config`、`PUT /api/dingtalk/credentials`（admin）、
`GET/PUT /api/dingtalk/templates`、`GET /api/dingtalk/templates/available`（拉钉钉全部可见模板）、
`POST /api/dingtalk/approvals`（发起实例）、`GET /api/dingtalk/approvals/{instance_id}`（查状态）、
`GET /api/dingtalk/instances`（拉列表，`process_code` 空 = 跨全部模板按手机号/关键词搜索）、
`GET /api/dingtalk/instances/{instance_id}`（实例详情 + 钉钉打开链接）。
发起记录同时落 `data/dingtalk_approvals.json`。

### 接入三步（对接新企业时）

1. 钉钉开放平台 → 企业内部应用：创建应用，取得 `AppKey/AppSecret`；企业 `corpId` 在首页获取。
2. 在后台「钉钉设置」填入凭证并保存（`PUT /api/dingtalk/credentials`）；拉取并勾选审批模板（`templates/available` → 保存 `templates`）。
3. 若钉钉后台为该应用配置了**服务器出口 IP 白名单**，把云端服务器公网 IP 加入；权限点需含「OA 审批实例创建/读取」「通讯录只读（手机号查人）」。

### 限额

- 免费限额约 **5000 次/月**（含实例创建、状态查询、列表拉取）；超出被限流属预期，注意查询频率（页面按需拉取即可，勿写轮询脚本）。

### 排障速查

- 发起报错看容器日志中钉钉返回码：`invalid appKey/secret`（凭证错）、`out of quota`（月限额）、
  `not in white list` / 403（出口 IP 未加白或应用权限不足）。
- 审批通过但系统未回显状态 → 页面「刷新状态」走 `GET /api/dingtalk/approvals/{instance_id}` 主动查询，确认能连 `oapi.dingtalk.com`。
- 可选告警：`DINGTALK_WEBHOOK_URL`（群机器人）把系统异常推送到钉钉群。

## 3. OCR（图片转报告）

| 引擎 | 形态 | 说明 |
|---|---|---|
| easyocr（默认，本地推理） | 进程内 PyTorch | Windows 本地可用；**首次调用加载模型很慢（实测曾 ~80s）**，之后常驻内存；Docker 镜像默认排除（体积 +2GB） |
| baidu_ocr（备选） | 云 API | ai_service 引擎骨架内置；需百度智能云凭证 |

**云端建议**：
1. 图片转报告非刚需 → 保持现状：上传入口提示 OCR 不可用，其余功能不受影响。
2. 刚需 → 首选接**云端 OCR**（baidu_ocr 等，需代码确认当前版本的云 OCR 图片直传链路已接通）；次选自建含 easyocr 的镜像（requirements 增加 `easyocr`，+2GB，首次运行需出网下载模型权重）。

## 4. 云端凭证核对清单（上线前）

| 项 | 存放 | 获取位置 | 云端必查 |
|---|---|---|---|
| `SECRET_KEY` | 容器 env / .env | `openssl rand -hex 32` | ✅ 生成并注入（新环境，不随数据迁移） |
| 阿里云百炼 API-KEY | `data/ai_config.json → engines.tongyi` | 百炼控制台 | ✅ Key 随数据搬迁；核验未过期、额度充足 |
| DeepSeek API-KEY | 同上 `engines.deepseek` | platform.deepseek.com | 可选 |
| 钉钉 AppKey/AppSecret | `data/dingtalk_config.json` | 钉钉开发者后台 | ✅ 核验有效；出口 IP 白名单（如配置了）加公网 IP |
| 群机器人 Webhook（可选） | env `DINGTALK_WEBHOOK_URL` | 钉钉群 → 机器人 | 可选 |

> 提醒：这些 `data/*.json` 含明文密钥，随数据卷存放在服务器上即可；**切勿**把它们放进 git 仓库或公开分享。
