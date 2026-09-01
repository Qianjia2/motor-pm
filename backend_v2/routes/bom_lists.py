"""Product BOM Lists — complete BOM documents (not individual items)."""
import json, os, csv, io, re as _re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Body
from fastapi.responses import FileResponse
from backend_v2.database import SessionLocal
from backend_v2.auth import get_current_user, require_admin
from backend_v2.config import settings
from backend_v2.storage import safe_load, safe_save, atomic_write

router = APIRouter(prefix="/api/bom-lists", tags=["bom-lists"])

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bom_lists.json")

# ── 内部 BOM 模板（公司模板, 支持多套: data/internal_templates/<id>.xls + <id>.json） ──
_INTERNAL_TPL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "internal_templates")
# 旧单模板文件路径（迁移到多模板目录后作为 default 的兜底来源）
INTERNAL_TPL_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bom_internal_template.xls")
INTERNAL_TPL_META = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bom_internal_template_meta.json")
INTERNAL_HEADERS = ["类别", "序号", "物料编码", "物料名称", "零件图号", "材料、牌号、规格、技术条件", "单位", "用量", "备注"]


def _ensure_internal_tpl_dir():
    """确保多模板目录存在; 首次调用时把旧单模板文件迁移为 default 模板(重新解析生成新结构 meta)。"""
    d = _INTERNAL_TPL_DIR
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
        if os.path.exists(INTERNAL_TPL_FILE):
            with open(INTERNAL_TPL_FILE, "rb") as f:
                tpl_bytes = f.read()
            with open(os.path.join(d, "default.xls"), "wb") as f:
                f.write(tpl_bytes)
            try:
                meta = _parse_internal_template(tpl_bytes, os.path.basename(INTERNAL_TPL_FILE))
                _save_internal_meta(meta, "default")
            except Exception:
                # 解析失败则直接沿用旧 meta
                if os.path.exists(INTERNAL_TPL_META):
                    with open(INTERNAL_TPL_META, "rb") as f:
                        data = f.read()
                    with open(os.path.join(d, "default.json"), "wb") as f:
                        f.write(data)
    return d


def _tpl_path(tpl_id="default"):
    p = os.path.join(_ensure_internal_tpl_dir(), f"{tpl_id}.xls")
    if not os.path.exists(p) and tpl_id == "default" and os.path.exists(INTERNAL_TPL_FILE):
        return INTERNAL_TPL_FILE
    return p


def _tpl_meta_path(tpl_id="default"):
    p = os.path.join(_ensure_internal_tpl_dir(), f"{tpl_id}.json")
    if not os.path.exists(p) and tpl_id == "default" and os.path.exists(INTERNAL_TPL_META):
        return INTERNAL_TPL_META
    return p


