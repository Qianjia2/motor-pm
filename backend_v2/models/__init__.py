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
    project_id = Column(Integer, ForeignKey("project.id"), nullable=True)   # 关联项目(可选)
    project = relationship("Project")
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
    # 个人权限矩阵的来源：NULL=未初始化(待启动回填) / 'dept'=来自部门模板 / 'manual'=人工单独配置。
    # 只服务于 UI 展示和「一键下发」的覆盖提示——权限判定本身只看 permissions 有没有内容，
    # 不依赖这一列（见 permissions.is_configured）。
    perm_source = Column(String(8))
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


class ProjectWorkflowStepConfirm(Base):
    """项目工作流·线下步骤的人工确认。

    平台观测不到线下动作(客户调研拜访、UAT、现场部署、客户培训、客户验收),
    这些步骤的状态只能由人确认,本表就是那份留痕。

    节点身份 = (阶段码, 阶段内序号): PHASE_NODES 的节点只存在于代码常量里,
    没有数据库主键,身份只能由配置给出,所以唯一键用配置身份而非代理键。
    用 phase_code 而不是 phase_id: 历史迁移改过 phase 的 id(见
    scripts/migrate_software_phases_s0_s3.py),code 不变,否则迁移后确认记录会挂错阶段。
    序号在同一阶段内唯一、跨阶段重复(每个阶段都有 seq=1),故必须带上阶段。
    """
    __tablename__ = "project_workflow_step_confirm"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    phase_id = Column(Integer, ForeignKey("phase.id"), nullable=False)  # 便于按阶段统计
    phase_code = Column(String(16), nullable=False)
    node_seq = Column(Integer, nullable=False)
    node_name = Column(String(128))                # 确认时的节点名快照
    confirmed_by = Column(String(64))              # 账号,风格同 gate_signoff_record.signed_by_username
    confirmed_at = Column(DateTime, default=datetime.utcnow)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "phase_code", "node_seq", name="uq_pwsc_step"),
        Index("idx_pwsc_project", "project_id", "phase_id"),
    )


# ══════════════════════════════════════════════════════════════════════
# 工作流引擎（一期地基）
#
# 和既有 PHASE_NODES 的关系：PHASE_NODES 是项目级宏观流程（85 个步骤，
# 硬编码在 routes/training_process.py），它是**模板层的素材**，不是被替换的
# 对象——本次一行都没改。本引擎把它的每一步导入成 wf_state_def，补上标准
# 状态语义、流转规则和按人权限。唯一衔接点 = phase_code / node_seq。
#
# 三层严格分开（需求明确要求，不要混成一个字段）：
#   元模型/属性/工作流三者分离 → 状态定义(wf_state_def) 与 权限(wf_node_acl_def)
#   与 流转(wf_transition_def) 各自成表，互不内嵌。
#   模板层  wf_template / wf_template_version / wf_state_def /
#           wf_transition_def / wf_node_acl_def
#   项目层  project_wf_instance / project_wf_state /
#           project_wf_transition / project_wf_node_acl
#   台账    wf_state_change_log / wf_force_drag_log
#
# 为什么 subject_name 和 subject_id 两个都存：PHASE_NODES 用到 16 个角色名，
# 其中 8 个（工艺工程师/技术负责人/管理层/试制负责人/采购/财务/责任工程师/
# 市场运营）**在 role 表里根本不存在**。只存外键的话这 8 个角色名全丢，
# 那些步骤会变成"除了管理员没人推得动"。所以按名字存是主，id 是能解析时的
# 加速与改名追踪用。既有 _can_confirm_node 本来就是按名字匹配的，这里一致。
# ══════════════════════════════════════════════════════════════════════


