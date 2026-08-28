from datetime import date, datetime
from flask import Blueprint, request, jsonify, g
from backend import db
from backend.models import Project, Phase, Gate, ProjectPhaseGate, TeamMember, ProjectMember, Role, Deliverable, Milestone, ReviewActionItem
from backend.audit import log_action, get_username

bp = Blueprint('projects', __name__)


@bp.route('/projects', methods=['GET'])
def list_projects():
    active = request.args.get('active', 'true').lower() != 'false'
    query = Project.query
    if active:
        query = query.filter_by(is_active=True)

    status = request.args.get('status')
    if status:
        query = query.filter_by(overall_status=status)

    search = request.args.get('search')
    if search:
        query = query.filter(Project.name.contains(search) | Project.code.contains(search))

    projects = query.order_by(Project.priority.asc(), Project.created_at.desc()).all()
    return jsonify([p.to_dict() for p in projects])


@bp.route('/projects/<int:id>', methods=['GET'])
def get_project(id):
    project = Project.query.get_or_404(id)
    d = project.to_dict()
    d['phase_gates'] = [pg.to_dict() for pg in project.phase_gates]
    d['milestones'] = [m.to_dict() for m in project.milestones]
    d['members'] = [pm.to_dict() for pm in project.members]
    return jsonify(d)


@bp.route('/projects', methods=['POST'])
def create_project():
    data = request.get_json()
    project = Project(
        name=data['name'],
        code=data.get('code'),
        description=data.get('description', ''),
        current_phase_id=data.get('current_phase_id', 1),
        start_date=date.fromisoformat(data['start_date']) if data.get('start_date') else None,
        planned_end_date=date.fromisoformat(data['planned_end_date']) if data.get('planned_end_date') else None,
        overall_status=data.get('overall_status', 'normal'),
        completion_pct=data.get('completion_pct', 0),
        problem_statement=data.get('problem_statement', ''),
        final_deliverable=data.get('final_deliverable', ''),
        acceptance_criteria=data.get('acceptance_criteria', ''),
        aligned_target=data.get('aligned_target', ''),
        deadline_type=data.get('deadline_type', ''),
        priority=data.get('priority', 'P1'),
        difficulty=data.get('difficulty', 'medium'),
        budget_total=data.get('budget_total'),
        budget_spent=data.get('budget_spent', 0),
    )
    db.session.add(project)
    db.session.flush()

    # Auto-create phase-gate records for all 6 phases
    phases = Phase.query.order_by(Phase.sort_order).all()
    gates = {g.phase_id: g for g in Gate.query.all()}
    for phase in phases:
        pg = ProjectPhaseGate(
            project_id=project.id,
            phase_id=phase.id,
            gate_id=gates.get(phase.id).id if phase.id in gates else None,
            status='not_started',
        )
        db.session.add(pg)

    db.session.commit()
    log_action(get_username(), 'create', 'project', project.id, project.name,
               summary=f'创建项目 {project.code}')
    return jsonify(project.to_dict()), 201


@bp.route('/projects/<int:id>', methods=['PUT'])
def update_project(id):
    project = Project.query.get_or_404(id)
    data = request.get_json()

    str_fields = ['name', 'code', 'description', 'overall_status', 'problem_statement',
                  'final_deliverable', 'acceptance_criteria', 'aligned_target',
                  'deadline_type', 'priority', 'difficulty', 'main_blocker',
                  'blocker_duration', 'morale', 'common_complaint', 'success_confidence']
    for f in str_fields:
        if f in data:
            setattr(project, f, data[f])

    int_fields = ['completion_pct', 'current_phase_id']
    for f in int_fields:
        if f in data:
            setattr(project, f, data[f])

    float_fields = ['budget_total', 'budget_spent']
    for f in float_fields:
        if f in data:
            setattr(project, f, data[f])

    date_fields = ['start_date', 'planned_end_date', 'actual_end_date']
    for f in date_fields:
        if f in data and data[f]:
            setattr(project, f, date.fromisoformat(data[f]))

    project.updated_at = datetime.utcnow()
    db.session.commit()
    log_action(get_username(), 'update', 'project', project.id, project.name,
               summary=f'编辑项目 {project.code}')
    return jsonify(project.to_dict())


