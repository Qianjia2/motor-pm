# 03 云端部署（Docker + HTTPS/域名）

> 目标形态：一台云 Ubuntu 服务器，Docker 单容器运行 MotorPM，Nginx/Caddy 提供 HTTPS 与域名。
> 本文命令按 **仓库 git 布局**（根目录即 `frontend/` + `backend_v2/`）编写——**不要**直接使用
> `deploy/docker/` 下的旧 Dockerfile（它按 `src/frontend/`、`src/backend_v2/` 部署包布局编写）。

## 0. 前置条件

| 项 | 要求 |
|---|---|
| 云服务器 | 2C4G 起（AI 报告为同步长请求，建议 4G）；Ubuntu 22.04/24.04 x86_64 |
| 磁盘 | 40G+（uploads 增长 + 镜像约 1.5G + 备份） |
| 域名 | A 记录指向服务器公网 IP（如 `pm.example.com`） |
| 出网 | 服务器需能访问：阿里云百炼 / DeepSeek / 钉钉 API / GitHub（拉代码） |

> ⚠️ 首次上线前先读「8. 数据搬迁」，把现有 `data/` 与 `uploads/` 迁过来，避免部署成功后面对空库。

## 1. 服务器初始化

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker

sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw --force enable

docker --version
```

## 2. 拉取代码并准备部署目录

```bash
mkdir -p /opt/motorpm && cd /opt/motorpm
git clone https://github.com/Qianjia2/motor-pm.git app
cd app && git checkout main

mkdir -p /opt/motorpm/{deploy,data,uploads}
cd /opt/motorpm/deploy
```

> 目录约定：`/opt/motorpm/app` = 代码（可 git pull 更新）；
> `/opt/motorpm/data` + `/opt/motorpm/uploads` = 数据（bind mount 进容器，备份只盯这两个）。

## 3. 云端专用 Dockerfile（适配 git 布局）

`/opt/motorpm/deploy/Dockerfile.cloud`：

```dockerfile
# Stage 1: 前端构建
FROM node:20-alpine AS fe
WORKDIR /build/frontend
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund --registry=https://registry.npmmirror.com
COPY app/frontend/ ./
RUN npm run build

