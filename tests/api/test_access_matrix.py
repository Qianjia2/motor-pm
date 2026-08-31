"""授权矩阵回归测试: 管理端点 未登录401 / 普通成员403 / 管理员200。"""
from tests.conftest import make_user, auth_headers

ADMIN_READ_ENDPOINTS = [
    "/api/audit-logs",
    "/api/admin/api-keys",
    "/api/admin/webhooks",
    "/api/admin/customer-access",
    "/api/knowledge/backup/status",
]


def test_unauth_401_on_admin_endpoints(client):
    for path in ADMIN_READ_ENDPOINTS:
        assert client.get(path).status_code == 401, path


def test_member_forbidden_on_admin_endpoints(client):
    headers = auth_headers(client, "am_member", "member")
    for path in ADMIN_READ_ENDPOINTS:
        assert client.get(path, headers=headers).status_code == 403, path


def test_admin_allowed(client):
    headers = auth_headers(client, "am_admin", "admin")
    for path in ADMIN_READ_ENDPOINTS:
        assert client.get(path, headers=headers).status_code == 200, path


def test_tunnel_start_admin_only(client):
    assert client.post("/api/tunnel/start").status_code == 401
    headers = auth_headers(client, "am_tun_member", "member")
    assert client.post("/api/tunnel/start", headers=headers).status_code == 403


def test_backup_create_admin_only(client):
    assert client.post("/api/knowledge/backup/create").status_code == 401
    headers = auth_headers(client, "am_bak_member", "member")
    assert client.post("/api/knowledge/backup/create", headers=headers).status_code == 403
    admin = auth_headers(client, "am_bak_admin", "admin")
    resp = client.post("/api/knowledge/backup/create", headers=admin)
    assert resp.status_code == 200
    assert resp.json().get("ok")


def test_member_can_use_normal_endpoints(client):
    headers = auth_headers(client, "am_scope_member", "member")
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.get("/api/bom-lists/internal-templates", headers=headers).status_code == 200
