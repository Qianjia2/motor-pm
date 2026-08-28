# -*- coding: utf-8 -*-
"""验证 el-tabs__content 高度是否随激活 pane 变化。"""
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

JS = """() => {
  const d = document.querySelector('.el-drawer');
  const q = (s) => d ? d.querySelector(s) : null;
  const r = (el) => el ? {
    h: Math.round(el.getBoundingClientRect().height),
    y: Math.round(el.getBoundingClientRect().y),
    sh: el.scrollHeight, ch: el.clientHeight,
  } : null;
  const body = q('.el-drawer__body');
  return {
    body: r(body),
    tabs: r(q('.el-tabs')),
    content: r(q('.el-tabs__content')),
    pane: r(q('.el-tabs__content .el-tab-pane')),
    paneOverflow: q('.el-tabs__content .el-tab-pane') ? getComputedStyle(q('.el-tabs__content .el-tab-pane')).overflowY : null,
    bodyScroll: body ? body.scrollHeight > body.clientHeight : false,
  };
}"""

async def main():
    tok, rtok = login()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1366, "height": 650})
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
        print("初始(概览):", json.dumps(await page.evaluate(JS), ensure_ascii=False))
        for tab in ["关系图谱", "沟通记录", "联系人", "关联项目", "商机概览"]:
            await page.get_by_role("tab", name=tab).click(timeout=3000)
            await page.wait_for_timeout(800)
            print(f"{tab}:", json.dumps(await page.evaluate(JS), ensure_ascii=False))
        await browser.close()

asyncio.run(main())