class WfTemplate(Base):
    """工作流模板（四类项目模板的载体）。

    一期只落 A/B 两个（A=合同交付·电机电控集成 ↔ hardware，B=合同交付·软件
    定制 ↔ software）。两者一一对应，所以 project 表**不需要新增任何列**——
    项目选了哪个模板记在 project_wf_instance.template_id 上。以后加 C/D
    （内部研发）只是插两行数据，不动表结构。
    """
    __tablename__ = "wf_template"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), nullable=False, unique=True)
    name = Column(String(64), nullable=False)
    project_type = Column(String(16), nullable=False)     # hardware / software
    category = Column(String(16), default="contract")     # contract=合同交付 / internal=内部研发
    description = Column(Text)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class WfTemplateVersion(Base):
    """模板版本。升级不推送——项目实例停在自己记录的版本上，直到 PM 主动迁移。

    版本一旦有项目实例在用就不改内容，改内容一律新建版本。这是"记录基于哪个
    模板版本"能成立的前提：如果版本可原地改，"基于 v1"这句话就没有意义了。
    """
    __tablename__ = "wf_template_version"
    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("wf_template.id"), nullable=False)
    version_no = Column(Integer, nullable=False)
    status = Column(String(16), default="published")      # draft / published / archived
    note = Column(Text)
    created_by = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)

    template = relationship("WfTemplate", lazy="joined")
    __table_args__ = (
        UniqueConstraint("template_id", "version_no", name="uq_wftv_no"),
        Index("idx_wftv_tpl", "template_id"),
    )


class WfStateDef(Base):
    """模板层的状态节点定义。

    state_code 在模板内稳定，形如 "PP1-3"/"S0-2"（阶段码-序号）。项目实例、
    审计、自动化规则一律按 state_code 引用，**不按自增 id**——沿用
    ProjectWorkflowStepConfirm 的教训：历史迁移改过 phase 的 id，code 不变。
    """
    __tablename__ = "wf_state_def"
    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("wf_template_version.id"), nullable=False)
    state_code = Column(String(32), nullable=False)
    name = Column(String(128), nullable=False)            # 显示别名，可改
    semantic_state = Column(String(24), nullable=False)   # 七选一，不可自定义
    phase_code = Column(String(16))                       # 衔接 PHASE_NODES
    node_seq = Column(Integer)
    lane = Column(String(32))                             # 泳道 = 阶段
    sort_order = Column(Integer, default=0)
    is_initial = Column(Boolean, default=False)
    is_terminal = Column(Boolean, default=False)
    is_gate = Column(Boolean, default=False)              # 阶段末位门禁节点
    is_required = Column(Boolean, default=True)           # 跳过它要填原因（强制拖拽）
    entry_condition = Column(Text)                        # JSON，不用 eval
    exit_condition = Column(Text)                         # JSON
    sla_hours = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("version_id", "state_code", name="uq_wfsd_code"),
        Index("idx_wfsd_ver", "version_id", "sort_order"),
    )


class WfTransitionDef(Base):
    """模板层的流转规则：谁能从哪个状态走到哪个状态。

    只登记"允许的边"，不登记"必经路径"——必经与否由 project_wf_state
    .is_required + 强制拖拽的跳过检测算出来，避免两处定义打架。
    """
    __tablename__ = "wf_transition_def"
    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("wf_template_version.id"), nullable=False)
    from_state_code = Column(String(32), nullable=False)
    to_state_code = Column(String(32), nullable=False)
    name = Column(String(64))
    require_reason = Column(Boolean, default=False)       # 走这条边必须填原因
    auto = Column(Boolean, default=False)                 # 由自动化引擎触发，人不直接点
    sort_order = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_wftd_ver", "version_id", "from_state_code"),
    )


