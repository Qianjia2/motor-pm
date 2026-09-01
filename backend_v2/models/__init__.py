"""SQLAlchemy 2.0 ORM models for Motor PM System v2."""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    Text, ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from backend_v2.database import Base


class Client(Base):
    __tablename__ = "client"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    abbreviation = Column(String(16), unique=True, nullable=False)
    industry = Column(String(64))
    address = Column(String(256))
    cooperation_status = Column(String(32), default="潜在")
    phone = Column(String(32))
    contact_person = Column(String(64))
    contact_phone = Column(String(32))
    contact_email = Column(String(128))
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    projects = relationship("Project", back_populates="client")


class ClientCommunication(Base):
    __tablename__ = "client_communication"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("client.id"), nullable=False)
    client = relationship("Client")
    comm_date = Column(Date)              # 沟通日期
    comm_type = Column(String(32))        # 电话/邮件/拜访/微信/会议/其他
    subject = Column(String(128))         # 沟通主题
    content = Column(Text)                # 沟通内容
    images = Column(Text)                 # 微信图片路径(JSON数组,相对 UPLOAD_DIR)
    owner = Column(String(64))            # 我方沟通人
    contact_person = Column(String(64))   # 对方联系人
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ClientContact(Base):
    __tablename__ = "client_contact"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("client.id"), nullable=False)
    client = relationship("Client")
    name = Column(String(64), nullable=False)    # 联系人姓名
    title = Column(String(64))                   # 职务
    phone = Column(String(32))
    email = Column(String(128))
    is_primary = Column(Boolean, default=False)  # 是否主要联系人
    notes = Column(String(256))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Opportunity(Base):
    __tablename__ = "opportunity"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    client_id = Column(Integer, ForeignKey("client.id"), nullable=False)
    client = relationship("Client")
    project_id = Column(Integer, ForeignKey("project.id"), nullable=True)
    project = relationship("Project")
    lead_source = Column(String(32))          # 线索来源
    amount = Column(Float, default=0)         # 预计金额（万元）
    stage = Column(String(32), default="线索")  # 线索/需求确认/方案报价/合同签订/样机试制/量产
    probability = Column(Integer, default=0)  # 成交概率 %
    expected_close = Column(Date)             # 预计成交日期
    owner = Column(String(64))                # 负责人
    description = Column(Text)
    status = Column(String(16), default="open")  # open 进行中 / won 赢单 / lost 丢单
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Phase(Base):
    __tablename__ = "phase"
    id = Column(Integer, primary_key=True)
    name = Column(String(32), nullable=False)
    code = Column(String(16), nullable=False)
    sort_order = Column(Integer, nullable=False)
    description = Column(Text)
    # hardware=电机研发项目(默认), software=软件研发项目
    project_type = Column(String(16), default="hardware")

    __table_args__ = (Index("idx_phase_sort", "sort_order"),)


class Gate(Base):
    __tablename__ = "gate"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    code = Column(String(8), nullable=False)
    sort_order = Column(Integer, nullable=False)
    phase_id = Column(Integer, ForeignKey("phase.id"))

    phase = relationship("Phase")


class TechnicalLine(Base):
    __tablename__ = "technical_line"
    id = Column(Integer, primary_key=True)
    name = Column(String(32), nullable=False)
    short_name = Column(String(16))
    sort_order = Column(Integer, nullable=False)
    icon = Column(String(32))


class Role(Base):
    __tablename__ = "role"
    id = Column(Integer, primary_key=True)
    name = Column(String(32), nullable=False)
    code = Column(String(16), nullable=False)
    sort_order = Column(Integer, nullable=False)
    is_core = Column(Boolean, default=True)


