# -*- coding: utf-8 -*-
"""回归：知识库页面 打开 PDF → 真实预览 → 下载原文件链接可用。"""
import asyncio, json, urllib.request
from playwright.async_api import async_playwright

BASE = "http://localhost:5002"

def login():
    req = urllib.request.Request(BASE + "/api/auth/login", method="POST",
        data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())["access_token"]

async def main():
    tok = login()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 950})
        errors = []
        bad_status = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("response", lambda r: bad_status.append(f"{r.status} {r.url}") if r.status >= 400 else None)
        await page.goto(BASE + "/", wait_until="load")
        await page.wait_for_timeout(600)
        await page.evaluate("""(args) => {
            localStorage.setItem('access_token', args.tok)
            localStorage.setItem('user', JSON.stringify({username:'admin', role:'admin', member_id:null, name:'admin'}))
        }""", {"tok": tok})
        await page.goto(BASE + "/knowledge", wait_until="load")
        await page.wait_for_timeout(3000)
        bad_status.clear()

        # 找一个 PDF 卡片
        card = None
        titles = page.locator(".fs-doc-card .fs-card-title")
        n = await titles.count()
        print(f"文档卡片数: {n}")
        for i in range(n):
            t = await titles.nth(i).inner_text()
            if ".pdf" in t.lower():
                card = titles.nth(i)
                print("目标 PDF:", t.strip())
                break
        if card is None:
            print("未找到 PDF 卡片")
            await browser.close()
            return

        # 点击该卡片所在行的「预览」按钮
        preview_btn = card.locator("xpath=ancestor::div[contains(@class,'fs-doc-card')]//button").filter(has_text="预览").first
        await preview_btn.click()
        await page.wait_for_timeout(3000)

        overlay = page.locator(".fs-overlay")
        print("遮罩存在:", await overlay.count())
        frames = [f for f in page.frames if f.url.startswith("about:srcdoc") and f.parent_frame]
        if frames:
            body = await frames[0].locator("body").inner_text()
            print("预览iframe 内容开头:", body[:80].replace("\n", " "))
            print("预览为真实文件(非回退):", "原始文件不在本地" not in body)
        else:
            print("无预览iframe")

        # 下载原文件链接
        link = page.locator("a.fs-link-text", has_text="下载原文件").first
        href = await link.get_attribute("href")
        print("下载链接:", href[:80])
        print("链接含 token:", "token=" in href)
        if href:
            req = urllib.request.Request(BASE + href)
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                print(f"下载: {r.status} | {len(data)}B | PDF={data[:4]==b'%PDF'}")
            except Exception as e:
                print("下载失败:", e)

        print("页面JS错误:", errors if errors else "无")
        print(">=400 响应:", bad_status if bad_status else "无")
        await browser.close()
    print("DONE")

asyncio.run(main())
