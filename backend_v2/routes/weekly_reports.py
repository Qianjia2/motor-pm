"""Weekly report CRUD with UPSERT semantics."""
import json
from datetime import date, datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, update, delete, insert, func
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.audit import log_audit
from backend_v2.schemas import WeeklyReportCreate, WeeklyReportUpdate, WeeklyReportLineItem
from backend_v2.models import WeeklyReport, WeeklyReportLine, Project, RiskIssue

router = APIRouter(tags=["reports"])

# Beijing time (UTC+8)
BJT = timezone(timedelta(hours=8))

def _now():
    """Get current datetime in Beijing time."""
    return datetime.now(BJT)

def _today():
    """Get current date in Beijing time."""
    return _now().date()


# ── Excel import helpers ──

def _upsert_report(db, project_id, year, week, rpt_date, overall, accomplishments, line_items):
    """Create or update a weekly report with line items."""
    existing = (db.execute(
        select(WeeklyReport).where(
            WeeklyReport.project_id == project_id,
            WeeklyReport.year == year,
            WeeklyReport.week_number == week,
        )
    )).scalars().one_or_none()

    if existing:
        db.execute(update(WeeklyReport).where(WeeklyReport.id == existing.id).values(
            report_date=rpt_date, overall_progress=overall,
            key_accomplishments=accomplishments,
        ))
        db.execute(delete(WeeklyReportLine).where(WeeklyReportLine.report_id == existing.id))
        report_id = existing.id
    else:
        rpt = WeeklyReport(
            project_id=project_id, year=year, week_number=week,
            report_date=rpt_date, overall_progress=overall,
            key_accomplishments=accomplishments,
            created_at=_now(),
        )
        db.add(rpt)
        db.flush()
        report_id = rpt.id

    for li in line_items:
        li["report_id"] = report_id
        db.add(WeeklyReportLine(**li))
    db.commit()
    return {"id": report_id, "year": year, "week": week}


# ── Excel import ──

PROJECT_NAME_MAP = {
    "西山磁浮手柄": "西山", "电机磁浮": "西山", "微电机磁浮": "西山", "磁浮手柄": "西山",
    "五星CM02": "五星", "CM02": "五星", "ebike集成": "五星",
    "五星CM03": "五星", "CM03": "五星",
    "优普森eVTOL": "优普森", "eVTOL": "优普森", "优普森": "优普森",
    "优普森5-30": "优普森",
    "优普森磁悬浮": "优普森",
    "金浪摩托车": "金浪", "金浪GCU": "金浪", "摩托车GCU": "金浪",
    "晟视": "晟视", "医疗磁悬浮": "晟视", "医疗": "晟视",
}

DISCIPLINE_MAP = {
    "控制算法": 2, "控制软件": 2, "软件": 2, "算法": 2,
    "控制硬件": 3, "电机硬件": 3, "硬件": 3,
    "电机结构": 4, "结构": 4,
    "电机电磁": 5, "电磁": 5,
    "测试验证": 6, "验证": 6, "测试": 6,
}


def _import_csv_data(db, project_id, project_name, rows, results):
    """Parse CSV/TSV rows with auto-detected columns."""
    if len(rows) < 2:
        return 0

    header = [str(c).strip() if c else '' for c in rows[0]]
    # Auto-detect column indices — broad keyword matching
    col_map = {}
    col_text_len = {}  # average text length per column (for fallback heuristics)
    for i, h in enumerate(header):
        if not h:
            continue
        hl = h.lower().replace(' ', '').replace('_', '').replace('-', '').replace('*', '')
        # Compute avg text length for this column (used for fallback)
        lens = [len(str(r[i]).strip()) if i < len(r) and r[i] else 0 for r in rows[1:]]
        col_text_len[i] = sum(lens) / max(len(lens), 1)
        # Broad matching
        if any(k in hl for k in ('技术线', '专业', 'discipline', 'line', '学科', '类别', '分类')):
            col_map['line'] = i
        elif any(k in hl for k in ('本周', 'thisweek', '本周完成', '本周工作', '当周', '当前', '完成情况', '工作内容', '任务内容', '进展', 'progress', 'content', 'work', '任务')):
            col_map['this_week'] = i
        elif any(k in hl for k in ('下周', 'nextweek', '计划', 'plan', '下一步', '后续', '待办')):
            col_map['next_week'] = i
        elif any(k in hl for k in ('阻塞', 'blocker', '问题', 'issue', '难点', '困难', '风险', '备注', 'remark', '障碍')):
            col_map['blocker'] = i
        elif any(k in hl for k in ('负责人', 'coordinator', '责任人', 'owner', '负责', '担当', '姓名', 'name')):
            col_map['coordinator'] = i
        elif any(k in hl for k in ('周次', 'week', '周', '日期', 'date')):
            col_map['week'] = i
        elif any(k in hl for k in ('目标', 'goal', '去哪里', '去向', '目的')):
            col_map['goal'] = i
        elif any(k in hl for k in ('状态', 'status', '进度', '状态')):
            col_map['status'] = i

    # Fallback: if no this_week column found, use the column with the most text
    if 'this_week' not in col_map and col_text_len:
        best = max(col_text_len, key=col_text_len.get)
        if col_text_len[best] > 5:
            col_map['this_week'] = best

    line_items = []
    # For rows without a matched discipline, assign line_id from the available pool
    available_lids = [2, 3, 4, 5, 6]
    lid_idx = 0
    for row in rows[1:]:
        cells = [str(c).strip() if c else '' for c in row]
        if not any(cells):
            continue
        # Try to match line/discipline
        line_id = None
        line_name = cells[col_map['line']] if 'line' in col_map and col_map['line'] < len(cells) else ''
        for dk, dl in DISCIPLINE_MAP.items():
            if dk in line_name:
                line_id = dl
                break
        if line_id is None:
            line_id = available_lids[lid_idx % len(available_lids)]
            lid_idx += 1

        li = {
            'line_id': line_id,
            'goal': cells[col_map['goal']] if 'goal' in col_map and col_map['goal'] < len(cells) else '',
            'this_week': cells[col_map['this_week']] if 'this_week' in col_map and col_map['this_week'] < len(cells) else '',
            'next_week': cells[col_map['next_week']] if 'next_week' in col_map and col_map['next_week'] < len(cells) else '',
            'blocker': cells[col_map['blocker']] if 'blocker' in col_map and col_map['blocker'] < len(cells) else '',
            'coordinator': cells[col_map['coordinator']] if 'coordinator' in col_map and col_map['coordinator'] < len(cells) else '',
            'status': 'delayed' if (cells[col_map['blocker']] if 'blocker' in col_map and col_map['blocker'] < len(cells) else '') else 'normal',
        }
        if li['this_week'] or li['next_week'] or li['goal']:
            line_items.append(li)

    if not line_items:
        headers_found = ', '.join([h for h in header if h][:10])
        matched = ', '.join(col_map.keys()) if col_map else '无'
        results.append(f"{project_name}: 未识别有效数据（表头=[{headers_found}]，匹配到列=[{matched}]）")
        return 0

    today = _today()
    cal = today.isocalendar()
    _upsert_report(db, project_id, cal[0], cal[1], today, '', '', line_items)
    results.append(f"{project_name}: CSV导入 W{cal[0]}-{cal[1]} ({len(line_items)}条)")
    return 1


