import hashlib
import secrets
from datetime import datetime
from backend import db


# ──────────────────────────────────────────────
# 客户信息
# ──────────────────────────────────────────────

class Client(db.Model):
    __tablename__ = 'client'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    abbreviation = db.Column(db.String(16), unique=True, nullable=False)
    address = db.Column(db.String(256))
    phone = db.Column(db.String(32))
    contact_person = db.Column(db.String(64))
    contact_phone = db.Column(db.String(32))
    contact_email = db.Column(db.String(128))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    projects = db.relationship('Project', back_populates='client')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


# ──────────────────────────────────────────────
# 参考数据表 (4 tables)
# ──────────────────────────────────────────────

class Phase(db.Model):
    __tablename__ = 'phase'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False)
    code = db.Column(db.String(16), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Gate(db.Model):
    __tablename__ = 'gate'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    code = db.Column(db.String(8), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False)
    phase_id = db.Column(db.Integer, db.ForeignKey('phase.id'))

    phase = db.relationship('Phase')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TechnicalLine(db.Model):
    __tablename__ = 'technical_line'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False)
    short_name = db.Column(db.String(16))
    sort_order = db.Column(db.Integer, nullable=False)
    icon = db.Column(db.String(32))

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Role(db.Model):
    __tablename__ = 'role'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False)
    code = db.Column(db.String(16), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False)
    is_core = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


# ──────────────────────────────────────────────
# 核心业务表 (13 tables)
# ──────────────────────────────────────────────

