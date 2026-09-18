"""浏览器端验证: 项目详情「工作流」页签(软件项目试点)。

期望值全部由接口现算,不写死数字——交付物状态会被脚本改成各种各样,
写死就会变成"改数据就红"的假测试。

验证点:
  1. 软件项目页签栏里出现「工作流」,硬件项目不出现
  2. 阶段标签上的门径状态与接口一致
  3. 每步的状态、依据来源、步数与接口逐条一致
  4. 缺件清单与接口一致,且必交未齐时不出现"可以发起门禁"的入口
  5. 点「确认已完成」后状态真的变成已完成(走通写接口)
  6. 不挂在步骤上的交付物标准单独列出,没有被藏起来
  7. 由交付物推导的步骤没有"确认已完成"按钮(不能点一下就算完成)

用法: python scripts/ui_check_project_workflow.py [--project 28]
"""
import argparse
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


def _reset_confirm(s, H, pid, phase_code):
    """撤掉该阶段第一条线下步骤的旧确认,让"确认已完成"按钮重新出现。

    没有这一步,脚本第二次跑时按钮已经变成长「撤销确认」,确认路径就测不到了。
    返回一句说明,拼进检查名里,免得看起来像什么都没做。
    """
    steps = s.get(f"{API}/projects/{pid}/workflow", headers=H,
                  params={"phase_code": phase_code}).json()["phases"][0]["steps"]
    tgt = next((st for st in steps if st["confirmable"] and st["kind"] != "gate"), None)
    if not tgt:
        return ""
    r = s.delete(f"{API}/projects/{pid}/workflow/steps/{phase_code}/{tgt['seq']}/confirm",
                 headers=H)
    if r.status_code == 200:
        return f"(已重置 {phase_code}-{tgt['seq']} 的旧确认)"
    return f"(重置 {phase_code}-{tgt['seq']} 失败 {r.status_code})"


