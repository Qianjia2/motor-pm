"""软件研发项目交付物标准调整迁移。

变更(用户 2026-09-10 指定的交付物清单):
  重命名(保留原条目 id,不新增重复项):
    S1 代码版本管理记录 → 代码版本管理   (并置为必交 required=1)
    S2 测试计划         → 软件测试计划
  新增 6 项:
    S0 软件需求分析文档 / S1 软件设计说明书 / S1 软件包提测说明
    S2 软件测试报告     / S3 用户定制功能文档 / S3 客户培训记录
  其余已有条目一律保留(不做删除);sort_order 按新清单在阶段内重排。

清单的数据源是 backend_v2/database.py::_seed_software_standards,
本脚本用 AST 读取它,避免两处维护同一份定义。

幂等:清单与库内 (阶段, 名称) 集合及 sort_order 完全一致时直接跳过。

用法: python scripts/migrate_software_deliverables.py [--db PATH] [--no-backup]
"""
import argparse
import ast
import os
import shutil
import sqlite3
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "data", "motor_pm_v2.db")
DATABASE_PY = os.path.join(ROOT, "backend_v2", "database.py")

# 旧名 → 新名(仅软件阶段)。重命名保留原 id,避免出现"新旧并存"的重复条目。
RENAMES = {
    ("S1", "代码版本管理记录"): "代码版本管理",
    ("S2", "测试计划"): "软件测试计划",
}


def load_standards():
    """从 database.py 的 _seed_software_standards 读出交付物清单。"""
    tree = ast.parse(open(DATABASE_PY, encoding="utf-8").read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_seed_software_standards")
    assign = next(n for n in ast.walk(fn)
                  if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "standards")
    out = []
    for e in assign.value.elts:
        phase_code, name, cat, required, desc, crit, role, sort = ast.literal_eval(e)
        out.append(dict(phase_code=phase_code, name=name, cat=cat, required=required,
                        desc=desc, crit=crit, role=role, sort=sort))
    assert out, "未读到交付物清单"
    return out


def current(cur):
    """库内软件交付物: {(阶段码, 名称): (id, sort_order)}"""
    return {(r[0], r[1]): (r[2], r[3]) for r in cur.execute(
        "SELECT p.code, s.name, s.id, s.sort_order FROM gate_deliverable_standard s "
        "JOIN phase p ON p.id = s.phase_id WHERE p.project_type='software'")}


def already_done(cur, stds):
    want = {(s["phase_code"], s["name"]): s["sort"] for s in stds}
    have = {k: v[1] for k, v in current(cur).items()}
    return want == have


def migrate(db_path, backup=True):
    stds = load_standards()

    if backup:
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        bak = db_path.replace(".db", f"_backup_before_deliverables_{stamp}.db")
        shutil.copy2(db_path, bak)
        print(f"[备份] {bak}")

    db = sqlite3.connect(db_path)
    cur = db.cursor()

    if already_done(cur, stds):
        print("[跳过] 交付物清单与库内一致,无需迁移")
        db.close()
        return 0

    n_before = len(current(cur))
    print(f"[现状] 软件交付物 {n_before} 项")

    try:
        # 1) 重命名:保留原 id 与其它字段,只改名称
        for (phase_code, old_name), new_name in RENAMES.items():
            row = cur.execute(
                "SELECT s.id FROM gate_deliverable_standard s JOIN phase p ON p.id=s.phase_id "
                "WHERE p.code=? AND s.name=?", (phase_code, old_name)).fetchone()
            if not row:
                continue
            clash = cur.execute(
                "SELECT s.id FROM gate_deliverable_standard s JOIN phase p ON p.id=s.phase_id "
                "WHERE p.code=? AND s.name=?", (phase_code, new_name)).fetchone()
            if clash:
                print(f"[警告] {phase_code} 已存在「{new_name}」,跳过重命名「{old_name}」"
                      f"(旧条目保留,可自行删除)", file=sys.stderr)
                continue
            cur.execute("UPDATE gate_deliverable_standard SET name=? WHERE id=?",
                        (new_name, row[0]))
            print(f"[重命名] {phase_code} 「{old_name}」→「{new_name}」(id={row[0]})")

        # 2) 逐条写入:存在则更新(字段+排序),不存在则插入
        n_new = 0
        for s in stds:
            pid = cur.execute("SELECT id FROM phase WHERE code=?", (s["phase_code"],)).fetchone()
            if not pid:
                print(f"[错误] 阶段 {s['phase_code']} 不存在", file=sys.stderr)
                db.rollback()
                db.close()
                return 1
            pid = pid[0]
            row = cur.execute(
                "SELECT id FROM gate_deliverable_standard WHERE phase_id=? AND name=?",
                (pid, s["name"])).fetchone()
            if row:
                cur.execute(
                    "UPDATE gate_deliverable_standard SET category=?, required=?, description=?, "
                    "acceptance_criteria=?, responsible_role=?, sort_order=? WHERE id=?",
                    (s["cat"], s["required"], s["desc"], s["crit"], s["role"], s["sort"], row[0]))
            else:
                cur.execute(
                    "INSERT INTO gate_deliverable_standard (phase_id, name, category, required, "
                    "description, acceptance_criteria, responsible_role, sort_order, is_active) "
                    "VALUES (?,?,?,?,?,?,?,?,1)",
                    (pid, s["name"], s["cat"], s["required"], s["desc"], s["crit"], s["role"], s["sort"]))
                n_new += 1
                print(f"[新增] {s['phase_code']} 「{s['name']}」 (必交={s['required']})")

        db.commit()
    except Exception:
        db.rollback()
        db.close()
        raise

    # 3) 校验
    total = cur.execute(
        "SELECT COUNT(*) FROM gate_deliverable_standard s JOIN phase p ON p.id=s.phase_id "
        "WHERE p.project_type='software'").fetchone()[0]
    print(f"\n[校验] 新增 {n_new} 项,软件交付物共 {total} 项")
    for pc in ("S0", "S1", "S2", "S3"):
        rows = cur.execute(
            "SELECT s.sort_order, s.name, s.required FROM gate_deliverable_standard s "
            "JOIN phase p ON p.id=s.phase_id WHERE p.code=? ORDER BY s.sort_order", (pc,)).fetchall()
        print(f"  {pc} ({len(rows)} 项):")
        for sort, name, req in rows:
            print(f"    {sort:>2}. {'★' if req else ' '} {name}")

    n_after = len(current(cur))
    if n_after != n_before + n_new:
        print(f"[警告] 条目数不符:迁移前 {n_before} + 新增 {n_new} ≠ 迁移后 {n_after}",
              file=sys.stderr)
    db.close()
    print("\n[完成] 迁移成功")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--no-backup", action="store_true")
    a = ap.parse_args()
    sys.exit(migrate(a.db, backup=not a.no_backup))