def _load_internal_meta(tpl_id="default"):
    try:
        with open(_tpl_meta_path(tpl_id), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_internal_meta(meta, tpl_id="default"):
    # 直接写多模板目录(不经 _tpl_meta_path 的旧文件回退, 避免 default 写回旧路径)
    d = _ensure_internal_tpl_dir()
    atomic_write(os.path.join(d, f"{tpl_id}.json"), meta)


def _gen_tpl_id():
    import time
    return f"t{int(time.time() * 1000)}"


def _list_internal_templates():
    """返回全部内部模板列表 [{id, name, filename, sheets, groups, is_default}]。"""
    out = []
    d = _ensure_internal_tpl_dir()
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        tpl_id = fn[:-5]
        meta = None
        try:
            with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue
        if not meta:
            continue
        out.append({
            "id": tpl_id,
            "name": (meta.get("title") or "").strip() or meta.get("filename") or tpl_id,
            "filename": meta.get("filename", ""),
            "sheets": meta.get("sheets", []),
            "groups": meta.get("groups", []),
            "is_default": tpl_id == "default",
        })
    return out


def _sheet_rows(ext, content):
    """读取 Excel 全部 sheet 为行数组(仅去末尾空行, 中间空行保留以维持行号)。"""
    if ext == "xls":
        import xlrd
        wb = xlrd.open_workbook(file_contents=content)
        out = []
        for sh in wb.sheets():
            rows = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
            while rows and not any(str(v).strip() != "" for v in rows[-1]):
                rows.pop()
            out.append({"name": sh.name, "rows": rows})
        return out
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    out = []
    for ws in wb.worksheets:
        rows = [[c.value for c in row] for row in ws.iter_rows()]
        while rows and not any(str(v).strip() != "" for v in rows[-1]):
            rows.pop()
        out.append({"name": ws.title, "rows": rows})
    return out


def _parse_internal_template(content: bytes, filename: str):
    """解析公司模板: 信息区字段、表头列映射、分组、半成品示例行。"""
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ("xls", "xlsx"):
        raise HTTPException(400, detail="内部模板仅支持 .xls / .xlsx 格式")
    sheets = _sheet_rows(ext, content)
    if not sheets:
        raise HTTPException(400, detail="模板文件无法读取, 请确认格式")

    def find_keyword(row, keywords):
        for kw in keywords:
            for c, v in enumerate(row):
                if isinstance(v, str) and kw in v.replace("\n", ""):
                    return c
        return None

    main = sheets[0]
    rows = main["rows"]
    # 合并单元格信息(用于值单元格推导)
    merged = []
    try:
        if ext == "xls":
            import xlrd
            _wb = xlrd.open_workbook(file_contents=content, formatting_info=True)
            merged = list(_wb.sheet_by_index(0).merged_cells)
        else:
            import openpyxl
            _wb2 = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            for _mr in _wb2.worksheets[0].merged_cells.ranges:
                merged.append((_mr.min_row - 1, _mr.max_row, _mr.min_col - 1, _mr.max_col))
    except Exception:
        merged = []
    # 表头行: 同时包含 序号 与 物料名称
    hdr_idx = None
    for r, row in enumerate(rows):
        c1 = find_keyword(row, ["序号"])
        c2 = find_keyword(row, ["物料名称"])
        if c1 is not None and c2 is not None:
            hdr_idx = r
            break
    if hdr_idx is None:
        raise HTTPException(400, detail="模板中未找到表头(需含 序号/物料名称 列)")
    hdr = rows[hdr_idx]
    next_row = rows[hdr_idx + 1] if hdr_idx + 1 < len(rows) else []
    col_map = {
        "code": find_keyword(hdr, ["物料编码"]),
        "name": find_keyword(hdr, ["物料名称"]),
        "part_no": find_keyword(hdr, ["零件图号"]),
        "spec": find_keyword(hdr, ["材料", "规格"]),
        "unit": find_keyword(next_row, ["单位"]) if find_keyword(next_row, ["单位"]) is not None else find_keyword(hdr, ["单位"]),
        "qty": find_keyword(next_row, ["用量", "数量"]) if find_keyword(next_row, ["用量", "数量"]) is not None else find_keyword(hdr, ["用量", "数量"]),
        "note": find_keyword(hdr, ["备注"]),
    }
    # 信息区: 表头行之前的标签行(第0列有值且非表头), 记录标签及所在行/列, 便于生成时回填表头
    info_fields = []
    notes = []
    title = ""
    for r in range(0, hdr_idx):
        row = rows[r]
        for c, v in enumerate(row):
            txt = str(v).strip() if v is not None else ""
            if not txt:
                continue
            if r == 0 and c == 0 and len(txt) >= 8 and any(kw in txt for kw in ("材料清单", "物料清单", "BOM", "清单")):
                title = txt  # 首行标题(公司材料清单), 按模板原样保留
                continue
            # 标签判定: 短文本含典型表头关键字, 或 8 字以内的中文短标签
            has_kw = any(kw in txt for kw in ("名称", "图号", "编号", "编码", "型号", "版本", "时间", "日期", "说明",
                                              "要求", "参数", "规格", "接口", "绕组", "客户", "条形码", "生产商",
                                              "制造商", "设计", "编制", "审批", "审核", "批准", "备注", "性能"))
            if (len(txt) <= 30 and has_kw) or (len(txt) <= 8 and any("一" <= ch <= "鿿" for ch in txt)):
                info_fields.append({"label": txt, "row": r, "col": c})
            elif len(txt) > 8:
                notes.append({"row": r, "col": c, "text": txt})  # 说明文字(如 R6 特殊要求说明后整行), 原样保留
    # 第二遍: label 右侧相邻单元格的预填值作为默认值(排除相邻标签与说明文字)
    known = {f["label"] for f in info_fields} | {n["text"] for n in notes}
    for f in info_fields:
        row = rows[f["row"]]
        dv = ""
        for dc in (f["col"] + 1, f["col"] + 2):
            if dc < len(row):
                t = str(row[dc]).strip() if row[dc] is not None else ""
                if t and t not in known:
                    dv = t
                    break
        f["default"] = dv
    # 值单元格推导: 优先标签下方空单元格, 否则标签右侧第一个 空/合并区左上角 单元格
    member = set()
    tops = {}
    for (rlo, rhi, clo, chi) in merged:
        tops[(rlo, clo)] = (rlo, rhi, clo, chi)
        for r in range(rlo, rhi):
            for c in range(clo, chi):
                if (r, c) != (rlo, clo):
                    member.add((r, c))
    def _cell_empty(r, c):
        if r < 0 or c < 0 or r >= len(rows) or c >= len(rows[r]):
            return True
        v = rows[r][c]
        return not (isinstance(v, str) and v.strip())
    for f in info_fields:
        r, c = f["row"], f["col"]
        if r + 1 < hdr_idx and _cell_empty(r + 1, c) and (r + 1, c) not in member:
            f["value_row"], f["value_col"] = r + 1, c
            continue
        span_end = c + 1
        if (r, c) in tops:
            span_end = tops[(r, c)][3]
        for j in range(span_end, len(rows[r])):
            if _cell_empty(r, j) or (r, j) in tops:
                f["value_row"], f["value_col"] = r, j
                break
    # 分组: 表头行之后第0列为 半成品/主材/标准件/辅材 的行(记录每组物料行数)
    groups = []
    for r in range(hdr_idx + 1, len(rows)):
        label = str(rows[r][0]).strip()
        if label in ("半成品", "主材", "标准件", "辅材"):
            groups.append({"name": label, "row": r})
    for i, g in enumerate(groups):
        nxt = groups[i + 1]["row"] if i + 1 < len(groups) else len(rows)
        if i + 1 >= len(groups):  # 末组后若紧邻注释行(注/说明), 不计入物料行
            while nxt - 1 > g["row"] and str(rows[nxt - 1][0]).strip().startswith(("注", "说明")):
                nxt -= 1
        g["rows"] = max(0, nxt - g["row"] - 1)
    # 半成品示例: 优先取子 sheet 中物料明细
    example_rows = []
    for sh in sheets[1:]:
        for r, row in enumerate(sh["rows"]):
            c1 = find_keyword(row, ["序号"])
            c2 = find_keyword(row, ["物料名称"])
            if c1 is not None and c2 is not None:
                nxt = sh["rows"][r + 1] if r + 1 < len(sh["rows"]) else []
                cm = {
                    "code": find_keyword(row, ["物料编码"]), "name": find_keyword(row, ["物料名称"]),
                    "part_no": find_keyword(row, ["零件图号"]), "spec": find_keyword(row, ["材料", "规格"]),
                    "unit": find_keyword(nxt, ["单位"]) if find_keyword(nxt, ["单位"]) is not None else find_keyword(row, ["单位"]),
                    "qty": find_keyword(nxt, ["用量", "数量"]) if find_keyword(nxt, ["用量", "数量"]) is not None else find_keyword(row, ["用量", "数量"]),
                    "note": find_keyword(row, ["备注"]),
                }
                for rr in sh["rows"][r + 1:]:
                    name = str(rr[cm["name"]]).strip() if cm["name"] is not None else ""
                    if not name or str(rr[0]).strip() in ("半成品", "主材", "标准件"):
                        continue
                    example_rows.append({
                        "code": str(rr[cm["code"]]).strip() if cm["code"] is not None else "",
                        "name": name,
                        "part_no": str(rr[cm["part_no"]]).strip() if cm["part_no"] is not None else "",
                        "spec": str(rr[cm["spec"]]).strip() if cm["spec"] is not None else "",
                        "unit": str(rr[cm["unit"]]).strip() if cm["unit"] is not None else "pcs",
                        "qty": str(rr[cm["qty"]]).strip() if cm["qty"] is not None else "1",
                        "note": str(rr[cm["note"]]).strip() if cm["note"] is not None else "",
                    })
                break
        if example_rows:
            break
    meta = {
        "filename": filename, "ext": ext, "sheets": [s["name"] for s in sheets],
        "main_sheet": main["name"], "info_fields": info_fields, "col_map": col_map,
        "groups": [g["name"] for g in groups],
        "group_rows": {g["name"]: g["rows"] for g in groups},
        "group_starts": {g["name"]: g["row"] + 1 for g in groups},  # 首行物料行号(标签行+1)
        "example_rows": example_rows, "title": title, "notes": notes,
    }
    return meta


_CAT_TO_GROUP = {"半成品": "半成品", "成品": "标准件", "辅料": "辅材"}

# 零件图号校验: 纯数字/序号类文本(数量、尺寸、幻觉数字)不是图号
_PN_DROP = _re.compile(r"^[0-9\s,，、;；./\-()（）×*~]*$")


def build_internal_items(meta, recognized=None):
    """按内部模板分组骨架生成清单行(9列): 优先填图纸识别物料(按类别归组),
    组容量溢出写入主材空位(主材无识别来源), 半成品无识别结果时保留模板示例行, 其余补空行。"""
    gr = meta.get("group_rows") or {}
    groups = meta.get("groups") or ["半成品", "主材", "标准件"]
    cap = {g: int(gr.get(g, 0) or 0) for g in groups}

    buckets = {g: [] for g in groups}
    for it in recognized or []:
        g = _CAT_TO_GROUP.get(str((it or {}).get("category", "") or "").strip(), "辅材")
        if g not in buckets:
            g = "辅材"
        if g not in buckets:
            continue
        buckets[g].append(it)

    def to_row(g, it):
        pn = str(it.get("position", "") or "").strip()
        if _PN_DROP.fullmatch(pn):  # 纯数字/序号类文本不是零件图号, 置空
            pn = ""
        return [g, "", str(it.get("code", "") or ""), str(it.get("name", "") or ""),
                pn, str(it.get("spec", "") or ""),
                str(it.get("unit", "") or "") or "pcs", str(it.get("qty", "") or "") or "1",
                str(it.get("note", "") or "")]

    rows, spare, m_start = [], [], None
    for g in groups:
        need = cap[g]
        items = buckets[g]
        if g != "主材" and len(items) > need:
            spare += items[need:]
            items = items[:need]
        filled = [to_row(g, it) for it in items]
        if g == "半成品" and not items:
            for ex in (meta.get("example_rows") or [])[:need]:
                filled.append([g, "", ex.get("code", ""), ex.get("name", ""), ex.get("part_no", ""),
                               ex.get("spec", ""), ex.get("unit", "pcs") or "pcs", ex.get("qty", "1") or "1", ex.get("note", "")])
        for _ in range(max(0, need - len(filled))):
            filled.append([g, "", "", "", "", "", "pcs", "1", ""])
        if g == "主材":
            m_start = len(rows)
        rows += filled
    # 组溢出的识别物料填入主材空位(主材行在识别结果中无来源, 最宽裕)
    if m_start is not None and spare:
        for i, it in enumerate(spare[: cap.get("主材", 0)]):
            rows[m_start + i] = to_row("主材", it)
    for i, it in enumerate(rows, 1):
        it[1] = str(i)
    return rows


def build_info_fields(meta, username="", member_name=""):
    """按模板表头区原始布局生成 info: 标题行 + 标准字段(生产商/设计/图号,模板缺失则补齐并自动填) + 模板字段(带行列位置) + 说明文字。
    生产商名称取自模板标题(公司名), 设计人员取当前用户, 编制时间取当天。"""
    import re
    out = []
    title = (meta or {}).get("title", "") or ""
    if title:
        out.append({"type": "title", "label": title, "row": 0, "col": 0, "value": title})
    company = ""
    m = re.search(r"([一-龥A-Za-z0-9]{2,}有限公司)", title)
    if m:
        company = m.group(1)
    else:
        for suf in ("材料清单", "物料清单", "BOM清单", "清单"):
            if title.endswith(suf):
                company = title[: -len(suf)]
                break
    designer = (member_name or "").strip() or (username or "").strip()
    today = datetime.now().strftime("%Y-%m-%d")
    # 标准四要素补齐: 模板缺失的生产商/设计人员 在标题下方独立成行(产品图号=模板总装图图号, 不再单列)
    all_lbl = " ".join(str(f.get("label", "")) for f in (meta or {}).get("info_fields") or [])
    std = []
    if "生产商" not in all_lbl and "制造商" not in all_lbl and "公司" not in all_lbl:
        std.append(("生产商名称", company))
    if "设计" not in all_lbl:
        std.append(("设计人员", designer))
    for lbl, val in std:
        out.append({"type": "std", "label": lbl, "row": 0, "col": -1, "value": val})
    # 自动编号: 总装图图号(产品图号) ZN-日期-流水, 条形码按模板规则(年2位+月2位+流水号4位)
    seq = len(_load()) + 1
    fig_no = f"ZN-{datetime.now().strftime('%Y%m%d')}-{seq:04d}"
    barcode = f"{datetime.now().strftime('%y%m')}{seq:04d}"
    seen = set()
    for f in (meta or {}).get("info_fields") or []:
        lbl = f.get("label") if isinstance(f, dict) else str(f)
        lbl = " ".join((lbl or "").split())
        if not lbl or lbl == "序号" or (f.get("row", 0), f.get("col", 0)) in seen:
            continue
        seen.add((f.get("row", 0), f.get("col", 0)))
        val = f.get("default", "") if isinstance(f, dict) else ""
        if any(kw in lbl for kw in ("时间", "日期")):
            val = today
        elif "总装图" in lbl:
            val = fig_no
        elif "条形码" in lbl:
            val = barcode
        elif "版本" in lbl and len(lbl) <= 6 and not val:
            val = "V1.0"
        vf = {"type": "field", "label": lbl,
              "row": f.get("row", 0), "col": f.get("col", 0), "value": val}
        if isinstance(f, dict) and f.get("value_row") is not None and f.get("value_col") is not None:
            vf["value_row"], vf["value_col"] = f["value_row"], f["value_col"]
        out.append(vf)
    for n in (meta or {}).get("notes") or []:
        txt = str(n.get("text", "")).strip()
        if txt:
            out.append({"type": "note", "label": txt,
                        "row": n.get("row", 0), "col": n.get("col", 0), "value": txt})
    return out


async def _read_template_upload(file: UploadFile):
    content = await file.read()
    if not content:
        raise HTTPException(400, detail="文件为空")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(400, detail="模板文件不能超过 20MB")
    meta = _parse_internal_template(content, file.filename or "template.xls")
    return content, meta


@router.get("/internal-templates")
def list_internal_templates(_user=Depends(get_current_user)):
    """列出全部内部模板。"""
    return {"templates": _list_internal_templates()}


@router.post("/internal-templates")
async def create_internal_template(file: UploadFile = File(...), name: str = Form(""),
                                   _user=Depends(require_admin)):
    """新增一套内部模板。"""
    content, meta = await _read_template_upload(file)
    tpl_id = _gen_tpl_id()
    if name and name.strip():
        meta["name"] = name.strip()
    with open(_tpl_path(tpl_id), "wb") as f:
        f.write(content)
    _save_internal_meta(meta, tpl_id)
    return {"ok": True, "id": tpl_id, "filename": file.filename, "sheets": meta["sheets"],
            "groups": meta["groups"], "example_count": len(meta["example_rows"])}


@router.post("/internal-template/{tpl_id}")
async def replace_internal_template(tpl_id: str, file: UploadFile = File(...),
                                    _user=Depends(require_admin)):
    """替换指定内部模板(重新解析)。"""
    if not _load_internal_meta(tpl_id):
        raise HTTPException(404, detail="模板不存在")
    content, meta = await _read_template_upload(file)
    with open(_tpl_path(tpl_id), "wb") as f:
        f.write(content)
    _save_internal_meta(meta, tpl_id)
    return {"ok": True, "id": tpl_id, "filename": file.filename, "sheets": meta["sheets"],
            "groups": meta["groups"], "example_count": len(meta["example_rows"])}


@router.delete("/internal-templates/{tpl_id}")
def delete_internal_template(tpl_id: str, _user=Depends(require_admin)):
    """删除非默认内部模板。"""
    if tpl_id == "default":
        raise HTTPException(400, detail="默认模板不可删除")
    if not os.path.exists(_tpl_meta_path(tpl_id)):
        raise HTTPException(404, detail="模板不存在")
    for f in (_tpl_path(tpl_id), _tpl_meta_path(tpl_id)):
        try:
            os.remove(f)
        except OSError:
            pass
    return {"ok": True}


@router.get("/internal-template/meta")
def get_internal_template_meta(template_id: str = "default", _user=Depends(get_current_user)):
    meta = _load_internal_meta(template_id)
    if not meta:
        return {"uploaded": False}
    return {"uploaded": True, "id": template_id, "filename": meta["filename"], "ext": meta["ext"],
            "sheets": meta["sheets"], "main_sheet": meta["main_sheet"],
            "info_fields": [f["label"] for f in meta["info_fields"]],
            "groups": meta["groups"], "example_count": len(meta["example_rows"])}


@router.get("/internal-template")
def download_internal_template(_user=Depends(get_current_user)):
    if not os.path.exists(_tpl_path("default")):
        raise HTTPException(404, detail="尚未上传内部模板")
    return FileResponse(_tpl_path("default"), filename="内部BOM模板.xls")


def _load():
    return safe_load(DATA_FILE, [])


def _save(data):
    safe_save(DATA_FILE, data)


def _next_id(data):
    return max((x.get("id", 0) for x in data), default=0) + 1


# ─── file parsing helpers ───

def _try_excel(content):
    """Try parsing as .xlsx (openpyxl) then .xls (xlrd). Returns (rows, error_msg)."""
    errors = []
    # Try openpyxl for .xlsx
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        ws = wb.active
        rows = [[str(c.value) if c.value is not None else '' for c in r] for r in ws.iter_rows()]
        if rows and any(any(c.strip() for c in r) for r in rows):
            return rows, None
        errors.append("openpyxl: 文件为空或所有单元格为空")
    except Exception as e:
        errors.append(f"openpyxl: {str(e)[:100]}")
    # Try xlrd for .xls
    try:
        import xlrd
        wb = xlrd.open_workbook(file_contents=content)
        ws = wb.sheet_by_index(0)
        rows = [[str(ws.cell_value(r, c)) for c in range(ws.ncols)] for r in range(ws.nrows)]
        if rows and any(any(c.strip() for c in r) for r in rows):
            return rows, None
        errors.append("xlrd: 文件为空")
    except Exception as e:
        errors.append(f"xlrd: {str(e)[:100]}")
    return None, "; ".join(errors) if errors else "未知错误"


def _is_readable(text):
    if not text: return False
    sample = text[:500]
    if not sample.strip(): return False
    total = max(len(sample), 1)
    good = sum(1 for c in sample if (
        c.isalpha() or c.isdigit() or ('一' <= c <= '鿿') or
        c in ' \t\n\r,;.:/-_()（）[]【】<>《》·、。，：；！？"\''
    ))
    return good / total >= 0.25


def _detect_encoding(content):
    try:
        import chardet
        result = chardet.detect(content[:10000])
        enc = result.get('encoding')
        return enc if enc else 'unknown'
    except ImportError:
        return 'unknown'

def _try_csv(content, filename):
    """Aggressive CSV/TSV parsing: tries every encoding to recover tabular data."""
    # 1. UTF-16 BOM
    if content[:2] == b'\xff\xfe':
        text = content[2:].decode('utf-16-le', errors='replace')
    elif content[:2] == b'\xfe\xff':
        text = content[2:].decode('utf-16-be', errors='replace')
    else:
        # 2. Try all encodings, pick the one with most CJK chars
        best_text = ''; best_cjk = -1; best_enc = ''
        candidates = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'gb18030', 'utf-16-le', 'utf-16-be', 'big5']
        for enc in candidates:
            try:
                text = content.decode(enc, errors='replace')
                cjk = sum(1 for c in text[:2000] if '一' <= c <= '鿿')
                # Also check if it has CSV structure
                has_delim = '\t' in text[:500] or ',' in text[:500]
                if cjk > best_cjk or (cjk == best_cjk and has_delim and best_enc):
                    best_cjk = cjk; best_text = text; best_enc = enc
            except: continue
        # Also try after stripping null bytes
        stripped = content.replace(b'\x00', b'')
        for enc in candidates:
            try:
                text = stripped.decode(enc, errors='replace')
                cjk = sum(1 for c in text[:2000] if '一' <= c <= '鿿')
                if cjk > best_cjk:
                    best_cjk = cjk; best_text = text; best_enc = enc + '-stripped'
            except: continue
        text = best_text if best_cjk > 0 else None

        if text is None:
            return None

    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Auto-detect delimiter: count tabs vs commas in first 500 chars
    sample = text[:500]
    tab_count = sample.count('\t')
    comma_count = sample.count(',')
    if tab_count > comma_count:
        delimiter = '\t'
    elif comma_count > 0:
        delimiter = ','
    else:
        delimiter = '\t' if filename.endswith('.tsv') else ','

    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        if rows and rows[0] and any(c.strip() for c in rows[0]):
            return rows
    except:
        pass

    # If comma didn't work, try tab
    if delimiter != '\t':
        try:
            rows = list(csv.reader(io.StringIO(text), delimiter='\t'))
            if rows and rows[0] and any(c.strip() for c in rows[0]):
                return rows
        except:
            pass

    return None


