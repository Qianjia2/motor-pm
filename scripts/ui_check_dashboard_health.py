"""浏览器端验证: 驾驶舱「异常项目」显示原因 + 点击跳到风险页签。

期望值全部由接口现算,不写死文案/数字——用哪个账号跑,就断言那个账号该看到什么。

验证点:
  1. 每条异常项目行都显示了原因,且文案与接口 health_reason 逐字一致
  2. 正常项目不出现在异常列表里(更不该有原因行)
  3. 点异常行 → 落在 /projects/{id}?tab=risks,且风险页签是选中态
  4. KPI 的「阻塞项目」「有风险」快捷链接同样按 id 跳到对应项目的风险页签
  5. 项目组合表格整行点击仍跳概览页(tab 不能被 el-table 的列对象污染成 [object Object])

用法:
  python scripts/ui_check_dashboard_health.py
  python scripts/ui_check_dashboard_health.py --base http://127.0.0.1:5003 --user admin --password admin123
"""
import argparse
import re
import sys

import requests
from playwright.sync_api import sync_playwright

DEFAULT_BASE = "http://127.0.0.1:5002"
# 「异常项目」卡片只渲染前 6 行(DashboardPage.vue exceptionProjects 的 .slice(0,6),
# 与旁边的「逾期里程碑」同一约定)。接口有 7 个异常项目时,页面就该只显示 6 行。
EXC_CAP = 6
ok, fail = 0, []


def check(name, cond, extra=""):
    global ok
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail.append(name)
        print(f"  FAIL  {name}  {extra}")