@router.post("/api/reports/import-excel")
async def import_reports_excel(file: UploadFile = File(...),
                               db: Session = Depends(get_db),
                               _user=Depends(get_current_user)):
    """Import weekly reports from the 项目总表+周进展跟踪表 Excel."""
    import openpyxl
    from io import BytesIO

    content = await file.read()
    filename = file.filename or ""

    # Parse: openpyxl -> xlrd -> CSV
    sheet_projects = []
    try:
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
        for sname in wb.sheetnames:
            ws = wb[sname]
            sr = []
            for r in ws.iter_rows(max_row=min(ws.max_row, 500), values_only=True):
                cells = [str(c).strip() if c is not None else "" for c in r]
                if any(cells):
                    sr.append("	".join(cells))
            if sr:
                sheet_projects.append({"sheet_name": sname, "rows": sr, "row_count": len(sr)})
    except Exception:
        try:
            import xlrd
            wb2 = xlrd.open_workbook(file_contents=content)
            for si in range(wb2.nsheets):
                sh = wb2.sheet_by_index(si)
                sr = []
                for r in range(sh.nrows):
                    cells = [str(sh.cell_value(r, c)).strip() for c in range(sh.ncols)]
                    if any(cells):
                        sr.append("	".join(cells))
                if sr:
                    sheet_projects.append({"sheet_name": sh.name, "rows": sr, "row_count": len(sr)})
        except Exception:
            for enc in ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'gb18030', 'utf-16']:
                try:
                    text = content.decode(enc)
                    if any('一' <= c <= '鿿' for c in text[:500]):
                        lines_t = [l.strip() for l in text.split(chr(10))[:500] if l.strip()]
                        if len(lines_t) >= 2:
                            sheet_projects = [{"sheet_name": filename, "rows": lines_t, "row_count": len(lines_t)}]
                        break
                except:
                    continue

    if not sheet_projects:
        return {"ok": False, "error": "无法解析文件，请确认是有效的 Excel 或 CSV 文件"}

    return {"ok": True, "projects": all_weeks, "sheet_count": len(sheet_projects)}


@router.post("/api/reports/import-excel-ai")
async def import_weekly_ai(file: UploadFile = File(...),
                            db: Session = Depends(get_db),
                            current_user=Depends(get_current_user)):
    """Smart weekly report import — openpyxl + xlrd + CSV."""
    import openpyxl, re
    from io import BytesIO
    content = await file.read()
    filename = file.filename or ""

    # Parse: openpyxl first (handles xlsx well)
    sheet_projects = []
    try:
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
        for sname in wb.sheetnames:
            ws = wb[sname]
            sr = []
            for r in ws.iter_rows(max_row=min(ws.max_row, 500), values_only=True):
                cells = [str(c).strip() if c is not None else "" for c in r]
                if any(cells):
                    sr.append("\t".join(cells))
            if sr:
                sheet_projects.append({"sheet_name": sname, "rows": sr, "row_count": len(sr)})
    except Exception:
        pass

    # Try xlrd for .xls
    if not sheet_projects:
        try:
            import xlrd
            wb2 = xlrd.open_workbook(file_contents=content)
            for si in range(wb2.nsheets):
                sh = wb2.sheet_by_index(si)
                sr = []
                for r in range(sh.nrows):
                    cells = [str(sh.cell_value(r, c)).strip() for c in range(sh.ncols)]
                    if any(cells):
                        sr.append("\t".join(cells))
                if sr:
                    sheet_projects.append({"sheet_name": sh.name, "rows": sr, "row_count": len(sr)})
        except Exception:
            pass

    # Try CSV/text
    if not sheet_projects:
        for enc in ["utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030", "utf-16"]:
            try:
                text = content.decode(enc)
                lines = [l.strip() for l in text.split("\n")[:500] if l.strip()]
                if len(lines) >= 2:
                    sheet_projects = [{"sheet_name": filename, "rows": lines, "row_count": len(lines)}]
                break
            except:
                continue

    if not sheet_projects:
        return {"ok": False, "error": "无法解析文件，请确认是有效的 Excel 或 CSV 文件"}

    # Rule-based column detection
    all_weeks = []
    for sp in sheet_projects[:15]:
        sn = sp["sheet_name"]
        raw = sp["rows"]
        parsed = []
        for r in raw:
            if "\t" in r: cells = r.split("\t")
            elif "," in r and r.count(",") >= 2: cells = r.split(",")
            else: cells = [r]
            cells = [c.strip() for c in cells]
            if any(cells): parsed.append(cells)
        if len(parsed) < 2:
            all_weeks.append({"sheet_name": sn, "error": "行数不足(" + str(len(parsed)) + ")", "items": []})
            continue
        header = parsed[0]
        col_map = {}
        for j, h in enumerate(header):
            hl = h.lower().replace(" ", "").replace("_", "").replace("-", "").replace("*", "")
            if any(k in hl for k in ("专", "技术线", "discipline", "line")): col_map["line"] = j
            elif any(k in hl for k in ("本周", "thisweek", "进展", "progress", "当前", "当周")): col_map["this_week"] = j
            elif any(k in hl for k in ("下周", "nextweek", "计划", "plan", "下一步")): col_map["next_week"] = j
            elif any(k in hl for k in ("阻塞", "blocker", "问题", "issue", "风险", "备注")): col_map["blocker"] = j
        if "line" not in col_map: col_map["line"] = 0
        if "this_week" not in col_map:
            lens = []
            for row in parsed[1:]:
                for j, c in enumerate(row):
                    while len(lens) <= j: lens.append(0)
                    lens[j] += len(c)
            if lens:
                col_map["this_week"] = max(range(len(lens)), key=lambda x: lens[x] if x not in col_map.values() else 0)
        year = _today().year
        wn = _today().isocalendar()[1]
        for r in parsed[:5]:
            rt = " ".join(r)
            m = re.search(r"第\s*(\d+)\s*周|W(\d{1,2})|(\d{1,2})周", rt)
            if m: wn = int(m.group(1) or m.group(2) or m.group(3)); break
        items = []
        for row in parsed[1:]:
            line_col = col_map.get("line", 0)
            ln = str(row[line_col]).strip() if line_col < len(row) else ""
            if not ln or len(ln) < 2: continue
            if any(k in ln for k in ("小结", "汇总", "领导", "关键", "资源", "基线", "下周", "本周")): continue
            tw_i = col_map.get("this_week", -1)
            tw = str(row[tw_i]).strip() if tw_i >= 0 and tw_i < len(row) else ""
            nw_i = col_map.get("next_week", -1)
            nw = str(row[nw_i]).strip() if nw_i >= 0 and nw_i < len(row) else ""
            bk_i = col_map.get("blocker", -1)
            bk = str(row[bk_i]).strip() if bk_i >= 0 and bk_i < len(row) else ""
            items.append({"line_name": ln, "this_week": tw if tw and tw not in ("0", "-") else "",
                          "next_week": nw if nw and nw not in ("0", "-") else "",
                          "blocker": bk if bk and bk not in ("0", "-") else "", "status": "on_track"})
        if items:
            all_weeks.append({"sheet_name": sn, "year": year, "week": wn, "report_date": "", "overall": "", "items": items})
    return {"ok": True, "projects": all_weeks, "sheet_count": len(sheet_projects)}