# ─── CRUD ───

@router.get("")
def list_bom_lists(
    search: str = Query(None),
    status: str = Query(None),
    project_id: int = Query(None),
    category: str = Query(None),
    _user=Depends(get_current_user)
):
    items = _load()
    if status:
        items = [x for x in items if x.get("status") == status]
    if project_id is not None:
        items = [x for x in items if x.get("project_id") == project_id]
    if category:
        items = [x for x in items if (x.get("meta") or {}).get("bom_category") == category or x.get("bom_category") == category]
    if search:
        q = search.lower()
        items = [x for x in items if q in (
            x.get("name","") + x.get("project_name","") +
            str((x.get("meta") or {}).get("bom_category","")) +
            str((x.get("meta") or {}).get("product_model",""))
        ).lower()]
    # resolve project names
    result = []
    for x in sorted(items, key=lambda x: x.get("created_at", ""), reverse=True):
        entry = dict(x)
        pid = x.get("project_id")
        if pid and not x.get("project_name"):
            try:
                from backend_v2.models import Project
                s = SessionLocal()
                p = s.query(Project).get(pid)
                entry["project_name"] = p.name if p else ""
                s.close()
            except:
                pass
        # don't send the full items array in list view
        entry["item_count"] = len(x.get("items", []))
        del entry["items"]
        m = entry.get("meta") or {}
        entry["product_name"] = entry.get("product_name", m.get("product_name", ""))
        entry["product_model"] = entry.get("product_model", m.get("product_model", ""))
        result.append(entry)
    return result


def _normalize_for_compare(val):
    """Normalize string for comparison: strip, collapse spaces, unify punctuation."""
    import re
    s = " ".join(str(val or "").split())
    for ch, en in [("，",","), ("。","."), ("；",";"), ("：",":"),
                    ("（","("), ("）",")"), ("＂",'"'), ("＇","'"),
                    ("！","!"), ("？","?"), ("～","~"), ("％","%"),
                    ("／","/"), ("＼","\\"), ("｛","{"), ("｝","}"),
                    ("［","["), ("］","]"), ("【","["), ("】","]"),
                    ("、",","), ("　"," ")]:
        s = s.replace(ch, en)
    return s


@router.get("/template")
def download_template(bom_category: str = "电机类", _user=Depends(get_current_user)):
    """Generate and download a BOM Excel template. 已上传内部模板时直接返回默认内部模板文件。"""
    if os.path.exists(_tpl_path("default")):
        meta = _load_internal_meta("default")
        fname = (meta or {}).get("filename", "内部BOM模板")
        return FileResponse(_tpl_path("default"), filename=fname)
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from io import BytesIO
    from fastapi.responses import StreamingResponse

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM模板"

    # ── styles ──
    blue_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    white_font = Font(color="FFFFFF", bold=True, size=11)
    title_font = Font(bold=True, size=14, color="1F4E79")
    label_font = Font(bold=True, size=10, color="333333")
    val_font = Font(size=10, color="555555")
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )
    header_border = Border(
        left=Side(style="thin", color="2F5496"),
        right=Side(style="thin", color="2F5496"),
        top=Side(style="thin", color="2F5496"),
        bottom=Side(style="thin", color="2F5496"),
    )

    # ── row 1: title with category ──
    cat_label = {"电机类":"电机类物料BOM","电控类":"电控类物料BOM","其他类":"其他物料BOM"}.get(bom_category, "物料清单")
    ws.merge_cells("A1:L1")
    c = ws.cell(row=1, column=1, value=f"BOM — {cat_label}")
    c.font = title_font; c.alignment = center

    # ── rows 2-5: meta info ──
    meta = [
        ["产品型号", "", "版本号", "", "发布日期", ""],
        ["设计人员", "", "审核人员", "", "批准人员", ""],
        ["项目名称", "", "客户名称", "", "BOM类别", bom_category],
        ["备注",  "", "", "", "", ""],
    ]
    for ri, row_data in enumerate(meta, 2):
        for ci, val in enumerate(row_data, 1):
            c = ws.cell(row=ri, column=ci, value=val)
            c.border = thin_border
            if ci % 2 == 1:  # label cell
                c.font = label_font
                c.alignment = center
                c.fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            else:
                c.font = val_font
                c.alignment = left

    # ── row 6: empty separator ──
    # leave row 6 blank

    # ── row 7: column headers (blue) ──
    HEADER_ROW = 7
    headers = ["序号", "物料编码", "物料名称", "规格型号", "元件位置", "封装", "品牌",
               "单位", "数量", "供应商", "参考单价", "备注"]
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=HEADER_ROW, column=col, value=h)
        c.fill = blue_fill; c.font = white_font; c.alignment = center
        c.border = header_border

    # ── column widths ──
    widths = [6, 14, 18, 18, 14, 10, 10, 6, 8, 18, 12, 20]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # ── row 8+: category-specific example data ──
    if bom_category == "电控类":
        examples = [
            ["1", "CTL-001", "IGBT模块", "FF600R12ME4", "PCB-B2", "Module", "Infineon", "个", "6", "供应商C", "280", "示例"],
            ["2", "CTL-002", "驱动芯片", "IR2110S", "PCB-B2", "SOIC-16", "IR", "个", "3", "供应商E", "18", "示例"],
            ["3", "CTL-003", "MCU主控", "TMS320F28335", "PCB-A1", "LQFP-176", "TI", "个", "1", "供应商F", "85", "示例"],
            ["4", "CTL-004", "电流传感器", "ACS712-20A", "PCB-B1", "SOIC-8", "Allegro", "个", "3", "供应商G", "22", "示例"],
            ["5", "CTL-005", "DC-Link电容", "500V/1000uF", "PCB-C1", "螺栓型", "Nichicon", "个", "1", "供应商H", "150", "示例"],
        ]
    elif bom_category == "其他类":
        examples = [
            ["1", "OTH-001", "接插件套件", "IP67/防水", "外壳-H1", "防水型", "Amphenol", "套", "2", "供应商X", "65", "示例"],
            ["2", "OTH-002", "散热器", "铝挤/风冷", "外壳-H1", "铝挤型", "自定义", "个", "1", "供应商Y", "200", "示例"],
            ["3", "OTH-003", "紧固件套装", "不锈钢M4-M8", "-", "标准件", "国标", "套", "1", "供应商Z", "35", "示例"],
            ["4", "OTH-004", "绝缘材料", "Nomex 0.25mm", "定子槽", "片状", "杜邦", "张", "10", "供应商W", "12", "示例"],
            ["5", "OTH-005", "线束总成", "耐高温200℃", "整机", "定制", "自定义", "套", "1", "供应商V", "180", "示例"],
        ]
    else:  # 电机类 (default)
        examples = [
            ["1", "MTR-001", "定子铁芯", "ST-210-35H300", "定子组-A1", "叠片式", "宝钢", "个", "1", "供应商A", "120", "示例"],
            ["2", "MTR-002", "永磁体", "N42SH-40x20x5", "转子组-A1", "径向", "日立", "片", "8", "供应商B", "45", "示例"],
            ["3", "MTR-003", "旋转变压器", "52XU0410", "传感器-A2", "SMD-52", "多摩川", "个", "1", "供应商D", "350", "示例"],
            ["4", "MTR-004", "轴承", "6205-2RS/C3", "端盖组", "深沟球", "SKF", "个", "2", "供应商K", "28", "示例"],
            ["5", "MTR-005", "转轴", "40Cr/调质", "转子组-A1", "光轴", "宝钢", "根", "1", "供应商L", "95", "示例"],
        ]
    gray_fill = PatternFill(start_color="F9F9F9", end_color="F9F9F9", fill_type="solid")
    for ri, row_data in enumerate(examples, HEADER_ROW + 1):
        for ci, val in enumerate(row_data, 1):
            c = ws.cell(row=ri, column=ci, value=val)
            c.font = Font(size=10, color="666666" if ri % 2 == 0 else "444444")
            c.alignment = center
            c.border = thin_border
            if ri % 2 == 0:
                c.fill = gray_fill

    # ── freeze panes below headers ──
    ws.freeze_panes = f"A{HEADER_ROW + 1}"

    buf = BytesIO(); wb.save(buf); buf.seek(0)
    from urllib.parse import quote
    safe_name = quote(f"BOM模板-{bom_category}.xlsx")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"})

