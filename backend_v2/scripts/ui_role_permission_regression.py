"""角色（分组标签）与权限面板前端回归测试（Playwright）

2026-09-11 重写。原版写的是一套已经不存在的 DOM——左侧「4 个内置角色」、
`.rp-dept-row`、`.rp-right .card:nth-of-type(2)` 里的 8 行矩阵——那是权限还挂在
角色上时期的界面；后来权限挪到部门矩阵时这个脚本就死了，本次「按人」改造只是
又往前推了一步。按「已有的先都不删」的约定不删文件，改成测**今天真实存在**的语义：

- 角色 = 人员分组标签，不参与权限计算（面板文案也是这么写的）
- 左侧是「部门 > 角色」两级导航
- 选中角色时，右边显示的矩阵是它**所属部门**的矩阵（角色自己没有矩阵）
- 角色 CRUD（建/改说明/删）

矩阵本身、按人配置、一键下发在 ui_dept_perms_regression.py 里测，这里不重复。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5002"
ok = True
results = []


def check(name, cond, detail=""):
    global ok
    results.append((name, cond, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond: ok = False


def login(page, username="admin", password="admin123"):
    page.goto(BASE + "/login")
    page.wait_for_load_state("networkidle")
    page.fill("input[placeholder*='用户名'], input[placeholder*='账号'], .el-input__inner >> nth=0", username, timeout=8000)
    page.fill("input[type=password]", password)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2500)
    return page.url


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1600, "height": 950})
    page = ctx.new_page()
    errors = []
    bad_responses = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("response", lambda r: bad_responses.append(r.url) if r.status >= 400 else None)

    # ── 1. 登录并进入资源管理 → 角色权限 ──
    login(page)
    check("登录成功进入系统", "/login" not in page.url, page.url)
    page.goto(BASE + "/resources")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    tabs = page.locator(".el-tabs__item").all_text_contents()
    check("资源管理有 3 个 Tab（含角色权限）", any("角色权限" in t for t in tabs), str(tabs))
    page.locator(".el-tabs__item", has_text="角色权限").click()
    page.wait_for_timeout(1500)
    check("左侧部门导航出现", page.locator(".rp-left").first.is_visible(), "")
    nav_items = [x.strip() for x in page.locator(".rp-nav-item").all_text_contents()]
    check("左侧为部门分组（不再平铺内置角色）", len(nav_items) >= 4, str(nav_items[:8]))
    check("左侧不出现内置角色名（管理员/查看者）",
          not any("管理员" in t or "查看者" in t for t in nav_items), str(nav_items[:8]))

    # ── 2. 建部门 + 建角色 ──
    dname = "回归部门" + os.urandom(2).hex()
    page.locator(".rp-left .card-header .el-button", has_text="新增部门").click()
    page.wait_for_timeout(600)
    page.locator(".el-dialog input").fill(dname)
    page.locator(".el-dialog .el-button--primary", has_text="保存").click()
    page.wait_for_timeout(1500)
    check("创建部门成功且显示", any(dname in t for t in page.locator(".rp-nav-item").all_text_contents()),
          str(page.locator(".rp-nav-item").all_text_contents()[-3:]))

    page.locator(".rp-nav-item", has_text=dname).click()
    page.wait_for_timeout(800)
    page.locator(".rp-right .card-header .el-button", has_text="新增角色").click()
    page.wait_for_timeout(600)
    rname = "回归角色" + os.urandom(2).hex()
    dlg = page.locator(".el-dialog:visible")
    dlg.locator("input").nth(0).fill(rname)
    dlg.locator("input").nth(2).fill("权限配置：回归测试用的分组标签")
    dlg.locator(".el-button--primary", has_text="保存").click()
    page.wait_for_timeout(1500)
    role_items = [x.strip() for x in page.locator(".rp-left .rp-role-item").all_text_contents()]
    check("角色创建成功且挂在部门下（左侧缩进项）", any(rname in t for t in role_items), str(role_items[:3]))
    badge = page.locator(".rp-nav-item", has_text=dname).locator(".rp-nav-badge").inner_text()
    check("部门徽标显示角色数=1", "1" in badge, badge)

    # ── 3. 选中角色 → 说明卡片+所属部门；右侧矩阵是**部门**的矩阵 ──
    page.locator(".rp-role-item", has_text=rname).click()
    page.wait_for_timeout(1200)
    desc = page.locator(".rp-desc").inner_text()
    check("说明卡片显示选中角色名", rname in desc, desc.replace("\n", " | ")[:120])
    check("说明卡片显示所属部门", dname in desc, "")
    check("说明卡片写明角色不参与权限计算", "不参与权限计算" in desc, "")
    right_title = page.locator(".rp-right .card-title").first.inner_text()
    check("右侧矩阵标题是「权限设置：<部门>」而非角色名",
          dname in right_title and rname not in right_title, right_title)

    # ── 4. 改角色说明 ──
    page.locator(".rp-desc-role-head .el-button", has_text="编辑").click()
    page.wait_for_timeout(700)
    dlg = page.locator(".el-dialog:visible")
    dlg.locator("input").nth(2).fill("权限配置：改过的说明文案")
    dlg.locator(".el-button--primary", has_text="保存").click()
    page.wait_for_timeout(1500)
    check("角色说明更新成功", "改过的说明文案" in page.locator(".rp-desc").inner_text(),
          page.locator(".rp-desc").inner_text().replace("\n", " | ")[:120])

    # ── 5. 角色说明只占分组标签，不影响部门矩阵：勾一个模块并保存，角色说明不变 ──
    mrows = page.locator(".rp-right .card:nth-of-type(1) .el-table__body-wrapper .el-table__row")
    mrows.first.wait_for(state="visible", timeout=8000)
    check("矩阵仍为 16 行", mrows.count() == 16, f"rows={mrows.count()}")
    proj_cb = mrows.nth(5).locator(".el-checkbox").nth(0)
    if not proj_cb.locator("input").is_checked():
        proj_cb.click()
        page.wait_for_timeout(200)
    save_btn = page.locator(".rp-right .card-header .el-button--primary", has_text="保存矩阵")
    check("保存矩阵按钮可用", save_btn.is_enabled(), "")
    save_btn.click()
    page.wait_for_timeout(1500)
    msg = page.locator(".el-message").all_text_contents() if page.locator(".el-message").count() else []
    check("部门矩阵保存成功", any("已保存" in m for m in msg), str(msg))
    check("保存矩阵不影响角色说明", "改过的说明文案" in page.locator(".rp-desc").inner_text(), "")

    # ── 6. 刷新后角色仍在 ──
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)
    page.locator(".el-tabs__item", has_text="角色权限").click()
    page.wait_for_timeout(1500)
    roles_after = [x.strip() for x in page.locator(".rp-left .rp-role-item").all_text_contents()]
    check("刷新后角色仍在左侧", any(rname in t for t in roles_after), str(roles_after[:3]))

    # ── 7. 删角色 ──
    page.locator(".rp-role-item", has_text=rname).hover()
    page.wait_for_timeout(400)
    page.locator(".rp-role-item", has_text=rname).locator("button", has_text="删").first.click()
    page.wait_for_timeout(600)
    page.locator(".el-popconfirm .el-button--primary, .el-popper .el-button--primary").last.click()
    page.wait_for_timeout(1500)
    roles_final = [x.strip() for x in page.locator(".rp-left .rp-role-item").all_text_contents()]
    check("角色删除成功", not any(rname in t for t in roles_final), str(roles_final[:3]))

    # ── 8. 删部门（跑完自己清干净）──
    # 必须放在删角色之后：部门下还挂着角色时后端会 409。
    # 残留部门不是「无所谓的垃圾」——SQLite 会复用 rowid，上一轮残留的部门 id
    # 会被下一轮新建的部门拿到，挂在它下面的旧角色就把计数断言污染了。
    page.locator(".rp-nav-item", has_text=dname).hover()
    page.wait_for_timeout(400)
    page.locator(".rp-nav-item", has_text=dname).locator("button", has_text="删").first.click()
    page.wait_for_timeout(600)
    page.locator(".el-popconfirm .el-button--primary, .el-popper .el-button--primary").last.click()
    page.wait_for_timeout(1500)
    nav_final = [x.strip() for x in page.locator(".rp-nav-item").all_text_contents()]
    check("部门删除成功", not any(dname in t for t in nav_final), str(nav_final[:4]))

    # ── 9. JS 错误检查（忽略既有 /api/ai/config 401 轮询，与本次改动无关）──
    real_errors = [e for e in errors if "Failed to load resource" not in e]
    bad_others = [u for u in bad_responses if "ai/config" not in u]
    check("无 JS 报错", len(real_errors) == 0, str(real_errors[:5]))
    check("无异常响应（除 ai/config 401）", len(bad_others) == 0, str(bad_others[:5]))

    browser.close()

print("\n=== 角色（分组标签）前端回归", "全部通过" if ok else "存在失败项", "===")
print("测试数据：部门=%s 角色=%s（跑完已自行清理）" % (dname, rname))
sys.exit(0 if ok else 1)
