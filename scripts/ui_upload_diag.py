# -*- coding: utf-8 -*-
"""诊断：点击"选择文件"按钮是否触发 filechooser，浏览器控制台有无报错。"""
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
        f.write("UI upload regression test content - 电机测试\n" * 10)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 950})

        console_msgs = []
        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: console_msgs.append(f"[PAGEERROR] {e}"))
        req_failures = []
        page.on("requestfailed", lambda r: req_failures.append(f"{r.method} {r.url} -> {r.failure}"))

        await page.goto(BASE + "/", wait_until="load")
        await page.wait_for_timeout(600)
        await page.evaluate("""(args) => {
            localStorage.setItem('access_token', args.tok)
            localStorage.setItem('user', JSON.stringify({username:'admin', role:'admin', member_id:null, name:'admin'}))
        }""", {"tok": tok})
        await page.goto(f"{BASE}/projects/{PID}?tab=deliverables", wait_until="load")
        await page.wait_for_timeout(2500)

        await page.get_by_role("button", name="添加交付物").click()
        await page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")

        # 阶段必选
        phase_item = dlg.locator(".el-form-item", has_text="阶段")
        await phase_item.locator(".el-select").click()
        await page.wait_for_timeout(600)
        await page.locator(".el-select-dropdown:visible .el-select-dropdown__item").first.click()
        await page.wait_for_timeout(300)

        # 真实点击"选择文件"按钮，监听 filechooser 事件
        btn = dlg.get_by_role("button", name="选择文件").first
        print("找到选择文件按钮:", await btn.count() > 0)
        chooser_fired = {"v": False}
        async def on_chooser(fc):
            chooser_fired["v"] = True
            print("FILE CHOOSER 事件触发!")
            await fc.set_files(TMP_FILE)
        page.on("filechooser", on_chooser)

        await btn.click()
        await page.wait_for_timeout(1500)
        print("filechooser 触发:", chooser_fired["v"])

        dlg_text = await dlg.inner_text()
        print("已选择提示出现:", "已选择" in dlg_text)

        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(2500)

        print("\n--- 控制台消息 (最后20条) ---")
        for m in console_msgs[-20:]:
            print(m)
        print("\n--- 请求失败 ---")
        for r in req_failures[-10:]:
            print(r)

        # 保存后数据库状态
        ds = api("GET", f"/api/projects/{PID}/deliverables", tok=tok)
        d = next((x for x in ds if x["name"].startswith("UI")), None)
        if d:
            print("\n文件路径:", d.get("file_path"))
            if d.get("file_path"):
                try:
                    r = urllib.request.urlopen(BASE + "/uploads/" + d["file_path"], timeout=15)
                    print("下载验证:", r.status, b"UI upload regression" in r.read())
                except Exception as e:
                    print("下载失败:", e)
            api("DELETE", f"/api/deliverables/{d['id']}", tok=tok)
        else:
            print("\n!! 未找到测试交付物 (可能保存失败)")

        await browser.close()

asyncio.run(main())
