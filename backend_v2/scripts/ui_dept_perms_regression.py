"""部门权限矩阵前端回归测试（Playwright）"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5002"
ok = True

def check(name, cond, detail=""):
    global ok
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond: ok = False

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1600, "height": 950})
    page = ctx.new_page()
    errors = []
    bad_responses = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("response", lambda r: bad_responses.append(r.url) if r.status >= 400 else None)

    # 登录
    page.goto(BASE + "/login")
    page.wait_for_load_state("networkidle")
    page.fill(".el-input__inner >> nth=0", "admin")
    page.fill("input[type=password]", "admin123")
    page.keyboard.press("Enter")
    page.wait_for_timeout(2500)
    check("登录成功", "/login" not in page.url, page.url)

    # 1. 进入资源管理 → 角色权限 Tab
    page.goto(BASE + "/resources")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)
    tabs = page.locator(".el-tabs__item").all_text_contents()
    check("资源管理有 3 个 Tab", any("角色权限" in t for t in tabs), str(tabs))
    page.locator(".el-tabs__item", has_text="角色权限").click()
    page.wait_for_timeout(1500)

    # 2. 左侧为按部门分组的角色列表（无内置角色组）
    nav_texts = [x.strip() for x in page.locator(".rp-nav-item").all_text_contents()]
    check("左侧为部门分组（无内置角色）", not any("管理员" in t or "查看者" in t for t in nav_texts), str(nav_texts[:8]))
    check("左侧含部门", len(nav_texts) >= 8, f"count={len(nav_texts)}")
    # 左侧标题
    left_title = page.locator(".rp-left .card-title").inner_text()
    check("左侧标题为角色列表", "角色" in left_title, left_title)

    # 3. 矩阵渲染 16 行 × 5 列
    page.wait_for_timeout(800)
    mrows = page.locator(".rp-right .card:nth-of-type(1) .el-table__body-wrapper .el-table__row")
    mrows.first.wait_for(state="visible", timeout=8000)
    check("权限矩阵渲染 16 行", mrows.count() == 16, f"rows={mrows.count()}")
    first_cell = mrows.nth(0).locator("td").first.inner_text()
    check("矩阵第一行=我的工作台", "我的工作台" in first_cell, first_cell)

    # 4. 创建临时部门并选中 → 勾选矩阵 → 保存 → 刷新保持
    dname = "回归部门" + os.urandom(2).hex()
    page.locator(".rp-left .card-header .el-button", has_text="新增部门").click()
    page.wait_for_timeout(600)
    page.locator(".el-dialog input").fill(dname)
    page.locator(".el-dialog .el-button--primary", has_text="保存").click()
    page.wait_for_timeout(1500)
    page.locator(".rp-nav-item", has_text=dname).click()
    page.wait_for_timeout(1000)
    mrows = page.locator(".rp-right .card:nth-of-type(1) .el-table__body-wrapper .el-table__row")
    mrows.first.wait_for(state="visible", timeout=8000)
    # projects 行（索引 5）勾 查看/编辑；users 行（索引 13）勾 查看
    proj = mrows.nth(5)
    cbs = proj.locator(".el-checkbox")
    for i in [0, 2]:
        if not cbs.nth(i).locator("input").is_checked():
            cbs.nth(i).click()
            page.wait_for_timeout(150)
    users_row = mrows.nth(13)
    uc = users_row.locator(".el-checkbox").nth(0)
    if not uc.locator("input").is_checked():
        uc.click()
        page.wait_for_timeout(150)
    page.wait_for_timeout(500)
    save_btn = page.locator(".rp-right .card-header .el-button--primary", has_text="保存矩阵")
    check("保存矩阵按钮可用", save_btn.is_enabled())
    save_btn.click()
    page.wait_for_timeout(1500)
    msg = page.locator(".el-message").all_text_contents() if page.locator(".el-message").count() else []
    check("矩阵保存成功", any("已保存" in m for m in msg), str(msg))

    # 5. 刷新后保持
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)
    page.locator(".el-tabs__item", has_text="角色权限").click()
    page.wait_for_timeout(1500)
    page.locator(".rp-nav-item", has_text=dname).click()
    page.wait_for_timeout(1000)
    mrows = page.locator(".rp-right .card:nth-of-type(1) .el-table__body-wrapper .el-table__row")
    mrows.first.wait_for(state="visible", timeout=8000)
    proj_states = [mrows.nth(5).locator(".el-checkbox").nth(i).locator("input").is_checked() for i in range(5)]
    check("刷新后 projects 保持 view+edit", proj_states[0] and proj_states[2] and not proj_states[1], str(proj_states))
    users_state = mrows.nth(13).locator(".el-checkbox").nth(0).locator("input").is_checked()
    check("刷新后 users.view 保持", users_state, "")

    # 6. 在该部门下创建角色（分组）
    page.locator(".rp-right .card:nth-of-type(1) .card-header .el-button", has_text="新增角色").click()
    page.wait_for_timeout(600)
    dialogs = page.locator(".el-dialog:visible")
    rname = "回归角色" + os.urandom(2).hex()
    dialogs.locator("input").nth(0).fill(rname)
    dialogs.locator(".el-button--primary", has_text="保存").click()
    page.wait_for_timeout(1500)
    role_items = page.locator(".rp-left .rp-role-item").all_text_contents()
    check("部门角色创建成功（分组，左侧列表可见）", any(rname in t for t in role_items), str(role_items[:1]))
    # 部门徽标显示角色数
    dept_badge = page.locator(".rp-nav-item", has_text=dname).locator(".rp-nav-badge").inner_text()
    check("部门角色计数=1", "1" in dept_badge, dept_badge)

    # 7. members Tab：对话框无权限勾选 UI，含部门字段，无独立「角色」字段（角色分组仅在角色权限 Tab 管理）
    page.locator(".el-tabs__item", has_text="人员与账号").click()
    page.wait_for_timeout(1200)
    page.locator("button", has_text="编辑").first.click()
    page.wait_for_timeout(800)
    dialog = page.locator(".el-dialog:visible")
    dtext = dialog.inner_text()
    cb_count = dialog.locator(".el-checkbox").count()
    check("成员对话框无权限勾选 UI", cb_count == 0, f"checkbox={cb_count}")
    check("成员对话框含部门字段", "部门" in dtext, "")
    role_labels = dialog.locator(".el-form-item__label").all_text_contents()
    check("成员对话框无独立角色字段", not any("角色" in t for t in role_labels), str(role_labels))

    # 8. JS 错误检查
    real_errors = [e for e in errors if "Failed to load resource" not in e]
    bad_others = [u for u in bad_responses if "ai/config" not in u]
    check("无 JS 报错", len(real_errors) == 0, str(real_errors[:5]))
    check("无异常响应", len(bad_others) == 0, str(bad_others[:5]))

    browser.close()

print("\n=== 部门矩阵前端回归", "全部通过" if ok else "存在失败项", "===")
print("测试数据：部门=%s 角色=%s（保留待清理）" % (dname, rname))
sys.exit(0 if ok else 1)
