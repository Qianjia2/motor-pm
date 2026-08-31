"""Shared fixtures for motor-pm unit tests."""
import os
import sys
import pathlib
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ── API 测试隔离环境: 必须在 import backend_v2 之前设置 ──
# 重定向数据库与上传目录到临时目录, 防止测试污染生产库 / NAS 路径
_TEST_TMP = tempfile.mkdtemp(prefix="motorpm_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TEST_TMP, 'test.db')}"
os.environ["UPLOAD_DIR"] = os.path.join(_TEST_TMP, "uploads")
# SECRET_KEY 兜底（.env 在 CI 中不存在；环境变量优先于 .env 配置）
os.environ.setdefault("SECRET_KEY", "motorpm-test-only-secret-key")

# 内部模板固定夹具: 仓库根 data/ 下的真实公司模板(git 已跟踪, CI 可用)
TEMPLATE_XLS = REPO_ROOT / "data" / "bom_internal_template.xls"


def _template_bytes():
    if not TEMPLATE_XLS.exists():
        raise FileNotFoundError(f"模板夹具缺失: {TEMPLATE_XLS}")
    return TEMPLATE_XLS.read_bytes()


import pytest


@pytest.fixture(scope="session")
def template_bytes():
    return _template_bytes()


@pytest.fixture(scope="session")
def template_meta(template_bytes):
    from backend_v2.routes.bom_lists import _parse_internal_template
    return _parse_internal_template(template_bytes, "bom_internal_template.xls")


# ═══════════════ API 测试夹具（tests/api/*） ═══════════════

@pytest.fixture(scope="session")
def client():
    """TestClient + 隔离数据库(临时文件)。startup 由 with 上下文触发。"""
    from fastapi.testclient import TestClient
    from backend_v2.main import app
    with TestClient(app) as c:
        yield c


def make_user(username: str, role: str = "member", password: str = "pw12345") -> None:
    """直接写库创建/重置用户(比走注册 API 快且不受注册开关影响)。"""
    from backend_v2.database import SessionLocal
    from backend_v2.models import UserAuth
    from backend_v2.auth import hash_password
    with SessionLocal() as db:
        from sqlalchemy import select
        user = db.execute(select(UserAuth).where(UserAuth.username == username)).scalar_one_or_none()
        if user:
            user.password_hash = hash_password(password)
            user.role = role
            user.is_active = True
        else:
            db.add(UserAuth(username=username, password_hash=hash_password(password), role=role))
        db.commit()


def login(client, username: str, password: str = "pw12345") -> dict:
    """登录并返回带 Authorization 头的 dict。"""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def auth_headers(client, username: str = "admin", role: str = "admin",
                 password: str = "pw12345") -> dict:
    """确保用户存在并返回登录头。注意: 失败登录测试勿与成功登录共用同一账号(限流)。"""
    make_user(username, role, password)
    return login(client, username, password)
