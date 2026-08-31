"""_parse_internal_template 基线: 公司模板(51行×11列, 27个合并单元格)的解析结果固化。
任何改动导致 value 单元格/分组行/列映射偏移都会在此暴露。"""
import pytest


def test_title_and_sheet_names(template_meta):
    assert "材料清单" in template_meta["title"]
    assert template_meta["main_sheet"] == "BOM"
    assert any("定子半成品" in s for s in template_meta["sheets"])


def test_group_starts_baseline(template_meta):
    """0-indexed 分组标签行: 半成品10 主材16 标准件30 辅材41 → 物料首行 11/17/31/42(1-indexed)。"""
    starts = template_meta["group_starts"]
    assert starts == {"半成品": 11, "主材": 17, "标准件": 31, "辅材": 42}, starts


def test_group_rows_baseline(template_meta):
    """每组物料行数: 5/13/10/8(辅材末行注释行不计入)。"""
    gr = template_meta["group_rows"]
    assert gr == {"半成品": 5, "主材": 13, "标准件": 10, "辅材": 8}, gr


def test_col_map_baseline(template_meta):
    cm = template_meta["col_map"]
    assert cm["name"] is not None and cm["code"] is not None
    assert cm["part_no"] is not None
    assert cm["qty"] is not None and cm["unit"] is not None


def test_info_fields_present(template_meta):
    """表头信息区字段应覆盖模板的 17 个关键字段。"""
    labels = [f["label"] for f in template_meta["info_fields"]]
    for kw in ("产品名称", "条形码", "当前版本", "编制时间", "客户名称", "总装图",
               "电机编号", "外形图", "定子组件", "转子组件", "特殊要求"):
        assert any(kw in lbl for lbl in labels), f"缺少字段: {kw}"


def test_info_fields_have_value_cells(template_meta):
    """每个信息字段都要推导出值单元格坐标(生成时回填位置)。"""
    for f in template_meta["info_fields"]:
        assert f.get("value_row") is not None and f.get("value_col") is not None, f
        assert "row" in f and "col" in f


def test_info_fields_no_label_value_confusion(template_meta):
    """预填值推导不能把相邻 label 当成值(之前 bug: 产品名称/规格 的值变成 条形码...)。"""
    for f in template_meta["info_fields"]:
        dv = f.get("default", "")
        if dv:
            assert len(dv) <= 40, f"默认值异常长: {f['label']} -> {dv}"
            assert not any(kw in dv for kw in ("名称", "编码", "型号", "图号", "条形码", "版本", "编号")), \
                f"label 被误当默认值: {f['label']} -> {dv}"


def test_notes_preserved(template_meta):
    """说明文字(特殊要求说明整行等)应保留。"""
    assert template_meta["notes"], "模板说明文字未解析到"


def test_example_rows_from_subsheet(template_meta):
    """半成品示例行应来自子 sheet(带真实物料)。"""
    assert template_meta["example_rows"], "未解析到半成品示例行"
    ex = template_meta["example_rows"][0]
    assert ex["name"] and ex["unit"] and ex["qty"]


def test_reject_wrong_format(template_bytes):
    from backend_v2.routes.bom_lists import _parse_internal_template
    with pytest.raises(Exception):
        _parse_internal_template(b"not an excel", "template.txt")


def test_reject_without_header():
    from backend_v2.routes.bom_lists import _parse_internal_template
    import xlwt, io
    wb = xlwt.Workbook()
    ws = wb.add_sheet("S")
    ws.write(0, 0, "无表头内容")
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(Exception):
        _parse_internal_template(buf.getvalue(), "bad.xls")
