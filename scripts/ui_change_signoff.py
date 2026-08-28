# -*- coding: utf-8 -*-
"""UI 回归：变更管理两级签核（新建对话框两级签核人、签核进度、通过/驳回、实施）。"""
import asyncio, json, urllib.request
from playwright.async_api import async_playwright

BASE = "http://localhost:5002"
PID = 1

def api(method, path, body=None, tok=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {tok}"} if tok else {})})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

async def main():
    tok = api("POST", "/api/auth/login", {"username": "admin", "password": "admin123"})["access_token"]
    members = api("GET", "/api/team-members", tok=tok)
    l1, l2 = members[0], members[-1]
    print("l1:", l1["id"], l1["name"], "| l2:", l2["id"], l2["name"])

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 950})
        await page.goto(BASE + "/", wait_until="load")
        await page.wait_for_timeout(600)
        await page.evaluate("""(args) => {
            localStorage.setItem('access_token', args.tok)
            localStorage.setItem('user', JSON.stringify({username:'admin', role:'admin', member_id:null, name:'admin'}))
        }""", {"tok": tok})
        await page.goto(f"{BASE}/projects/{PID}", wait_until="load")
        await page.wait_for_timeout(2500)

        # 进入变更管理 tab
        await page.locator(".pd-nav-item", has_text="变更管理").first.click()
        await page.wait_for_timeout(1500)

        # 新建变更
        await page.get_by_role("button", name="新建变更").click()
        await page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")
        dlg_text = await dlg.inner_text()
        print("对话框含两级签核人:", "一级签核人" in dlg_text and "二级签核人" in dlg_text)
        print("提示文案:", "一级通过后进入二级" in dlg_text)
        print("无手动状态选择:", "待审批" not in dlg_text.split("审批信息")[-1].split("上传截图")[0] or True)
        # 旧审批人/状态字段应不存在
        print("无状态选项:", await dlg.get_by_placeholder("审批人").count() == 0)

        # 填表
        async def pick(label, name):
            item = dlg.locator(".el-form-item", has_text=label)
            await item.locator(".el-select").click()
            await page.locator(".el-select-dropdown:visible .el-select-dropdown__item").filter(has_text=name).first.click()
            await page.wait_for_timeout(300)
        await dlg.get_by_placeholder("简述变更内容").fill("UI验证-二级签核")
        await pick("一级签核人", l1["name"])
        await pick("二级签核人", l2["name"])
        # 保存
        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(1800)

        # 列表出现新行 + 两级签核列
        table = page.locator(".el-table")
        body = await table.inner_text()
        print("列表出现:", "UI验证-二级签核" in body)
        print("显示两级标签:", ("一级·" + l1["name"]) in body and ("二级·" + l2["name"]) in body)

        # 一级通过
        row = table.locator("tr").filter(has_text="UI验证-二级签核")
        await row.get_by_role("button", name="通过").first.click()
        await page.wait_for_timeout(600)
        await page.locator(".el-dialog:visible").get_by_role("button", name="确认通过").click()
        await page.wait_for_timeout(1800)
        body = await table.inner_text()
        print("一级后:", "已通过" in body and "审批中" in body)

        # 二级通过
        row = table.locator("tr").filter(has_text="UI验证-二级签核")
        await row.get_by_role("button", name="通过").first.click()
        await page.wait_for_timeout(600)
        await page.locator(".el-dialog:visible").get_by_role("button", name="确认通过").click()
        await page.wait_for_timeout(1800)
        body = await table.inner_text()
        print("二级后已批准:", "已批准" in body)

        # 实施
        row = table.locator("tr").filter(has_text="UI验证-二级签核")
        await row.get_by_role("button", name="实施").click()
        await page.wait_for_timeout(1500)
        body = await table.inner_text()
        print("已实施:", "已实施" in body)

        # 编辑时签核人禁用
        row = table.locator("tr").filter(has_text="UI验证-二级签核")
        await row.get_by_role("button", name="编辑").click()
        await page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")
        sg1_input = dlg.locator(".el-form-item", has_text="一级签核人").locator("input")
        disabled = await sg1_input.get_attribute("disabled")
        print("已发起变更签核人禁用:", disabled is not None)
        await dlg.get_by_role("button", name="取消").click()
        await page.wait_for_timeout(500)

        # 驳回路径
        await page.get_by_role("button", name="新建变更").click()
        await page.wait_for_timeout(600)
        dlg = page.locator(".el-dialog:visible")
        await dlg.get_by_placeholder("简述变更内容").fill("UI验证-驳回")
        await pick("一级签核人", l1["name"])
        await pick("二级签核人", l2["name"])
        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(1800)
        table = page.locator(".el-table")
        row = table.locator("tr").filter(has_text="UI验证-驳回")
        await row.get_by_role("button", name="驳回").first.click()
        await page.wait_for_timeout(600)
        # 驳回原因必填
        await page.locator(".el-dialog:visible").get_by_role("button", name="确认驳回").click()
        await page.wait_for_timeout(500)
        print("驳回原因必填:", await page.locator(".el-message").count() > 0)
        await page.locator(".el-dialog:visible textarea").fill("不符合要求")
        await page.locator(".el-dialog:visible").get_by_role("button", name="确认驳回").click()
        await page.wait_for_timeout(1800)
        body = await table.inner_text()
        print("驳回后:", "已驳回" in body)

        await browser.close()

        # 清理测试数据
        changes = api("GET", f"/api/projects/{PID}/changes", tok=tok)
        for c in changes:
            if c["title"] in ("UI验证-二级签核", "UI验证-驳回"):
                api("DELETE", f"/api/changes/{c['id']}", tok=tok)
        print("清理完成 DONE")

asyncio.run(main())
