"""移除「控制算法」技术线（并入「控制软件」）。

背景: 平台的技术线只需要 5 条（控制软件/控制硬件/电机结构/电机电磁/测试验证）。
「算法」一直是要并进「控制软件」的——前端 AI 归类的关键词表（WeeklyReportForm.vue
的 lineKeywords[2]）和后端导入的 DISCIPLINE_MAP 都已经把 控制算法/算法/FOC/PID
映射到 控制软件(id=2)，只有 technical_line 表里还留着一条独立的「控制算法」。

这条记录会被两处带出来:
  - 周报表单按 technical_line 全量铺行（WeeklyReportForm.vue:324）
  - 已提交的周报 56/57/58 各有一条它的空行（this_week/next_week 都是空串）

反复出现的根源是 backend_v2/seed.py：它按名称判断「不存在才插入」，
所以每次重跑 seed，被删掉的「控制算法」都会被补回来。本脚本只清库，
seed 侧已同步移除（见该文件的技术线列表）。

幂等: 库里没有「控制算法」时直接跳过、不备份。

用法: python scripts/migrate_remove_algorithm_line.py [--db PATH] [--no-backup]
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "data", "motor_pm_v2.db")
LINE_NAME = "控制算法"
KEEP = ["控制软件", "控制硬件", "电机结构", "电机电磁", "测试验证"]


def migrate(db_path, backup=True):
    if not os.path.exists(db_path):
        print(f"[错误] 数据库不存在: {db_path}")
        return 1
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("SELECT * FROM technical_line WHERE name = ?", (LINE_NAME,)).fetchall()
    if not rows:
        print(f"[跳过] 库里没有「{LINE_NAME}」技术线,无需处理")
        conn.close()
        return 0
    if len(rows) > 1:
        print(f"[错误] 查到 {len(rows)} 条「{LINE_NAME}」,请先人工确认: "
              f"{[r['id'] for r in rows]}")
        conn.close()
        return 1

    line = rows[0]
    lid = line["id"]

    # 引用面先摸清楚:除了周报行,其它表也可能挂着这条线
    refs = {}
    for table in ("weekly_report_line", "milestone", "risk_issue", "deliverable", "task"):
        try:
            n = conn.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE line_id = ?', (lid,)  # noqa: S608
            ).fetchone()[0]
        except sqlite3.OperationalError:
            continue
        if n:
            refs[table] = n

    wl = conn.execute(
        "SELECT id, report_id, this_week, next_week, coordinator, goal "
        "FROM weekly_report_line WHERE line_id = ?", (lid,)).fetchall()
    filled = [r["id"] for r in wl
              if (r["this_week"] or "").strip() or (r["next_week"] or "").strip()
              or (r["coordinator"] or "").strip() or (r["goal"] or "").strip()]
    if filled:
        print(f"[中止] 周报行 {filled} 里填过内容,不能删。请先人工决定这些内容归到哪条线。")
        conn.close()
        return 1

    print(f"[计划] 删除 technical_line id={lid} name={line['name']} "
          f"short={line['short_name']} sort={line['sort_order']}")
    print(f"[计划] 引用情况: {refs or '无'}")
    for r in wl:
        print(f"        连带删除 weekly_report_line id={r['id']} (report {r['report_id']}) —— 空行")

    if backup:
        bdir = os.path.join(ROOT, "data", "backup")
        os.makedirs(bdir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = os.path.join(bdir, f"pre_remove_algorithm_line_{stamp}.db")
        shutil.copy2(db_path, bak)
        print(f"[备份] {bak}")

    conn.execute("DELETE FROM weekly_report_line WHERE line_id = ?", (lid,))
    conn.execute("DELETE FROM technical_line WHERE id = ?", (lid,))
    conn.commit()

    left = [dict(r) for r in conn.execute(
        "SELECT id, name, short_name, sort_order FROM technical_line ORDER BY sort_order, id")]
    print(f"[完成] 剩余 {len(left)} 条技术线: {[x['name'] for x in left]}")
    missing = [n for n in KEEP if n not in [x["name"] for x in left]]
    if missing:
        print(f"[警告] 少了预期保留的技术线: {missing}")
    conn.close()
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--no-backup", action="store_true")
    a = ap.parse_args()
    sys.exit(migrate(a.db, backup=not a.no_backup))


if __name__ == "__main__":
    main()
