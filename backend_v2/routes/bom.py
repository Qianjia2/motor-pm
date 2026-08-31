"""BOM Management — Product BOM & Material Archive."""
import json, os, csv, io, copy, uuid, logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from backend_v2.database import get_db, SessionLocal
from backend_v2.auth import get_current_user
from backend_v2.storage import safe_load, safe_save as _safe_save

router = APIRouter(prefix="/api/bom", tags=["bom"])
BOM_LISTS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bom_lists.json")

def _load():
    return safe_load(BOM_LISTS_FILE, [])
def _save(items):
    _safe_save(BOM_LISTS_FILE, items)

# ── BOM Lists (Tab 1 - product BOM management) ──

def _sync_product_fields(x, data):
    """Write product_name/product_model to top level + meta so both list and detail views see them."""
    for k, mk in (("product_name", "product_name"), ("product_model", "product_model")):
        if k in data:
            x[k] = data[k]
            x.setdefault("meta", {})[mk] = data[k] or ""

@router.get("/lists")
def list_bom_lists(category: str = Query(None), _user=Depends(get_current_user)):
    items = _load()
    if category: items = [x for x in items if x.get("bom_category") == category]
    for x in items:
        m = x.get("meta") or {}
        x.setdefault("product_name", m.get("product_name", ""))
        x.setdefault("product_model", m.get("product_model", ""))
    return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)

@router.get("/lists/{lid}")
def get_bom_list(lid: int, _user=Depends(get_current_user)):
    for x in _load():
        if x.get("id") == lid:
            m = x.get("meta") or {}
            x.setdefault("product_name", m.get("product_name", ""))
            x.setdefault("product_model", m.get("product_model", ""))
            return x
    raise HTTPException(404)

@router.post("/lists")
def create_bom_list(data: dict, _user=Depends(get_current_user)):
    items = _load(); new_id = max([x.get("id",0) for x in items], default=0) + 1
    now = datetime.utcnow().isoformat()
    item = {"id": new_id, "name": data.get("name",""), "project_name": data.get("project_name",""),
            "status": data.get("status","有效"), "headers": data.get("headers",[]),
            "items": data.get("items",[]), "source_file": data.get("source_file",""),
            "meta": data.get("meta",{}), "item_count": len(data.get("items",[])),
            "bom_category": data.get("bom_category",""), "created_at": now, "updated_at": now}
    _sync_product_fields(item, data)
    items.append(item); _save(items); return item

@router.put("/lists/{lid}")
def update_bom_list(lid: int, data: dict, _user=Depends(get_current_user)):
    items = _load()
    for x in items:
        if x.get("id") == lid:
            for k in ("name","project_name","status","headers","items","meta","bom_category","notes","source_file"):
                if k in data: x[k] = data[k]
            _sync_product_fields(x, data)
            x["item_count"] = len(x.get("items",[])); x["updated_at"] = datetime.utcnow().isoformat()
            _save(items); return x
    raise HTTPException(404)

@router.delete("/lists/{lid}")
def delete_bom_list(lid: int, _user=Depends(get_current_user)):
    _save([x for x in _load() if x.get("id") != lid]); return {"ok": True}

@router.post("/lists/import")
async def import_bom_file(file: UploadFile = File(...), _user=Depends(get_current_user)):
    """Import BOM from Excel/CSV file."""
    content = await file.read(); fname = file.filename or "bom.xlsx"
    ext = fname.rsplit(".",1)[-1].lower()
    headers, rows = [], []
    try:
        if ext in ("xlsx","xls"):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            ws = wb.active
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                vals = [str(c) if c is not None else "" for c in row]
                if i == 0: headers = vals
                else: rows.append(vals)
        elif ext == "csv":
            reader = csv.reader(io.StringIO(content.decode("utf-8-sig")))
            for i, row in enumerate(reader):
                if i == 0: headers = row
                else: rows.append(row)
        else:
            raise HTTPException(400, detail=f"不支持格式: {ext}")
    except Exception as e:
        raise HTTPException(400, detail=f"解析失败: {str(e)[:100]}")

    items = _load(); new_id = max([x.get("id",0) for x in items], default=0) + 1
    item = {"id": new_id, "name": fname, "headers": headers, "items": rows,
            "status": "有效", "source_file": fname, "item_count": len(rows),
            "created_at": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat()}
    items.append(item); _save(items); return item