# ── Cost trend: per-product cost comparison ──

def _cell(row, headers, keywords):
    for i, h in enumerate(headers):
        hh = str(h or "").strip()
        if any(k in hh for k in keywords):
            return str(row[i]).strip() if isinstance(row, list) and i < len(row) and row[i] is not None else ""
    return ""

def _to_qty(val):
    val = str(val or "").strip()
    try: return float(val)
    except:
        import re
        m = re.search(r"\d+(?:\.\d+)?", val)
        return float(m.group()) if m else 0

def _parse_bom_rows(bl):
    """Locate header row, then return data rows as dicts {name, spec, qty, price}."""
    headers = list(bl.get("headers", []))
    items = bl.get("items", [])
    if not items: return []
    hdr_idx = None
    for idx, row in enumerate(items):
        if isinstance(row, list):
            text = " ".join(str(c) for c in row)
            if ("名称" in text and "数量" in text) or ("元件类型" in text and "数量" in text):
                hdr_idx = idx; break
    if hdr_idx is not None:
        headers = items[hdr_idx]
        items = items[hdr_idx + 1:]
    rows = []
    for row in items:
        if not isinstance(row, list): continue
        name = _cell(row, headers, ["名称", "元件类型"])
        text = " ".join(str(c) for c in row)
        if not name or "合计" in text or "小计" in text or "总计" in text or "编号" == _cell(row, headers, ["编号"]):
            continue
        spec = _cell(row, headers, ["规格"])
        qty = _to_qty(_cell(row, headers, ["数量"]))
        price = _cell(row, headers, ["单价"])
        rows.append({"name": name[:60], "spec": spec[:60], "qty": qty, "price": price})
    return rows

def _material_price_db():
    """unit prices from the material archive (bom_materials.json), keyed by name|spec and name."""
    db = {}
    try:
        import os as _os
        path = _os.path.join(_os.path.dirname(__file__), "..", "..", "data", "bom_materials.json")
        mats = safe_load(path, [])
        for m in mats:
            try:
                pn = float(m.get("unit_price") or 0)
                nm = (m.get("name") or "").strip()
                if pn > 0 and nm:
                    key = f"{nm}|{(m.get('spec') or '').strip()}"
                    if key not in db or pn > db[key]:
                        db[key] = pn
                    if nm not in db or pn > db[nm]:
                        db[nm] = pn
            except: pass
    except: pass
    return db

@router.get("/cost-trend")
def bom_cost_trend(_user=Depends(get_current_user)):
    """Per-BOM material vs total cost comparison. Material cost = Σ(qty×unit price) using
    in-BOM prices or historical prices; total cost = material + 10% estimated manufacturing."""
    lists = _load()
    # price source chain: material archive -> historical prices seen across BOMs
    price_db = _material_price_db()
    for bl in lists:
        for row in _parse_bom_rows(bl):
            try:
                pn = float(row["price"])
                if pn > 0 and row["name"]:
                    key = f"{row['name']}|{row['spec']}"
                    if key not in price_db or pn > price_db[key]:
                        price_db[key] = pn
            except: pass
    result = []
    for bl in lists:
        rows = _parse_bom_rows(bl)
        material = 0.0
        found = 0
        for r in rows:
            pn = 0.0
            try: pn = float(r["price"])
            except: pass
            if pn <= 0:
                pn = price_db.get(f"{r['name']}|{r['spec']}") or price_db.get(r["name"], 0)
            if pn > 0 and r["qty"] > 0:
                material += pn * r["qty"]; found += 1
        overhead = material * 0.10  # estimated manufacturing/assembly overhead
        meta = bl.get("meta") or {}
        result.append({
            "id": bl.get("id"),
            "product_name": bl.get("product_name") or meta.get("product_name") or bl.get("name", ""),
            "product_model": bl.get("product_model") or meta.get("product_model") or "",
            "version": meta.get("version", ""),
            "bom_name": bl.get("name", ""),
            "date": (bl.get("created_at") or "")[:10],
            "rows": len(rows),
            "rows_priced": found,
            "material_cost": round(material, 2),
            "overhead_cost": round(overhead, 2),
            "total_cost": round(material + overhead, 2),
        })
    result.sort(key=lambda x: -x["total_cost"])
    return {
        "items": result,
        "overhead_rate": 0.10,
        "summary": {
            "bom_count": len(result),
            "total_material": round(sum(x["material_cost"] for x in result), 2),
            "total_cost": round(sum(x["total_cost"] for x in result), 2),
        },
    }


@router.get("/{list_id}")
def get_bom_list(list_id: int, _user=Depends(get_current_user)):
    items = _load()
    for x in items:
        if x["id"] == list_id:
            x = dict(x)
            m = x.get("meta") or {}
            x["product_name"] = x.get("product_name", m.get("product_name", ""))
            x["product_model"] = x.get("product_model", m.get("product_model", ""))
            return x
    raise HTTPException(status_code=404, detail="BOM清单不存在")


@router.post("", status_code=201)
def create_bom_list(data: dict, _user=Depends(get_current_user)):
    items = _load()
    bom = {
        "id": _next_id(items),
        "name": data.get("name", ""),
        "project_id": data.get("project_id"),
        "project_name": data.get("project_name", ""),
        "status": data.get("status", "有效"),
        "notes": data.get("notes", ""),
        "headers": data.get("headers", []),
        "items": data.get("items", []),
        "source_file": data.get("source_file", "粘贴导入"),
        "meta": data.get("meta", {}) or {},
        "info": data.get("info", []),
        "version": (data.get("meta") or {}).get("version", ""),
        "product_name": (data.get("meta") or {}).get("product_name", ""),
        "product_model": (data.get("meta") or {}).get("product_model", ""),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    # resolve project name if only id given
    if bom["project_id"] and not bom["project_name"]:
        try:
            from backend_v2.models import Project
            s = SessionLocal()
            p = s.query(Project).get(bom["project_id"])
            bom["project_name"] = p.name if p else ""
            s.close()
        except:
            pass
    if data.get("bom_category"):
        bom["meta"] = {**bom["meta"], "bom_category": data["bom_category"]}
    items.append(bom)
    _save(items)
    return bom


@router.put("/batch/associate-project")
def batch_associate_project(data: dict, _user=Depends(get_current_user)):
    """Batch associate BOM lists with a project."""
    ids = set(data.get("ids", []))
    project_id = data.get("project_id")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    items = _load()
    from backend_v2.models import Project, SessionLocal
    pname = ""
    try:
        s = SessionLocal()
        p = s.query(Project).get(project_id)
        pname = p.name if p else ""
        s.close()
    except:
        pass
    updated = 0
    for x in items:
        if x["id"] in ids:
            x["project_id"] = project_id
            x["project_name"] = pname
            x["updated_at"] = datetime.utcnow().isoformat()
            updated += 1
    _save(items)
    return {"updated": updated}


@router.put("/{list_id}")
def update_bom_list(list_id: int, data: dict, _user=Depends(get_current_user)):
    items = _load()
    for x in items:
        if x["id"] == list_id:
            for k in ("name","project_id","project_name","status","notes","items","meta","bom_category","info"):
                if k in data:
                    if k == "bom_category":
                        # store in meta
                        m = x.get("meta") or {}
                        m["bom_category"] = data[k]
                        x["meta"] = m
                    else:
                        x[k] = data[k]
            # product fields: top level + meta mirror (same pattern as version)
            m = x.get("meta") or {}
            for k, mk in (("product_name", "product_name"), ("product_model", "product_model")):
                if k in data:
                    m[mk] = data[k] or ""
                    x[k] = data[k] or ""
            if m:
                x["meta"] = m
            x["updated_at"] = datetime.utcnow().isoformat()
            _save(items)
            return x
    raise HTTPException(status_code=404, detail="BOM清单不存在")


@router.delete("/{list_id}")
def delete_bom_list(list_id: int, _user=Depends(get_current_user)):
    items = _load()
    filtered = [x for x in items if x["id"] != list_id]
    if len(filtered) == len(items):
        raise HTTPException(status_code=404, detail="BOM清单不存在")
    _save(filtered)
    # Also clean up attachments and their files
    atts = _load_att()
    for a in atts[:]:
        if str(a.get("list_id")) == str(list_id):
            path = _resolve_att_path(a)
            if path and os.path.exists(path):
                try: os.remove(path)
                except: pass
            atts.remove(a)
    _save_att(atts)
    return {"ok": True}


@router.post("/batch-delete")
def batch_delete(body: dict = Body(...), _user=Depends(get_current_user)):
    ids = set(body.get("ids", []))
    items = _load()
    filtered = [x for x in items if x["id"] not in ids]
    removed = len(items) - len(filtered)
    _save(filtered)
    return {"removed": removed}


# ─── preview decoded file content ───

@router.post("/preview")
async def preview_file(
    file: UploadFile = File(...),
    encoding: str = Form(""),
    _user=Depends(get_current_user)
):
    """Preview file content: try Excel first, then text decoding."""
    content = await file.read()
    filename = (file.filename or "")
    sample = ""
    detected = "unknown"
    method = "text"

    # 1. Try Excel parsing first (most common for BOM files)
    rows, excel_err = _try_excel(content)
    if rows and len(rows) > 0:
        # Format as table preview
        lines = []
        headers = [str(c).strip() for c in rows[0]]
        lines.append(" | ".join(headers[:10]))
        for row in rows[1:6]:  # first 5 data rows
            lines.append(" | ".join(str(c).strip()[:30] for c in row[:10]))
        sample = "\n".join(lines)
        detected = "excel"
        method = "excel"
        return {
            "filename": filename, "encoding": detected, "size": len(content),
            "sample": sample, "method": method,
            "rows": min(len(rows) - 1, 5), "total_rows": len(rows) - 1,
            "headers": headers[:10],
        }

    # 2. Try text decoding with chardet + fallbacks
    if encoding:
        try:
            text = content.decode(encoding, errors='replace')
            detected = encoding
            sample = text[:2000]
        except Exception as e:
            return {"error": f"解码失败: {str(e)[:100]}", "encoding": encoding, "method": "text"}
    else:
        detected = _detect_encoding(content)
        if detected and detected != 'unknown':
            try:
                text = content.decode(detected, errors='replace')
                if _is_readable(text):
                    sample = text[:2000]
                else:
                    sample = ""
            except:
                sample = ""
        if not sample:
            # Try all encodings, pick the one with most CJK chars
            best_enc = 'unknown'; best_text = ''; best_cjk = 0
            for enc in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'gb18030', 'utf-16-le', 'utf-16-be', 'big5']:
                try:
                    text = content.decode(enc, errors='replace')
                    cjk = sum(1 for c in text[:1000] if '一' <= c <= '鿿' or '㐀' <= c <= '䶿')
                    if cjk > best_cjk:
                        best_cjk = cjk; best_text = text; best_enc = enc
                except: continue
            if best_cjk > 0:
                sample = best_text[:2000]; detected = best_enc
            elif best_text:
                # No CJK found, use the one with best printable ratio
                sample = best_text[:2000]; detected = best_enc

    if not sample:
        # 3. Show hex for truly binary files
        sample = f"[无法解码为文本] 文件头: {content[:80].hex(' ')}"

    return {
        "filename": filename, "encoding": detected, "size": len(content),
        "sample": sample, "method": method,
    }