class Project(db.Model):
    __tablename__ = 'project'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    code = db.Column(db.String(32), unique=True)
    description = db.Column(db.Text)

    current_phase_id = db.Column(db.Integer, db.ForeignKey('phase.id'))
    current_phase = db.relationship('Phase')
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    client = db.relationship('Client', back_populates='projects')

    start_date = db.Column(db.Date)
    planned_end_date = db.Column(db.Date)
    actual_end_date = db.Column(db.Date)

    overall_status = db.Column(db.String(16), default='normal')
    completion_pct = db.Column(db.Integer, default=0)

    # Section A: 目标
    problem_statement = db.Column(db.Text)
    final_deliverable = db.Column(db.Text)
    acceptance_criteria = db.Column(db.Text)
    aligned_target = db.Column(db.Text)
    deadline_type = db.Column(db.String(16))

    # Section D: 当前难点
    main_blocker = db.Column(db.Text)
    blocker_duration = db.Column(db.String(16))
    morale = db.Column(db.String(16))
    common_complaint = db.Column(db.Text)
    success_confidence = db.Column(db.String(16))

    # 元数据
    priority = db.Column(db.String(8), default='P1')
    difficulty = db.Column(db.String(16))
    is_active = db.Column(db.Boolean, default=True)
    budget_total = db.Column(db.Float)
    budget_spent = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    members = db.relationship('ProjectMember', back_populates='project', cascade='all,delete-orphan')
    milestones = db.relationship('Milestone', back_populates='project', cascade='all,delete-orphan')
    weekly_reports = db.relationship('WeeklyReport', back_populates='project', cascade='all,delete-orphan')
    risks = db.relationship('RiskIssue', back_populates='project', cascade='all,delete-orphan')
    changes = db.relationship('ChangeRequest', back_populates='project', cascade='all,delete-orphan')
    deliverables = db.relationship('Deliverable', back_populates='project', cascade='all,delete-orphan')
    phase_gates = db.relationship('ProjectPhaseGate', back_populates='project', cascade='all,delete-orphan')

    def to_dict(self):
        d = {}
        for c in self.__table__.columns:
            val = getattr(self, c.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            elif isinstance(val, (bytes,)):
                val = None
            elif hasattr(val, 'isoformat'):
                val = val.isoformat() if val else None
            d[c.name] = val
        d['current_phase'] = self.current_phase.to_dict() if self.current_phase else None
        d['client'] = self.client.to_dict() if self.client else None
        d['member_count'] = len(self.members) if self.members else 0
        return d


class TeamMember(db.Model):
    __tablename__ = 'team_member'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    department = db.Column(db.String(64))
    email = db.Column(db.String(128))
    phone = db.Column(db.String(32))
    title = db.Column(db.String(64))
    skills = db.Column(db.String(256))
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class ProjectMember(db.Model):
    __tablename__ = 'project_member'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('team_member.id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    allocation_pct = db.Column(db.Integer, default=100)
    is_key = db.Column(db.Boolean, default=False)

    project = db.relationship('Project', back_populates='members')
    member = db.relationship('TeamMember', lazy='joined')
    role = db.relationship('Role', lazy='joined')

    __table_args__ = (db.UniqueConstraint('project_id', 'member_id', 'role_id'),)

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'member_id': self.member_id,
            'role_id': self.role_id,
            'allocation_pct': self.allocation_pct,
            'is_key': self.is_key,
            'member': self.member.to_dict() if self.member else None,
            'role': self.role.to_dict() if self.role else None,
        }


class ProjectPhaseGate(db.Model):
    __tablename__ = 'project_phase_gate'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    phase_id = db.Column(db.Integer, db.ForeignKey('phase.id'), nullable=False)
    gate_id = db.Column(db.Integer, db.ForeignKey('gate.id'))

    planned_start_date = db.Column(db.Date)
    planned_end_date = db.Column(db.Date)
    actual_start_date = db.Column(db.Date)
    actual_end_date = db.Column(db.Date)

    status = db.Column(db.String(16), default='not_started')
    gate_status = db.Column(db.String(16))
    gate_review_date = db.Column(db.Date)
    gate_review_notes = db.Column(db.Text)

    project = db.relationship('Project', back_populates='phase_gates')
    phase = db.relationship('Phase', lazy='joined')
    gate = db.relationship('Gate', lazy='joined')

    __table_args__ = (db.UniqueConstraint('project_id', 'phase_id'),)

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for date_field in ['planned_start_date', 'planned_end_date', 'actual_start_date', 'actual_end_date', 'gate_review_date']:
            val = d.get(date_field)
            d[date_field] = val.isoformat() if val else None
        d['phase'] = self.phase.to_dict() if self.phase else None
        d['gate'] = self.gate.to_dict() if self.gate else None
        return d


class ReviewActionItem(db.Model):
    """Design review action items linked to a phase gate review."""
    __tablename__ = 'review_action_item'
    id = db.Column(db.Integer, primary_key=True)
    project_phase_gate_id = db.Column(db.Integer, db.ForeignKey('project_phase_gate.id'), nullable=False)
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text)
    assignee_id = db.Column(db.Integer, db.ForeignKey('team_member.id'))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(16), default='open')  # open / in_progress / closed
    resolution = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime)

    phase_gate = db.relationship('ProjectPhaseGate', backref=db.backref('action_items', lazy='dynamic', cascade='all, delete-orphan'))
    assignee = db.relationship('TeamMember', lazy='joined')

    def to_dict(self):
        return {
            'id': self.id,
            'project_phase_gate_id': self.project_phase_gate_id,
            'title': self.title,
            'description': self.description,
            'assignee_id': self.assignee_id,
            'assignee_name': self.assignee.name if self.assignee else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'status': self.status,
            'resolution': self.resolution,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
        }


class Milestone(db.Model):
    __tablename__ = 'milestone'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    planned_date = db.Column(db.Date, nullable=False)
    actual_date = db.Column(db.Date)
    line_id = db.Column(db.Integer, db.ForeignKey('technical_line.id'))
    phase_id = db.Column(db.Integer, db.ForeignKey('phase.id'))
    status = db.Column(db.String(16), default='pending')
    is_key = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)

    project = db.relationship('Project', back_populates='milestones')
    line = db.relationship('TechnicalLine', lazy='joined')
    phase = db.relationship('Phase', lazy='joined')

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for date_field in ['planned_date', 'actual_date']:
            val = d.get(date_field)
            d[date_field] = val.isoformat() if val else None
        d['line'] = self.line.to_dict() if self.line else None
        d['phase'] = self.phase.to_dict() if self.phase else None
        return d