@router.post("/api/reports/import-paste")
async def import_weekly_paste(data: dict, db: Session = Depends(get_db),
                               current_user=Depends(get_current_user)):
    """Paste-based weekly report import."""
    text = data.get("text", "").strip()
    project_id = data.get("project_id")
    if not text or not project_id:
        raise HTTPException(400, "缺少文本或项目ID")
    import re
    raw_lines = text.split("\n")

    # Merge multi-line quoted cells (Excel cells with embedded newlines)
    merged_lines = []
    in_quote = False
    buf = ""
    for line in raw_lines:
        stripped = line.rstrip("\r")
        if not in_quote:
            # Count quotes in this line
            dq_count = stripped.count('"')
            if dq_count % 2 == 1:
                in_quote = True
                buf = stripped
            else:
                merged_lines.append(stripped)
        else:
            buf += "\n" + stripped
            dq_count = buf.count('"')
            if dq_count % 2 == 0:
                in_quote = False
                merged_lines.append(buf)
                buf = ""
    if buf:
        merged_lines.append(buf)

    lines = [l.strip() for l in merged_lines if l.strip()]
    if len(lines) < 2:
        return {"ok": False, "error": f"至少需要表头+1行数据，当前{len(lines)}行"}

    # Detect delimiter
    sep = "\t"
    if "\t" not in lines[0] and "," in lines[0]:
        sep = ","

    # Smart split: handle quoted fields that may contain the separator
    parsed = []
    for line in lines:
        if '"' in line:
            # CSV-style quoted field parsing
            row = []
            cur = ""; in_q = False
            for ch in line:
                if ch == '"':
                    in_q = not in_q
                elif ch == sep and not in_q:
                    row.append(cur.strip().strip('"'))
                    cur = ""
                else:
                    cur += ch
            row.append(cur.strip().strip('"'))
            parsed.append(row)
        else:
            parsed.append(line.split(sep))
    parsed = [[c.strip() for c in row] for row in parsed if any(c.strip() for c in row)]
    if len(parsed) < 2:
        return {"ok": False, "error": "解析后数据不足"}

    # Find header row — might be row 0 or row 1 (row 0 might be week title)
    header = parsed[0]
    header_row_idx = 0
    # Check if first row is a week/date header (has "第X周" or date), skip it
    first_text = " ".join(header[:6])
    if re.search(r"第\s*\d+\s*周|\d+\s*月\s*\d+\s*日", first_text):
        header_row_idx = 1
        header = parsed[1] if len(parsed) > 1 else parsed[0]

    # Try to find a real header row with column names (NOT discipline names)
    col_map = {}
    for j in range(min(4, len(parsed))):
        test_row = parsed[j]
        test_text = " ".join(test_row[:6]).lower()
        # Skip week/date headers
        if re.search(r"第\s*\d+\s*周", test_text):
            header_row_idx = j + 1
            continue
        # If this looks like a real header (has column labels like 本周/下周/专业)
        header_keywords = ("本周", "下周", "计划", "进展", "专业", "技术线", "学科", "完成", "内容",
                          "去哪里", "在哪里", "下一步", "难点", "风险", "阻塞",
                          "discipline", "line", "thisweek", "nextweek", "目标", "实际")
        if any(k in test_text for k in header_keywords):
            header_row_idx = j
            header = test_row
            for jj, h in enumerate(header):
                hl = h.lower().replace(" ", "").replace("_", "").replace(":", "").replace("：", "")
                if any(k in hl for k in ("专", "技术线", "学科", "discipline", "line", "类别")): col_map["line"] = jj
                elif any(k in hl for k in ("去哪里", "目标", "任务", "本周", "内容", "goal", "target")) and "this_week_goal" not in col_map: col_map["this_week_goal"] = jj
                elif any(k in hl for k in ("在哪里", "实际", "进展", "完成", "当前", "当周", "工作", "thisweek", "progress", "在哪里（实际进展）")): col_map["this_week"] = jj
                elif any(k in hl for k in ("下一步", "下周", "计划", "nextweek", "plan")): col_map["next_week"] = jj
                elif any(k in hl for k in ("难点", "阻塞", "blocker", "问题", "issue", "风险")): col_map["blocker"] = jj
                elif any(k in hl for k in ("状态", "status")): col_map["status"] = jj
                elif any(k in hl for k in ("预计完成", "deadline", "截止", "日期")): col_map["deadline"] = jj
                elif any(k in hl for k in ("严重", "severity", "等级")): col_map["severity"] = jj
            if "this_week" not in col_map and "this_week_goal" in col_map:
                col_map["this_week"] = col_map["this_week_goal"]  # fallback
            break

    # If no real header found, assume: col 0 = discipline, col 1 = this_week, col 3 = next_week
    if not col_map:
        col_map = {"line": 0, "this_week": 1, "next_week": 3}
        # If 2nd column has no useful text, try 3rd for content
        sample_text_len_col1 = sum(len(str(row[1]).strip()) if len(row) > 1 else 0 for row in parsed[header_row_idx+1:header_row_idx+4])
        if sample_text_len_col1 < 10 and len(parsed[0]) > 3:
            # 2nd column might be empty — real content in col 1 (0-indexed)
            sample_1 = sum(len(str(row[1]).strip()) if len(row) > 1 else 0 for row in parsed[header_row_idx+1:header_row_idx+4])
            sample_2 = sum(len(str(row[2]).strip()) if len(row) > 2 else 0 for row in parsed[header_row_idx+1:header_row_idx+4])
            if sample_2 > sample_1:
                col_map = {"line": 0, "this_week": 2, "next_week": 3}
        header_row_idx = max(0, header_row_idx - 1)  # adjust since no header found

    # Extract week number
    year = _today().year
    wn = _today().isocalendar()[1]
    for r in parsed[:5]:
        rt = " ".join(r)
        m = re.search(r"第\s*(\d+)\s*周|W(\d{1,2})|(\d{1,2})周", rt)
        if m: wn = int(m.group(1) or m.group(2) or m.group(3)); break

    items = []
    for row in parsed[header_row_idx + 1:]:
        # Skip empty or very short rows
        row_text = " ".join(row).strip()
        if not row_text or len(row_text) < 3: continue

        # Skip summary/header rows
        if any(k in row_text for k in ("◆", "整体", "关键事项", "关键节点", "领导决策", "领导协调", "遗留跟踪", "汇总", "小结")):
            continue

        line_col = col_map.get("line", 0)
        ln = str(row[line_col]).strip() if line_col < len(row) else ""
        if not ln or len(ln) < 2: continue
        if any(k in ln for k in ("◆", "整体", "关键", "领导", "遗留", "汇总", "小结")): continue

        tw_i = col_map.get("this_week", -1)
        tw = str(row[tw_i]).strip() if 0 <= tw_i < len(row) else ""
        gl_i = col_map.get("this_week_goal", -1)
        gl = str(row[gl_i]).strip() if 0 <= gl_i < len(row) else ""
        nw_i = col_map.get("next_week", -1)
        nw = str(row[nw_i]).strip() if 0 <= nw_i < len(row) else ""
        bk_i = col_map.get("blocker", -1)
        bk = str(row[bk_i]).strip() if 0 <= bk_i < len(row) else ""
        # Merge goal + actual into this_week if both present
        tw_merged = tw
        if gl and gl != tw and gl not in ("-", "0"):
            tw_merged = ("【目标】" + gl + ("；【进展】" + tw if tw and tw not in ("-", "0") else "")) if tw and tw not in ("-", "0") else ("【目标】" + gl)
        items.append({"line_name": ln, "this_week": tw_merged if tw_merged and tw_merged not in ("0", "-") else "",
                       "next_week": nw if nw and nw not in ("-", "0") else "",
                       "blocker": bk if bk and bk not in ("-", "0") else "", "status": "on_track"})

    if not items:
        return {"ok": False, "error": f"未识别有效数据（表头: {', '.join(header[:6])}）"}

    # Save
    merged = {}; used_ids = set(); nf = 2
    for it in items:
        lid = None
        for lk, lv in DISCIPLINE_MAP.items():
            if lk in it["line_name"]: lid = lv; break
        if not lid:
            while nf in used_ids and nf <= 6: nf += 1
            lid = nf; nf += 1
        used_ids.add(lid)
        if lid in merged:
            m = merged[lid]
            if it["this_week"]: m["this_week"] = (m["this_week"] + "；" + it["this_week"]) if m["this_week"] else it["this_week"]
            if it["next_week"]: m["next_week"] = (m["next_week"] + "；" + it["next_week"]) if m["next_week"] else it["next_week"]
        else:
            merged[lid] = {"line_id": lid, "this_week": it["this_week"],
                           "next_week": it["next_week"], "blocker": it["blocker"],
                           "status": it["status"]}
    line_items = list(merged.values())
    result = _upsert_report(db, project_id, year, wn, _today(), "", "", line_items)
    log_audit(db, current_user.username, "paste_import", "report", result["id"],
              f"W{year}-{wn}", project_id, f"粘贴导入({len(line_items)}条)")
    return {"ok": True, "count": len(line_items), "year": year, "week": wn}


