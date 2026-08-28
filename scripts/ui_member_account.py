# -*- coding: utf-8 -*-
"""UI 回归：人员与账号 —— 职务=系统设置角色（下拉可自定义），保存后角色自动入角色表，
项目详情添加成员可选；角色权限=账号访问权限（管理员/编辑者）；账号关联+权限保存。"""
import asyncio, json, urllib.request
from playwright.async_api import async_playwright

BASE = "http://localhost:5002"
TEST_NAME = "UI验证-职务角色"
TEST_NAME2 = "UI验证-补账号"
TEST_USER = "ui_role_sep_01"
TEST_USER2 = "ui_role_sep_02"
CUSTOM_ROLE = "UI验证-自定义角色"

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

def deactivate_test_data(tok):
    for is_active in (True, False):
        m = api("GET", f"/api/team-members?is_active={str(is_active).lower()}", tok=tok)
        for x in m:
            if x["name"] in (TEST_NAME, TEST_NAME2):
                api("PUT", f"/api/team-members/{x['id']}", {"is_active": False}, tok=tok)
    users = api("GET", "/api/auth/users", tok=tok)
    for u in users:
        if u["username"] in (TEST_USER, TEST_USER2):
            api("DELETE", f"/api/auth/users/{u['id']}", tok=tok)
    roles = api("GET", "/api/lookups/roles", tok=tok)
    for r in roles:
        if r["name"] == CUSTOM_ROLE:
            api("DELETE", f"/api/lookups/roles/{r['id']}", tok=tok)

