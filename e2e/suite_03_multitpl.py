"""E2E: 新增第二套内部模板 → UI 选择 → 21项生成保存 → 导出落位第二模板 → 删除模板后回退默认"""
import sys, json, io
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import asyncio, urllib.request, urllib.error, uuid, os
from playwright.async_api import async_playwright

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)
BASE = os.environ.get("E2E_BASE", "http://localhost:5002")
API = BASE + "/api"
OUT = os.path.join(_OUT, "export_tpl2.xls")
OUT_FB = os.path.join(_OUT, "export_fallback.xls")

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

def api_form(path, token, file_bytes, filename, name=""):
    boundary = uuid.uuid4().hex
    parts = []
    if name:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"name\"\r\n\r\n{name}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                 f"Content-Type: application/vnd.ms-excel\r\n\r\n".encode() + file_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    data = b"".join(parts)
    r = urllib.request.Request(API + path, data=data, method="POST")
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

# ---- 构造第二套模板: 标题R0, 信息R1(产品名称/规格→(1,3)) R2(总装图图号→(2,3)), 表头R3,
#      半成品R4(行5-8), 主材R9(行10-22), 标准件R23(行24-32), 辅材R33(行34-41), 注R42 ----
import xlwt
wb = xlwt.Workbook()
ws = wb.add_sheet("BOM")
bold = xlwt.easyxf("font: bold on")
title = "测试电机材料清单"
ws.write(0, 0, title, bold)
ws.write(1, 2, "产品名称/规格")
ws.write(2, 2, "总装图图号")
hdr = ["序号", "物料编码", "物料名称", "零件图号", "材料、牌号、规格、技术条件", "单位", "用量", "备注"]
for c, h in enumerate(hdr):
    ws.write(3, c, h, bold)
def group(r, label):
    ws.write(r, 0, label, bold)
group(4, "半成品")
group(9, "主材")
group(23, "标准件")
group(33, "辅材")
ws.write(42, 0, "注: 测试注释行")
buf = io.BytesIO()
wb.save(buf)
TPL2_BYTES = buf.getvalue()

MOCK = []
cats = [("半成品", 4), ("成品", 9), ("辅料", 8)]
n = 0
names = []
for cat, cnt in cats:
    for i in range(cnt):
        n += 1
        nm = f"MT{cat}{i+1:02d}-{n}"
        names.append(nm)
        MOCK.append({"seq": n, "category": cat, "code": f"T{i:02d}-{n}", "name": nm,
                     "spec": f"规格{n}×100", "position": f"ZN-{n:04d}", "package": "", "brand": "",
                     "unit": "个", "qty": n, "supplier": "", "price": "", "note": f"备注{n}"})

