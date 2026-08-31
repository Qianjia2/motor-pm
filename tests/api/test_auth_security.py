"""登录/注册/改密/token 安全回归测试。

限流按 IP:用户名 分桶（TestClient 中 IP 恒为 "testclient"），
失败登录测试一律使用独立用户名，避免与成功登录互相干扰。
"""
from tests.conftest import make_user, auth_headers


def test_login_success(client):
    make_user("sec_login_ok", "member", "pw12345")
    resp = client.post("/api/auth/login", json={"username": "sec_login_ok", "password": "pw12345"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_wrong_password(client):
    make_user("sec_login_bad", "member", "pw12345")
    resp = client.post("/api/auth/login", json={"username": "sec_login_bad", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user(client):
    resp = client.post("/api/auth/login", json={"username": "sec_no_such_user", "password": "x"})
    assert resp.status_code == 401


def test_rate_limit_after_5_failures(client):
    make_user("sec_rl_user", "member", "pw12345")
    make_user("sec_rl_other", "member", "pw12345")
    for _ in range(5):
        resp = client.post("/api/auth/login", json={"username": "sec_rl_user", "password": "wrong"})
        assert resp.status_code == 401
    resp = client.post("/api/auth/login", json={"username": "sec_rl_user", "password": "wrong"})
    assert resp.status_code == 429
    # 限流键为 IP:用户名，不影响其他账号
    assert client.post("/api/auth/login",
                       json={"username": "sec_rl_other", "password": "pw12345"}).status_code == 200


def test_rate_limit_reset_on_success(client):
    make_user("sec_rl_reset", "member", "pw12345")
    for _ in range(3):
        assert client.post("/api/auth/login",
                           json={"username": "sec_rl_reset", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login",
                       json={"username": "sec_rl_reset", "password": "pw12345"}).status_code == 200


def test_register_closed_by_default(client):
    resp = client.post("/api/auth/register", json={"username": "sec_newbie", "password": "pw12345"})
    assert resp.status_code == 403
    assert "注册已关闭" in resp.json()["detail"]


def test_forged_token_rejected(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer forged.invalid.token"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_current_user(client):
    headers = auth_headers(client, "sec_me_user", "member")
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    assert "sec_me_user" in resp.text


def test_change_password_body(client):
    headers = auth_headers(client, "sec_pw_user", "member")
    # 原密码错误 → 400
    resp = client.put("/api/auth/password",
                      json={"old_password": "wrong", "new_password": "newpw999"}, headers=headers)
    assert resp.status_code == 400
    # 正确修改 → 200
    resp = client.put("/api/auth/password",
                      json={"old_password": "pw12345", "new_password": "newpw999"}, headers=headers)
    assert resp.status_code == 200
    # 新密码可登录，旧密码失效
    assert client.post("/api/auth/login",
                       json={"username": "sec_pw_user", "password": "newpw999"}).status_code == 200
    assert client.post("/api/auth/login",
                       json={"username": "sec_pw_user", "password": "pw12345"}).status_code == 401