@bp.route('/projects/<int:id>', methods=['DELETE'])
def delete_project(id):
    project = Project.query.get_or_404(id)
    project.is_active = False
    db.session.commit()
    log_action(get_username(), 'delete', 'project', project.id, project.name,
               summary=f'删除项目 {project.code}')
    return jsonify({'message': 'deleted'})


@bp.route('/projects/<int:id>/clone', methods=['POST'])
def clone_project(id):
    """Clone a project as a template — copies structure, not data."""
    src = Project.query.get_or_404(id)
    data = request.get_json() or {}

    code = data.get('code', f'{src.code}-COPY')
    name = data.get('name', f'{src.name} (副本)')

    new_proj = Project(
        name=name,
        code=code,
        description=src.description,
        current_phase_id=1,
        start_date=date.today(),
        planned_end_date=None,
        overall_status='normal',
        completion_pct=0,
        problem_statement=src.problem_statement,
        final_deliverable=src.final_deliverable,
        acceptance_criteria=src.acceptance_criteria,
        aligned_target=src.aligned_target,
        deadline_type=src.deadline_type,
        priority=src.priority,
        difficulty=src.difficulty,
        budget_total=src.budget_total,
        budget_spent=0,
        client_id=src.client_id,
    )
    db.session.add(new_proj)
    db.session.flush()

    # Copy phase-gate records with fresh dates
    for pg in src.phase_gates:
        new_pg = ProjectPhaseGate(
            project_id=new_proj.id,
            phase_id=pg.phase_id,
            gate_id=pg.gate_id,
            status='not_started',
        )
        db.session.add(new_pg)

    # Copy deliverable templates (structure only, no files)
    for d in src.deliverables:
        new_d = Deliverable(
            project_id=new_proj.id,
            phase_id=d.phase_id,
            line_id=d.line_id,
            name=d.name,
            description=d.description,
            status='not_submitted',
            owner_id=None,
        )
        db.session.add(new_d)

    # Copy milestones (structure only, dates shifted)
    from datetime import timedelta
    day_offset = (date.today() - (src.start_date or date.today())).days
    for m in src.milestones:
        new_m = Milestone(
            project_id=new_proj.id,
            name=m.name,
            description=m.description,
            planned_date=date.today() + timedelta(days=max(0, (m.planned_date - src.start_date).days)) if m.planned_date and src.start_date else None,
            line_id=m.line_id,
            phase_id=m.phase_id,
            status='pending',
            is_key=m.is_key,
            sort_order=m.sort_order,
        )
        db.session.add(new_m)

    db.session.commit()
    log_action(get_username(), 'create', 'project', new_proj.id, new_proj.name,
               summary=f'从 {src.code} 复制创建项目 {new_proj.code}')
    return jsonify(new_proj.to_dict()), 201


# ── 阶段门径 ──────────────────────────────────────────

@bp.route('/projects/<int:id>/phase-gates', methods=['GET'])
def get_phase_gates(id):
    pgs = ProjectPhaseGate.query.filter_by(project_id=id).order_by(ProjectPhaseGate.phase_id).all()
    return jsonify([pg.to_dict() for pg in pgs])


@bp.route('/projects/<int:id>/phase-gates/<int:phase_id>', methods=['PUT'])
def update_phase_gate(id, phase_id):
    pg = ProjectPhaseGate.query.filter_by(project_id=id, phase_id=phase_id).first_or_404()
    data = request.get_json()
    str_fields = ['status', 'gate_status', 'gate_review_notes']
    for f in str_fields:
        if f in data:
            setattr(pg, f, data[f])
    date_fields = ['planned_start_date', 'planned_end_date', 'actual_start_date', 'actual_end_date', 'gate_review_date']
    for f in date_fields:
        if f in data and data[f]:
            setattr(pg, f, date.fromisoformat(data[f]))
    db.session.commit()

    # Update project's current phase if a phase is completed
    if pg.status == 'completed':
        project = Project.query.get(id)
        next_phase = Phase.query.filter(Phase.sort_order > Phase.query.get(phase_id).sort_order).order_by(Phase.sort_order).first()
        if next_phase and project.current_phase_id < next_phase.id:
            project.current_phase_id = next_phase.id
            db.session.commit()

    return jsonify(pg.to_dict())


# ── 评审意见（Action Items） ──────────────────────

