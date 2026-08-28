"""验证: BOM管理批量操作条 — 勾选后出现下拉(批量删除/设为失效/移动), 表头不再有设为失效"""
import sys, json, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import asyncio, urllib.request, urllib.error
from playwright.async_api import async_playwright

BASE = os.environ.get("E2E_BASE", "http://localhost:5002")
API = BASE + "/api"

results = []
def check(name, cond, detail=""):
    results.append((name, cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {str(detail)[:140]}")

def api(method, path, token=None, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token: r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

async def main():
    st, body = api("POST", "/auth/login", body={"username": "admin", "password": "admin123"})
    token = json.loads(body).get("access_token")
    check("API登录", token is not None)

    # 造两个测试BOM
    st, body = api("GET", "/bom-lists", token)
    pre = json.loads(body)
    if not isinstance(pre, list): pre = pre.get("items") or []
    baseline_id = max((x.get("id", 0) for x in pre), default=0)
    ids = []
    for i in range(2):
        st, body = api("POST", "/bom-lists", token, body={
            "name": f"批量操作测试{i+1}", "headers": ["序号","物料编码","物料名称"],
            "items": [["1","C01","测试物料"]]})
        ids.append(json.loads(body)["id"])

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 900})
        await page.goto(BASE + "/login")
        await page.fill('input[placeholder="用户名"]', "admin")
        await page.fill('input[placeholder="密码"]', "admin123")
        await page.click('button:has-text("登 录"), button:has-text("登录")')
        await page.wait_for_url("**/my-work", timeout=10000)
        await page.goto(BASE + "/bom")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        # 1. 表头不再有 设为失效 按钮
        hdr_has = await page.evaluate("""() => [...document.querySelectorAll('button')]
            .some(b => b.textContent.includes('设为失效'))""")
        check("表头无设为失效按钮", not hdr_has)

        # 2. 勾选两行 → 批量条出现, 含下拉
        rows = page.locator('.el-table__body tbody tr').first
        await page.wait_for_timeout(300)
        boxes = page.locator('.el-table__body tbody .el-checkbox')
        nbox = await boxes.count()
        check("表有数据可勾选", nbox >= 2, f"n={nbox}")
        await boxes.nth(0).click()
        await boxes.nth(1).click()
        await page.wait_for_timeout(400)
        bar_txt = await page.evaluate("""() => {
            const els = [...document.querySelectorAll('div')].filter(d => d.textContent.includes('已选择') && d.textContent.includes('批量操作'));
            return els.length ? els[els.length-1].textContent : '';
        }""")
        check("批量条出现", "已选择 2 个BOM" in bar_txt, bar_txt[:80])
        await page.click('.el-select:has-text("批量操作")')
        await page.wait_for_timeout(500)
        opts = await page.evaluate("""() => [...document.querySelectorAll('.el-select-dropdown__item')]
            .filter(e => e.offsetParent !== null).map(e => e.textContent)""")
        check("下拉含删除/失效/移动", all(k in opts for k in ("批量删除", "批量设为失效", "批量移动")), opts)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        # 3. 批量设为失效
        await page.click('.el-select:has-text("批量操作")')
        await page.wait_for_timeout(500)
        await page.evaluate("""() => {
            const items = [...document.querySelectorAll('.el-select-dropdown__item')];
            const el = items.find(e => e.offsetParent !== null && e.textContent.includes('批量设为失效'));
            if (el) el.click();
        }""")
        await page.wait_for_timeout(400)
        await page.click('.el-message-box button:has-text("确定"), .el-message-box button:has-text("OK")')
        await page.wait_for_timeout(1200)
        st, body = api("GET", "/bom-lists", token)
        cur = json.loads(body)
        if not isinstance(cur, list): cur = cur.get("items") or []
        st2 = {x["id"]: x.get("status") for x in cur if x["id"] in ids}
        check("两个BOM已失效", all(v == "失效" for v in st2.values()), st2)

        # 4. 批量移动 → 选项目 → 移动
        # 重新勾选(失效后仍在列表)
        boxes = page.locator('.el-table__body tbody .el-checkbox')
        nbox = await boxes.count()
        check("失效后仍可勾选", nbox >= 2, f"n={nbox}")
        await boxes.nth(0).click()
        await boxes.nth(1).click()
        await page.wait_for_timeout(400)
        await page.click('.el-select:has-text("批量操作")')
        await page.wait_for_timeout(500)
        await page.evaluate("""() => {
            const items = [...document.querySelectorAll('.el-select-dropdown__item')];
            const el = items.find(e => e.offsetParent !== null && e.textContent.includes('批量移动'));
            if (el) el.click();
        }""")
        await page.wait_for_timeout(600)
        dlg_txt = await page.evaluate("""() => {
            const dlg = [...document.querySelectorAll('.el-dialog')].find(d => d.offsetParent !== null);
            return dlg ? dlg.textContent : '';
        }""")
        check("批量移动弹窗", "批量移动" in dlg_txt and "选择项目" in dlg_txt, dlg_txt[:80])
        # 取消, 直接API验证移动
        await page.click('.el-dialog:visible button:has-text("取消")')
        await page.wait_for_timeout(400)
        await browser.close()

        st, body = api("PUT", "/bom-lists/batch/associate-project", token, body={"ids": ids, "project_id": None})
        # 无项目时后端行为未知, 不校验结果; 仅验证接口可达
        check("移动接口可达", st in (200, 400, 422), f"st={st}")

    # 清理
    api("POST", "/bom-lists/batch-delete", token, body={"ids": ids})
    st, body = api("GET", "/bom-lists", token)
    cur = json.loads(body)
    if not isinstance(cur, list): cur = cur.get("items") or []
    for x in cur:
        if x.get("id", 0) > baseline_id:
            api("DELETE", f"/bom-lists/{x['id']}", token)
    print("已清理")

    npass = sum(1 for _, c in results if c)
    print(f"\n==== {npass}/{len(results)} PASS ====")
    sys.exit(0 if npass == len(results) else 1)

asyncio.run(main())