class Project(Base):
    __tablename__ = "project"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    code = Column(String(32), unique=True)
    description = Column(Text)
    # hardware=电机研发项目(默认), software=软件研发项目(电机仿真设计软件纯开发)
    project_type = Column(String(16), default="hardware")
    current_phase_id = Column(Integer, ForeignKey("phase.id"))
    current_phase = relationship("Phase")
    client_id = Column(Integer, ForeignKey("client.id"))
    client = relationship("Client", back_populates="projects")
    start_date = Column(Date)
    planned_end_date = Column(Date)
    actual_end_date = Column(Date)
    overall_status = Column(String(16), default="normal")
    completion_pct = Column(Integer, default=0)
    # Goals
    problem_statement = Column(Text)
    final_deliverable = Column(Text)
    acceptance_criteria = Column(Text)
    aligned_target = Column(Text)
    deadline_type = Column(String(16))
    # Health
    main_blocker = Column(Text)
    blocker_duration = Column(String(16))
    morale = Column(String(16))
    common_complaint = Column(Text)
    success_confidence = Column(String(16))
    # Meta
    priority = Column(String(8), default="P1")
    difficulty = Column(String(16))
    is_active = Column(Boolean, default=True)
    # Financials (万元)
    contract_amount = Column(Float, default=0)      # 合同总额
    contract_amount_manual = Column(Boolean, default=False)  # 合同总额是否手工填写(手工填写后不再被回款记录覆盖)
    received_amount = Column(Float, default=0)       # 已回款
    budget = Column(Float, default=0)                # 项目预算
    actual_cost = Column(Float, default=0)           # 实际成本

    transactions = relationship("Transaction", back_populates="project", cascade="all, delete-orphan")
    requirements = relationship("Requirement", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    budget_total = Column(Float)
    budget_spent = Column(Float)
    version = Column(Integer, default=1)  # optimistic locking
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    members = relationship("ProjectMember", back_populates="project", cascade="all,delete-orphan")
    milestones = relationship("Milestone", back_populates="project", cascade="all,delete-orphan")
    weekly_reports = relationship("WeeklyReport", back_populates="project", cascade="all,delete-orphan")
    risks = relationship("RiskIssue", back_populates="project", cascade="all,delete-orphan")
    changes = relationship("ChangeRequest", back_populates="project", cascade="all,delete-orphan")
    deliverables = relationship("Deliverable", back_populates="project", cascade="all,delete-orphan")
    phase_gates = relationship("ProjectPhaseGate", back_populates="project", cascade="all,delete-orphan")

    __table_args__ = (
        Index("idx_project_active", "is_active", "overall_status", "priority"),
        Index("idx_project_client", "client_id"),
    )


class TeamMember(Base):
    __tablename__ = "team_member"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    department = Column(String(64))
    email = Column(String(128))
    phone = Column(String(32))
    title = Column(String(64))
    skills = Column(String(256))
    is_active = Column(Boolean, default=True)


class ProjectMember(Base):
    __tablename__ = "project_member"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("team_member.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("role.id"), nullable=False)
    allocation_pct = Column(Integer, default=100)
    is_key = Column(Boolean, default=False)
    phase_ids = Column(Text, default="[]")  # JSON array: [1,2,3] — which phases member can access

    project = relationship("Project", back_populates="members")
    member = relationship("TeamMember", lazy="joined")
    role = relationship("Role", lazy="joined")

    __table_args__ = (
        UniqueConstraint("project_id", "member_id", "role_id", name="uq_pm_unique"),
        Index("idx_pm_project", "project_id"),
        Index("idx_pm_member", "member_id"),
    )


class ProjectPhaseGate(Base):
    __tablename__ = "project_phase_gate"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    phase_id = Column(Integer, ForeignKey("phase.id"), nullable=False)
    gate_id = Column(Integer, ForeignKey("gate.id"))
    planned_start_date = Column(Date)
    planned_end_date = Column(Date)
    actual_start_date = Column(Date)
    actual_end_date = Column(Date)
    status = Column(String(16), default="not_started")
    gate_status = Column(String(16))
    gate_review_date = Column(Date)
    gate_review_notes = Column(Text)
    signoff_initiated_by = Column(String(64))

    project = relationship("Project", back_populates="phase_gates")
    phase = relationship("Phase", lazy="joined")
    gate = relationship("Gate", lazy="joined")

    __table_args__ = (
        UniqueConstraint("project_id", "phase_id", name="uq_pg_unique"),
        Index("idx_pg_project", "project_id"),
    )


class ReviewActionItem(Base):
    __tablename__ = "review_action_item"
    id = Column(Integer, primary_key=True)
    project_phase_gate_id = Column(Integer, ForeignKey("project_phase_gate.id"), nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(Text)
    assignee_id = Column(Integer, ForeignKey("team_member.id"))
    due_date = Column(Date)
    status = Column(String(16), default="open")
    resolution = Column(Text)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime)

    phase_gate = relationship("ProjectPhaseGate", backref="action_items")
    assignee = relationship("TeamMember", lazy="joined")

    __table_args__ = (Index("idx_rai_phasegate", "project_phase_gate_id"),)


class Milestone(Base):
    __tablename__ = "milestone"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text)
    planned_date = Column(Date, nullable=False)
    actual_date = Column(Date)
    line_id = Column(Integer, ForeignKey("technical_line.id"))
    phase_id = Column(Integer, ForeignKey("phase.id"))
    planned_end_date = Column(Date)
    actual_end_date = Column(Date)
    depends_on_id = Column(Integer, ForeignKey("milestone.id"), nullable=True)
    status = Column(String(16), default="pending")
    is_key = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)

    project = relationship("Project", back_populates="milestones")
    line = relationship("TechnicalLine", lazy="joined")
    phase = relationship("Phase", lazy="joined")
    depends_on = relationship("Milestone", remote_side=[id], foreign_keys=[depends_on_id], lazy="select")

    __table_args__ = (
        Index("idx_ms_project", "project_id"),
        Index("idx_ms_overdue", "project_id", "planned_date", postgresql_where="status NOT IN ('completed','cancelled')"),
    )


