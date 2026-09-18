# -*- coding: utf-8 -*-
"""Startup migration for the department/role permission system.

所有步骤幂等，异常不阻断启动（防止 watchdog 重启循环）。
执行顺序（main.py startup 在 init_db() 之后调用，**同步**执行完才对外服务，
所以不存在「回填没跑完就有请求进来」的窗口）：
1. ensure_columns: user_auth 补 role_id / perm_source 列（SQLite 无列迁移，须手动 ALTER）
2. 部门种子：team_member.department 去重
3. 内置角色种子：admin/editor/viewer/member
4. 遗留角色 biz → editor
5. role_id 回填（按 role 字符串匹配内置角色 code）
6. 旧 4 级 permissions 就地转换为 5 布尔矩阵
7. 角色矩阵升级到 16 模块
8. **个人权限回填**：把每人当前生效的矩阵固化到 user_auth.permissions（必须最后跑）
"""
import json
import logging

from sqlalchemy import select, text

from backend_v2.database import SessionLocal
from backend_v2.permissions import (
    ACTIONS,
    BUILTIN_ROLE_DEFAULTS,
    BUILTIN_ROLE_DESC,
    MODULES,
    matrix_has_any,
    normalize_legacy_permissions,
)

log = logging.getLogger("permission_migrate")


def _ensure_columns():
    """user_auth 补 role_id / perm_source 列、department 补 permissions 列（不带 REFERENCES）。"""
    db = SessionLocal()
    try:
        cols = [r[1] for r in db.execute(text("PRAGMA table_info(user_auth)")).fetchall()]
        if "role_id" not in cols:
            db.execute(text("ALTER TABLE user_auth ADD COLUMN role_id INTEGER"))
            db.commit()
            log.info("user_auth 已补 role_id 列")
        else:
            log.info("user_auth.role_id 列已存在")
        if "perm_source" not in cols:
            db.execute(text("ALTER TABLE user_auth ADD COLUMN perm_source TEXT"))
            db.commit()
            log.info("user_auth 已补 perm_source 列")
        else:
            log.info("user_auth.perm_source 列已存在")
        dept_cols = [r[1] for r in db.execute(text("PRAGMA table_info(department)")).fetchall()]
        if "permissions" not in dept_cols:
            db.execute(text("ALTER TABLE department ADD COLUMN permissions TEXT"))
            db.commit()
            log.info("department 已补 permissions 列")
        else:
            log.info("department.permissions 列已存在")
    except Exception:
        log.exception("ensure_columns 失败")
    finally:
        db.close()


def _seed_departments():
    """部门种子：team_member.department 去重。"""
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT DISTINCT department FROM team_member WHERE department IS NOT NULL AND trim(department) != ''")
        ).fetchall()
        order = 0
        added = 0
        for (name,) in rows:
            name = name.strip()
            exists = db.execute(text("SELECT id FROM department WHERE name = :n"), {"n": name}).fetchone()
            if not exists:
                db.execute(
                    text("INSERT INTO department (name, sort_order, is_active, created_at) VALUES (:n, :o, 1, datetime('now'))"),
                    {"n": name, "o": order},
                )
                added += 1
            order += 1
        db.commit()
        log.info("部门种子: 新增 %s / 共 %s 个", added, len(rows))
    except Exception:
        log.exception("seed_departments 失败")
    finally:
        db.close()


def _seed_builtin_roles():
    """内置角色种子：code 对齐旧 role 值；已存在则不覆盖（保留用户修改）。"""
    db = SessionLocal()
    try:
        for idx, code in enumerate(["admin", "editor", "viewer", "member"]):
            exists = db.execute(text("SELECT id FROM permission_role WHERE code = :c"), {"c": code}).fetchone()
            if exists:
                continue
            db.execute(
                text(
                    "INSERT INTO permission_role (name, code, dept_id, permissions, desc, is_builtin, sort_order, created_at) "
                    "VALUES (:name, :code, NULL, :perms, :desc, 1, :order, datetime('now'))"
                ),
                {
                    "name": {"admin": "管理员", "editor": "编辑者", "viewer": "查看者", "member": "成员"}[code],
                    "code": code,
                    "perms": json.dumps(BUILTIN_ROLE_DEFAULTS[code], ensure_ascii=False),
                    "desc": BUILTIN_ROLE_DESC[code],
                    "order": idx,
                },
            )
        db.commit()
        log.info("内置角色种子完成")
    except Exception:
        log.exception("seed_builtin_roles 失败")
    finally:
        db.close()


