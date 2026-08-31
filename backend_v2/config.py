"""Application configuration via pydantic-settings."""
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List


class Settings(BaseSettings):
    # ── Database ──
    # Absolute path ensures CWD-independent database location
    DATABASE_URL: str = "sqlite:///" + str(Path(__file__).parent.parent / "data" / "motor_pm_v2.db")

    # ── Data Directory (for uploads, configs, exports) ──
    DATA_DIR: str = ""  # 留空 = 本地 ./data；填服务器路径如 Z:/motor-pm-data

    # ── Auth ──
    # 必填：通过环境变量 SECRET_KEY 或 .env 提供，缺失时启动失败（防默认密钥被伪造 JWT）
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # ── Upload ──
    # 主存储在公司 NAS（2026-08-11 迁移）；如 NAS 不可用可临时改回本地 data/uploads
    UPLOAD_DIR: str = r"\\10.136.101.13\easitech\个人文件夹\qianjia\麦克斯韦-AI项目管理平台工具后台资料存放\MotorPM_Live\uploads"
    MAX_UPLOAD_SIZE_MB: int = 100
    ALLOWED_EXTENSIONS: List[str] = [
        # Office documents
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        "rtf", "odt", "ods", "odp",
        # CAD / Engineering
        "step", "stp", "dwg", "dxf", "igs", "iges", "stl",
        "catpart", "catproduct", "cgr", "prt", "asm",
        "sldprt", "sldasm", "slddrw", "sat", "x_t", "x_b",
        "ipt", "iam", "dft", "par", "psm",
        # Simulation / Analysis
        "cae", "inp", "dat", "sim", "frd", "odb",
        # Archives
        "zip", "rar", "7z", "tar", "gz", "bz2",
        # Images (svg 排除: 可内嵌脚本, 防存储型 XSS)
        "jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif", "ico",
        # Text / Data / Code (html/htm 排除: 同上, 防止免登录 /uploads 被用作钓鱼/钓鱼页)
        "txt", "csv", "json", "xml", "yaml", "yml", "toml",
        "py", "ipynb", "js", "ts", "vue", "css", "scss",
        "c", "cpp", "h", "hpp", "cs", "java", "go", "rs", "swift",
        "sql", "sh", "bat", "ps1", "cmd",
        # Logs / Config
        "log", "cfg", "ini", "conf", "env",
        # Media
        "mp4", "avi", "mov", "wmv", "mp3", "wav", "flac",
        # Markdown
        "md", "rst",
    ]

    # ── CORS ──
    CORS_ORIGINS: List[str] = [
        "http://localhost:5000",
        "http://localhost:5173",
        "http://127.0.0.1:5000",
    ]

    # ── Rate Limit ──
    LOGIN_RATE_LIMIT: int = 5       # max attempts
    LOGIN_RATE_WINDOW: int = 300    # seconds

    # ── Seed (seed.py 读取; 未设置时随机生成并打印一次) ──
    INITIAL_ADMIN_PASSWORD: str = ""
    INITIAL_USER_PASSWORD: str = ""

    # ── Registration ──
    # 默认关闭自助注册（内部系统由管理员建号）；确需开放时设 REGISTER_OPEN=true
    REGISTER_OPEN: bool = False

    # ── Audit ──
    AUDIT_RETENTION_DAYS: int = 90

    # ── DingTalk (optional) ──
    DINGTALK_WEBHOOK_URL: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
