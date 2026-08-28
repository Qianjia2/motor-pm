"""Pydantic v2 schemas for request/response validation."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from datetime import date, datetime


# ═══════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=3, max_length=128)
    member_id: Optional[int] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


# ═══════════════════════════════════════════════
# Project
# ═══════════════════════════════════════════════

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    code: str = Field(..., min_length=1, max_length=32)  # relaxed validation
    project_type: Optional[str] = "hardware"  # hardware=电机研发项目, software=软件研发项目
    description: Optional[str] = None
    client_id: Optional[int] = None  # not required on create
    current_phase_id: Optional[int] = None
    start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    priority: Optional[str] = "P1"
    difficulty: Optional[str] = None
    contract_amount: Optional[float] = None
    budget: Optional[float] = None
    final_deliverable: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    problem_statement: Optional[str] = None
    aligned_target: Optional[str] = None
    deadline_type: Optional[str] = None

    @field_validator("start_date", "planned_end_date", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" or v is None else v


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    code: Optional[str] = None  # allow any format on update (frontend may send existing code unchanged)
    project_type: Optional[str] = None
    description: Optional[str] = None
    client_id: Optional[int] = None
    current_phase_id: Optional[int] = None
    start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    actual_end_date: Optional[date] = None

    @field_validator("start_date", "planned_end_date", "actual_end_date", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" or v is None else v
    overall_status: Optional[str] = None
    completion_pct: Optional[int] = Field(default=None, ge=0, le=100)
    priority: Optional[str] = None
    difficulty: Optional[str] = None
    contract_amount: Optional[float] = None
    received_amount: Optional[float] = None
    budget: Optional[float] = None
    actual_cost: Optional[float] = None
    final_deliverable: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    problem_statement: Optional[str] = None
    aligned_target: Optional[str] = None
    deadline_type: Optional[str] = None
    main_blocker: Optional[str] = None
    blocker_duration: Optional[str] = None
    morale: Optional[str] = None
    success_confidence: Optional[str] = None
    version: Optional[int] = None  # optimistic locking — optional, skip if not provided


class CopyProjectRequest(BaseModel):
    new_code: str = Field(..., pattern=r'^[A-Z]{2,4}-\d{4}-\d{3}$')


# ═══════════════════════════════════════════════
# Milestone
# ═══════════════════════════════════════════════

class MilestoneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    planned_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    actual_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    line_id: Optional[int] = None
    phase_id: Optional[int] = None
    depends_on_id: Optional[int] = None
    status: Literal["pending", "in_progress", "completed", "overdue"] = "pending"
    is_key: bool = False

    @field_validator("planned_date", "planned_end_date", "actual_date", "actual_end_date", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" or v is None else v


class MilestoneUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    planned_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    actual_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    line_id: Optional[int] = None
    phase_id: Optional[int] = None
    depends_on_id: Optional[int] = None
    status: Optional[Literal["pending", "in_progress", "completed", "overdue"]] = None
    is_key: Optional[bool] = None

    @field_validator("planned_date", "planned_end_date", "actual_date", "actual_end_date", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" or v is None else v


# ═══════════════════════════════════════════════
# Weekly Report
# ═══════════════════════════════════════════════

class WeeklyReportLineItem(BaseModel):
    line_id: int
    this_week: str = ""
    next_week: str = ""
    status: Optional[str] = None
    blocker: str = ""
    coordinator: str = ""


class WeeklyReportCreate(BaseModel):
    year: Optional[int] = None
    week_number: Optional[int] = None
    report_date: Optional[date] = None
    overall_progress: str = ""
    key_accomplishments: str = ""
    completion_rate: Optional[str] = None
    reporter_id: Optional[int] = None
    line_items: List[WeeklyReportLineItem] = Field(default_factory=lambda: [
        WeeklyReportLineItem(line_id=2), WeeklyReportLineItem(line_id=3),
        WeeklyReportLineItem(line_id=4), WeeklyReportLineItem(line_id=5),
        WeeklyReportLineItem(line_id=6),
    ])

    @field_validator("line_items")
    @classmethod
    def must_have_five_lines(cls, v):
        if len(v) != 5:
            raise ValueError(f"周报必须包含5条技术线，当前{len(v)}条")
        line_ids = {item.line_id for item in v}
        if line_ids != {2, 3, 4, 5, 6}:
            raise ValueError(f"line_id 必须是 2-6, got {line_ids}")
        return v


class WeeklyReportUpdate(BaseModel):
    year: Optional[int] = None
    week_number: Optional[int] = None
    report_date: Optional[date] = None
    reporter_id: Optional[int] = None
    overall_progress: Optional[str] = None
    key_accomplishments: Optional[str] = None
    completion_rate: Optional[str] = None


# ═══════════════════════════════════════════════
# Risk / Issue
# ═══════════════════════════════════════════════

class RiskIssueCreate(BaseModel):
    type: Literal["risk", "issue"] = "risk"
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    probability: Optional[Literal["high", "medium", "low"]] = None
    impact: Optional[Literal["high", "medium", "low"]] = None
    risk_level: Optional[Literal["critical", "high", "medium", "low"]] = None
    severity: Optional[Literal["S", "A", "B", "C"]] = None
    mitigation_plan: Optional[str] = None
    owner_id: Optional[int] = None
    line_id: Optional[int] = None
    phase_id: Optional[int] = None
    identified_date: Optional[date] = None
    target_resolve_date: Optional[date] = None


class RiskIssueUpdate(BaseModel):
    type: Optional[Literal["risk", "issue"]] = None
    title: Optional[str] = Field(None, max_length=256)
    description: Optional[str] = None
    probability: Optional[Literal["high", "medium", "low"]] = None
    impact: Optional[Literal["high", "medium", "low"]] = None
    risk_level: Optional[Literal["critical", "high", "medium", "low"]] = None
    severity: Optional[Literal["S", "A", "B", "C"]] = None
    status: Optional[Literal["open", "in_progress", "resolved", "closed", "wont_fix"]] = None
    mitigation_plan: Optional[str] = None
    owner_id: Optional[int] = None
    line_id: Optional[int] = None
    phase_id: Optional[int] = None
    identified_date: Optional[date] = None
    target_resolve_date: Optional[date] = None


class CloseRiskRequest(BaseModel):
    resolution: str = Field(..., min_length=1, max_length=5000)


# ═══════════════════════════════════════════════
# Change Request
# ═══════════════════════════════════════════════

class ChangeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    change_level: Literal["A", "B", "C"] = "C"
    requester_id: Optional[int] = None
    affected_lines: Optional[str] = None
    impact_scope: Optional[str] = None
    impact_schedule: Optional[str] = None
    impact_cost: Optional[str] = None
    submitted_date: Optional[date] = None


class ChangeUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=256)
    description: Optional[str] = None
    change_level: Optional[Literal["A", "B", "C"]] = None
    affected_lines: Optional[str] = None
    impact_scope: Optional[str] = None
    impact_schedule: Optional[str] = None
    impact_cost: Optional[str] = None
    status: Optional[Literal["pending", "approved", "rejected", "implemented"]] = None
    reviewer_id: Optional[int] = None
    review_notes: Optional[str] = None
    decision_date: Optional[date] = None


# ═══════════════════════════════════════════════
# Deliverable
# ═══════════════════════════════════════════════

class DeliverableCreate(BaseModel):
    phase_id: int
    line_id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    status: Literal["not_submitted", "submitted", "reviewed", "approved", "rejected"] = "not_submitted"
    owner_id: Optional[int] = None


class DeliverableUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=256)
    description: Optional[str] = None
    phase_id: Optional[int] = None
    line_id: Optional[int] = None
    status: Optional[Literal["not_submitted", "submitted", "reviewed", "approved", "rejected"]] = None
    owner_id: Optional[int] = None
    submitted_date: Optional[date] = None
    file_path: Optional[str] = None

    @field_validator("submitted_date", mode="before")
    @classmethod
    def empty_date_to_none(cls, v):
        return None if v == "" else v


# ═══════════════════════════════════════════════
# Document
# ═══════════════════════════════════════════════

class DocumentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    doc_type: str
    notes: Optional[str] = None
    upload_date: Optional[date] = None


class DocumentUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=256)
    doc_type: Optional[str] = None
    notes: Optional[str] = None
    content: Optional[str] = None


# ═══════════════════════════════════════════════
# Phase Gate
# ═══════════════════════════════════════════════

class PhaseGateUpdate(BaseModel):
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    status: Optional[str] = None
    gate_status: Optional[Literal["pending", "passed", "failed", "waived"]] = None
    gate_review_date: Optional[date] = None
    gate_review_notes: Optional[str] = None

    @field_validator("planned_start_date", "planned_end_date", "actual_start_date", "actual_end_date", "gate_review_date", "gate_status", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" or v is None else v


class ActionItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    due_date: Optional[date] = None


class ActionItemUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=256)
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    due_date: Optional[date] = None
    status: Optional[Literal["open", "in_progress", "closed"]] = None
    resolution: Optional[str] = None


# ═══════════════════════════════════════════════
# Team
# ═══════════════════════════════════════════════

class ProjectMemberCreate(BaseModel):
    member_id: int
    role_id: int
    allocation_pct: int = Field(default=100, ge=0, le=100)
    is_key: bool = False
    phase_ids: Optional[str] = "[]"  # JSON array of phase IDs: "[1,2,3]"


class ProjectMemberUpdate(BaseModel):
    role_id: Optional[int] = None
    allocation_pct: Optional[int] = Field(default=None, ge=0, le=100)
    is_key: Optional[bool] = None
    phase_ids: Optional[str] = None  # override phase permissions


# ═══════════════════════════════════════════════
# Client
# ═══════════════════════════════════════════════

class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    abbreviation: str = Field(..., min_length=1, max_length=16)
    industry: Optional[str] = None
    address: Optional[str] = None
    cooperation_status: Optional[str] = Field(None, max_length=32)
    phone: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    abbreviation: Optional[str] = Field(None, max_length=16)
    industry: Optional[str] = None
    address: Optional[str] = None
    cooperation_status: Optional[str] = Field(None, max_length=32)
    phone: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


# ═══════════════════════════════════════════════
# Pagination
# ═══════════════════════════════════════════════

class AIChatRequest(BaseModel):
    question: str = ""
    mode: str = "auto"  # "auto" | "project" | "general"


class PaginatedResponse(BaseModel):
    data: list = []
    total: int = 0
    page: int = 1
    page_size: int = 20
