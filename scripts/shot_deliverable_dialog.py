# -*- coding: utf-8 -*-
"""截图：项目详情-交付物矩阵-添加交付物对话框（含上传控件）。"""
import asyncio, json, urllib.request, os
from playwright.async_api import async_playwright

BASE = "http://localhost:5002"
PID = 1
SHOT = os.path.join(os.path.dirname(__file__), "shot_deliverable_dialog.png")

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
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 950})
        await page.goto(BASE + "/", wait_until="load")
        await page.wait_for_timeout(600)
        await page.evaluate("""(args) => {
            localStorage.setItem('access_token', args.tok)
            localStorage.setItem('user', JSON.stringify({username:'admin', role:'admin', member_id:null, name:'admin'}))
        }""", {"tok": tok})
        await page.goto(f"{BASE}/projects/{PID}?tab=deliverables", wait_until="load")
        await page.wait_for_timeout(2500)

        # 只截图对话框区域，不点上传，保持初始状态
        await page.get_by_role("button", name="添加交付物").click()
        await page.wait_for_timeout(1000)
        dlg = page.locator(".el-dialog:visible")
        box = await dlg.bounding_box()
        await page.screenshot(path=SHOT, clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]})
        print("截图保存:", SHOT)
        await browser.close()

asyncio.run(main())
