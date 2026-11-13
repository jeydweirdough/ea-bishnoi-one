"""Administration: approval chain configuration, priorities & SLA, access grants, audit log."""

import re
from datetime import date, datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from ..core import audit, bad_request, conflict, next_reference, not_found
from ..models import AuditEvent, Company, Department, Employee, Priority, RequestKind, Role, SlaPolicy, WorkflowStage, WorkflowTemplate
from ..security import AdminOnly, Session, Staff
from ..serialize import iso, person
from ..workflow import run_escalations

router = APIRouter(prefix="/api/v1/admin", tags=["administration"])

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


# ------------------------------------------------------------------ workflows


def template_out(t: WorkflowTemplate) -> dict:
    return {
        "id": t.id,
        "key": t.key,
        "name": t.name,
        "description": t.description,
        "kinds": t.kinds,
        "processing": t.processing,
        "active": t.active,
        "updated_at": iso(t.updated_at),
        "stages": [
            {
                "id": s.id,
                "position": s.position,
                "name": s.name,
                "approver_type": s.approver_type,
                "approver": person(s.approver),
                "active": s.active,
                "min_priority": s.min_priority,
            }
            for s in t.stages
        ],
    }


@router.get("/workflows")
async def workflows(principal: Staff, session: Session) -> list[dict]:
    rows = (await session.execute(select(WorkflowTemplate).order_by(WorkflowTemplate.id))).scalars()
    return [template_out(t) for t in rows]


class StageIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    approver_type: str = Field("employee", pattern="^(employee|department_head)$")
    approver_id: int | None = None
    active: bool = True
    min_priority: Priority | None = None


class TemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    kinds: list[RequestKind]
    active: bool = True
    stages: list[StageIn] = Field(..., max_length=12)


@router.put("/workflows/{template_id}")
async def update_workflow(template_id: int, body: TemplateIn, principal: AdminOnly, session: Session) -> dict:
    tpl = await session.get(WorkflowTemplate, template_id)
    if tpl is None:
        raise not_found()
    errors: dict[str, str] = {}
    for i, s in enumerate(body.stages):
        if s.approver_type == "employee":
            if s.approver_id is None:
                errors[f"stages.{i}.approver_id"] = "Choose an approver"
                continue
            emp = await session.get(Employee, s.approver_id)
            if emp is None or not emp.active:
                errors[f"stages.{i}.approver_id"] = "Unknown employee"
            elif not emp.can_approve:
                errors[f"stages.{i}.approver_id"] = f"{emp.name} has no approval grant"
    # A request kind may route through only one active template.
    others = (await session.execute(select(WorkflowTemplate).where(WorkflowTemplate.id != tpl.id, WorkflowTemplate.active.is_(True)))).scalars()
    taken = {k: o.name for o in others for k in (o.kinds or [])}
    for k in body.kinds:
        if body.active and k in taken:
            errors["kinds"] = f"{k.replace('_', ' ')} already routes through “{taken[k]}”"
    if errors:
        raise bad_request({"message": "Some fields need attention", "fields": errors})
    before = template_out(tpl)
    tpl.name = body.name
    tpl.description = body.description
    tpl.kinds = [k.value for k in body.kinds]
    tpl.active = body.active
    tpl.stages.clear()
    await session.flush()
    for i, s in enumerate(body.stages):
        tpl.stages.append(
            WorkflowStage(
                position=i,
                name=s.name.strip(),
                approver_type=s.approver_type,
                approver_id=s.approver_id if s.approver_type == "employee" else None,
                active=s.active,
                min_priority=s.min_priority.value if s.min_priority else None,
            )
        )
    await session.flush()
    await audit(
        session, actor_id=principal.id, action="workflow.update", entity_type="workflow", entity_id=tpl.id, entity_ref=tpl.key,
        data={"before": [s["name"] for s in before["stages"]], "after": [s.name for s in body.stages], "kinds": tpl.kinds},
    )
    await session.commit()
    tpl = (await session.execute(select(WorkflowTemplate).where(WorkflowTemplate.id == template_id).execution_options(populate_existing=True))).scalar_one()
    return template_out(tpl)


# ------------------------------------------------------------------ SLA


def sla_out(p: SlaPolicy) -> dict:
    return {
        "priority": p.priority,
        "response_hours": p.response_hours,
        "resolution_hours": p.resolution_hours,
        "escalate_every_hours": p.escalate_every_hours,
        "default_assignee": person(p.default_assignee),
        "updated_at": iso(p.updated_at),
    }


@router.get("/sla")
async def sla(principal: Staff, session: Session) -> list[dict]:
    order = {p.value: i for i, p in enumerate(Priority)}
    rows = sorted((await session.execute(select(SlaPolicy))).scalars(), key=lambda p: order.get(p.priority, 9))
    return [sla_out(p) for p in rows]