class WeeklyReport(Base):
    __tablename__ = "weekly_report"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    week_number = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    report_date = Column(Date)
    overall_progress = Column(Text)
    key_accomplishments = Column(Text)
    completion_rate = Column(String(16))
    reporter_id = Column(Integer, ForeignKey("team_member.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="weekly_reports")
    reporter = relationship("TeamMember", lazy="joined")
    line_items = relationship("WeeklyReportLine", back_populates="report", cascade="all,delete-orphan", lazy="select")

    __table_args__ = (
        UniqueConstraint("project_id", "year", "week_number", name="uq_report_week"),
        Index("idx_report_project_week", "project_id", "year", "week_number"),
    )


class WeeklyReportLine(Base):
    __tablename__ = "weekly_report_line"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("weekly_report.id"), nullable=False)
    line_id = Column(Integer, ForeignKey("technical_line.id"), nullable=False)
    goal = Column(Text)
    this_week = Column(Text)
    next_week = Column(Text)
    status = Column(String(16))
    blocker = Column(Text)
    coordinator = Column(String(64))
    sort_order = Column(Integer, default=0)

    report = relationship("WeeklyReport", back_populates="line_items")
    line = relationship("TechnicalLine", lazy="joined")

    __table_args__ = (
        UniqueConstraint("report_id", "line_id", name="uq_report_line"),
        Index("idx_wrl_report", "report_id"),
    )


class RiskIssue(Base):
    __tablename__ = "risk_issue"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    type = Column(String(16), nullable=False, default="risk")
    title = Column(String(256), nullable=False)
    description = Column(Text)
    probability = Column(String(16))
    impact = Column(String(16))
    risk_level = Column(String(16))
    severity = Column(String(8))
    status = Column(String(16), default="open")
    mitigation_plan = Column(Text)
    owner_id = Column(Integer, ForeignKey("team_member.id"))
    line_id = Column(Integer, ForeignKey("technical_line.id"))
    phase_id = Column(Integer, ForeignKey("phase.id"))
    identified_date = Column(Date)
    target_resolve_date = Column(Date)
    resolved_date = Column(Date)
    resolution = Column(Text)
    attachment_path = Column(String(512))
    source_quote = Column(Text)
    source_report_id = Column(Integer, ForeignKey("weekly_report.id"))
    confidence = Column(Integer)
    source_type = Column(String(32), default="manual")
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="risks")
    owner = relationship("TeamMember", lazy="joined")
    line = relationship("TechnicalLine", lazy="joined")
    phase = relationship("Phase", lazy="joined")
    source_report = relationship("WeeklyReport", lazy="joined", foreign_keys=[source_report_id])

    __table_args__ = (
        Index("idx_risk_project", "project_id"),
        Index("idx_risk_open", "project_id", "risk_level", "status"),
        Index("idx_risk_owner", "owner_id"),
        Index("idx_risk_source_type", "source_type"),
    )


