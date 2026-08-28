# -*- coding: utf-8 -*-
"""小视口复现：测量抽屉内部元素 + 滚动行为。"""
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
  const r = (el) => el ? {
    w: Math.round(el.getBoundingClientRect().width),
    h: Math.round(el.getBoundingClientRect().height),
    x: Math.round(el.getBoundingClientRect().x),
    y: Math.round(el.getBoundingClientRect().y),
    sh: el.scrollHeight, ch: el.clientHeight,
    overflowY: getComputedStyle(el).overflowY,
  } : null;
  const d = document.querySelector('.el-drawer');
  const body = d ? d.querySelector('.el-drawer__body') : null;
  const tabs = d ? d.querySelector('.el-tabs') : null;
  const nav = d ? d.querySelector('.el-tabs__nav-wrap') : null;
  const content = d ? d.querySelector('.el-tabs__content') : null;
  return {
    viewport: { w: innerWidth, h: innerHeight },
    drawer: r(d), body: r(body), tabs: r(tabs), nav: r(nav), content: r(content),
    panes: d ? [...d.querySelectorAll('.el-tab-pane')].map(p => ({id: p.id, ...r(p)})) : [],
    activePane: content ? r(content.querySelector('.el-tab-pane')) : null,
  };
}"""

async def run(page, label):
    await page.get_by_role("button", name="360").first.click(timeout=5000)
    await page.wait_for_timeout(2500)
    print("===", label, "===")
    print(json.dumps(await page.evaluate(JS), ensure_ascii=False))

async def main():
    tok, rtok = login()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for vp, label in [((1366, 650), "1366x650"), ((1500, 900), "1500x900")]:
            page = await browser.new_page(viewport={"width": vp[0], "height": vp[1]})
            await page.goto(BASE + "/", wait_until="load")
            await page.wait_for_timeout(600)
            await page.evaluate("""(args) => {
                localStorage.setItem('access_token', args.tok)
                localStorage.setItem('refresh_token', args.rtok)
                localStorage.setItem('user', JSON.stringify({username:'admin', role:'admin', member_id:null, name:'admin'}))
            }""", {"tok": tok, "rtok": rtok or ""})
            await page.goto(BASE + "/clients", wait_until="load")
            await page.wait_for_timeout(2000)
            try:
                await run(page, label)
            except Exception as e:
                print(label, "FAIL", e)
            await page.close()
        await browser.close()

asyncio.run(main())