class SlaIn(BaseModel):
    response_hours: int = Field(..., ge=1, le=24 * 60)
    resolution_hours: int = Field(..., ge=1, le=24 * 365)
    escalate_every_hours: int = Field(24, ge=1, le=24 * 30)
    default_assignee_id: int | None = None


@router.put("/sla/{priority}")
async def update_sla(priority: Priority, body: SlaIn, principal: AdminOnly, session: Session) -> dict:
    if body.resolution_hours < body.response_hours:
        raise bad_request({"message": "Resolution target cannot be shorter than the response target", "fields": {"resolution_hours": "Too short"}})
    if body.default_assignee_id is not None:
        emp = await session.get(Employee, body.default_assignee_id)
        if emp is None or emp.role not in (Role.admin, Role.assistant):
            raise bad_request({"message": "Default owner must be an Admin or Assistant", "fields": {"default_assignee_id": "Not staff"}})
    p = (await session.execute(select(SlaPolicy).where(SlaPolicy.priority == priority))).scalar_one_or_none()
    if p is None:
        p = SlaPolicy(priority=priority.value, response_hours=1, resolution_hours=1)
        session.add(p)
    before = {"response": p.response_hours, "resolution": p.resolution_hours}
    p.response_hours = body.response_hours
    p.resolution_hours = body.resolution_hours
    p.escalate_every_hours = body.escalate_every_hours
    p.default_assignee_id = body.default_assignee_id
    await audit(
        session, actor_id=principal.id, action="sla.update", entity_type="sla", entity_ref=priority.value,
        data={"before": before, "after": body.model_dump()},
    )
    await session.commit()
    p = (await session.execute(select(SlaPolicy).where(SlaPolicy.priority == priority).execution_options(populate_existing=True))).scalar_one()
    return sla_out(p)


@router.post("/escalations/run")
async def escalations(principal: AdminOnly, session: Session) -> dict:
    await audit(session, actor_id=principal.id, action="sla.run_escalations", entity_type="sla")
    return await run_escalations(session)


# ------------------------------------------------------------------ access grants


def grant_out(e: Employee) -> dict:
    from ..auth import aware, utcnow

    return {
        **person(e),
        "role": e.role,
        "company": e.company.code,
        "company_id": e.company_id,
        "department_id": e.department_id,
        "email": e.email,
        "active": e.active,
        "can_approve": e.can_approve,
        "delegations": e.delegations or {},
        "company_access": e.company_access or [],
        "sign_in": {
            "has_password": bool(e.password_hash),
            "must_change_password": bool(e.must_change_password),
            "locked": bool(aware(e.locked_until) and aware(e.locked_until) > utcnow()),
            "last_login_at": iso(e.last_login_at),
        },
    }


# ------------------------------------------------------------------ accounts (email + password sign-in)


class AccountIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str = Field(min_length=5, max_length=200)
    designation: str | None = Field(None, max_length=200)
    role: Literal["admin", "assistant", "employee"] = "employee"
    company_id: int
    department_id: int | None = None
    employee_no: str | None = Field(None, max_length=32)
    active: bool = True


def _clean_email(raw: str) -> str:
    email = raw.strip().lower()
    if not EMAIL.fullmatch(email):
        raise bad_request({"message": "Enter a valid email address", "fields": {"email": "Enter a valid email address"}})
    return email


async def _email_taken(session, email: str, but: int | None = None) -> bool:
    stmt = select(Employee.id).where(func.lower(Employee.email) == email)
    if but:
        stmt = stmt.where(Employee.id != but)
    return (await session.execute(stmt)).first() is not None


async def _check_org(session, company_id: int, department_id: int | None) -> None:
    if await session.get(Company, company_id) is None:
        raise bad_request({"message": "Choose a company", "fields": {"company_id": "Choose a company"}})
    if department_id is not None:
        d = await session.get(Department, department_id)
        if d is None or d.company_id != company_id:
            raise bad_request({"message": "That department is not in this company", "fields": {"department_id": "Not in this company"}})


