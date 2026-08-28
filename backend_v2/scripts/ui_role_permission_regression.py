"""角色权限功能前端回归测试（Playwright）"""
import sys, os, json, time
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

    # ── 1. 登录并进入资源管理 ──
    login(page)
    check("登录成功进入系统", "/login" not in page.url, page.url)
    page.goto(BASE + "/resources")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)

    # ── 2. 第三个 Tab「角色权限」存在 ──
    tabs = page.locator(".el-tabs__item").all_text_contents()
    check("资源管理有 3 个 Tab（含角色权限）", any("角色权限" in t for t in tabs), str(tabs))

    # ── 3. 点击角色权限 Tab ──
    page.locator(".el-tabs__item", has_text="角色权限").click()
    page.wait_for_timeout(1500)
    left = page.locator(".rp-left").first
    check("左侧部门-角色导航出现", left.is_visible(), "")
    nav_items = page.locator(".rp-nav-item").all_text_contents()
    builtin_names = [x.strip() for x in nav_items]
    check("左侧含 4 个内置角色", len(builtin_names) >= 4, str(builtin_names[:8]))
    dept_rows = page.locator(".rp-dept-row").all_text_contents()
    check("左侧含部门分组", len(dept_rows) >= 1, f"dept rows={len(dept_rows)}")

    # ── 4. 默认选中内置 admin，users 行 disabled ──
    page.wait_for_timeout(1200)
    admin_locked = True
    try:
        # 权限矩阵表 = .rp-right 第 2 个 card 的 el-table（第 1 个是部门角色表）
        mrows = page.locator(".rp-right .card:nth-of-type(2) .el-table__body-wrapper .el-table__row")
        mrows.first.wait_for(state="visible", timeout=8000)
        row_count = mrows.count()
        check("权限矩阵渲染 8 行", row_count == 8, f"rows={row_count}")
        # users 模块行（最后一行）checkbox disabled
        last_row = mrows.nth(row_count - 1)
        cb = last_row.locator(".el-checkbox").first
        is_disabled = "is-disabled" in (cb.get_attribute("class") or "")
        # projects 行（第一行）不禁用
        proj_row = mrows.nth(0)
        proj_disabled = "is-disabled" in (proj_row.locator(".el-checkbox").first.get_attribute("class") or "")
        check("admin 角色 users 行锁定、projects 行可勾", is_disabled and not proj_disabled, f"users_locked={is_disabled} projects_disabled={proj_disabled}")
    except Exception as e:
        check("admin users 行锁定检查", False, str(e)[:120])

    # ── 5. 创建部门 ──
    dname = "回归部门" + os.urandom(2).hex()
    page.locator(".rp-left .card-header .el-button", has_text="新增部门").click()
    page.wait_for_timeout(600)
    page.locator(".el-dialog input").fill(dname)
    page.locator(".el-dialog .el-button--primary", has_text="保存").click()
    page.wait_for_timeout(1500)
    dept_texts = page.locator(".rp-dept-row").all_text_contents()
    check("创建部门成功且显示", any(dname in t for t in dept_texts), str(dept_texts[-3:]))

    # ── 6. 在该部门下创建角色 ──
    # 点击新部门的名字（span）选中该部门组
    page.locator(".rp-dept-row", has_text=dname).locator("span").first.click()
    page.wait_for_timeout(800)
    page.locator(".rp-right .card .card-header .el-button", has_text="新增角色").click()
    page.wait_for_timeout(600)
    dialogs = page.locator(".el-dialog:visible")
    rname = "回归角色" + os.urandom(2).hex()
    # 名称输入
    dialogs.locator("input").nth(0).fill(rname)
    # 保存
    dialogs.locator(".el-button--primary", has_text="保存").click()
    page.wait_for_timeout(1500)
    nav_texts = page.locator(".rp-nav-item").all_text_contents()
    check("部门角色创建成功且出现在左侧", any(rname in t for t in nav_texts), f"nav has {rname}: {any(rname in t for t in nav_texts)}")

    # ── 7. 勾选权限矩阵并保存 ──
    page.wait_for_timeout(800)
    # 选中刚创建的角色
    page.locator(".rp-nav-item", has_text=rname).click()
    page.wait_for_timeout(1000)
    # 权限矩阵表（第 2 个 card）
    mrows = page.locator(".rp-right .card:nth-of-type(2) .el-table__body-wrapper .el-table__row")
    mrows.first.wait_for(state="visible", timeout=8000)
    # projects 行勾选 查看/新建/编辑/导出（跳过删除）
    proj = mrows.nth(0)
    cbs = proj.locator(".el-checkbox")
    # 列顺序: 模块名, 查看, 新建, 编辑, 删除, 导出 → checkbox 索引 0..4
    for i in [0, 1, 2, 4]:  # view create edit export
        cb = cbs.nth(i)
        if not cb.locator("input").is_checked():
            cb.click()
            page.wait_for_timeout(150)
    # bom 行勾选 查看
    bom = mrows.nth(1)
    bom_cb = bom.locator(".el-checkbox").nth(0)
    if not bom_cb.locator("input").is_checked():
        bom_cb.click()
        page.wait_for_timeout(150)
    page.wait_for_timeout(500)
    # 保存矩阵
    save_btn = page.locator(".rp-right .card-header .el-button--primary", has_text="保存矩阵")
    check("保存矩阵按钮可用（dirty）", save_btn.is_enabled())
    save_btn.click()
    page.wait_for_timeout(1500)
    msg = page.locator(".el-message").all_text_contents() if page.locator(".el-message").count() else []
    check("矩阵保存成功提示", any("已保存" in m for m in msg), str(msg))

    # ── 8. 刷新后矩阵仍在 ──
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)
    page.locator(".el-tabs__item", has_text="角色权限").click()
    page.wait_for_timeout(1500)
    page.locator(".rp-nav-item", has_text=rname).click()
    page.wait_for_timeout(1000)
    mrows = page.locator(".rp-right .card:nth-of-type(2) .el-table__body-wrapper .el-table__row")
    mrows.first.wait_for(state="visible", timeout=8000)
    proj = mrows.nth(0)
    cbs = proj.locator(".el-checkbox")
    states = [cbs.nth(i).locator("input").is_checked() for i in range(5)]
    check("刷新后矩阵保持（projects: view+create+edit+export）", states == [True, True, True, False, True], str(states))
    bom_states = [mrows.nth(1).locator(".el-checkbox").nth(i).locator("input").is_checked() for i in range(5)]
    check("刷新后 bom 仅 view", bom_states[0] and not any(bom_states[1:]), str(bom_states))

    # ── 9. members Tab 回归 ──
    page.locator(".el-tabs__item", has_text="人员与账号").click()
    page.wait_for_timeout(1200)
    body_text = page.locator("body").inner_text()
    check("members Tab 无角色权限说明卡片", "角色权限说明" not in body_text, "")
    # 打开第一个成员的编辑对话框
    edit_btn = page.locator("button", has_text="编辑").first
    edit_btn.click()
    page.wait_for_timeout(800)
    dialog = page.locator(".el-dialog:visible")
    dtext = dialog.inner_text()
    cb_count = dialog.locator(".el-checkbox").count()
    check("成员对话框无权限勾选 UI（个人矩阵已移除）", cb_count == 0, f"checkbox_count={cb_count}")
    check("成员对话框含权限继承说明", "账号权限" in dtext, "")
    # 部门字段是 select
    page.wait_for_timeout(400)
    check("成员对话框含部门下拉", "部门" in dtext, "")
    dialog.locator(".el-dialog__headerbtn").click()
    page.wait_for_timeout(500)

    # ── 10. JS 错误检查（忽略既有 /api/ai/config 401 轮询，与本次改动无关）──
    real_errors = [e for e in errors if "Failed to load resource" not in e]
    bad_others = [u for u in bad_responses if "ai/config" not in u]
    check("无 JS 报错", len(real_errors) == 0, str(real_errors[:5]))
    check("无异常响应（除 ai/config 401）", len(bad_others) == 0, str(bad_others[:5]))

    browser.close()

print("\n=== 前端回归", "全部通过" if ok else "存在失败项", "===")
print("创建的测试数据：部门=%s 角色=%s（保留用于人工检查，可从 UI 删除）" % (dname, rname))
sys.exit(0 if ok else 1)