class WfNodeAclDef(Base):
    """模板层的节点权限默认值。

    四类权限原子：can_enter（进入）/ can_exit（退出）/ can_edit_fields（编辑字段）
    / can_force_drag（强制拖拽）。前三个**并集**（allow 胜），第四个**交集**
    （deny 胜）且**永不继承**——强制拖拽是 PM 的超级权限，模板默认给谁就是谁，
    不能因为"谁都没明确给"而落到某个宽泛的主体上。
    """
    __tablename__ = "wf_node_acl_def"
    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("wf_template_version.id"), nullable=False)
    state_code = Column(String(32), nullable=False)
    subject_type = Column(String(24), nullable=False)     # user / group / project_role / role_name
    subject_name = Column(String(64), nullable=False)     # 按名字存，见模块头注释
    subject_id = Column(Integer)                          # 能解析到 role.id 时填，解析不到为 NULL
    can_enter = Column(Boolean, default=True)
    can_exit = Column(Boolean, default=True)
    can_edit_fields = Column(Boolean, default=True)
    can_force_drag = Column(Boolean, default=False)
    field_scope = Column(Text)                            # JSON 数组，空=全部字段

    __table_args__ = (
        UniqueConstraint("version_id", "state_code", "subject_type", "subject_name",
                         name="uq_wfnad_key"),
        Index("idx_wfnad_lookup", "version_id", "state_code"),
    )


class ProjectWfInstance(Base):
    """项目层：一个项目挂到一个模板版本上的那次实例化。

    base_version_id 和 current_version_id 分开记：
      base    = 创建时基于哪个版本（"记录基于哪个模板版本"就是它，永不改）
      current = 现在跑在哪个版本（迁移后才会变，与 base 不同即"已迁移过"）
    两个都留，迁移差异才有比较对象。
    """
    __tablename__ = "project_wf_instance"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False, unique=True)
    template_id = Column(Integer, ForeignKey("wf_template.id"), nullable=False)
    base_version_id = Column(Integer, ForeignKey("wf_template_version.id"), nullable=False)
    current_version_id = Column(Integer, ForeignKey("wf_template_version.id"), nullable=False)
    status = Column(String(16), default="active")         # active / archived
    created_by = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)
    migrated_at = Column(DateTime)

    template = relationship("WfTemplate", lazy="joined")


class ProjectWfState(Base):
    """项目层的状态节点。实例化时深拷贝模板，之后可由 PM 自由调整。

    is_customized 是迁移时的冲突判据：模板新版和项目本地**两边都改过**的
    状态，迁移时列出来让人决定，绝不自动合并。
    """
    __tablename__ = "project_wf_state"
    id = Column(Integer, primary_key=True)
    instance_id = Column(Integer, ForeignKey("project_wf_instance.id"), nullable=False)
    state_code = Column(String(32), nullable=False)
    name = Column(String(128), nullable=False)
    semantic_state = Column(String(24), nullable=False)
    phase_code = Column(String(16))
    node_seq = Column(Integer)
    lane = Column(String(32))
    sort_order = Column(Integer, default=0)
    is_initial = Column(Boolean, default=False)
    is_terminal = Column(Boolean, default=False)
    is_gate = Column(Boolean, default=False)
    is_required = Column(Boolean, default=True)
    entry_condition = Column(Text)
    exit_condition = Column(Text)
    sla_hours = Column(Integer)
    # 运行态。引擎**持有**状态而不是每次从交付物现算——现算的话"强制拖拽把它
    # 推到已完成"这件事根本表达不出来（交付物没批，现算永远算回未开始）。
    # 既有 workflow 接口的推导逻辑保持不变，两者互不干扰。
    runtime_status = Column(String(24), default="not_started")
    status_source = Column(String(16), default="auto")   # auto=交付物推导 / manual=人推的 / force=强制拖拽
    last_changed_at = Column(DateTime)
    last_changed_by = Column(String(64))
    is_customized = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("instance_id", "state_code", name="uq_pwst_code"),
        Index("idx_pwst_inst", "instance_id", "sort_order"),
    )


class ProjectWfTransition(Base):
    """项目层的流转规则（模板流转规则的实例副本，可 PM 调整）。"""
    __tablename__ = "project_wf_transition"
    id = Column(Integer, primary_key=True)
    instance_id = Column(Integer, ForeignKey("project_wf_instance.id"), nullable=False)
    from_state_code = Column(String(32), nullable=False)
    to_state_code = Column(String(32), nullable=False)
    name = Column(String(64))
    require_reason = Column(Boolean, default=False)
    auto = Column(Boolean, default=False)
    is_customized = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)

    __table_args__ = (Index("idx_pwtd_inst", "instance_id", "from_state_code"),)


