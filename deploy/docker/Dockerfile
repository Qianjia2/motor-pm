# MotorPM v2.0 容器镜像
# 多阶段构建:Stage1 用 Node 构建前端,Stage2 用 Python 运行后端
#
# 构建命令(在部署包目录执行):
#   docker build -t motorpm:2.0 .

# ══════════ Stage 1: 前端构建 ══════════
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend

# 先装依赖(利用层缓存)
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund --registry=https://registry.npmmirror.com

# 再复制源码并构建
COPY src/frontend/ ./
RUN npm run build

# ══════════ Stage 2: 后端运行 ══════════
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    UPLOAD_DIR=/app/uploads

# 时区数据(上海)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 后端代码 + 前端构建产物
COPY src/backend_v2/ backend_v2/
COPY --from=frontend-builder /build/frontend/dist frontend/dist

# 数据目录(数据库 + 业务配置)与上传目录均通过卷挂载持久化
VOLUME ["/app/data", "/app/uploads"]

EXPOSE 5002

# 直接由 uvicorn 运行(容器崩溃由 docker restart 策略自动拉起,无需 watchdog)
CMD ["uvicorn", "backend_v2.main:app", "--host", "0.0.0.0", "--port", "5002"]