class WeeklyReport(db.Model):
    __tablename__ = 'weekly_report'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    report_date = db.Column(db.Date)
    overall_progress = db.Column(db.Text)
    key_accomplishments = db.Column(db.Text)
    completion_rate = db.Column(db.String(16))
    reporter_id = db.Column(db.Integer, db.ForeignKey('team_member.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', back_populates='weekly_reports')
    reporter = db.relationship('TeamMember', lazy='joined')
    line_items = db.relationship('WeeklyReportLine', back_populates='report', cascade='all,delete-orphan', lazy='joined')

    __table_args__ = (db.UniqueConstraint('project_id', 'year', 'week_number'),)

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for date_field in ['report_date']:
            val = d.get(date_field)
            d[date_field] = val.isoformat() if val else None
        d['created_at'] = self.created_at.isoformat() if self.created_at else None
        d['reporter'] = self.reporter.to_dict() if self.reporter else None
        d['line_items'] = [li.to_dict() for li in self.line_items] if self.line_items else []
        d['project_name'] = self.project.name if self.project else ''
        return d


class WeeklyReportLine(db.Model):
    __tablename__ = 'weekly_report_line'
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('weekly_report.id'), nullable=False)
    line_id = db.Column(db.Integer, db.ForeignKey('technical_line.id'), nullable=False)
    this_week = db.Column(db.Text)
    next_week = db.Column(db.Text)
    status = db.Column(db.String(16))
    blocker = db.Column(db.Text)
    coordinator = db.Column(db.String(64))
    sort_order = db.Column(db.Integer, default=0)

    report = db.relationship('WeeklyReport', back_populates='line_items')
    line = db.relationship('TechnicalLine', lazy='joined')

    __table_args__ = (db.UniqueConstraint('report_id', 'line_id'),)

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        d['line'] = self.line.to_dict() if self.line else None
        return d


class RiskIssue(db.Model):
    __tablename__ = 'risk_issue'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    type = db.Column(db.String(16), nullable=False, default='risk')
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text)
    probability = db.Column(db.String(16))
    impact = db.Column(db.String(16))
    risk_level = db.Column(db.String(16))
    severity = db.Column(db.String(8))
    status = db.Column(db.String(16), default='open')
    mitigation_plan = db.Column(db.Text)
    owner_id = db.Column(db.Integer, db.ForeignKey('team_member.id'))
    line_id = db.Column(db.Integer, db.ForeignKey('technical_line.id'))
    phase_id = db.Column(db.Integer, db.ForeignKey('phase.id'))
    identified_date = db.Column(db.Date)
    target_resolve_date = db.Column(db.Date)
    resolved_date = db.Column(db.Date)
    resolution = db.Column(db.Text)
    attachment_path = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', back_populates='risks')
    owner = db.relationship('TeamMember', lazy='joined')
    line = db.relationship('TechnicalLine', lazy='joined')
    phase = db.relationship('Phase', lazy='joined')

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for date_field in ['identified_date', 'target_resolve_date', 'resolved_date']:
            val = d.get(date_field)
            d[date_field] = val.isoformat() if val else None
        d['created_at'] = self.created_at.isoformat() if self.created_at else None
        d['owner'] = self.owner.to_dict() if self.owner else None
        d['line'] = self.line.to_dict() if self.line else None
        d['phase'] = self.phase.to_dict() if self.phase else None
        return d


class ChangeRequest(db.Model):
    __tablename__ = 'change_request'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text)
    change_level = db.Column(db.String(16))
    requester_id = db.Column(db.Integer, db.ForeignKey('team_member.id'))
    affected_lines = db.Column(db.String(256))
    impact_scope = db.Column(db.Text)
    impact_schedule = db.Column(db.Text)
    impact_cost = db.Column(db.Text)
    status = db.Column(db.String(16), default='pending')
    reviewer_id = db.Column(db.Integer, db.ForeignKey('team_member.id'))
    review_notes = db.Column(db.Text)
    submitted_date = db.Column(db.Date)
    decision_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', back_populates='changes')
    requester = db.relationship('TeamMember', foreign_keys=[requester_id], lazy='joined')
    reviewer = db.relationship('TeamMember', foreign_keys=[reviewer_id], lazy='joined')

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for date_field in ['submitted_date', 'decision_date']:
            val = d.get(date_field)
            d[date_field] = val.isoformat() if val else None
        d['created_at'] = self.created_at.isoformat() if self.created_at else None
        d['requester'] = self.requester.to_dict() if self.requester else None
        d['reviewer'] = self.reviewer.to_dict() if self.reviewer else None
        return d


