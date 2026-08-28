# -*- coding: utf-8 -*-
"""核对失效路径对应的文件是否存在于 NAS knowledge 目录。"""
import os, sqlite3

NAS_KB = r"\\10.136.101.13\easitech\个人文件夹\qianjia\麦克斯韦-AI项目管理平台工具后台资料存放\MotorPM_Live\uploads\knowledge"

conn = sqlite3.connect("D:/AI/motor-pm/data/motor_pm_v2.db")
cur = conn.cursor()
rows = cur.execute("SELECT id, name, file_path FROM project_document WHERE file_path LIKE 'D:\\AI\\motor-pm%'").fetchall()

missing = []
ok = 0
for did, name, fp in rows:
    fname = fp.replace("/", "\\").split("\\")[-1]
    if os.path.exists(os.path.join(NAS_KB, fname)):
        ok += 1
    else:
        missing.append((did, name, fname))
print(f"NAS 上存在: {ok} / {len(rows)}")
if missing:
    print("NAS 缺失 (id, name, fname):")
    for did, name, fname in missing:
        print(" ", did, "|", str(name)[:40], "|", fname)