# ─── import BOM file as a complete list ───

@router.post("/import")
async def import_bom_list(
    file: UploadFile = File(...),
    name: str = Form(""),
    project_id: int = Form(None),
    status: str = Form("有效"),
    encoding: str = Form(""),
    _user=Depends(get_current_user)
):
    content = await file.read()
    filename = (file.filename or "")
    if not name:
        name = os.path.splitext(filename)[0] if filename else "未命名BOM"

    detected_encoding = "unknown"

    rows, excel_err = _try_excel(content)
    csv_rows = None
    csv_err = None
    if not rows:
        if encoding:
            # Manual encoding specified: decode directly
            try:
                text = content.decode(encoding, errors='replace')
                text = text.replace('\r\n', '\n').replace('\r', '\n')
                delimiter = '\t' if '\t' in text[:500] else ','
                csv_rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
                detected_encoding = encoding
            except Exception as e:
                csv_err = f"指定编码{encoding}解码失败: {str(e)[:100]}"
        else:
            csv_rows = _try_csv(content, filename)
            if csv_rows:
                detected_encoding = _detect_encoding(content)
    if not rows:
        rows = csv_rows
    if not rows or len(rows) < 1:
        hex_preview = content[:40].hex(' ')
        detail = f"文件头(hex): {hex_preview}"
        if excel_err: detail += f"\nExcel解析: {excel_err}"
        if csv_err: detail += f"\nCSV解析: {csv_err}"
        if detected_encoding != "unknown": detail += f"\n检测编码: {detected_encoding}"
        if content[:2] == b'PK': detail += "\n提示: ZIP格式。如是加密.xlsx，请先取消保护。"
        elif content[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1': detail += "\n提示: 旧版.xls格式。请用Excel另存为 .xlsx"
        raise HTTPException(status_code=400, detail=detail)

    # Use first row as headers
    headers = [str(c).strip() for c in rows[0]]
    data_rows = []
    for row in rows[1:]:
        if not any(str(c).strip() for c in row): continue
        data_rows.append([str(c).strip() if c else '' for c in row])

    # Get project name
    project_name = ""
    if project_id:
        try:
            from backend_v2.models import Project
            s = SessionLocal()
            p = s.query(Project).get(project_id)
            project_name = p.name if p else ""
            s.close()
        except:
            pass

    items = _load()
    bom = {
        "id": _next_id(items),
        "name": name,
        "project_id": project_id,
        "project_name": project_name,
        "status": status,
        "notes": "",
        "source_file": filename,
        "headers": headers,
        "items": data_rows,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    items.append(bom)
    _save(items)
    # preview sample (first 2 data rows)
    sample = []
    for row in data_rows[:2]:
        sample.append(" | ".join(str(c)[:30] for c in row[:6]))
    return {
        "id": bom["id"], "name": name,
        "item_count": len(data_rows), "headers": headers,
        "encoding": detected_encoding,
        "sample": sample,
        "filename": filename,
    }


# ─── export a BOM list to CSV ───

@router.get("/{list_id}/export")
def export_bom_list(list_id: int, _user=Depends(get_current_user)):
    data = _load()
    for x in data:
        if x["id"] == list_id:
            headers = x.get("headers", [f"Col{i+1}" for i in range(max(len(r) for r in x.get("items", [[]])))])
            csv_lines = []
            # 表头信息区: 标题行 + 标准字段 + 字段按模板行列布局(label,value 成对), 说明文字原样
            title = ""
            std = []
            by_row = {}
            notes = []
            for f in x.get("info") or []:
                if not isinstance(f, dict):
                    continue
                if f.get("type") == "title":
                    title = str(f.get("label", ""))
                elif f.get("type") == "note":
                    notes.append(str(f.get("label", "")))
                elif f.get("type") == "std":
                    std.append((f.get("col", 0), str(f.get("label", "")), str(f.get("value", ""))))
                else:
                    r = f.get("row", 0)
                    by_row.setdefault(r, []).append((f.get("col", 0), str(f.get("label", "")), str(f.get("value", ""))))
            if title:
                csv_lines.append(f'"{title}"')
            for _, lbl, val in sorted(std):
                csv_lines.append(f'"{lbl}","{val}"')
            for r in sorted(by_row):
                cells = []
                for _, lbl, val in sorted(by_row[r]):
                    cells.append(f'"{lbl}","{val}"')
                if cells:
                    csv_lines.append(",".join(cells))
            for n in notes:
                csv_lines.append(f'"{n}"')
            if csv_lines:
                csv_lines.append("")
            csv_lines.append(','.join(f'"{h}"' for h in headers))
            for row in x.get("items", []):
                csv_lines.append(','.join(f'"{c}"' for c in row))
            return {"csv": '\n'.join(csv_lines), "name": x.get("name", ""), "headers": headers}
    raise HTTPException(status_code=404, detail="BOM清单不存在")


# 模板表头字段 → 值单元格 (xls 行, 列) 映射, 由模板合并/布局实测得出
_TPL_VALUE_CELLS = [
    (("产品名称", "规格"), (1, 3)),
    (("条形码",), (1, 4)),
    (("版本",), (1, 5)),
    (("时间", "日期"), (1, 7)),
    (("客户名称",), (2, 2)),
    (("总装图",), (2, 4)),
    (("定子组件",), (2, 7)),
    (("电机编号",), (3, 2)),
    (("外形图",), (3, 4)),
    (("转子组件",), (3, 7)),
    (("电机编码",), (4, 2)),
    (("接口类型",), (4, 4)),
    (("定子半成品",), (4, 7)),
    (("电磁方案号",), (5, 2)),
    (("电气原理图",), (5, 4)),
    (("绕组",), (5, 7)),
    (("性能参数",), (7, 2)),
]
# 模板物料区分组起始行(xls 0-based): 分组行之下即物料行
_TPL_GROUP_START = {"半成品": 11, "主材": 17, "标准件": 31, "辅材": 42}


def _template_base_sheet(tpl_file):
    """以模板文件为基底复制出可写 sheet, 返回 (nwb, ws, style_of, src)。

    复制保留全部合并单元格与行列信息; xlutils 复制时会跳过空单元格、合并成员格
    沿用主格样式, 因此再按模板每个单元格各自的 XF 逐一写回(含空白记录), 保证
    导出文件的字体/边框/底色/对齐与模板 1:1。style_of(r,c) 返回该格模板样式。"""
    import xlrd
    from xlutils.filter import process, XLRDReader, XLWTWriter
    wb = xlrd.open_workbook(tpl_file, formatting_info=True)
    for fmt in wb.format_map.values():  # xlwt 无法写 None 格式字符串, 需修正
        if getattr(fmt, "format_str", None) is None:
            fmt.format_str = "General"

    class _CapWriter(XLWTWriter):
        def workbook(self, rdbook, wtbook_name):
            super().workbook(rdbook, wtbook_name)
            self.captured_styles = list(self.style_list)

    writer = _CapWriter()
    process(XLRDReader(wb, "unknown.xls"), writer)
    _name, nwb = writer.output[0]
    src = wb.sheet_by_index(0)
    ws = nwb.get_sheet(0)
    styles = writer.captured_styles

    def style_of(r, c):
        xf = src.cell_xf_index(r, c)
        return styles[xf] if xf is not None else None

    for r in range(src.nrows):
        for c in range(src.ncols):
            xf = src.cell_xf_index(r, c)
            if xf is None:
                continue
            v = src.cell_value(r, c)
            if isinstance(v, str):
                v = v.strip()
            ws.write(r, c, v, styles[xf])
    return nwb, ws, style_of, src


@router.get("/{list_id}/export-xlsx")
def export_bom_list_xlsx(list_id: int, _user=Depends(get_current_user)):
    """以模板文件为基底导出 .xls: 模板样式/合并/布局 100% 保留, 表头值与物料按模板位置填入。
    按 BOM 保存时记录的 template_id 定位其所属模板; 旧 BOM 无记录时回退默认模板。"""
    from fastapi.responses import StreamingResponse
    data = _load()
    x = next((d for d in data if d["id"] == list_id), None)
    if not x:
        raise HTTPException(status_code=404, detail="BOM清单不存在")
    tpl_id = ((x.get("meta") or {}).get("template_id") or "default")
    meta = _load_internal_meta(tpl_id) or _load_internal_meta("default")
    tpl_file = _tpl_path(tpl_id)
    if not os.path.exists(tpl_file):
        tpl_file = _tpl_path("default")
    nwb, ws, style_of, src = _template_base_sheet(tpl_file)

    # 表头信息区: 字段自带值单元格则按值单元格写, 否则按标签关键字回退硬编码映射(旧数据)
    for f in x.get("info") or []:
        if not isinstance(f, dict) or f.get("type") not in ("field", "std"):
            continue
        lbl = str(f.get("label", ""))
        val = str(f.get("value", ""))
        if not val:
            continue
        pos = None
        if f.get("value_row") is not None and f.get("value_col") is not None:
            pos = (f["value_row"], f["value_col"])
        else:
            for keys, rc in _TPL_VALUE_CELLS:
                if any(k in lbl for k in keys):  # keys 为同一单元格的候选关键字, 命中任一即可
                    pos = rc
                    break
        if pos:
            ws.write(pos[0], pos[1], val, style_of(pos[0], pos[1]))
    # 物料区: 按模板分组行位置写入当前 BOM 物料(序号/编码/名称/图号/规格/单位/用量/备注)
    by_group = {}
    for it in x.get("items", []):
        if isinstance(it, (list, tuple)) and len(it) >= 9:
            by_group.setdefault(str(it[0]), []).append(it)
    gs = (meta or {}).get("group_starts") or {}
    gr = (meta or {}).get("group_rows") or {}
    order = (meta or {}).get("groups") or list(_TPL_GROUP_START.keys())
    if not gs:
        gs = dict(_TPL_GROUP_START)
    for gi, gname in enumerate(order):
        if gname not in gs:
            continue
        r0 = gs[gname]
        # 组容量: 解析出的每组行数; 缺省按下一分组行之前(末组到第50行)的物料行数
        if gname in gr:
            cap = int(gr[gname])
        else:
            nxt = gs[order[gi + 1]] if gi + 1 < len(order) and order[gi + 1] in gs else 50
            cap = nxt - r0 - 1
        row = r0
        for it in by_group.get(gname, [])[:cap]:
            ws.write(row, 0, str(it[1]), style_of(row, 0))       # 序号
            ws.write(row, 1, str(it[2]), style_of(row, 1))       # 物料编码
            ws.write(row, 2, str(it[3]), style_of(row, 2))       # 物料名称
            ws.write(row, 3, str(it[4]), style_of(row, 3))       # 零件图号
            ws.write(row, 4, str(it[5]), style_of(row, 4))       # 材料、牌号、规格、技术条件
            ws.write(row, 5, str(it[6]), style_of(row, 5))       # 单位
            ws.write(row, 6, str(it[7]), style_of(row, 6))       # 用量
            ws.write(row, 7, str(it[8]), style_of(row, 7))       # 备注
            row += 1

    buf = io.BytesIO()
    nwb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.ms-excel",
        headers={"Content-Disposition": f'attachment; filename="BOM_{list_id}.xls"'},
    )


# ─── compare two BOM lists ───

@router.post("/compare")
def compare_bom_lists(body: dict = Body(...), _user=Depends(get_current_user)):
    """Compare two BOM lists by code column, return per-cell diff markers."""
    id_a = body.get("id_a")
    id_b = body.get("id_b")
    data = _load()
    a = next((x for x in data if x["id"] == id_a), None)
    b = next((x for x in data if x["id"] == id_b), None)
    if not a or not b:
        raise HTTPException(status_code=404, detail="BOM清单不存在")

    headers_a = a.get("headers", [])
    headers_b = b.get("headers", [])
    items_a = {row[0]: row for row in a.get("items", []) if row and row[0]}
    items_b = {row[0]: row for row in b.get("items", []) if row and row[0]}

    codes_a = set(items_a.keys())
    codes_b = set(items_b.keys())

    # Per-cell comparison for shared codes
    max_cols = max(len(headers_a), len(headers_b))
    changed_detail = []
    for code in sorted(codes_a & codes_b):
        ra = items_a[code]
        rb = items_b[code]
        if ra == rb:
            continue
        cells = []
        for ci in range(max_cols):
            va = ra[ci] if ci < len(ra) else ""
            vb = rb[ci] if ci < len(rb) else ""
            # Normalize for comparison: strip, collapse spaces, normalize punctuation
            va_norm = _normalize_for_compare(va)
            vb_norm = _normalize_for_compare(vb)
            if va_norm != vb_norm:
                cells.append({
                    "col": ci,
                    "header": headers_a[ci] if ci < len(headers_a) else f"列{ci+1}",
                    "a": va,
                    "b": vb,
                })
        changed_detail.append({"code": code, "cells": cells, "a": ra, "b": rb})

    return {
        "name_a": a.get("name"), "name_b": b.get("name"),
        "headers_a": headers_a, "headers_b": headers_b,
        "count_a": len(items_a), "count_b": len(items_b),
        "only_in_a": [items_a[c] for c in sorted(codes_a - codes_b)],
        "only_in_b": [items_b[c] for c in sorted(codes_b - codes_a)],
        "common": len(codes_a & codes_b),
        "changed_detail": changed_detail,
    }


# ─── OCR image to table ───

# Lazy-load OCR reader (singleton, loaded once)
_ocr_reader = None

def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        _ocr_reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
    return _ocr_reader


@router.post("/ocr-to-table")
async def ocr_to_table(file: UploadFile = File(...), _user=Depends(get_current_user)):
    """Upload screenshot/image, OCR extract text, return as tab-separated table."""
    import tempfile
    content = await file.read()

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(content)
    tmp.close()

    try:
        reader = _get_ocr_reader()
        results = reader.readtext(tmp.name)
    except ImportError:
        os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail="OCR引擎未安装，请运行: pip install easyocr")
    except Exception as e:
        os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail=f"OCR识别失败: {str(e)[:200]}")
    os.unlink(tmp.name)

    if not results:
        return {"text": "", "rows": 0, "message": "未检测到文字"}

    # Sort results by Y position (top to bottom), group into rows
    # Each result: (bbox, text, confidence)
    results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))  # sort by Y then X

    # Group text lines by similar Y coordinate
    rows = []
    current_row = []
    current_y = None
    y_threshold = 15  # pixels tolerance for same row

    for bbox, text, conf in results:
        y_center = (bbox[0][1] + bbox[2][1]) / 2
        if current_y is None or abs(y_center - current_y) < y_threshold:
            current_row.append((bbox[0][0], text))  # store X position + text
        else:
            # Sort current row by X, save
            current_row.sort(key=lambda x: x[0])
            rows.append([t for _, t in current_row])
            current_row = [(bbox[0][0], text)]
        current_y = y_center

    if current_row:
        current_row.sort(key=lambda x: x[0])
        rows.append([t for _, t in current_row])

    # Convert to tab-separated text
    text = "\n".join("\t".join(r) for r in rows)

    return {"text": text, "rows": len(rows), "sample": text[:500]}


