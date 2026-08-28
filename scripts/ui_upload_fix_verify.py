# -*- coding: utf-8 -*-
"""验证修复：1) 不选阶段保存→前端拦截提示 2) 状态=已评审+上传→成功 3) 正常上传流程。"""
import asyncio, json, urllib.request, os
from playwright.async_api import async_playwright

BASE = "http://localhost:5002"
PID = 1
TMP_FILE = os.path.join(os.path.dirname(__file__), "tmp_upload_test.txt")

def api(method, path, body=None, tok=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {tok}"} if tok else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read().decode())
        except Exception: return {}

async def main():
    tok = api("POST", "/api/auth/login", {"username": "admin", "password": "admin123"})["access_token"]
    for d in api("GET", f"/api/projects/{PID}/deliverables", tok=tok):
        if d["name"].startswith("UI修复验证"):
            api("DELETE", f"/api/deliverables/{d['id']}", tok=tok)
    with open(TMP_FILE, "w", encoding="utf-8") as f:
        f.write("UI upload fix verify content\n" * 10)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 950})
        page.on("pageerror", lambda e: print("[PAGEERROR]", e))
        await page.goto(BASE + "/", wait_until="load")
        await page.wait_for_timeout(600)
        await page.evaluate("""(args) => {
            localStorage.setItem('access_token', args.tok)
            localStorage.setItem('user', JSON.stringify({username:'admin', role:'admin', member_id:null, name:'admin'}))
        }""", {"tok": tok})
        await page.goto(f"{BASE}/projects/{PID}?tab=deliverables", wait_until="load")
        await page.wait_for_timeout(2500)

        # ── 场景1：只填名称不选阶段，直接保存 → 应弹"请选择阶段"且不创建
        await page.get_by_role("button", name="添加交付物").click()
        await page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")
        await dlg.get_by_placeholder("如：电磁可行性分析报告").fill("UI修复验证-无阶段")
        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(1000)
        toast = await page.locator(".el-message:visible").inner_text()
        print("场景1 无阶段保存 → 提示:", repr(toast))
        ds = api("GET", f"/api/projects/{PID}/deliverables", tok=tok)
        print("场景1 未创建交付物:", not any(x["name"] == "UI修复验证-无阶段" for x in ds))
        await dlg.get_by_role("button", name="取消").click()
        await page.wait_for_timeout(400)

        # ── 场景2：状态选"已评审" + 选文件 + 保存 → 应成功且上传
        await page.get_by_role("button", name="添加交付物").click()
        await page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")
        await dlg.get_by_placeholder("如：电磁可行性分析报告").fill("UI修复验证-已评审")
        phase_item = dlg.locator(".el-form-item", has_text="阶段")
        await phase_item.locator(".el-select").click()
        await page.wait_for_timeout(600)
        await page.locator(".el-select-dropdown:visible .el-select-dropdown__item").first.click()
        await page.wait_for_timeout(300)
        status_item = dlg.locator(".el-form-item", has_text="状态")
        await status_item.locator(".el-select").click()
        await page.wait_for_timeout(600)
        await page.locator(".el-select-dropdown:visible .el-select-dropdown__item", has_text="已评审").click()
        await page.wait_for_timeout(300)
        await dlg.locator("input[type='file']").set_input_files(TMP_FILE)
        await page.wait_for_timeout(400)
        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(2500)
        ds = api("GET", f"/api/projects/{PID}/deliverables", tok=tok)
        d = next((x for x in ds if x["name"] == "UI修复验证-已评审"), None)
        print("场景2 创建成功:", bool(d), "| 状态:", (d or {}).get("status"), "| file_path:", (d or {}).get("file_path"))
        if d and d.get("file_path"):
            r = urllib.request.urlopen(BASE + "/uploads/" + d["file_path"], timeout=15)
            print("场景2 下载验证:", r.status == 200 and b"UI upload fix verify" in r.read())
        # 清理
        if d: api("DELETE", f"/api/deliverables/{d['id']}", tok=tok)

        await browser.close()
    print("DONE")

asyncio.run(main())
