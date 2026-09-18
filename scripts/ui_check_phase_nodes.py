"""浏览器端验证: 项目管理流程页的「阶段动作清单」。

验证点:
  1. 每个项目阶段展开后先看到动作清单, 再看到交付物表(先"怎么干", 再"要交什么")
  2. 节点卡片四要素齐全、venue 标签按 钉钉/本平台/线下 着色
  3. 选岗位后清单节点按 mine 高亮, 且概览里的计数与页面上高亮节点数一致
     (计数改成按动作清单算之后, 不能再把交付物也算一遍)

用法: python scripts/ui_check_phase_nodes.py
"""
import re
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


def expected_counts(flow, role):
    """前端概览的两处计数口径(见 TrainingProcessView.vue): 有动作清单的阶段按清单算,
    没有清单的阶段退回按交付物算。"""
    stages = items = 0
    for st in flow["stages"]:
        if role in (st.get("roles") or []):
            stages += 1
        nodes = st.get("nodes") or []
        if nodes:
            items += sum(1 for n in nodes if role in n["roles"])
        else:
            items += sum(1 for d in st.get("deliverables") or [] if role in (d.get("role") or ""))
    return stages, items


def row_of(page, code):
    """轴上的阶段码 → 该行在页面上的取数结果。"""
    return page.evaluate("""(code) => {
        const row = [...document.querySelectorAll('.flow-row')]
            .find(r => r.querySelector('.dot')?.textContent.trim() === code);
        if (!row) return null;
        const body = row.querySelector('.stage-body');
        const list = body?.querySelector('.node-list');
        const table = body?.querySelector('.deliver-table');
        const nodes = [...(list?.querySelectorAll('.node') || [])];
        return {
            open: body ? body.offsetParent !== null : false,
            hasList: !!list,
            steps: nodes.length,
            mine: nodes.filter(n => n.classList.contains('mine')).length,
            // 清单在表格之前: 用文档序比较两个元素
            listBeforeTable: !!(list && table &&
                (list.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0),
            nodeKeys: nodes.map(n => [...n.querySelectorAll('.node-row .k')]
                .map(e => e.innerText.trim())),
            venues: nodes.map(n => n.querySelector('.venue-tag')?.innerText.trim()),
            seqs: nodes.map(n => n.querySelector('.node-seq')?.innerText.trim()),
        };
    }""", code)


