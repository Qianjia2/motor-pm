# -*- coding: utf-8 -*-
"""把失效的本地绝对路径 file_path 迁移为相对路径 uploads\\knowledge\\<file>。"""
import sqlite3

conn = sqlite3.connect("D:/AI/motor-pm/data/motor_pm_v2.db")
cur = conn.cursor()

rows = cur.execute(
    "SELECT id, file_path FROM project_document WHERE file_path LIKE 'D:\\AI\\motor-pm%' OR file_path LIKE 'D:/AI/motor-pm%'"
).fetchall()
print(f"待迁移: {len(rows)}")

done = 0
for did, fp in rows:
    fname = fp.replace("/", "\\").split("\\")[-1]
    new_fp = "uploads\\knowledge\\" + fname
    cur.execute("UPDATE project_document SET file_path = ? WHERE id = ?", (new_fp, did))
    done += 1
conn.commit()
print(f"已更新: {done}")
# 复核
remain = cur.execute("SELECT COUNT(*) FROM project_document WHERE file_path LIKE 'D:\\AI\\motor-pm%' OR file_path LIKE 'D:/AI/motor-pm%'").fetchone()[0]
print(f"剩余本地绝对路径: {remain}")
conn.close()
