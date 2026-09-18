# -*- coding: utf-8 -*-
"""迁移等价性验证：权限从「按部门算」改成「按人算」的切换当天，不能有人掉权限。

做法（**全程只碰副本，绝不写线上库**）：
1. 用 sqlite3.Connection.backup() 把 data/motor_pm_v2.db 拷到临时目录
2. 把 DATABASE_URL 指向副本（必须在 import backend_v2.* 之前设，engine 是 import 时建的）
3. BEFORE：用**冻结的旧算法**（permission_migrate._effective_matrix_legacy，部门优先）
   算出每个账号「今天实际生效」的矩阵
4. 跑一遍完整 run_all()（就是启动时会跑的那套）
5. AFTER：用**新引擎**（permissions.get_user_permissions，个人优先）再算一次
6. 逐账号逐模块逐动作比对，必须 100% 一致

为什么 BEFORE 要用旧算法而不是直接读库：线上库里 9 个账号的 permissions 存着
从没生效过的旧 8 模块矩阵，直接读列会把「没生效过的值」当成现状。旧算法才是
「今天用户登录进来实际看到什么」的唯一正确表述。

顺带验证幂等：再跑一遍 run_all()，第二次必须一行都不改。

用法：python -m backend_v2.scripts.verify_permission_equivalence
退出码 0 = 全部一致；1 = 存在差异（会逐条打印）。
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "data" / "motor_pm_v2.db"


def _copy_live_db(tmpdir: Path) -> Path:
    """只读打开线上库 + backup() 到副本。backup API 保证读到一致快照，不受并发写影响。"""
    copy = tmpdir / "motor_pm_v2_copy.db"
    src = sqlite3.connect(f"file:{LIVE}?mode=ro", uri=True)
    dst = sqlite3.connect(str(copy))
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    return copy


def _fingerprint(matrix) -> str:
    """把矩阵压成一行可比对指纹：按模块顺序列出开着的动作。"""
    from backend_v2.permissions import ACTIONS, MODULES
    out = []
    for m in MODULES:
        open_acts = [a for a in ACTIONS if matrix.get(m, {}).get(a)]
        out.append(f"{m}={'+'.join(open_acts) if open_acts else '-'}")
    return "|".join(out)


def main() -> int:
    if not LIVE.exists():
        print(f"[FATAL] 线上库不存在: {LIVE}")
        return 1

    tmpdir = Path(tempfile.mkdtemp(prefix="perm_equiv_"))
    copy = _copy_live_db(tmpdir)
    print(f"[1] 已备份线上库 → {copy}  ({copy.stat().st_size} bytes)")

    # 必须在 import backend_v2.* 之前设：database.py 在 import 时就 create_engine
    os.environ["DATABASE_URL"] = "sqlite:///" + str(copy).replace("\\", "/")
    os.environ["DATA_DIR"] = str(tmpdir)
    os.environ["UPLOAD_DIR"] = str(tmpdir / "uploads")

    from backend_v2.database import SessionLocal, engine
    from backend_v2.models import UserAuth
    from backend_v2.permission_migrate import _effective_matrix_legacy, _ensure_columns, run_all
    from backend_v2.permissions import get_user_permissions

    # 安全闸：引擎没指向副本就立刻停——下面 run_all() 会写库。
    # 比的是规范化后的绝对路径：SQLite URL 用正斜杠，Windows 的 str(Path) 用反斜杠，
    # 直接比字符串会误判（并且这个闸门误判的代价只是拒绝运行，不会写错库）。
    def _norm(p) -> str:
        return str(p).replace("\\", "/").lower()

    if _norm(copy) not in _norm(engine.url):
        print(f"[FATAL] 引擎指向 {engine.url}，不是副本，拒绝继续")
        return 1
    print(f"[2] 引擎已指向副本: {engine.url}")
    print(f"[3] 线上库只读打开、未被写入: {LIVE}")

    # 先只补列（run_all 的第 1 步）。纯 schema 变更不改数据，但 ORM 的 UserAuth
    # 声明了 perm_source，不补列连 SELECT 都会炸。之所以单独提前跑：BEFORE 快照
    # 必须在这之后、任何数据变更之前拿到。
    _ensure_columns()

    # 人员档案快照：team_member 是部门归属的载体，迁移只该**读**它，一行都不该改。
    # 计划里点名要覆盖「department 为空的 team_member 行」——其中没有账号的那部分
    # 在账号比对里根本不会出现，得单独看。
    from sqlalchemy import text as _text

    def _members():
        d = SessionLocal()
        try:
            rows = d.execute(
                _text("SELECT id, name, COALESCE(department,'') FROM team_member ORDER BY id")
            ).fetchall()
            linked = {
                r[0] for r in d.execute(
                    _text("SELECT member_id FROM user_auth WHERE member_id IS NOT NULL")
                ).fetchall()
            }
            return rows, linked
        finally:
            d.close()

    members_before, linked_ids = _members()
    empty_members = [r[0] for r in members_before if not r[2].strip()]
    empty_no_acct = [i for i in empty_members if i not in linked_ids]
    print(f"[4b] team_member 共 {len(members_before)} 行；department 为空 {len(empty_members)} 行 {empty_members}")
    print(f"     其中未绑定账号 {len(empty_no_acct)} 行 {empty_no_acct}（不参与权限计算，仅确认迁移没动它们）")

    # ── BEFORE：冻结的旧算法 ──
    db = SessionLocal()
    try:
        users = db.query(UserAuth).order_by(UserAuth.id).all()
        before = {}
        meta = {}
        for u in users:
            before[u.id] = _fingerprint(_effective_matrix_legacy(db, u))
            raw = (u.permissions or "").strip()
            dept = (u.member.department if u.member else None) or ""
            meta[u.id] = {
                "username": u.username,
                "role": u.role,
                "dept": dept,
                "perm_source_before": u.perm_source,
                # 「休眠旧值」= 非空非 {}，且**从没生效过**（部门分支挡住的那 9 个）
                "dormant": raw not in ("", "{}"),
                "raw_before": raw,
            }
    finally:
        db.close()
    print(f"[4] BEFORE 快照: {len(before)} 个账号")

    # ── 跑迁移 ──
    run_all()
    print("[5] run_all() 执行完毕")

    # ── AFTER：新引擎 ──
    db = SessionLocal()
    try:
        users = db.query(UserAuth).order_by(UserAuth.id).all()
        after = {u.id: _fingerprint(get_user_permissions(u)) for u in users}
        source_after = {u.id: u.perm_source for u in users}
        raw_after = {u.id: (u.permissions or "").strip() for u in users}
        # 幂等：第二遍 run_all 后逐行比 permissions / perm_source
    finally:
        db.close()

    # ── 比对 ──
    diffs = []
    for uid in sorted(before):
        if before[uid] != after.get(uid):
            diffs.append(uid)

    print("\n" + "=" * 100)
    print("逐账号比对（BEFORE=旧算法部门优先 / AFTER=新引擎个人优先）")
    print("=" * 100)
    print(f"{'id':>3} {'账号':<16} {'角色':<7} {'部门':<12} {'来源':<7} {'休眠':<5} 结果")
    print("-" * 100)
    for uid in sorted(before):
        m = meta[uid]
        ok = "OK" if uid not in diffs else "**DIFF**"
        print(
            f"{uid:>3} {m['username']:<16} {m['role']:<7} {(m['dept'] or '(空)'):<12} "
            f"{str(source_after.get(uid)):<7} {'是' if m['dormant'] else '否':<5} {ok}"
        )

    print("-" * 100)
    empty_dept = [u for u in sorted(before) if not meta[u]["dept"]]
    dormant = [u for u in sorted(before) if meta[u]["dormant"]]
    admins = [u for u in sorted(before) if meta[u]["role"] == "admin"]
    print(f"账号总数 {len(before)} | 部门为空 {len(empty_dept)} 个 {empty_dept} | "
          f"休眠旧值 {len(dormant)} 个 {dormant} | admin {len(admins)} 个 {admins}")

    if diffs:
        print("\n" + "!" * 100)
        print(f"存在 {len(diffs)} 处权限差异——切换当天这些人会掉权限，不能上线：")
        for uid in diffs:
            print(f"\n--- user id={uid} {meta[uid]['username']} (role={meta[uid]['role']}, "
                  f"dept={meta[uid]['dept'] or '(空)'}) ---")
            b = before[uid].split("|")
            a = after[uid].split("|")
            missing = [x for x in b if x not in a]
            gained = [x for x in a if x not in b]
            print(f"    掉权限: {missing or '无'}")
            print(f"    多权限: {gained or '无'}")
        print("!" * 100)

    # ── 幂等：第二遍不得再改任何行 ──
    snapshot = dict(raw_after)
    source_snapshot = dict(source_after)
    run_all()
    db = SessionLocal()
    try:
        changed = []
        for u in db.query(UserAuth).order_by(UserAuth.id).all():
            if (u.permissions or "").strip() != snapshot.get(u.id) or u.perm_source != source_snapshot.get(u.id):
                changed.append(u.id)
    finally:
        db.close()
    print(f"\n[6] 幂等检查：第二遍 run_all() 改动了 {len(changed)} 行 {changed if changed else '(应为 0)'}")

    # ── team_member 必须一行没动 ──
    members_after, _ = _members()
    member_drift = [
        (b[0], b[2], a[2])
        for b, a in zip(members_before, members_after)
        if (b[0], b[2]) != (a[0], a[2])
    ]
    print(f"[7] team_member 漂移检查：{len(member_drift)} 行 {member_drift[:5] if member_drift else '(应为 0)'}")

    ok = not diffs and not changed and not member_drift
    print("\n" + ("=" * 100))
    print("结论：迁移前后权限 100% 一致 ✅" if ok else "结论：存在差异 ❌ —— 不可上线")
    print("=" * 100)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
