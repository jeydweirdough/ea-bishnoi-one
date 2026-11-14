"""
Executive Admin data model (Phase 2.1 – 2.2).

Directory tables (companies, departments, employees) mirror what One Admin and
People will provide; in development they are seeded by app.seed. Everything
else is owned by Executive Admin.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import false

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(StrEnum):
    admin = "admin"
    assistant = "assistant"
    employee = "employee"


class RequestKind(StrEnum):
    concern = "concern"
    supplies = "supplies"
    asset = "asset"
    local_purchase = "local_purchase"
    repair = "repair"
    other = "other"


class RequestStatus(StrEnum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    returned = "returned"
    approved = "approved"
    rejected = "rejected"
    in_progress = "in_progress"
    awaiting_finance = "awaiting_finance"
    fulfilled = "fulfilled"
    closed = "closed"
    cancelled = "cancelled"


class Priority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    critical = "critical"


class StepStatus(StrEnum):
    waiting = "waiting"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    returned = "returned"
    skipped = "skipped"


class TaskStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class Recurrence(StrEnum):
    none = "none"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


# ------------------------------------------------------------------ directory


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(400))


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("company_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200))
    head_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", use_alter=True))

    company: Mapped[Company] = relationship(lazy="joined")


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_no: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    designation: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    role: Mapped[str] = mapped_column(String(16), default=Role.employee)
    # Approval power is an explicit grant, never implied by role.
    can_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    # Delegated capabilities for Assistants: {"assign": bool, "set_priority": bool}
    delegations: Mapped[dict] = mapped_column(JSON, default=dict)
    # Companies an Admin/Assistant may operate on (codes). Employees: own company only.
    company_access: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Personal details used to fill forms (travel, IDs, documents). Name parts are optional for
    # directory people (their `name` is authoritative) and required for people added in the app.
    first_name: Mapped[str | None] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    suffix: Mapped[str | None] = mapped_column(String(20))
    gender: Mapped[str | None] = mapped_column(String(20))  # male | female | unspecified
    birth_date: Mapped[date | None] = mapped_column(Date)
    # When only the age is known: the age on the day it was recorded, so it can keep counting up.
    age_years: Mapped[int | None] = mapped_column(Integer)
    age_recorded_on: Mapped[date | None] = mapped_column(Date)
    # directory = from the company directory (One Admin later); added = added by staff in Executive Admin.
    # Added people can be picked on forms but can never sign in or approve.
    source: Mapped[str] = mapped_column(String(16), default="directory", server_default="directory")
    added_by_id: Mapped[int | None] = mapped_column(Integer)
    # Sign-in (production, until One Admin): scrypt hash, never the password itself.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company] = relationship(lazy="joined", foreign_keys=[company_id])
    department: Mapped[Department | None] = relationship(lazy="joined", foreign_keys=[department_id])

    @property
    def age(self) -> int | None:
        today = date.today()
        if self.birth_date:
            b = self.birth_date
            return today.year - b.year - ((today.month, today.day) < (b.month, b.day))
        if self.age_years is not None and self.age_recorded_on:
            r = self.age_recorded_on
            return self.age_years + today.year - r.year - ((today.month, today.day) < (r.month, r.day))
        return self.age_years


# ------------------------------------------------------------------ workflows


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # Request kinds that route through this template.
    kinds: Mapped[list] = mapped_column(JSON, default=list)
    # Processing stages shown after approval (informational, driven by request status).
    processing: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    stages: Mapped[list[WorkflowStage]] = relationship(
        back_populates="template", order_by="WorkflowStage.position", cascade="all, delete-orphan", lazy="selectin"
    )


class WorkflowStage(Base):
    __tablename__ = "workflow_stages"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("workflow_templates.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    # "department_head" resolves from the requester's department; "employee" is a named approver.
    approver_type: Mapped[str] = mapped_column(String(32), default="employee")
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Only use this stage when the request priority is at least this level (None = always).
    min_priority: Mapped[str | None] = mapped_column(String(16))

    template: Mapped[WorkflowTemplate] = relationship(back_populates="stages")
    approver: Mapped[Employee | None] = relationship(lazy="joined")


class ApprovalDelegation(Base):
    __tablename__ = "approval_delegations"
    id: Mapped[int] = mapped_column(primary_key=True)
    delegator_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    delegate_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(400))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    delegator: Mapped[Employee] = relationship(foreign_keys=[delegator_id], lazy="joined")
    delegate: Mapped[Employee] = relationship(foreign_keys=[delegate_id], lazy="joined")


# ------------------------------------------------------------------ requests


class Request(Base):
    __tablename__ = "requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(String(120))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    requester_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    subject: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str | None] = mapped_column(String(300))
    related_asset: Mapped[str | None] = mapped_column(String(300))
    purpose: Mapped[str | None] = mapped_column(Text)
    delivery_location: Mapped[str | None] = mapped_column(String(300))
    requested_priority: Mapped[str] = mapped_column(String(16), default=Priority.normal)
    # Set by Admin (or an Assistant with delegated priority rights); falls back to requested.
    effective_priority: Mapped[str | None] = mapped_column(String(16))
    needed_by: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default=RequestStatus.draft, index=True)
    fulfillment_status: Mapped[str | None] = mapped_column(String(120))
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    workflow_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_templates.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Optimistic concurrency + duplicate-submission guard.
    version: Mapped[int] = mapped_column(Integer, default=1)
    client_token: Mapped[str | None] = mapped_column(String(64), unique=True)

    company: Mapped[Company] = relationship(lazy="joined")
    department: Mapped[Department | None] = relationship(lazy="joined")
    requester: Mapped[Employee] = relationship(foreign_keys=[requester_id], lazy="joined")
    assigned_to: Mapped[Employee | None] = relationship(foreign_keys=[assigned_to_id], lazy="joined")
    items: Mapped[list[RequestItem]] = relationship(
        back_populates="request", order_by="RequestItem.position", cascade="all, delete-orphan", lazy="selectin"
    )
    steps: Mapped[list[ApprovalStep]] = relationship(
        back_populates="request", order_by="ApprovalStep.position", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def priority(self) -> str:
        return self.effective_priority or self.requested_priority


class RequestItem(Base):
    __tablename__ = "request_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    item_name: Mapped[str] = mapped_column(String(300))
    item_category: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(40))
    received_quantity: Mapped[int] = mapped_column(Integer, default=0)

    request: Mapped[Request] = relationship(back_populates="items")


class ApprovalStep(Base):
    """A snapshot of a workflow stage for one request. Config changes never rewrite in-flight routes."""

    __tablename__ = "approval_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String(16), default=StepStatus.waiting)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(String(300))

    request: Mapped[Request] = relationship(back_populates="steps")
    approver: Mapped[Employee | None] = relationship(foreign_keys=[approver_id], lazy="joined")
    decided_by: Mapped[Employee | None] = relationship(foreign_keys=[decided_by_id], lazy="joined")


class RequestEvent(Base):
    """The request timeline: submissions, decisions, comments, clarifications, status changes."""

    __tablename__ = "request_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    type: Mapped[str] = mapped_column(String(40))
    message: Mapped[str | None] = mapped_column(Text)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    # Internal notes are visible to staff only.
    internal: Mapped[bool] = mapped_column(Boolean, default=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    actor: Mapped[Employee | None] = relationship(lazy="joined")


# ------------------------------------------------------------------ shared


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(32))  # "request" | "task"
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    purpose: Mapped[str | None] = mapped_column(String(60))  # e.g. "evidence", "completion", "proof"
    # Proof photos: how it was taken (camera / upload), when and where (if the person allowed location).
    meta: Mapped[dict | None] = mapped_column(JSON)

    uploaded_by: Mapped[Employee] = relationship(lazy="joined")


class AuthSession(Base):
    """A signed-in browser. The cookie holds a random token; only its SHA-256 is stored."""

    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(200))


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # De-duplicates reminders such as "overdue" for the same record and level.
    dedupe_key: Mapped[str | None] = mapped_column(String(120), unique=True)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String(16), default=Priority.normal)
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.open, index=True)
    recurrence: Mapped[str] = mapped_column(String(16), default=Recurrence.none)
    source_module: Mapped[str | None] = mapped_column(String(40))
    source_record_id: Mapped[int | None] = mapped_column(Integer)
    completion_note: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    parent_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))

    company: Mapped[Company] = relationship(lazy="joined")
    assignee: Mapped[Employee | None] = relationship(foreign_keys=[assignee_id], lazy="joined")
    created_by: Mapped[Employee] = relationship(foreign_keys=[created_by_id], lazy="joined")


class SlaPolicy(Base):
    __tablename__ = "sla_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    priority: Mapped[str] = mapped_column(String(16), unique=True)
    response_hours: Mapped[int] = mapped_column(Integer)
    resolution_hours: Mapped[int] = mapped_column(Integer)
    # Hours after the resolution deadline before escalating again (level 2+).
    escalate_every_hours: Mapped[int] = mapped_column(Integer, default=24)
    # Priority-based assignment: default owner once a request is approved.
    default_assignee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    default_assignee: Mapped[Employee | None] = relationship(lazy="joined")


class DocumentSequence(Base):
    __tablename__ = "document_sequences"
    __table_args__ = (UniqueConstraint("doc_type", "year"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(16))
    year: Mapped[int] = mapped_column(Integer)
    last_value: Mapped[int] = mapped_column(Integer, default=0)


class AuditEvent(Base):
    """Append-only. No API updates or deletes these rows."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    entity_ref: Mapped[str | None] = mapped_column(String(60))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    actor: Mapped[Employee | None] = relationship(lazy="joined")


class WebRequest(Base):
    """A request sent through the shared request link (/request) by someone who isn't signed in.

    It waits here until Admin or an Assistant checks who sent it and accepts it (which files the
    real request or requests for that person and starts the usual approval route) or declines it.
    Only what the form asks for is kept. Photos are stored re-encoded, without metadata.
    """

    __tablename__ = "web_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    position: Mapped[str | None] = mapped_column(String(120))
    # The problem report part (optional).
    problem: Mapped[dict | None] = mapped_column(JSON)
    # The items part (optional): {"items": [...], "purpose": str, "needed_by": "YYYY-MM-DD"}.
    supplies: Mapped[dict | None] = mapped_column(JSON)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    # [{"key": storage key, "size": bytes}] re-encoded JPEGs; moved onto the request when accepted.
    photos: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)  # new | accepted | declined
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    request_ids: Mapped[list] = mapped_column(JSON, default=list)
    handled_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decline_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    company: Mapped[Company] = relationship(lazy="joined")
    department: Mapped[Department | None] = relationship(lazy="joined")
    employee: Mapped[Employee | None] = relationship(foreign_keys=[employee_id], lazy="joined")
    handled_by: Mapped[Employee | None] = relationship(foreign_keys=[handled_by_id], lazy="joined")
