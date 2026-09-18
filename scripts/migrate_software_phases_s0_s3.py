"""软件研发项目阶段门合并迁移: S0-S4(5阶段) → S0-S3(4阶段)。

变更内容:
  旧 S0 需求分析阶段  → 新 S0 需求分析阶段   (不变)
  旧 S1 架构设计阶段  ┐
  旧 S2 开发编码阶段  ┘→ 新 S1 软件开发阶段   (合并,阶段 id 保留旧 S1)
  旧 S3 测试验证阶段  → 新 S2 测试验证阶段   (顺移)
  旧 S4 发布交付阶段  → 新 S3 发布交付阶段   (顺移)

门禁: G-S0~G-S4 → G-S0~G-S3(旧 G-S4 删除,旧 G-S2/G-S3 分别改挂新 S2/S3)

幂等:已迁移(phase 表无 S4 且有 4 个 software 阶段)则直接跳过。

用法: python scripts/migrate_software_phases_s0_s3.py [--db PATH]
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "motor_pm_v2.db")

# 新阶段定义: code -> (name, sort_order, description)
NEW_PHASES = {
    "S0": ("需求分析阶段", 101, "需求调研/需求评审/开发合同"),
    "S1": ("软件开发阶段", 102, "架构设计/接口定义/模块开发/单元测试"),
    "S2": ("测试验证阶段", 103, "集成测试/性能测试/验收测试"),
    "S3": ("发布交付阶段", 104, "版本发布/部署交付/验收归档"),
}
# 新门禁定义: code -> (name, sort_order, phase_code)
NEW_GATES = {
    "G-S0": ("S0 需求评审", 101, "S0"),
    "G-S1": ("S1 开发完成", 102, "S1"),
    "G-S2": ("S2 测试完成", 103, "S2"),
    "G-S3": ("S3 发布交付", 104, "S3"),
}


def already_migrated(cur):
    codes = [r[0] for r in cur.execute(
        "SELECT code FROM phase WHERE project_type='software' ORDER BY sort_order")]
    return codes == sorted(NEW_PHASES, key=lambda c: NEW_PHASES[c][1])


def migrate(db_path, backup=True):
    if backup:
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        bak = db_path.replace(".db", f"_backup_before_phase_merge_{stamp}.db")
        shutil.copy2(db_path, bak)
        print(f"[备份] {bak}")

    db = sqlite3.connect(db_path)
    cur = db.cursor()

    if already_migrated(cur):
        print("[跳过] 已是 S0-S3 四阶段结构,无需迁移")
        db.close()
        return 0

    # 阶段 id 按 code 取
    pid = {c: r[0] for c, r in
           ((r[1], (r[0],)) for r in cur.execute(
               "SELECT id, code FROM phase WHERE code IN ('S0','S1','S2','S3','S4')"))}
    if len(pid) < 5:
        print(f"[错误] 期望找到 S0-S4 五个阶段,实际 {sorted(pid)}", file=sys.stderr)
        db.close()
        return 1
    old_s1, old_s2, old_s3, old_s4 = pid["S1"], pid["S2"], pid["S3"], pid["S4"]

    try:
        # 1) 合并阶段门记录: 旧 S2 行删除,其状态并入旧 S1 行
        #    (软件项目每个阶段一条;旧 S2 若有已推进状态,取二者中较靠后的)
        rank = {"not_started": 0, "in_progress": 1, "completed": 2}
        s2_rows = cur.execute(
            "SELECT id, project_id, status FROM project_phase_gate WHERE phase_id=?",
            (old_s2,)).fetchall()
        for row_id, project_id, s2_status in s2_rows:
            s1 = cur.execute(
                "SELECT id, status FROM project_phase_gate WHERE project_id=? AND phase_id=?",
                (project_id, old_s1)).fetchone()
            if s1 and rank.get(s2_status, 0) > rank.get(s1[1], 0):
                cur.execute("UPDATE project_phase_gate SET status=? WHERE id=?", (s2_status, s1[0]))
                print(f"[合并] 项目 {project_id}: 旧S2 状态 {s2_status} 并入 S1 行")
            cur.execute("DELETE FROM project_phase_gate WHERE id=?", (row_id,))
        print(f"[阶段门] 删除旧 S2 记录 {len(s2_rows)} 条")

        # 2) 交付物标准: 旧 S2 的挂到旧 S1 名下,sort_order 顺延到旧 S1 之后
        max_s1_sort = cur.execute(
            "SELECT COALESCE(MAX(sort_order),0) FROM gate_deliverable_standard WHERE phase_id=?",
            (old_s1,)).fetchone()[0]
        n = cur.execute(
            "UPDATE gate_deliverable_standard SET phase_id=?, sort_order=sort_order+? WHERE phase_id=?",
            (old_s1, max_s1_sort, old_s2)).rowcount
        print(f"[交付物] 旧 S2 的 {n} 项并入 S1(sort 顺延 +{max_s1_sort})")

        # 3) 删除旧 S2 阶段(id 释放出 code 'S2')
        cur.execute("DELETE FROM phase WHERE id=?", (old_s2,))

        # 4) 编码顺移: S3→S2, S4→S3(顺序不可颠倒,否则 code 撞车)
        for old_id, new_code in ((old_s3, "S2"), (old_s4, "S3")):
            name, sort, desc = NEW_PHASES[new_code]
            cur.execute("UPDATE phase SET code=?, name=?, sort_order=?, description=? WHERE id=?",
                        (new_code, name, sort, desc, old_id))
            print(f"[阶段] id={old_id} → {new_code} {name}")
        # 旧 S1 改名/改描述(编号不变)
        name, sort, desc = NEW_PHASES["S1"]
        cur.execute("UPDATE phase SET name=?, sort_order=?, description=? WHERE id=?",
                    (name, sort, desc, old_s1))
        print(f"[阶段] id={old_s1} → S1 {name}")
        name, sort, desc = NEW_PHASES["S0"]
        cur.execute("UPDATE phase SET name=?, sort_order=?, description=? WHERE id=?",
                    (name, sort, desc, pid["S0"]))

        # 5) 门禁: G-S1 改名;G-S2/G-S3 改挂新阶段;G-S4 删除
        new_s2, new_s3 = old_s3, old_s4   # 阶段 id 未变,只是 code 变了
        for gcode, (gname, gsort, pcode) in NEW_GATES.items():
            target_phase = {"S0": pid["S0"], "S1": old_s1, "S2": new_s2, "S3": new_s3}[pcode]
            row = cur.execute("SELECT id FROM gate WHERE code=?", (gcode,)).fetchone()
            if row:
                cur.execute("UPDATE gate SET name=?, sort_order=?, phase_id=? WHERE id=?",
                            (gname, gsort, target_phase, row[0]))
        # 旧 G-S4 的门禁行删除
        gs4 = cur.execute("SELECT id FROM gate WHERE code='G-S4'").fetchone()
        if gs4:
            cur.execute("DELETE FROM gate WHERE id=?", (gs4[0],))
            print(f"[门禁] G-S4(id={gs4[0]}) 删除")

        # 阶段门记录重新对齐:每条软件项目的阶段门记录,其 gate_id 归位到该阶段自己的门。
        # (阶段 id 全程未变,而门禁被重新编号,必须显式对齐,否则 S2/S3 会同时挂到 G-S3)
        fixed = cur.execute(
            "UPDATE project_phase_gate SET gate_id = "
            "(SELECT g.id FROM gate g WHERE g.phase_id = project_phase_gate.phase_id) "
            "WHERE phase_id IN (SELECT id FROM phase WHERE project_type='software')"
        ).rowcount
        print(f"[阶段门] 对齐 gate_id: {fixed} 条")

        db.commit()
    except Exception:
        db.rollback()
        db.close()
        raise

    # 6) 校验
    print("\n[校验] 软件阶段:")
    for r in cur.execute("SELECT id, code, name, sort_order FROM phase "
                         "WHERE project_type='software' ORDER BY sort_order"):
        print(f"   id={r[0]:<3} {r[1]:<3} {r[2]}  sort={r[3]}")
    print("[校验] 软件门禁:")
    for r in cur.execute("SELECT g.code, g.name, p.code FROM gate g "
                         "LEFT JOIN phase p ON p.id=g.phase_id "
                         "WHERE g.code LIKE 'G-S%' ORDER BY g.sort_order"):
        print(f"   {r[0]:<6} {r[1]:<10} → {r[2]}")
    print("[校验] 交付物标准数:")
    for r in cur.execute("SELECT p.code, COUNT(*) FROM gate_deliverable_standard s "
                         "JOIN phase p ON p.id=s.phase_id WHERE p.project_type='software' "
                         "GROUP BY p.code ORDER BY p.code"):
        print(f"   {r[0]}: {r[1]} 项")
    print("[校验] 各软件项目阶段门记录:")
    for r in cur.execute("SELECT pg.project_id, p.code, g.code, pg.status "
                         "FROM project_phase_gate pg "
                         "JOIN phase p ON p.id=pg.phase_id "
                         "LEFT JOIN gate g ON g.id=pg.gate_id "
                         "WHERE p.project_type='software' ORDER BY pg.project_id, p.sort_order"):
        print(f"   项目{r[0]}: {r[1]} / {r[2]} / {r[3]}")

    db.close()
    print("\n[完成] 迁移成功")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--no-backup", action="store_true")
    a = ap.parse_args()
    sys.exit(migrate(a.db, backup=not a.no_backup))
