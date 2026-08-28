# -*- coding: utf-8 -*-
"""Startup migration for the department/role permission system.

所有步骤幂等，异常不阻断启动（防止 watchdog 重启循环）。
执行顺序（main.py startup 在 init_db() 之后调用）：
1. ensure_columns: user_auth 补 role_id 列（SQLite 无列迁移，须手动 ALTER）
2. 部门种子：team_member.department 去重
3. 内置角色种子：admin/editor/viewer/member
4. 遗留角色 biz → editor
5. role_id 回填（按 role 字符串匹配内置角色 code）
6. 旧 4 级 permissions 就地转换为 5 布尔矩阵
"""
import json
import logging

from sqlalchemy import text

from backend_v2.database import SessionLocal
from backend_v2.permissions import BUILTIN_ROLE_DEFAULTS, BUILTIN_ROLE_DESC, normalize_legacy_permissions

log = logging.getLogger("permission_migrate")


def _ensure_columns():
    """user_auth 补 role_id 列、department 补 permissions 列（不带 REFERENCES）。"""
    db = SessionLocal()
    try:
        cols = [r[1] for r in db.execute(text("PRAGMA table_info(user_auth)")).fetchall()]
        if "role_id" not in cols:
            db.execute(text("ALTER TABLE user_auth ADD COLUMN role_id INTEGER"))
            db.commit()
            log.info("user_auth 已补 role_id 列")
        else:
            log.info("user_auth.role_id 列已存在")
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


def run_all():
    """启动时执行全部迁移（幂等）。"""
    try:
        _ensure_columns()
        _seed_departments()
        _seed_builtin_roles()
        _migrate_legacy_roles()
        _migrate_legacy_permissions()
        _migrate_role_permissions()
        log.info("permission_migrate.run_all 完成")
    except Exception:
        log.exception("permission_migrate.run_all 异常（不阻断启动）")