@router.post("/users", status_code=201)
async def create_account(body: AccountIn, principal: AdminOnly, session: Session) -> dict:
    """Add a person who can sign in. Returns a one-time temporary password to hand over."""
    from ..auth import hash_password, temporary_password

    email = _clean_email(body.email)
    if await _email_taken(session, email):
        raise conflict("Someone already uses this email")
    await _check_org(session, body.company_id, body.department_id)
    no = (body.employee_no or "").strip().upper() or None
    if no and (await session.execute(select(Employee.id).where(Employee.employee_no == no))).first():
        raise conflict("That employee number is already used")
    if no is None:
        no = await next_reference(session, "USR")
    company = await session.get(Company, body.company_id)
    temp = temporary_password()
    emp = Employee(
        employee_no=no, name=body.name.strip(), email=email, designation=(body.designation or "").strip() or None,
        company_id=body.company_id, department_id=body.department_id, role=body.role, active=body.active,
        company_access=[company.code] if body.role in ("admin", "assistant") else [],
        password_hash=hash_password(temp), must_change_password=True,
    )
    session.add(emp)
    await session.flush()
    await audit(session, actor_id=principal.id, action="account.create", entity_type="employee", entity_id=emp.id, entity_ref=emp.employee_no, data={"email": email, "role": body.role})
    await session.commit()
    await session.refresh(emp)
    return {**grant_out(emp), "temporary_password": temp}


class AccountPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    email: str | None = Field(None, min_length=5, max_length=200)
    designation: str | None = Field(None, max_length=200)
    role: Literal["admin", "assistant", "employee"] | None = None
    company_id: int | None = None
    department_id: int | None = None
    active: bool | None = None


@router.patch("/users/{employee_id}")
async def update_account(employee_id: int, body: AccountPatch, principal: AdminOnly, session: Session) -> dict:
    from ..auth import end_sessions

    emp = await session.get(Employee, employee_id)
    if emp is None or emp.source == "added":
        raise not_found()
    data = body.model_dump(exclude_unset=True)
    if emp.id == principal.id and (data.get("active") is False or data.get("role", "admin") != "admin"):
        raise bad_request({"message": "You can't deactivate yourself or remove your own Admin role"})
    if "email" in data:
        data["email"] = _clean_email(data["email"])
        if await _email_taken(session, data["email"], but=emp.id):
            raise conflict("Someone already uses this email")
    if "company_id" in data or "department_id" in data:
        await _check_org(session, data.get("company_id", emp.company_id), data.get("department_id", emp.department_id))
    before = {k: getattr(emp, k) for k in data}
    for k, v in data.items():
        setattr(emp, k, v.strip() if isinstance(v, str) else v)
    if data.get("role") == "employee":
        emp.delegations, emp.company_access = {}, []
    if data.get("active") is False or "role" in data:
        await end_sessions(session, emp.id)  # takes effect immediately
    await audit(session, actor_id=principal.id, action="account.update", entity_type="employee", entity_id=emp.id, entity_ref=emp.employee_no, data={"before": before, "after": data})
    await session.commit()
    await session.refresh(emp)
    return grant_out(emp)


@router.post("/users/{employee_id}/temporary-password")
async def reset_password(employee_id: int, principal: AdminOnly, session: Session) -> dict:
    """New one-time password (shown once). Unlocks the account and signs it out everywhere."""
    from ..auth import end_sessions, hash_password, temporary_password

    emp = await session.get(Employee, employee_id)
    if emp is None or emp.source == "added":
        raise not_found()
    if not emp.email:
        raise bad_request({"message": "Add an email address first; it is the sign-in name"})
    temp = temporary_password()
    emp.password_hash = hash_password(temp)
    emp.must_change_password = True
    emp.failed_logins = 0
    emp.locked_until = None
    await end_sessions(session, emp.id)
    await audit(session, actor_id=principal.id, action="account.temporary_password", entity_type="employee", entity_id=emp.id, entity_ref=emp.employee_no)
    await session.commit()
    await session.refresh(emp)
    return {**grant_out(emp), "temporary_password": temp}


# ------------------------------------------------------------------ departments (heads approve "Department Head" stages)


def department_out(d: Department, head: Employee | None) -> dict:
    return {"id": d.id, "code": d.code, "name": d.name, "company": {"id": d.company.id, "code": d.company.code}, "head": person(head)}


@router.get("/departments")
async def list_departments(principal: AdminOnly, session: Session) -> list[dict]:
    rows = (await session.execute(select(Department).order_by(Department.company_id, Department.name))).scalars().all()
    heads = {e.id: e for e in (await session.execute(select(Employee).where(Employee.id.in_([d.head_id for d in rows if d.head_id] or [0])))).scalars()}
    return [department_out(d, heads.get(d.head_id)) for d in rows]


class DepartmentIn(BaseModel):
    company_id: int
    name: str = Field(min_length=2, max_length=120)
    code: str | None = Field(None, max_length=16)