@bp.route('/projects/<int:id>/phase-gates/<int:phase_id>/action-items', methods=['GET'])
def list_action_items(id, phase_id):
    pg = ProjectPhaseGate.query.filter_by(project_id=id, phase_id=phase_id).first_or_404()
    items = ReviewActionItem.query.filter_by(project_phase_gate_id=pg.id).order_by(ReviewActionItem.sort_order).all()
    return jsonify([ai.to_dict() for ai in items])


@bp.route('/projects/<int:id>/phase-gates/<int:phase_id>/action-items', methods=['POST'])
def create_action_item(id, phase_id):
    pg = ProjectPhaseGate.query.filter_by(project_id=id, phase_id=phase_id).first_or_404()
    data = request.get_json()
    ai = ReviewActionItem(
        project_phase_gate_id=pg.id,
        title=data['title'],
        description=data.get('description', ''),
        assignee_id=data.get('assignee_id'),
        due_date=date.fromisoformat(data['due_date']) if data.get('due_date') else None,
        status=data.get('status', 'open'),
        sort_order=data.get('sort_order', 0),
    )
    db.session.add(ai)
    db.session.commit()
    log_action(get_username(), 'create', 'action_item', ai.id, ai.title,
               project_id=id, summary=f'门径评审新增意见: {ai.title}')
    return jsonify(ai.to_dict()), 201


@bp.route('/projects/<int:id>/action-items/<int:ai_id>', methods=['PUT'])
def update_action_item(id, ai_id):
    ai = ReviewActionItem.query.get_or_404(ai_id)
    data = request.get_json()
    for f in ['title', 'description', 'status', 'resolution']:
        if f in data:
            setattr(ai, f, data[f])
    if 'assignee_id' in data:
        ai.assignee_id = data['assignee_id']
    if data.get('due_date'):
        ai.due_date = date.fromisoformat(data['due_date'])
    if data.get('status') == 'closed' and not ai.closed_at:
        ai.closed_at = datetime.utcnow()
    if data.get('sort_order') is not None:
        ai.sort_order = data['sort_order']
    db.session.commit()
    log_action(get_username(), 'update', 'action_item', ai.id, ai.title,
               project_id=id, summary=f'更新评审意见: {ai.title}')
    return jsonify(ai.to_dict())


@bp.route('/projects/<int:id>/action-items/<int:ai_id>', methods=['DELETE'])
def delete_action_item(id, ai_id):
    ai = ReviewActionItem.query.get_or_404(ai_id)
    db.session.delete(ai)
    db.session.commit()
    log_action(get_username(), 'delete', 'action_item', ai_id, ai.title,
               project_id=id, summary=f'删除评审意见: {ai.title}')
    return jsonify({'message': 'deleted'})


# ── 项目成员 ──────────────────────────────────────────

@bp.route('/projects/<int:id>/members', methods=['GET'])
def get_project_members(id):
    pms = ProjectMember.query.filter_by(project_id=id).all()
    return jsonify([pm.to_dict() for pm in pms])


@bp.route('/projects/<int:id>/members', methods=['POST'])
def add_project_member(id, member_id=None):
    data = request.get_json()
    pm = ProjectMember(
        project_id=id,
        member_id=data['member_id'],
        role_id=data['role_id'],
        allocation_pct=data.get('allocation_pct', 100),
        is_key=data.get('is_key', False),
    )
    db.session.add(pm)
    db.session.commit()
    return jsonify(pm.to_dict()), 201


@bp.route('/projects/<int:id>/members/<int:mid>', methods=['PUT'])
def update_project_member(id, mid):
    pm = ProjectMember.query.filter_by(project_id=id, member_id=mid).first_or_404()
    data = request.get_json()
    if 'allocation_pct' in data:
        pm.allocation_pct = data['allocation_pct']
    if 'is_key' in data:
        pm.is_key = data['is_key']
    if 'role_id' in data:
        pm.role_id = data['role_id']
    db.session.commit()
    return jsonify(pm.to_dict())


@bp.route('/projects/<int:id>/members/<int:mid>', methods=['DELETE'])
def remove_project_member(id, mid):
    pm = ProjectMember.query.filter_by(project_id=id, member_id=mid).first_or_404()
    db.session.delete(pm)
    db.session.commit()
    return jsonify({'message': 'removed'})
