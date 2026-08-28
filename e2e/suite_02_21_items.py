"""E2E: 识别21种物料 → 内部模板 → 生成并编辑 → 草稿含全部21种 → 保存 → 导出 1:1 模板"""
import sys, json, io, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import asyncio, urllib.request, urllib.error, uuid
from playwright.async_api import async_playwright

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)
BASE = os.environ.get("E2E_BASE", "http://localhost:5002")
API = BASE + "/api"
OUT = os.path.join(_OUT, "export_21.xls")
TPL = os.path.join(_ROOT, "data", "bom_internal_template.xls")

# 21 种物料(与真实识别同构)
MOCK = []
cats = [("半成品", 4), ("成品", 9), ("辅料", 8)]
n = 0
names = []
for cat, cnt in cats:
    for i in range(cnt):
        n += 1
        nm = f"{cat}{i+1:02d}号物料-{n}"
        names.append(nm)
        MOCK.append({"seq": n, "category": cat, "code": f"MC{cats.index((cat, cnt)):02d}-{i+1:02d}",
                     "name": nm, "spec": f"规格{n}×100", "position": f"ZN-{n:04d}",
                     "package": "", "brand": "", "unit": "个", "qty": n,
                     "supplier": "", "price": "", "note": f"备注{n}"})

results = []
def check(name, cond, detail=""):
    results.append((name, cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {str(detail)[:160]}")

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
    st, body = api("POST", "/auth/login", body={"username": "admin", "password": "admin123"})
    token = json.loads(body).get("access_token")
    check("API登录", token is not None)

    # 基线: 测试开始前最大 BOM id, 结束后清理本次新建的测试BOM
    st, body = api("GET", "/bom-lists", token)
    pre_items = json.loads(body)
    if not isinstance(pre_items, list):
        pre_items = pre_items.get("items") or pre_items.get("data") or []
    baseline_id = max((x.get("id", 0) for x in pre_items), default=0)

    # 0. 后端直测: /bom/generate 带 items
    st, body = api("POST", "/bom/generate", token,
                   body={"template": "internal", "preview": True, "items": MOCK})
    j = json.loads(body)
    if st == 200 and j.get("items"):
        filled = [r for r in j["items"] if r[3] or r[2]]
        check("后端 generate 返回21种", len(filled) == 21, f"n={len(filled)}")
        from collections import Counter
        c = Counter(r[0] for r in filled)
        check("分组: 半成品4/标准件9/辅材8", c == {"半成品": 4, "标准件": 9, "辅材": 8}, dict(c))
        got_names = {r[3] for r in filled}
        check("物料名全对应", got_names == set(names), f"缺{len(set(names) - got_names)}")
    else:
        check("后端 generate 返回21种", False, f"st={st} {body[:200]}")

    # 1. UI 全流程(拦截识别接口, 模拟图纸返回21种)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1700, "height": 950})
        await page.route("**/api/bom/from-drawing", lambda route: route.fulfill(
            content_type="application/json",
            body=json.dumps({"items": MOCK, "raw_answer": "mock"})))
        await page.goto(BASE + "/login")
        await page.fill('input[placeholder="用户名"]', "admin")
        await page.fill('input[placeholder="密码"]', "admin123")
        await page.click('button:has-text("登 录"), button:has-text("登录")')
        await page.wait_for_url("**/my-work", timeout=10000)
        await page.goto(BASE + "/bom")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(800)

        await page.click('button:has-text("自动生成BOM")')
        await page.wait_for_timeout(800)
        # 选 内部模板
        dlg = page.locator('.el-dialog:visible').first
        await dlg.locator('.el-select').first.click()
        await page.wait_for_timeout(500)
        await page.evaluate("""(label) => {
            const items = [...document.querySelectorAll('.el-select-dropdown__item')];
            const el = items.find(e => e.offsetParent !== null && e.textContent.includes(label));
            if (el) el.click();
        }""", "内部模板")
        await page.wait_for_timeout(500)

        # 上传图纸(识别输入框) → 触发识别(被拦截)
        await page.set_input_files('.el-dialog:visible input[type="file"][accept*="image"]', {
            "name": "drawing.png", "mimeType": "image/png", "buffer": b"\x89PNG\r\n\x1a\n"
        })
        await page.wait_for_timeout(2500)
        status = await page.evaluate("""() => {
            const dlg = [...document.querySelectorAll('.el-dialog')].find(d => d.offsetParent !== null);
            return dlg ? dlg.textContent : '';
        }""")
        check("识别状态含21项", "21" in status and "识别到" in status, status[:120])

        # 识别成功自动弹出图纸核对弹窗(13列, 含"保存为BOM") → 点取消关闭(保留genItems)
        await page.evaluate("""() => {
            const dlgs = [...document.querySelectorAll('.el-dialog')].filter(d => d.offsetParent !== null);
            const dlg = dlgs[dlgs.length - 1];  // 后开的最上层
            const btn = [...(dlg?.querySelectorAll('button') || [])].find(b => b.textContent.includes('取消'));
            if (btn) btn.click();
        }""")
        await page.wait_for_timeout(600)

        # 点击 生成并编辑
        await page.evaluate("""() => {
            const dlg = [...document.querySelectorAll('.el-dialog')].find(d => d.offsetParent !== null && d.textContent.includes('自动生成'));
            const btn = [...(dlg?.querySelectorAll('button') || [])].find(b => b.textContent.includes('生成并编辑'));
            if (btn) btn.click();
        }""")
        await page.wait_for_timeout(1500)

        # 2. 内部模板草稿弹窗: 21 种物料都在
        draft = await page.evaluate("""() => {
            const dlg = [...document.querySelectorAll('.el-dialog')].find(d => d.offsetParent !== null && d.textContent.includes('核对并编辑'));
            if (!dlg) return { found: false, rows: [], text: '' };
            const table = dlg.querySelector('.el-table, table');
            const rows = [];
            if (table) {
                for (const tr of table.querySelectorAll('tbody tr')) {
                    const tds = [...tr.querySelectorAll('td')].map(td => {
                        const sel = td.querySelector('.el-select');
                        if (sel) return sel.innerText.trim();
                        const inp = td.querySelector('input');
                        if (inp) return inp.value.trim();
                        return td.textContent.trim();
                    });
                    rows.push(tds);
                }
            }
            return { found: true, rows, text: dlg.innerText.slice(0, 300) };
        }""")
        check("草稿弹窗出现", draft.get("found"), draft.get("text", "")[:100])
        filled_rows = [r for r in draft.get("rows", []) if any(c and c != "pcs" and c != "1" for c in r[2:9])]
        names_in_draft = [r[3] for r in draft.get("rows", []) if r[3]]
        check("草稿含21种物料", len(names_in_draft) == 21, f"有值行={len(filled_rows)} 名称数={len(names_in_draft)}")
        check("21种名称全部匹配", set(names_in_draft) == set(names), f"缺{len(set(names)-set(names_in_draft))}")
        cat_cnt = {}
        for r in draft.get("rows", []):
            if r[3]:
                cat_cnt[r[1]] = cat_cnt.get(r[1], 0) + 1
        check("分组分布 4/9/8", cat_cnt == {"半成品": 4, "标准件": 9, "辅材": 8}, cat_cnt)
        check("总行数36(模板骨架)", len(draft.get("rows", [])) == 36, len(draft.get("rows", [])))

        # 3. 保存
        await page.evaluate("""() => {
            const dlg = [...document.querySelectorAll('.el-dialog')].find(d => d.offsetParent !== null && d.textContent.includes('核对并编辑'));
            const btn = [...(dlg?.querySelectorAll('button') || [])].find(b => b.textContent.includes('保存'));
            if (btn) btn.click();
        }""")
        await page.wait_for_timeout(2500)
        await browser.close()

    # 4. 取最新 BOM 导出并核对
    st, body = api("GET", "/bom-lists", token)
    lst = json.loads(body)
    items = lst if isinstance(lst, list) else (lst.get("items") or lst.get("data") or [])
    check("列表取到BOM", len(items) > 0)
    new_id = items[0]["id"]
    st, raw = api("GET", f"/bom-lists/{new_id}/export-xlsx", token)
    check("导出接口200", st == 200, f"size={len(raw)}")
    with open(OUT, "wb") as f:
        f.write(raw)

    import xlrd
    twb = xlrd.open_workbook(TPL, formatting_info=True)
    ewb = xlrd.open_workbook(OUT, formatting_info=True)
    tsh, esh = twb.sheet_by_index(0), ewb.sheet_by_index(0)
    check("行列数一致", (esh.nrows, esh.ncols) == (tsh.nrows, tsh.ncols))
    check("合并单元格一致", sorted(esh.merged_cells) == sorted(tsh.merged_cells))

    # 分组物料落位: 半成品R11-14(4), 标准件R31-39(9), 辅材R42-49(8), 主材R17-29 空白
    for r in range(11, 15):
        check(f"半成品行R{r}有值", bool(str(esh.cell_value(r, 2)).strip()))
    for r in range(17, 30):
        v = str(esh.cell_value(r, 2)).strip()
        if r < 30 and v:
            check(f"主材R{r}应空白", False, v[:30])
            break
    else:
        check("主材区R17-29空白", True)
    std_n = sum(1 for r in range(31, 40) if str(esh.cell_value(r, 2)).strip())
    check("标准件9行有值", std_n == 9, f"n={std_n}")
    aux_n = sum(1 for r in range(42, 50) if str(esh.cell_value(r, 2)).strip())
    check("辅材8行有值", aux_n == 8, f"n={aux_n}")
    check("R16仍为主材分组行", str(esh.cell_value(16, 0)).strip() == "主材")
    check("R50仍为注释行", "注" in str(esh.cell_value(50, 0)).strip())
    # 序号连续 1..21
    seqs = [str(esh.cell_value(r, 0)).strip() for r in [*range(11, 15), *range(31, 40), *range(42, 50)]]
    seqs = [s for s in seqs if s]
    check("序号1..21连续", [str(i) for i in range(1, 22)] == seqs, f"共{len(seqs)}个")
    # 表头值仍自动填
    check("总装图图号已填", str(esh.cell_value(2, 4)).strip().startswith("ZN-"))
    check("版本V1.0", str(esh.cell_value(1, 5)).strip() == "V1.0")
    check("条形码8位", len(str(esh.cell_value(1, 4)).strip()) == 8)

    # 清理测试产生的 BOM(id > baseline)
    st, body = api("GET", "/bom-lists", token)
    cur = json.loads(body)
    if not isinstance(cur, list):
        cur = cur.get("items") or cur.get("data") or []
    for x in cur:
        if x.get("id", 0) > baseline_id:
            api("DELETE", f"/bom-lists/{x['id']}", token)
            print("已清理测试BOM:", x["id"])

    npass = sum(1 for _, c in results if c)
    print(f"\n==== {npass}/{len(results)} PASS ====")
    sys.exit(0 if npass == len(results) else 1)

asyncio.run(main())
