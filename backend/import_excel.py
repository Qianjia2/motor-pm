"""Import real project data from Excel into the PM tool database."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime, timedelta
import openpyxl
from backend import create_app, db
from backend.models import (
    Phase, Gate, TechnicalLine, Role,
    Project, TeamMember, ProjectMember, ProjectPhaseGate,
    Milestone, WeeklyReport, WeeklyReportLine, RiskIssue,
    Deliverable, UserAuth,
)

EXCEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.codepilot-uploads', '1781674560604-___________.xlsx')

def safe(v):
    """Return stripped string or empty string."""
    if v is None:
        return ''
    return str(v).strip()

def safe_date(v):
    """Parse date from various formats."""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        v = v.strip()
        if not v or v == '0':
            return None
        for fmt in ['%Y%m%d', '%Y-%m-%d', '%Y/%m/%d']:
            try:
                return datetime.strptime(v, fmt).date()
            except ValueError:
                pass
        try:
            # Excel serial date
            return date(1899, 12, 30) + timedelta(days=int(float(v)))
        except (ValueError, TypeError):
            pass
    if isinstance(v, (int, float)) and v > 40000:
        return date(1899, 12, 30) + timedelta(days=int(v))
    return None

def safe_float(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def import_all():
    app = create_app()
    with app.app_context():
        db.create_all()

        # Clear existing data
        for model in [RiskIssue, WeeklyReportLine, WeeklyReport, Deliverable,
                       Milestone, ProjectPhaseGate, ProjectMember,
                       UserAuth, TeamMember, Project]:
            db.session.query(model).delete()
        for model in [Phase, Gate, TechnicalLine, Role]:
            db.session.query(model).delete()
        db.session.commit()
        print('Cleared existing data.')

        # ── Reference data ──────────────────────
        phases = [
            Phase(id=1, name='概念阶段', code='CONCEPT', sort_order=1, description='确认要不要做、能不能做'),
            Phase(id=2, name='方案阶段', code='SCHEME', sort_order=2, description='方案设计、技术路线选定'),
            Phase(id=3, name='详细设计', code='DESIGN', sort_order=3, description='各专业详细设计、图纸、仿真'),
            Phase(id=4, name='样机试制', code='PROTOTYPE', sort_order=4, description='样机制造、装配、调试'),
            Phase(id=5, name='测试验证', code='TEST', sort_order=5, description='部件测试、集成测试、型式试验'),
            Phase(id=6, name='设计定型', code='FINALIZE', sort_order=6, description='设计定型、文件归档、项目移交'),
        ]
        db.session.add_all(phases)

        gates = [
            Gate(id=1, name='概念方案评审', code='G1', sort_order=1, phase_id=2),
            Gate(id=2, name='电磁方案冻结', code='G2', sort_order=2, phase_id=3),
            Gate(id=3, name='结构设计定型', code='G3', sort_order=3, phase_id=3),
            Gate(id=4, name='硬件原理图/PCB冻结', code='G4', sort_order=4, phase_id=4),
            Gate(id=5, name='软件架构评审通过', code='G5', sort_order=5, phase_id=4),
            Gate(id=6, name='算法仿真验收通过', code='G6', sort_order=6, phase_id=4),
            Gate(id=7, name='样机试制完成', code='G7', sort_order=7, phase_id=5),
            Gate(id=8, name='台架测试通过', code='G8', sort_order=8, phase_id=5),
            Gate(id=9, name='设计定型/冻结', code='G9', sort_order=9, phase_id=6),
        ]
        db.session.add_all(gates)

        lines = [
            TechnicalLine(id=1, name='控制算法', short_name='算法', sort_order=1),
            TechnicalLine(id=2, name='控制软件', short_name='软件', sort_order=2),
            TechnicalLine(id=3, name='控制硬件', short_name='硬件', sort_order=3),
            TechnicalLine(id=4, name='电机结构', short_name='结构', sort_order=4),
            TechnicalLine(id=5, name='电机电磁', short_name='电磁', sort_order=5),
            TechnicalLine(id=6, name='测试验证', short_name='测试', sort_order=6),
        ]
        db.session.add_all(lines)

        roles = [
            Role(id=1, name='项目经理', code='PM', sort_order=1),
            Role(id=2, name='技术负责人', code='SE', sort_order=2),
            Role(id=3, name='控制算法负责人', code='ALG', sort_order=3),
            Role(id=4, name='控制软件负责人', code='SW', sort_order=4),
            Role(id=5, name='控制硬件负责人', code='HW', sort_order=5),
            Role(id=6, name='电机结构负责人', code='STR', sort_order=6),
            Role(id=7, name='电机电磁负责人', code='EM', sort_order=7),
            Role(id=8, name='测试验证负责人', code='TEST', sort_order=8),
        ]
        db.session.add_all(roles)
        db.session.commit()
        print('Reference data created.')

        # ── Team members ────────────────────────
        member_map = {}  # name -> member obj
        people_data = [
            ('晋兆海', '项目部', '项目经理'),
            ('王明轩', '项目部', '项目经理'),
            ('李书培', '算法部', '算法工程师'),
            ('张翔', '软件部', '嵌入式工程师'),
            ('梁伟恩', '硬件部', '硬件工程师'),
            ('马晓皓', '结构部', '结构工程师'),
        ]
        for name, dept, title in people_data:
            m = TeamMember(name=name, department=dept, title=title, is_active=True)
            db.session.add(m)
            db.session.flush()
            member_map[name] = m
        db.session.commit()
        print(f'Created {len(people_data)} team members.')

        # ── User accounts ───────────────────────
        users = [
            UserAuth(username='admin', password_hash=UserAuth.hash_password('admin123'), role='admin'),
            UserAuth(username='jin', password_hash=UserAuth.hash_password('jin123'), member_id=member_map['晋兆海'].id, role='pm'),
            UserAuth(username='wangmx', password_hash=UserAuth.hash_password('wang123'), member_id=member_map['王明轩'].id, role='pm'),
            UserAuth(username='lishupei', password_hash=UserAuth.hash_password('123'), member_id=member_map['李书培'].id, role='member'),
            UserAuth(username='zhangxiang', password_hash=UserAuth.hash_password('123'), member_id=member_map['张翔'].id, role='member'),
            UserAuth(username='liang', password_hash=UserAuth.hash_password('123'), member_id=member_map['梁伟恩'].id, role='member'),
            UserAuth(username='maxiaohao', password_hash=UserAuth.hash_password('123'), member_id=member_map['马晓皓'].id, role='member'),
        ]
        db.session.add_all(users)
        db.session.commit()
        print(f'Created {len(users)} user accounts.')

        # ── Parse Excel ─────────────────────────
        wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)

        # Read main table
        ws_main = wb['项目总列表']
        project_list = []
        for row in ws_main.iter_rows(min_row=5, max_row=16, values_only=True):
            name = safe(row[1])
            if not name:
                continue
            project_list.append({
                'name': name,
                'product': safe(row[2]),
                'phase_name': safe(row[3]),
                'goal': safe(row[4]),
                'target_date': safe_date(row[5]),
                'completion_pct': int(safe_float(row[6]) or 0),
                'status': safe(row[7]),
                'pm_name': safe(row[8]),
                'dept': safe(row[9]),
                'team_size': int(safe_float(row[10]) or 0),
                'client': safe(row[11]),
                'client_contact': safe(row[12]),
                'client_doc': safe(row[13]),
                'contract_no': safe(row[14]),
                'contract_date': safe_date(row[15]),
                'contract_scope': safe(row[16]),
                'contract_milestones': safe(row[17]),
                'output_files': safe(row[18]),
                'input_files': safe(row[19]),
                'pending_files': safe(row[20]),
                'file_location': safe(row[21]),
                'main_risk': safe(row[22]),
                'last_update': safe_date(row[23]),
                'notes': safe(row[24]),
            })

        # Determine phase for each project based on detail sheet
        detail_phase_map = {}
        detail_data_map = {}

        detail_sheets = {
            '西山磁浮手柄': '西山磁浮手柄',
            '晟视磁浮': '晟视磁浮',
            '五星CM02': '五星CM02',
            '五星CM03': '五星CM03',
            '优普森eVTOL': '优普森eVTOL',
            '优普森5相30KW': '优普森5相30KW',
            '优普森防爆关节': '优普森防爆关节',
            '金浪科技': '金浪科技',
        }

        for sheet_name in detail_sheets:
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(min_row=1, max_row=92, values_only=True))

            # Extract project info from rows 2-3
            proj_name = safe(rows[1][1]) if len(rows) > 1 else ''
            proj_code = safe(rows[1][3]) if len(rows[1]) > 3 else ''
            pm_name = safe(rows[1][5]) if len(rows[1]) > 5 else ''
            phase_text = safe(rows[2][3]) if len(rows) > 2 else ''
            goal_deliverable = safe(rows[4][1]) if len(rows) > 4 else ''
            acceptance = safe(rows[5][1]) if len(rows) > 5 else ''
            overall_status_text = safe(rows[15][1]) if len(rows) > 15 else ''

            # Parse current phase from "概念-方案-详细设计-样机试制- 测试验证-设计定型  详细设计"
            current_phase_id = 1
            phase_keywords = ['概念', '方案', '详细设计', '样机试制', '测试验证', '设计定型']
            if phase_text:
                for i, kw in enumerate(phase_keywords):
                    # Check if word appears at the end of phase_text (indicates current phase)
                    parts = phase_text.replace(' ', '').split('-')
                    last_part = parts[-1] if parts else ''
                    if kw in last_part:
                        current_phase_id = min(i + 1, 6)
                        break

            # Read line progress from rows 9-14
            line_progress = {}
            line_owner_map = {}
            for li in range(6):
                r = rows[9 + li] if len(rows) > 9 + li else None
                if r:
                    line_progress[li + 1] = {
                        'deliverable': safe(r[1]),
                        'completion': safe_float(r[2]),
                        'activity': safe(r[3]),
                        'quality_ok': safe(r[4]),
                        'blocker': safe(r[5]),
                        'next_step': safe(r[6]),
                    }
                    owner = safe(r[7])
                    if owner:
                        line_owner_map[li + 1] = owner

            detail_phase_map[proj_name] = current_phase_id
            detail_data_map[proj_name] = {
                'code': proj_code,
                'pm_name': pm_name,
                'goal': goal_deliverable or acceptance,
                'acceptance': acceptance,
                'overall_status': overall_status_text,
                'line_progress': line_progress,
                'line_owner_map': line_owner_map,
            }

        print(f'Parsed {len(project_list)} projects from main table.')
        print(f'Parsed detail data for {len(detail_data_map)} projects.')

        # Explicit name mapping: main_table_name -> detail_sheet_name
        name_bridge = {
            '微电机磁浮手柄': '重庆西山-微电机磁浮手柄',
            '医疗用磁悬浮微型电机及控制模块': '晟视天辰（迪远医疗）-医疗用磁悬浮微型电机及控制模块',
            '新型ebike集成式电机研发项目--CM02': '五星新型ebike集成式电机研发项目--CM02',
            '电磁变速ebike驱动系统研发项目--CM03': '五星电磁变速ebike驱动系统研发项目--CM03',
            '5相30KW': '优普森5相30KW',
            '防爆关节': '优普森防爆关节-',
            '摩托车': '金浪摩托车GCU和发电机',
        }

        def match_detail(pname, product=''):
            if pname in detail_data_map:
                return detail_data_map[pname], pname
            # Try explicit mapping
            if pname in name_bridge:
                dname = name_bridge[pname]
                if dname in detail_data_map:
                    return detail_data_map[dname], dname
            # eVOTL: 2 main table entries share one detail sheet
            if 'eVTOL' in pname or 'eVTOL' in product:
                for dname in detail_data_map:
                    if 'eVTOL' in dname:
                        if '280kW' in product or '280kW' in dname:
                            return detail_data_map[dname], dname
            # Substring match as fallback
            for dname in detail_data_map:
                short_p = pname.replace('--', '-').replace(' ', '')
                short_d = dname.replace('--', '-').replace(' ', '')
                if len(short_p) >= 4 and short_p in short_d:
                    return detail_data_map[dname], dname
            return {}, ''

        # ── Create projects ─────────────────────
        project_counter = 0
        for pdata in project_list:
            name = pdata['name']
            detail, matched_dname = match_detail(name, pdata.get('product', ''))
            if detail:
                pass  # matched
            pm_name = pdata['pm_name'] or detail.get('pm_name', '')
            phase_id = detail_phase_map.get(name, 1)

            # Map status
            status = 'normal'
            risk_text = pdata.get('main_risk', '')
            if risk_text:
                status = 'risk'

            code = detail.get('code') or pdata.get('contract_no') or ''
            if not code or Project.query.filter_by(code=code).first():
                code = f'P{project_counter+1:04d}'
                if pdata.get('product'):
                    code += '-' + pdata['product'][:20].replace(' ', '')

            proj = Project(
                name=name,
                code=code,
                description=f"产品方向: {pdata.get('product','')}\n客户: {pdata['client']}\n合同: {pdata.get('contract_no','')}",
                current_phase_id=phase_id,
                start_date=pdata.get('contract_date') or date.today(),
                planned_end_date=pdata.get('target_date'),
                overall_status=status,
                completion_pct=pdata.get('completion_pct', 0),
                problem_statement=pdata.get('product', ''),
                final_deliverable=detail.get('goal', pdata.get('goal', '')),
                acceptance_criteria=detail.get('acceptance', ''),
                aligned_target=pdata.get('client', ''),
                deadline_type='硬性' if pdata.get('contract_no') else '可调',
                priority='P1' if status == 'risk' else 'P2',
                difficulty='medium',
                main_blocker=risk_text if risk_text else None,
                budget_total=safe_float(pdata.get('contract_scope', '0')),
            )
            db.session.add(proj)
            db.session.flush()

            # Assign PM
            if pm_name and pm_name in member_map:
                pm = ProjectMember(
                    project_id=proj.id, member_id=member_map[pm_name].id,
                    role_id=1, allocation_pct=50, is_key=True
                )
                db.session.add(pm)

            # Assign line owners
            line_owners = detail.get('line_owner_map', {})
            role_map = {1: 3, 2: 4, 3: 5, 4: 6, 5: 7, 6: 8}  # line_id -> role_id
            for line_id, owner_name in line_owners.items():
                # Check if this owner already exists as a member in the map
                if owner_name not in member_map:
                    # Create new member
                    m = TeamMember(name=owner_name, department='', title='', is_active=True)
                    db.session.add(m)
                    db.session.flush()
                    member_map[owner_name] = m
                pm_role = ProjectMember(
                    project_id=proj.id, member_id=member_map[owner_name].id,
                    role_id=role_map.get(line_id, 3), allocation_pct=80,
                    is_key=(line_id in [3, 4, 5])  # hardware, structure, emag are key
                )
                db.session.add(pm_role)

            # Create phase-gate records
            for ph_id in range(1, 7):
                pg = ProjectPhaseGate(
                    project_id=proj.id, phase_id=ph_id,
                    status='completed' if ph_id < phase_id else ('in_progress' if ph_id == phase_id else 'not_started'),
                    gate_status='passed' if ph_id < phase_id else None,
                )
                db.session.add(pg)

            # Create line progress data
            line_progress = detail.get('line_progress', {})
            for line_id, lp in line_progress.items():
                block_text = lp.get('blocker', '')
                if block_text and block_text not in ('无', '0', ''):
                    risk = RiskIssue(
                        project_id=proj.id,
                        type='issue',
                        title=block_text[:100] if block_text else '未命名问题',
                        description=lp.get('deliverable', ''),
                        severity='B' if len(block_text) > 20 else 'C',
                        status='open',
                        line_id=line_id,
                        phase_id=phase_id,
                        mitigation_plan=lp.get('next_step', ''),
                    )
                    db.session.add(risk)

            project_counter += 1

        db.session.commit()
        print(f'\n=== IMPORT COMPLETE ===')
        print(f'Projects: {project_counter}')
        print(f'Team members: {TeamMember.query.count()}')
        print(f'User accounts: {UserAuth.query.count()}')
        print(f'Phase-gate records: {ProjectPhaseGate.query.count()}')
        print(f'Risk/issues: {RiskIssue.query.count()}')
        print(f'\nServer ready. Open http://localhost:5000 to view.')


if __name__ == '__main__':
    import_all()
