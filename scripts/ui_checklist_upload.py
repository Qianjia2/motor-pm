# -*- coding: utf-8 -*-
"""回归：清单视图(点导航"交付物")的添加交付物→选文件→保存自动上传→列表链接可下载。"""
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
        if d["name"].startswith("UI清单验证"):
            api("DELETE", f"/api/deliverables/{d['id']}", tok=tok)
    with open(TMP_FILE, "w", encoding="utf-8") as f:
        f.write("UI checklist upload verify\n" * 10)

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

        # 按用户路径：点击左侧导航"交付物"(非 tab) → 清单视图
        nav = page.locator("div").filter(has_text="交付物").filter(has_text="矩阵")
        clicked = False
        for sel in ["div.side-nav-item", ".nav-item", ".menu-item"]:
            item = page.locator(sel).filter(has_text="交付物").first
            if await item.count() > 0 and await item.is_visible():
                await item.click()
                clicked = True
                print("点击导航:", sel)
                break
        if not clicked:
            # 兜底：点矩阵里带"交付物"文本的块
            await page.get_by_text("交付物", exact=True).first.click()
            print("点击文本: 交付物")
        await page.wait_for_timeout(2000)

        # 找到 "+ 添加交付物" 按钮（清单视图）
        add_btns = page.get_by_role("button", name="添加交付物")
        print("清单视图添加按钮数量:", await add_btns.count())
        if await add_btns.count() == 0:
            print("页面当前文本:", (await page.locator("body").inner_text())[:400])
            await browser.close()
            return
        await add_btns.first.click()
        await page.wait_for_timeout(1000)
        dlg = page.locator(".el-dialog:visible")
        dlg_text = await dlg.inner_text()
        print("对话框含选择文件:", "选择文件" in dlg_text)
        print("对话框含自动上传:", "自动上传" in dlg_text)

        # 选文件
        await dlg.locator("input[type='file']").set_input_files(TMP_FILE)
        await page.wait_for_timeout(500)
        print("已选择提示:", "已选择" in await dlg.inner_text())
        # 名称由标准预填，强制改为测试名以唯一识别
        name_input = dlg.locator(".el-form-item", has_text="名称").locator("input")
        await name_input.fill("UI清单验证-上传")
        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(2500)

        # 验证
        ds = api("GET", f"/api/projects/{PID}/deliverables", tok=tok)
        d = next((x for x in ds if x["name"].startswith("UI清单验证")), None)
        print("创建成功:", bool(d), "| file_path:", (d or {}).get("file_path"))
        if d and d.get("file_path"):
            r = urllib.request.urlopen(BASE + "/uploads/" + d["file_path"], timeout=15)
            print("下载验证:", r.status == 200 and b"UI checklist upload verify" in r.read())
            # 列表展示链接
            table_text = await page.locator(".pdc-tab").inner_text()
            print("列表显示文件链接:", "tmp_upload_test" in table_text)
            api("DELETE", f"/api/deliverables/{d['id']}", tok=tok)
        await browser.close()
    print("DONE")

asyncio.run(main())