async def main():
    tok = api("POST", "/api/auth/login", {"username": "admin", "password": "admin123"})["access_token"]
    deactivate_test_data(tok)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1500, "height": 900})
        await page.goto(BASE + "/", wait_until="load")
        await page.wait_for_timeout(600)
        await page.evaluate("""(args) => {
            localStorage.setItem('access_token', args.tok)
            localStorage.setItem('user', JSON.stringify({username:'admin', role:'admin', member_id:null, name:'admin'}))
        }""", {"tok": tok})
        await page.goto(BASE + "/resources", wait_until="load")
        await page.wait_for_timeout(2000)
        await page.get_by_role("tab", name="人员与账号").click()
        await page.wait_for_timeout(1500)

        # ── 场景1：职务下拉选系统设置角色（软件工程师），角色权限=编辑者，账号+权限 ──
        await page.get_by_role("button", name="新增人员").click()
        await page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")
        dlg_text = await dlg.inner_text()
        print("职务下拉存在:", "职务" in dlg_text)
        print("角色权限字段存在:", "角色权限" in dlg_text)

        await dlg.get_by_label("姓名").fill(TEST_NAME)
        # 职务 = 软件工程师（来自系统设置角色表）
        title_item = dlg.locator(".el-form-item", has_text="职务")
        await title_item.locator(".el-select").click()
        await page.wait_for_timeout(600)
        opts = await page.locator(".el-select-dropdown:visible .el-select-dropdown__item").all_inner_texts()
        print("下拉含系统设置角色(项目经理/软件工程师):", "项目经理" in opts and "软件工程师" in opts)
        await page.locator(".el-select-dropdown:visible .el-select-dropdown__item").filter(has_text="软件工程师").first.click()
        await page.wait_for_timeout(300)
        # 角色权限 = 编辑者
        role_item = dlg.locator(".el-form-item", has_text="角色权限")
        await role_item.locator(".el-select").click()
        await page.locator(".el-select-dropdown:visible .el-select-dropdown__item").filter(has_text="编辑者").first.click()
        await page.wait_for_timeout(300)
        await dlg.get_by_placeholder("登录账号").fill(TEST_USER)
        await dlg.locator('input[type="password"]').fill("test123456")
        await dlg.locator('tbody input[value="edit"]').first.click()
        await page.wait_for_timeout(300)
        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(2000)

        table = page.locator(".el-tab-pane:visible .el-table")
        row = table.locator("tr").filter(has_text=TEST_NAME).first
        cells = await row.locator("td").all_inner_texts()
        print("职务列=软件工程师:", "软件工程师" in cells[2], "|", cells[2].strip())
        print("关联账号显示:", TEST_USER in cells[3])
        print("角色权限列=编辑者:", "编辑者" in cells[4])

        users = api("GET", "/api/auth/users", tok=tok)
        u = next((x for x in users if x["username"] == TEST_USER), None)
        print("账号已关联成员:", bool(u and u.get("member_name") == TEST_NAME), "|", (u or {}).get("member_name"))
        print("权限已保存且未双重编码:", bool(u and u.get("permissions") not in ("{}", "", "null")))

        # 编辑回显：职务/角色权限各自独立
        await row.get_by_role("button", name="编辑").click()
        await page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")
        tsel = dlg.locator(".el-form-item", has_text="职务").locator(".el-select")
        print("编辑职务=软件工程师:", "软件工程师" in await tsel.inner_text())
        rsel = dlg.locator(".el-form-item", has_text="角色权限").locator(".el-select")
        print("编辑角色权限=编辑者:", "编辑者" in await rsel.inner_text())
        await dlg.get_by_role("button", name="取消").click()
        await page.wait_for_timeout(500)

        # ── 场景2：人员补账号 + 自定义职务 → 自动入角色表 ──
        await page.get_by_role("button", name="新增人员").click()
        await page.wait_for_timeout(600)
        dlg = page.locator(".el-dialog:visible")
        await dlg.get_by_label("姓名").fill(TEST_NAME2)
        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(1500)

        table = page.locator(".el-tab-pane:visible .el-table")
        row2 = table.locator("tr").filter(has_text=TEST_NAME2).first
        await row2.get_by_role("button", name="编辑").click()
        await page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")
        await dlg.get_by_placeholder("登录账号").fill(TEST_USER2)
        await dlg.locator('input[type="password"]').fill("test123456")
        # 角色权限改为 查看者
        rsel = dlg.locator(".el-form-item", has_text="角色权限").locator(".el-select")
        await rsel.click()
        await page.locator(".el-select-dropdown:visible .el-select-dropdown__item").filter(has_text="查看者").first.click()
        await page.wait_for_timeout(300)
        # 自定义职务：输入并回车（allow-create）
        tsel = dlg.locator(".el-form-item", has_text="职务").locator(".el-select")
        await tsel.click()
        await page.keyboard.type(CUSTOM_ROLE)
        await page.wait_for_timeout(300)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(300)
        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(1800)

        table = page.locator(".el-tab-pane:visible .el-table")
        body = await table.inner_text()
        print("补账号后显示关联账号:", TEST_USER2 in body)
        users = api("GET", "/api/auth/users", tok=tok)
        u2 = next((x for x in users if x["username"] == TEST_USER2), None)
        print("补账号已关联成员:", bool(u2 and u2.get("member_name") == TEST_NAME2), "|", (u2 or {}).get("member_name"))
        print("补账号角色=查看者:", (u2 or {}).get("role") == "viewer", "|", (u2 or {}).get("role"))

        # 自定义职务已自动进入角色表（项目详情添加成员即用此表）
        roles_now = api("GET", "/api/lookups/roles", tok=tok)
        print("自定义角色已入角色表:", any(r["name"] == CUSTOM_ROLE for r in roles_now))
        # 打开新增人员对话框，下拉里应能看到自定义角色
        await page.get_by_role("button", name="新增人员").click()
        await page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")
        title_item = dlg.locator(".el-form-item", has_text="职务")
        await title_item.locator(".el-select").click()
        await page.wait_for_timeout(600)
        opts = await page.locator(".el-select-dropdown:visible .el-select-dropdown__item").all_inner_texts()
        print("下拉含自定义角色:", CUSTOM_ROLE in opts)
        await page.keyboard.press("Escape")
        await dlg.get_by_role("button", name="取消").click()
        await page.wait_for_timeout(400)

        await browser.close()

    deactivate_test_data(tok)
    print("清理完成 DONE")

asyncio.run(main())
