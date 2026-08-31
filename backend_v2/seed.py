"""Seed reference data and default users for Motor PM v2."""
from backend_v2.database import SessionLocal, init_db
from backend_v2.models import Phase, Gate, TechnicalLine, Role, UserAuth
from backend_v2.auth import hash_password
from sqlalchemy import select


def seed():
    init_db()

    with SessionLocal() as db:
        # ── Phases (硬件 P0→PP5 / 软件 S0→S4, 与项目导航模块的 phase code 硬编码一致) ──
        phase_defs = [
            ("概念需求阶段", "P0", 1, "需求分析、技术方案概念设计，门径G1", "hardware"),
            ("方案设计阶段", "PP1", 2, "详细方案设计、仿真分析，门径G2", "hardware"),
            ("样机试制阶段", "PP2", 3, "工程图纸、BOM、工艺设计、零部件加工、样机装配，门径G3", "hardware"),
            ("验证阶段", "PP3", 4, "台架测试、DV/PV验证，门径G4", "hardware"),
            ("设计定型阶段", "PP4", 5, "设计冻结、生产移交、项目结题，门径G5", "hardware"),
            ("售后维护阶段", "PP5", 6, "量产支持、售后维护", "hardware"),
            ("需求分析阶段", "S0", 101, "需求调研、立项申请，门径G-S0", "software"),
            ("架构设计阶段", "S1", 102, "系统架构、技术选型，门径G-S1", "software"),
            ("开发编码阶段", "S2", 103, "模块开发、编码实现，门径G-S2", "software"),
            ("测试验证阶段", "S3", 104, "功能测试、集成测试，门径G-S3", "software"),
            ("发布交付阶段", "S4", 105, "发布上线、交付验收，门径G-S4", "software"),
        ]
        phase_ids = {}
        for name, code, sort, desc, ptype in phase_defs:
            existing = (db.execute(select(Phase).where(Phase.code == code))).scalar_one_or_none()
            if not existing:
                p = Phase(name=name, code=code, sort_order=sort, description=desc, project_type=ptype)
                db.add(p)
                db.flush()
                phase_ids[code] = p.id
            else:
                phase_ids[code] = existing.id

        # ── Gates (按阶段 code 关联 phase_id) ──
        gate_defs = [
            ("G1 概念评审", "G1", 1, "P0"),
            ("G2 方案评审", "G2", 2, "PP1"),
            ("G3 设计评审", "G3", 3, "PP2"),
            ("G4 试制评审", "G4", 4, "PP3"),
            ("G5 验证评审", "G5", 5, "PP4"),
            ("S0 需求评审", "G-S0", 101, "S0"),
            ("S1 架构评审", "G-S1", 102, "S1"),
            ("S2 开发完成", "G-S2", 103, "S2"),
            ("S3 测试完成", "G-S3", 104, "S3"),
            ("S4 发布交付", "G-S4", 105, "S4"),
        ]
        for name, code, sort, phase_code in gate_defs:
            existing = (db.execute(select(Gate).where(Gate.code == code))).scalar_one_or_none()
            if not existing:
                db.add(Gate(name=name, code=code, sort_order=sort, phase_id=phase_ids[phase_code]))
        db.flush()

        # ── Technical Lines ──
        lines = [
            ("控制算法", "算法", 1, "cpu"),
            ("控制软件", "软件", 2, "monitor"),
            ("控制硬件", "硬件", 3, "cpu"),
            ("电机结构", "结构", 4, "setting"),
            ("电机电磁", "电磁", 5, "magnet"),
            ("测试验证", "测试", 6, "checked"),
        ]
        for name, short, sort, icon in lines:
            existing = (db.execute(select(TechnicalLine).where(TechnicalLine.name == name))).scalar_one_or_none()
            if not existing:
                db.add(TechnicalLine(name=name, short_name=short, sort_order=sort, icon=icon))
        db.flush()

        # ── Roles ──
        roles = [
            ("项目经理", "PM", 1, True),
            ("算法工程师", "ALGO", 2, True),
            ("软件工程师", "SW", 3, True),
            ("硬件工程师", "HW", 4, True),
            ("结构工程师", "STRUCT", 5, True),
            ("电磁工程师", "EM", 6, True),
            ("测试工程师", "TEST", 7, True),
        ]
        for name, code, sort, is_core in roles:
            existing = (db.execute(select(Role).where(Role.code == code))).scalar_one_or_none()
            if not existing:
                db.add(Role(name=name, code=code, sort_order=sort, is_core=is_core))
        db.flush()

        # ── Default Users ──
        # 密码不再硬编码：INITIAL_ADMIN_PASSWORD 环境变量优先，未设置则随机生成并打印一次。
        # 已有库中的账号不会重置。
        import secrets as _secrets
        from backend_v2.config import settings as _settings
        admin_pwd = _settings.INITIAL_ADMIN_PASSWORD or _secrets.token_urlsafe(12)
        member_pwd = _settings.INITIAL_USER_PASSWORD or _secrets.token_urlsafe(12)
        users = [
            ("admin", admin_pwd, "admin"),
            ("jinzhaohai", member_pwd, "pm"),
            ("wangmingxuan", member_pwd, "pm"),
            ("lishupei", member_pwd, "member"),
            ("zhangxiang", member_pwd, "member"),
            ("liangweien", member_pwd, "member"),
            ("maxiaohao", member_pwd, "member"),
        ]
        admin_created = False
        for username, pwd, role in users:
            existing = (db.execute(select(UserAuth).where(UserAuth.username == username))).scalar_one_or_none()
            if not existing:
                db.add(UserAuth(username=username, password_hash=hash_password(pwd), role=role))
                if username == "admin":
                    admin_created = True

        db.commit()
        print("Seed data loaded successfully.")
        if admin_created:
            print(f"[seed] 初始管理员已创建: admin / {admin_pwd}（请尽快修改；其他账号初始密码见环境变量 INITIAL_USER_PASSWORD）")


if __name__ == "__main__":
    seed()
