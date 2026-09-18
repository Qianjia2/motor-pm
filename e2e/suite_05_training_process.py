"""验证: 培训学习-项目管理流程可视化 — 从商务对接到结题归档的全流程、
岗位筛选高亮、阶段交付物表、硬件/软件切换。"""
import sys, json, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import asyncio, urllib.request, urllib.error
from playwright.async_api import async_playwright

BASE = os.environ.get("E2E_BASE", "http://localhost:5002")
API = BASE + "/api"

results = []
def check(name, cond, detail=""):
    results.append((name, cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {str(detail)[:140]}")

def api(method, path, token=None, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token: r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


async def main():
    # ── 1. 接口先行: 数据源本身要正确 ──
    st, body = api("POST", "/auth/login", body={"username": "admin", "password": "admin123"})
    token = json.loads(body).get("access_token")
    check("API登录", token is not None)

    st, body = api("GET", "/training/process-flow?project_type=hardware", token)
    flow = json.loads(body) if st == 200 else {}
    stages = flow.get("stages", [])
    keys = [s["key"] for s in stages]
    check("接口: 硬件全流程", st == 200 and keys[0] == "PRE" and keys[-1] == "POST",
          f"st={st} keys={keys}")
    phase_keys = [s["key"] for s in stages if s["kind"] == "phase"]
    check("接口: 含P0-PP5", phase_keys == ["P0", "PP1", "PP2", "PP3", "PP4", "PP5"], phase_keys)
    pre = stages[0] if stages else {}
    check("接口: 前置含合同与立项",
          "合同" in " ".join(n["name"] for n in pre.get("nodes", [])) and
          "立项" in " ".join(n["name"] for n in pre.get("nodes", [])))

    # 平台边界: 审批在钉钉, 平台只做阶段门把关
    notes = flow.get("notes", [])
    check("接口: 返回平台边界说明",
          len(notes) >= 3 and "钉钉" in "".join(notes) and "阶段门" in "".join(notes),
          f"{len(notes)} 条")
    venues = {n["name"]: n.get("venue") for n in pre.get("nodes", [])}
    approvals = ("合同评审与签订", "发起立项申请", "立项审批")
    check("接口: 审批节点标注钉钉",
          all(venues.get(x) == "钉钉" for x in approvals), venues)
    join = next((n for n in pre.get("nodes", []) if "建项目" in n["name"]), {})
    check("接口: 交接点在本平台且落到团队配置",
          join.get("venue") == "本平台" and "团队" in (join.get("module") or ""),
          f"{join.get('venue')} | {join.get('module')}")

    # ── 2. 浏览器: 页面真实渲染 ──
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 950})
        await page.goto(BASE + "/login")
        await page.fill('input[placeholder="用户名"]', "admin")
        await page.fill('input[placeholder="密码"]', "admin123")
        await page.click('button:has-text("登 录"), button:has-text("登录")')
        await page.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        await page.goto(BASE + "/training")
        await page.wait_for_timeout(1200)

        # 切到流程页签
        await page.click('.el-tabs__item:has-text("项目管理流程")')
        await page.wait_for_timeout(1500)

        txt = await page.evaluate("() => document.body.innerText")
        check("流程页打开", "商务对接与立项" in txt, txt[:100])
        check("渲染前置节点: 合同签订", "合同评审与签订" in txt)
        check("渲染前置节点: 立项", "发起立项申请" in txt)
        check("渲染收尾: 结题归档", "结题与归档" in txt)
        check("渲染硬件阶段", all(k in txt for k in ("P0", "PP1", "PP2", "PP3", "PP4", "PP5")))
        check("渲染门禁标签", "G1 概念评审" in txt and "G5 定型评审" in txt)

        # 平台边界横幅
        banner = await page.evaluate("""() => {
            const b = document.querySelector('.boundary-note');
            return b ? { visible: b.offsetParent !== null, text: b.innerText } : null;
        }""")
        check("渲染平台边界横幅", banner and banner["visible"] and "钉钉" in banner["text"],
              banner and banner["text"][:80])

        # 前置节点上的「在哪办」标签
        pre_tags = await page.evaluate("""() => {
            const row = [...document.querySelectorAll('.flow-row')]
                .find(r => r.querySelector('.dot')?.textContent.trim() === 'PRE');
            return [...(row?.querySelectorAll('.node-head .venue-tag') || [])]
                .map(e => e.innerText.trim());
        }""")
        check("前置节点标注在哪办",
              pre_tags == ['本平台', '线下', '钉钉', '钉钉', '钉钉', '本平台', '线下'],
              pre_tags)
        check("合同与立项节点标为钉钉", pre_tags[2:5] == ['钉钉'] * 3, pre_tags[2:5])
        check("已取消立项审查与分级", "立项审查与分级" not in txt)

        # 时间轴圆点数量: PRE + 6 阶段 + POST = 8
        dots = await page.locator(".axis .dot").count()
        check("时间轴圆点数=8", dots == 8, f"实际 {dots}")

        # ── 3. 岗位筛选: 选「测试工程师」 ──
        await page.click('.filter-right .el-select')
        await page.wait_for_timeout(500)
        await page.evaluate("""() => {
            const items = [...document.querySelectorAll('.el-select-dropdown__item')];
            const el = items.find(e => e.offsetParent !== null && e.textContent.trim() === '测试工程师');
            if (el) el.click();
        }""")
        await page.wait_for_timeout(900)
        txt2 = await page.evaluate("() => document.body.innerText")
        check("岗位筛选出概览", "测试工程师" in txt2 and "个阶段共" in txt2, txt2[:120])
        check("标记我的阶段", "我在此阶段" in txt2)

        mine = await page.locator(".flow-row.mine").count()
        dim = await page.locator(".flow-row.dimmed").count()
        check("高亮我的阶段/压暗无关阶段", mine >= 1 and dim >= 1, f"mine={mine} dim={dim}")

        # ── 4. 展开 PP3(验证阶段)看交付物表 ──
        # 注意: 阶段体是 v-show 隐藏, 表格仍在 DOM 中; 必须按轴上的阶段码定位到该行。
        await page.evaluate("""() => {
            const row = [...document.querySelectorAll('.flow-row')]
                .find(r => r.querySelector('.dot')?.textContent.trim() === 'PP3');
            if (row) row.querySelector('.stage-head').click();
        }""")
        await page.wait_for_timeout(800)
        tbl = await page.evaluate("""() => {
            const row = [...document.querySelectorAll('.flow-row')]
                .find(r => r.querySelector('.dot')?.textContent.trim() === 'PP3');
            const t = row?.querySelector('.deliver-table');
            if (!t) return null;
            return {
                visible: t.offsetParent !== null,
                heads: [...t.querySelectorAll('.el-table__header th')].map(e => e.innerText.trim()),
                mine: t.querySelectorAll('tr.row-mine').length,
                dim: t.querySelectorAll('tr.row-dim').length,
                mineNames: [...t.querySelectorAll('tr.row-mine .d-name')].map(e => e.innerText.trim()),
            };
        }""")
        check("PP3 已展开且表格可见", tbl and tbl["visible"], tbl and tbl["visible"])
        joined = " ".join(tbl["heads"]) if tbl else ""
        check("交付物表含 谁来做/用什么模板/验收要点",
              "谁来做" in joined and "用什么模板" in joined and "验收要点" in joined, joined[:90])

        # 测试工程师在 PP3 应命中 4 项(样机验证方案/型式试验/可靠性试验/环境适应性试验)
        check("交付物行按岗位高亮", tbl and tbl["mine"] == 4, tbl and
              {"mine": tbl["mine"], "dim": tbl["dim"], "names": tbl["mineNames"]})

        # ── 5. 切换到软件项目 ──
        await page.click('.filter-left .el-radio-button:has-text("软件项目")')
        await page.wait_for_timeout(1500)
        txt3 = await page.evaluate("() => document.body.innerText")
        check("软件项目走 S0-S3", all(k in txt3 for k in ("S0", "S1", "S2", "S3")))
        check("软件项目不出现 PP 阶段", "PP1" not in txt3 and "样机试制阶段" not in txt3)

        await page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "output", "training_process.png"), full_page=True)
        await browser.close()

    npass = sum(1 for _, c in results if c)
    print(f"\n==== {npass}/{len(results)} PASS ====")
    sys.exit(0 if npass == len(results) else 1)

asyncio.run(main())