@router.post("/lists/compare")
def compare_bom(data: dict, _user=Depends(get_current_user)):
    """Compare two BOM lists."""
    items = _load()
    a = next((x for x in items if x.get("id") == data.get("id_a")), None)
    b = next((x for x in items if x.get("id") == data.get("id_b")), None)
    if not a or not b: raise HTTPException(404)
    ha, hb = a.get("headers",[]), b.get("headers",[])
    da, db = a.get("items",[]), b.get("items",[])
    # Find common, only-A, only-B, changed
    common, only_a, only_b, changed = 0, [], [], []
    for ra in da:
        found = False
        for rb in db:
            if ra[:3] == rb[:3]: found = True; break
        if found: common += 1
        else: only_a.append(ra)
    for rb in db:
        found = False
        for ra in da:
            if rb[:3] == ra[:3]: found = True; break
        if not found: only_b.append(rb)
    return {"name_a": a.get("name"), "name_b": b.get("name"),
            "count_a": len(da), "count_b": len(db), "common": common,
            "only_in_a": only_a, "only_in_b": only_b, "headers_a": ha, "headers_b": hb}

@router.put("/lists/batch/associate-project")
def batch_associate(data: dict, _user=Depends(get_current_user)):
    items = _load(); ids = set(data.get("ids",[])); pid = data.get("project_id")
    for x in items:
        if x.get("id") in ids: x["project_id"] = pid; x["updated_at"] = datetime.utcnow().isoformat()
    _save(items); return {"ok": True}

@router.get("/lists/template")
def get_bom_template(cat: str = Query("电机类"), _user=Depends(get_current_user)):
    """Download BOM Excel template."""
    from fastapi.responses import StreamingResponse
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = f"BOM-{cat}"
    # Info rows
    info = [["产品型号",""],["版本号",""],["发布日期",""],["设计人员",""],["审核人员",""],["批准人员",""],["项目名称",""],["客户名称",""],["备注",""],[""]]
    for r in info: ws.append(r)
    ws.append([])
    # Headers
    hdr_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    hdr_font = Font(color="FFFFFF", bold=True, size=11)
    headers = ["序号","物料编码","物料名称","规格型号","元件位置","封装","品牌","单位","数量","供应商","参考单价","备注"]
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=len(info)+2, column=i, value=h)
        c.fill = hdr_fill; c.font = hdr_font
    # Sample data
    samples = {
        "电机类": [["1","MTR-001","定子铁芯","DW310-0.5","M1","","","个","1","供应商A","120",""],
                   ["2","MTR-002","永磁体","N42SH","M2","","","片","8","供应商B","45",""],
                   ["3","MTR-003","旋转变压器","磁阻式","M3","","","个","1","供应商C","280",""]],
        "电控类": [["1","CTL-001","IGBT模块","1200V/100A","U1","Module","Infineon","个","6","供应商A","280",""],
                   ["2","CTL-002","驱动芯片","IR2110S","U2","SOP-8","TI","个","3","供应商B","15",""]],
        "其他": [["1","OTH-001","接插件套件","JST-XH","CN1","","","套","2","供应商A","8",""]]
    }
    for row in samples.get(cat, samples["电机类"]): ws.append(row)
    for col in range(1,13): ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 14
    ws.freeze_panes = ws.cell(row=len(info)+3, column=1)
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=BOM模板-{cat}.xlsx"})

# ── Material Archive (Tab 2) ──
MATERIAL_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bom_materials.json")
def _load_mat():
    return safe_load(MATERIAL_FILE, [])
def _save_mat(items):
    _safe_save(MATERIAL_FILE, items)

