"""新增「项目工作流·线下步骤确认」表 project_workflow_step_confirm。

背景: 项目详情的「工作流」页签把 PHASE_NODES 的步骤按项目渲染出来,其中线下步骤
(客户调研、UAT、现场部署、客户培训、客户验收)平台没有数据源,只能由人确认,
确认记录存在这张新表里。

这张表是纯新增,不动任何既有表的数据。启动时 init_db() 的 create_all 也会建它,
本脚本的意义是: 先备份、幂等建表、并把建出来的结构与模型对齐后打印校验结果。
表结构与 backend_v2/models/__init__.py::ProjectWorkflowStepConfirm 一致
(约束名也保持同名,避免两条路径建出的库结构不同)。

用法: python scripts/migrate_workflow_step_confirm.py [--db PATH] [--no-backup]
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "data", "motor_pm_v2.db")
TABLE = "project_workflow_step_confirm"

# 与 ORM 模型逐列对应(顺序也保持一致,便于比对)
COLUMNS = [
    ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
    ("project_id", "INTEGER NOT NULL REFERENCES project(id)"),
    ("phase_id", "INTEGER NOT NULL REFERENCES phase(id)"),
    ("phase_code", "VARCHAR(16) NOT NULL"),
    ("node_seq", "INTEGER NOT NULL"),
    ("node_name", "VARCHAR(128)"),
    ("confirmed_by", "VARCHAR(64)"),
    ("confirmed_at", "DATETIME"),
    ("note", "TEXT"),
    ("created_at", "DATETIME"),
    ("updated_at", "DATETIME"),
]

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    {", ".join(f"{n} {t}" for n, t in COLUMNS)},
    CONSTRAINT uq_pwsc_step UNIQUE (project_id, phase_code, node_seq)
)
"""


def migrate(db_path, backup=True):
    if not os.path.exists(db_path):
        print(f"[错误] 数据库不存在: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    existed = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
    ).fetchone()
    if existed:
        cols = [r["name"] for r in conn.execute(f'PRAGMA table_info("{TABLE}")')]
        expect = [n for n, _ in COLUMNS]
        if cols == expect:
            n = conn.execute(f'SELECT COUNT(*) FROM "{TABLE}"').fetchone()[0]
            print(f"[跳过] {TABLE} 已存在且列一致({len(cols)} 列, {n} 行),无需处理")
            conn.close()
            return 0
        print(f"[警告] {TABLE} 已存在但列不一致,将只补缺失的列(不删不改既有列)")
        print(f"        现有: {cols}")
        print(f"        期望: {expect}")

    if backup:
        bdir = os.path.join(ROOT, "data", "backup")
        os.makedirs(bdir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = os.path.join(bdir, f"pre_workflow_step_confirm_{stamp}.db")
        shutil.copy2(db_path, bak)
        print(f"[备份] {bak}")

    conn.execute(DDL)
    conn.execute(f'CREATE INDEX IF NOT EXISTS idx_pwsc_project ON {TABLE} (project_id, phase_id)')
    conn.commit()

    # 校验: 列、唯一约束、行数
    cols = [r["name"] for r in conn.execute(f'PRAGMA table_info("{TABLE}")')]
    uq = [r["name"] for r in conn.execute(f'PRAGMA index_list("{TABLE}")') if r["unique"]]
    rows = conn.execute(f'SELECT COUNT(*) FROM "{TABLE}"').fetchone()[0]
    print(f"[完成] {TABLE}: {len(cols)} 列 {rows} 行, 唯一索引 {uq}")
    missing = [n for n, _ in COLUMNS if n not in cols]
    if missing:
        print(f"[警告] 缺列: {missing}")
        conn.close()
        return 1
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