def _migrate_legacy_roles():
    """biz 遗留角色 → editor；role_id 回填。"""
    db = SessionLocal()
    try:
        n = db.execute(text("UPDATE user_auth SET role = 'editor' WHERE role = 'biz'")).rowcount
        if n:
            log.info("遗留角色 biz → editor: %s 行", n)
        users = db.execute(text("SELECT id, role FROM user_auth")).fetchall()
        backfilled = 0
        for uid, role in users:
            if role in ("admin", "editor", "viewer", "member"):
                r = db.execute(
                    text("SELECT id FROM permission_role WHERE code = :c AND is_builtin = 1"), {"c": role}
                ).fetchone()
                if r:
                    db.execute(text("UPDATE user_auth SET role_id = :rid WHERE id = :uid AND role_id IS NULL"), {"rid": r[0], "uid": uid})
                    backfilled += 1
        db.commit()
        log.info("role_id 回填: %s 行", backfilled)
    except Exception:
        log.exception("migrate_legacy_roles 失败")
    finally:
        db.close()


def _migrate_role_permissions():
    """把 permission_role 现有矩阵升级到新 16 模块结构（旧 8 模块按映射展开）。"""
    db = SessionLocal()
    try:
        rows = db.execute(text("SELECT id, permissions FROM permission_role")).fetchall()
        converted = 0
        for rid, raw in rows:
            if not raw:
                continue
            data = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, dict):
                continue
            matrix = normalize_legacy_permissions(data)
            out = json.dumps(matrix, ensure_ascii=False)
            if out != raw:
                db.execute(
                    text("UPDATE permission_role SET permissions = :p WHERE id = :rid"),
                    {"p": out, "rid": rid},
                )
                converted += 1
        db.commit()
        log.info("角色矩阵升级 16 模块: %s 行", converted)
    except Exception:
        log.exception("migrate_role_permissions 失败")
    finally:
        db.close()


def _migrate_legacy_permissions():
    """旧 4 级 permissions（字符串值）就地转换为 5 布尔矩阵。"""
    db = SessionLocal()
    try:
        rows = db.execute(text("SELECT id, permissions FROM user_auth")).fetchall()
        converted = 0
        for uid, raw in rows:
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            has_legacy = any(isinstance(v, str) for v in data.values())
            if not has_legacy:
                continue
            matrix = normalize_legacy_permissions(data)
            db.execute(
                text("UPDATE user_auth SET permissions = :p WHERE id = :uid"),
                {"p": json.dumps(matrix, ensure_ascii=False), "uid": uid},
            )
            converted += 1
        db.commit()
        log.info("旧 permissions 转换: %s 行", converted)
    except Exception:
        log.exception("migrate_legacy_permissions 失败")
    finally:
        db.close()


