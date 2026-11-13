"""Signed-in user, development sign-in list, directory lookup, notifications."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from ..config import get_settings
from ..core import audit, bad_request, conflict, next_reference, not_found, now
from ..models import ApprovalStep, Employee, Notification, Role, StepStatus
from ..ops_common import company_for
from ..security import CurrentPrincipal, Session, Staff
from ..serialize import notification_out, person
from ..workflow import approver_scope_ids

router = APIRouter(prefix="/api/v1", tags=["session"])

OPERATIONS_GROUPS = ["dashboard", "requests", "assets", "fleet", "compliance", "travel", "contracts", "banking", "administration"]


@router.get("/me")
async def me(principal: CurrentPrincipal, session: Session) -> dict:
    e = principal.employee
    unread = (
        await session.execute(select(func.count()).where(Notification.recipient_id == e.id, Notification.read_at.is_(None)))
    ).scalar_one()
    scope = await approver_scope_ids(session, principal)
    inbox = 0
    if scope:
        inbox = (
            await session.execute(
                select(func.count()).where(ApprovalStep.status == StepStatus.pending, ApprovalStep.approver_id.in_(scope))
            )
        ).scalar_one()
    return {
        "employee": {**person(e), "company": {"id": e.company.id, "code": e.company.code, "name": e.company.name}},
        "role": principal.role,
        "approver": principal.approver,
        "email": e.email,
        "must_change_password": bool(e.must_change_password),
        "acts_for": sorted(scope - {e.id}),
        "can": {
            "assign": principal.can("assign"),
            "set_priority": principal.can("set_priority"),
            "configure": principal.is_admin,
        },
        "unread_notifications": unread,
        "inbox_count": inbox,
        "navigation": {
            "operations": OPERATIONS_GROUPS if principal.is_staff else [],
            "self_service": True,
            "approval_inbox": bool(scope),
        },
    }


@router.get("/dev/users")
async def dev_users(session: Session) -> list[dict]:
    """Development sign-in list. Disabled outside development."""
    if not get_settings().is_dev:
        raise not_found()
    rows = (await session.execute(select(Employee).where(Employee.active.is_(True), Employee.source != "added").order_by(Employee.role, Employee.name))).scalars()
    return [
        {**person(e), "role": e.role, "approver": e.can_approve, "company": e.company.code}
        for e in rows
    ]


@router.get("/directory")
async def directory(
    principal: CurrentPrincipal,
    session: Session,
    q: str | None = Query(None, max_length=100),
    role: list[str] = Query(default_factory=list),
    approvers: bool = False,
    limit: int = Query(20, le=50),
    include: int | None = None,
) -> list[dict]:
    """Minimal people lookup (name, designation, department) for assignment and delegation pickers."""
    stmt = select(Employee).where(Employee.active.is_(True))
    if not principal.is_admin:
        stmt = stmt.where(Employee.company_id.in_(principal.company_ids))
    if role:
        stmt = stmt.where(Employee.role.in_(role))
    if approvers:
        stmt = stmt.where(Employee.can_approve.is_(True))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Employee.name.ilike(like), Employee.employee_no.ilike(like), Employee.designation.ilike(like)))
    rows = list((await session.execute(stmt.order_by(Employee.name).limit(limit))).scalars())
    if include and all(e.id != include for e in rows):  # keep the selected person visible beyond the first page
        extra = (await session.execute(stmt.where(Employee.id == include))).scalar_one_or_none()
        if extra:
            rows.append(extra)
    return [directory_out(e) for e in rows]


def directory_out(e: Employee) -> dict:
    return {**person(e), "role": e.role, "approver": e.can_approve, "gender": e.gender, "age": e.age, "added": e.source == "added", "company": e.company.code}


SUFFIXES = ["Jr.", "Sr.", "II", "III", "IV", "V"]


def full_name(first: str, middle: str | None, last: str, suffix: str | None) -> str:
    return " ".join(x for x in (first.strip(), (middle or "").strip(), last.strip(), (suffix or "").strip()) if x)


class PersonIn(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: str | None = Field(None, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    suffix: Literal["Jr.", "Sr.", "II", "III", "IV", "V"] | None = None
    gender: Literal["male", "female", "unspecified"] | None = None
    birth_date: date | None = None
    age: int | None = Field(None, ge=0, le=120)
    designation: str | None = Field(None, max_length=200)
    company_id: int | None = None
    allow_duplicate: bool = False


@router.post("/directory/people", status_code=201)
async def add_person(body: PersonIn, principal: Staff, session: Session) -> dict:
    """Add someone who is not in the company directory yet (guest, new hire, consultant, family member).
    They can be picked on forms; they can never sign in or approve."""
    if body.birth_date and (body.birth_date > date.today() or body.birth_date.year < 1900):
        raise bad_request({"message": "Check the date of birth", "fields": {"birth_date": "Cannot be in the future or before 1900"}})
    if not body.first_name.strip() or not body.last_name.strip():
        raise bad_request({"message": "First and last name are required", "fields": {"first_name": "Required"}})
    cid = await company_for(session, principal, body.company_id)
    name = full_name(body.first_name, body.middle_name, body.last_name, body.suffix)
    if not body.allow_duplicate:
        same = (await session.execute(select(Employee).where(Employee.active.is_(True), func.lower(Employee.name) == name.lower(), Employee.company_id.in_(principal.company_ids)))).scalars().first()
        if same:
            raise conflict({"message": f"{same.name} is already in the list", "fields": {"first_name": "Already in the list"}, "existing_id": same.id})
    e = Employee(
        employee_no=await next_reference(session, "PPL"), name=name, designation=body.designation, company_id=cid, role="employee",
        can_approve=False, delegations={}, company_access=[], active=True, source="added", added_by_id=principal.id,
        first_name=body.first_name.strip(), middle_name=(body.middle_name or "").strip() or None, last_name=body.last_name.strip(), suffix=body.suffix,
        gender=body.gender, birth_date=body.birth_date,
        age_years=None if body.birth_date else body.age, age_recorded_on=None if body.birth_date or body.age is None else date.today(),
    )
    session.add(e)
    await session.flush()
    await audit(session, actor_id=principal.id, action="person.add", entity_type="employee", entity_id=e.id, entity_ref=e.employee_no, company_id=cid, data={"name": name})
    await session.commit()
    await session.refresh(e)
    return directory_out(e)


@router.get("/directory/people/{person_id}")
async def person_details(person_id: int, principal: Staff, session: Session) -> dict:
    """Details used to fill forms: name parts, gender and age."""
    e = await session.get(Employee, person_id)
    if e is None or e.company_id not in principal.company_ids:
        raise not_found()
    parts = e.name.split()
    return {
        **directory_out(e),
        "first_name": e.first_name or (parts[0] if parts else None),
        "middle_name": e.middle_name,
        "last_name": e.last_name or (parts[-1] if len(parts) > 1 else None),
        "suffix": e.suffix,
        "birth_date": e.birth_date.isoformat() if e.birth_date else None,
    }


@router.get("/directory/departments")
async def departments(principal: CurrentPrincipal, session: Session) -> list[dict]:
    from ..models import Department

    rows = (await session.execute(select(Department).where(Department.company_id.in_(principal.company_ids)).order_by(Department.name))).scalars()
    return [{"id": d.id, "name": d.name, "code": d.code, "company": d.company.code} for d in rows]


# ------------------------------------------------------------------ notifications


@router.get("/notifications", tags=["notifications"])
async def notifications(
    principal: CurrentPrincipal,
    session: Session,
    unread: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
) -> dict:
    stmt = select(Notification).where(Notification.recipient_id == principal.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).offset((page - 1) * page_size).limit(page_size))
    ).scalars()
    return {"items": [notification_out(n) for n in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/notifications/{notification_id}/read", tags=["notifications"])
async def mark_read(notification_id: int, principal: CurrentPrincipal, session: Session) -> dict:
    n = await session.get(Notification, notification_id)
    if n is None or n.recipient_id != principal.id:
        raise not_found()
    if n.read_at is None:
        n.read_at = now()
        await session.commit()
    return notification_out(n)


@router.post("/notifications/read-all", tags=["notifications"])
async def mark_all_read(principal: CurrentPrincipal, session: Session) -> dict:
    rows = (
        await session.execute(select(Notification).where(Notification.recipient_id == principal.id, Notification.read_at.is_(None)))
    ).scalars()
    t = now()
    n = 0
    for row in rows:
        row.read_at = t
        n += 1
    await session.commit()
    return {"updated": n}


__all__ = ["router", "Role"]
