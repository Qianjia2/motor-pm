"""上传白名单与扩展名过滤回归测试。"""
from backend_v2.config import settings
from tests.conftest import make_user, auth_headers


def test_allowed_extensions_whitelist():
    banned = {"svg", "html", "htm"}
    assert banned.isdisjoint(set(settings.ALLOWED_EXTENSIONS))


def test_plm_upload_requires_auth(client):
    resp = client.post("/api/prototype-builds/1/bom-files",
                       files={"file": ("a.xlsx", b"x", "application/octet-stream")})
    assert resp.status_code == 401


def test_plm_upload_rejects_html(client):
    headers = auth_headers(client, "up_evil", "member")
    resp = client.post("/api/prototype-builds/1/bom-files",
                       headers=headers,
                       files={"file": ("evil.html", b"<script>alert(1)</script>", "text/html")})
    assert resp.status_code == 400


def test_plm_upload_rejects_svg(client):
    headers = auth_headers(client, "up_evil2", "member")
    resp = client.post("/api/prototype-builds/1/bom-files",
                       headers=headers,
                       files={"file": ("pic.svg", b"<svg onload=alert(1)>", "image/svg+xml")})
    assert resp.status_code == 400


def test_plm_upload_accepts_xlsx(client):
    headers = auth_headers(client, "up_ok", "member")
    resp = client.post("/api/prototype-builds/1/bom-files",
                       headers=headers,
                       files={"file": ("bom.xlsx", b"PK\x03\x04fake",
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert resp.status_code == 200
    assert resp.json().get("ok")
