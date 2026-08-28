"""Seed reference data and default users for Motor PM v2."""
from backend_v2.database import SessionLocal, init_db
from backend_v2.models import Phase, Gate, TechnicalLine, Role, UserAuth
from backend_v2.auth import hash_password
from sqlalchemy import select


def seed():
    init_db()

    with SessionLocal() as db:
        # ── Phases ──
        phases = [
            ("概念阶段", "CONCEPT", 1, "需求分析、技术方案概念设计，门径G1"),
            ("方案阶段", "SCHEME", 2, "详细方案设计、仿真分析，门径G2"),
            ("详细设计", "DETAIL", 3, "工程图纸、BOM、工艺设计，门径G3"),
            ("样机试制", "PROTOTYPE", 4, "零部件加工、样机装配，门径G4"),
            ("测试验证", "VERIFY", 5, "台架测试、DV/PV验证，门径G5"),
            ("设计定型", "FINAL", 6, "设计冻结、生产移交、项目结题"),
        ]
        for i, (name, code, sort, desc) in enumerate(phases):
            existing = (db.execute(select(Phase).where(Phase.code == code))).scalar_one_or_none()
            if not existing:
                db.add(Phase(name=name, code=code, sort_order=sort, description=desc))
        db.flush()

        # ── Gates ──
        gates = [
            ("G1 概念评审", "G1", 1, 1),
            ("G2 方案评审", "G2", 2, 2),
            ("G3 设计评审", "G3", 3, 3),
            ("G4 试制评审", "G4", 4, 4),
            ("G5 验证评审", "G5", 5, 5),
        ]
        for name, code, sort, phase_id in gates:
            existing = (db.execute(select(Gate).where(Gate.code == code))).scalar_one_or_none()
            if not existing:
                db.add(Gate(name=name, code=code, sort_order=sort, phase_id=phase_id))
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
        users = [
            ("admin", "admin123", "admin"),
            ("jinzhaohai", "jin123", "pm"),
            ("wangmingxuan", "wang123", "pm"),
            ("lishupei", "123", "member"),
            ("zhangxiang", "123", "member"),
            ("liangweien", "123", "member"),
            ("maxiaohao", "123", "member"),
        ]
        for username, pwd, role in users:
            existing = (db.execute(select(UserAuth).where(UserAuth.username == username))).scalar_one_or_none()
            if not existing:
                db.add(UserAuth(username=username, password_hash=hash_password(pwd), role=role))

        db.commit()
        print("Seed data loaded successfully.")


if __name__ == "__main__":
    seed()
