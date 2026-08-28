"""Product Technology Library — Motor & Motor Control specialties."""
import json, os, io, csv, re, shutil
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from backend_v2.auth import get_current_user
from backend_v2.config import settings
from backend_v2.storage import safe_load, safe_save

router = APIRouter(prefix="/api/product-tech", tags=["product-tech"])
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "product_tech.json")
UPLOAD_DIR = os.path.join(settings.UPLOAD_DIR, "product_tech_files")
ATTACH_META_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "product_tech_attachments.json")

# ── Shared encoding detection ──
ALL_ENCODINGS = [
    "utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030", "big5",
    "utf-16-le", "utf-16-be", "utf-16",
]


def decode_content(content: bytes):
    """Try to decode binary content to text. Uses chardet for auto-detection."""
    # Strip BOM
    if len(content) >= 2:
        if content[:2] == b'\xff\xfe':
            return content[2:].decode("utf-16-le"), "utf-16-le-bom"
        if content[:2] == b'\xfe\xff':
            return content[2:].decode("utf-16-be"), "utf-16-be-bom"
    if len(content) >= 3 and content[:3] == b'\xef\xbb\xbf':
        return content[3:].decode("utf-8"), "utf-8-bom"

    # Try chardet first
    try:
        import chardet
        result = chardet.detect(content)
        enc = result.get("encoding")
        confidence = result.get("confidence", 0)
        if enc and confidence > 0.5 and enc.lower() not in ("latin-1", "cp1252", "iso-8859-1", "ascii"):
            try:
                decoded = content.decode(enc).replace("\x00", "")
                # Verify it has CJK content or recognizable structure
                cjk = len(re.findall(r"[一-鿿]", decoded))
                tabs = decoded.count("\t")
                if (cjk > 0 or tabs > 0) and sum(1 for ch in decoded[:200] if ch.isprintable() or ch in "\t\n\r") / min(len(decoded), 200) > 0.5:
                    return decoded, f"chardet-{enc}"
            except:
                pass
    except ImportError:
        pass

    # Fallback: score-based selection
    null_ratio = sum(1 for b in content if b == 0) / max(len(content), 1)
    if null_ratio > 0.15:
        priority = ["utf-16-le", "utf-16-be", "utf-8-sig", "gbk", "gb18030", "utf-8"]
    else:
        priority = ["utf-8-sig", "gbk", "gb18030", "utf-8", "big5", "utf-16-le"]

    best_text, best_enc = None, "unknown"
    best_score = -1
    for enc in priority + [e for e in ALL_ENCODINGS if e not in priority]:
        try:
            decoded = content.decode(enc).replace("\x00", "")
        except (UnicodeDecodeError, LookupError):
            continue
        cjk = len(re.findall(r"[一-鿿㐀-䶿豈-﫿]", decoded))
        ascii_alnum = len(re.findall(r"[a-zA-Z0-9]", decoded))
        total = max(len(decoded), 1)
        score = (cjk * 5 + ascii_alnum) / total
        if score > best_score and (cjk > 0 or ascii_alnum > 0):
            best_score = score
            best_text = decoded
            best_enc = enc

    if best_text is None or best_score < 0.03:
        # Force GBK then UTF-8 as last resort
        for enc in ["gbk", "gb18030", "utf-8"]:
            try:
                best_text = content.decode(enc).replace("\x00", "")
                best_enc = f"forced-{enc}"
                break
            except:
                continue
    if best_text is None:
        best_text = content.decode("utf-8", errors="replace").replace("\x00", "")
        best_enc = "utf-8-replace"

    return best_text, best_enc