class ChangeRequest(Base):
    __tablename__ = "change_request"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(Text)
    change_level = Column(String(16))
    requester_id = Column(Integer, ForeignKey("team_member.id"))
    affected_lines = Column(String(256))
    impact_scope = Column(Text)
    impact_schedule = Column(Text)
    impact_cost = Column(Text)
    status = Column(String(16), default="pending")
    reviewer_id = Column(Integer, ForeignKey("team_member.id"))
    review_notes = Column(Text)
    submitted_date = Column(Date)
    decision_date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)
    attachment_path = Column(String(512))
    attachment_name = Column(String(256))
    attachment_size = Column(Integer)

    project = relationship("Project", back_populates="changes")
    requester = relationship("TeamMember", foreign_keys=[requester_id], lazy="joined")
    reviewer = relationship("TeamMember", foreign_keys=[reviewer_id], lazy="joined")

    __table_args__ = (Index("idx_change_project", "project_id"),)


class ChangeSignoffRecord(Base):
    """变更签核记录(两级:1=项目负责人,2=管理层复核)。"""
    __tablename__ = "change_signoff_record"
    id = Column(Integer, primary_key=True)
    change_id = Column(Integer, ForeignKey("change_request.id"), nullable=False)
    level = Column(Integer, nullable=False)  # 1=项目负责人 2=管理层复核
    signer_id = Column(Integer, ForeignKey("team_member.id"), nullable=False)
    status = Column(String(16), default="pending")  # pending/approved/rejected
    comment = Column(Text)
    signed_by_username = Column(String(64))
    signed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    change = relationship("ChangeRequest", backref="signoff_records")
    signer = relationship("TeamMember", lazy="joined")

    __table_args__ = (
        UniqueConstraint("change_id", "level", name="uq_change_signoff_level"),
        Index("idx_csr_signer", "signer_id", "status"),
    )


class Deliverable(Base):
    __tablename__ = "deliverable"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    phase_id = Column(Integer, ForeignKey("phase.id"), nullable=False)
    line_id = Column(Integer, ForeignKey("technical_line.id"))
    name = Column(String(256), nullable=False)
    description = Column(Text)
    file_path = Column(String(512))
    content = Column(Text)
    status = Column(String(16), default="not_submitted")
    owner_id = Column(Integer, ForeignKey("team_member.id"))
    submitted_date = Column(Date)

    project = relationship("Project", back_populates="deliverables")
    phase = relationship("Phase", lazy="joined")
    line = relationship("TechnicalLine", lazy="joined")
    owner = relationship("TeamMember", lazy="joined")
    attachments = relationship(
        "DeliverableAttachment", back_populates="deliverable",
        cascade="all, delete-orphan", order_by="DeliverableAttachment.id",
    )

    __table_args__ = (
        Index("idx_deliv_project", "project_id"),
        Index("idx_deliv_matrix", "project_id", "phase_id", "line_id"),
    )


class ProjectDocument(Base):
    __tablename__ = "project_document"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    name = Column(String(256), nullable=False)
    doc_type = Column(String(32), nullable=False, default="other")
    file_path = Column(String(512))
    file_size = Column(Integer)
    uploaded_by = Column(String(64))
    upload_date = Column(Date)
    notes = Column(Text)
    content = Column(Text)
    phase_id = Column(Integer, ForeignKey("phase.id"))
    folder = Column(String(256), default="")
    tags = Column(Text, default="[]")
    space_id = Column(String(32), default="default")
    ext_visibility = Column(String(16), default="shared")
    source_filename = Column(String(256))
    source_url = Column(String(512))
    doc_description = Column(String(500))
    created_by = Column(String(64))
    status = Column(String(16), default="active")
    version = Column(Integer, default=1)
    replaced_by_id = Column(Integer, ForeignKey("project_document.id"))
    owner_id = Column(Integer, ForeignKey("user_auth.id"), nullable=True)

    project = relationship("Project")
    replaced_by = relationship("ProjectDocument", remote_side=[id], foreign_keys=[replaced_by_id])
    owner_user = relationship("UserAuth", foreign_keys=[owner_id])

    __table_args__ = (Index("idx_doc_project", "project_id"),)


# ── Knowledge Base dedicated tables ──

class KbSpace(Base):
    __tablename__ = "kb_space"
    id = Column(String(32), primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text)
    icon = Column(String(16), default="📁")
    creator_id = Column(Integer, ForeignKey("user_auth.id"))
    is_public = Column(Boolean, default=False)
    doc_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class KbSpaceMember(Base):
    __tablename__ = "kb_space_member"
    id = Column(Integer, primary_key=True)
    space_id = Column(String(32), ForeignKey("kb_space.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user_auth.id"), nullable=False)
    role = Column(String(16), nullable=False, default="viewer")
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("space_id", "user_id", name="uq_space_member"),)


