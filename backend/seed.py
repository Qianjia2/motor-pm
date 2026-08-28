"""Seed reference data and demo projects into the database."""
from datetime import date, timedelta
from backend import db
from backend.models import (
    Phase, Gate, TechnicalLine, Role,
    Project, TeamMember, ProjectMember, ProjectPhaseGate,
    Milestone, Deliverable, UserAuth
)
from backend.utils import compute_risk_level


def seed_all():
    # Only seed if no reference data exists
    if Phase.query.first():
        # But seed users if they're missing
        if not UserAuth.query.first():
            _seed_users()
        return

    # ── 参考数据 ──────────────────────────────────

    phases = [
        Phase(id=1, name='概念阶段', code='CONCEPT', sort_order=1, description='确认要不要做、能不能做、划不划算'),
        Phase(id=2, name='方案阶段', code='SCHEME', sort_order=2, description='方案设计、技术路线选定'),
        Phase(id=3, name='详细设计', code='DESIGN', sort_order=3, description='各专业详细设计、图纸、仿真'),
        Phase(id=4, name='样机试制', code='PROTOTYPE', sort_order=4, description='样机制造、装配、调试'),
        Phase(id=5, name='测试验证', code='TEST', sort_order=5, description='部件测试、集成测试、型式试验'),
        Phase(id=6, name='量产交付', code='DELIVERY', sort_order=6, description='量产准备、文件归档、项目移交'),
    ]
    db.session.add_all(phases)

    gates = [
        Gate(id=1, name='方案评审 G1', code='G1', sort_order=1, phase_id=2),
        Gate(id=2, name='设计评审 G2', code='G2', sort_order=2, phase_id=3),
        Gate(id=3, name='试制评审 G3', code='G3', sort_order=3, phase_id=4),
        Gate(id=4, name='测试评审 G4', code='G4', sort_order=4, phase_id=5),
        Gate(id=5, name='量产评审 G5', code='G5', sort_order=5, phase_id=6),
    ]
    db.session.add_all(gates)

    lines = [
        TechnicalLine(id=1, name='电机电磁', short_name='电磁', sort_order=1, icon='magnet'),
        TechnicalLine(id=2, name='电机结构', short_name='结构', sort_order=2, icon='cube'),
        TechnicalLine(id=3, name='控制硬件', short_name='硬件', sort_order=3, icon='cpu'),
        TechnicalLine(id=4, name='控制算法', short_name='算法', sort_order=4, icon='function'),
        TechnicalLine(id=5, name='控制软件', short_name='软件', sort_order=5, icon='code'),
        TechnicalLine(id=6, name='测试验证', short_name='测试', sort_order=6, icon='check-circle'),
    ]
    db.session.add_all(lines)

    roles = [
        Role(id=1, name='项目经理', code='PM', sort_order=1, is_core=True),
        Role(id=2, name='技术负责人', code='SE', sort_order=2, is_core=True),
        Role(id=3, name='电磁负责人', code='EM', sort_order=3, is_core=True),
        Role(id=4, name='结构负责人', code='STR', sort_order=4, is_core=True),
        Role(id=5, name='硬件负责人', code='HW', sort_order=5, is_core=True),
        Role(id=6, name='算法负责人', code='ALG', sort_order=6, is_core=True),
        Role(id=7, name='软件负责人', code='SW', sort_order=7, is_core=True),
        Role(id=8, name='测试负责人', code='TEST', sort_order=8, is_core=True),
        Role(id=9, name='质量负责人', code='QA', sort_order=9, is_core=True),
    ]
    db.session.add_all(roles)

    # ── 演示人员 ──────────────────────────────────

    people = [
        TeamMember(id=1, name='张工', department='项目管理部', title='高级项目经理', email='zhang@example.com', is_active=True),
        TeamMember(id=2, name='李博士', department='研发中心', title='技术总监', email='li@example.com', is_active=True),
        TeamMember(id=3, name='王工', department='电磁部', title='电磁工程师', email='wang@example.com', is_active=True),
        TeamMember(id=4, name='赵工', department='结构部', title='结构工程师', email='zhao@example.com', is_active=True),
        TeamMember(id=5, name='钱工', department='硬件部', title='硬件工程师', email='qian@example.com', is_active=True),
        TeamMember(id=6, name='孙工', department='算法部', title='算法工程师', email='sun@example.com', is_active=True),
        TeamMember(id=7, name='周工', department='软件部', title='嵌入式工程师', email='zhou@example.com', is_active=True),
        TeamMember(id=8, name='吴工', department='测试部', title='测试工程师', email='wu@example.com', is_active=True),
        TeamMember(id=9, name='陈工', department='质量部', title='质量工程师', email='chen@example.com', is_active=True),
    ]
    db.session.add_all(people)

    # ── 演示项目 ──────────────────────────────────

    proj1 = Project(
        name='200kW永磁同步电机驱动器开发',
        code='P2026-EM001',
        description='为新能源商用车开发200kW永磁同步电机及其控制器，含电磁设计、结构设计、控制硬件、控制算法、嵌入式软件、系统测试全流程。',
        current_phase_id=2,
        start_date=date.today() - timedelta(days=90),
        planned_end_date=date.today() + timedelta(days=275),
        overall_status='normal',
        completion_pct=25,
        problem_statement='商用车电动化需要高效、高功率密度的电驱系统',
        final_deliverable='200kW电机本体样机2台 + 控制器样机2台 + 型式试验报告 + 量产工艺文件',
        acceptance_criteria='额定功率200kW，峰值功率250kW，最高效率≥96%，通过GB/T 18488型式试验',
        aligned_target='公司新能源商用车动力总成战略',
        deadline_type='硬性',
        priority='P0',
        difficulty='high',
        budget_total=8000000,
        budget_spent=1500000,
    )
    proj2 = Project(
        name='15kW伺服电机控制系统',
        code='P2026-EM002',
        description='工业机器人关节用15kW伺服电机及驱动器，高精度位置控制，低齿槽转矩。',
        current_phase_id=3,
        start_date=date.today() - timedelta(days=150),
        planned_end_date=date.today() + timedelta(days=150),
        overall_status='risk',
        completion_pct=45,
        problem_statement='国产替代进口伺服系统，降低工业机器人成本',
        final_deliverable='伺服电机样机3台 + 驱动器样机3台 + 精度测试报告 + 可靠性测试报告',
        acceptance_criteria='位置精度±0.01°，速度范围0.1-3000rpm，转矩波动<3%',
        aligned_target='工业自动化产品线战略',
        deadline_type='硬性',
        priority='P1',
        difficulty='medium',
        budget_total=3000000,
        budget_spent=1800000,
        main_blocker='控制硬件EMC测试不通过，PCB需重新设计',
        blocker_duration='1-4 周',
        morale='中等',
    )
    db.session.add_all([proj1, proj2])
    db.session.flush()

    # ── 演示项目成员分配 ──────────────────────────

    pm_members = [
        ProjectMember(project_id=proj1.id, member_id=1, role_id=1, allocation_pct=50, is_key=True),
        ProjectMember(project_id=proj1.id, member_id=2, role_id=2, allocation_pct=30, is_key=True),
        ProjectMember(project_id=proj1.id, member_id=3, role_id=3, allocation_pct=80),
        ProjectMember(project_id=proj1.id, member_id=4, role_id=4, allocation_pct=60),
        ProjectMember(project_id=proj1.id, member_id=5, role_id=5, allocation_pct=70),
        ProjectMember(project_id=proj1.id, member_id=6, role_id=6, allocation_pct=60),
        ProjectMember(project_id=proj1.id, member_id=7, role_id=7, allocation_pct=50),
        ProjectMember(project_id=proj1.id, member_id=8, role_id=8, allocation_pct=30),
        ProjectMember(project_id=proj1.id, member_id=9, role_id=9, allocation_pct=20),
        ProjectMember(project_id=proj2.id, member_id=1, role_id=1, allocation_pct=50, is_key=True),
        ProjectMember(project_id=proj2.id, member_id=2, role_id=2, allocation_pct=30, is_key=True),
        ProjectMember(project_id=proj2.id, member_id=5, role_id=5, allocation_pct=80),
        ProjectMember(project_id=proj2.id, member_id=6, role_id=6, allocation_pct=70),
        ProjectMember(project_id=proj2.id, member_id=7, role_id=7, allocation_pct=60),
        ProjectMember(project_id=proj2.id, member_id=8, role_id=8, allocation_pct=50),
    ]
    db.session.add_all(pm_members)

    # ── 演示项目阶段门径 ──────────────────────────

    pg_data = []
    for proj in [proj1, proj2]:
        for phase_id in range(1, 7):
            offset = (phase_id - 1) * 45
            days_behind = 0 if proj == proj1 else (15 if phase_id > 2 else 0)
            actual_start = proj.start_date + timedelta(days=offset - days_behind) if phase_id <= proj.current_phase_id else None
            actual_end = actual_start + timedelta(days=40) if actual_start else None
            gate = Gate.query.filter_by(phase_id=phase_id).first()
            pg = ProjectPhaseGate(
                project_id=proj.id,
                phase_id=phase_id,
                gate_id=gate.id if gate else None,
                planned_start_date=proj.start_date + timedelta(days=offset),
                planned_end_date=proj.start_date + timedelta(days=offset + 40),
                actual_start_date=actual_start,
                actual_end_date=actual_end,
                status='completed' if phase_id < proj.current_phase_id else ('in_progress' if phase_id == proj.current_phase_id else 'not_started'),
                gate_status='passed' if phase_id < proj.current_phase_id else (None if phase_id >= proj.current_phase_id else 'pending'),
            )
            pg_data.append(pg)
    db.session.add_all(pg_data)

    # ── 演示里程碑 ────────────────────────────────

    mstones = [
        Milestone(project_id=proj1.id, name='电磁方案确定', planned_date=date.today() - timedelta(days=30), actual_date=date.today() - timedelta(days=28), line_id=1, phase_id=2, status='completed', is_key=True, sort_order=1),
        Milestone(project_id=proj1.id, name='控制器原理图完成', planned_date=date.today() + timedelta(days=30), line_id=3, phase_id=3, status='in_progress', is_key=True, sort_order=2),
        Milestone(project_id=proj1.id, name='首台样机下线', planned_date=date.today() + timedelta(days=120), line_id=6, phase_id=4, status='pending', is_key=True, sort_order=3),
        Milestone(project_id=proj1.id, name='型式试验通过', planned_date=date.today() + timedelta(days=210), line_id=6, phase_id=5, status='pending', is_key=True, sort_order=4),
        Milestone(project_id=proj1.id, name='量产SOP', planned_date=date.today() + timedelta(days=275), line_id=4, phase_id=6, status='pending', is_key=True, sort_order=5),
        Milestone(project_id=proj2.id, name='结构3D冻结', planned_date=date.today() - timedelta(days=60), actual_date=date.today() - timedelta(days=55), line_id=2, phase_id=3, status='completed', is_key=True, sort_order=1),
        Milestone(project_id=proj2.id, name='EMC测试通过', planned_date=date.today() + timedelta(days=20), line_id=5, phase_id=4, status='in_progress', is_key=True, sort_order=2),
        Milestone(project_id=proj2.id, name='客户验收', planned_date=date.today() + timedelta(days=150), line_id=6, phase_id=5, status='pending', is_key=True, sort_order=3),
    ]
    db.session.add_all(mstones)

    # ── 演示交付物 ────────────────────────────────

    deliverables = [
        Deliverable(project_id=proj1.id, phase_id=1, line_id=1, name='电磁可行性分析报告', status='submitted'),
        Deliverable(project_id=proj1.id, phase_id=1, line_id=3, name='硬件方案可行性分析', status='submitted'),
        Deliverable(project_id=proj1.id, phase_id=2, line_id=1, name='电磁方案设计报告', status='submitted'),
        Deliverable(project_id=proj1.id, phase_id=2, line_id=2, name='结构方案设计报告', status='submitted'),
        Deliverable(project_id=proj1.id, phase_id=2, line_id=3, name='硬件方案设计报告', status='not_submitted'),
        Deliverable(project_id=proj1.id, phase_id=2, line_id=4, name='算法方案设计报告', status='not_submitted'),
    ]
    db.session.add_all(deliverables)

    _seed_users()

    db.session.commit()
    print('Seed data created: phases, gates, lines, roles, 2 demo projects, 9 people, 10 user accounts.')


def _seed_users():
    users = [
        UserAuth(username='admin', password_hash=UserAuth.hash_password('admin123'), member_id=None, role='admin'),
        UserAuth(username='jinzhaohai', password_hash=UserAuth.hash_password('jin123'), member_id=1, role='pm'),
        UserAuth(username='wangmingxuan', password_hash=UserAuth.hash_password('wang123'), member_id=2, role='pm'),
        UserAuth(username='lishupei', password_hash=UserAuth.hash_password('123'), member_id=3, role='member'),
        UserAuth(username='zhangxiang', password_hash=UserAuth.hash_password('123'), member_id=4, role='member'),
        UserAuth(username='liangweien', password_hash=UserAuth.hash_password('123'), member_id=5, role='member'),
        UserAuth(username='maxiaohao', password_hash=UserAuth.hash_password('123'), member_id=6, role='member'),
    ]
    db.session.add_all(users)
    print('Seed users created: 10 accounts.')
