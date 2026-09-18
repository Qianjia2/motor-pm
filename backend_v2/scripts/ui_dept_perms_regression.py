"""部门权限矩阵前端回归测试（Playwright）"""
import sys, os, json
# 三层 dirname 才到仓库根（backend_v2/scripts/x.py → backend_v2 → motor-pm），
# 少了这层下面 `import backend_v2.*` 会 ModuleNotFoundError。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
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
    role_labels = [t.strip() for t in dialog.locator(".el-form-item__label").all_text_contents()]
    # 原断言是 `not any("角色" in t)`，但对话框里有个「账号角色」（UserAuth.role 内置兜底角色，
    # 和 PermissionRole 分组标签是两回事），所以那条断言从加了这个字段起就一直红着。
    # 收敛到它真正想表达的意思：没有选择 PermissionRole（分组标签）的字段。
    check("成员对话框无「角色」分组标签字段（账号角色≠分组标签）",
          not any(t in ("角色", "权限角色") for t in role_labels), str(role_labels))
    check("成员对话框保留「账号角色」内置兜底字段", "账号角色" in role_labels, str(role_labels))

    # ══ 9. 按人配置 UI（2026-09-11 新增）══════════════════════════════
    # 上一段（成员编辑对话框）跑完没关，弹层会拦住后面所有点击——先关掉。
    if page.locator(".el-dialog:visible").count():
        page.locator(".el-dialog:visible .el-dialog__headerbtn").first.click()
        page.wait_for_timeout(600)
    # 造一个临时账号来点，避免动到真实人员的权限；跑完自己删掉。
    import urllib.request, urllib.error

    def api(method, path, token=None, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(BASE + "/api" + path, data=data, method=method)
        r.add_header("Content-Type", "application/json")
        if token: r.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try: return e.code, json.loads(e.read().decode())
            except Exception: return e.code, {}
        except Exception as e:
            return -1, {"err": str(e)}

    _, lb = api("POST", "/auth/login", body={"username": "admin", "password": "admin123"})
    adm = lb.get("access_token")
    # 自愈：上次跑崩了可能留下本脚本的临时账号（名如 uireg_xxxxxx），先扫掉再开始。
    # 线上库上不该攒着能登录的测试账号，跑一次清一次。
    _, allu = api("GET", "/auth/users", adm)
    allu = allu if isinstance(allu, list) else allu.get("users", [])
    stale = [x for x in allu if str(x.get("username", "")).startswith("uireg_")]
    for x in stale:
        api("DELETE", f"/auth/users/{x['id']}", adm)
    if stale:
        print(f"[sweep] 清理上次残留的临时账号 {len(stale)} 个: {[x['username'] for x in stale]}")
    # 成员名也必须每轮唯一：上一轮跑崩留下的同名成员会让下面的 .first 选错行，
    # 断言就变成在测别人的数据了（第一版就是这么骗过自己的）。顺手扫掉旧残留。
    from backend_v2.database import SessionLocal as _SL
    from backend_v2.models import TeamMember as _TM
    _db = _SL()
    swept_m = _db.execute(_TM.__table__.delete().where(_TM.name.like("UI回归%"))).rowcount
    _db.commit(); _db.close()
    if swept_m:
        print(f"[sweep] 清理残留的临时成员 {swept_m} 行")
    mname = "UI回归" + os.urandom(2).hex()
    uname = "uireg_" + os.urandom(3).hex()
    st, _ = api("POST", "/team-members", adm, {
        "name": mname, "department": dname, "username": uname, "password": "test123",
    })
    check("(建) 临时账号用于按人配置测试", st == 201, f"status={st}")
    st, users = api("GET", "/auth/users", adm)
    users = users if isinstance(users, list) else users.get("users", [])
    urow = next((x for x in users if x["username"] == uname), None)
    uid = urow["id"] if urow else None
    check("(建) 新账号来源=dept（建号套部门模板）", (urow or {}).get("perm_source") == "dept",
          f"perm_source={(urow or {}).get('perm_source')}")

    # 账号是刚用 API 建的，页面上的列表还是旧数据——刷新后再搜出来。
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)
    page.locator(".el-tabs__item", has_text="人员与账号").click()
    page.wait_for_timeout(1500)
    page.locator("input[placeholder='搜索姓名 / 部门']").fill(mname)
    page.wait_for_timeout(900)
    row = page.locator(".el-table__row", has_text=uname).first
    row.wait_for(state="visible", timeout=15000)
    row_text = row.inner_text()
    check("人员列表「权限来源」列显示随部门模板", "随部门模板" in row_text, row_text.replace("\n", " | ")[:120])

    # 打开「权限」抽屉
    row.locator("button", has_text="权限").first.click()
    page.wait_for_timeout(1200)
    drawer = page.locator(".perm-drawer")
    drawer.wait_for(state="visible", timeout=8000)
    check("权限抽屉打开", drawer.is_visible(), "")
    check("抽屉显示当前随部门模板", "当前随部门模板" in drawer.inner_text(), "")
    drows = drawer.locator(".el-table__body-wrapper .el-table__row")
    check("抽屉内矩阵 16 行", drows.count() == 16, f"rows={drows.count()}")

    # 关掉 projects（第 6 行，索引 5）的「查看」——这是旧引擎做不到的事
    proj_row = drows.nth(5)
    check("抽屉第 6 行=项目台账", "项目台账" in proj_row.inner_text(), proj_row.inner_text()[:40])
    pview = proj_row.locator(".el-checkbox").nth(0)
    was_checked = pview.locator("input").is_checked()
    if was_checked:
        pview.click()
        page.wait_for_timeout(200)
    page.wait_for_timeout(400)
    save = page.locator(".el-drawer:visible .el-button--primary", has_text="保存权限")
    check("保存按钮因 dirty 可用", save.is_enabled(), "")
    save.click()
    page.wait_for_timeout(1800)
    msg = page.locator(".el-message").all_text_contents() if page.locator(".el-message").count() else []
    check("保存权限成功", any("已" in m for m in msg), str(msg))

    # 列表里的来源列应立刻变成「已单独配置」
    page.wait_for_timeout(800)
    row = page.locator(".el-table__row", has_text=uname).first
    check("列表来源列变为「已单独配置」", "已单独配置" in row.inner_text(), row.inner_text().replace("\n", " | ")[:140])

    # 该账号登录后，被关掉的模块确实没了
    _, tb = api("POST", "/auth/login", body={"username": uname, "password": "test123"})
    utok = tb.get("access_token")
    st, mpm = api("GET", "/auth/my-permissions", utok)
    pj = (mpm.get("permissions") or {}).get("projects", {})
    check("个人按钮生效：projects.view 已关", pj.get("view") is False, f"projects={pj}")

    # 10. 改部门模板 → 不影响已单独配置的人
    st, depts = api("GET", "/departments", adm)
    depts = depts if isinstance(depts, list) else depts.get("data", [])
    dept_id = next((x["id"] for x in depts if x["name"] == dname), None)
    check("(查) 按名字取到临时部门", dept_id is not None, f"dept_id={dept_id}")
    only_view = {"projects": {"view": True, "create": False, "edit": False, "delete": False, "export": False}}
    st, _ = api("PUT", f"/departments/{dept_id}", adm, {"permissions": only_view})
    check("(改) 部门模板改成 projects 仅 view", st == 200, f"status={st}")
    page.wait_for_timeout(600)
    _, tb2 = api("POST", "/auth/login", body={"username": uname, "password": "test123"})
    st, mpm2 = api("GET", "/auth/my-permissions", tb2.get("access_token"))
    check("改部门模板后该账号不受影响（仍无 projects.view）",
          ((mpm2.get("permissions") or {}).get("projects") or {}).get("view") is False,
          str((mpm2.get("permissions") or {}).get("projects")))

    # 11. 一键下发：确认框要报出「1 人已单独配置」，点取消不能改数据
    page.locator(".el-tabs__item", has_text="角色权限").click()
    page.wait_for_timeout(1500)
    page.locator(".rp-nav-item", has_text=dname).click()
    page.wait_for_timeout(1200)
    page.locator(".rp-right .card-header .el-button", has_text="应用到本部门所有人").click()
    page.wait_for_timeout(1800)
    box = page.locator(".el-message-box")
    box.wait_for(state="visible", timeout=8000)
    box_text = box.inner_text()
    check("下发确认框报出「1 人已单独配置」", "1 人已单独配置" in box_text, box_text.replace("\n", " | ")[:160])
    box.locator("button", has_text="取消").click()
    page.wait_for_timeout(800)
    _, tb3 = api("POST", "/auth/login", body={"username": uname, "password": "test123"})
    st, mpm3 = api("GET", "/auth/my-permissions", tb3.get("access_token"))
    check("点取消后个人权限没变（projects.view 仍关）",
          ((mpm3.get("permissions") or {}).get("projects") or {}).get("view") is False, "")

    # 清理本次造的全部临时数据。原来只留「部门/角色待清理」，但残留角色会挂在被
    # SQLite 复用的部门 id 上，下一轮「部门角色计数=1」就数到上一轮的角色——
    # 自己污染自己的断言。改成跑完就清干净。
    if uid:
        st, _ = api("DELETE", f"/auth/users/{uid}", adm)
        check("(清) 删除临时账号", st in (200, 204), f"status={st}")
    _db = _SL()
    swept = _db.execute(_TM.__table__.delete().where(_TM.name == mname)).rowcount
    _db.commit(); _db.close()
    check("(清) 删除临时成员", swept == 1, f"rows={swept}")
    # 顺序不能反：部门下还有角色时 delete_department 会 409。
    # 按 dept_id 删而不是按角色名：名字匹配会漏（残留的旧角色名字对不上），
    # 而部门下挂着任何一个角色，部门就删不掉。
    # 少传 token 会 401，e.code 分支返回 {} → 下面 .get("data") 得到空列表 →
    # 一个角色都删不掉 → 部门 409。401 必须当硬错误报出来，不能静默变成空名单。
    st, roles_all = api("GET", "/auth/permission-roles", adm)
    roles_all = roles_all if isinstance(roles_all, list) else roles_all.get("data", [])
    check("(清) 取到角色列表（带鉴权）", st == 200 and isinstance(roles_all, list), f"status={st} n={len(roles_all) if isinstance(roles_all, list) else roles_all}")
    # 比字符串是防序列化差异的保险（两边现在都是 int，但接口改一次就可能变 str）。
    mine = [x for x in roles_all if str(x.get("dept_id")) == str(dept_id)]
    for r in mine:
        api("DELETE", f"/auth/permission-roles/{r['id']}", adm)
    st, _ = api("DELETE", f"/departments/{dept_id}", adm)
    check("(清) 删除临时部门与角色", st == 200, f"status={st} 删角色{len(mine)}个 {[x['name'] for x in mine]}")

    # 12. JS 错误检查
    real_errors = [e for e in errors if "Failed to load resource" not in e]
    bad_others = [u for u in bad_responses if "ai/config" not in u]
    check("无 JS 报错", len(real_errors) == 0, str(real_errors[:5]))
    check("无异常响应", len(bad_others) == 0, str(bad_others[:5]))

    browser.close()

print("\n=== 部门矩阵前端回归", "全部通过" if ok else "存在失败项", "===")
print("测试数据：部门=%s 角色=%s（跑完已自行清理）" % (dname, rname))
sys.exit(0 if ok else 1)
