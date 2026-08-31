"""路径穿越与未授权文件访问回归测试。"""
import pytest
from fastapi import HTTPException
from tests.conftest import make_user, auth_headers


def test_serve_image_requires_auth(client):
    assert client.get("/api/knowledge/images/1/x.png").status_code == 401


def test_serve_image_traversal_404(client):
    """绕过 HTTP 层直接验证 serve_image 的穿越防护（TestClient 会把 %2F 解码,
    编码的 ../ 根本到不了该路由, 这里直接调用处理函数）。"""
    from backend_v2.routes._knowledge_core import serve_image
    for evil in ("../../../../etc/passwd", "..\\..\\..\\Windows\\win.ini", "C:\\Windows\\win.ini"):
        with pytest.raises(HTTPException) as ei:
            serve_image(1, evil, _user=None)
        assert ei.value.status_code == 404
    # 正常访问不存在的图片也是 404
    with pytest.raises(HTTPException) as ei:
        serve_image(1, "none.png", _user=None)
    assert ei.value.status_code == 404


def test_serve_image_http_never_leaks(client):
    # HTTP 层: 编码穿越请求即使落到 SPA 兜底, 也绝不能泄露文件内容
    headers = auth_headers(client, "trv_img", "admin")
    resp = client.get("/api/knowledge/images/1/..%2F..%2F..%2F..%2Fetc%2Fpasswd", headers=headers)
    assert "root:" not in resp.text
    assert resp.status_code in (200, 404)


def test_doc_preview_raw_no_auth_bypass(client):
    # 修复前 raw=true 可绕过鉴权直接读文件
    resp = client.get("/api/docs/999/preview?raw=true")
    assert resp.status_code == 401
    headers = auth_headers(client, "trv_doc", "admin")
    resp = client.get("/api/docs/999/preview?raw=true", headers=headers)
    assert resp.status_code == 404


def test_plm_download_requires_auth(client):
    assert client.get("/api/prototype-builds/1/bom-files/x/download").status_code == 401
    headers = auth_headers(client, "trv_plm", "admin")
    assert client.get("/api/prototype-builds/1/bom-files/nonexistent/download",
                      headers=headers).status_code == 404


def test_spa_fallback_traversal_404(client):
    # SPA 兜底路由不允许越出 static 目录
    resp = client.get("/..%2F..%2Fdata%2Fmotor_pm_v2.db")
    assert resp.status_code == 404
