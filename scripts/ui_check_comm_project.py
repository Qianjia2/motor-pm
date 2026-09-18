"""浏览器端验证: 沟通记录关联项目(客户360 筛选/新增,项目详情沟通面板,商机弹窗回归)。

用法: python scripts/ui_check_comm_project.py
"""
import sys
import requests
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5002"
API = BASE + "/api"
ok, fail = 0, []


def check(name, cond, extra=""):
    global ok
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail.append(name)
        print(f"  FAIL  {name}  {extra}")


# ── 准备: 找一个有项目的客户 ──
s = requests.Session()
tok = s.post(f"{API}/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
projects = s.get(f"{API}/projects", params={"page_size": 100}, headers=H).json()["data"]
proj = next(p for p in projects if p.get("client") and p["is_active"])
pid, cid, pname = proj["id"], proj["client"]["id"], proj["name"]
client_name = proj["client"]["name"]
print(f"  使用 客户「{client_name}」#{cid} / 项目「{pname}」#{pid}")

created_ids = []
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 950})

        # ── 登录 ──
        page.goto(f"{BASE}/login")
        page.fill("input[placeholder='用户名']", "admin")
        page.fill("input[placeholder='密码']", "admin123")
        page.click("button:has-text('登录')")
        page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
        check("登录成功", "/login" not in page.url, page.url)

        # ── (g) 硬刷新直达项目页 comms 页签 ──
        page.goto(f"{BASE}/projects/{pid}?tab=comms")
        page.wait_for_timeout(2500)
        body = page.inner_text("body")
        check("(g) ?tab=comms 直达沟通面板",
              "客户沟通记录" in body, body[:200].replace("\n", " "))

        # ── (b) 项目页新增一条带项目的沟通 ──
        page.click("button:has-text('新增')")
        page.wait_for_selector(".el-dialog:visible")
        dlg = page.locator(".el-dialog:visible")
        check("(b) 弹窗带「关联项目」字段", dlg.locator("text=关联项目").count() > 0,
              dlg.inner_text()[:200])
        proj_field = dlg.locator(".el-form-item:has-text('关联项目') .el-select").first.inner_text().strip()
        check("(b) 关联项目已预选本项目", pname in proj_field, f"{proj_field!r}")
        dlg.locator("input[placeholder*='样机测试进度确认']").fill("UI冒烟-项目侧新增")
        dlg.locator("textarea").first.fill("由 UI 冒烟脚本创建")
        dlg.locator("button:has-text('保存')").click()
        page.wait_for_timeout(2000)
        check("(b) 保存后项目面板出现该记录", "UI冒烟-项目侧新增" in page.inner_text("body"))

        # 记录 id 供清理
        rows = s.get(f"{API}/projects/{pid}/communications", headers=H).json()
        mine = [r for r in rows if r["subject"] == "UI冒烟-项目侧新增"]
        if mine:
            created_ids.append(mine[0]["id"])

        # ── (c) 客户 360 同步可见 ──
        page.goto(f"{BASE}/clients")
        page.wait_for_selector(".el-table__row")
        page.click(f".el-table__row:has-text('{client_name}') >> text=360")
        page.wait_for_selector(".el-drawer")
        page.click(".el-drawer .el-tabs__item:has-text('沟通记录')")
        page.wait_for_timeout(1200)
        drawer = page.locator(".el-drawer")
        check("(c) 客户360 沟通记录里同步可见", "UI冒烟-项目侧新增" in drawer.inner_text())
        check("(c) 记录带项目标签", "📎" in drawer.inner_text(), drawer.inner_text()[-300:])

        # ── (a) 按项目筛选 ──
        title_before = drawer.locator(".p360-title:has-text('沟通记录')").inner_text()
        check("(a) 未筛选时只显示总数", "/" not in title_before, title_before)
        drawer.locator(".comm-filter .el-select").click()
        page.wait_for_timeout(600)
        page.click(".el-select-dropdown:visible .el-select-dropdown__item:has-text('未关联项目')")
        page.wait_for_timeout(900)
        drawer = page.locator(".el-drawer")
        after_unlinked = drawer.inner_text()
        check("(a) 选「未关联项目」后本项目记录被过滤掉",
              "UI冒烟-项目侧新增" not in after_unlinked)
        title_unlinked = drawer.locator(".p360-title:has-text('沟通记录')").inner_text()
        check("(a) 筛选后变成 命中/总数 且收窄",
              "/" in title_unlinked and title_unlinked != title_before,
              f"{title_before!r} → {title_unlinked!r}")

        drawer.locator(".comm-filter .el-select").click()
        page.wait_for_timeout(600)
        page.click(f".el-select-dropdown:visible .el-select-dropdown__item:has-text('{pname}')")
        page.wait_for_timeout(900)
        drawer = page.locator(".el-drawer")
        check("(a) 按本项目筛选后只剩本项目的记录",
              "UI冒烟-项目侧新增" in drawer.inner_text())

        # ── (h) 商机关联项目下拉(loadProjects 修复的回归面) ──
        page.goto(f"{BASE}/clients")            # 抽屉还开着会挡住表格,直接重载页面
        page.wait_for_selector(".el-table__row")
        page.click(f".el-table__row:has-text('{client_name}') >> text=商机")
        page.wait_for_selector(".el-dialog:visible")
        odlg = page.locator(".el-dialog:visible")
        check("(h) 商机弹窗仍能打开", odlg.locator("text=商机名称").count() > 0, odlg.inner_text()[:150])
        odlg.locator(".el-form-item:has-text('关联项目') .el-select").click()
        page.wait_for_timeout(800)
        opts = page.locator(".el-select-dropdown:visible .el-select-dropdown__item").count()
        check("(h) 商机「关联项目」下拉有选项(修复前恒为空)", opts > 0, f"{opts} 个选项")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ── (e) 清空项目并保存 → 重开确认未关联 ──
        page.goto(f"{BASE}/clients")
        page.wait_for_selector(".el-table__row")
        page.click(f".el-table__row:has-text('{client_name}') >> text=360")
        page.wait_for_selector(".el-drawer")
        page.click(".el-drawer .el-tabs__item:has-text('沟通记录')")
        page.wait_for_timeout(1000)
        page.click(".el-drawer .comm-item:has-text('UI冒烟-项目侧新增')")
        page.wait_for_selector(".el-dialog:visible")
        dlg = page.locator(".el-dialog:visible")
        proj_sel = dlg.locator(".el-form-item:has-text('关联项目') .el-select")
        proj_sel.hover()                       # clearable 的清除图标只在 hover 时可见
        page.wait_for_timeout(400)
        proj_sel.locator(".el-select__clear").click()
        page.wait_for_timeout(400)
        dlg.locator("button:has-text('保存')").click()
        page.wait_for_timeout(1800)

        # 重新打开确认
        page.click(".el-drawer .comm-item:has-text('UI冒烟-项目侧新增')")
        page.wait_for_selector(".el-dialog:visible")
        page.wait_for_timeout(800)
        dlg = page.locator(".el-dialog:visible")
        val = dlg.locator(".el-form-item:has-text('关联项目') input").first.input_value()
        check("(e) 清空项目保存后重开为空", val == "", f"{val!r}")

        # 后端也确认已解除
        rows = s.get(f"{API}/clients/{cid}/communications", headers=H).json()
        rec = [r for r in rows if r["subject"] == "UI冒烟-项目侧新增"]
        check("(e) 后端已解除关联", rec and rec[0]["project_id"] is None,
              str(rec[0] if rec else None))

        # ── (c) 项目页删除 → 客户侧同步 ──
        if created_ids:
            # (e) 刚把关联清掉了,先重新关联,才能从项目侧验证删除
            s.put(f"{API}/communications/{created_ids[0]}", headers=H, json={"project_id": pid})
            page.goto(f"{BASE}/projects/{pid}?tab=comms")
            page.wait_for_timeout(2200)
            page.click(".cc-item:has-text('UI冒烟-项目侧新增')")
            page.wait_for_selector(".el-dialog:visible")
            page.locator(".el-dialog:visible button:has-text('删除')").click()
            page.wait_for_selector(".el-message-box", timeout=8000)
            page.click(".el-message-box button:has-text('确定')")
            page.wait_for_timeout(1800)
            check("(c) 项目页删除后列表不再显示",
                  "UI冒烟-项目侧新增" not in page.inner_text("body"))
            left = s.get(f"{API}/clients/{cid}/communications", headers=H).json()
            check("(c) 客户侧同步删除",
                  not [r for r in left if r["subject"] == "UI冒烟-项目侧新增"])
            created_ids.clear()

        # ── (f) 无客户项目: 提示 + 只读 ──
        r = s.post(f"{API}/projects", headers=H,
                   json={"name": "UI冒烟-无客户项目", "code": "UI-SMOKE-NOCLIENT"})
        check("(f) 准备无客户项目", r.status_code == 201, r.text[:150])
        if r.status_code == 201:
            nopid = r.json()["id"]
            page.goto(f"{BASE}/projects/{nopid}?tab=comms")
            page.wait_for_timeout(2500)
            b = page.inner_text("body")
            check("(f) 显示未关联客户提示", "该项目未关联客户" in b, b[:200].replace("\n", " "))
            check("(f) 无新增按钮",
                  page.locator(".card-header button:has-text('新增')").count() == 0)
            # 清理: 直接删库行(该表由 __table__.columns 决定,新项目无依赖数据)
            import sqlite3
            conn = sqlite3.connect("data/motor_pm_v2.db")
            tables = [t[0] for t in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            for t in tables:
                if t.startswith("sqlite_"):
                    continue
                # 表名要加引号: 库里存在名为 transaction 的表,裸写是 SQL 关键字
                cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{t}")')]
                if "project_id" in cols:
                    conn.execute(f'DELETE FROM "{t}" WHERE project_id=?', (nopid,))
            conn.execute('DELETE FROM "project" WHERE id=?', (nopid,))
            conn.commit()
            print(f"        已清理无客户测试项目 #{nopid}")

        browser.close()
finally:
    for i in created_ids:
        s.delete(f"{API}/communications/{i}", headers=H)
        print(f"  清理遗留沟通记录 #{i}")

print(f"\n{ok} passed, {len(fail)} failed" + (f" → {fail}" if fail else ""))
sys.exit(1 if fail else 0)