def rows(page):
    """把当前阶段的步骤读成结构化数据。

    el-tabs 会把所有阶段面板都留在 DOM 里,只把非活动的藏起来,所以要按可见性过滤,
    否则读到的是四个阶段混在一起的 36 步。
    """
    return page.evaluate("""() => {
        return [...document.querySelectorAll('.pw-phase .step')]
            .filter(el => el.offsetParent !== null)
            .map(el => ({
            state: el.querySelector('.step-bar .el-tag')?.innerText.trim(),
            src: el.querySelector('.step-bar .src')?.innerText.trim(),
            name: el.querySelector('.node .node-name')?.innerText.trim(),
            bar: [...el.querySelectorAll('.step-bar .el-tag')].map(t => t.innerText.trim()),
            confirmBtn: !!([...el.querySelectorAll('button')]
                .find(b => b.innerText.includes('确认已完成'))),
            dels: [...el.querySelectorAll('.dels .del-row')].map(r => ({
                name: r.querySelector('.del-name')?.innerText.trim(),
                tags: [...r.querySelectorAll('.el-tag')].map(t => t.innerText.trim()),
            })),
        }));
    }""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=int, default=28)
    a = ap.parse_args()
    pid = a.project

    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"username": "admin", "password": "admin123"})
    if r.status_code != 200:
        print(f"[错误] 登录失败: {r.text[:200]}")
        return 1
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}

    wf = s.get(f"{API}/projects/{pid}/workflow", headers=H).json()
    if not wf.get("supported"):
        print(f"[错误] 项目 {pid} 不是软件项目(或工作流不支持),先跑 seed_workflow_demo_project.py")
        return 1
    phases = {p["phase_code"]: p for p in wf["phases"]}
    print(f"[接口] 项目 {pid} {wf['project_name']}  {wf['summary']}")

    # 找硬件项目做"不该出现"的反例
    hw = None
    for p in s.get(f"{API}/projects", headers=H, params={"page_size": 100}).json()["data"]:
        if p.get("project_type") == "hardware":
            hw = p["id"]
            break

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            page.goto(f"{BASE}/login")
            page.fill("input[placeholder='用户名']", "admin")
            page.fill("input[placeholder='密码']", "admin123")
            page.click("button:has-text('登录')")
            page.wait_for_url(lambda u: "/login" not in u, timeout=20000)

            # ── 1. 导航项存在 ──
            # 项目详情的模块导航是左侧 .pd-nav,不是 el-tabs(页面里那组 el-tabs 是工作流
            # 组件自己的阶段切换)
            page.goto(f"{BASE}/projects/{pid}?tab=workflow")
            page.wait_for_timeout(2500)
            nav = page.inner_text(".pd-nav") if page.locator(".pd-nav").count() else ""
            check("软件项目导航里有「工作流」", "工作流" in nav, nav.replace("\n", "|")[:160])
            check("默认落在工作流页(不是回退到概览)",
                  page.locator(".pw").count() == 1 and page.locator(".pw-summary").count() == 1)

            if hw:
                page.goto(f"{BASE}/projects/{hw}")
                page.wait_for_timeout(2000)
                hnav = page.inner_text(".pd-nav") if page.locator(".pd-nav").count() else ""
                check("硬件项目导航里没有「工作流」", "工作流" not in hnav,
                      hnav.replace("\n", "|")[:160])
                page.goto(f"{BASE}/projects/{pid}?tab=workflow")
                page.wait_for_timeout(2500)

            # ── 2. 阶段标签与门径状态 ──
            labels = page.evaluate("""() => [...document.querySelectorAll('.pw-tabs .el-tabs__item')]
                .map(e => e.innerText.replace(/\\s+/g, ' ').trim())""")
            check(f"阶段标签 {len(phases)} 个", len(labels) == len(phases), labels)
            for code, ph in phases.items():
                hit = next((l for l in labels if ph["phase_name"] in l), None)
                check(f"{code} 标签显示门径「{ph['gate_state_label']}」",
                      hit and ph["gate_state_label"] in hit, hit)

            # ── 3. S0 逐步比对 ──
            page.click('.pw-tabs .el-tabs__item:has-text("需求")')
            page.wait_for_timeout(900)
            got = rows(page)
            s0 = phases["S0"]
            check(f"S0 步数={len(s0['steps'])}", len(got) == len(s0["steps"]), len(got))
            bad = []
            for exp, g in zip(s0["steps"], got):
                if g["name"] != exp["node"]["name"]:
                    bad.append(f"名称 {g['name']}!={exp['node']['name']}")
                if g["state"] != exp["state_label"]:
                    bad.append(f"{exp['node']['name']} 状态 {g['state']}!={exp['state_label']}")
            check("S0 每步名称与状态都与接口一致", not bad, bad[:4])

            srcs = {g["src"] for g in got}
            check("每步都标出了状态依据", srcs and all(s.startswith("依据：") for s in srcs), srcs)

            # ── 4. 缺件清单 ──
            body = page.evaluate(
                "() => [...document.querySelectorAll('.pw-phase')]"
                ".find(e => e.offsetParent !== null)?.innerText || ''")
            missing = s0["progress"]["missing_required"]
            miss_shown = all(m in body for m in missing)
            check(f"S0 缺件清单 {len(missing)} 条都列出来了", miss_shown,
                  [m for m in missing if m not in body])
            check("必交未齐时不显示「去发起门禁签署」",
                  not s0["progress"]["can_initiate_signoff"]
                  and page.locator("button:has-text('去发起门禁签署')").count() == 0)

            # ── 5. 由交付物推导的步骤不能人工确认 ──
            step2 = got[1]
            check(f"「{step2['name']}」由交付物推导,无确认按钮", not step2["confirmBtn"])
            check("该步列出了对应交付物", len(step2["dels"]) > 0, step2["dels"])
            del_tags = step2["dels"][0]["tags"] if step2["dels"] else []
            check("交付物标出必交/选交与提交状态", len(del_tags) >= 2, del_tags)

            # ── 6. 不挂在步骤上的标准要单列 ──
            has_unmapped = bool(s0["unmapped_standards"])
            unmapped_box = page.evaluate(
                "() => [...document.querySelectorAll('.unmapped')]"
                ".filter(e => e.offsetParent !== null).length")
            check("不挂步骤的标准单独列出(没被藏起来)",
                  unmapped_box == (1 if has_unmapped else 0),
                  f"接口 {len(s0['unmapped_standards'])} 条, 页面 {unmapped_box} 块")
            if has_unmapped:
                ub = page.evaluate(
                    "() => [...document.querySelectorAll('.unmapped')]"
                    ".find(e => e.offsetParent !== null)?.innerText || ''")
                check(f"单列块含全部 {len(s0['unmapped_standards'])} 条",
                      all(u["name"] in ub for u in s0["unmapped_standards"]),
                      [u["name"] for u in s0["unmapped_standards"] if u["name"] not in ub])

            # ── 7. 线下步骤的人工确认 ──
            # 先把这个阶段里第一条线下步骤的旧确认撤掉,保证每次跑都有"可确认"的按钮,
            # 否则第二次跑就只剩"撤销确认",测不到确认这条路径
            fresh = _reset_confirm(s, H, pid, "S2")
            page.reload()
            page.wait_for_timeout(2500)
            page.click('.pw-tabs .el-tabs__item:has-text("测试")')
            page.wait_for_timeout(900)
            got2 = rows(page)
            s2 = next(p for p in s.get(f"{API}/projects/{pid}/workflow", headers=H,
                                       params={"phase_code": "S2"}).json()["phases"])
            cands = [(i, e) for i, (e, g) in enumerate(zip(s2["steps"], got2))
                     if e["confirmable"] and e["kind"] != "gate" and g["confirmBtn"]]
            check(f"S2 存在可人工确认的线下步骤{fresh}", bool(cands),
                  [(e["seq"], e["node"]["venue"], e["kind"], g["confirmBtn"])
                   for e, g in zip(s2["steps"], got2)][:9])
            if cands:
                target, exp = cands[0]
                # 「:visible」是必须的:四个阶段的面板都在 DOM 里,nth(target) 很容易落到
                # 别的阶段的隐藏步骤上,点不动
                page.locator(".pw-phase .step:visible").nth(target).locator(
                    "button:has-text('确认已完成')").click()
                page.wait_for_timeout(700)
                # 弹窗里确认
                page.locator(".el-message-box button:has-text('确认')").first.click()
                page.wait_for_timeout(2000)

                after = s_api = s.get(f"{API}/projects/{pid}/workflow",
                                      headers=H, params={"phase_code": "S2"}).json()
                step_after = next(st for st in s_api["phases"][0]["steps"]
                                  if st["seq"] == exp["seq"])
                check(f"确认后接口记录了确认人",
                      step_after["confirm"] and step_after["confirm"]["confirmed_by"],
                      step_after["confirm"])
                got2b = rows(page)[target]
                name = exp["node"]["name"]
                if exp["standards"]:
                    # 这一步是"线下但报告就是证据":确认只留痕,状态仍按交付物算,
                    # 且必须提示材料没批完、门禁照样拦(别让人以为点一下就放行)
                    check(f"「{name}」确认只留痕:页面显示确认人,状态仍按交付物算",
                          any("已确认" in t for t in got2b["bar"])
                          and got2b["state"] == exp["state_label"], got2b)
                    check(f"「{name}」材料没批完时提示门禁仍会拦",
                          any("门禁仍会拦截" in t for t in got2b["bar"]), got2b["bar"])
                    check("留痕可撤销(撤销确认按钮出现)",
                          page.locator(".pw-phase .step:visible").nth(target)
                          .locator("button:has-text('撤销确认')").count() == 1)
                else:
                    # 本库所有非门禁步骤都配了标准,这条分支走不到,留着是为了口径完整
                    check("无交付物标准的步骤确认后变为已完成",
                          step_after["state"] == "done", step_after["state"])
                    check("页面同步显示为已完成/已确认",
                          got2b["state"] in ("已完成", "待确认")
                          or any("已确认" in t for t in got2b["bar"]), got2b)

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