@router.post("/api/reports/import-excel-ai-confirm")
async def import_weekly_ai_confirm(data: dict, db: Session = Depends(get_db),
                                    current_user=Depends(get_current_user)):
    """Save parsed weekly report data."""
    projects_data = data.get("projects", [])
    if not projects_data:
        preview = data.get("preview", {})
        if preview: projects_data = [preview]
    if not projects_data:
        raise HTTPException(400, "没有可导入的数据")

    all_projects = db.execute(select(Project)).scalars().all()
    name_map = {}
    for p in all_projects:
        name_map[p.name.lower()] = p.id
        if p.code: name_map[p.code.lower()] = p.id

    results_list = []
    for proj_data in projects_data:
        sn = proj_data.get("sheet_name", proj_data.get("project_name", ""))
        pid = data.get("project_id")
        if not pid:
            for n, pc in name_map.items():
                if n in sn.lower() or sn.lower() in n: pid = pc; break
        if not pid:
            results_list.append({"sheet": sn, "error": "未匹配到项目"})
            continue

        year = proj_data.get("year", _today().year)
        week = proj_data.get("week", _today().isocalendar()[1])
        try:
            from datetime import date as dt_date
            rpt_date = dt_date.fromisoformat(proj_data.get("report_date", "")) if proj_data.get("report_date") else _today()
        except:
            rpt_date = _today()

        items = proj_data.get("items", [])
        merged = {}; used_ids = set(); nf = 2
        for it in items:
            lid = None
            for lk, lv in DISCIPLINE_MAP.items():
                if lk in it.get("line_name", ""): lid = lv; break
            if not lid:
                while nf in used_ids and nf <= 6: nf += 1
                lid = nf
                if nf < 6: nf += 1
            used_ids.add(lid)
            if lid in merged:
                m = merged[lid]
                if it.get("this_week"): m["this_week"] = (m["this_week"] + "；" + it["this_week"]) if m["this_week"] else it["this_week"]
                if it.get("next_week"): m["next_week"] = (m["next_week"] + "；" + it["next_week"]) if m["next_week"] else it["next_week"]
            else:
                merged[lid] = {"line_id": lid, "this_week": it.get("this_week", ""),
                               "next_week": it.get("next_week", ""), "blocker": it.get("blocker", ""),
                               "status": it.get("status", "on_track")}
        line_items = list(merged.values())
        if not line_items: continue
        result = _upsert_report(db, pid, year, week, rpt_date, proj_data.get("overall", ""), "", line_items)
        log_audit(db, current_user.username, "ai_import", "report", result["id"],
                  f"W{year}-{week}", pid, f"导入({sn} {len(line_items)}条)")
        results_list.append({"sheet": sn, "year": year, "week": week, "items": len(line_items), "ok": True})

    return {"ok": True, "results": results_list}