# ── Field definitions per specialty ──
SPECIALTY_FIELDS = {
    "电机专业": {
        "common": [
            ("product_code", "产品编码"),
            ("product_model", "产品型号"),
            ("product_drawing_no", "产品图号"),
            ("motor_type", "电机种类"),
            ("product_line", "产品线"),
            ("status", "状态"),
            ("rated_power", "额定功率"),
            ("rated_voltage", "额定电压"),
            ("rated_speed", "额定转速"),
            ("standard", "参考标准"),
            ("supplier", "供应商"),
            ("notes", "其他"),
        ],
        "product_lines": {
            "主驱电机": [
                ("em_design_no", "电磁方案编号"),
                ("back_emf_coef", "反电势系数(V/krpm)"),
                ("peak_torque", "峰值转矩(Nm)"),
                ("peak_torque_current", "峰值转矩电流(A)"),
                ("peak_torque_speed", "峰值转矩转速(rpm)"),
                ("stack_height", "叠高(mm)"),
                ("winding", "绕组"),
                ("sensor_type", "传感器类型"),
                ("spline_spec", "花键规格"),
                ("mounting_spigot_dia", "接口安装止口直径(mm)"),
                ("mounting_method", "接口安装方式"),
                ("rear_cover_fixing", "后端盖固定"),
                ("brake", "制动器"),
                ("insulation_class", "绝缘等级"),
                ("protection_level", "防护等级"),
            ],
            "辅驱电机": [
                ("product_drawing_no", "产品图号"),
                ("rated_power", "额定功率(kW)"),
                ("rated_speed", "额定转速(rpm)"),
                ("rated_voltage", "额定电压(V)"),
                ("rear_cover", "后端盖"),
                ("temp_wire", "温度线"),
                ("ground_wire", "接地线"),
                ("shaft_dia", "轴伸直径(mm)"),
                ("front_cover_spigot", "前端盖止口(mm)"),
                ("mounting_hole", "安装孔(mm)"),
                ("shaft_rotation", "轴伸转向"),
                ("harness_bracket", "线束固定架"),
            ],
            "空压机": [
                ("rated_power", "额定功率(kW)"),
                ("rated_speed", "额定转速(rpm)"),
                ("rated_voltage", "额定电压(V)"),
                ("rated_current", "额定电流(A)"),
                ("efficiency", "效率(%)"),
                ("cooling_method", "冷却方式"),
                ("protection_level", "防护等级"),
                ("em_design_no", "电磁方案编号"),
                ("winding", "绕组"),
                ("mounting_method", "安装方式"),
                ("weight", "重量(kg)"),
            ],
            "转向泵": [
                ("rated_power", "额定功率(kW)"),
                ("rated_speed", "额定转速(rpm)"),
                ("rated_voltage", "额定电压(V)"),
                ("rated_current", "额定电流(A)"),
                ("efficiency", "效率(%)"),
                ("cooling_method", "冷却方式"),
                ("protection_level", "防护等级"),
                ("em_design_no", "电磁方案编号"),
                ("winding", "绕组"),
                ("mounting_method", "安装方式"),
                ("weight", "重量(kg)"),
            ],
            "工业永磁": [
                ("rated_power", "额定功率(kW)"),
                ("peak_power", "峰值功率(kW)"),
                ("rated_torque", "额定转矩(Nm)"),
                ("peak_torque", "峰值转矩(Nm)"),
                ("rated_speed", "额定转速(rpm)"),
                ("max_speed", "最高转速(rpm)"),
                ("rated_voltage", "额定电压(V)"),
                ("efficiency", "最高效率(%)"),
                ("cooling_method", "冷却方式"),
                ("insulation_class", "绝缘等级"),
                ("protection_level", "防护等级"),
                ("em_design_no", "电磁方案编号"),
                ("winding", "绕组"),
                ("mounting_method", "安装方式"),
                ("weight", "重量(kg)"),
            ],
            "EMB": [
                ("rated_power", "额定功率(kW)"),
                ("rated_torque", "额定转矩(Nm)"),
                ("peak_torque", "峰值转矩(Nm)"),
                ("rated_speed", "额定转速(rpm)"),
                ("rated_voltage", "额定电压(V)"),
                ("rated_current", "额定电流(A)"),
                ("efficiency", "效率(%)"),
                ("cooling_method", "冷却方式"),
                ("protection_level", "防护等级"),
                ("em_design_no", "电磁方案编号"),
                ("winding", "绕组"),
                ("brake", "制动器"),
                ("mounting_method", "安装方式"),
                ("weight", "重量(kg)"),
            ],
            "关节模组": [
                ("rated_power", "额定功率(kW)"),
                ("rated_torque", "额定转矩(Nm)"),
                ("peak_torque", "峰值转矩(Nm)"),
                ("rated_speed", "额定转速(rpm)"),
                ("rated_voltage", "额定电压(V)"),
                ("efficiency", "效率(%)"),
                ("cooling_method", "冷却方式"),
                ("protection_level", "防护等级"),
                ("em_design_no", "电磁方案编号"),
                ("winding", "绕组"),
                ("sensor_type", "传感器类型"),
                ("mounting_method", "安装方式"),
                ("weight", "重量(kg)"),
            ],
            "其他": [
                ("rated_power", "额定功率(kW)"),
                ("rated_torque", "额定转矩(Nm)"),
                ("rated_speed", "额定转速(rpm)"),
                ("rated_voltage", "额定电压(V)"),
                ("rated_current", "额定电流(A)"),
                ("efficiency", "效率(%)"),
                ("cooling_method", "冷却方式"),
                ("protection_level", "防护等级"),
                ("em_design_no", "电磁方案编号"),
                ("winding", "绕组"),
                ("sensor_type", "传感器类型"),
                ("mounting_method", "安装方式"),
                ("weight", "重量(kg)"),
            ],
        },
        "enums": {
            "product_line": ["主驱电机", "辅驱电机", "空压机", "转向泵", "工业永磁", "EMB", "关节模组", "其他"],
            "motor_type": [
                "永磁同步电机(PMSM)",
                "异步电机(IM)",
                "直流无刷电机(BLDC)",
                "直流有刷电机",
                "开关磁阻电机(SRM)",
                "同步磁阻电机(SynRM)",
                "步进电机",
                "直线电机",
                "其他",
            ],
            "status": ["在售", "研发中", "预研"],
        },
    },
    "电机控制专业": {
        "core": [
            ("product_model", "产品型号"),
            ("name", "产品名称"),
            ("product_line", "产品线"),
            ("controller_type", "控制器类型"),
            ("rated_power", "额定功率(kW)"),
            ("rated_voltage", "额定电压(V)"),
            ("rated_current", "额定电流(A)"),
            ("control_method", "控制方式"),
            ("comm_interface", "通信接口"),
            ("switching_freq", "开关频率(kHz)"),
            ("protection_level", "防护等级"),
            ("cooling_method", "冷却方式"),
            ("efficiency", "效率(%)"),
            ("standard", "参考标准"),
            ("supplier", "供应商"),
            ("notes", "备注"),
        ],
        "enums": {
            "product_line": ["主驱控制器", "辅驱控制器", "EMB控制器", "EPS控制器", "工业变频器", "其他"],
            "controller_type": ["MCU", "VCU", "BMS", "OBC", "DC/DC", "多合一", "其他"],
            "status": ["在售", "研发中", "预研"],
        },
    },
}

SPECIALTIES = list(SPECIALTY_FIELDS.keys())


def _load():
    return safe_load(DATA_FILE, [])

def _save(data):
    safe_save(DATA_FILE, data)


def _next_id(data):
    return max((x.get("id", 0) for x in data), default=0) + 1


@router.get("/specialties")
def list_specialties(_user=Depends(get_current_user)):
    """Return specialties with field definitions (per product-line for motor)."""
    result = []
    for s, f in SPECIALTY_FIELDS.items():
        entry = {"value": s, "label": s, "enums": f.get("enums", {})}
        if "common" in f:
            # Motor specialty: common + per-product-line fields
            entry["fields"] = [{"key": k, "label": l} for k, l in f["common"]]
            entry["product_line_fields"] = {
                pl: [{"key": k, "label": l} for k, l in fields]
                for pl, fields in f.get("product_lines", {}).items()
            }
        else:
            entry["fields"] = [{"key": k, "label": l} for k, l in f["core"]]
        result.append(entry)
    return result