class ProjectWfNodeAcl(Base):
    """项目层的节点权限——**权限按人分配，就落在这张表**。

    实例化时从 wf_node_acl_def 深拷贝，之后 PM 只改这里，模板不受影响。
    subject_type='user' 时 subject_id = team_member.id，是按人的那一种。
    """
    __tablename__ = "project_wf_node_acl"
    id = Column(Integer, primary_key=True)
    instance_id = Column(Integer, ForeignKey("project_wf_instance.id"), nullable=False)
    state_code = Column(String(32), nullable=False)
    subject_type = Column(String(24), nullable=False)
    subject_name = Column(String(64), nullable=False)
    subject_id = Column(Integer)
    can_enter = Column(Boolean, default=True)
    can_exit = Column(Boolean, default=True)
    can_edit_fields = Column(Boolean, default=True)
    can_force_drag = Column(Boolean, default=False)
    field_scope = Column(Text)
    is_customized = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("instance_id", "state_code", "subject_type", "subject_name",
                         name="uq_pwna_key"),
        Index("idx_pwna_lookup", "instance_id", "state_code"),
    )


class WfStateChangeLog(Base):
    """状态流转台账（含正常流转与强制拖拽的入口记录）。

    与 AuditLog 分开：audit_log 是全局操作流水（给人看的"谁干了什么"），
    这张表是工作流自己的台账，要支撑"这个状态在谁手上停过多久"这类查询，
    字段结构不同，不硬塞进 audit_log 的 details JSON 里。
    """
    __tablename__ = "wf_state_change_log"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    instance_id = Column(Integer, ForeignKey("project_wf_instance.id"), nullable=False)
    state_code = Column(String(32), nullable=False)       # 这次动作针对的状态
    from_semantic = Column(String(24))
    to_semantic = Column(String(24), nullable=False)
    action = Column(String(16), nullable=False)           # enter / exit / advance / force_drag / revert
    operator = Column(String(64), nullable=False)
    operator_roles = Column(Text)                         # JSON 数组，动作发生时的角色快照
    reason = Column(Text)
    force_drag_log_id = Column(Integer)                   # 非空表示这次是强制拖拽
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_wfscl_proj", "project_id", "created_at"),
        Index("idx_wfscl_state", "instance_id", "state_code"),
    )


class WfForceDragLog(Base):
    """PM 强制拖拽的审计与回退台账（需求第 5 项）。

    from_/to_ 两侧都存 code+name+semantic 的快照：状态定义以后会被 PM 改名
    甚至删掉，审计要能独立复述"当时从哪拖到哪"，不能靠 join 现算。
    """
    __tablename__ = "wf_force_drag_log"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    instance_id = Column(Integer, ForeignKey("project_wf_instance.id"), nullable=False)
    from_state_code = Column(String(32))
    from_state_name = Column(String(128))
    from_semantic = Column(String(24))
    to_state_code = Column(String(32), nullable=False)
    to_state_name = Column(String(128))
    to_semantic = Column(String(24), nullable=False)
    operator = Column(String(64), nullable=False)
    operator_roles = Column(Text)                         # JSON 数组
    reason = Column(Text)                                 # 跳过必经验证节点时必填
    reason_required = Column(Boolean, default=False)      # 当时是否强制要求了原因
    skipped_states = Column(Text)                         # JSON：[{code,name,semantic}, ...]
    has_unrevertable = Column(Boolean, default=False)     # 是否跳过了不可回滚的动作
    auto_backlog_created = Column(Boolean, default=False) # 是否已自动建补验证待办
    is_reverted = Column(Boolean, default=False)
    reverted_at = Column(DateTime)
    reverted_by = Column(String(64))
    superseded_by_id = Column(Integer)                    # 被后一次强制拖拽取代时指向新的那条
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "from_state_code", "to_state_code", "created_at",
                         name="uq_wfdl_dedup"),
        Index("idx_wfdl_proj", "project_id", "created_at"),
    )