def report_to_dict(r):
    d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
    d["report_date"] = d["report_date"].isoformat() if d.get("report_date") else None
    d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
    d["reporter"] = {"id": r.reporter.id, "name": r.reporter.name} if r.reporter else None
    d["project_name"] = r.project.name if r.project else ""
    d["line_items"] = []
    for li in (r.line_items or []):
        li_d = {c.name: getattr(li, c.name) for c in li.__table__.columns}
        li_d["line"] = {"id": li.line.id, "name": li.line.name, "short_name": li.line.short_name} if li.line else None
        d["line_items"].append(li_d)
    return d


@router.get("/api/projects/{project_id}/reports")
def list_reports(
    project_id: int,
    year: int = Query(None),
    week: int = Query(None),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    q = select(WeeklyReport).options(selectinload(WeeklyReport.project), selectinload(WeeklyReport.reporter), selectinload(WeeklyReport.line_items).selectinload(WeeklyReportLine.line)).where(WeeklyReport.project_id == project_id)
    if year:
        q = q.where(WeeklyReport.year == year)
    if week:
        q = q.where(WeeklyReport.week_number == week)

    q = q.order_by(WeeklyReport.year.desc(), WeeklyReport.week_number.desc())
    result = db.execute(q)
    rows = result.scalars().all()
    return [report_to_dict(r) for r in rows]


@router.post("/api/projects/{project_id}/reports", status_code=201)
def create_or_update_report(
    project_id: int, data: WeeklyReportCreate,
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    p = (db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not data.report_date:
        from datetime import date as dt
        data.report_date = dt.today()
    # Prefer user-specified year/week, fall back to report_date
    year = data.year if data.year else data.report_date.isocalendar()[0]
    week = data.week_number if data.week_number else data.report_date.isocalendar()[1]

    # Check existing report
    existing = (db.execute(
        select(WeeklyReport).where(
            WeeklyReport.project_id == project_id,
            WeeklyReport.year == year,
            WeeklyReport.week_number == week,
        )
    )).scalars().one_or_none()

    if existing:
        # Update
        db.execute(update(WeeklyReport).where(WeeklyReport.id == existing.id).values(
            report_date=data.report_date,
            overall_progress=data.overall_progress,
            key_accomplishments=data.key_accomplishments,
            completion_rate=data.completion_rate,
            reporter_id=data.reporter_id,
        ))
        report_id = existing.id
        # Replace line items
        db.execute(delete(WeeklyReportLine).where(WeeklyReportLine.report_id == report_id))
        action = "update"
    else:
        # Insert
        r = WeeklyReport(
            project_id=project_id, year=year, week_number=week,
            report_date=data.report_date,
            overall_progress=data.overall_progress,
            key_accomplishments=data.key_accomplishments,
            completion_rate=data.completion_rate,
            reporter_id=data.reporter_id,
            created_at=_now(),
        )
        db.add(r)
        db.flush()
        report_id = r.id
        action = "create"

    # Insert line items
    for li in data.line_items:
        db.add(WeeklyReportLine(
            report_id=report_id, line_id=li.line_id,
            this_week=li.this_week, next_week=li.next_week,
            status=li.status, blocker=li.blocker, coordinator=li.coordinator,
        ))

    # Auto-extract risks/issues from weekly report lines
    # 阻塞有内容 → issue (问题/已发生)
    # 状态"延期" → issue (问题/已发生)
    # 状态"有风险"且无阻塞 → risk (风险/潜在)
    risks_created = 0
    for li in data.line_items:
        blocker_text = (li.blocker or '').strip()
        work_text = (li.this_week or '').strip()

        if not (blocker_text or (li.status in ("delayed", "risk") and work_text)):
            continue

        # 判定类型：有阻塞内容 → 问题；延期 → 问题；仅标记有风险 → 风险
        if blocker_text:
            item_type = "issue"
            title = f"[周报W{week}] {blocker_text[:80]}"
        elif li.status == "delayed":
            item_type = "issue"
            title = f"[周报W{week}] (延期) {(work_text)[:80]}"
        else:  # status == "risk"
            item_type = "risk"
            title = f"[周报W{week}] (风险) {(work_text)[:80]}"

        # Deduplicate
        today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        existing = (db.execute(
            select(RiskIssue).where(
                RiskIssue.project_id == project_id,
                RiskIssue.title == title,
                RiskIssue.created_at >= today_start,
            )
        )).scalar_one_or_none()
        if not existing:
            desc_parts = [f"来源: W{week}周报 技术线{li.line_id}"]
            if blocker_text:
                desc_parts.append(f"阻塞: {blocker_text}")
            desc_parts.append(f"进展: {work_text}")
            db.add(RiskIssue(
                project_id=project_id, type=item_type, title=title,
                description="\n".join(desc_parts),
                severity="中", status="open", line_id=li.line_id,
                created_at=_now(),
            ))
            risks_created += 1

    log_audit(db, current_user.username, action, "report", report_id, f"W{year}-{week}", project_id, f"{action} 周报")
    db.commit()

    # Return created/updated report
    if risks_created > 0:
        import json as _json
        report_dict = report_to_dict((db.execute(select(WeeklyReport).where(WeeklyReport.id == report_id))).scalars().one())
        report_dict["_risks_created"] = risks_created
        return report_dict

    result = db.execute(select(WeeklyReport).where(WeeklyReport.id == report_id))
    r = result.scalars().one()
    return report_to_dict(r)


@router.get("/api/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    result = db.execute(select(WeeklyReport).where(WeeklyReport.id == report_id))
    r = result.scalars().one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="周报不存在")
    return report_to_dict(r)


@router.put("/api/reports/{report_id}")
def update_report(report_id: int, data: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    result = db.execute(select(WeeklyReport).where(WeeklyReport.id == report_id))
    r = result.scalars().one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="周报不存在")

    # Update header fields
    header_fields = {"year", "week_number", "report_date", "reporter_id", "overall_progress", "key_accomplishments", "completion_rate"}
    upd = {k: v for k, v in data.items() if k in header_fields and v is not None}
    # Parse date strings
    for f in ("report_date",):
        if f in upd and upd[f] and isinstance(upd[f], str):
            try: upd[f] = date.fromisoformat(upd[f])
            except: pass
    if upd:
        db.execute(update(WeeklyReport).where(WeeklyReport.id == report_id).values(**upd))

    # Update line items if provided
    risks_created = 0
    if data.get("line_items"):
        db.execute(delete(WeeklyReportLine).where(WeeklyReportLine.report_id == report_id))
        for li in data["line_items"]:
            db.add(WeeklyReportLine(
                report_id=report_id, line_id=li.get("line_id"),
                this_week=li.get("this_week", ""), next_week=li.get("next_week", ""),
                status=li.get("status", "normal"), blocker=li.get("blocker", ""),
                coordinator=li.get("coordinator", ""),
            ))
            # Risk/Issue extraction: 阻塞→issue, 延期→issue, 仅标记有风险→risk
            bt = (li.get("blocker") or '').strip()
            wt = (li.get("this_week") or '').strip()
            if not (bt or (li.get("status") in ("delayed", "risk") and wt)):
                continue
            if bt:
                item_type = "issue"
                title = f"[周报W{r.week_number}] {bt}"[:200]
            elif li.get("status") == "delayed":
                item_type = "issue"
                title = f"[周报W{r.week_number}] (延期) {wt}"[:200]
            else:
                item_type = "risk"
                title = f"[周报W{r.week_number}] (风险) {wt}"[:200]
            today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
            ex = (db.execute(
                select(RiskIssue).where(
                    RiskIssue.project_id == r.project_id, RiskIssue.title == title,
                    RiskIssue.created_at >= today_start,
                )
            )).scalar_one_or_none()
            if not ex:
                db.add(RiskIssue(
                    project_id=r.project_id, type=item_type, title=title,
                    description=f"来源: W{r.week_number}周报(编辑) 技术线{li.get('line_id')}\n阻塞: {bt}\n进展: {wt}",
                    severity="中", status="open", line_id=li.get("line_id"),
                    created_at=_now(),
                ))
                risks_created += 1

    log_audit(db, current_user.username, "update", "report", report_id, f"W{r.year}-{r.week_number}", r.project_id, "更新周报")
    db.commit()

    # Re-fetch
    refetched = db.execute(
        select(WeeklyReport).options(selectinload(WeeklyReport.project), selectinload(WeeklyReport.reporter),
            selectinload(WeeklyReport.line_items).selectinload(WeeklyReportLine.line))
        .where(WeeklyReport.id == report_id)
    )
    result_dict = report_to_dict(refetched.scalars().one())
    if risks_created > 0:
        result_dict["_risks_created"] = risks_created
    return result_dict


@router.delete("/api/reports/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    result = db.execute(select(WeeklyReport).where(WeeklyReport.id == report_id))
    r = result.scalars().one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="周报不存在")
    # Delete line items first
    db.execute(delete(WeeklyReportLine).where(WeeklyReportLine.report_id == report_id))
    db.delete(r)
    log_audit(db, current_user.username, "delete", "report", report_id, "", r.project_id, f"删除周报 W{r.year}-{r.week_number}")
    db.commit()
    return {"ok": True, "message": f"W{r.year}-{r.week_number} 已删除"}


@router.get("/api/projects/{project_id}/reports/latest")
def latest_report(project_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    result = db.execute(
        select(WeeklyReport).where(WeeklyReport.project_id == project_id)
        .order_by(WeeklyReport.year.desc(), WeeklyReport.week_number.desc())
        .limit(1)
    )
    r = result.scalars().one_or_none()
    if not r:
        return {"report": None, "message": "暂无周报"}
    return {"report": report_to_dict(r)}


@router.get("/api/reports")
def list_all_reports(limit: int = Query(20), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Get recent weekly reports across all active projects."""
    q = select(WeeklyReport).join(Project).where(Project.is_active == True) \
        .options(selectinload(WeeklyReport.reporter), selectinload(WeeklyReport.project)) \
        .order_by(WeeklyReport.year.desc(), WeeklyReport.week_number.desc()).limit(limit)
    return [report_to_dict(r) for r in db.execute(q).scalars().all()]


# ── Milestone sync from weekly report ──

MILESTONE_KEYWORDS = [
    "结构评审", "设计评审", "方案评审", "样机试制", "样机完成", "样机测试",
    "台架测试", "耐久测试", "性能测试", "可靠性测试", "NVH测试", "EMC测试", "路试",
    "小批量", "试生产", "量产", "PPAP", "OTS", "SOP",
    "交付客户", "客户验收", "验收通过", "项目结题",
    "BOM冻结", "图纸完成", "供应商定点", "模具完成", "首件",
]

COMPLETION_PATTERNS = [
    # "XXX已完成" / "XXX通过" / "XXX已交付" → completed
    ("完成", +3), ("已完成", +4), ("通过", +3), ("已通过", +4), ("结束", +3),
    ("做完", +3), ("交付", +3), ("已交付", +4), ("发布", +3), ("下发", +3),
    ("归档", +3), ("冻结", +3), ("合格", +3), ("达标", +3), ("验收", +3),
    ("完成。", +5), ("通过。", +5),  # End-of-sentence completion is strongest
]
IN_PROGRESS_PATTERNS = [
    # "XXX中" / "正在XXX" / "XXX开始" → in_progress
    ("中", +2), ("正在", +3), ("进行中", +4), ("开始", +2), ("启动", +2),
    ("推进", +2), ("展开", +2), ("开展", +2), ("着手", +2), ("准备", +1),
    ("制作中", +3), ("调试中", +3), ("测试中", +3), ("验证中", +3), ("设计中", +3),
]
DELAY_PATTERNS = [
    ("延期", -3), ("推迟", -3), ("延后", -3), ("受阻", -3), ("暂停", -3),
    ("等待", -2), ("滞后", -3), ("待定", -2), ("搁置", -3),
]
# Patterns that indicate something happened AFTER completion (negates completion)
POST_COMPLETION_PATTERNS = [
    ("完成后", -5), ("结束后", -5), ("通过后", -5), ("交付后", -5),
    ("完成，", -3), ("通过，", -3),
]
# Patterns that explicitly say NOT done yet
NOT_DONE_PATTERNS = [
    ("未完成", -5), ("未通过", -5), ("还没完成", -5), ("尚未完成", -5),
    ("还没开始", -3), ("未开始", -3), ("待完成", -3), ("待推进", -2),
]


def _analyze_context(all_text: str, keyword: str) -> tuple:
    """Analyze text around a keyword to determine status.
    Returns (action: str, confidence: int, reason_snippet: str)
    """
    idx = all_text.find(keyword)
    if idx < 0:
        return ("", 0, "")

    # Get sentence-level context: 50 chars before and after the keyword
    start = max(0, idx - 50)
    end = min(len(all_text), idx + len(keyword) + 50)
    context = all_text[start:end]
    before = all_text[start:idx]
    after = all_text[idx + len(keyword):end]
    # The immediate vicinity: 20 chars
    nearby = all_text[max(0, idx - 20):idx + len(keyword) + 20]

    score = 0

    # ── Check post-completion patterns first (these NEGATE completion) ──
    for pat, penalty in POST_COMPLETION_PATTERNS:
        if pat in nearby:
            score += penalty
            break  # Only apply the strongest one

    # ── Check NOT-done patterns ──
    for pat, penalty in NOT_DONE_PATTERNS:
        if pat in nearby:
            score += penalty
            break

    # ── Check completion patterns in context ──
    for pat, pts in COMPLETION_PATTERNS:
        if pat in after[:30]:  # Completion indicator AFTER keyword
            score += pts
            break
        if pat in before[-20:]:  # Completion indicator immediately BEFORE keyword
            score += pts - 1
            break

    # ── Check in-progress patterns ──
    for pat, pts in IN_PROGRESS_PATTERNS:
        if pat in nearby:
            # "XXX中" right after keyword = in progress
            if pat in after[:5]:
                score += pts
                break
            # Otherwise weaker signal
            score += max(0, pts - 1)
            break

    # ── Check delay patterns ──
    for pat, penalty in DELAY_PATTERNS:
        if pat in nearby:
            score += penalty
            break

    # Determine action based on final score
    if score >= 3:
        return ("completed", min(score, 8), f"「{keyword}」附近出现完成信号（{context[:60].strip()}...）")
    elif score >= 1:
        return ("in_progress", 2, f"「{keyword}」正在进行中（{context[:60].strip()}...）")
    elif score <= -3:
        return ("delayed", 2, f"「{keyword}」被标记为延期/受阻（{context[:60].strip()}...）")
    else:
        # Keyword exists with neutral context → just note it exists
        return ("noted", 1, f"周报中提到「{keyword}」但无法判断完成状态")


@router.get("/api/projects/{project_id}/reports/{report_id}/sync-milestones")
def sync_milestones_from_report(
    project_id: int,
    report_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Analyze a weekly report and suggest milestone updates."""
    from backend_v2.models import Milestone, WeeklyReportLine

    report = db.get(WeeklyReport, report_id)
    if not report or report.project_id != project_id:
        raise HTTPException(404, "周报不存在")

    # Calculate the week's date range (Monday-Sunday)
    from datetime import date, timedelta
    import re as _re
    jan4 = date(report.year, 1, 4)
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    report_monday = week1_monday + timedelta(weeks=report.week_number - 1)
    report_sunday = report_monday + timedelta(days=6)

    lines = db.execute(
        select(WeeklyReportLine).where(WeeklyReportLine.report_id == report_id)
    ).scalars().all()

    milestones = db.execute(
        select(Milestone).where(Milestone.project_id == project_id)
    ).scalars().all()

    # Collect all text from the report, preserving sentence boundaries
    all_text = f"{report.overall_progress or ''}\n{report.key_accomplishments or ''}\n"
    for line in lines:
        all_text += f"{line.this_week or ''}\n{line.next_week or ''}\n{line.goal or ''}\n{line.blocker or ''}\n"

    # Extract dates from report text (e.g. "预计8.16完成", "8月16日", "8/16")
    parsed_dates = []
    date_patterns = [
        (r'(\d{1,2})[.](\d{1,2})', None),   # 8.16
        (r'(\d{1,2})[/](\d{1,2})', None),    # 8/16
        (r'(\d{1,2})月(\d{1,2})[日号]', None),  # 8月16日
    ]
    for pat, _ in date_patterns:
        for m in _re.finditer(pat, all_text):
            try:
                month, day = int(m.group(1)), int(m.group(2))
                if 1 <= month <= 12 and 1 <= day <= 31:
                    yr = report.year
                    if month < report_monday.month:
                        yr += 1
                    parsed_dates.append((m.start(), date(yr, month, day)))
            except: pass

    suggestions = []
    matched_milestone_ids = set()

    for ms in milestones:
        # Skip milestones already completed or with actual dates (don't override existing data)
        if ms.status == "completed" and ms.actual_date:
            continue
        if ms.status == "cancelled":
            continue

        ms_name = ms.name or ""
        # Find any milestone-related text in the report
        best_action = ""
        best_confidence = 0
        best_reason = ""
        best_keyword = ""

        # Strategy 1a: Full milestone name appears in report text?
        if ms_name in all_text:
            action, conf, reason = _analyze_context(all_text, ms_name)
            if conf > best_confidence:
                best_action, best_confidence, best_reason, best_keyword = action, conf, reason, ms_name

        # Strategy 1b: Fuzzy character-overlap matching (catch related but non-identical text)
        if best_confidence < 3 and len(ms_name) >= 3:
            ms_chars = set(ms_name)
            # Find best-matching segment in report text using sliding window
            for win_size in range(len(ms_name), max(2, len(ms_name) // 2), -1):
                if best_confidence >= 3: break
                for i in range(len(all_text) - win_size + 1):
                    window = all_text[i:i + win_size]
                    window_chars = set(window)
                    if not ms_chars or not window_chars: continue
                    overlap = len(ms_chars & window_chars)
                    ratio = overlap / len(ms_chars)
                    if ratio >= 0.5 and any(c in window for c in ms_name if c.strip() and len(c.strip()) >= 1 and '一' <= c <= '鿿'):
                        # Found fuzzy match — extract the relevant keyword
                        best_chars = [c for c in ms_name if c in window and '一' <= c <= '鿿']
                        fuzzy_kw = ''.join(best_chars[:4])
                        if len(fuzzy_kw) >= 2:
                            action, conf, reason = _analyze_context(all_text, fuzzy_kw)
                            if conf >= 2:
                                best_action, best_confidence, best_reason, best_keyword = action, conf, reason, fuzzy_kw
                                break

        # Strategy 1c: Check all 2+ character substrings of milestone name
        if not best_keyword:
            seen = set()
            for slen in range(min(6, len(ms_name)), 1, -1):
                for i in range(len(ms_name) - slen + 1):
                    sub = ms_name[i:i+slen]
                    if sub in seen: continue
                    seen.add(sub)
                    if len(sub) >= 2 and sub in all_text:
                        # Skip common stop words
                        if sub in ('的', '了', '是', '在', '和', '与', '及', '或', '等', '对', '将', '已', '不', '为', '而', '且', '但', '所', '则', '要', '会', '可', '能', '到', '从', '由', '被', '把', '向', '以', '之', '其', '上', '下', '前', '后', '都', '也', '就', '还', '又', '这', '那', '各', '些', '很', '更', '最', '较', '只', '多', '少', '大', '小', '准备', '计划', '推进', '项目', '阶段', '进行'):
                            continue
                        action, conf, reason = _analyze_context(all_text, sub)
                        if conf > best_confidence:
                            best_action = action
                            best_confidence = conf
                            best_reason = reason
                            best_keyword = sub
                        if best_confidence >= 4:
                            break
                if best_confidence >= 4:
                    break

        # Strategy 2: Look for engineering keywords
        for kw in MILESTONE_KEYWORDS:
            if kw in all_text and kw in ms_name:
                action, conf, reason = _analyze_context(all_text, kw)
                if conf > best_confidence:
                    best_action = action
                    best_confidence = conf
                    best_reason = reason
                    best_keyword = kw

        # Strategy 3: Check if milestone description words appear
        if not best_keyword and ms.description:
            desc_words = [w for w in ms.description.replace('(', ' ').replace(')', ' ').split() if len(w) >= 2]
            for w in desc_words[:5]:
                if w in all_text:
                    action, conf, reason = _analyze_context(all_text, w)
                    if conf > best_confidence:
                        best_action = action
                        best_confidence = conf
                        best_reason = reason
                        best_keyword = w

        if best_confidence >= 1 and best_keyword:
            suggested_status = ms.status
            if best_action == "completed":
                suggested_status = "completed"
            elif best_action == "in_progress":
                suggested_status = "in_progress"
            elif best_action == "delayed":
                suggested_status = "delayed" if hasattr(Milestone, 'delayed') else ms.status
            elif best_action == "noted":
                suggested_status = ms.status  # No change detected, just noted

            # Show suggestion if status changed OR confidence is medium+
            # Don't override: completed→in_progress, or if actual_date already set
            if suggested_status == "in_progress" and ms.status == "completed":
                pass  # Never downgrade
            elif ms.actual_date and suggested_status == "in_progress":
                pass  # Don't override existing actual completion
            elif suggested_status != ms.status or best_confidence >= 2:
                item = {
                    "milestone_id": ms.id,
                    "milestone_name": ms_name,
                    "current_status": ms.status or "pending",
                    "suggested_status": suggested_status,
                    "matched_keyword": best_keyword,
                    "confidence": "high" if best_confidence >= 4 else ("medium" if best_confidence >= 2 else "low"),
                    "reason": best_reason,
                }
                # Suggest date based on parsed text dates or report week
                nearest_date = None
                if parsed_dates:
                    # Find the closest mentioned date to the keyword position
                    kw_pos = all_text.find(best_keyword)
                    min_dist = 9999
                    for pos, dt in parsed_dates:
                        dist = abs(pos - kw_pos) if kw_pos >= 0 else 9999
                        if dist < min_dist:
                            min_dist = dist
                            nearest_date = dt
                if not nearest_date:
                    nearest_date = report_sunday

                if suggested_status == "completed":
                    if not ms.actual_date:
                        item["suggested_actual_date"] = nearest_date.isoformat()
                elif nearest_date and not ms.actual_date:
                    item["suggested_actual_date"] = nearest_date.isoformat()
                suggestions.append(item)
                matched_milestone_ids.add(ms.id)

    # Phase progression: if later-phase milestones are active, earlier phases should be done
    from backend_v2.models import Phase
    phases = db.execute(select(Phase).order_by(Phase.sort_order)).scalars().all()
    phase_map = {p.id: {"code": p.code, "sort": p.sort_order} for p in phases}

    # Find the "furthest" phase that has in_progress milestones
    max_active_phase = 0
    for ms in milestones:
        if ms.phase_id and ms.status in ("in_progress", "completed"):
            pi = phase_map.get(ms.phase_id, {})
            max_active_phase = max(max_active_phase, pi.get("sort", 0))
    # Also check suggestions for in_progress/completed status
    for s in suggestions:
        if s["suggested_status"] in ("in_progress", "completed"):
            ms = next((m for m in milestones if m.id == s["milestone_id"]), None)
            if ms and ms.phase_id:
                pi = phase_map.get(ms.phase_id, {})
                max_active_phase = max(max_active_phase, pi.get("sort", 0))

    # Auto-complete pending milestones in earlier phases
    if max_active_phase >= 2:  # At least PP1 has active work
        for ms in milestones:
            if ms.id in matched_milestone_ids: continue
            if ms.status != "pending": continue
            if not ms.phase_id: continue
            pi = phase_map.get(ms.phase_id, {})
            ms_sort = pi.get("sort", 99)
            if ms_sort < max_active_phase:
                suggestions.append({
                    "milestone_id": ms.id,
                    "milestone_name": ms.name,
                    "current_status": "pending",
                    "suggested_status": "completed",
                    "matched_keyword": "阶段推进",
                    "confidence": "medium",
                    "reason": f"后续阶段（{pi.get('code','')}）已有进展，此前阶段里程碑应已完成",
                    "suggested_actual_date": report_sunday.isoformat(),
                })

    return {
        "report_id": report_id,
        "project_id": project_id,
        "suggestions": suggestions,
        "total_milestones": len(milestones),
        "matched_count": len(matched_milestone_ids),
    }


@router.post("/api/projects/{project_id}/milestones/sync-apply")
def apply_milestone_sync(
    project_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Apply suggested milestone updates from weekly report sync."""
    from backend_v2.models import Milestone

    updates = data.get("updates", [])
    create_new = data.get("create_new", [])
    results = {"updated": [], "created": [], "errors": []}

    from datetime import date as DateType

    for item in updates:
        ms_id = item.get("milestone_id")
        ms = db.get(Milestone, ms_id)
        if ms and ms.project_id == project_id:
            if "status" in item:
                ms.status = item["status"]
                if item["status"] == "completed":
                    if not ms.actual_date:
                        actual_str = item.get("actual_date")
                        ms.actual_date = date.fromisoformat(actual_str) if actual_str else DateType.today()
                    if item.get("end_date"):
                        ms.planned_end_date = date.fromisoformat(item["end_date"])
            results["updated"].append(ms.name)

    for item in create_new:
        name = item.get("name", "")
        if name:
            m = Milestone(
                project_id=project_id,
                name=name,
                status=item.get("status", "pending"),
                planned_date=DateType.today(),
                created_by=current_user.username,
            )
            db.add(m)
            db.flush()
            results["created"].append(name)

    db.commit()
    return results