def _effective_matrix_legacy(db, u):
    """**冻结的**旧版生效矩阵算法（部门优先）。

    这是 2026-09-11「权限改为按人」改造前 get_user_permissions 的副本。
    **故意不与主逻辑共用**：迁移要的是「改造前那一刻的算法」，共用会让它随主逻辑
    漂移——主逻辑已经变成「个人优先」，拿它算等于把结果当输入，回头再跑也不是
    「冻结现状」了。这段是历史快照，除非要重跑历史迁移，否则别改。
    """
    from backend_v2.models import Department, PermissionRole

    role = u.role or "member"
    if role == "admin":
        return {m: {a: True for a in ACTIONS} for m in MODULES}

    # 部门矩阵（权威）：人员资料的部门文本 → 部门表 → 部门权限矩阵
    dept_name = u.member.department if u.member else None
    if dept_name:
        dept = db.execute(
            select(Department).where(Department.name == dept_name, Department.is_active == True)
        ).scalar_one_or_none()
        if dept and dept.permissions:
            matrix = normalize_legacy_permissions(dept.permissions)
            if matrix_has_any(matrix):
                return matrix

    # 角色矩阵兜底（role_id）→ 内置默认（role 字符串）
    matrix = None
    if u.role_id:
        pr = db.get(PermissionRole, u.role_id)
        if pr and pr.permissions:
            matrix = normalize_legacy_permissions(pr.permissions)
    if matrix is None:
        matrix = normalize_legacy_permissions(
            BUILTIN_ROLE_DEFAULTS.get(role, BUILTIN_ROLE_DEFAULTS["member"])
        )
    return matrix


def _backfill_personal_permissions():
    """把每个账号「当前实际生效」的权限固化成个人矩阵（一次性）。

    权限来源从「按部门算」改成「按人算」。为了让切换当天所有人权限一模一样、
    没人登进来发现菜单变了，这里先把每个人当前生效的矩阵写进 user_auth.permissions；
    之后 get_user_permissions 认这一份，部门矩阵退居为模板。

    两条关键约定：
    1. 只处理 perm_source IS NULL 的行。跑完这列就有值，第二次启动匹配 0 行，
       幂等不靠「值长得像」——「已回填」和「用户后来手改过」在数据上一模一样，
       用值判定会把用户手改的权限覆盖掉。
    2. 原值非空非 {} 的先写进 audit_log 备查。线上有 9 个账号的 permissions 存着
       **从没生效过**的旧 8 模块矩阵，按「冻结现状」的约定不进计算，但原值得留痕。

    admin 跳过：反正 get_user_permissions 对他们直接全开，写了是噪音。
    """
    from backend_v2.audit import log_audit

    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT id FROM user_auth WHERE perm_source IS NULL ORDER BY id")
        ).fetchall()
        if not rows:
            log.info("个人权限回填: 无待处理行")
            return
        from backend_v2.models import UserAuth

        backfilled = audited = 0
        for (uid,) in rows:
            u = db.get(UserAuth, uid)
            if u is None:
                continue
            if u.role == "admin":
                db.execute(
                    text("UPDATE user_auth SET perm_source = 'dept' WHERE id = :i"), {"i": uid}
                )
                continue
            raw = (u.permissions or "").strip()
            if raw and raw != "{}":
                log_audit(
                    db, "system", "权限迁移留痕", "user_auth", uid, u.username,
                    summary=f"改造为按人授权前的个人 permissions 原值（未生效过，仅留痕）",
                    details=raw,
                )
                audited += 1
            matrix = _effective_matrix_legacy(db, u)
            db.execute(
                text("UPDATE user_auth SET permissions = :p, perm_source = 'dept' WHERE id = :i"),
                {"p": json.dumps(matrix, ensure_ascii=False), "i": uid},
            )
            backfilled += 1
        db.commit()
        log.info("个人权限回填: %s 行（其中 %s 行原值非空已留痕）", backfilled, audited)
    except Exception:
        db.rollback()
        log.exception("backfill_personal_permissions 失败")
    finally:
        db.close()


def run_all():
    """启动时执行全部迁移（幂等）。"""
    try:
        _ensure_columns()
        _seed_departments()
        _seed_builtin_roles()
        _migrate_legacy_roles()
        _migrate_legacy_permissions()
        _migrate_role_permissions()
        # 必须放最后:上面几步会改写 user_auth.permissions,回填要读的是它们处理完的结果
        _backfill_personal_permissions()
        log.info("permission_migrate.run_all 完成")
    except Exception:
        log.exception("permission_migrate.run_all 异常（不阻断启动）")
