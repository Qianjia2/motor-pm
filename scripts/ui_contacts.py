# -*- coding: utf-8 -*-
"""UI 回归：360 抽屉联系人新增/编辑/删除 + 抽屉宽度。"""
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
        await page.wait_for_timeout(600)
        await page.evaluate("""(args) => {
            localStorage.setItem('access_token', args.tok)
            localStorage.setItem('refresh_token', args.rtok)
            localStorage.setItem('user', JSON.stringify({username:'admin', role:'admin', member_id:null, name:'admin'}))
        }""", {"tok": tok, "rtok": rtok or ""})
        await page.goto(BASE + "/clients", wait_until="load")
        await page.wait_for_timeout(2000)
        await page.get_by_role("button", name="360").first.click(timeout=5000)
        await page.wait_for_timeout(2000)
        # 抽屉宽度
        w = await page.evaluate("() => document.querySelector('.el-drawer').getBoundingClientRect().width")
        print("drawer width:", round(w))
        # 联系人 tab
        await page.get_by_role("tab", name="联系人").click()
        await page.wait_for_timeout(800)
        body = await page.evaluate("() => document.querySelector('.el-drawer__body').innerText")
        print("联系人tab 空态:", "暂无联系人" in body)
        # 新增联系人（限定在抽屉内）
        await page.locator(".el-drawer").get_by_role("button", name="+ 新增").click()
        await page.wait_for_timeout(600)
        await page.get_by_placeholder("联系人姓名").fill("李四")
        await page.get_by_placeholder("如：技术总监").fill("采购总监")
        await page.locator(".el-dialog input.el-input__inner").nth(2).fill("13700001111")
        await page.locator(".el-dialog:visible").get_by_role("button", name="保存").click()
        await page.wait_for_timeout(1500)
        body = await page.evaluate("() => document.querySelector('.el-drawer__body').innerText")
        print("新增后显示:", "李四" in body and "采购总监" in body and "主要" in body)
        # 编辑
        await page.locator(".el-drawer").get_by_role("button", name="编辑").first.click()
        await page.wait_for_timeout(600)
        await page.get_by_placeholder("联系人姓名").fill("李四（改）")
        await page.locator(".el-dialog:visible").get_by_role("button", name="保存").click()
        await page.wait_for_timeout(1500)
        body = await page.evaluate("() => document.querySelector('.el-drawer__body').innerText")
        print("编辑后显示:", "李四（改）" in body)
        # 删除（ElMessageBox 是自定义对话框，点击"确定"确认）
        await page.locator(".el-drawer").get_by_role("button", name="删除").first.click()
        await page.wait_for_timeout(600)
        await page.locator(".el-message-box:visible").get_by_role("button", name="确定").click()
        await page.wait_for_timeout(1500)
        body = await page.evaluate("() => document.querySelector('.el-drawer__body').innerText")
        print("删除后空态:", "暂无联系人" in body)
        await browser.close()
        print("DONE")

asyncio.run(main())
