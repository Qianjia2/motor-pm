"""上传即预览回归:选完附件(保存前)可立即预览 xlsx/pdf,不落盘。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5002"
ok = True
results = []

def check(name, cond, detail=""):
    global ok
    results.append((name, cond, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond: ok = False

def login(page):
    page.goto(BASE + "/login")
    page.wait_for_load_state("networkidle")
    page.fill("input[placeholder*='用户名'], input[placeholder*='账号'], .el-input__inner >> nth=0", "admin", timeout=8000)
    page.fill("input[type=password]", "admin123")
    page.keyboard.press("Enter")
    page.wait_for_timeout(2500)

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1600, "height": 950})
    page = ctx.new_page()
    errors = []
    bad = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("response", lambda r: bad.append(r.url) if r.status >= 400 else None)

    pdf_responses = []
    page.on("response", lambda r: pdf_responses.append(r.status) if "preview-attachment" in r.url else None)

    login(page)
    check("登录成功", "/login" not in page.url, page.url)
    page.goto(BASE + "/projects/2?tab=changes")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    check("变更 Tab 加载", page.locator("button", has_text="新建变更").first.is_visible(), "")

    # 点「新建变更」打开编辑弹窗
    page.locator("button", has_text="新建变更").first.click()
    page.wait_for_timeout(800)
    dialog = page.locator(".el-dialog:visible").last
    check("新建弹窗打开", dialog.is_visible(), "")

    # 选择附件(不保存)
    tmp = r"C:\Users\qianjia\AppData\Local\Temp\uiprev_test.xlsx"
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "自查表"
    ws.append(["编号", "变更内容"]); ws.append(["UIP-1", "绕组方案自查"])
    wb.save(tmp)

    # el-upload 内部 input[type=file] 直接 set_input_files
    page.locator(".el-dialog:visible input[type=file]").first.set_input_files(tmp)
    page.wait_for_timeout(800)
    check("显示已选择文件名", page.locator(".el-dialog:visible").last.locator("text=已选择").is_visible(), "")

    # 点「预览」→ LibreOffice 转真 PDF,blob 原生渲染
    pv = page.locator(".el-dialog:visible").last.locator("a", has_text="预览").first
    check("预览按钮出现", pv.is_visible(), "")
    pv.click()
    page.wait_for_timeout(3000)
    dlg = page.locator(".el-dialog:visible").last
    check("预览弹窗打开", dlg.locator("text=附件预览").is_visible(), "")
    src = dlg.locator("iframe").first.get_attribute("src") or ""
    srcdoc = dlg.locator("iframe").first.get_attribute("srcdoc") or ""
    check("office 预览为 PDF blob(原排版)", src.startswith("blob:") and not srcdoc, src[:60] or srcdoc[:60])
    page.keyboard.press("Escape")
    page.wait_for_timeout(600)
    check("关闭预览弹窗", not page.locator(".el-dialog:visible").last.locator("text=附件预览").is_visible(), "")

    # PDF 本地 objectURL 预览
    tmp_pdf = r"C:\Users\qianjia\AppData\Local\Temp\uiprev_test.pdf"
    open(tmp_pdf, "wb").write(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")
    page.locator(".el-dialog:visible input[type=file]").first.set_input_files(tmp_pdf)
    page.wait_for_timeout(600)
    pv2 = page.locator(".el-dialog:visible").last.locator("a", has_text="预览").first
    pv2.click()
    page.wait_for_timeout(800)
    dlg2 = page.locator(".el-dialog:visible").last
    src = dlg2.locator("iframe").first.get_attribute("src") or ""
    check("pdf 用 blob objectURL", src.startswith("blob:"), src[:60])
    page.keyboard.press("Escape")
    page.wait_for_timeout(600)
    page.keyboard.press("Escape")  # 关闭新建弹窗
    page.wait_for_timeout(400)

    # 预览接口全部 200
    check("预览接口 200", all(s == 200 for s in pdf_responses), str(pdf_responses))
    # 无前端 JS 报错
    check("无 pageerror", len(errors) == 0, str(errors[:3]))

    print("BAD(>=400):", bad if bad else "无")
    print("ALL PASS" if ok else "HAS FAILURES")
    sys.exit(0 if ok else 1)
