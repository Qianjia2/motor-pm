# -*- coding: utf-8 -*-
"""分析 project_document.file_path 的路径形态，找出失效的本地绝对路径。"""
import sqlite3
from collections import Counter

conn = sqlite3.connect("D:/AI/motor-pm/data/motor_pm_v2.db")
cur = conn.cursor()
rows = cur.execute("SELECT file_path FROM project_document WHERE file_path IS NOT NULL AND file_path != ''").fetchall()

prefixes = Counter()
for (fp,) in rows:
    p = fp.replace("/", "\\")
    if p.startswith("D:\\AI\\motor-pm\\data\\uploads\\"):
        prefixes["LOCAL-absolute (broken)"] += 1
    elif p.startswith("\\\\"):
        prefixes["UNC-absolute (NAS)"] += 1
    elif p.startswith("uploads\\"):
        prefixes["relative-uploads (ok)"] += 1
    else:
        prefixes["other: " + p[:50]] += 1
for k, v in prefixes.most_common():
    print(v, "|", k)

print("\n-- 失效路径文档 (id, name, fp) --")
for r in cur.execute("SELECT id, name, file_path FROM project_document WHERE file_path LIKE 'D:\\AI\\motor-pm%' OR file_path LIKE 'D:/AI/motor-pm%'"):
    print(r[0], "|", str(r[1])[:40], "|", str(r[2])[:80])