class Deliverable(db.Model):
    __tablename__ = 'deliverable'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    phase_id = db.Column(db.Integer, db.ForeignKey('phase.id'), nullable=False)
    line_id = db.Column(db.Integer, db.ForeignKey('technical_line.id'))
    name = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text)
    file_path = db.Column(db.String(512))
    status = db.Column(db.String(16), default='not_submitted')
    owner_id = db.Column(db.Integer, db.ForeignKey('team_member.id'))
    submitted_date = db.Column(db.Date)

    project = db.relationship('Project', back_populates='deliverables')
    phase = db.relationship('Phase', lazy='joined')
    line = db.relationship('TechnicalLine', lazy='joined')
    owner = db.relationship('TeamMember', lazy='joined')

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        if d.get('submitted_date'):
            d['submitted_date'] = d['submitted_date'].isoformat()
        d['phase'] = self.phase.to_dict() if self.phase else None
        d['line'] = self.line.to_dict() if self.line else None
        d['owner'] = self.owner.to_dict() if self.owner else None
        return d


class ProjectHealthSnapshot(db.Model):
    __tablename__ = 'project_health_snapshot'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    snapshot_date = db.Column(db.Date, nullable=False)
    completion_pct = db.Column(db.Integer)
    schedule_deviation = db.Column(db.Integer)
    open_risks_count = db.Column(db.Integer)
    open_issues_count = db.Column(db.Integer)
    morale = db.Column(db.String(16))
    overall_status = db.Column(db.String(16))

    __table_args__ = (db.UniqueConstraint('project_id', 'snapshot_date'),)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


# ──────────────────────────────────────────────
# 用户认证
# ──────────────────────────────────────────────

class ProjectDocument(db.Model):
    __tablename__ = 'project_document'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    name = db.Column(db.String(256), nullable=False)
    doc_type = db.Column(db.String(32), nullable=False, default='other')
    file_path = db.Column(db.String(512))
    file_size = db.Column(db.Integer)
    uploaded_by = db.Column(db.String(64))
    upload_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    status = db.Column(db.String(16), default='active')  # active / deprecated / superseded
    version = db.Column(db.Integer, default=1)
    replaced_by_id = db.Column(db.Integer, db.ForeignKey('project_document.id'))

    project = db.relationship('Project')
    replaced_by = db.relationship('ProjectDocument', remote_side=[id], foreign_keys=[replaced_by_id])

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        if d.get('upload_date'):
            d['upload_date'] = d['upload_date'].isoformat()
        return d


class UserAuth(db.Model):
    __tablename__ = 'user_auth'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('team_member.id'))
    role = db.Column(db.String(16), default='member')
    token = db.Column(db.String(64), unique=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    member = db.relationship('TeamMember', lazy='joined')

    @staticmethod
    def hash_password(password):
        salt = secrets.token_hex(8)
        return salt + ':' + hashlib.sha256((salt + password).encode()).hexdigest()

    @staticmethod
    def verify_password(stored, password):
        try:
            salt, h = stored.split(':')
            return h == hashlib.sha256((salt + password).encode()).hexdigest()
        except ValueError:
            return False

    @staticmethod
    def generate_token():
        return secrets.token_hex(32)

    def to_dict(self):
        return {
            'id': self.id, 'username': self.username, 'role': self.role,
            'member_id': self.member_id,
            'member': self.member.to_dict() if self.member else None,
        }


class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False)
    action = db.Column(db.String(16), nullable=False)  # create/update/delete/close/replace/deprecate
    entity_type = db.Column(db.String(32), nullable=False)  # project/milestone/risk/change/deliverable/report/document
    entity_id = db.Column(db.Integer)
    entity_name = db.Column(db.String(256))
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    summary = db.Column(db.String(512))
    details = db.Column(db.Text)  # JSON string of changed fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', lazy='joined')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'action': self.action,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'entity_name': self.entity_name,
            'project_id': self.project_id,
            'project_name': self.project.name if self.project else None,
            'summary': self.summary,
            'details': self.details,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