class KbFolder(Base):
    __tablename__ = "kb_folder"
    id = Column(Integer, primary_key=True)
    space_id = Column(String(32), default="default")
    parent_path = Column(String(256), default="/")
    name = Column(String(128), nullable=False)
    path = Column(String(512), nullable=False)
    doc_count = Column(Integer, default=0)
    creator_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("space_id", "path", name="uq_folder_path"),)


class KbVector(Base):
    __tablename__ = "kb_vector"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("project_document.id"), nullable=False, unique=True)
    embedding = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class KbDocumentVersion(Base):
    __tablename__ = "kb_document_version"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("project_document.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    title = Column(String(256))
    content_preview = Column(Text)
    saved_by = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("document_id", "version_number", name="uq_doc_version"),)


class KbDocumentShare(Base):
    __tablename__ = "kb_document_share"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("project_document.id", ondelete="CASCADE"), nullable=False)
    shared_with_user_id = Column(Integer, ForeignKey("user_auth.id"), nullable=False)
    access_level = Column(String(16), nullable=False, default="limited")  # "limited" or "full"
    shared_by_user_id = Column(Integer, ForeignKey("user_auth.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("document_id", "shared_with_user_id", name="uq_doc_share"),)


class ProjectHealthSnapshot(Base):
    __tablename__ = "project_health_snapshot"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    snapshot_date = Column(Date, nullable=False)
    completion_pct = Column(Integer)
    schedule_deviation = Column(Integer)
    open_risks_count = Column(Integer)
    open_issues_count = Column(Integer)
    morale = Column(String(16))
    overall_status = Column(String(16))

    __table_args__ = (UniqueConstraint("project_id", "snapshot_date", name="uq_snapshot"),)


class UserAuth(Base):
    __tablename__ = "user_auth"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    member_id = Column(Integer, ForeignKey("team_member.id"))
    role = Column(String(16), default="member")
    role_id = Column(Integer, ForeignKey("permission_role.id"))
    permissions = Column(Text, default="{}")
    dingtalk_id = Column(String(128), unique=True)
    refresh_token = Column(String(256), unique=True)
    is_active = Column(Boolean, default=True)
    kb_admin = Column(Boolean, default=False)   # 知识库管理员:可删除知识库中的项目文档
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)

    member = relationship("TeamMember", lazy="joined")

    __table_args__ = (Index("idx_user_refresh_token", "refresh_token"),)


class Department(Base):
    """部门字典（权限矩阵的载体）。"""
    __tablename__ = "department"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    permissions = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PermissionRole(Base):
    """系统权限角色：dept_id 为空=内置角色（code 与旧 role 值对齐）。"""
    __tablename__ = "permission_role"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    code = Column(String(32), unique=True, nullable=True)
    dept_id = Column(Integer, ForeignKey("department.id"), nullable=True)
    permissions = Column(Text, default="{}")
    desc = Column(String(256), default="")
    is_builtin = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department", lazy="joined")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), nullable=False)
    action = Column(String(16), nullable=False)
    entity_type = Column(String(32), nullable=False)
    entity_id = Column(Integer)
    entity_name = Column(String(256))
    project_id = Column(Integer, ForeignKey("project.id"))
    summary = Column(String(512))
    details = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", lazy="joined")

    __table_args__ = (
        Index("idx_audit_time", "created_at"),
        Index("idx_audit_project", "project_id", "created_at"),
        Index("idx_audit_user", "username", "created_at"),
    )


class Transaction(Base):
    """Financial transaction record (收入/支出)."""
    __tablename__ = "transaction"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    type = Column(String(8), nullable=False, default="income")  # income / expense
    category = Column(String(32), nullable=False)  # 合同回款/材料采购/外协加工/测试费/差旅/其他
    amount = Column(Float, nullable=False, default=0)
    description = Column(String(256))
    trans_date = Column(Date, nullable=False)
    recorded_by = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="transactions")

    __table_args__ = (
        Index("idx_trans_project", "project_id", "trans_date"),
    )