@router.get("")
def list_items(
    search: str = Query(None),
    specialty: str = Query(None),
    motor_type: str = Query(None),
    controller_type: str = Query(None),
    product_line: str = Query(None),
    status: str = Query(None),
    _user=Depends(get_current_user),
):
    items = _load()
    if specialty:
        items = [x for x in items if x.get("specialty") == specialty]
    if motor_type:
        items = [x for x in items if x.get("motor_type") == motor_type]
    if controller_type:
        items = [x for x in items if x.get("controller_type") == controller_type]
    if product_line:
        items = [x for x in items if x.get("product_line") == product_line]
    if status:
        items = [x for x in items if x.get("status") == status]
    if search:
        q = search.lower()
        items = [x for x in items if q in json.dumps(x, ensure_ascii=False).lower()]
    return items


@router.get("/stats")
def get_stats(
    specialty: str = Query(None),
    _user=Depends(get_current_user),
):
    items = _load()
    if specialty:
        items = [x for x in items if x.get("specialty") == specialty]
    total = len(items)
    on_sale = sum(1 for x in items if x.get("status") == "在售")
    in_dev = sum(1 for x in items if x.get("status") == "研发中")
    pre_research = sum(1 for x in items if x.get("status") == "预研")
    # Product line breakdown
    from collections import Counter
    line_counts = Counter(x.get("product_line", "其他") or "其他" for x in items)
    type_counts = Counter(x.get("motor_type", "") or x.get("controller_type", "") for x in items)
    return {
        "total": total, "on_sale": on_sale, "in_dev": in_dev, "pre_research": pre_research,
        "product_lines": dict(line_counts.most_common()),
        "motor_types": {k:v for k,v in type_counts.most_common() if k},
    }


@router.post("", status_code=201)
def create_item(data: dict, _user=Depends(get_current_user)):
    items = _load()
    specialty = data.get("specialty", "电机专业")
    if specialty not in SPECIALTIES:
        raise HTTPException(status_code=400, detail=f"专业类别无效: {specialty}")
    # Save ALL fields from request, not just known ones
    item = {
        "id": _next_id(items),
        "specialty": specialty,
        "product_model": data.get("product_model", "") or data.get("product_drawing_no", ""),
        "name": data.get("name", ""),
        "product_code": data.get("product_code", ""),
    }
    # Always preserve product_drawing_no if present
    if data.get("product_drawing_no"):
        item["product_drawing_no"] = data["product_drawing_no"]
    # Fill all known fields from specialty definition
    spec = SPECIALTY_FIELDS.get(specialty, {})
    common_fields = spec.get("common", spec.get("core", []))
    for key, _ in common_fields:
        if key not in item:
            item[key] = str(data.get(key, "")) if data.get(key) else ""
    # Fill product_line specific fields
    pl = data.get("product_line", "")
    for key, _ in spec.get("product_lines", {}).get(pl, []):
        item[key] = str(data.get(key, "")) if data.get(key) else ""
    # Also save any extra fields from request (catch-all)
    for k, v in data.items():
        if k not in item and k not in ("id",):
            item[k] = str(v) if v else ""
    item["created_at"] = datetime.utcnow().isoformat()
    item["updated_at"] = datetime.utcnow().isoformat()
    items.append(item)
    _save(items)
    return item


