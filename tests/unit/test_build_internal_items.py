"""build_internal_items 落位计算: 21 项识别物料按类别归组、组溢出进主材、示例行保留、零件图号防幻觉。

rows 为按组紧凑拼接(0-indexed): 半成品 0-4 / 主材 5-17 / 标准件 18-27 / 辅材 28-35。
"""
import pytest

from backend_v2.routes.bom_lists import build_internal_items, _PN_DROP

HALF, MAIN, STD, AUX = 5, 13, 10, 8  # 各组容量


def _item(name, cat, position="", code="", spec="", unit="", qty=""):
    return {"category": cat, "name": name, "position": position,
            "code": code, "spec": spec, "unit": unit, "qty": qty, "note": ""}


def _span(start, n):
    return range(start, start + n)


def test_21_items_placement(template_meta):
    """半成品4 + 标准件9 + 辅材8 = 21 项全部落入对应组, 序号连续, 余位留空。"""
    recognized = (
        [_item(f"半成品{i}", "半成品") for i in range(4)] +
        [_item(f"标准件{i}", "成品") for i in range(9)] +
        [_item(f"辅材{i}", "辅料") for i in range(8)]
    )
    rows = build_internal_items(template_meta, recognized)
    assert len(rows) == HALF + MAIN + STD + AUX
    names = [r[3] for r in rows]
    # 半成品 4 项占 0-3, 余 1 空占位; 主材 13 行全空; 标准件 9 项占 18-26, 余 1 空占位; 辅材 8 项占满
    assert names[:4] == [f"半成品{i}" for i in range(4)]
    assert names[4] == ""
    assert names[5:5 + MAIN] == [""] * MAIN
    assert names[5 + MAIN:5 + MAIN + 9] == [f"标准件{i}" for i in range(9)]
    assert names[5 + MAIN + 9] == ""
    assert names[5 + MAIN + 9 + 1:] == [f"辅材{i}" for i in range(8)]
    seq = [r[1] for r in rows]
    assert seq == [str(i) for i in range(1, len(rows) + 1)]


def test_group_overflow_goes_to_materials(template_meta):
    """半成品 6 项(容量 5) → 溢出 1 项进主材首行, 不丢失。"""
    recognized = [_item(f"半成品{i}", "半成品") for i in range(6)]
    rows = build_internal_items(template_meta, recognized)
    names = [r[3] for r in rows]
    assert names[5].startswith("半成品"), f"溢出项未进主材首行: {names[5]}"
    assert names[5] == "半成品5"


def test_overflow_fits_materials_capacity(template_meta):
    """溢出 13 项 ≤ 主材容量 13 → 全部收下。"""
    recognized = [_item(f"半成品{i}", "半成品") for i in range(5 + 13)]
    rows = build_internal_items(template_meta, recognized)
    names = [r[3] for r in rows]
    assert names[:5] == [f"半成品{i}" for i in range(5)]
    mats = names[5:5 + MAIN]
    assert mats == [f"半成品{i}" for i in range(5, 18)]


def test_empty_recognized_keeps_example_rows(template_meta):
    """无识别结果 → 半成品保留模板示例行, 其余组全空行。"""
    rows = build_internal_items(template_meta, [])
    names = [r[3] for r in rows]
    assert any(names[:HALF]), "半成品区应有示例行"
    assert all(n == "" for n in names[HALF:]), "主材/标准件/辅材应为空占位行"


def test_pure_number_part_no_dropped(template_meta):
    """零件图号防幻觉: 纯数字/序号/尺寸置空, 真实图号保留。"""
    recognized = [
        _item("带数字", "成品", position="1"),
        _item("带尺寸", "成品", position="200×100"),
        _item("带列表", "成品", position="1,2,3"),
        _item("真图号", "成品", position="ZN-2026-0001"),
        _item("轴承", "成品", position="6204-2RS"),
    ]
    rows = build_internal_items(template_meta, recognized)
    names = {r[3]: r[4] for r in rows if r[3]}
    assert names["带数字"] == "" and names["带尺寸"] == "" and names["带列表"] == ""
    assert names["真图号"] == "ZN-2026-0001"
    assert names["轴承"] == "6204-2RS"


def test_unknown_category_falls_to_aux(template_meta):
    """未知类别兜底到辅材组。"""
    rows = build_internal_items(template_meta, [_item("未知料", "其他类别")])
    names = [r[3] for r in rows]
    assert "未知料" in names[HALF + MAIN + STD:]


def test_default_unit_and_qty(template_meta):
    """unit/qty 缺省: pcs / 1。"""
    rows = build_internal_items(template_meta, [_item("料", "成品")])
    r = next(r for r in rows if r[3] == "料")
    assert r[6] == "pcs" and r[7] == "1"


def test_pn_drop_regex():
    assert _PN_DROP.fullmatch("1")
    assert _PN_DROP.fullmatch("1,2,3")
    assert _PN_DROP.fullmatch("200×100")
    assert _PN_DROP.fullmatch("  5  ")
    assert not _PN_DROP.fullmatch("ZN-2026-0001")
    assert not _PN_DROP.fullmatch("6204-2RS")
    assert not _PN_DROP.fullmatch("M10×30")
    assert not _PN_DROP.fullmatch("C1,R2")