@router.get("/{list_id}/check")
def check_bom_completeness(list_id: str, _user=Depends(get_current_user)):
    """AI-powered BOM completeness check — rule-based + optional AI analysis."""
    lists = _load()
    bom = next((l for l in lists if l.get("id") == list_id), None)
    if not bom:
        raise HTTPException(404, "BOM not found")

    items = bom.get("items", [])
    headers = bom.get("headers", [])
    total = len(items)

    issues = []
    warnings = 0
    errors = 0

    # Map header names to fields using Chinese names
    hdr_map = {}
    for i, h in enumerate(headers):
        hdr_map[i] = h.strip() if h else ""

    for idx, item in enumerate(items):
        row = idx + 1
        # Handle both list and dict items
        if isinstance(item, list):
            cells = [str(c).strip() if c else "" for c in item]
            def get_col(name):
                for i, h in enumerate(headers):
                    if h.strip().lower().find(name) >= 0 and i < len(cells):
                        return cells[i]
                return ""
        else:
            def get_col(name):
                for k, v in item.items():
                    if k.lower().find(name.lower()) >= 0 or name.lower().find(k.lower()) >= 0:
                        return str(v).strip() if v else ""
                return ""

        name = get_col("名称")
        spec = get_col("规格")
        pos = get_col("位置") or get_col("位号")
        qty = get_col("数量")
        unit = get_col("单位")
        supplier = get_col("供应商")
        price = get_col("单价")
        code = get_col("编码")
        brand = get_col("品牌")

        # Check 1: Missing name
        if not name:
            issues.append({"row": row, "field": "物料名称", "severity": "error", "msg": "物料名称为空"})
            errors += 1

        # Check 2: Missing spec
        if not spec:
            issues.append({"row": row, "field": "规格型号", "severity": "warning", "msg": "规格型号为空"})
            warnings += 1

        # Check 3: Zero or negative quantity
        try:
            qn = float(qty) if qty else 0
            if qn <= 0:
                issues.append({"row": row, "field": "数量", "severity": "error", "msg": f"数量异常({qty})"})
                errors += 1
        except:
            if not qty:
                issues.append({"row": row, "field": "数量", "severity": "error", "msg": "数量为空"})
                errors += 1

        # Check 4: Missing unit
        if not unit:
            issues.append({"row": row, "field": "单位", "severity": "warning", "msg": "单位为空"})
            warnings += 1

        # Check 5: Missing supplier
        if not supplier:
            issues.append({"row": row, "field": "供应商", "severity": "warning", "msg": "供应商为空"})
            warnings += 1

        # Check 6: Zero price
        try:
            pn = float(price) if price else 0
            if pn <= 0:
                issues.append({"row": row, "field": "参考单价", "severity": "warning", "msg": f"单价为0或为空"})
                warnings += 1
        except:
            pass

        # Check 7: Missing brand
        if not brand and not supplier:
            issues.append({"row": row, "field": "品牌", "severity": "info", "msg": "品牌和供应商均为空"})

        # Check 8: Empty position
        if not pos:
            issues.append({"row": row, "field": "元件位置", "severity": "warning", "msg": "元件位置为空"})
            warnings += 1

    # Check 9: Duplicate positions
    positions = {}
    for idx, item in enumerate(items):
        pos = ""
        if isinstance(item, list):
            hdrs = [h.strip() for h in headers]
            for i, h in enumerate(hdrs):
                if h.lower().find("位置") >= 0 or h.lower().find("位号") >= 0:
                    if i < len(item): pos = str(item[i]).strip()
        else:
            for k, v in item.items():
                if "position" in k.lower() or "位置" in k.lower() or "位号" in k.lower():
                    pos = str(v).strip()
        if pos:
            positions.setdefault(pos, []).append(idx + 1)

    for pos, rows in positions.items():
        if len(rows) > 1 and pos:
            issues.append({"row": rows[1], "field": "元件位置", "severity": "error",
                          "msg": f"位号'{pos}'重复(第{rows[0]}行已使用)"})
            errors += 1

    # Build summary
    complete = total > 0 and errors == 0
    score = max(0, 100 - errors * 10 - warnings * 3)

    return {
        "total_items": total,
        "issues": issues,
        "errors": errors,
        "warnings": warnings,
        "score": score,
        "complete": complete,
        "summary": f"共 {total} 项物料，发现 {errors} 个错误、{warnings} 个警告，健康度 {score}/100"
    }


