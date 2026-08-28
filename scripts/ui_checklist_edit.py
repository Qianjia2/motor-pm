# -*- coding: utf-8 -*-
"""回归：清单视图 添加交付物+上传 → 保存 → 重新编辑改状态 → 保存成功（用户报告的失败路径）。"""
import asyncio, json, urllib.request, os
from playwright.async_api import async_playwright

BASE = "http://localhost:5002"
PID = 1
NAME = "UI编辑验证-改状态"
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
        if d["name"].startswith("UI编辑") or (d.get("file_path") or "").endswith("tmp_upload_test.txt"):
            api("DELETE", f"/api/deliverables/{d['id']}", tok=tok)
    with open(TMP_FILE, "w", encoding="utf-8") as f:
        f.write("UI edit verify\n" * 10)

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
        await page.goto(f"{BASE}/projects/{PID}", wait_until="load")
        await page.wait_for_timeout(3000)

        # 进入清单视图
        await page.get_by_text("交付物", exact=True).first.click()
        await page.wait_for_timeout(2000)

        # 添加交付物 + 上传（名称由标准预填，与用户真实操作一致）
        await page.get_by_role("button", name="添加交付物").first.click()
        await page.wait_for_timeout(1000)
        dlg = page.locator(".el-dialog:visible")
        name_input = dlg.locator(".el-form-item", has_text="名称").locator("input")
        NAME = (await name_input.input_value()).strip()
        print("标准预填名称:", NAME)
        await dlg.locator("input[type='file']").set_input_files(TMP_FILE)
        await page.wait_for_timeout(400)
        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(2500)
        ds = api("GET", f"/api/projects/{PID}/deliverables", tok=tok)
        d = next((x for x in ds if x["name"] == NAME), None)
        print("创建+上传:", bool(d and d.get("file_path")))

        # 重新编辑：改状态为"已提交" → 保存
        row = page.locator(".el-table tr").filter(has_text=NAME).first
        await row.get_by_role("button", name="编辑").click()
        await page.wait_for_timeout(1000)
        dlg = page.locator(".el-dialog:visible")
        status_item = dlg.locator(".el-form-item", has_text="状态")
        await status_item.locator(".el-select").click()
        await page.wait_for_timeout(600)
        await page.locator(".el-select-dropdown:visible .el-select-dropdown__item", has_text="已提交").click()
        await page.wait_for_timeout(300)
        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(2500)

        # 验证：状态已更新 + 文件还在 + 对话框已关闭
        ds = api("GET", f"/api/projects/{PID}/deliverables", tok=tok)
        d = next((x for x in ds if x["name"] == NAME), None)
        print("编辑保存后 status:", (d or {}).get("status"))
        print("编辑保存后 file_path 保留:", bool((d or {}).get("file_path")))
        print("编辑对话框已关闭:", await page.locator(".el-dialog:visible").count() == 0)
        # 编辑对话框里显示已上传文件（再次打开检查）
        row = page.locator(".el-table tr").filter(has_text=NAME).first
        await row.get_by_role("button", name="编辑").click()
        await page.wait_for_timeout(1000)
        dlg = page.locator(".el-dialog:visible")
        print("编辑对话框显示已上传文件:", "tmp_upload_test" in await dlg.inner_text())
        await dlg.get_by_role("button", name="取消").click()
        await page.wait_for_timeout(400)

        if d: api("DELETE", f"/api/deliverables/{d['id']}", tok=tok)
        await browser.close()
    print("DONE")

asyncio.run(main())