class Requirement(Base):
    """Project requirement (需求管理)."""
    __tablename__ = "requirement"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(Text)
    category = Column(String(32), default="functional")  # functional/performance/interface/safety/reliability/cost
    priority = Column(String(8), default="P1")            # P0/P1/P2/P3
    source = Column(String(128))                           # 客户/技术协议/标准规范/内部
    status = Column(String(16), default="draft")           # draft/reviewed/approved/changed/closed
    version = Column(Integer, default=1)
    change_history = Column(Text)                          # JSON: [{version, date, change, author}]
    deliverable_id = Column(Integer, ForeignKey("deliverable.id"), nullable=True)
    attachment_path = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime)

    project = relationship("Project", back_populates="requirements")
    deliverable = relationship("Deliverable", foreign_keys=[deliverable_id])

    __table_args__ = (
        Index("idx_req_project", "project_id"),
        Index("idx_req_priority", "project_id", "priority"),
    )


class Task(Base):
    """WBS task (工作分解)."""
    __tablename__ = "task"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("task.id"), nullable=True)
    name = Column(String(256), nullable=False)
    description = Column(Text)
    assignee_id = Column(Integer, ForeignKey("team_member.id"), nullable=True)
    line_id = Column(Integer, ForeignKey("technical_line.id"), nullable=True)
    phase_id = Column(Integer, ForeignKey("phase.id"), nullable=True)
    start_date = Column(Date)
    end_date = Column(Date)
    progress_pct = Column(Integer, default=0)
    status = Column(String(16), default="pending")  # pending/in_progress/completed/blocked/cancelled
    priority = Column(String(8), default="P2")
    sort_order = Column(Integer, default=0)
    milestone_id = Column(Integer, ForeignKey("milestone.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="tasks")
    parent = relationship("Task", remote_side=[id], backref="children")
    assignee = relationship("TeamMember", lazy="joined")
    line = relationship("TechnicalLine", lazy="joined")
    phase = relationship("Phase", lazy="joined")
    milestone = relationship("Milestone", lazy="joined")

    __table_args__ = (
        Index("idx_task_project", "project_id"),
        Index("idx_task_parent", "parent_id"),
    )


class TestPlan(Base):
    """测试验证计划 (DV/PV/Bench/Durability/Environmental)."""
    __tablename__ = "test_plan"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    name = Column(String(256), nullable=False)
    test_type = Column(String(32), nullable=False, default="DV")  # DV/PV/bench/durability/environmental/other
    phase_id = Column(Integer, ForeignKey("phase.id"), nullable=True)
    description = Column(Text)
    planned_start = Column(Date)
    planned_end = Column(Date)
    actual_start = Column(Date)
    actual_end = Column(Date)
    status = Column(String(16), default="planned")  # planned/in_progress/completed/cancelled
    attachment_path = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project")
    phase = relationship("Phase", lazy="joined")
    results = relationship("TestResult", back_populates="test_plan", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_tp_project", "project_id"),)


class TestResult(Base):
    """测试结果记录."""
    __tablename__ = "test_result"
    id = Column(Integer, primary_key=True)
    test_plan_id = Column(Integer, ForeignKey("test_plan.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    name = Column(String(256), nullable=False)
    test_date = Column(Date)
    result = Column(String(16), default="pending")  # pending/pass/fail/partial
    measured_value = Column(Text)
    spec_value = Column(Text)
    notes = Column(Text)
    attachment_path = Column(String(512))

    test_plan = relationship("TestPlan", back_populates="results")
    project = relationship("Project")


class TestIssue(Base):
    """测试问题 8D 闭环."""
    __tablename__ = "test_issue"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    test_result_id = Column(Integer, ForeignKey("test_result.id"), nullable=True)
    title = Column(String(256), nullable=False)
    description = Column(Text)
    severity = Column(String(8), default="中")  # 高/中/低
    status = Column(String(16), default="open")  # open/analyzing/resolved/closed

    # 8D fields
    d1_team = Column(Text)         # 团队成员
    d2_problem = Column(Text)      # 问题描述
    d3_containment = Column(Text)  # 临时措施
    d4_root_cause = Column(Text)   # 根因分析
    d5_corrective = Column(Text)   # 永久纠正措施
    d6_implementation = Column(Text) # 实施验证
    d7_prevention = Column(Text)   # 预防措施
    d8_recognition = Column(Text)  # 团队认可

    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime)

    project = relationship("Project")
    test_result = relationship("TestResult")

    __table_args__ = (Index("idx_ti_project", "project_id"),)


class PrototypeBuild(Base):
    """样机试制批次."""
    __tablename__ = "prototype_build"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    batch_name = Column(String(128), nullable=False)
    planned_qty = Column(Integer, default=1)
    actual_qty = Column(Integer)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(16), default="planned")  # planned/material_ready/in_progress/completed
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project")
    material_checks = relationship("MaterialCheck", back_populates="build", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_pb_project", "project_id"),)


class MaterialCheck(Base):
    """物料齐套检查."""
    __tablename__ = "material_check"
    id = Column(Integer, primary_key=True)
    prototype_build_id = Column(Integer, ForeignKey("prototype_build.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    material_name = Column(String(256), nullable=False)
    specification = Column(String(256))
    required_qty = Column(Integer, default=0)
    available_qty = Column(Integer, default=0)
    status = Column(String(16), default="ordered")  # ready/missing/ordered/urgent
    supplier = Column(String(128))
    lead_time_days = Column(Integer)
    notes = Column(Text)

    build = relationship("PrototypeBuild", back_populates="material_checks")
    project = relationship("Project")

    __table_args__ = (Index("idx_mc_build", "prototype_build_id"),)


class CustomerAccess(Base):
    """Customer portal access — per-project shareable access."""
    __tablename__ = "customer_access"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("client.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    access_code = Column(String(32), unique=True, nullable=False)  # shareable code
    password_hash = Column(String(256))  # optional password
    permissions = Column(String(64), default="view")  # view / comment / approve
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime)
    expires_at = Column(DateTime)

    client = relationship("Client")
    project = relationship("Project")


class BomItem(Base):
    """BOM (Bill of Materials) item — hierarchical."""
    __tablename__ = "bom_item"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    build_id = Column(Integer, ForeignKey("prototype_build.id", ondelete="CASCADE"), nullable=True)
    parent_id = Column(Integer, ForeignKey("bom_item.id"), nullable=True)
    level = Column(Integer, default=0)
    part_number = Column(String(64))
    name = Column(String(256), nullable=False)
    specification = Column(String(256))
    material = Column(String(128))
    quantity = Column(Float, default=1)
    unit = Column(String(16), default="pcs")
    supplier = Column(String(128))
    drawing_file = Column(String(512))    # CAD/drawing file path
    model_file = Column(String(512))      # 3D model file path
    notes = Column(Text)
    sort_order = Column(Integer, default=0)

    project = relationship("Project")
    parent = relationship("BomItem", remote_side=[id], backref="children")

    __table_args__ = (Index("idx_bom_project", "project_id"), Index("idx_bom_parent", "parent_id"))


class Ecn(Base):
    """Engineering Change Notice (工程变更通知)."""
    __tablename__ = "ecn"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    ecn_number = Column(String(32), unique=True, nullable=False)
    title = Column(String(256), nullable=False)
    reason = Column(Text)
    change_description = Column(Text)
    affected_items = Column(Text)  # JSON list of affected BOM/drawing/doc IDs
    status = Column(String(16), default="draft")  # draft/submitted/reviewed/approved/rejected/implemented
    submitted_by = Column(String(64))
    approved_by = Column(String(64))
    submitted_date = Column(Date)
    approved_date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project")

    __table_args__ = (Index("idx_ecn_project", "project_id"),)


class ApiKey(Base):
    """API Key for external system integration."""
    __tablename__ = "api_key"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    key_hash = Column(String(128), unique=True, nullable=False)
    key_prefix = Column(String(8), nullable=False)  # first 8 chars for display
    permissions = Column(String(128), default="read")  # read / write / admin
    is_active = Column(Boolean, default=True)
    created_by = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime)
    expires_at = Column(DateTime)


class WebhookConfig(Base):
    """Webhook configuration for event notifications."""
    __tablename__ = "webhook_config"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    url = Column(String(512), nullable=False)
    secret = Column(String(128))
    events = Column(String(256), default="project.status_change,milestone.completed,risk.created")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_triggered_at = Column(DateTime)
    failure_count = Column(Integer, default=0)


class GateDeliverableStandard(Base):
    """阶段交付物标准(全局配置,按阶段维护)。"""
    __tablename__ = "gate_deliverable_standard"
    id = Column(Integer, primary_key=True)
    phase_id = Column(Integer, ForeignKey("phase.id"), nullable=False)
    name = Column(String(256), nullable=False)
    category = Column(String(64))  # document/report/approval/other
    required = Column(Boolean, default=True)
    description = Column(Text)
    acceptance_criteria = Column(Text)  # 通过标准
    responsible_role = Column(String(64))  # 责任角色
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    template_path = Column(String(512))  # 上传的模板文件(相对 UPLOAD_DIR);为空时下载自动生成骨架
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    phase = relationship("Phase", lazy="joined")

    __table_args__ = (Index("idx_gds_phase", "phase_id"),)


class GateSignoffRecord(Base):
    """阶段门签核记录(两级:1=项目负责人,2=管理层复核)。"""
    __tablename__ = "gate_signoff_record"
    id = Column(Integer, primary_key=True)
    project_phase_gate_id = Column(Integer, ForeignKey("project_phase_gate.id"), nullable=False)
    level = Column(Integer, nullable=False)  # 1=项目负责人 2=管理层复核
    signer_id = Column(Integer, ForeignKey("team_member.id"), nullable=False)
    status = Column(String(16), default="pending")  # pending/approved/rejected
    comment = Column(Text)
    signed_by_username = Column(String(64))
    signed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    phase_gate = relationship("ProjectPhaseGate", backref="signoff_records")
    signer = relationship("TeamMember", lazy="joined")

    __table_args__ = (
        UniqueConstraint("project_phase_gate_id", "level", name="uq_signoff_level"),
        Index("idx_gsr_signer", "signer_id", "status"),
    )


class TrainingMaterial(Base):
    """培训学习素材(每个模块的学习视频/操作手册)。"""
    __tablename__ = "training_material"
    id = Column(Integer, primary_key=True)
    category = Column(String(64), nullable=False)      # 所属模块/分类,如"阶段门评审"
    title = Column(String(256), nullable=False)        # 素材标题
    description = Column(Text)                          # 简介/说明
    material_type = Column(String(16), default="video")  # video/manual/other
    file_path = Column(String(512))                     # 相对 UPLOAD_DIR
    file_ext = Column(String(16))
    file_size = Column(Integer, default=0)
    uploader = Column(String(64))                       # 上传人用户名
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_tm_category", "category"),)


class TrainingTask(Base):
    """培训任务定义(按模块 x 基础/进阶/高级三档)。"""
    __tablename__ = "training_task"
    id = Column(Integer, primary_key=True)
    category = Column(String(64), nullable=False)      # 所属模块,如"客户管理"
    level = Column(String(16), nullable=False)         # basic/intermediate/advanced
    title = Column(String(256), nullable=False)        # 任务标题
    description = Column(Text)                          # 任务说明(怎么算完成)
    points = Column(Integer, default=10)                # 分值
    required_target = Column(String(64))                # 提交前必须实操的模块页面路径(如 /product-tech)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_tt_category", "category", "level"),)


class TrainingModuleVisit(Base):
    """培训任务实操痕迹:进入关联模块页面时前端上报一次,用于校验提交前是否实际访问过。"""
    __tablename__ = "training_module_visit"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_auth.id"), nullable=False)
    username = Column(String(64))                       # 冗余存用户名便于查询
    module_path = Column(String(128), nullable=False)   # 访问的页面路径
    visited_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_tmv_user_path", "user_id", "module_path", "visited_at"),)


class TrainingTaskProgress(Base):
    """培训任务完成进度(每个账号对每条任务的完成情况)。"""
    __tablename__ = "training_task_progress"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("training_task.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user_auth.id"), nullable=False)
    username = Column(String(64))                       # 冗余存用户名便于显示
    status = Column(String(16), default="pending")      # pending/submitted/approved/rejected
    submit_note = Column(Text)                          # 提交时填写的完成说明
    review_note = Column(String(256))                   # 审核备注
    reviewed_by = Column(String(64))                    # 审核人
    submitted_at = Column(DateTime)
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    task = relationship("TrainingTask", lazy="joined")

    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_ttprogress_task_user"),)


class DeliverableAttachment(Base):
    """交付物多附件（三维模型、仿真过程视频等设计资料）。"""
    __tablename__ = "deliverable_attachment"
    id = Column(Integer, primary_key=True)
    deliverable_id = Column(Integer, ForeignKey("deliverable.id"), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_name = Column(String(256))
    file_size = Column(Integer, default=0)
    uploaded_by = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)

    deliverable = relationship("Deliverable", back_populates="attachments")

    __table_args__ = (Index("idx_deliv_att", "deliverable_id"),)