@router.get("/template")
def download_template(specialty: str = Query("电机专业"), product_line: str = Query(None), _user=Depends(get_current_user)):
    """Download Excel template with product-line-specific fields."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active

    spec = SPECIALTY_FIELDS.get(specialty, {})
    if "common" in spec:
        common = spec["common"]
        pl = product_line or "主驱电机"
        pl_fields = spec.get("product_lines", {}).get(pl, [])

        # 主驱电机: hardcoded exact column order
        if pl == "主驱电机":
            fields = [
                ("product_code", "产品编码"),
                ("rated_power", "额定功率(kW)"),
                ("rated_voltage", "额定电压(V)"),
                ("rated_speed", "额定转速(rpm)"),
                ("product_model", "产品型号"),
                ("em_design_no", "电磁方案编号"),
                ("back_emf_coef", "反电势系数(V/krpm)"),
                ("peak_torque", "峰值转矩(Nm)"),
                ("peak_torque_current", "峰值转矩电流(A)"),
                ("peak_torque_speed", "峰值转矩转速(rpm)"),
                ("stack_height", "叠高(mm)"),
                ("winding", "绕组"),
                ("sensor_type", "传感器类型"),
                ("spline_spec", "花键规格"),
                ("mounting_spigot_dia", "接口安装止口直径(mm)"),
                ("mounting_method", "接口安装方式"),
                ("rear_cover_fixing", "后端盖固定"),
                ("brake", "制动器"),
                ("insulation_class", "绝缘等级"),
                ("protection_level", "防护等级"),
                ("motor_type", "电机种类"),
                ("status", "状态"),
                ("notes", "其他"),
            ]
        # 辅驱电机: hardcoded exact column order
        elif pl == "辅驱电机":
            fields = [
                ("product_code", "产品编码"),
                ("product_drawing_no", "产品图号"),
                ("motor_type", "电机种类"),
                ("rated_power", "额定功率"),
                ("rated_speed", "额定转速"),
                ("rated_voltage", "额定电压"),
                ("rear_cover", "后端盖"),
                ("temp_wire", "温度线"),
                ("ground_wire", "接地线"),
                ("shaft_dia", "轴伸直径"),
                ("front_cover_spigot", "前端盖止口"),
                ("mounting_hole", "安装孔"),
                ("shaft_rotation", "轴伸转向"),
                ("harness_bracket", "线束固定架"),
                ("notes", "其他"),
            ]
            # skip the common+pl_fields concatenation — fields already set
        else:
            fields = common + pl_fields
    else:
        fields = spec.get("core", [])
        pl = specialty

    ws.title = pl[:31]
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="409EFF", end_color="409EFF", fill_type="solid")
    for ci, (_, label) in enumerate(fields, 1):
        cell = ws.cell(row=1, column=ci, value=label)
        cell.font = header_font; cell.fill = header_fill

    sample_defaults = {
        "product_code": "YPS-E50-001", "product_model": "YPS-E50-T01",
        "product_drawing_no": "YPS-E50-A00",
        "motor_type": "永磁同步电机(PMSM)", "product_line": pl,
        "status": "研发中", "rated_power": "200", "rated_voltage": "380",
        "rated_speed": "3000",
        "rear_cover": "止口定位", "temp_wire": "PT100", "ground_wire": "M6",
        "shaft_dia": "28", "front_cover_spigot": "180",
        "mounting_hole": "4-M8", "shaft_rotation": "顺时针", "harness_bracket": "有",
        "standard": "GB/T 18488", "supplier": "", "notes": "",
    }
    for ci, (key, _) in enumerate(fields, 1):
        ws.cell(row=2, column=ci, value=sample_defaults.get(key, ""))

    ws.freeze_panes = "A2"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(buf.read()); tmp_path = tmp.name
    return FileResponse(tmp_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       filename=f"产品技术库_{pl}_导入模板.xlsx")


@router.get("/{item_id}")
def get_item(item_id: int, _user=Depends(get_current_user)):
    items = _load()
    for x in items:
        if x["id"] == item_id:
            # Include attached files
            attachments = _load_attachments()
            x["files"] = [a for a in attachments if a.get("item_id") == item_id]
            return x
    raise HTTPException(status_code=404, detail="产品不存在")


@router.put("/{item_id}")
def update_item(item_id: int, data: dict, _user=Depends(get_current_user)):
    items = _load()
    for x in items:
        if x["id"] == item_id:
            for k in data:
                if k != "id":
                    x[k] = data[k]
            x["updated_at"] = datetime.utcnow().isoformat()
            _save(items)
            return x
    raise HTTPException(status_code=404, detail="条目不存在")


@router.delete("/{item_id}")
def delete_item(item_id: int, _user=Depends(get_current_user)):
    items = _load()
    filtered = [x for x in items if x["id"] != item_id]
    if len(filtered) == len(items):
        raise HTTPException(status_code=404, detail="条目不存在")
    _save(filtered)
    return {"ok": True}


@router.post("/import")
async def import_items(
    file: UploadFile = File(...),
    specialty: str = Form("电机专业"),
    _user=Depends(get_current_user),
):
    """Import product items from file (Excel/CSV/text)."""
    if specialty not in SPECIALTIES:
        raise HTTPException(status_code=400, detail=f"专业类别无效: {specialty}")

    content = await file.read()
    all_rows = []
    excel_ok = False

    # Try Excel parsers
    for parser in ["openpyxl", "xlrd"]:
        try:
            if parser == "openpyxl":
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(content))
                ws = wb.active
                all_rows = [[str(c or "").strip() for c in row] for row in ws.iter_rows(values_only=True)]
            else:
                import xlrd
                wb = xlrd.open_workbook(file_contents=content)
                sh = wb.sheet_by_index(0)
                all_rows = [[str(sh.cell_value(r, c) or "").strip() for c in range(sh.ncols)] for r in range(sh.nrows)]
            excel_ok = True
            break
        except:
            continue

    if not excel_ok:
        null_ratio = sum(1 for b in content if b == 0) / max(len(content), 1)
        encodings = (
            ["utf-16-le", "utf-16-be", "utf-8-sig", "gbk", "gb2312", "gb18030", "utf-8"]
            if null_ratio > 0.15
            else ["utf-8-sig", "gbk", "gb2312", "gb18030", "utf-16-le", "utf-16-be", "utf-8"]
        )
        text = None
        for enc in encodings:
            try:
                text = content.decode(enc).replace("\x00", "")
                sample = text[:200]
                if sum(1 for ch in sample if ch.isprintable() or ch in "\t\n\r") / max(len(sample), 1) > 0.7:
                    break
                text = None
            except:
                continue
        if text is None:
            text = content.decode("utf-8", errors="replace").replace("\x00", "")

        delim = "\t" if text.count("\t") > text.count(",") else ","
        try:
            reader = csv.reader(io.StringIO(text), delimiter=delim)
            all_rows = list(reader)
        except:
            for line in text.strip().split("\n"):
                all_rows.append([c.strip() for c in line.split(delim)])

    if not all_rows:
        raise HTTPException(status_code=400, detail="文件为空或无法识别")

    # Build header map for current specialty
    field_aliases = {
        "product_code": ["产品编码", "编码", "code"],
        "product_model": ["产品型号", "型号", "model"],
        "product_drawing_no": ["产品图号", "图号", "drawing"],
        "name": ["产品名称", "名称", "name", "产品"],
        "motor_type": ["电机种类", "电机类型", "种类", "motor_type", "类型"],
        "product_line": ["产品线", "产品系列", "product_line", "系列"],
        "status": ["状态", "status", "阶段"],
        "rated_power": ["额定功率", "功率", "power", "额定功率(kW)"],
        "rated_voltage": ["额定电压", "电压", "voltage", "额定电压(V)"],
        "rated_speed": ["额定转速", "转速", "speed", "额定转速(rpm)"],
        "rated_torque": ["额定转矩", "转矩", "torque", "额定转矩(Nm)"],
        "peak_power": ["峰值功率", "peak_power"],
        "peak_torque": ["峰值转矩", "peak_torque", "峰值转矩(Nm)"],
        "peak_torque_current": ["峰值转矩电流", "峰值转矩电流(A)", "peak_torque_current"],
        "peak_torque_speed": ["峰值转矩转速", "峰值转矩转速(rpm)", "peak_torque_speed"],
        "max_speed": ["最高转速", "max_speed", "最高转速(rpm)"],
        "rated_current": ["额定电流", "电流", "current", "额定电流(A)"],
        "poles": ["极数", "poles", "极对数"],
        "cooling_method": ["冷却方式", "冷却", "cooling"],
        "protection_level": ["防护等级", "防护", "IP", "protection"],
        "insulation_class": ["绝缘等级", "绝缘", "insulation"],
        "efficiency": ["效率", "efficiency", "效率(%)", "最高效率(%)"],
        "weight": ["重量", "weight", "重量(kg)"],
        "dimensions": ["外形尺寸", "尺寸", "dimensions"],
        "controller_type": ["控制器类型", "控制器", "controller"],
        "control_method": ["控制方式", "控制", "control"],
        "comm_interface": ["通信接口", "通信", "接口", "CAN", "通讯"],
        "switching_freq": ["开关频率", "频率", "switching", "开关频率(kHz)"],
        "duty_cycle": ["工作制", "duty_cycle"],
        "noise_level": ["噪声", "noise", "噪声(dB)"],
        "back_emf_coef": ["反电势系数", "back_emf", "反电势系数(V/krpm)"],
        "stack_height": ["叠高", "stack", "叠高(mm)"],
        "winding": ["绕组", "winding"],
        "sensor_type": ["传感器类型", "sensor", "传感器"],
        "spline_spec": ["花键规格", "spline", "花键"],
        "mounting_spigot_dia": ["止口直径", "spigot", "止口直径(mm)"],
        "mounting_method": ["安装方式", "安装", "mounting"],
        "mounting_hole": ["安装孔", "安装孔(mm)"],
        "brake": ["制动器", "brake", "制动"],
        "rear_cover": ["后端盖", "rear_cover"],
        "temp_wire": ["温度线", "temp_wire"],
        "ground_wire": ["接地线", "ground_wire"],
        "shaft_dia": ["轴伸直径", "shaft", "轴伸直径(mm)"],
        "shaft_rotation": ["轴伸转向", "rotation", "转向"],
        "front_cover_spigot": ["前端盖止口", "front_cover", "前端盖止口(mm)"],
        "harness_bracket": ["线束固定架", "harness", "线束架"],
        "em_design_no": ["电磁方案编号", "em_design", "电磁方案"],
        "standard": ["参考标准", "标准", "standard"],
        "supplier": ["供应商", "supplier", "来源", "厂商"],
        "notes": ["备注", "notes", "说明", "remark", "其他"],
    }

    hdr_row = all_rows[0]
    try_headers = [str(c).strip() for c in hdr_row]

    def _clean(s):
        return re.sub(r"[^\w一-鿿]+", "", str(s)).lower()

    col_map = {}
    for i, h in enumerate(try_headers):
        if not h: continue
        h_clean = _clean(h)
        for field, aliases in field_aliases.items():
            if field in col_map: continue
            for alias in aliases:
                a_clean = _clean(alias)
                if a_clean == h_clean or (len(a_clean) >= 2 and a_clean in h_clean) or (len(h_clean) >= 2 and h_clean in a_clean):
                    col_map[field] = i
                    break

    has_header = len(col_map) >= 1
    if not has_header:
        pos_fields = ["product_model", "name", "motor_type", "product_line", "status",
                       "rated_power", "rated_voltage", "rated_speed"]
        for pi, pf in enumerate(pos_fields):
            if pi < len(try_headers): col_map[pf] = pi
    data_rows = all_rows[1:] if len(all_rows) > 1 else []
    headers = try_headers

    items = _load()
    count = 0
    for row in data_rows:
        if not row or all(not c for c in row if c):
            continue

        def _val(field):
            if field in col_map and col_map[field] < len(row):
                v = str(row[col_map[field]]).strip()
                return v if v and v.lower() not in ("none", "nan", "null") else ""
            return ""

        product_model = _val("product_model") or _val("product_drawing_no") or _val("product_code")
        name = _val("name")
        if not product_model and not name:
            continue

        product_line = _val("product_line")
        item = {
            "id": _next_id(items),
            "specialty": specialty,
            "product_model": product_model,
            "name": name,
            "product_line": product_line,
        }
        # Fill common fields
        spec = SPECIALTY_FIELDS.get(specialty, {})
        for key, _ in spec.get("common", spec.get("core", [])):
            if key not in ("product_model", "name", "product_drawing_no"):
                item[key] = _val(key)
        # Fill product_line specific fields
        if product_line and "product_lines" in spec:
            for key, _ in spec["product_lines"].get(product_line, []):
                item[key] = _val(key)
        item["created_at"] = datetime.utcnow().isoformat()
        item["updated_at"] = datetime.utcnow().isoformat()
        items.append(item)
        count += 1

    if not count:
        raise HTTPException(status_code=400, detail="未识别到有效产品记录。请确保文件包含'产品型号'或'产品图号'或'产品名称'列。")

    _save(items)
    return {"ok": True, "count": count, "specialty": specialty}


# ── File Attachments ──

def _load_attachments():
    return safe_load(ATTACH_META_FILE, [])

def _save_attachments(data):
    safe_save(ATTACH_META_FILE, data)


def _next_attach_id(data):
    return max((x.get("id", 0) for x in data), default=0) + 1


@router.get("/{item_id}/files")
def list_files(item_id: int, _user=Depends(get_current_user)):
    attachments = _load_attachments()
    return [a for a in attachments if a.get("item_id") == item_id]


@router.post("/{item_id}/files")
async def upload_files(
    item_id: int,
    files: list[UploadFile] = File(...),
    _user=Depends(get_current_user),
):
    attachments = _load_attachments()
    results = []
    for file in files:
        aid = _next_attach_id(attachments)
        safe_name = f"{item_id}_{aid}_{file.filename}"
        dest_dir = os.path.join(UPLOAD_DIR, str(item_id))
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, safe_name)
        content = await file.read()
        with open(dest_path, "wb") as f:
            f.write(content)
        attach = {
            "id": aid,
            "item_id": item_id,
            "filename": file.filename,
            "size": len(content),
            "stored_path": dest_path,
            "uploaded_at": datetime.utcnow().isoformat(),
        }
        attachments.append(attach)
        results.append({"id": aid, "filename": file.filename, "size": len(content)})
    _save_attachments(attachments)
    return {"ok": True, "files": results}


@router.delete("/{item_id}/files/{file_id}")
def delete_file(item_id: int, file_id: int, _user=Depends(get_current_user)):
    attachments = _load_attachments()
    target = None
    for a in attachments:
        if a.get("item_id") == item_id and a.get("id") == file_id:
            target = a
            break
    if not target:
        raise HTTPException(status_code=404, detail="文件不存在")

    # Remove physical file
    try:
        if os.path.exists(target.get("stored_path", "")):
            os.remove(target.get("stored_path"))
    except:
        pass

    new_list = [a for a in attachments if not (a.get("item_id") == item_id and a.get("id") == file_id)]
    _save_attachments(new_list)
    # Clean up empty dir
    item_dir = os.path.join(UPLOAD_DIR, str(item_id))
    try:
        if os.path.isdir(item_dir) and not os.listdir(item_dir):
            os.rmdir(item_dir)
    except:
        pass
    return {"ok": True}


@router.get("/{item_id}/files/{file_id}/download")
def download_file(item_id: int, file_id: int, _user=Depends(get_current_user)):
    attachments = _load_attachments()
    for a in attachments:
        if a.get("item_id") == item_id and a.get("id") == file_id:
            path = a.get("stored_path", "")
            if os.path.exists(path):
                return FileResponse(path, filename=a.get("filename", "download"), media_type="application/octet-stream")
            raise HTTPException(status_code=404, detail="文件已丢失")
    raise HTTPException(status_code=404, detail="文件不存在")


@router.get("/{item_id}/files/{file_id}/preview")
def preview_file(item_id: int, file_id: int, _user=Depends(get_current_user)):
    """Serve file inline for browser preview (images, PDFs, text, Excel, Word)."""
    attachments = _load_attachments()
    for a in attachments:
        if a.get("item_id") == item_id and a.get("id") == file_id:
            path = a.get("stored_path", "")
            if not os.path.exists(path):
                raise HTTPException(status_code=404, detail="文件已丢失")
            fn = (a.get("filename", "") or "").lower()
            # Map common extensions to inline MIME types
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

            # Excel → HTML table preview
            if fn.endswith((".xlsx", ".xls")):
                try:
                    html = _excel_to_html(path, fn)
                    return Response(content=html, media_type="text/html; charset=utf-8")
                except Exception as e:
                    return Response(content=f"<p style='color:red'>Excel预览失败: {e}</p>", media_type="text/html; charset=utf-8")

            # Word .docx → text extraction
            if fn.endswith(".docx"):
                try:
                    text = _docx_to_text(path)
                    html = f"<pre style='font-family:monospace;white-space:pre-wrap;padding:16px'>{text}</pre>"
                    return Response(content=html, media_type="text/html; charset=utf-8")
                except Exception as e:
                    return Response(content=f"<p style='color:red'>Word预览失败: {e}</p>", media_type="text/html; charset=utf-8")

            # Default: force download for unknown types
            return FileResponse(path, filename=a.get("filename", "download"), media_type="application/octet-stream")
    raise HTTPException(status_code=404, detail="文件不存在")


def _excel_to_html(path, fn):
    """Convert Excel file to a simple HTML table."""
    sheets_html = []
    rows_by_sheet = []

    if fn.endswith(".xls"):
        # Old format → try xlrd
        try:
            import xlrd
            wb = xlrd.open_workbook(path)
            for si in range(wb.nsheets):
                sh = wb.sheet_by_index(si)
                rows = [[str(sh.cell_value(r, c) or "") for c in range(sh.ncols)] for r in range(sh.nrows)]
                if rows:
                    rows_by_sheet.append((sh.name, rows))
        except ImportError:
            return "<p style='color:red'>预览 .xls 需要 xlrd 库: pip install xlrd</p>"
        except Exception as e:
            return f"<p style='color:red'>解析 .xls 失败: {e}</p>"
    else:
        # .xlsx → openpyxl
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        for ws_name in wb.sheetnames:
            ws = wb[ws_name]
            rows = [[str(c or "") for c in row] for row in ws.iter_rows(values_only=True)]
            if rows:
                rows_by_sheet.append((ws_name, rows))

    for ws_name, rows in rows_by_sheet:
        if not rows:
            continue
        max_cols = max(len(r) for r in rows)
        html = f'<h3 style="margin:12px 0 4px;font-family:sans-serif">📊 {ws_name}</h3>\n<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:12px;font-family:sans-serif">\n'
        for ri, row in enumerate(rows):
            tag = "th" if ri == 0 else "td"
            bg = ' style="background:#e8f0fe;font-weight:bold"' if ri == 0 else ""
            cells = []
            for c in range(max_cols):
                v = row[c] if c < len(row) else ""
                cells.append(f"<{tag}{bg}>{v}</{tag}>")
            html += "<tr>" + "".join(cells) + "</tr>\n"
        html += "</table>\n"
        sheets_html.append(html)
    if not sheets_html:
        return "<p>空工作簿</p>"
    return f"<html><body style='padding:12px'>{''.join(sheets_html)}</body></html>"


def _docx_to_text(path):
    """Extract text from .docx file."""
    try:
        import docx
        doc = docx.Document(path)
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paras) if paras else "(文档无文字内容)"
    except ImportError:
        return "(需要安装 python-docx 才能预览Word文档: pip install python-docx)"


@router.post("/qrcode")
def generate_qrcodes(data: dict, _user=Depends(get_current_user)):
    """Generate QR codes for selected product IDs."""
    import base64
    try:
        import qrcode
    except ImportError:
        raise HTTPException(status_code=500, detail="请先安装依赖: pip install qrcode[pil]")
    ids = data.get("ids", [])
    items = _load()
    results = []
    for item in items:
        if item["id"] in ids:
            label = item.get("product_model") or item.get("name", "N/A")
            try:
                img = qrcode.make(label)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode()
                results.append({"id": item["id"], "label": label, "qr": f"data:image/png;base64,{b64}"})
            except Exception as e:
                results.append({"id": item["id"], "label": label, "error": str(e)})
    return {"ok": True, "results": results}


@router.post("/parse-all")
async def parse_all_products(
    file: UploadFile = File(...),
    specialty: str = Form("电机专业"),
    encoding: str = Form(""),
    _user=Depends(get_current_user),
):
    """Parse ALL products from a file and return extracted fields for preview."""
    content = await file.read()
    all_rows = []
    excel_ok = False

    for parser in ["openpyxl", "xlrd"]:
        try:
            if parser == "openpyxl":
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(content))
                for ws_name in wb.sheetnames:
                    ws = wb[ws_name]
                    rows = [[str(c or "").strip() for c in row] for row in ws.iter_rows(values_only=True)]
                    if rows:
                        all_rows.extend(rows)
            else:
                import xlrd
                wb = xlrd.open_workbook(file_contents=content)
                for si in range(wb.nsheets):
                    sh = wb.sheet_by_index(si)
                    rows = [[str(sh.cell_value(r, c) or "").strip() for c in range(sh.ncols)] for r in range(sh.nrows)]
                    if rows:
                        all_rows.extend(rows)
            excel_ok = True
            break
        except:
            continue

    text_encoding = "excel" if excel_ok else "unknown"
    if not excel_ok:
        if encoding:
            # Manual encoding override
            try:
                text = content.decode(encoding).replace("\x00", "")
                text_encoding = f"manual-{encoding}"
            except:
                raise HTTPException(status_code=400, detail=f"无法使用 {encoding} 解码文件，请尝试其他编码")
        else:
            text, text_encoding = decode_content(content)
        delim = "\t" if text.count("\t") > text.count(",") else ","
        try:
            reader = csv.reader(io.StringIO(text), delimiter=delim)
            all_rows = list(reader)
        except:
            all_rows = [[c.strip() for c in line.split(delim)] for line in text.strip().split("\n")]

    if not all_rows:
        raise HTTPException(status_code=400, detail="文件为空")

    # Build header map
    field_aliases = {
        "product_code": ["产品编码", "编码", "code"],
        "product_model": ["产品型号", "型号", "model"],
        "product_drawing_no": ["产品图号", "图号", "drawing"],
        "name": ["产品名称", "名称", "name", "产品"],
        "motor_type": ["电机种类", "电机类型", "种类", "motor_type"],
        "product_line": ["产品线", "产品系列", "product_line"],
        "status": ["状态", "status"],
        "rated_power": ["额定功率", "功率", "power", "额定功率(kW)"],
        "rated_voltage": ["额定电压", "电压", "voltage", "额定电压(V)"],
        "rated_speed": ["额定转速", "转速", "speed", "额定转速(rpm)"],
        "rated_torque": ["额定转矩", "转矩", "torque", "额定转矩(Nm)"],
        "peak_power": ["峰值功率", "peak_power"],
        "peak_torque": ["峰值转矩", "峰值扭矩", "peak_torque", "峰值转矩(Nm)"],
        "max_speed": ["最高转速", "max_speed", "最高转速(rpm)"],
        "rated_current": ["额定电流", "电流", "current", "额定电流(A)"],
        "em_design_no": ["电磁方案编号", "电磁方案", "em_design"],
        "back_emf_coef": ["反电势系数", "反电势", "back_emf", "V/krpm"],
        "stack_height": ["叠高", "stack_height", "叠厚", "叠高(mm)"],
        "winding": ["绕组", "winding", "线径", "匝数", "并绕"],
        "sensor_type": ["传感器类型", "传感器", "sensor"],
        "spline_spec": ["花键规格", "花键", "spline"],
        "mounting_spigot_dia": ["止口直径", "止口", "spigot", "止口直径(mm)"],
        "mounting_method": ["安装方式", "安装", "mounting"],
        "mounting_hole": ["安装孔", "安装孔(mm)"],
        "brake": ["制动器", "brake", "刹车", "制动"],
        "rear_cover": ["后端盖", "rear_cover"],
        "rear_cover_fixing": ["后端盖固定", "rear_cover_fixing"],
        "temp_wire": ["温度线", "temp_wire"],
        "ground_wire": ["接地线", "ground_wire"],
        "shaft_dia": ["轴伸直径", "shaft", "轴伸直径(mm)"],
        "shaft_rotation": ["轴伸转向", "rotation", "转向"],
        "front_cover_spigot": ["前端盖止口", "front_cover", "前端盖止口(mm)"],
        "harness_bracket": ["线束固定架", "harness", "线束架"],
        "poles": ["极数", "poles"],
        "cooling_method": ["冷却方式", "冷却", "cooling"],
        "protection_level": ["防护等级", "防护", "IP", "protection"],
        "insulation_class": ["绝缘等级", "绝缘", "insulation"],
        "duty_cycle": ["工作制", "duty_cycle"],
        "noise_level": ["噪声", "noise", "噪声(dB)"],
        "efficiency": ["效率", "efficiency", "效率(%)", "最高效率(%)"],
        "weight": ["重量", "weight", "重量(kg)"],
        "dimensions": ["外形尺寸", "尺寸", "dimensions"],
        "controller_type": ["控制器类型", "控制器", "controller"],
        "control_method": ["控制方式", "控制", "control"],
        "comm_interface": ["通信接口", "通信", "CAN", "通讯"],
        "switching_freq": ["开关频率", "频率", "switching"],
        "standard": ["参考标准", "标准", "standard"],
        "supplier": ["供应商", "supplier", "来源", "厂商"],
        "notes": ["备注", "notes", "说明", "remark", "其他"],
    }

    hdr_row = all_rows[0]
    try_headers = [str(c).strip() for c in hdr_row]

    def _clean(s):
        # Remove all non-CJK, non-ASCII-letters, non-digits chars
        return re.sub(r"[^\w一-鿿]+", "", str(s)).lower()

    col_map = {}
    for i, h in enumerate(try_headers):
        if not h:
            continue
        h_clean = _clean(h)
        for field, aliases in field_aliases.items():
            if field in col_map:
                continue
            for alias in aliases:
                a_clean = _clean(alias)
                # Exact match first, then substring match
                if a_clean == h_clean or (len(a_clean) >= 2 and a_clean in h_clean) or (len(h_clean) >= 2 and h_clean in a_clean):
                    col_map[field] = i
                    break

    has_header = len(col_map) >= 1
    if has_header:
        data_rows = all_rows[1:]
    else:
        # Try positional fallback: col0=product_model, col1=name, col2=motor_type, etc
        pos_fields = ["product_model", "name", "motor_type", "product_line", "status",
                       "rated_power", "rated_voltage", "rated_speed"]
        for pi, pf in enumerate(pos_fields):
            if pi < len(try_headers):
                col_map[pf] = pi
        data_rows = all_rows[1:] if len(all_rows) > 1 else []
    headers = try_headers

    if not col_map:
        # Auto-retry with forced GBK/UTF-8
        for retry_enc in ["gbk", "gb18030", "utf-8-sig", "utf-8"]:
            try:
                retry_text = content.decode(retry_enc).replace("\x00", "")
                retry_delim = "\t" if retry_text.count("\t") > retry_text.count(",") else ","
                retry_rows = list(csv.reader(io.StringIO(retry_text), delimiter=retry_delim))
                if retry_rows:
                    retry_hdr = [str(c).strip() for c in retry_rows[0]]
                    retry_map = {}
                    for i, h in enumerate(retry_hdr):
                        if not h: continue
                        h_clean = _clean(h)
                        for field, aliases in field_aliases.items():
                            if field in retry_map: continue
                            for alias in aliases:
                                a_clean = _clean(alias)
                                if a_clean == h_clean or (len(a_clean) >= 2 and a_clean in h_clean) or (len(h_clean) >= 2 and h_clean in a_clean):
                                    retry_map[field] = i
                                    break
                    if len(retry_map) >= 3:
                        col_map = retry_map
                        all_rows = retry_rows
                        text_encoding = f"retry-{retry_enc}"
                        break
            except:
                continue

    if not col_map:
        raise HTTPException(status_code=400, detail=f"未识别到有效列名。文件前5列: {headers[:5]}")

    results = []
    for row in data_rows:
        if not row or all(not c for c in row if c):
            continue
        item = {"specialty": specialty}
        spec = SPECIALTY_FIELDS.get(specialty, {})
        common_fields = spec.get("common", spec.get("core", []))
        for key, _ in common_fields:
            if key in col_map and col_map[key] < len(row):
                v = str(row[col_map[key]]).strip()
                item[key] = v if v and v.lower() not in ("none", "nan", "null") else ""
            else:
                item[key] = ""
        # Also map product_line specific fields
        pl = item.get("product_line", "")
        for key, _ in spec.get("product_lines", {}).get(pl, []):
            if key in col_map and col_map[key] < len(row):
                v = str(row[col_map[key]]).strip()
                item[key] = v if v and v.lower() not in ("none", "nan", "null") else ""
        if item.get("product_model") or item.get("product_drawing_no") or item.get("name"):
            results.append(item)

    # Check if first data row looks garbled
    sample_preview = ""
    if results:
        r0 = results[0]
        sample_preview = f"{r0.get('product_model','')} / {r0.get('rated_power','')}"

    return {
        "ok": True,
        "records": results,
        "total": len(results),
        "headers_found": list(col_map.keys()),
        "encoding": text_encoding,
        "raw_headers": try_headers[:8],
        "sample": sample_preview,
    }


@router.post("/batch-delete")
def batch_delete(data: dict, _user=Depends(get_current_user)):
    ids = set(data.get("ids", []))
    items = _load()
    new_items = [x for x in items if x["id"] not in ids]
    deleted = len(items) - len(new_items)
    # Also clean up attachments
    attachments = _load_attachments()
    new_att = [a for a in attachments if a.get("item_id") not in ids]
    _save_attachments(new_att)
    _save(new_items)
    return {"ok": True, "deleted": deleted}


@router.post("/batch-upload-drawings")
async def batch_upload_drawings(
    files: list[UploadFile] = File(...),
    _user=Depends(get_current_user),
):
    """Batch upload drawings — match to products by filename prefix (product_model)."""
    items = _load()
    attachments = _load_attachments()
    results = []
    for file in files:
        matched = None
        name_no_ext = os.path.splitext(file.filename)[0].strip()
        for item in items:
            pm = (item.get("product_model") or "").strip()
            nm = (item.get("name") or "").strip()
            if pm and (pm in file.filename or name_no_ext in pm or pm in name_no_ext):
                matched = item
                break
            if nm and (nm in file.filename or name_no_ext in nm or nm in name_no_ext):
                matched = item
                break
        if not matched:
            results.append({"filename": file.filename, "ok": False, "msg": "未匹配到产品"})
            continue
        aid = _next_attach_id(attachments)
        safe_name = f"{matched['id']}_{aid}_{file.filename}"
        dest_dir = os.path.join(UPLOAD_DIR, str(matched["id"]))
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, safe_name)
        content = await file.read()
        with open(dest_path, "wb") as f:
            f.write(content)
        attachments.append({
            "id": aid, "item_id": matched["id"], "filename": file.filename,
            "size": len(content), "stored_path": dest_path,
            "uploaded_at": datetime.utcnow().isoformat(),
        })
        results.append({"filename": file.filename, "ok": True, "matched": matched.get("product_model") or matched.get("name")})
    _save_attachments(attachments)
    return {"ok": True, "results": results}
