# -*- coding: utf-8 -*-
"""验证 POST /api/changes/preview-attachment:内存解析,不落盘。"""
import io, sys, traceback
import requests

BASE = "http://localhost:5002"
s = requests.Session()

def req(method, path, **kw):
    r = s.request(method, BASE + path, **kw)
    try:
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
    except Exception:
        body = r.text[:200]
    print(f"[{r.status_code}] {method} {path} -> {body if isinstance(body, str) else str(body)[:400]}")
    return r

r = req("POST", "/api/auth/login", json={"username": "admin", "password": "admin123"})
tok = r.json().get("access_token")
s.headers["Authorization"] = f"Bearer {tok}"

# 1. xlsx -> html
from openpyxl import Workbook
wb = Workbook()
ws = wb.active
ws.title = "技术变更"
ws.append(["编号", "变更内容", "影响范围"])
ws.append(["TC-001", "电机绕组方案调整", "功率密度提升"])
buf = io.BytesIO(); wb.save(buf)
r = req("POST", "/api/changes/preview-attachment",
        files={"file": ("测试表.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
assert r.status_code == 200, "xlsx preview failed"
d = r.json()
assert d.get("kind") == "html" and "TC-001" in d.get("html", ""), "xlsx html content missing"
print("OK: xlsx -> html 含表格内容")

# 2. pdf -> raw
pdf_bytes = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
r = req("POST", "/api/changes/preview-attachment",
        files={"file": ("测试.pdf", pdf_bytes, "application/pdf")})
assert r.status_code == 200 and r.json().get("kind") == "raw", "pdf should be raw"
print("OK: pdf -> raw")

# 3. zip -> unsupported
r = req("POST", "/api/changes/preview-attachment",
        files={"file": ("a.zip", b"PK\x05\x06\x00" * 4, "application/zip")})
assert r.status_code == 200 and r.json().get("kind") == "unsupported", "zip should be unsupported"
print("OK: zip -> unsupported")

# 4. 超大文件 -> 413 (MAX_UPLOAD_SIZE_MB=100)
r = req("POST", "/api/changes/preview-attachment",
        files={"file": ("big.pdf", b"0" * (101 * 1024 * 1024), "application/pdf")})
assert r.status_code == 413, f"oversize should 413, got {r.status_code}"
print("OK: oversize -> 413")

print("ALL PASS")
