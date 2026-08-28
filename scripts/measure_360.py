# -*- coding: utf-8 -*-
"""Playwright 测量 360 抽屉各元素尺寸，定位渲染异常。"""
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
  const rect = (el) => el ? {
    w: Math.round(el.getBoundingClientRect().width),
    h: Math.round(el.getBoundingClientRect().height),
    x: Math.round(el.getBoundingClientRect().x),
    y: Math.round(el.getBoundingClientRect().y),
    display: getComputedStyle(el).display,
    sh: el.scrollHeight, ch: el.clientHeight,
  } : null;
  const drawer = document.querySelector('.el-drawer');
  const body = document.querySelector('.el-drawer__body');
  const tabs = document.querySelector('.el-tabs');
  const content = document.querySelector('.el-tabs__content');
  const svg = document.querySelector('.g-svg');
  const panes = [...document.querySelectorAll('.el-tab-pane')].map(p => ({
    label: p.id, ...rect(p), children: [...p.children].map(c => ({cls: c.className.slice(0,30), ...rect(c)}))
  }));
  return {
    drawer: rect(drawer), body: rect(body), tabs: rect(tabs), content: rect(content),
    svg: rect(svg), viewBox: svg ? svg.getAttribute('viewBox') : null,
    panes: panes,
  };
}"""

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
        await page.goto(BASE + "/clients", wait_until="load")
        await page.wait_for_timeout(2500)
        await page.get_by_role("button", name="360").first.click(timeout=5000)
        await page.wait_for_timeout(2500)
        print("=== 默认(商机概览) ===")
        print(json.dumps(await page.evaluate(JS), ensure_ascii=False))
        for tab in ["关系图谱", "沟通记录", "联系人", "关联项目"]:
            try:
                await page.get_by_role("tab", name=tab).click(timeout=3000)
                await page.wait_for_timeout(900)
                print(f"=== {tab} ===")
                print(json.dumps(await page.evaluate(JS), ensure_ascii=False))
            except Exception as e:
                print(tab, "FAIL", e)
        # 页面控制台错误
        errors = page._console_messages if hasattr(page, "_console_messages") else None
        await browser.close()

asyncio.run(main())
