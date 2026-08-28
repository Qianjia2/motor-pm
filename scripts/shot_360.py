# -*- coding: utf-8 -*-
"""Playwright 截图：打开客户360抽屉，检查各标签页渲染。"""
import asyncio, json, urllib.request
from playwright.async_api import async_playwright

BASE = "http://localhost:5002"

def login():
    req = urllib.request.Request(BASE + "/api/auth/login", method="POST",
        data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read().decode())
    return d["access_token"], d.get("refresh_token")

async def main():
    tok, rtok = login()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1500, "height": 900})
        await page.goto(BASE + "/", wait_until="load")
        await page.wait_for_timeout(800)
        await page.evaluate("""(args) => {
            localStorage.setItem('access_token', args.tok)
            localStorage.setItem('refresh_token', args.rtok)
            const u = {username:'admin', role:'admin', member_id: null, name: 'admin'}
            localStorage.setItem('user', JSON.stringify(u))
        }""", {"tok": tok, "rtok": rtok or ""})
        # createWebHistory：hash 无效，需按真实路径导航（localStorage 同源保留）
        await page.goto(BASE + "/clients", wait_until="load")
        await page.wait_for_timeout(2500)
        await page.screenshot(path="D:/AI/motor-pm/scripts/shot_1_list.png")
        # 页面信息
        txt = await page.evaluate("() => document.body.innerText.slice(0, 300)")
        print("page text:", txt.replace(chr(10), " | ")[:300])

        # 点击优普森 360
        try:
            await page.get_by_role("button", name="360").first.click(timeout=5000)
        except Exception as e:
            print("click 360 failed:", e)
            await page.screenshot(path="D:/AI/motor-pm/scripts/shot_fail.png")
            await browser.close()
            return
        await page.wait_for_timeout(2500)
        await page.screenshot(path="D:/AI/motor-pm/scripts/shot_2_drawer.png")

        # 抽屉里各标签页
        for tab, name in [("关系图谱", "graph"), ("沟通记录", "comms"), ("关联项目", "proj"), ("联系人", "cont")]:
            try:
                await page.get_by_role("tab", name=tab).click(timeout=3000)
                await page.wait_for_timeout(1200)
                await page.screenshot(path=f"D:/AI/motor-pm/scripts/shot_3_{name}.png")
                print("tab ok:", tab)
            except Exception as e:
                print("tab fail:", tab, e)
        await browser.close()
        print("DONE")

asyncio.run(main())