@router.post("/{list_id}/ask")
def ask_bom(list_id: str, body: dict = Body(...), _user=Depends(get_current_user)):
    """AI-powered Q&A over a BOM list. Body: {"question": "最贵的5个料是什么?"}"""
    import json as _json, urllib.request, ssl as _ssl

    question = body.get("question", "").strip()
    if not question:
        raise HTTPException(400, "问题不能为空")

    lists = _load()
    bom = next((l for l in lists if l.get("id") == list_id), None)
    if not bom:
        raise HTTPException(404, "BOM not found")

    headers = bom.get("headers", [])
    items = bom.get("items", [])
    bom_name = bom.get("name", "") or bom.get("meta", {}).get("name", "")

    # Build compact BOM text for AI context
    lines = [f"BOM名称: {bom_name}", f"总物料数: {len(items)}", "表头: " + ", ".join(headers[:12]), ""]
    for idx, item in enumerate(items):
        if isinstance(item, list):
            row_str = " | ".join(str(c) for c in item[:12])
        else:
            row_str = " | ".join(str(item.get(k, "")) for k in list(item.keys())[:12])
        lines.append(f"{idx+1}. {row_str}")
    bom_text = "\n".join(lines[:150])  # Cap at ~150 lines for token budget

    # Load API key
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ai_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = _json.load(f)
    api_key = config.get("engines", {}).get("tongyi", {}).get("api_key", "")
    if len(api_key) < 20:
        # Fallback: keyword-based search
        return _keyword_search(bom_text, question, items)

    prompt = f"""你是BOM分析助手。根据以下BOM数据回答用户问题。简洁直接，用中文。

{bom_text}

用户问题: {question}

要求:
- 如果问题是查询具体物料，列出物料名称、规格、数量
- 如果是统计类问题，给出准确数字
- 如果是排序/筛选类问题，逐一列出
- 回答控制在200字以内，避免重复BOM全部数据"""

    try:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False; ctx.verify_mode = _ssl.CERT_NONE
        data = _json.dumps({"model": "qwen-turbo", "messages": [{"role": "user", "content": prompt}],
                           "max_tokens": 600, "temperature": 0.1}).encode()
        req = urllib.request.Request("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            data=data, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        result = _json.loads(resp.read())
        answer = result["choices"][0]["message"]["content"]
        return {"question": question, "answer": answer, "source": "ai"}
    except Exception as e:
        return _keyword_search(bom_text, question, items)


def _keyword_search(bom_text: str, question: str, items: list):
    """Fallback: keyword-based search when AI is unavailable."""
    q_lower = question.lower()
    keywords = []
    # Extract Chinese/English keywords from question
    for kw in ["电容", "电阻", "电感", "IC", "芯片", "连接器", "MOSFET", "IGBT", "二极管", "三极管",
               "永磁", "绕组", "定子", "转子", "轴承", "散热", "PCB", "最贵", "品牌", "供应商",
               "数量", "单价", "封装", "规格", "最多", "最少", "电容", "cap", "resistor", "inductor"]:
        if kw.lower() in q_lower:
            keywords.append(kw)

    # Search items for keyword matches
    matches = []
    for idx, item in enumerate(items):
        if isinstance(item, list):
            row_text = " ".join(str(c).lower() for c in item)
        else:
            row_text = " ".join(str(v).lower() for v in item.values())
        score = sum(1 for kw in keywords if kw.lower() in row_text)
        if score > 0:
            matches.append({"idx": idx + 1, "score": score, "text": row_text[:200]})

    matches.sort(key=lambda x: -x["score"])
    top = matches[:10]

    if not top:
        answer = "未找到与 \"" + question + "\" 相关的物料。可尝试: 查询具体物料名(如电容=cap)、统计数量、对比单价等。"
    else:
        answer = f"关键词匹配找到 {len(matches)} 项相关物料，Top {len(top)}:\n"
        for m in top:
            answer += f"  · 第{m['idx']}行: {m['text'][:120]}\n"

    return {"question": question, "answer": answer, "source": "keyword"}


@router.get("/{list_id}/estimate-cost")
def estimate_bom_cost(list_id: str, _user=Depends(get_current_user)):
    """Estimate BOM cost based on historical procurement prices."""
    lists = _load()
    bom = next((l for l in lists if l.get("id") == list_id), None)
    if not bom: raise HTTPException(404, "BOM not found")

    items = bom.get("items", [])
    headers = bom.get("headers", [])

    # Build historical price database from ALL BOMs
    price_db = {}  # key: normalized_name|spec -> {price, supplier, date}
    for bl in lists:
        for item in bl.get("items", []):
            name, spec, price, supplier = "", "", "", ""
            if isinstance(item, list):
                for i, h in enumerate(bl.get("headers", [])):
                    val = str(item[i]).strip() if i < len(item) and item[i] else ""
                    hl = h.strip().lower()
                    if "名称" in hl: name = val
                    elif "规格" in hl: spec = val
                    elif "单价" in hl: price = val
                    elif "供应商" in hl: supplier = val
            else:
                for k, v in item.items():
                    if k.lower().find("name") >= 0: name = str(v).strip()
                    elif k.lower().find("spec") >= 0: spec = str(v).strip()
                    elif k.lower().find("price") >= 0: price = str(v).strip()
                    elif k.lower().find("supplier") >= 0: supplier = str(v).strip()
            try:
                pn = float(price)
                if pn > 0 and name:
                    key = f"{name}|{spec}"
                    if key not in price_db or pn > price_db[key]["price"]:  # keep highest price
                        price_db[key] = {"price": pn, "supplier": supplier, "date": bl.get("created_at", "")}
            except: pass

    # Estimate each item
    results = []
    total = 0
    found_count = 0
    for idx, item in enumerate(items):
        name, spec, qty = "", "", "1"
        if isinstance(item, list):
            for i, h in enumerate(headers):
                val = str(item[i]).strip() if i < len(item) and item[i] else ""
                hl = h.strip().lower()
                if "名称" in hl: name = val
                elif "规格" in hl: spec = val
                elif "数量" in hl and val: qty = val
        else:
            for k, v in item.items():
                vl = str(v).strip() if v else ""
                if k.lower().find("name") >= 0: name = vl
                elif k.lower().find("spec") >= 0: spec = vl
                elif k.lower().find("qty") >= 0 and vl: qty = vl

        key = f"{name}|{spec}"
        hist = price_db.get(key)
        qn = 0
        try: qn = float(qty)
        except: qn = 0

        if hist and qn > 0:
            item_cost = hist["price"] * qn
            total += item_cost
            found_count += 1
            results.append({"row": idx + 1, "name": name[:40], "spec": spec[:40], "qty": qty,
                           "unit_price": hist["price"], "total_price": round(item_cost, 2),
                           "supplier": hist["supplier"], "has_price": True})
        else:
            results.append({"row": idx + 1, "name": name[:40], "spec": spec[:40], "qty": qty,
                           "unit_price": 0, "total_price": 0, "supplier": "", "has_price": False})

    return {
        "items": results,
        "total_cost": round(total, 2),
        "items_with_price": found_count,
        "items_without_price": len(results) - found_count,
        "summary": f"总预估成本: ¥{total:,.2f} ({found_count}/{len(results)} 项有历史价格)"
    }


@router.post("/compare/generate-ecn")
def generate_ecn(body: dict = Body(...), _user=Depends(get_current_user)):
    """Generate ECN (Engineering Change Notice) from BOM comparison, powered by AI."""
    import json as _json, urllib.request, ssl as _ssl

    id_a = body.get("bom_a", "")
    id_b = body.get("bom_b", "")
    if not id_a or not id_b:
        raise HTTPException(400, "需要两个BOM ID")

    lists = _load()
    bom_a = next((l for l in lists if l.get("id") == id_a), None)
    bom_b = next((l for l in lists if l.get("id") == id_b), None)
    if not bom_a or not bom_b:
        raise HTTPException(404, "BOM not found")

    name_a = bom_a.get("name", "") or bom_a.get("meta", {}).get("name", "BOM-A")
    name_b = bom_b.get("name", "") or bom_b.get("meta", {}).get("name", "BOM-B")

    # Quick comparison
    items_a = bom_a.get("items", [])
    items_b = bom_b.get("items", [])

    # Build lookup by first columns (code/position)
    def row_key(item):
        if isinstance(item, list): return str(item[0]).strip() if item else ""
        else: return str(item.get("code", item.get("position", item.get("seq", "")))).strip()

    set_a = {row_key(i): i for i in items_a}
    set_b = {row_key(i): i for i in items_b}

    only_a = [set_a[k] for k in set_a if k and k not in set_b]
    only_b = [set_b[k] for k in set_b if k and k not in set_a]
    common_keys = [k for k in set_a if k and k in set_b]

    # Build summary for AI
    summary = [
        f"BOM-A: {name_a} ({len(items_a)} 项)",
        f"BOM-B: {name_b} ({len(items_b)} 项)",
        f"\n新增物料 ({len(only_b)} 项):",
    ]
    for item in only_b[:10]:
        row = " | ".join(str(c) for c in (item if isinstance(item, list) else list(item.values())[:6]))
        summary.append(f"  + {row[:150]}")
    summary.append(f"\n删除物料 ({len(only_a)} 项):")
    for item in only_a[:10]:
        row = " | ".join(str(c) for c in (item if isinstance(item, list) else list(item.values())[:6]))
        summary.append(f"  - {row[:150]}")
    summary.append(f"\n共同物料 ({len(common_keys)} 项)")

    diff_text = "\n".join(summary)[:2000]

    # Load API key
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ai_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = _json.load(f)
    api_key = config.get("engines", {}).get("tongyi", {}).get("api_key", "")

    if len(api_key) < 20:
        return {
            "ecn_number": f"ECN-{datetime.now().strftime('%Y%m%d%H%M')}",
            "title": f"{name_a} → {name_b} BOM变更",
            "change_description": f"新增{len(only_b)}项，删除{len(only_a)}项",
            "affected_items": {"added": len(only_b), "removed": len(only_a), "common": len(common_keys)},
            "impact": "请配置AI Key以获取详细分析",
            "approval_level": "常规",
            "source": "rule"
        }

    prompt = f"""你是ECN工程师。根据以下BOM对比摘要，生成一份工程变更通知单。用中文回答。

{diff_text}

请返回以下格式的JSON(只返回JSON):
{{
  "title": "变更标题(15字以内)",
  "change_description": "变更详细描述(100字以内)",
  "impact": "影响评估(50字以内)",
  "approval_level": "常规/重要/紧急"
}}"""

    try:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False; ctx.verify_mode = _ssl.CERT_NONE
        data = _json.dumps({"model": "qwen-turbo", "messages": [{"role": "user", "content": prompt}],
                           "max_tokens": 400, "temperature": 0.3}).encode()
        req = urllib.request.Request("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            data=data, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        result = _json.loads(resp.read())
        answer = result["choices"][0]["message"]["content"]

        import re
        match = re.search(r'\{.*\}', answer, re.DOTALL)
        ecn = _json.loads(match.group()) if match else {}
        return {
            "ecn_number": f"ECN-{datetime.now().strftime('%Y%m%d%H%M')}",
            "title": ecn.get("title", "BOM变更通知"),
            "change_description": ecn.get("change_description", diff_text[:200]),
            "affected_items": {"added": len(only_b), "removed": len(only_a), "common": len(common_keys)},
            "impact": ecn.get("impact", ""),
            "approval_level": ecn.get("approval_level", "常规"),
            "source": "ai"
        }
    except Exception as e:
        return {
            "ecn_number": f"ECN-{datetime.now().strftime('%Y%m%d%H%M')}",
            "title": f"{name_a} → {name_b} BOM变更",
            "change_description": f"新增{len(only_b)}项，删除{len(only_a)}项",
            "affected_items": {"added": len(only_b), "removed": len(only_a), "common": len(common_keys)},
            "impact": f"(AI分析失败: {str(e)[:50]})",
            "approval_level": "常规",
            "source": "rule"
        }


# ═══════════ BOM File Attachments ═══════════
import shutil
from fastapi.responses import FileResponse, Response

ATTACH_DIR = os.path.join(settings.UPLOAD_DIR, "bom_files")
ATTACH_META = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bom_attachments.json")
os.makedirs(ATTACH_DIR, exist_ok=True)


def _load_att():
    return safe_load(ATTACH_META, [])


def _save_att(data):
    safe_save(ATTACH_META, data)


def _resolve_att_path(a):
    """返回附件实际文件路径。stored_path 是上传时的绝对路径,uploads 目录
    迁移到 NAS 后可能失效,此时按 stored_name（相对文件名）在 ATTACH_DIR 重建。"""
    path = a.get("stored_path", "")
    if path and os.path.exists(path):
        return path
    stored = a.get("stored_name", "")
    if stored:
        cand = os.path.join(ATTACH_DIR, os.path.basename(stored))
        if os.path.exists(cand):
            return cand
    fname = a.get("filename", "")
    if fname and os.path.isdir(ATTACH_DIR):
        for f in os.listdir(ATTACH_DIR):
            if fname in f or f.endswith(fname):
                return os.path.join(ATTACH_DIR, f)
    return path


@router.post("/{list_id}/files")
async def bom_upload_files(list_id: str, files: list[UploadFile] = File(...), _user=Depends(get_current_user)):
    """Upload attachment files to a BOM list."""
    attachments = _load_att()
    uploaded = []
    for f in files:
        fid = _new_att_id(attachments)
        ext = os.path.splitext(f.filename or "")[1]
        stored = f"{list_id}_{fid}_{int(datetime.now().timestamp())}{ext}"
        stored_path = os.path.join(ATTACH_DIR, stored)
        content = await f.read()
        with open(stored_path, "wb") as fh:
            fh.write(content)
        att = {
            "id": fid, "list_id": list_id,
            "filename": f.filename, "size": len(content),
            "stored_path": stored_path, "stored_name": stored,
            "uploaded_at": datetime.now().isoformat(),
        }
        attachments.append(att)
        uploaded.append(att)
    _save_att(attachments)
    return {"ok": True, "files": uploaded}


@router.get("/{list_id}/files")
def bom_list_files(list_id: str, _user=Depends(get_current_user)):
    """List attachment files for a BOM list."""
    return [a for a in _load_att() if a.get("list_id") == list_id]


@router.get("/{list_id}/files/{file_id}/download")
def bom_download_file(list_id: str, file_id: int, _user=Depends(get_current_user)):
    """Download a BOM attachment file."""
    for a in _load_att():
        if a.get("list_id") == list_id and a.get("id") == file_id:
            path = _resolve_att_path(a)
            if path and os.path.exists(path):
                return FileResponse(path, filename=a.get("filename", "download"), media_type="application/octet-stream")
            raise HTTPException(404, "文件已丢失")
    raise HTTPException(404, "文件不存在")


@router.get("/{list_id}/files/{file_id}/preview")
def bom_preview_file(list_id: str, file_id: int, _user=Depends(get_current_user)):
    """Preview a BOM attachment inline (images, PDFs, Excel, Word, text)."""
    for a in _load_att():
        if a.get("list_id") == list_id and a.get("id") == file_id:
            path = _resolve_att_path(a)
            if not path or not os.path.exists(path):
                raise HTTPException(404, "文件已丢失")
            fn = (a.get("filename", "") or "").lower()
            mime_map = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
                ".bmp": "image/bmp", ".ico": "image/x-icon",
                ".pdf": "application/pdf",
                ".txt": "text/plain; charset=utf-8", ".csv": "text/csv; charset=utf-8",
                ".json": "application/json", ".xml": "application/xml",
                ".html": "text/html", ".htm": "text/html",
                ".mp4": "video/mp4", ".webm": "video/webm",
            }
            for ext, mime in mime_map.items():
                if fn.endswith(ext):
                    return FileResponse(path, media_type=mime)
            # Excel → HTML table
            if fn.endswith((".xlsx", ".xls")):
                try:
                    html = _excel_to_html(path, fn)
                    return Response(content=html, media_type="text/html; charset=utf-8")
                except Exception as e:
                    return Response(content=f"<p style='color:red'>Excel预览失败: {e}</p>", media_type="text/html; charset=utf-8")
            # Word → text
            if fn.endswith(".docx"):
                try:
                    text = _docx_to_text(path)
                    html = f"<pre style='font-family:monospace;white-space:pre-wrap;padding:16px'>{text}</pre>"
                    return Response(content=html, media_type="text/html; charset=utf-8")
                except Exception as e:
                    return Response(content=f"<p style='color:red'>Word预览失败: {e}</p>", media_type="text/html; charset=utf-8")
            return FileResponse(path, filename=a.get("filename", "download"), media_type="application/octet-stream")
    raise HTTPException(404, "文件不存在")


@router.post("/{list_id}/files/{file_id}/import")
def bom_import_from_attachment(list_id: str, file_id: int, _user=Depends(get_current_user)):
    """Parse a saved attachment (Excel/CSV) and import its data into the BOM list."""
    atts = _load_att()
    att = next((a for a in atts if a.get("list_id") == list_id and a.get("id") == file_id), None)
    if not att:
        raise HTTPException(404, "附件不存在")
    path = _resolve_att_path(att)
    if not path or not os.path.exists(path):
        raise HTTPException(404, "文件已丢失")
    fn = (att.get("filename", "") or "").lower()

    # Read file
    with open(path, "rb") as fh:
        content = fh.read()

    # Parse
    rows = None
    if fn.endswith((".xlsx", ".xls")):
        rows, _ = _try_excel(content)
    if not rows and fn.endswith(".csv"):
        rows = _try_csv(content, fn)
    if not rows:
        # Also try CSV for non-.csv files
        rows = _try_csv(content, fn)

    if not rows or len(rows) < 1:
        raise HTTPException(400, detail="无法解析文件内容")

    headers = [str(c).strip() for c in rows[0]]
    data_rows = []
    for row in rows[1:]:
        if not any(str(c).strip() for c in row):
            continue
        data_rows.append([str(c).strip() if c else "" for c in row])

    # Update the BOM list's items
    items = _load()
    for bom in items:
        if str(bom.get("id")) == str(list_id):
            bom["headers"] = headers
            bom["items"] = data_rows
            bom["item_count"] = len(data_rows)
            bom["source_file"] = att.get("filename", "")
            bom["updated_at"] = datetime.utcnow().isoformat()
            _save(items)
            return {"ok": True, "item_count": len(data_rows), "headers": headers}
    raise HTTPException(404, "BOM清单不存在")


@router.delete("/{list_id}/files/{file_id}")
def bom_delete_file(list_id: str, file_id: int, _user=Depends(get_current_user)):
    """Delete a BOM attachment."""
    atts = _load_att()
    for a in atts:
        if a.get("list_id") == list_id and a.get("id") == file_id:
            path = a.get("stored_path", "")
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
            atts.remove(a)
            _save_att(atts)
            return {"ok": True}
    raise HTTPException(404, "文件不存在")


def _new_att_id(attachments):
    return max([a.get("id", 0) for a in attachments], default=0) + 1


def _excel_to_html(path, fn):
    """Convert Excel file to HTML table for preview."""
    sheets = []
    if fn.endswith(".xls"):
        try:
            import xlrd
            wb = xlrd.open_workbook(path)
            for si in range(wb.nsheets):
                sh = wb.sheet_by_index(si)
                rows = [[str(sh.cell_value(r, c) or "") for c in range(sh.ncols)] for r in range(sh.nrows)]
                if rows: sheets.append((sh.name, rows))
        except ImportError:
            return "<p style='color:red'>预览 .xls 需要 xlrd: pip install xlrd</p>"
        except Exception as e:
            return f"<p style='color:red'>解析失败: {e}</p>"
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        for ws_name in wb.sheetnames:
            ws = wb[ws_name]
            rows = [[str(c or "") for c in row] for row in ws.iter_rows(values_only=True)]
            if rows: sheets.append((ws_name, rows))
    if not sheets:
        return "<p>空工作簿</p>"
    parts = []
    for ws_name, rows in sheets:
        max_cols = max(len(r) for r in rows)
        h = f'<h3 style="margin:10px 0 4px;font-family:sans-serif">📊 {ws_name}</h3>\n'
        h += '<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:12px;font-family:sans-serif">\n'
        for ri, row in enumerate(rows):
            tag = "th" if ri == 0 else "td"
            bg = ' style="background:#e8f0fe;font-weight:bold"' if ri == 0 else ""
            cells = [f"<{tag}{bg}>{row[c] if c < len(row) else ''}</{tag}>" for c in range(max_cols)]
            h += "<tr>" + "".join(cells) + "</tr>\n"
        h += "</table>\n"
        parts.append(h)
    return f"<html><body style='padding:12px'>{''.join(parts)}</body></html>"


def _docx_to_text(path):
    """Extract text from .docx."""
    try:
        import docx
        doc = docx.Document(path)
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paras) if paras else "(文档无文字)"
    except ImportError:
        return "(需要 python-docx: pip install python-docx)"