@router.get("/materials/template")
def download_materials_template():
    """Download Excel template for material archive import."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "研发物料档案"

    # Header style
    header_font = Font(name="微软雅黑", bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="409EFF", end_color="409EFF", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin")
    )

    headers = ["类别", "物料编码", "物料名称", "规格型号", "单位", "数量", "供应商", "供应商料号", "参考单价", "备注"]
    col_widths = [14, 20, 28, 28, 8, 8, 22, 22, 12, 22]

    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = header_font; cell.fill = header_fill
        cell.alignment = header_align; cell.border = thin_border
        ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = w

    # Example rows
    examples = [
        ["电机类物料", "MT-001", "永磁体", "N38SH 40x20x5mm", "个", "16", "宁波韵升", "YS-N38SH-40205", "12.50", ""],
        ["电机类物料", "MT-002", "定子铁芯", "SK-210-70 硅钢片", "个", "1", "宝钢", "", "180.00", "按图纸定制"],
        ["电控类物料", "CT-001", "IGBT模块", "FS100R12KT4G", "个", "6", "Infineon", "FS100R12KT4G", "85.00", ""],
        ["电控类物料", "CT-002", "电解电容", "470uF/450V", "个", "3", "Nippon Chemi-Con", "EKMQ451VSN471MA40S", "22.00", "D40x40mm"],
        ["其他物料", "OT-001", "散热片", "AL6061 120x80x40mm", "个", "1", "深圳华强", "", "15.00", "表面阳极氧化"],
    ]
    example_font = Font(name="微软雅黑", size=10)
    data_align = Alignment(vertical="center")

    for ri, row in enumerate(examples, 2):
        for ci, val in enumerate(row, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.font = example_font; cell.alignment = data_align; cell.border = thin_border

    # Freeze header
    ws.freeze_panes = "A2"
    # Auto-filter
    ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(len(headers))}{len(examples)+1}"

    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    from urllib.parse import quote
    filename = quote("物料档案导入模板.xlsx")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})

@router.get("/materials")
def list_materials(search: str = Query(None), category: str = Query(None), _user=Depends(get_current_user)):
    items = _load_mat()
    if search:
        q = search.lower()
        items = [x for x in items if q in (x.get("name","")+x.get("spec","")).lower()]
    if category: items = [x for x in items if x.get("category") == category]
    return sorted(items, key=lambda x: x.get("created_at",""), reverse=True)

@router.post("/materials")
def create_material(data: dict, _user=Depends(get_current_user)):
    items = _load_mat(); new_id = str(uuid.uuid4().hex[:8])
    item = {"id": new_id, "name": data.get("name",""), "spec": data.get("spec",""),
            "category": data.get("category",""), "supplier": data.get("supplier",""),
            "unit": data.get("unit","个"), "unit_price": data.get("unit_price"),
            "created_at": datetime.utcnow().isoformat()}
    items.append(item); _save_mat(items); return item

@router.put("/materials/{mid}")
def update_material(mid: str, data: dict, _user=Depends(get_current_user)):
    items = _load_mat()
    for x in items:
        if x.get("id") == mid:
            for k in ("name","spec","category","supplier","unit","unit_price"):
                if k in data: x[k] = data[k]
            _save_mat(items); return x
    raise HTTPException(404)

@router.post("/materials/batch-delete")
def batch_delete_materials(data: dict, _user=Depends(get_current_user)):
    """Batch delete materials by IDs."""
    ids = set(data.get("ids", []))
    if not ids: raise HTTPException(400, "ids不能为空")
    items = _load_mat()
    before = len(items)
    items = [x for x in items if x.get("id") not in ids]
    _save_mat(items)
    return {"deleted": before - len(items)}

@router.delete("/materials/{mid}")
def delete_material(mid: str, _user=Depends(get_current_user)):
    _save_mat([x for x in _load_mat() if x.get("id") != mid]); return {"ok": True}

@router.post("/import")
async def import_materials(file: UploadFile = File(...), category: str = Form(""), _user=Depends(get_current_user)):
    """Import materials — auto-detects .xlsx / .xls / csv by file header bytes."""
    content = await file.read(); fname = file.filename or "materials"
    items = _load_mat(); count = 0

    # Strip prepended garbage bytes (WPS sometimes adds headers)
    zip_offset = content.find(b'PK\x03\x04', 0, 1024)
    ole_offset = content.find(b'\xd0\xcf\x11\xe0', 0, 1024)
    content = content
    if zip_offset > 0:
        content = content[zip_offset:]
    elif ole_offset > 0:
        content = content[ole_offset:]

    header = content[:4]
    rows_data = []
    errors = []

    if header[:2] == b'PK' or zip_offset > 0:
        parsed = False
        # pandas (handles more edge cases)
        try:
            import pandas as pd
            df = pd.read_excel(io.BytesIO(content), dtype=str, header=0)
            for _, row in df.iterrows():
                rows_data.append([str(v) if v and str(v) != 'nan' else '' for v in row.values])
            parsed = bool(rows_data)
        except Exception:
            pass
        # fallback to openpyxl
        if not parsed:
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
                ws = wb.active
                for row in ws.iter_rows(min_row=2, values_only=True):
                    rows_data.append([str(c) if c is not None else "" for c in row])
            except Exception as e:
                errors.append(f"xlsx: {str(e)[:80]}")

    # 2) Try .xls (OLE)
    if (not rows_data) and (header[:4] == b'\xd0\xcf\x11\xe0' or ole_offset > 0):
        try:
            import xlrd
            wb = xlrd.open_workbook(file_contents=content)
            ws = wb.sheet_by_index(0)
            for ri in range(1, ws.nrows):
                row_vals = []
                for ci in range(ws.ncols):
                    v = ws.cell_value(ri, ci)
                    row_vals.append(str(v) if v != '' else '')
                if any(row_vals):
                    rows_data.append(row_vals)
        except Exception as e:
            errors.append(f"xls: {str(e)[:80]}")

    # 3) WPS binary extraction — find CSV/TSV text embedded in binary
    if not rows_data and header[:4].hex() == '0000e58b':
        import re as _re
        # Extract all printable UTF-8/GBK substrings from binary
        for enc in ['utf-8', 'gbk']:
            try:
                text = content.decode(enc, errors='ignore')
                # Find lines that look like CSV data (comma or tab separated, with Chinese chars)
                lines = text.replace('\r\n','\n').replace('\r','\n').split('\n')
                csv_lines = []
                for line in lines:
                    line = line.strip()
                    if not line or len(line) < 5: continue
                    # Must have delimiters AND Chinese or ASCII text
                    has_delim = '\t' in line or ',' in line
                    has_content = any('一' <= c <= '鿿' for c in line) or any(c.isascii() and c.isalpha() for c in line)
                    if has_delim and has_content:
                        csv_lines.append(line)
                if len(csv_lines) >= 2:
                    text = '\n'.join(csv_lines)
                    break
            except: continue

        if text and len(text) > 20:
            delim = ',' if ',' in text.split('\n')[0] else '\t'
            reader = csv.reader(io.StringIO(text), delimiter=delim)
            headers_seen = False
            for row in reader:
                if not headers_seen:
                    headers_seen = True
                    continue
                vals = [c.strip() for c in row]
                if not any(v for v in vals): continue
                rows_data.append(vals)

    # 4) Universal text fallback — intelligent encoding detection
    if not rows_data:
        text = None
        # Detect if file has many null bytes (UTF-16 signature)
        null_count = sum(1 for b in content if b == 0)
        null_ratio = null_count / max(len(content), 1)
        is_likely_utf16 = null_ratio > 0.2  # > 20% null bytes = likely UTF-16

        # Order encodings based on file signature
        if is_likely_utf16:
            encodings = ["utf-16-le", "utf-16-be", "utf-16", "utf-8-sig", "utf-8", "gbk", "gb18030"]
        else:
            encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030", "utf-16-le", "utf-16-be", "utf-16", "big5", "latin-1"]

        for enc in encodings:
            try:
                candidate = content.decode(enc)
                # Score: prefer encodings that produce Chinese characters
                cjk_chars = sum(1 for c in candidate if '一' <= c <= '鿿' or '㐀' <= c <= '䶿')
                if cjk_chars > 0 or '\t' in candidate or '\n' in candidate:
                    text = candidate
                    break
            except: continue

        if not text:
            # Last resort: any encoding that works
            for enc in encodings:
                try: text = content.decode(enc); break
                except: continue
        if text:
            # Try to find tabular data in the text
            lines = text.replace('\r\n','\n').replace('\r','\n').split('\n')
            # Skip non-data lines (very short, or obvious non-table content)
            for line in lines:
                line = line.strip()
                if not line or len(line) < 2: continue
                # Try tab first, then comma, then multiple spaces
                if '\t' in line:
                    vals = [c.strip() for c in line.split('\t')]
                elif ',' in line and line.count(',') >= 1:
                    vals = [c.strip() for c in line.split(',')]
                else:
                    # Split by 2+ spaces
                    import re as _re
                    vals = [c.strip() for c in _re.split(r'\s{2,}', line)]
                if len(vals) >= 2 and any(v for v in vals):
                    rows_data.append(vals)
        if not text:
            # Absolute last resort: extract strings from binary
            import re as _re
            # Find all sequences of printable characters (like Unix `strings` command)
            strings = _re.findall(rb'[\x20-\x7e\x80-\xff]{4,}', content)
            text = '\n'.join(s.decode('latin-1', errors='replace') for s in strings)
            if text:
                # Try to find tabular structure
                lines = text.split('\n')
                text_lines = []
                for line in lines:
                    if '\t' in line or ',' in line:
                        text_lines.append(line)
                if text_lines:
                    text = '\n'.join(text_lines)
            if not text or len(text) < 10:
                errors.append(f"二进制文件无法解析(hex:{header[:4].hex()})")

    if not rows_data:
        hexh = header.hex() if header else "empty"
        detail = f"无法解析文件(前4字节: {hexh})。"
        if errors: detail += " " + "; ".join(errors)
        if header[:2] == b'PK':
            detail += " 文件是ZIP格式但数据读取失败，请用Excel重新打开→另存为 .xlsx。"
        elif header[:4] == b'\xd0\xcf\x11\xe0':
            detail += " 文件是旧版xls（需用Excel打开后另存为 .xlsx）。"
        else:
            detail += " 请下载模板，填入数据后保存为 Excel (.xlsx) 再导入。"
        raise HTTPException(400, detail=detail)

    # Quality check: reject clearly garbage data
    if rows_data:
        sample_text = "".join(str(v) for v in rows_data[0])
        # Count non-printable / non-ASCII / non-CJK characters
        garbage_chars = sum(1 for c in sample_text if ord(c) < 32 and c not in '\t\n\r')
        total_chars = max(len(sample_text), 1)
        if garbage_chars / total_chars > 0.3:
            raise HTTPException(400, detail=f"文件内容无法识别(二进制乱码)。请确保: 1)下载模板填入数据 2)另存为 Microsoft Excel(.xlsx) 3)不要使用WPS默认格式")

    # Template columns: 类别(0), 物料编码(1), 物料名称(2), 规格型号(3), 单位(4), 数量(5), 供应商(6), 供应商料号(7), 参考单价(8), 备注(9)
    HEADER_KEYWORDS = ["物料名称", "物料编码", "规格型号", "类别"]
    for vals in rows_data:
        if not any(v for v in vals): continue
        # Skip header rows
        name_val = vals[2].strip() if len(vals) > 2 else ""
        if any(kw in name_val for kw in HEADER_KEYWORDS): continue
        items.append({"id": str(uuid.uuid4().hex[:8]),
                      "category": (vals[0].strip() if len(vals)>0 and vals[0] else category),
                      "code": (vals[1].strip() if len(vals)>1 else ""),
                      "name": (vals[2].strip() if len(vals)>2 else ""),
                      "spec": (vals[3].strip() if len(vals)>3 else ""),
                      "unit": (vals[4].strip() if len(vals)>4 else "个"),
                      "qty": (vals[5].strip() if len(vals)>5 else "1"),
                      "supplier": (vals[6].strip() if len(vals)>6 else ""),
                      "supplier_code": (vals[7].strip() if len(vals)>7 else ""),
                      "unit_price": (vals[8].strip() if len(vals)>8 else ""),
                      "notes": (vals[9].strip() if len(vals)>9 else ""),
                      "created_at": datetime.utcnow().isoformat()})
        count += 1

    _save_mat(items)
    sample = items[-1].get("name", "") if items else ""
    debug_row0 = rows_data[0] if rows_data else []
    null_ratio = sum(1 for b in content if b == 0) / max(len(content), 1)
    return {"count": count, "sample": sample, "hex": content[:4].hex(),
            "debug": {"first_row": debug_row0[:6], "null_ratio": f"{null_ratio:.1%}"}}

@router.post("/import-paste")
def import_materials_paste(data: dict, _user=Depends(get_current_user)):
    """Import materials from pasted text (auto-detect tab or comma delimiter)."""
    text = data.get("text",""); category = data.get("category","")
    lines = text.strip().split("\n")
    # Auto-detect delimiter from first line
    first = lines[0] if lines else ""
    delim = "\t" if "\t" in first else ("," if "," in first else "\t")
    items = _load_mat(); count = 0
    for line in lines:
        if delim == ",":
            reader = csv.reader(io.StringIO(line), delimiter=",")
            cols = next(reader, [])
        else:
            cols = line.split("\t")
        vals = [c.strip() for c in cols]
        if not any(v for v in vals): continue
        items.append({"id": str(uuid.uuid4().hex[:8]),
                      "category": (vals[0] if len(vals)>0 else category),
                      "code": (vals[1] if len(vals)>1 else ""),
                      "name": (vals[2] if len(vals)>2 else vals[0]),
                      "spec": (vals[3] if len(vals)>3 else ""),
                      "unit": (vals[4] if len(vals)>4 else "个"),
                      "qty": (vals[5] if len(vals)>5 else "1"),
                      "supplier": (vals[6] if len(vals)>6 else ""),
                      "supplier_code": (vals[7] if len(vals)>7 else ""),
                      "unit_price": (vals[8] if len(vals)>8 else ""),
                      "notes": (vals[9] if len(vals)>9 else ""),
                      "created_at": datetime.utcnow().isoformat()})
        count += 1
    _save_mat(items)
    sample = items[-1].get("name", "") if items else ""
    return {"count": count, "sample": sample}

@router.get("/projects")
def get_projects(_user=Depends(get_current_user)):
    """List projects for BOM association."""
    from backend_v2.models import Project
    from backend_v2.database import SessionLocal
    s = SessionLocal()
    try:
        projs = s.query(Project).filter(Project.is_active == True).all()
        return [{"id": p.id, "name": p.name} for p in projs]
    finally: s.close()

@router.post("/generate")
def generate_bom(data: dict, _user=Depends(get_current_user)):
    """Generate BOM from predefined template.

    preview=true 只返回模板内容不落库，由前端在可编辑表格中核对修改后再保存，
    因为每个产品的物料清单并不固定，不能直接按模板落库。
    """
    template = data.get("template","standard_motor"); pid = data.get("project_id")
    tpl_id = None
    headers = ["序号","物料编码","物料名称","规格型号","元件位置","封装","品牌","单位","数量","供应商","参考单价","备注"]
    templates = {
        "standard_motor": ("电机类BOM", [["1","","定子铁芯","","","","","个","1","","",""],["2","","永磁体","N42SH","","","","片","8","","",""],["3","","绕组","","","","","套","1","","",""],["4","","转轴","40Cr","","","","根","1","","",""],["5","","轴承","","","","","个","2","","",""],["6","","前端盖","ADC12","","","","个","1","","",""],["7","","后端盖","ADC12","","","","个","1","","",""],["8","","编码器","","","","","个","1","","",""],["9","","接线盒","","","","","个","1","","",""],["10","","风扇","","","","","个","1","","",""],["11","","紧固件套","","","","","套","1","","",""]]),
        "standard_control": ("电控类BOM", [["1","","IGBT模块","1200V/100A","","Module","","个","6","","",""],["2","","驱动IC","IR2110","","SOP-8","","个","3","","",""],["3","","MCU","TMS320","","QFP","","个","1","","",""],["4","","电流传感器","","","","","个","3","","",""],["5","","DC-Link电容","","","","","个","2","","",""],["6","","PCB板","4层","","","","","块","1","","",""],["7","","散热器","","","","","个","1","","",""],["8","","接插件","","","","","套","1","","",""],["9","","保险丝","","","","","个","2","","",""]]),
        "standard_other": ("其他类BOM", [["1","","接插件套件","","","","","套","1","","",""],["2","","散热器","","","","","个","1","","",""],["3","","紧固件套装","","","","","套","1","","",""],["4","","绝缘材料","","","","","套","1","","",""],["5","","线束总成","","","","","套","1","","",""]])
    }
    if str(template).startswith("internal"):
        from backend_v2.routes.bom_lists import _load_internal_meta, build_internal_items, build_info_fields, INTERNAL_HEADERS
        tpl_id = data.get("template_id") or "default"
        meta = _load_internal_meta(tpl_id)
        if not meta:
            raise HTTPException(400, detail="内部模板不存在, 请先在「自动生成BOM」弹窗中上传公司模板")
        headers = INTERNAL_HEADERS
        rows = build_internal_items(meta, data.get("items"))
        member_name = _user.member.name if getattr(_user, "member", None) and _user.member.name else ""
        info = build_info_fields(meta, username=getattr(_user, "username", ""), member_name=member_name)
        cat_name = "内部模板BOM"
        category = "内部模板"
    else:
        cat_name, rows = templates.get(template, templates["standard_motor"])
        category = template.replace("standard_","")+"类"
    project_name = ""
    if pid:
        from backend_v2.models import Project
        from backend_v2.database import SessionLocal
        s = SessionLocal()
        try: p = s.query(Project).get(pid); project_name = p.name if p else ""
        finally: s.close()

    if data.get("preview"):
        return {"headers": headers, "items": rows,
                "bom_category": category,
                "info": info if str(template).startswith("internal") else [],
                "template_id": tpl_id,
                "name": f"{cat_name}-{datetime.utcnow().isoformat()[:16].replace('T','-')}"}

    items = _load(); new_id = max([x.get("id",0) for x in items], default=0) + 1
    now = datetime.utcnow().isoformat()
    item = {"id": new_id, "name": f"{cat_name}-{now[:16].replace('T','-')}",
            "project_name": project_name, "project_id": pid, "status": "有效",
            "headers": headers, "items": rows, "item_count": len(rows),
            "bom_category": category,
            "info": info if str(template).startswith("internal") else [],
            "meta": {"bom_category": category, **({"template_id": tpl_id} if tpl_id else {})},
            "created_at": now, "updated_at": now}
    items.append(item); _save(items); return item

# ── AI BOM from drawing (MULTIMODAL: vision + OCR fallback) ──
@router.post("/from-drawing")
async def bom_from_drawing(file: UploadFile = File(...), _user=Depends(get_current_user)):
    import base64 as _b64, json as _json, aiohttp, ssl as _ssl, re as _re

    content = await file.read(); fname = file.filename or "drawing"
    if len(content) < 100: raise HTTPException(400, detail="文件太小")
    ext = fname.rsplit(".",1)[-1].lower() if "." in fname else "png"
    mime = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","webp":"image/webp","bmp":"image/bmp"}.get(ext,"image/jpeg")
    if ext == "pdf":
        doc = None
        parsed = False
        parse_err = None
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            if doc.page_count < 1:
                raise HTTPException(400, detail="PDF没有可解析的页面")
            content = doc[0].get_pixmap(dpi=200).tobytes("png")
            mime = "image/png"
            parsed = True
        except HTTPException:
            raise
        except Exception as e:
            parse_err = e
            if "encrypt" in str(e).lower():
                raise HTTPException(400, detail="PDF已加密，请先取消密码保护后再上传")
            # 兜底1：内容实为图片(截图/预览图改名 .pdf) → 直接按图片识别
            for magic, m in ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
                             (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"),
                             (b"BM", "image/bmp"), (b"RIFF", "image/webp")):
                if content.startswith(magic):
                    mime = m
                    parsed = True
                    break
            # 兜底2：头部被微信/网盘等污染，定位真实 %PDF- 头截取后重试
            if not parsed:
                idx = content.find(b"%PDF-")
                if idx > 0:
                    try:
                        doc = fitz.open(stream=content[idx:], filetype="pdf")
                        if doc.page_count > 0:
                            content = doc[0].get_pixmap(dpi=200).tobytes("png")
                            mime = "image/png"
                            parsed = True
                    except Exception:
                        pass
        finally:
            if doc is not None:
                try: doc.close()
                except Exception: pass
        if not parsed:
            logging.getLogger("bom").exception("BOM图纸PDF解析失败: %s (%s) len=%d head=%s", fname, parse_err, len(content), content[:16].hex(), exc_info=parse_err)
            raise HTTPException(400, detail="PDF文件损坏或无法打开，请重新导出图纸后再上传")

    with open(os.path.join(os.path.dirname(__file__),"..","..","data","ai_config.json"),"r",encoding="utf-8") as f:
        api_key = _json.load(f).get("engines",{}).get("tongyi",{}).get("api_key","")
    if len(api_key) < 20: raise HTTPException(400, detail="API Key未配置")

    img_b64 = _b64.b64encode(content).decode(); answer = ""
    try:
        # Step 1: Vision analysis — list all parts exhaustively
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as s:
            prompt_v1 = """你是资深电机/电控设计工程师，正在审核一张设计图纸。请按区域仔细扫描这张图纸。

