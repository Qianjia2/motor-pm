"""浏览器端验证: 工作流「我的工作台」+「阶段流程图」(软件项目)。

期望值全部由接口现算,不写死文案/数字——用哪个账号跑,就断言那个账号该看到什么。
所以同一个脚本可以拿不同账号反复跑,验"每个人进到自己项目看到的不一样"。

验证点:
  1. 默认落在「编排图」而不是清单
  2. 四个阶段列都渲出来了,列头名称/门径状态/步数与接口一致
  3. 每列的节点数与接口 steps 数一致,节点名与状态逐条对得上
  4. 我负责的步骤有「你」标,阶段当前步有高亮
  5. 点节点开抽屉,抽屉里的名称/状态/依据/交付物与接口一致
  6. 切到「清单」视图原有阶段 Tab 还在,切回来编排图还在
  7. 工作台五态:按接口的 me 推出该账号应处于哪一态,断言卡片渲染成那一态

用法:
  python scripts/ui_check_workflow_graph.py --project 28
  python scripts/ui_check_workflow_graph.py --project 1 --base http://127.0.0.1:5003 \\
      --user maxiaohao --password 123456
"""
import argparse
import sys

import requests
from playwright.sync_api import sync_playwright

DEFAULT_BASE = "http://127.0.0.1:5002"
ok, fail = 0, []


def check(name, cond, extra=""):
    global ok
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail.append(name)
        print(f"  FAIL  {name}  {extra}")


# MyWorkbench.vue 里 state -> 标题 的映射,照抄一份当期望值
STATE_TITLE = {
    "no_role": "你在本项目没有分配角色",
    "no_steps": "本项目没有安排到你名下的步骤",
    "todo": "轮到你了",
    "waiting": "先等前面这几步做完",
    "all_done": "你的活都干完了",
}

# 管理员看自己没参与的项目时,MyWorkbench 把 no_role 换成说明性文案——
# 他没角色是对的,不是配置缺失,甩"请联系项目经理"会像报错。
ADMIN_TITLE = "你是管理员，未参与本项目"


def expect_title(state, is_admin):
    """与 MyWorkbench.vue 的 title computed 对齐。"""
    if state == "no_role" and is_admin:
        return ADMIN_TITLE
    return STATE_TITLE[state]


def expect_state(me):
    """与 MyWorkbench.vue 的 state computed 同序:先判角色,再判有没有我的活。"""
    if not me["has_role"]:
        return "no_role"
    if not me["mine_total"]:
        return "no_steps"
    if me["next"] and not me["next_waiting_on_prev"]:
        return "todo"
    if me["next"] and me["next_waiting_on_prev"]:
        return "waiting"
    return "all_done"