# Stage 2: 后端运行（镜像不含 easyocr/torch，仓库根 requirements 与 CI 同款）
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai
RUN apt-get update && apt-get install -y --no-install-recommends tzdata     && rm -rf /var/lib/apt/lists/*
COPY app/backend_v2/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY app/backend_v2/ backend_v2/
COPY --from=fe /build/frontend/dist frontend/dist
VOLUME ["/app/data", "/app/uploads"]
EXPOSE 5002
CMD ["uvicorn", "backend_v2.main:app", "--host", "0.0.0.0", "--port", "5002"]
```

## 4. 环境变量与 compose

```bash
cd /opt/motorpm/deploy
openssl rand -hex 32 > .secret   # SECRET_KEY：必填且必须随机；丢失=全员重新登录（数据无损）
```

`.env.motorpm`（把 `<...>` 换成上一步真实值）：

```ini
SECRET_KEY=<openssl rand -hex 32 输出的 64 字符>
TZ=Asia/Shanghai
# 覆盖 config.py 里的 NAS UNC 默认值 —— 云端必须
UPLOAD_DIR=/app/uploads
```

`docker-compose.yml`（云端版）：

```yaml
services:
  motorpm:
    build:
      context: /opt/motorpm        # 仓库根（app/ 在其中）
      dockerfile: deploy/Dockerfile.cloud
    image: motorpm:cloud
    container_name: motorpm
    restart: unless-stopped
    # 只监听宿主回环 —— 公网 HTTPS 由宿主机反代，5002 不暴露公网
    ports:
      - "127.0.0.1:5002:5002"
    volumes:
      - /opt/motorpm/data:/app/data
      - /opt/motorpm/uploads:/app/uploads
    env_file:
      - .env.motorpm
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5002/api/health', timeout=5)"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s
    logging:
      options:
        max-size: "10m"
        max-file: "3"
```

构建并启动（首次 5–10 分钟）：

```bash
cd /opt/motorpm/deploy
docker compose up -d --build
docker compose ps               # STATUS 应为 healthy
docker compose logs -f --tail=50
curl -s http://127.0.0.1:5002/api/health   # 期望 {"status":"ok","version":"2.0.0"}
```

## 5. 配置 AI 引擎（云端必须做）

云端容器内**没有 Ollama**。把问答/总结/报告路由到云端模型——直接编辑数据目录下的业务配置
（宿主机 `/opt/motorpm/data/ai_config.json`，**保存即生效，每次调用实时读盘，无需重启**）：

```bash
nano /opt/motorpm/data/ai_config.json
# 1) 确认 engines.tongyi.api_key 已填（阿里云百炼控制台，形如 sk-xxx）
# 2) routing 设为：
#      "routing": { "chat": "tongyi", "qa": "tongyi", "summary": "tongyi",
#                   "report": "tongyi", "report_model": "qwen-plus" }
```

> 当前本地线上的 routing 已指向通义并带有效 Key——数据搬迁后直接沿用，仅核验 Key 未过期即可。
> 引擎字段说明见 [05-external-integrations.md](./05-external-integrations.md)。

## 6. HTTPS 与域名（二选一）

### 方案 A：Caddy（推荐，证书自动申请/续期）

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`（域名替换成自己的）：

```
pm.example.com {
        reverse_proxy 127.0.0.1:5002
        encode gzip
        request_body {
                max_size 200MB
        }
        header {
                -Server
        }
}
```

```bash
sudo systemctl reload caddy
# 浏览器访问 https://pm.example.com —— 证书自动签发
```

### 方案 B：Nginx + certbot

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

`/etc/nginx/sites-available/motorpm`：

```nginx
server {
    listen 80;
    server_name pm.example.com;
    client_max_body_size 200m;       # 上传大文件（后端另有 100MB 校验）
    location / {
        proxy_pass http://127.0.0.1:5002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;     # AI 报告/OCR 是同步长请求
        proxy_send_timeout 300s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/motorpm /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d pm.example.com
```

### HTTPS 就绪后的两件确认

1. **同源即无 CORS 问题**：前端与 API 同一域名反代，浏览器视为同源，`CORS_ORIGINS` 无需改动（仅未来前端独立域名时才需加，见 04 文档）。
2. 对外 URL（钉钉审批为拉式、无回调地址配置项）；知识库分享/客户门户等链接域名随部署域名自动变化，无硬编码。

## 7. 上线后验证清单

```bash
# 1) 健康检查
curl -s https://pm.example.com/api/health
# 2) 浏览器打开首页 → 用原管理员账号登录 → 核对项目/周报/知识库数据在
# 3) 上传一个附件 → 列表可见、可下载
# 4) AI 助手提问一句 → 有回复（验证通义 Key）
# 5) 图片转报告（可选，依赖 OCR 方案，见 05）
# 6) 钉钉发起审批（可选，见 05）
```

## 8. 数据搬迁（首次上线，从本地/NAS 到云端）

当前数据在两处：本地 `D:\AI\motor-pm\data\`（db + 配置 + 本地备份）与 NAS 共享盘 `MotorPM_Live\uploads\`（附件）。只搬迁这两类。

```powershell
# 本地 Windows PowerShell —— 在数据目录打包（NAS 盘符按实际挂载）
Compress-Archive -Path "D:\AI\motor-pm\data\*" -DestinationPath D:\tmp\motorpm-data.zip
Compress-Archive -Path "\\10.136.101.13\...\MotorPM_Live\uploads\*" -DestinationPath D:\tmp\motorpm-uploads.zip
scp D:\tmp\motorpm-data.zip D:\tmp\motorpm-uploads.zip ubuntu@<服务器IP>:/opt/motorpm/
```

```bash
# 服务器：先停容器 → 解压进数据目录 → 再启动
cd /opt/motorpm && docker compose -f deploy/docker-compose.yml stop
sudo apt install -y unzip
unzip motorpm-data.zip    -d data     # motor_pm_v2.db、*.json、backups/...
unzip motorpm-uploads.zip -d uploads
rm -f motorpm-*.zip
docker compose -f deploy/docker-compose.yml up -d
```

> 迁移后立即验证登录与数据；原数据再保留 1–2 周后清理。uploads 量大会拖慢首次 scp，可并行传或分卷。

## 9. 备份（云端替代 NAS auto_backup）

Windows 本地的 `auto_backup.py` 写死 UNC/NAS 路径，**云端不使用**。改由宿主机 cron
（每日一次 SQLite VACUUM INTO 一致性快照 + 目录归档，保留 14 天）。

`/opt/motorpm/backup.sh`（`chmod +x`）：

```bash
#!/bin/bash
set -euo pipefail
DST=/opt/motorpm/backups/$(date +%Y%m%d_%H%M)
mkdir -p "$DST"
# 热备：VACUUM INTO 生成自洽的 SQLite 快照（运行中可安全执行）
docker exec -e DST="$DST" motorpm python - <<'PYINNER'
import sqlite3, os
sqlite3.connect("/app/data/motor_pm_v2.db").execute(
    "VACUUM INTO '" + os.environ["DST"] + "/motor_pm_v2.db'"
)
PYINNER
cp /opt/motorpm/data/*.json "$DST/" 2>/dev/null || true
tar -czf "$DST/uploads.tar.gz" -C /opt/motorpm uploads
find /opt/motorpm/backups -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
```

`/etc/cron.d/motorpm-backup`：

```
13 2 * * * root /opt/motorpm/backup.sh
```

> 进阶：把 `/opt/motorpm/backups` 同步到对象存储（rclone/restic/云厂商 CLI），实现真异地备份。

## 10. 日常运维速查

```bash
cd /opt/motorpm/deploy
docker compose ps                                   # 状态
docker compose logs -f --tail=100                   # 日志
git -C /opt/motorpm/app pull --ff-only origin main  # 更新代码
docker compose up -d --build                        # 重建生效（db 无损）
curl -s http://127.0.0.1:5002/api/health            # 健康检查
```

常见故障：启动即退 + 日志含 SECRET_KEY → 密钥未注入；数据为空 → `data/` 卷没迁移；
AI 报 401 → 通义 Key 失效；长请求超时 → 反代 read_timeout 已按 300s 放宽。