【第一步】逐区域列出图中每个零件：
- 从上到下、从左到右，按图纸区域逐一识别
- 每个零件标注：位号(如C1,R2,U3)、直观名称、封装类型、标注文字
- 同类零件（如多个相同电阻）必须逐一列出每个位号，不要合并

【第二步】分类汇总：
- 将识别到的零件按类型分组
- 对每组零件：统计精确数量、统一规格型号
- 使用标准物料命名

【第三步】物料类别判定：为每个物料判定类别 category，只能是以下三种之一：
- "成品"：外购的完整部件或可直接装配的总成（如整机、外购模块、已装配组件）
- "半成品"：需要公司内部加工后再装配的零件或组件（如定子铁芯、转子、绕组、机座、端盖、转轴、机加工件）
- "辅料"：生产消耗性/通用辅助材料（如漆包线、绝缘纸、绑扎带、焊锡、绝缘漆、密封胶、螺钉螺母等标准紧固件）

【输出格式】只返回JSON数组：
[{"seq":1,"category":"半成品","code":"","name":"物料名称","spec":"规格","position":"位号1,位号2","package":"封装","brand":"","unit":"个","qty":数量,"supplier":"","price":"","note":""}]

关键要求：
- 不要遗漏任何标注的零件
- 数量=该零件出现次数，必须准确
- 位号列出所有出现的位置
- name使用行业标准术语(如"片式多层陶瓷电容"简化为"电容")
- 无法辨认的标注填写"未知"而不是编造
- category 必须从"成品/半成品/辅料"三选一，拿不准的按"辅料"
- 电路原理图重点识别: IC芯片、电阻、电容、电感、二极管、三极管、MOSFET、连接器、晶振、变压器
- 结构图重点识别: 定子铁芯、永磁体、绕组线圈、转轴、轴承、端盖、机座、接线盒
- position(位号) 只在图纸中有明确位号/图号标注时填写(如原理图 C1/R2/U3, 或图号栏里的编号); 机械结构图通常没有位号, 此时 position 一律填空字符串 "", 严禁编造数字"""
            async with s.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                json={"model":"qwen-vl-max","messages":[{"role":"user","content":[
                    {"type":"image_url","image_url":{"url":f"data:{mime};base64,{img_b64}"}},
                    {"type":"text","text":prompt_v1}
                ]}],"max_tokens":3000,"temperature":0.1},
                headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"}, ssl=_ssl.create_default_context()
            ) as resp:
                answer = (await resp.json())["choices"][0]["message"]["content"] if resp.status==200 else f"[Vision {resp.status}]"

        # OCR fallback with improved prompt
        if not answer or answer.startswith("[Vision"):
            ocr_text = ""
            try:
                import easyocr, numpy as np, io as _io
                from PIL import Image as _PILImage
                img = _PILImage.open(_io.BytesIO(content))
                if img.mode in ('RGBA','LA','P'): img = img.convert('RGB')
                reader = easyocr.Reader(['ch_sim','en'], gpu=False, verbose=False)
                ocr_text = " ".join(reader.readtext(np.array(img), detail=0))[:3000]
            except: pass
            if ocr_text.strip():
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s2:
                    async with s2.post(
                        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                        json={"model":"qwen-turbo","messages":[{"role":"user","content":f"""OCR识别到的图纸文字:
{ocr_text}