@router.post("/departments", status_code=201)
async def create_department(body: DepartmentIn, principal: AdminOnly, session: Session) -> dict:
    if await session.get(Company, body.company_id) is None:
        raise bad_request({"message": "Choose a company", "fields": {"company_id": "Choose a company"}})
    name = body.name.strip()
    code = (body.code or "".join(w[0] for w in name.split() if w[:1].isalnum())[:6] or name[:6]).strip().upper()
    clash = (await session.execute(select(Department.id).where(Department.company_id == body.company_id, or_(func.lower(Department.name) == name.lower(), Department.code == code)))).first()
    if clash:
        raise conflict("This company already has a department with that name or code")
    d = Department(company_id=body.company_id, name=name, code=code)
    session.add(d)
    await session.flush()
    await audit(session, actor_id=principal.id, action="department.create", entity_type="department", entity_id=d.id, entity_ref=code, data={"name": name})
    await session.commit()
    await session.refresh(d)
    return department_out(d, None)


class DepartmentPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    head_id: int | None = None


@router.patch("/departments/{department_id}")
async def update_department(department_id: int, body: DepartmentPatch, principal: AdminOnly, session: Session) -> dict:
    d = await session.get(Department, department_id)
    if d is None:
        raise not_found()
    data = body.model_dump(exclude_unset=True)
    head = None
    if "head_id" in data and data["head_id"] is not None:
        head = await session.get(Employee, data["head_id"])
        if head is None or not head.active or head.source == "added":
            raise bad_request({"message": "Choose an active person who can sign in", "fields": {"head_id": "Not available"}})
    before = {"name": d.name, "head_id": d.head_id}
    if "name" in data and data["name"]:
        d.name = data["name"].strip()
    if "head_id" in data:
        d.head_id = data["head_id"]
        # A head approves the "Department Head" stage, so they need approval duties.
        if head is not None and not head.can_approve:
            head.can_approve = True
    await audit(session, actor_id=principal.id, action="department.update", entity_type="department", entity_id=d.id, entity_ref=d.code, data={"before": before, "after": data})
    await session.commit()
    await session.refresh(d)
    if d.head_id and head is None:
        head = await session.get(Employee, d.head_id)
    return department_out(d, head)


@router.get("/companies")
async def companies(principal: AdminOnly, session: Session) -> list[dict]:
    rows = (await session.execute(select(Company).order_by(Company.code))).scalars()
    return [{"id": c.id, "code": c.code, "name": c.name} for c in rows]


@router.get("/users")
async def users(principal: AdminOnly, session: Session, q: str | None = None) -> list[dict]:
    stmt = select(Employee).where(Employee.source != "added")  # access grants are for directory staff only
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Employee.name.ilike(like), Employee.employee_no.ilike(like), Employee.email.ilike(like)))
    rows = (await session.execute(stmt.order_by(Employee.active.desc(), Employee.role, Employee.name))).scalars()
    return [grant_out(e) for e in rows]


class GrantIn(BaseModel):
    can_approve: bool
    assign: bool = False
    set_priority: bool = False
    travel_documents: bool = False
    banking: bool = False
    inventory_adjust: bool = False
    company_access: list[str] = Field(default_factory=list)


@router.put("/users/{employee_id}/grants")
async def update_grants(employee_id: int, body: GrantIn, principal: AdminOnly, session: Session) -> dict:
    emp = await session.get(Employee, employee_id)
    if emp is None:
        raise not_found()
    before = grant_out(emp)
    emp.can_approve = body.can_approve
    emp.delegations = {"assign": body.assign, "set_priority": body.set_priority, "travel_documents": body.travel_documents, "banking": body.banking, "inventory_adjust": body.inventory_adjust} if emp.role == Role.assistant else {}
    emp.company_access = body.company_access if emp.role in (Role.admin, Role.assistant) else []
    await audit(
        session, actor_id=principal.id, action="access.update_grants", entity_type="employee", entity_id=emp.id,
        entity_ref=emp.employee_no, data={"before": {k: before[k] for k in ("can_approve", "delegations", "company_access")}, "after": body.model_dump()},
    )
    await session.commit()
    return grant_out(emp)


# ------------------------------------------------------------------ audit


@router.get("/audit")
async def audit_log(
    principal: AdminOnly,
    session: Session,
    q: str | None = Query(None, max_length=100),
    entity_type: str | None = None,
    action: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    stmt = select(AuditEvent).where(or_(AuditEvent.company_id.is_(None), AuditEvent.company_id.in_(principal.company_ids)))
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditEvent.action.startswith(action))
    if q:
        stmt = stmt.where(or_(AuditEvent.entity_ref.ilike(f"%{q}%"), AuditEvent.action.ilike(f"%{q}%")))
    if date_from:
        stmt = stmt.where(AuditEvent.at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        stmt = stmt.where(AuditEvent.at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(AuditEvent.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars()
    return {
        "items": [
            {
                "id": a.id,
                "at": iso(a.at),
                "actor": person(a.actor),
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "entity_ref": a.entity_ref,
                "data": a.data,
            }
            for a in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
