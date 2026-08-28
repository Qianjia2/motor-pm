"""全流程验证: UI 自动生成→表头检查→填写→保存→导出 .xls 与模板 1:1 比对"""
import sys, io, json, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import asyncio, urllib.request, urllib.error
from playwright.async_api import async_playwright

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)
BASE = os.environ.get("E2E_BASE", "http://localhost:5002")
API = BASE + "/api"
TPL = os.path.join(_ROOT, "data", "bom_internal_template.xls")
OUT = os.path.join(_OUT, "export_check.xls")

results = []
def check(name, cond, detail=""):
    results.append((name, cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {str(detail)[:180]}")

def api(method, path, token=None, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token: r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

async def main():
    # 1. 登录
    st, body = api("POST", "/auth/login", body={"username": "admin", "password": "admin123"})
    token = json.loads(body).get("access_token")
    check("API登录", token is not None)
    st, body = api("GET", "/bom-lists", token)
    pre = json.loads(body)
    if not isinstance(pre, list): pre = pre.get("items") or []
    baseline_id = max((x.get("id", 0) for x in pre), default=0)

    # 2. UI 自动生成
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1700, "height": 950})
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
        gen = page.locator('.el-dialog:visible')
        await gen.locator('.el-select').first.click()
        await page.wait_for_timeout(600)
        await page.evaluate("""(label) => {
            const items = [...document.querySelectorAll('.el-select-dropdown__item')];
            const el = items.find(e => e.offsetParent !== null && e.textContent.includes(label));
            if (el) el.click();
        }""", "内部模板")
        await page.wait_for_timeout(600)
        await page.evaluate("""() => {
            const dlgs = [...document.querySelectorAll('.el-dialog')].filter(d => d.offsetParent !== null);
            const btn = dlgs.flatMap(d => [...d.querySelectorAll('button')]).find(b => b.textContent.includes('生成并编辑'));
            if (btn) btn.click();
        }""")
        await page.wait_for_timeout(1500)

        # 3. 草稿弹窗表头区字段与自动填充值
        info = await page.evaluate("""() => {
            const dlgs = [...document.querySelectorAll('.el-dialog')].filter(d => d.offsetParent !== null);
            const dlg = dlgs.find(d => d.textContent.includes('核对并编辑'));
            const sec = dlg ? dlg.querySelector('.el-dialog__body') : null;
            if (!sec) return { found: false, pairs: [] };
            const pairs = [];
            for (const div of sec.querySelectorAll('div')) {
                const inp = div.querySelector('input');
                const span = div.querySelector('span');
                if (inp && span) pairs.push(span.textContent.trim() + '=' + (inp.value || ''));
            }
            return { found: sec.innerText.includes('生产商名称'), pairs: pairs };
        }""")
        check("草稿弹窗表头区存在", info.get("found"))
        for pair in info.get("pairs", [])[:18]:
            print("   ", pair)
        joined = " ".join(info.get("pairs", []))
        check("自动填: 总装图图号", "总装图图号=ZN-" in joined, "查找 ZN- 前缀")
        bc = [p.split("=")[1] for p in info.get("pairs", []) if p.startswith("条形码") and "=" in p]
        check("自动填: 条形码(YYMM+4位)", bool(bc) and len(bc[0]) == 8 and bc[0][:4].isdigit(), bc[:1])
        check("自动填: 版本", "当前版本=V1.0" in joined)
        check("自动填: 编制时间", "编制时间=20" in joined)

        # 4. 填 产品名称/规格 + 客户名称（图号）→ 保存
        await page.evaluate("""() => {
            const dlgs = [...document.querySelectorAll('.el-dialog')].filter(d => d.offsetParent !== null);
            const dlg = dlgs.find(d => d.textContent.includes('核对并编辑'));
            const body = dlg ? dlg.querySelector('.el-dialog__body') : null;
            if (!body) return;
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            for (const div of body.querySelectorAll('div')) {
                const inp = div.querySelector('input');
                const span = div.querySelector('span');
                if (!inp || !span) continue;
                const lbl = span.textContent.trim();
                if (lbl.includes('产品名称')) { setter.call(inp, '交流伺服电机 PM-2000'); inp.dispatchEvent(new Event('input', {bubbles: true})); }
                if (lbl.includes('客户名称')) { setter.call(inp, 'ZN-2026-0001'); inp.dispatchEvent(new Event('input', {bubbles: true})); }
            }
        }""")
        await page.evaluate("""() => {
            const dlgs = [...document.querySelectorAll('.el-dialog')].filter(d => d.offsetParent !== null);
            const btn = dlgs.flatMap(d => [...d.querySelectorAll('button')]).find(b => b.textContent.includes('保存'));
            if (btn) btn.click();
        }""")
        await page.wait_for_timeout(2000)
        await browser.close()

    # 5. 取最新 BOM 并导出
    st, body = api("GET", "/bom-lists", token)
    lst = json.loads(body)
    items = lst if isinstance(lst, list) else (lst.get("items") or lst.get("data") or [])
    check("列表取到BOM", len(items) > 0, f"n={len(items)}")
    if not items:
        return
    new_id = items[0]["id"]
    print("最新BOM id:", new_id, "name:", items[0].get("name", ""))
    st, raw = api("GET", f"/bom-lists/{new_id}/export-xlsx", token)
    check("导出接口 200", st == 200, f"status={st} size={len(raw)}")
    with open(OUT, "wb") as f:
        f.write(raw)

    # 6. xlrd 与模板逐格比对
    import xlrd
    twb = xlrd.open_workbook(TPL, formatting_info=True)
    ewb = xlrd.open_workbook(OUT, formatting_info=True)
    tsh, esh = twb.sheet_by_index(0), ewb.sheet_by_index(0)
    check("行列数一致", (esh.nrows, esh.ncols) == (tsh.nrows, tsh.ncols),
          f"tpl={tsh.nrows}x{tsh.ncols} exp={esh.nrows}x{esh.ncols}")
    check("合并单元格一致", sorted(esh.merged_cells) == sorted(tsh.merged_cells),
          f"tpl={len(tsh.merged_cells)} exp={len(esh.merged_cells)}")

    # 表头值位置
    cells = [("产品名称/规格", (1, 3)), ("条形码", (1, 4)), ("当前版本", (1, 5)), ("编制时间", (1, 7)),
             ("客户名称", (2, 2)), ("总装图图号", (2, 4)), ("定子组件图号", (2, 7)),
             ("电机编号", (3, 2)), ("外形图图号", (3, 4)), ("转子组件图号", (3, 7)),
             ("电机编码", (4, 2)), ("接口类型", (4, 4)), ("定子半成品", (4, 7)),
             ("电磁方案号", (5, 2)), ("电气原理图图号", (5, 4)), ("绕组", (5, 7)), ("性能参数", (7, 2))]
    # 有值字段必须写入模板位置; 无值字段对应格必须保持空白(模板原样)
    filled = [("产品名称/规格", (1, 3), "交流伺服电机 PM-2000"), ("客户名称", (2, 2), "ZN-2026-0001"),
              ("总装图图号", (2, 4), None), ("版本", (1, 5), "V1.0"), ("条形码", (1, 4), None),
              ("编制时间", (1, 7), None)]
    empty_ok = [("定子组件图号", (2, 7)), ("电机编号", (3, 2)), ("外形图图号", (3, 4)), ("转子组件图号", (3, 7)),
                ("电机编码", (4, 2)), ("接口类型", (4, 4)), ("定子半成品", (4, 7)),
                ("电磁方案号", (5, 2)), ("电气原理图图号", (5, 4)), ("绕组", (5, 7)),
                ("性能参数", (7, 2))]
    for lbl, (r, c), expect in filled:
        v = str(esh.cell_value(r, c)).strip()
        ok = (v == expect) if expect else bool(v)
        check(f"表头值 R{r}C{c}({lbl})", ok, v[:50])
    for lbl, (r, c) in empty_ok:
        v = str(esh.cell_value(r, c)).strip()
        check(f"未填字段保持空白 R{r}C{c}({lbl})", v == "", v[:30])

    # 分组行/注释行原样
    for r, lbl in ((10, "半成品"), (16, "主材"), (30, "标准件"), (41, "辅材"), (50, "注")):
        v = str(esh.cell_value(r, 0)).strip()
        check(f"分组/注释行 R{r} 保留", lbl in v, v[:40])
    # 半成品区有物料行
    semi = [str(esh.cell_value(r, 2)).strip() for r in range(11, 16)]
    check("半成品区有物料", any(semi), semi[:4])
    # 未溢出: R16 仍为主材分组行
    check("物料未溢出分组", str(esh.cell_value(16, 0)).strip() == "主材")

    # 样式逐格比对
    def xf_tuple(book, sheet, r, c):
        xf = book.xf_list[sheet.cell_xf_index(r, c)]
        f = book.font_list[xf.font_index]
        b = xf.border
        bg = xf.background
        a = xf.alignment
        return (f.height, f.bold, f.name, f.colour_index, f.weight,
                (b.left_line_style, b.right_line_style, b.top_line_style, b.bottom_line_style),
                bg.fill_pattern, bg.pattern_colour_index,
                a.hor_align, a.vert_align, a.text_wrapped,
                book.format_map[xf.format_key].format_str)
    diff = [(r, c) for r in range(tsh.nrows) for c in range(tsh.ncols)
            if xf_tuple(twb, tsh, r, c) != xf_tuple(ewb, esh, r, c)]
    check("全部单元格样式一致", len(diff) == 0, f"不一致={len(diff)} {diff[:6]}")

    # 行高/列宽
    h_diff = [r for r in range(tsh.nrows)
              if tsh.rowinfo_map.get(r) and esh.rowinfo_map.get(r)
              and tsh.rowinfo_map[r].height != esh.rowinfo_map[r].height]
    check("行高一致", not h_diff, h_diff[:6])
    w_diff = [c for c in range(tsh.ncols)
              if tsh.colinfo_map.get(c) is not None and esh.colinfo_map.get(c) is not None
              and tsh.colinfo_map[c].width != esh.colinfo_map[c].width]
    check("列宽一致", not w_diff, w_diff[:6])

    # 清理本次新建的测试BOM
    st, body = api("GET", "/bom-lists", token)
    cur = json.loads(body)
    if not isinstance(cur, list): cur = cur.get("items") or []
    for x in cur:
        if x.get("id", 0) > baseline_id:
            api("DELETE", f"/bom-lists/{x['id']}", token)
            print("已清理测试BOM:", x["id"])

    npass = sum(1 for _, c in results if c)
    print(f"\n==== {npass}/{len(results)} PASS ====")
    sys.exit(0 if npass == len(results) else 1)

asyncio.run(main())