请根据这些文字识别零件并生成BOM清单。
- 将相似零件合并，统计数量
- 使用标准物料命名
- 每个物料判定类别 category，只能三选一："成品"=外购完整部件/总成，"半成品"=需公司内部加工的零件或组件(定子铁芯、转子、绕组、机座等)，"辅料"=生产消耗性辅助材料(漆包线、绝缘纸、焊锡、绑扎带、紧固件等)，拿不准的按"辅料"
- position(位号) 只在文字中明确出现位号/图号时才填, 纯数字(数量/尺寸/序号)不算位号, 没有就填空字符串 ""
- 返回JSON数组，每项格式:
{{"seq":序号,"category":"半成品","code":"","name":"物料名称","spec":"规格型号","position":"位号","package":"封装","brand":"","unit":"个","qty":数量,"supplier":"","price":"","note":""}}
只返回JSON数组"""}],"max_tokens":2000,"temperature":0.1},
                        headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"}, ssl=_ssl.create_default_context()
                    ) as r2:
                        answer = (await r2.json())["choices"][0]["message"]["content"] if r2.status==200 else f"[OCR {r2.status}]"
            else:
                answer = "[]"

        # Parse JSON
        items = []; txt = answer.replace('\n',' ').replace('\r','')
        for m in _re.finditer(r'\[\s*\{.*?\}\s*\]', txt, _re.DOTALL):
            try: items = _json.loads(m.group()); break
            except: continue
        # 后置校验: position(位号/零件图号) 若是纯数字/序号类文本(数量、尺寸、幻觉数字), 一律置空
        _POS_DROP = _re.compile(r'^[0-9\s,，、;；./\-()（）×*~]*$')
        for it in items:
            if isinstance(it, dict) and str(it.get("position", "") or "").strip():
                p = str(it["position"]).strip()
                if _POS_DROP.fullmatch(p):
                    it["position"] = ""
        return {"items": items, "raw_answer": answer[:800]}
    except Exception as e:
        # 不向客户端返回堆栈（信息泄露），完整堆栈走日志
        import logging
        logging.getLogger("bom").exception("识别物料解析失败")
        return {"items": [], "error": str(e)[:100], "raw_answer": answer[:500]}


# ── Convert hardware tool BOM → template format ──
@router.post("/convert-tool-bom")
async def convert_tool_bom(file: UploadFile = File(...), _user=Depends(get_current_user)):
    """Upload BOM from Altium/Cadence/KiCad → maps to 12-column template."""
    import json as _json, re as _re

    content = await file.read(); fname = file.filename or "bom"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "csv"

    headers, rows = [], []
    try:
        if ext in ("xlsx", "xls"):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True); ws = wb.active
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                vals = [str(c) if c is not None else "" for c in row]
                if i == 0: headers = [h.strip() for h in vals]
                else: rows.append(vals)
        elif ext == "csv":
            text = None
            for enc in ["utf-8-sig", "utf-16", "utf-16-le", "gbk", "utf-8"]:
                try: text = content.decode(enc); break
                except: continue
            if not text:
                raise HTTPException(400, detail="无法识别CSV编码，请另存为UTF-8格式")
            # Auto-detect delimiter: try tab if comma gives only 1 column
            delimiter = ","
            first_line = text.split("\n")[0] if "\n" in text else text
            if "\t" in first_line:
                delimiter = "\t"
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            for i, row in enumerate(reader):
                if i == 0: headers = [h.strip() for h in row]
                else: rows.append(row)
        else:
            raise HTTPException(400, detail=f"不支持格式: {ext}")
    except Exception as e:
        raise HTTPException(400, detail=f"解析失败: {str(e)[:100]}")

    if not headers or not rows:
        raise HTTPException(400, detail="文件为空")

    # Hardcoded column mapping — covers all common HW tool exports
    hw_map = {
        # Altium
        "designator": "position", "comment": "spec", "footprint": "package",
        "quantity": "qty", "manufacturer": "brand", "supplier": "supplier",
        "description": "name", "manufacturer part": "code", "supplier part": "code",
        "libref": "name", "part number": "code", "value": "spec",
        "no": "seq", "no.": "seq", "item": "seq", "序号": "seq",
        "qty": "qty", "数量": "qty",
        # Chinese
        "位号": "position", "元件位置": "position",
        "值": "spec", "规格型号": "spec", "规格": "spec",
        "封装": "package",
        "物料编码": "code", "物料名称": "name",
        "品牌": "brand", "厂商": "brand",
        "供应商": "supplier",
        "单位": "unit",
        "单价": "price", "参考单价": "price",
        "描述": "name", "名称": "name",
    }

    # Build column map from headers (only for columns that ACTUALLY exist)
    col_map = {}
    for h in headers:
        hl = h.strip().lower()
        if not hl: continue
        matched = hw_map.get(hl, "")
        if not matched:
            for kw, target in hw_map.items():
                if kw in hl:
                    matched = target
                    break
        if matched:
            col_map[hl] = matched

    # Convert all rows, skip empty rows
    tpl = ["seq","code","name","spec","position","package","brand","unit","qty","supplier","price","note"]
    items = []
    seq = 0
    for row in rows:
        # Skip empty rows
        if not row or all(not str(c).strip() for c in row):
            continue
        seq += 1
        item = {c: "" for c in tpl}
        item["seq"] = str(seq)
        for ci, h in enumerate(headers):
            field = col_map.get(h.strip().lower(), "")
            val = str(row[ci]).strip() if ci < len(row) and row[ci] is not None and str(row[ci]).strip() else ""
            if field and val:
                item[field] = val
        items.append(item)

    return {
        "items": items,
        "column_map": col_map,
        "raw_answer": f"硬编码映射，{len(rows)}行原始→{len(items)}行有效",
        "debug_headers": headers,
        "debug_first_rows": [list(r) for r in rows[:3]],
    }
