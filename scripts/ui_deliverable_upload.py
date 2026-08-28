# -*- coding: utf-8 -*-
"""UI 回归：交付物矩阵-添加交付物-上传文件（选文件→保存自动上传→列表链接可下载）。"""
import asyncio, json, urllib.request, os
from playwright.async_api import async_playwright

BASE = "http://localhost:5002"
PID = 1
TEST_NAME = "UI验证-交付物上传"
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
    # 清理上一轮残留
    for d in api("GET", f"/api/projects/{PID}/deliverables", tok=tok):
        if d["name"] == TEST_NAME:
            api("DELETE", f"/api/deliverables/{d['id']}", tok=tok)

    with open(TMP_FILE, "w", encoding="utf-8") as f:
        f.write("UI upload regression test content - 电机测试\n" * 10)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 950})
        await page.goto(BASE + "/", wait_until="load")
        await page.wait_for_timeout(600)
        await page.evaluate("""(args) => {
            localStorage.setItem('access_token', args.tok)
            localStorage.setItem('user', JSON.stringify({username:'admin', role:'admin', member_id:null, name:'admin'}))
        }""", {"tok": tok})
        await page.goto(f"{BASE}/projects/{PID}?tab=deliverables", wait_until="load")
        await page.wait_for_timeout(2500)

        # 添加交付物
        await page.get_by_role("button", name="添加交付物").click()
        await page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")
        await dlg.get_by_placeholder("如：电磁可行性分析报告").fill(TEST_NAME)
        # 阶段必选
        phase_item = dlg.locator(".el-form-item", has_text="阶段")
        await phase_item.locator(".el-select").click()
        await page.wait_for_timeout(500)
        await page.locator(".el-select-dropdown:visible .el-select-dropdown__item").first.click()
        await page.wait_for_timeout(300)
        # 选择文件（el-upload auto-upload=false）
        await dlg.locator("input[type='file']").set_input_files(TMP_FILE)
        await page.wait_for_timeout(500)
        dlg_text = await dlg.inner_text()
        print("已选择文件提示:", "已选择" in dlg_text)
        await dlg.get_by_role("button", name="保存").click()
        await page.wait_for_timeout(2500)

        # 列表出现 + 文件链接
        table = page.locator(".el-table")
        row = table.locator("tr").filter(has_text=TEST_NAME).first
        cells = await row.locator("td").all_inner_texts()
        joined = "|".join(cells)
        print("列表出现新交付物:", TEST_NAME in joined)
        print("列表含文件链接:", "tmp_upload_test" in joined)

        # API 复核：file_path 已保存
        ds = api("GET", f"/api/projects/{PID}/deliverables", tok=tok)
        d = next((x for x in ds if x["name"] == TEST_NAME), None)
        fp = (d or {}).get("file_path") or ""
        print("file_path 已保存:", bool(fp), "|", fp)
        # 文件在磁盘上存在
        import subprocess
        if fp:
            local = fp.replace("/", "\\")
            # UPLOAD_DIR 为 NAS 路径；检查 /uploads 链接可访问即可
            print("本机可查路径:", local)

        # 通过 /uploads 链接下载验证
        if fp:
            try:
                r = urllib.request.urlopen(BASE + "/uploads/" + fp, timeout=15)
                body_bytes = r.read()
                print("链接可下载(200):", r.status == 200, "| 内容匹配:", b"UI upload regression" in body_bytes)
            except Exception as e:
                print("链接下载失败:", e)

        # 编辑回显：对话框里显示已上传文件链接
        await row.get_by_role("button", name="编辑").click()
        await page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")
        print("编辑对话框显示已上传文件:", "tmp_upload_test" in await dlg.inner_text())
        await dlg.get_by_role("button", name="取消").click()
        await page.wait_for_timeout(400)

        await browser.close()

    # 清理：删除测试交付物 + 磁盘文件
    for d in api("GET", f"/api/projects/{PID}/deliverables", tok=tok):
        if d["name"] == TEST_NAME:
            api("DELETE", f"/api/deliverables/{d['id']}", tok=tok)
            print("已删除测试交付物:", d["id"])
    print("清理完成 DONE")

asyncio.run(main())
