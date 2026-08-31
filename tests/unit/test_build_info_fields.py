"""build_info_fields 表头自动填充: 总装图图号/条形码/版本/编制时间/生产商/设计人员。"""
import re
from datetime import datetime

from backend_v2.routes.bom_lists import build_info_fields


def _by_label(fields, kw):
    return [f for f in fields if kw in f.get("label", "")]


def test_company_extracted_from_title(template_meta):
    fields = build_info_fields(template_meta)
    std = [f for f in fields if f["type"] == "std"]
    assert any("浙江新能" in f.get("value", "") for f in std), std


def test_designer_falls_back_to_username(template_meta):
    fields = build_info_fields(template_meta, username="admin", member_name="")
    std = [f for f in fields if f["type"] == "std" and "设计" in f.get("label", "")]
    assert std and std[0]["value"] == "admin"


def test_designer_prefers_member_name(template_meta):
    fields = build_info_fields(template_meta, username="admin", member_name="王设计")
    std = [f for f in fields if f["type"] == "std" and "设计" in f.get("label", "")]
    assert std and std[0]["value"] == "王设计"


def test_fig_no_format(template_meta):
    """总装图图号: ZN-YYYYMMDD-流水4位。"""
    fields = build_info_fields(template_meta)
    figs = _by_label(fields, "总装图")
    assert figs, "模板应有总装图字段"
    val = figs[0]["value"]
    assert re.fullmatch(r"ZN-\d{8}-\d{4}", val), val
    assert val[3:11] == datetime.now().strftime("%Y%m%d")


def test_barcode_format(template_meta):
    """条形码: 年2位+月2位+流水4位 = 8 位。"""
    fields = build_info_fields(template_meta)
    bars = _by_label(fields, "条形码")
    assert bars, "模板应有条形码字段"
    val = bars[0]["value"]
    assert re.fullmatch(r"\d{8}", val), val
    assert val[:4] == datetime.now().strftime("%y%m")


def test_version_default(template_meta):
    fields = build_info_fields(template_meta)
    vers = _by_label(fields, "版本")
    assert vers and vers[0]["value"] in ("V1.0", "")


def test_prepare_date_is_today(template_meta):
    fields = build_info_fields(template_meta)
    dates = _by_label(fields, "时间")
    assert dates, "模板应有编制时间字段"
    assert dates[0]["value"] == datetime.now().strftime("%Y-%m-%d")


def test_notes_included(template_meta):
    fields = build_info_fields(template_meta)
    notes = [f for f in fields if f["type"] == "note"]
    assert notes and all(n["value"] for n in notes)


def test_value_cell_coords_passed_through(template_meta):
    fields = build_info_fields(template_meta)
    for f in fields:
        if f["type"] == "field":
            assert "value_row" in f and "value_col" in f, f
