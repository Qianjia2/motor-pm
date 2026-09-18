"""浏览器端验证: 工作流作为独立模块的入口,以及"一项目一开放"在界面上的效果。

这一轮把工作流从"项目详情里的一个页签"提成独立模块(应用级入口 + 项目详情独立
分组),并在硬件里只开金浪一个试点。后端判定已有单测焊死(见
tests/api/test_project_workflow.py::TestWorkflowOptIn),这个脚本管的是另半截:
界面有没有把这些判定正确地反映出来——该出现的入口出现,不该出现的页签不出现。

期望值全部由接口现算(白名单只有 workflow_map 一处,前端不复制),不写死项目名单。

验证点:
  1. 侧边栏出现「项目工作流」,点进去落在 /project-workflow
  2. 项目下拉里只有开放的项目:开放的都在,没开放的硬件项目一个都没有
  3. 选中一个开放项目后,主体渲染出编排图(与项目详情里那个页签是同一个组件)
  4. 选中的项目落进 URL(query),刷新后还在——分享链接能带出同一个项目
  5. 未开放的硬件项目:详情页里既没有「工作流」分组,也没有工作流页签
  6. 已开放的硬件项目:详情页里有独立的「工作流」分组,且不与「全程管控」混在一起

用法: python scripts/ui_check_workflow_optin.py --base http://127.0.0.1:5003 \\
          --open 1 --closed 2 --user admin --password admin123
"""
import argparse
import sys

import requests
from playwright.sync_api import sync_playwright

ok, fail = 0, []


def check(name, cond, extra=""):
    global ok
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail.append(name)
        print(f"  FAIL  {name}  {extra}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5002")
    ap.add_argument("--open", type=int, required=True, help="已开放的硬件项目 id(金浪)")
    ap.add_argument("--closed", type=int, required=True, help="未开放的硬件项目 id")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", required=True)
    a = ap.parse_args()
    base = a.base.rstrip("/")
    api = base + "/api"

    s = requests.Session()
    r = s.post(f"{api}/auth/login", json={"username": a.user, "password": a.password})
    if r.status_code != 200:
        print(f"[错误] 登录失败 {r.status_code}: {r.text[:200]}")
        return 1
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # 期望值:后端说开放了哪些,界面就该列哪些
    listed = s.get(f"{api}/workflow/projects", headers=H).json()
    listed_codes = {p["code"] for p in listed}
    listed_ids = {p["id"] for p in listed}
    print(f"[接口] 开放项目 {len(listed)} 个: {sorted(listed_codes)}")

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 1000})
        # 走真实登录表单,不能只往 localStorage 塞 token:侧边栏是按权限过滤的,
        # 权限由登录后那次 /my-permissions 拉回来,跳过它整个主菜单都是空的
        # ("看得见一个入口"这件事本身就在验证范围内)。
        page.goto(f"{base}/login")
        page.fill("input[placeholder='用户名']", a.user)
        page.fill("input[placeholder='密码']", a.password)
        page.click("button:has-text('登录')")
        page.wait_for_url(lambda u: "/login" not in u, timeout=20000)

        # ── 1/2/3/4. 独立页面 ──
        print("=== 独立模块:侧边栏入口 + 项目选择器 ===")
        page.goto(base + "/my-work")
        page.wait_for_timeout(800)
        entry = page.locator(".nav-item", has_text="项目工作流")
        check("侧边栏有「项目工作流」入口", entry.count() == 1, f"count={entry.count()}")
        if entry.count():
            entry.first.click()
            page.wait_for_timeout(1200)
            check("点入口落在 /project-workflow", page.url.endswith("/project-workflow"),
                  f"实际 {page.url}")

        check("页面标题在", page.locator("h2", has_text="项目工作流").count() >= 1)

        # 打开下拉读选项
        page.locator(".wf-bar .el-select").click()
        page.wait_for_timeout(600)
        opts = page.locator(".el-select-dropdown__item:visible")
        opt_codes = set()
        for i in range(opts.count()):
            code = (opts.nth(i).locator(".opt-code").inner_text() or "").strip()
            if code:
                opt_codes.add(code)
        check("下拉里的项目与接口返回的一致", opt_codes == listed_codes,
              f"界面={sorted(opt_codes)} 接口={sorted(listed_codes)}")
        check("未开放的硬件项目不在下拉里", not (opt_codes - listed_codes))

        # 选一个开放项目 → 主体必须渲染出编排图
        target = next(p for p in listed if p["id"] == a.open) if a.open in listed_ids else None
        check("--open 指定的项目确实在开放清单里", target is not None,
              f"id={a.open} 不在 {sorted(listed_ids)}")
        if target:
            page.locator(".el-select-dropdown__item", has_text=target["code"]).first.click()
            page.wait_for_timeout(1500)
            check("选中后渲染出工作流主体", page.locator(".pw").count() >= 1)
            check("主体不是空态", page.locator(".el-empty").count() == 0)
            check(f"URL 带上了选中项目 id={a.open}",
                  f"project={a.open}" in page.url, f"实际 {page.url}")
            # 刷新后还在(URL 是唯一真源,localStorage 只是兜底)
            page.reload()
            page.wait_for_timeout(1500)
            check("刷新后仍停在同一个项目", page.locator(".pw").count() >= 1,
                  "刷新后没渲染出主体")

        # ── 5/6. 项目详情里的分组 ──
        print("=== 项目详情:工作流自成一组,且逐项目开放 ===")
        page.goto(f"{base}/projects/{a.closed}")
        page.wait_for_timeout(1500)
        groups = page.locator(".pd-nav .group-name")
        closed_groups = [groups.nth(i).inner_text().strip() for i in range(groups.count())]
        check("未开放项目:没有「工作流」分组", "工作流" not in closed_groups,
              f"分组={closed_groups}")
        tabs = page.locator(".pd-nav .pd-nav-item")
        closed_tabs = [tabs.nth(i).inner_text().strip() for i in range(tabs.count())]
        check("未开放项目:没有工作流页签",
              not any("工作流" in t for t in closed_tabs), f"页签={closed_tabs}")

        page.goto(f"{base}/projects/{a.open}")
        page.wait_for_timeout(1500)
        groups = page.locator(".pd-nav .group-name")
        open_groups = [groups.nth(i).inner_text().strip() for i in range(groups.count())]
        check("已开放项目:有独立的「工作流」分组", "工作流" in open_groups,
              f"分组={open_groups}")
        check("「工作流」与「全程管控」是两个并列分组",
              "工作流" in open_groups and "全程管控" in open_groups, f"分组={open_groups}")
        tabs = page.locator(".pd-nav .pd-nav-item")
        open_tabs = [tabs.nth(i).inner_text().strip() for i in range(tabs.count())]
        check("已开放项目:有工作流页签",
              any("工作流" in t for t in open_tabs), f"页签={open_tabs}")

        b.close()

    print(f"\n通过 {ok}, 失败 {len(fail)}")
    if fail:
        print("失败项: " + "; ".join(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