async def main():
    st, body = api("POST", "/auth/login", body={"username": "admin", "password": "admin123"})
    token = json.loads(body).get("access_token")
    check("API登录", token is not None)

    st, body = api("GET", "/bom-lists", token)
    pre_items = json.loads(body)
    if not isinstance(pre_items, list): pre_items = pre_items.get("items") or []
    baseline_id = max((x.get("id", 0) for x in pre_items), default=0)

    # 0. 上传第二套模板
    st, body = api_form("/bom-lists/internal-templates", token, TPL2_BYTES, "tpl2.xls", "测试模板")
    j = json.loads(body)
    check("新增模板接口", st == 200 and j.get("id"), body[:120])
    tpl2 = j.get("id", "")
    st, body = api("GET", "/bom-lists/internal-templates", token)
    lst = json.loads(body).get("templates", [])
    t2 = next((t for t in lst if t["id"] == tpl2), None)
    check("列表含新模板", t2 is not None and "测试电机材料清单" in (t2.get("name") or ""), t2)
    check("默认模板仍在", any(t.get("is_default") for t in lst))

    # 1. UI: 选新模板 → 21项 → 生成并编辑 → 保存
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1700, "height": 950})
        await page.route("**/api/bom/from-drawing", lambda route: route.fulfill(
            content_type="application/json", body=json.dumps({"items": MOCK, "raw_answer": "mock"})))
        await page.goto(BASE + "/login")
        await page.fill('input[placeholder="用户名"]', "admin")
        await page.fill('input[placeholder="密码"]', "admin123")
        await page.click('button:has-text("登 录"), button:has-text("登录")')
        await page.wait_for_url("**/my-work", timeout=10000)
        await page.goto(BASE + "/bom")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(800)
        await page.click('button:has-text("自动生成BOM")')
        await page.wait_for_timeout(1000)
        dlg = page.locator('.el-dialog:visible').first
        await dlg.locator('.el-select').first.click()
        await page.wait_for_timeout(700)
        opts = await page.evaluate("""() => [...document.querySelectorAll('.el-select-dropdown__item')]
            .filter(e => e.offsetParent !== null).map(e => e.textContent)""")
        check("下拉含第二模板", any("测试电机材料清单" in o for o in opts), opts)
        await page.evaluate("""(label) => {
            const items = [...document.querySelectorAll('.el-select-dropdown__item')];
            const el = items.find(e => e.offsetParent !== null && e.textContent.includes(label));
            if (el) el.click();
        }""", "测试电机材料清单")
        await page.wait_for_timeout(500)
        await page.set_input_files('.el-dialog:visible input[type="file"][accept*="image"]', {
            "name": "drawing.png", "mimeType": "image/png", "buffer": b"\x89PNG\r\n\x1a\n"})
        await page.wait_for_timeout(2500)
        # 取消图纸核对弹窗
        await page.evaluate("""() => {
            const dlgs = [...document.querySelectorAll('.el-dialog')].filter(d => d.offsetParent !== null);
            const dlg = dlgs[dlgs.length - 1];
            const btn = [...(dlg?.querySelectorAll('button') || [])].find(b => b.textContent.includes('取消'));
            if (btn) btn.click();
        }""")
        await page.wait_for_timeout(600)
        await page.evaluate("""() => {
            const dlg = [...document.querySelectorAll('.el-dialog')].find(d => d.offsetParent !== null && d.textContent.includes('自动生成'));
            const btn = [...(dlg?.querySelectorAll('button') || [])].find(b => b.textContent.includes('生成并编辑'));
            if (btn) btn.click();
        }""")
        await page.wait_for_timeout(1500)
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
            return { found: true, rows, text: dlg.innerText.slice(0, 200) };
        }""")
        check("草稿弹窗出现", draft.get("found"), str(draft.get("text", ""))[:80])
        names_in_draft = [r[3] for r in draft.get("rows", []) if r[3]]
        check("草稿含21种", len(names_in_draft) == 21, f"n={len(names_in_draft)}")
        cat_cnt = {}
        for r in draft.get("rows", []):
            if r[3]: cat_cnt[r[1]] = cat_cnt.get(r[1], 0) + 1
        check("分组4/9/8", cat_cnt == {"半成品": 4, "标准件": 9, "辅材": 8}, cat_cnt)
        # 保存
        await page.evaluate("""() => {
            const dlg = [...document.querySelectorAll('.el-dialog')].find(d => d.offsetParent !== null && d.textContent.includes('核对并编辑'));
            const btn = [...(dlg?.querySelectorAll('button') || [])].find(b => b.textContent.includes('保存'));
            if (btn) btn.click();
        }""")
        await page.wait_for_timeout(2500)
        await browser.close()

    # 2. 取最新 BOM → 导出 → 验证第二模板落位
    st, body = api("GET", "/bom-lists", token)
    lst2 = json.loads(body)
    items = lst2 if isinstance(lst2, list) else (lst2.get("items") or [])
    new_id = items[0]["id"]
    st, raw = api("GET", f"/bom-lists/{new_id}/export-xlsx", token)
    check("导出200", st == 200, f"size={len(raw)}")
    with open(OUT, "wb") as f:
        f.write(raw)
    import xlrd
    ewb = xlrd.open_workbook(OUT, formatting_info=True)
    esh = ewb.sheet_by_index(0)
    check("标题=测试电机材料清单", str(esh.cell_value(0, 0)).strip() == "测试电机材料清单",
          str(esh.cell_value(0, 0)).strip()[:20])
    check("表头R3=物料名称", str(esh.cell_value(3, 2)).strip() == "物料名称")
    bp_n = sum(1 for r in range(5, 9) if str(esh.cell_value(r, 2)).strip())
    check("半成品R5-8四行", bp_n == 4, f"n={bp_n}")
    mz = all(not str(esh.cell_value(r, 2)).strip() for r in range(10, 23))
    check("主材R10-22空白", mz)
    std_n = sum(1 for r in range(24, 33) if str(esh.cell_value(r, 2)).strip())
    check("标准件R24-32九行", std_n == 9, f"n={std_n}")
    aux_n = sum(1 for r in range(34, 42) if str(esh.cell_value(r, 2)).strip())
    check("辅材R34-41八行", aux_n == 8, f"n={aux_n}")
    seqs = [str(esh.cell_value(r, 0)).strip() for r in [*range(5, 9), *range(24, 33), *range(34, 42)]]
    seqs = [s for s in seqs if s]
    check("序号1..21连续", [str(i) for i in range(1, 22)] == seqs, f"共{len(seqs)}个")
    check("总装图图号(2,3)已填", str(esh.cell_value(2, 3)).strip().startswith("ZN-"),
          str(esh.cell_value(2, 3)).strip()[:16])
    check("产品名称/规格标签(1,2)保留", str(esh.cell_value(1, 2)).strip() == "产品名称/规格",
          str(esh.cell_value(1, 2)).strip()[:12])
    check("R42注释行保留", "注" in str(esh.cell_value(42, 0)).strip())

    # 3. 删除第二模板 → 同一BOM导出回退默认模板
    st, body = api("DELETE", f"/bom-lists/internal-templates/{tpl2}", token)
    check("删除模板", st == 200, body[:80])
    st, raw = api("GET", f"/bom-lists/{new_id}/export-xlsx", token)
    with open(OUT_FB, "wb") as f:
        f.write(raw)
    fwb = xlrd.open_workbook(OUT_FB, formatting_info=True)
    fsh = fwb.sheet_by_index(0)
    check("回退标题=默认模板", "材料清单" in str(fsh.cell_value(0, 0)).strip() and "测试电机" not in str(fsh.cell_value(0, 0)).strip(),
          str(fsh.cell_value(0, 0)).strip()[:24])
    fb_bp = sum(1 for r in range(11, 15) if str(fsh.cell_value(r, 2)).strip())
    check("回退半成品R11-14", fb_bp == 4, f"n={fb_bp}")
    fb_std = sum(1 for r in range(31, 40) if str(fsh.cell_value(r, 2)).strip())
    check("回退标准件R31-39", fb_std == 9, f"n={fb_std}")

    # 清理测试 BOM
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