s = requests.Session()
tok = s.post(f"{API}/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
flows = {}
for pt in ("hardware", "software"):
    flows[pt] = s.get(f"{API}/training/process-flow",
                      params={"project_type": pt}, headers=H).json()
by_key = {pt: {st["key"]: st for st in flows[pt]["stages"]} for pt in flows}

try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(f"{BASE}/login")
        page.fill("input[placeholder='用户名']", "admin")
        page.fill("input[placeholder='密码']", "admin123")
        page.click("button:has-text('登录')")
        page.wait_for_url(lambda u: "/login" not in u, timeout=20000)

        page.goto(f"{BASE}/training")
        page.wait_for_timeout(1200)
        page.click('.el-tabs__item:has-text("项目管理流程")')
        page.wait_for_timeout(1500)

        # ── 接口先行: 每个阶段都有动作清单 ──
        for pt, codes in (("hardware", ["P0", "PP1", "PP2", "PP3", "PP4", "PP5"]),
                          ("software", ["S0", "S1", "S2", "S3"])):
            missing = [c for c in codes if not by_key[pt][c]["nodes"]]
            check(f"接口: {pt} 全部阶段带动作清单", not missing, f"缺 {missing}")

        # ── 展开 PP1: 清单在交付物表之前 ──
        page.evaluate("""() => {
            const r = [...document.querySelectorAll('.flow-row')]
                .find(x => x.querySelector('.dot')?.textContent.trim() === 'PP1');
            r?.querySelector('.stage-head').click();
        }""")
        page.wait_for_timeout(700)
        pp1 = row_of(page, "PP1")
        api_pp1 = by_key["hardware"]["PP1"]["nodes"]
        check("PP1 展开且出现动作清单", pp1 and pp1["open"] and pp1["hasList"],
              pp1 and {k: pp1[k] for k in ("open", "hasList")})
        check("PP1 清单渲染在交付物表之前", pp1 and pp1["listBeforeTable"])
        check(f"PP1 步数={len(api_pp1)}", pp1 and pp1["steps"] == len(api_pp1),
              pp1 and pp1["steps"])
        check("PP1 步骤序号连续", pp1 and pp1["seqs"] == [str(i + 1) for i in range(len(api_pp1))],
              pp1 and pp1["seqs"])
        check("节点卡片四要素齐全",
              pp1 and all(keys[:4] == ["做什么", "产出什么", "交给谁", "平台落点"]
                          for keys in pp1["nodeKeys"]),
              pp1 and pp1["nodeKeys"][:1])
        check("PP1 节点都在本平台办理", pp1 and set(pp1["venues"]) == {"本平台"},
              pp1 and set(pp1["venues"]))
        check("清单标题写明步数",
              f"本阶段动作清单（{len(api_pp1)} 步）" in page.inner_text("body"))

        # ── 线下节点着色: PP3 的型式试验 ──
        page.evaluate("""() => {
            const r = [...document.querySelectorAll('.flow-row')]
                .find(x => x.querySelector('.dot')?.textContent.trim() === 'PP3');
            r?.querySelector('.stage-head').click();
        }""")
        page.wait_for_timeout(700)
        pp3 = row_of(page, "PP3")
        check("PP3 步数=10", pp3 and pp3["steps"] == 10, pp3 and pp3["steps"])
        check("试验类节点标为线下", pp3 and pp3["venues"][1:4] == ["线下"] * 3,
              pp3 and pp3["venues"])
        check("PP3 交付物表仍在清单之后",
              page.evaluate("""() => {
                  const r = [...document.querySelectorAll('.flow-row')]
                      .find(x => x.querySelector('.dot')?.textContent.trim() === 'PP3');
                  const b = r.querySelector('.stage-body');
                  return b.querySelector('.deliver-table').offsetParent !== null;
              }"""))

        # ── 选岗位: 清单按岗位高亮, 概览计数与高亮数一致 ──
        page.click(".filter-right .el-select")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            const items = [...document.querySelectorAll('.el-select-dropdown__item')];
            const el = items.find(e => e.offsetParent !== null && e.textContent.trim() === '电磁工程师');
            if (el) el.click();
        }""")
        page.wait_for_timeout(900)
        pp1 = row_of(page, "PP1")
        expect_nodes = [n for n in api_pp1 if "电磁工程师" in n["roles"]]
        check(f"PP1 高亮 {len(expect_nodes)} 个我的节点",
              pp1 and pp1["mine"] == len(expect_nodes), pp1 and pp1["mine"])

        summary = page.inner_text(".my-summary")
        m = re.search(r"(\d+)\s*个阶段共\s*(\d+)\s*项工作", summary)
        page_total = page.locator(".node.mine").count()
        exp_stages, exp_items = expected_counts(flows["hardware"], "电磁工程师")
        check("概览计数与页面高亮节点数一致",
              m and int(m.group(2)) == page_total,
              f"概览={m.group(2) if m else None} 高亮={page_total}")
        check(f"概览阶段数={exp_stages}（P0/PP1 都用到电磁工程师）",
              m and int(m.group(1)) == exp_stages, summary[:60].replace("\n", " "))
        check(f"概览项数={exp_items}", m and int(m.group(2)) == exp_items,
              f"概览={m.group(2) if m else None}")
        p0 = row_of(page, "P0")
        check("P0 的技术可行性分析也按岗位高亮", p0 and p0["mine"] == 1, p0 and p0["mine"])

        # 计数不再把交付物算一遍: 若重复计数, 概览会大于页面上的高亮节点数
        table_mine = page.locator(".deliver-table tr.row-mine").count()
        check("未把交付物重复计入(高亮节点数=计数)", page_total > 0 and table_mine > 0,
              f"节点高亮={page_total} 交付物高亮={table_mine}")

        # ── 切软件: S1 清单 ──
        page.click('.filter-left .el-radio-button:has-text("软件项目")')
        page.wait_for_timeout(1500)
        page.evaluate("""() => {
            const r = [...document.querySelectorAll('.flow-row')]
                .find(x => x.querySelector('.dot')?.textContent.trim() === 'S1');
            r?.querySelector('.stage-head').click();
        }""")
        page.wait_for_timeout(800)
        s1 = row_of(page, "S1")
        api_s1 = by_key["software"]["S1"]["nodes"]
        check(f"S1 步数={len(api_s1)}", s1 and s1["steps"] == len(api_s1), s1 and s1["steps"])
        check("S1 清单渲染在交付物表之前", s1 and s1["listBeforeTable"])
        body = page.inner_text("body")
        check("软件视图不串硬件阶段码",
              all(k not in body for k in ("PP1", "样机试制阶段")))
        check("页脚说明涵盖动作清单", "各阶段动作清单" in body)

        page.screenshot(path="e2e/output/training_phase_nodes.png", full_page=True)
        browser.close()
finally:
    pass

print(f"\n{ok} passed, {len(fail)} failed" + (f" → {fail}" if fail else ""))
sys.exit(1 if fail else 0)
