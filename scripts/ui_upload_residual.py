# -*- coding: utf-8 -*-
"""回归：添加交付物选文件→取消→重新打开，上传控件应为空（上次文件不残留）。"""
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
    with open(TMP_FILE, "w", encoding="utf-8") as f:
        f.write("residual check\n" * 10)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 950})
        await page.goto(BASE + "/", wait_until="load")
        await page.wait_for_timeout(600)
        await page.evaluate("""(args) => {
            localStorage.setItem('access_token', args.tok)
            localStorage.setItem('user', JSON.stringify({username:'admin', role:'admin', member_id:null, name:'admin'}))
        }""", {"tok": tok})
        await page.goto(f"{BASE}/projects/{PID}", wait_until="load")
        await page.wait_for_timeout(3000)
        await page.get_by_text("交付物", exact=True).first.click()
        await page.wait_for_timeout(2000)

        def dlg_text():
            return page.locator(".el-dialog:visible").inner_text()

        # 1. 打开添加 → 选文件（不保存）→ 取消
        await page.get_by_role("button", name="添加交付物").first.click()
        await page.wait_for_timeout(1000)
        dlg = page.locator(".el-dialog:visible")
        print("1a 添加对话框(初始) 无残留:", "已选择" not in await dlg_text() and "选择文件" in await dlg_text())
        await dlg.locator("input[type='file']").set_input_files(TMP_FILE)
        await page.wait_for_timeout(500)
        print("1b 选文件后 已选择提示:", "已选择" in await dlg_text())
        await dlg.get_by_role("button", name="取消").click()
        await page.wait_for_timeout(600)

        # 2. 重新打开添加 → 应为空
        await page.get_by_role("button", name="添加交付物").first.click()
        await page.wait_for_timeout(1000)
        t2 = await dlg_text()
        print("2 重新打开 无残留文件:", "tmp_upload_test" not in t2 and "已选择" not in t2)
        # 上传控件文件列表项
        print("2b el-upload 列表项数量:", await dlg.locator(".el-upload-list__item").count())
        await dlg.get_by_role("button", name="取消").click()
        await page.wait_for_timeout(500)
        await browser.close()
    print("DONE")

asyncio.run(main())