def lanes(page):
    """把编排图的四列读成结构化数据。"""
    return page.evaluate("""() => [...document.querySelectorAll('.g .lane')].map(l => ({
        code: l.querySelector('.lh-code')?.innerText.trim(),
        name: l.querySelector('.lh-name')?.innerText.trim(),
        gate: l.querySelector('.lh-top .el-tag')?.innerText.trim(),
        meta: l.querySelector('.lh-meta')?.innerText.trim(),
        nodes: [...l.querySelectorAll('.lane-body .node')].map(n => ({
            seq: n.querySelector('.n-badge')?.innerText.trim(),
            name: n.querySelector('.n-name')?.innerText.trim(),
            sub: n.querySelector('.n-sub')?.innerText.trim(),
            mine: !!n.querySelector('.n-me'),
            current: n.classList.contains('n-current'),
            locked: n.classList.contains('n-locked'),
            gate: n.classList.contains('n-gate'),
        })),
    }))""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=int, default=28)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    a = ap.parse_args()
    pid, base = a.project, a.base.rstrip("/")
    api = base + "/api"

    s = requests.Session()
    r = s.post(f"{api}/auth/login", json={"username": a.user, "password": a.password})
    if r.status_code != 200:
        print(f"[错误] 接口登录失败 {r.status_code}: {r.text[:200]}")
        return 1
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # 系统角色(admin/member)决定 no_role 时显示哪句文案,得单独问一次
    is_admin = (s.get(f"{api}/auth/me", headers=H).json().get("user") or {}).get("role") == "admin"

    wf = s.get(f"{api}/projects/{pid}/workflow", headers=H).json()
    if not wf.get("supported"):
        print(f"[错误] 项目 {pid} 未开放工作流(软件全线开放,硬件见 workflow_map.WORKFLOW_OPT_IN_CODES)")
        return 1
    me = wf["me"]
    state = expect_state(me)
    title = expect_title(state, is_admin)
    print(f"[接口] 账号 {a.user} 管理员={is_admin} 角色={me['roles']} "
          f"我的={me['mine_done']}/{me['mine_total']} "
          f"next={me['next'] and (me['next']['phase_code'], me['next']['seq'])} "
          f"等前面={me['next_waiting_on_prev']} → 工作台应为「{title}」")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            page.goto(f"{base}/login")
            page.fill("input[placeholder='用户名']", a.user)
            page.fill("input[placeholder='密码']", a.password)
            page.click("button:has-text('登录')")
            page.wait_for_url(lambda u: "/login" not in u, timeout=20000)

            page.goto(f"{base}/projects/{pid}?tab=workflow")
            page.wait_for_timeout(2500)

            # ── 1. 默认视图是编排图 ──
            check("默认落在编排图(不是清单)",
                  page.locator(".g-wrap").count() == 1 and page.locator(".pw-tabs").count() == 0)
            check("视图切换器在", page.locator(".pw-summary .el-radio-group").count() == 1)

            # ── 2. 四列阶段 ──
            got = lanes(page)
            check(f"阶段列数={len(wf['phases'])}", len(got) == len(wf["phases"]),
                  [g["code"] for g in got])
            bad = []
            for ph, g in zip(wf["phases"], got):
                if g["code"] != ph["phase_code"]:
                    bad.append(f"列序 {g['code']}!={ph['phase_code']}")
                if g["name"] != ph["phase_name"]:
                    bad.append(f"{g['code']} 名称 {g['name']}!={ph['phase_name']}")
                if g["gate"] != ph["gate_state_label"]:
                    bad.append(f"{g['code']} 门径 {g['gate']}!={ph['gate_state_label']}")
                want_meta = f"{ph['progress']['steps_done']}/{len(ph['steps'])} 步"
                if want_meta not in (g["meta"] or ""):
                    bad.append(f"{g['code']} 步数 {g['meta']}!~{want_meta}")
            check("每列的名称/门径状态/步数都与接口一致", not bad, bad[:5])

            # ── 3. 列内节点 ──
            nbad = []
            for ph, g in zip(wf["phases"], got):
                if len(g["nodes"]) != len(ph["steps"]):
                    nbad.append(f"{ph['phase_code']} 节点数 {len(g['nodes'])}!={len(ph['steps'])}")
                    continue
                for st, n in zip(ph["steps"], g["nodes"]):
                    if n["seq"] != str(st["seq"]):
                        nbad.append(f"{ph['phase_code']} seq {n['seq']}!={st['seq']}")
                    if n["name"] != st["node"]["name"]:
                        nbad.append(f"{ph['phase_code']}-{st['seq']} 名 {n['name']}!={st['node']['name']}")
                    if n["sub"] != st["state_label"]:
                        nbad.append(f"{ph['phase_code']}-{st['seq']} 状态 {n['sub']}!={st['state_label']}")
                    if n["mine"] != st["assigned_to_me"]:
                        nbad.append(f"{ph['phase_code']}-{st['seq']} 我的标 {n['mine']}!={st['assigned_to_me']}")
                    if n["current"] != st["is_current"]:
                        nbad.append(f"{ph['phase_code']}-{st['seq']} 当前标 {n['current']}!={st['is_current']}")
                    if n["gate"] != (st["kind"] == "gate"):
                        nbad.append(f"{ph['phase_code']}-{st['seq']} 门禁标 {n['gate']}")
            check("36 步的名称/状态/我的标/当前标都与接口一致", not nbad, nbad[:5])

            mine_n = sum(1 for ph in wf["phases"] for st in ph["steps"] if st["assigned_to_me"])
            check(f"我负责的 {mine_n} 步在图上带「你」标",
                  sum(1 for g in got for n in g["nodes"] if n["mine"]) == mine_n)

            # ── 4. 点节点开抽屉 ──
            tgt_ph = next((ph for ph in wf["phases"] if ph["steps"]), None)
            tgt = tgt_ph["steps"][0]
            page.locator(".g .lane").first.locator(".node").first.click()
            page.wait_for_timeout(800)
            check("点节点弹出详情抽屉", page.locator(".el-drawer").count() == 1)
            dtxt = page.inner_text(".el-drawer") if page.locator(".el-drawer").count() else ""
            check("抽屉标题带阶段与步序",
                  f"{tgt_ph['phase_code']}" in dtxt and f"第 {tgt['seq']} 步" in dtxt, dtxt[:80])
            check("抽屉里有步骤状态", (tgt["state_label"] or "") in dtxt, tgt["state_label"])
            for sname in [st["standard_name"] for st in tgt["standards"]]:
                check(f"抽屉列出交付物「{sname}」", sname in dtxt)
            page.keyboard.press("Escape")
            page.wait_for_timeout(700)

            # ── 5. 工作台五态 ──
            check("工作台卡片在", page.locator(".wb").count() == 1)
            cls = page.get_attribute(".wb", "class") or ""
            want_cls = "wb-admin" if (state == "no_role" and is_admin) else f"wb-{state}"
            check(f"工作台渲染成「{state}」态", want_cls in cls, cls)
            check(f"工作台标题=「{title}」",
                  page.inner_text(".wb .t1").strip() == title,
                  page.inner_text(".wb .t1").strip())
            if state == "todo":
                check("「轮到你了」摊开了这一步的名称",
                      page.inner_text(".wb .n-name").strip() == next(
                          st["node"]["name"] for ph in wf["phases"] for st in ph["steps"]
                          if ph["phase_code"] == me["next"]["phase_code"] and st["seq"] == me["next"]["seq"]),
                      page.inner_text(".wb .n-name").strip())
                keys = page.evaluate(
                    "() => [...document.querySelectorAll('.wb .n-grid .n-cell .k')]"
                    ".map(e => e.innerText.trim())")
                check("四要素「做什么/产出什么/交给谁/在哪办」都在",
                      keys == ["做什么", "产出什么", "交给谁", "在哪办"], keys)
            if state == "waiting":
                want = len(me["next"]["blocked_by"])
                wn = page.locator(".wb .w-row").count()
                check(f"「先等前面」列出了 {want} 步在等谁", wn == want, wn)
                # 五态互斥:等待态不能同时又渲染"轮到你了"那套详情+按钮。
                # 曾经就是这里错了——模板第一分支判的是 nextStep 而不是 state,
                # 而等待态 next 也非空,于是等待分支永远轮不到,被挡着的人反而
                # 看到一个"去交付物矩阵"的按钮。这条断言把那种回归钉住。
                check("等待态没有混进「轮到你了」的详情块",
                      page.locator(".wb .n-grid").count() == 0
                      and page.locator(".wb button:has-text('去交付物矩阵')").count() == 0)
            if state == "todo":
                check("轮到你了不混进「先等前面」的等待列表",
                      page.locator(".wb .w-row").count() == 0)
            if state == "no_role" and is_admin:
                # 管理员看到的是说明文案 + 项目当前卡点,不是后端那句"请联系项目经理"
                txt = page.inner_text(".wb")
                check("管理员看到说明而不是「请联系项目经理」那句",
                      "你是管理员" in txt and "请联系项目经理" not in txt, txt[:120])
                check("管理员仍能看到项目当前卡点",
                      page.locator(".wb .bn").count() == 1)
            elif state == "no_role":
                check("没角色时把后端 hint 原文给人看",
                      me.get("hint", "") and me["hint"] in page.inner_text(".wb"),
                      page.inner_text(".wb")[:120])

            # ── 6. 视图切换 ──
            page.locator(".pw-summary .el-radio-button:has-text('清单')").click()
            page.wait_for_timeout(800)
            check("切到清单视图后阶段 Tab 出现", page.locator(".pw-tabs").count() == 1)
            check("清单视图下编排图收起", page.locator(".g-wrap").count() == 0)
            check("清单视图下列表还在",
                  page.locator(".pw-phase .step").count() > 0)
            page.locator(".pw-summary .el-radio-button:has-text('编排图')").click()
            page.wait_for_timeout(800)
            check("切回编排图", page.locator(".g-wrap").count() == 1
                  and page.locator(".pw-tabs").count() == 0)

            browser.close()
    except Exception as e:
        fail.append(f"异常: {e}")
        import traceback
        traceback.print_exc()

    print()
    print(f"通过 {ok}, 失败 {len(fail)}")
    for f in fail:
        print("  -", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
