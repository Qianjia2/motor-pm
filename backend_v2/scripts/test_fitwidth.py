# -*- coding: utf-8 -*-
"""对比两种让宽表格单页显示的方案。"""
import os, subprocess, tempfile, shutil, time

SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_diag_orig.xlsx")
print("SRC exists:", os.path.exists(SRC))

def convert(src, outdir, fopt=None):
    cmd = [SOFFICE, "--headless", "--norestore"]
    if fopt:
        cmd += ["--convert-to", fopt]
    else:
        cmd += ["--convert-to", "pdf"]
    cmd += ["--outdir", outdir, src]
    for attempt in range(4):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=120)
        except PermissionError:
            time.sleep(3); continue
        if r.returncode == 0:
            break
        time.sleep(3)
    pdfs = [f for f in os.listdir(outdir) if f.endswith(".pdf")]
    return r.returncode, pdfs

def pages(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    rd = PdfReader(path)
    return [ (pg.extract_text() or "").strip() for pg in rd.pages ]

# ── 方案 A:导出过滤器 ScaleToPagesX=1 ──
tmp = tempfile.mkdtemp(prefix="lo_a_")
try:
    opts = '{"ScaleToPagesX":{"type":"long","value":1},"ScaleToPagesY":{"type":"long","value":0}}'
    rc, pdfs = convert(SRC, tmp, f"pdf:calc_pdf_Export:{opts}")
    print("A(export filter) rc:", rc, "pdfs:", pdfs)
    if pdfs:
        for i, t in enumerate(pages(os.path.join(tmp, pdfs[0])), 1):
            print(f"  A p{i} ({len(t)}): {t[:90].replace(chr(10),' | ')}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ── 方案 B:openpyxl 预处理 fitToWidth=1 ──
tmp2 = tempfile.mkdtemp(prefix="lo_b_")
try:
    import openpyxl
    from openpyxl.worksheet.properties import PageSetupProperties
    wb = openpyxl.load_workbook(SRC)
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    fixed = os.path.join(tmp2, "fixed.xlsx")
    wb.save(fixed)
    rc, pdfs = convert(fixed, tmp2)
    print("B(openpyxl preprocess) rc:", rc, "pdfs:", pdfs)
    if pdfs:
        for i, t in enumerate(pages(os.path.join(tmp2, pdfs[0])), 1):
            print(f"  B p{i} ({len(t)}): {t[:90].replace(chr(10),' | ')}")
finally:
    shutil.rmtree(tmp2, ignore_errors=True)