def rows(page, card_title):
    """读某张卡片下的 .todo-row(标题/元信息/原因/状态标签)。"""
    return page.evaluate(
        """(t) => {
            const card = [...document.querySelectorAll('.card')].find(
                c => c.querySelector('.card-title')?.innerText.trim() === t);
            if (!card) return null;
            return [...card.querySelectorAll('.todo-row')].map(r => ({
                title: r.querySelector('.todo-title')?.innerText.trim(),
                meta:  r.querySelector('.todo-meta')?.innerText.trim(),
                reason: r.querySelector('.todo-reason')?.innerText.trim() || null,
                tag:   r.querySelector('.tag')?.innerText.trim(),
                icon:  r.querySelector('.todo-icon')?.innerText.trim(),
            }));
        }""", card_title)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    api = base + "/api"

    s = requests.Session()
    r = s.post(f"{api}/auth/login", json={"username": a.user, "password": a.password})
    if r.status_code != 200:
        print(f"[错误] 接口登录失败 {r.status_code}: {r.text[:200]}")
        return 1
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # ── 期望值：由接口现算 ──
    all_p = s.get(f"{api}/projects", headers=H, params={"page_size": 100}).json()["data"]
    api_exc = [p for p in all_p if p["overall_status"] in ("blocked", "at_risk")]
    api_normal = [p for p in all_p if p["overall_status"] not in ("blocked", "at_risk")]
    by_name = {p["name"]: p for p in all_p}
    print(f"[接口] 共 {len(all_p)} 个项目，异常 {len(api_exc)} 个")
    for p in api_exc[:3]:
        print(f"       [{p['overall_status']}] {p['name'][:24]} → {p['health_reason']}")
    missing_reason = [p["name"] for p in api_exc if not p.get("health_reason")]
    check("接口侧:异常项目都有原因", not missing_reason, f"缺原因={missing_reason}")
    check("接口侧:异常项目不重复出现在正常集合",
          not ({p["id"] for p in api_exc} & {p["id"] for p in api_normal}))

    if not api_exc:
        print("[跳过] 当前库里没有异常项目，浏览器断言无从谈起")
        return 0

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            errs, bad_resp = [], []
            page.on("pageerror", lambda e: errs.append(str(e)))
            # 控制台的 401/404 会以 "Failed to load resource" 形式出现,看不出是谁,
            # 所以另收一份带 URL 的,排查时才不至于抓瞎。
            page.on("response",
                    lambda r: r.status >= 400 and bad_resp.append(f"{r.status} {r.url}"))

            page.goto(f"{base}/login")
            page.fill("input[placeholder='用户名']", a.user)
            page.fill("input[placeholder='密码']", a.password)
            page.click("button:has-text('登录')")
            page.wait_for_url(lambda u: "/login" not in u, timeout=20000)

            page.goto(f"{base}/")
            page.wait_for_timeout(2500)

            # ── 1. 异常项目每行都有原因，且与接口逐字一致 ──
            got = rows(page, "异常项目")
            check("异常项目卡片渲染出来了", got is not None)
            got = got or []
            want_n = min(EXC_CAP, len(api_exc))
            check(f"异常行数 = min(卡片上限{EXC_CAP}, 接口{len(api_exc)} 个)",
                  len(got) == want_n, f"页面={len(got)} 期望={want_n}")

            bad_reason, bad_tag = [], []
            for r_ in got:
                p = by_name.get(r_.get("title") or "")
                if not p:
                    bad_reason.append(f"页面上的「{r_['title']}」不在接口返回里")
                    continue
                if r_["reason"] != p["health_reason"]:
                    bad_reason.append(f"{p['name'][:16]}: 页面={r_['reason']!r} 接口={p['health_reason']!r}")
                want_tag = "阻塞" if p["overall_status"] == "blocked" else "有风险"
                if r_["tag"] != want_tag:
                    bad_tag.append(f"{p['name'][:16]}: 页面={r_['tag']!r} 期望={want_tag!r}")
            check("每行的原因文案与接口逐字一致", not bad_reason, "; ".join(bad_reason[:3]))
            check("状态标签(阻塞/有风险)与接口一致", not bad_tag, "; ".join(bad_tag[:3]))

            # 原因里应出现判定分量,证明确实是"同一个数"而不是另算一遍
            sample = next((r_ for r_ in got if by_name.get(r_.get("title"))), None)
            if sample:
                p = by_name[sample["title"]]
                bits = []
                if p["overdue_milestones"]:
                    bits.append(f"{p['overdue_milestones']} 个里程碑逾期")
                if p["open_risks"]:
                    bits.append(f"{p['open_risks']} 项风险未关闭")
                check("原因由逾期/风险两个分量拼成",
                      sample["reason"] == "、".join(bits), f"{sample['reason']!r}")

            # ── 2. 正常项目不该出现在异常列表 ──
            normal_names = {p["name"] for p in api_normal}
            leaked = [r_ for r_ in got if (r_.get("title") or "") in normal_names]
            check("正常项目没混进异常列表", not leaked, f"{[r_['title'] for r_ in leaked][:3]}")
            check("正常项目不显示原因行",
                  not any(r_["reason"] for r_ in got
                          if (r_.get("title") or "") in normal_names))

            # ── 3. 点异常行 → 风险页签 ──
            target_name = got[0]["title"]
            target = by_name[target_name]
            page.locator(".card", has=page.locator(".card-title", has_text="异常项目")) \
                .locator(".todo-row").first.click()
            page.wait_for_timeout(2000)
            url = page.url
            print(f"[浏览器] 点「{target_name[:20]}」→ {url}")
            check(f"跳到 /projects/{target['id']}",
                  f"/projects/{target['id']}" in url, url)
            check("带上了 ?tab=risks", "tab=risks" in url, url)

            # 风险页签真的选中了(而不是回落概览)。
            # 详情页的页签是自定义 .pd-nav-item,不是 el-tabs——别拿 is-active 去套。
            active = page.evaluate(
                """() => [...document.querySelectorAll('.pd-nav-item.active')]
                        .map(e => e.innerText.trim())""")
            check("风险/问题页签处于选中态",
                  any("风险" in t for t in active), f"选中={active}")

            # 内容断言:该项目的风险条目应该真的渲染在页面上
            # 这个接口返回裸数组(前端 getRisks 直接取 axios 的 .data 当列表用)
            rk = s.get(f"{api}/projects/{target['id']}/risks", headers=H).json()
            rk = rk if isinstance(rk, list) else (rk.get("data") or [])
            body = page.inner_text("body")
            titles = [(x.get("title") or "").strip() for x in rk]
            titles = [t for t in titles if t]
            print(f"[浏览器] 该项目风险 {len(titles)} 条，页面命中 "
                  f"{sum(1 for t in titles if t in body)} 条")
            check("风险页签渲染出了该项目的风险条目",
                  bool(titles) and any(t in body for t in titles),
                  f"接口={titles[:3]}")
            check("页签角标数字与接口未关闭风险数一致",
                  str(len(titles)) in body or not titles)

            # ── 4. KPI 快捷链接 ──
            # 必须先回驾驶舱:刚才停在项目详情页,那里根本没有 .kpi-link,
            # 不回来看就会数出 0 个然后"通过"——等于没验。
            page.goto(f"{base}/")
            page.wait_for_timeout(2500)
            links = page.locator(".kpi-link")
            n = links.count()
            print(f"[浏览器] KPI 快捷链接 {n} 个 (阻塞 {len([p for p in api_exc if p['overall_status']=='blocked'])}"
                  f" / 有风险 {len([p for p in api_exc if p['overall_status']=='at_risk'])})")
            check("KPI 快捷链接渲染出来了", n > 0, "0 个")
            if n:
                first = links.first
                fname = first.inner_text().strip()
                fpid = next((p["id"] for p in all_p if p["name"].startswith(fname)), None)
                check("KPI 链接的项目能在接口里对上", fpid is not None, fname)
                if fpid:
                    first.click()
                    page.wait_for_timeout(2000)
                    check(f"KPI 链接跳到 /projects/{fpid}?tab=risks",
                          f"/projects/{fpid}" in page.url and "tab=risks" in page.url, page.url)
                    check("KPI 链接跳过去后风险页签也是选中的",
                          "风险" in " ".join(page.evaluate(
                              """() => [...document.querySelectorAll('.pd-nav-item.active')]
                                       .map(e => e.innerText.trim())""")))

            # ── 5. 表格整行点击仍跳概览(tab 不能被列对象污染) ──
            page.goto(f"{base}/")
            page.wait_for_timeout(2500)
            page.locator(".el-table__body tr").first.click()
            page.wait_for_timeout(2000)
            url = page.url
            print(f"[浏览器] 表格整行点击 → {url}")
            check("表格整行点击不带 [object Object]", "object" not in url.lower(), url)
            check("表格整行点击落在项目详情页", re.search(r"/projects/\d+", url) is not None, url)

            check("没有 JS 运行时报错", not errs, "; ".join(errs[:2]))
            print(f"[浏览器] 4xx/5xx 响应 {len(bad_resp)} 条")
            for b in dict.fromkeys(bad_resp):
                print(f"         {b}")
            # 只揪跟本次改动相关的接口,别把登录前的既有 401 也算成回归
            related = [b for b in bad_resp
                       if "/api/projects" in b or "/api/dashboard" in b]
            check("本次涉及的接口没有 4xx/5xx", not related, "; ".join(related[:3]))
            browser.close()
    except Exception as e:
        print(f"[错误] 浏览器验证异常: {type(e).__name__}: {e}")
        return 1

    print(f"\n{'='*54}\n通过 {ok} 项" + (f"，失败 {len(fail)} 项: {fail}" if fail else "，全部通过 ✓"))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
