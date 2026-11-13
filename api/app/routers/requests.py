"""Requests & concerns: employee self-service and staff work queues share one endpoint set."""

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import aliased

from ..core import admin_ids, audit, bad_request, conflict, forbidden, not_found, notify, now
from ..models import (
    Attachment,
    Employee,
    Priority,
    Request,
    RequestEvent,
    RequestItem,
    RequestKind,
    RequestStatus as S,
    Role,
    StepStatus,
)
from ..security import CurrentPrincipal, Principal, Session
from ..serialize import request_detail, request_summary
from ..workflow import (
    IN_APPROVAL,
    OPEN,
    TERMINAL,
    allowed_actions,
    apply_sla,
    can_view,
    decide,
    employee_or_404,
    event,
    is_operator,
    link_for,
    move,
    scope_filter,
    submit,
)

router = APIRouter(prefix="/api/v1", tags=["requests"])

CONCERN_CATEGORIES = [
    "Facilities",
    "Damaged equipment",
    "Repairs",
    "Maintenance",
    "IT & equipment",
    "Utilities",
    "Safety & security",
    "Department concern",
    "Other",
]
SUPPLY_CATEGORIES = ["Office supplies", "Utility supplies", "Equipment", "Furniture", "IT peripherals", "Other"]
UNITS = ["pc", "box", "pack", "ream", "set", "unit", "roll", "bottle", "gallon", "kg", "pair", "lot"]
# Concern categories that belong in the Repairs & Maintenance queue.
REPAIR_CATEGORIES = {"Damaged equipment", "Repairs", "Maintenance"}


class ItemIn(BaseModel):
    item_name: str = Field("", max_length=300)
    item_category: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=2000)
    brand: str | None = Field(None, max_length=120)
    model: str | None = Field(None, max_length=120)
    quantity: int = Field(1, ge=0, le=100000)
    unit: str = Field("pc", max_length=40)


class RequestIn(BaseModel):
    kind: RequestKind
    category: str | None = Field(None, max_length=120)
    subject: str = Field("", max_length=300)
    description: str = Field("", max_length=10000)
    location: str | None = Field(None, max_length=300)
    related_asset: str | None = Field(None, max_length=300)
    purpose: str | None = Field(None, max_length=4000)
    delivery_location: str | None = Field(None, max_length=300)
    requested_priority: Priority = Priority.normal
    needed_by: date | None = None
    items: list[ItemIn] = Field(default_factory=list, max_length=100)
    submit: bool = False
    client_token: str | None = Field(None, max_length=64)

    @field_validator("subject", "description")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


class RequestPatch(RequestIn):
    version: int


class ActionIn(BaseModel):
    message: str | None = Field(None, max_length=4000)
    assignee_id: int | None = None
    priority: Priority | None = None
    step_id: int | None = None
    approver_id: int | None = None


class CommentIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    internal: bool = False


# ------------------------------------------------------------------ helpers


async def load(session, request_id: int) -> Request:
    req = (
        await session.execute(select(Request).where(Request.id == request_id).execution_options(populate_existing=True))
    ).scalar_one_or_none()
    if req is None:
        raise not_found()
    return req


async def load_visible(session, principal: Principal, request_id: int) -> Request:
    req = await load(session, request_id)
    if not await can_view(session, principal, req):
        raise not_found()
    return req


async def detail(session, principal: Principal, req: Request) -> dict:
    events = (
        (await session.execute(select(RequestEvent).where(RequestEvent.request_id == req.id).order_by(RequestEvent.at, RequestEvent.id)))
        .scalars()
        .all()
    )
    atts = (
        (
            await session.execute(
                select(Attachment).where(Attachment.owner_type == "request", Attachment.owner_id == req.id).order_by(Attachment.id)
            )
        )
        .scalars()
        .all()
    )
    head = await session.get(Employee, req.department.head_id) if req.department and req.department.head_id else None
    staff = principal.is_staff and req.company_id in principal.company_ids
    return request_detail(req, list(events), list(atts), await allowed_actions(session, principal, req), staff, head)


def apply_fields(req: Request, body: RequestIn) -> None:
    kind = body.kind
    if kind == RequestKind.concern and body.category in REPAIR_CATEGORIES:
        kind = RequestKind.repair
    req.kind = kind
    req.category = body.category
    req.subject = body.subject
    req.description = body.description
    req.location = body.location
    req.related_asset = body.related_asset
    req.purpose = body.purpose
    req.delivery_location = body.delivery_location
    req.requested_priority = body.requested_priority
    req.needed_by = body.needed_by
    req.items.clear()
    for i, it in enumerate(body.items):
        req.items.append(RequestItem(position=i, **it.model_dump()))


# ------------------------------------------------------------------ options


@router.get("/requests/options")
async def options(principal: CurrentPrincipal, session: Session) -> dict:
    e = principal.employee
    head = await session.get(Employee, e.department.head_id) if e.department and e.department.head_id else None
    return {
        "concern_categories": CONCERN_CATEGORIES,
        "supply_categories": SUPPLY_CATEGORIES,
        "units": UNITS,
        "priorities": [p.value for p in Priority],
        "kinds": [k.value for k in RequestKind],
        "statuses": [s.value for s in S],
        "requester": {
            "employee_no": e.employee_no,
            "name": e.name,
            "company": e.company.name,
            "department": e.department.name if e.department else None,
            "department_head": head.name if head else None,
        },
    }


# ------------------------------------------------------------------ create / list


@router.post("/requests", status_code=201)
async def create_request(body: RequestIn, principal: CurrentPrincipal, session: Session) -> dict:
    if body.client_token:
        existing = (
            await session.execute(select(Request).where(Request.client_token == body.client_token))
        ).scalar_one_or_none()
        if existing:
            if existing.requester_id != principal.id:
                raise conflict("Duplicate submission token")
            return await detail(session, principal, existing)  # idempotent retry
    if not body.subject and not body.description and not body.items:
        raise bad_request({"message": "Add a subject before saving", "fields": {"subject": "Required"}})
    from ..core import next_reference

    e = principal.employee
    req = Request(
        reference=await next_reference(session, "REQ"),
        company_id=e.company_id,
        department_id=e.department_id,
        requester_id=e.id,
        status=S.draft,
        client_token=body.client_token,
    )
    session.add(req)
    apply_fields(req, body)
    await session.flush()
    await event(session, req, principal, "created", "Draft saved")
    await audit(
        session, actor_id=principal.id, action="request.create", entity_type="request", entity_id=req.id,
        entity_ref=req.reference, company_id=req.company_id, data={"kind": req.kind},
    )
    await session.flush()
    req = await load(session, req.id)
    if body.submit:
        await submit(session, principal, req)
    await session.commit()
    return await detail(session, principal, await load(session, req.id))


@router.get("/requests")
async def list_requests(
    principal: CurrentPrincipal,
    session: Session,
    scope: Literal["mine", "all", "assigned"] = "mine",
    status: list[str] = Query(default_factory=list),
    group: Literal["open", "approval", "processing", "done", "attention"] | None = None,
    kind: list[str] = Query(default_factory=list),
    priority: list[str] = Query(default_factory=list),
    sla: Literal["overdue", "due_soon"] | None = None,
    assigned: Literal["me", "unassigned"] | None = None,
    company: str | None = None,
    q: str | None = Query(None, max_length=200),
    sort: Literal["newest", "oldest", "due", "priority", "updated"] = "newest",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    stmt = select(Request)
    if scope == "mine":
        stmt = stmt.where(Request.requester_id == principal.id)
    else:
        if not principal.is_staff:
            raise forbidden("Only Admin and Assistant users can view operational queues")
        stmt = stmt.where(scope_filter(principal), Request.status != S.draft)
        if scope == "assigned":
            stmt = stmt.where(Request.assigned_to_id == principal.id)
    if status:
        stmt = stmt.where(Request.status.in_(status))
    groups = {
        "open": OPEN,
        "approval": IN_APPROVAL,
        "processing": {S.approved, S.in_progress, S.awaiting_finance, S.fulfilled},
        "done": TERMINAL | {S.fulfilled},
        "attention": {S.returned, S.fulfilled},
    }
    if group:
        stmt = stmt.where(Request.status.in_(list(groups[group])))
    if kind:
        stmt = stmt.where(Request.kind.in_(kind))
    eff = func.coalesce(Request.effective_priority, Request.requested_priority)
    if priority:
        stmt = stmt.where(eff.in_(priority))
    t = now()
    if sla == "overdue":
        stmt = stmt.where(Request.status.in_(list(OPEN)), Request.resolution_due_at < t)
    elif sla == "due_soon":
        stmt = stmt.where(Request.status.in_(list(OPEN)), Request.resolution_due_at >= t, Request.resolution_due_at < t + timedelta(hours=24))
    if assigned == "me":
        stmt = stmt.where(Request.assigned_to_id == principal.id)
    elif assigned == "unassigned":
        stmt = stmt.where(Request.assigned_to_id.is_(None))
    if company:
        from ..models import Company

        stmt = stmt.join(Company, Company.id == Request.company_id).where(Company.code == company)
    if q:
        req_emp = aliased(Employee)
        like = f"%{q.strip()}%"
        stmt = stmt.join(req_emp, req_emp.id == Request.requester_id).where(
            or_(Request.reference.ilike(like), Request.subject.ilike(like), req_emp.name.ilike(like), Request.category.ilike(like))
        )
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rank = case({"critical": 0, "high": 1, "normal": 2, "low": 3}, value=eff, else_=2)
    order = {
        "newest": [Request.created_at.desc(), Request.id.desc()],
        "oldest": [Request.created_at.asc(), Request.id.asc()],
        "updated": [Request.updated_at.desc()],
        "due": [Request.resolution_due_at.is_(None), Request.resolution_due_at.asc()],
        "priority": [rank, Request.created_at.asc()],
    }[sort]
    rows = (await session.execute(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [request_summary(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/requests/stats")
async def stats(principal: CurrentPrincipal, session: Session, scope: Literal["mine", "ops"] = "mine") -> dict:
    if scope == "mine":
        base = Request.requester_id == principal.id
    else:
        if not principal.is_staff:
            raise forbidden()
        base = scope_filter(principal) & (Request.status != S.draft)
    rows = (await session.execute(select(Request.status, func.count()).where(base).group_by(Request.status))).all()
    by = {s: n for s, n in rows}
    t = now()
    overdue = (
        await session.execute(
            select(func.count()).where(base, Request.status.in_(list(OPEN)), Request.resolution_due_at < t)
        )
    ).scalar_one()
    eff = func.coalesce(Request.effective_priority, Request.requested_priority)
    priority_open = (
        await session.execute(select(func.count()).where(base, Request.status.in_(list(OPEN)), eff.in_(["high", "critical"])))
    ).scalar_one()
    unassigned = 0
    if scope == "ops":
        unassigned = (
            await session.execute(
                select(func.count()).where(
                    base, Request.status.in_([S.approved, S.in_progress, S.awaiting_finance]), Request.assigned_to_id.is_(None)
                )
            )
        ).scalar_one()
    return {
        "by_status": by,
        "total": sum(by.values()),
        "drafts": by.get(S.draft, 0),
        "in_approval": sum(by.get(s, 0) for s in IN_APPROVAL),
        "needs_you": by.get(S.returned, 0) + by.get(S.fulfilled, 0) if scope == "mine" else None,
        "in_progress": sum(by.get(s, 0) for s in (S.approved, S.in_progress, S.awaiting_finance)),
        "completed": by.get(S.fulfilled, 0) + by.get(S.closed, 0),
        "open": sum(by.get(s, 0) for s in OPEN),
        "overdue": overdue,
        "priority_open": priority_open,
        "unassigned": unassigned,
    }


# ------------------------------------------------------------------ one request


@router.get("/requests/{request_id}")
async def get_request(request_id: int, principal: CurrentPrincipal, session: Session) -> dict:
    req = await load_visible(session, principal, request_id)
    return await detail(session, principal, req)


@router.patch("/requests/{request_id}")
async def update_request(request_id: int, body: RequestPatch, principal: CurrentPrincipal, session: Session) -> dict:
    req = await load_visible(session, principal, request_id)
    if req.requester_id != principal.id:
        raise forbidden("Only the requester can edit this request")
    if req.status not in (S.draft, S.returned):
        raise conflict("Only drafts and returned requests can be edited")
    if body.version != req.version:
        raise conflict("This request changed since you opened it. Reload to see the latest version.")
    if req.status == S.returned and body.kind != req.kind and not (body.kind == RequestKind.concern and req.kind == RequestKind.repair):
        raise bad_request("The request type cannot change after submission")
    apply_fields(req, body)
    req.version += 1
    await event(session, req, principal, "edited", "Details updated")
    await audit(
        session, actor_id=principal.id, action="request.update", entity_type="request", entity_id=req.id,
        entity_ref=req.reference, company_id=req.company_id,
    )
    await session.flush()
    req = await load(session, req.id)
    if body.submit and req.status == S.draft:
        await submit(session, principal, req)
    await session.commit()
    return await detail(session, principal, await load(session, req.id))


@router.delete("/requests/{request_id}", status_code=204)
async def delete_draft(request_id: int, principal: CurrentPrincipal, session: Session) -> None:
    req = await load_visible(session, principal, request_id)
    if req.requester_id != principal.id or req.status != S.draft:
        raise conflict("Only your own drafts can be deleted")
    await audit(
        session, actor_id=principal.id, action="request.delete_draft", entity_type="request", entity_id=req.id,
        entity_ref=req.reference, company_id=req.company_id,
    )
    await session.delete(req)
    await session.commit()


@router.post("/requests/{request_id}/actions/{action}")
async def act(request_id: int, action: str, body: ActionIn, principal: CurrentPrincipal, session: Session) -> dict:
    req = await load_visible(session, principal, request_id)
    allowed = await allowed_actions(session, principal, req)
    if action not in allowed:
        if req.status in TERMINAL:
            raise conflict("This request is already closed")
        raise forbidden("This action is not available to you for this request")
    msg = (body.message or "").strip() or None

    if action == "submit":
        await submit(session, principal, req)
    elif action == "resubmit":
        await submit(session, principal, req, resubmit_message=msg)
    elif action == "withdraw":
        await move(session, req, principal, S.cancelled, "withdrawn", msg)
        for s in req.steps:
            if s.status in (StepStatus.pending, StepStatus.waiting, StepStatus.returned):
                s.status = StepStatus.skipped
                s.note = "Request withdrawn"
    elif action == "confirm":
        await move(session, req, principal, S.closed, "confirmed", msg)
        await notify(
            session, await admin_ids(session, req.company_id) | ({req.assigned_to_id} if req.assigned_to_id else set()),
            kind="fulfillment_confirmation", title=f"Confirmed by requester: {req.reference}", body=msg, link=link_for(req),
        )
    elif action in ("approve", "reject", "return"):
        await decide(session, principal, req, action, msg)
    elif action == "assign":
        if body.assignee_id is None:
            raise bad_request({"message": "Choose who should own this request", "fields": {"assignee_id": "Required"}})
        emp = await employee_or_404(session, body.assignee_id)
        if emp.role not in (Role.admin, Role.assistant):
            raise bad_request({"message": "Requests can only be assigned to Admin or Assistant users", "fields": {"assignee_id": "Not staff"}})
        if emp.company_id != req.company_id and req.company.code not in (emp.company_access or []):
            raise bad_request({"message": "That user has no access to this company", "fields": {"assignee_id": "Wrong company"}})
        prev = req.assigned_to.name if req.assigned_to else None
        req.assigned_to_id = emp.id
        req.version += 1
        if req.first_response_at is None:
            req.first_response_at = now()
        await event(session, req, principal, "assigned", f"Owner: {emp.name}" + (f" (was {prev})" if prev else ""))
        await audit(
            session, actor_id=principal.id, action="request.assign", entity_type="request", entity_id=req.id,
            entity_ref=req.reference, company_id=req.company_id, data={"assignee": emp.employee_no, "previous": prev},
        )
        await notify(
            session, {emp.id}, kind="task_assignment", title=f"Assigned to you: {req.reference}", body=req.subject,
            link=link_for(req), skip=principal.id,
        )
    elif action == "set_priority":
        if body.priority is None:
            raise bad_request({"message": "Choose a priority", "fields": {"priority": "Required"}})
        prev = req.priority
        req.effective_priority = body.priority
        req.version += 1
        await apply_sla(session, req)
        await event(session, req, principal, "priority", f"Priority {prev} → {body.priority}" + (f" — {msg}" if msg else ""))
        await audit(
            session, actor_id=principal.id, action="request.set_priority", entity_type="request", entity_id=req.id,
            entity_ref=req.reference, company_id=req.company_id, data={"from": prev, "to": body.priority},
        )
    elif action == "start":
        await move(session, req, principal, S.in_progress, "processing", msg)
        req.fulfillment_status = "Processing"
    elif action == "await_finance":
        await move(session, req, principal, S.awaiting_finance, "awaiting_finance", msg)
        req.fulfillment_status = "Awaiting Finance"
    elif action == "finance_done":
        await move(session, req, principal, S.in_progress, "finance_confirmed", msg)
        req.fulfillment_status = "Payment confirmed"
        await notify(session, {req.requester_id}, kind="payment_status", title=f"Payment confirmed: {req.reference}", link=link_for(req))
    elif action == "fulfill":
        if not msg:
            raise bad_request({"message": "Describe what was delivered or resolved", "fields": {"message": "Required"}})
        await move(session, req, principal, S.fulfilled, "fulfilled", msg)
        req.fulfillment_status = "Fulfilled"
        await notify(
            session, {req.requester_id}, kind="fulfillment_confirmation", title=f"Please confirm: {req.reference}",
            body="Executive Admin marked this as fulfilled. Confirm receipt or resolution.", link=link_for(req),
        )
    elif action == "close":
        await move(session, req, principal, S.closed, "closed", msg)
    elif action == "reopen":
        if not msg:
            raise bad_request({"message": "Say why it is being reopened", "fields": {"message": "Required"}})
        await move(session, req, principal, S.in_progress, "reopened", msg)
    elif action == "cancel":
        if not msg:
            raise bad_request({"message": "A cancellation reason is required", "fields": {"message": "Required"}})
        await move(session, req, principal, S.cancelled, "cancelled", msg)
        await notify(session, {req.requester_id}, kind="approval_decision", title=f"Cancelled: {req.reference}", body=msg, link=link_for(req))
    elif action == "reassign_step":
        step = next((s for s in req.steps if s.id == body.step_id and s.status == StepStatus.pending), None)
        if step is None or body.approver_id is None:
            raise bad_request("Choose the pending stage and the new approver")
        emp = await employee_or_404(session, body.approver_id)
        if not emp.can_approve:
            raise bad_request({"message": f"{emp.name} has not been granted approval duties", "fields": {"approver_id": "No grant"}})
        if emp.id == req.requester_id:
            raise bad_request({"message": "The requester cannot approve their own request", "fields": {"approver_id": "Conflict"}})
        prev = step.approver.name if step.approver else "unassigned"
        step.approver_id = emp.id
        step.note = None
        await event(session, req, principal, "approver_changed", f"{step.name}: {prev} → {emp.name}" + (f" — {msg}" if msg else ""))
        await audit(
            session, actor_id=principal.id, action="approval.reassign", entity_type="request", entity_id=req.id,
            entity_ref=req.reference, company_id=req.company_id, data={"stage": step.name, "to": emp.employee_no},
        )
        await notify(session, {emp.id}, kind="approval_required", title=f"Approval needed: {req.reference}", body=f"{req.subject} — {step.name}", link=link_for(req))
    else:
        raise bad_request("Unknown action")
    await session.commit()
    return await detail(session, principal, await load(session, req.id))


@router.post("/requests/{request_id}/comments", status_code=201)
async def comment(request_id: int, body: CommentIn, principal: CurrentPrincipal, session: Session) -> dict:
    req = await load_visible(session, principal, request_id)
    if "comment" not in await allowed_actions(session, principal, req):
        raise forbidden()
    internal = body.internal and principal.is_staff and req.company_id in principal.company_ids
    await event(session, req, principal, "comment", body.message.strip(), internal=internal)
    if not internal:
        recipients = {req.requester_id} | ({req.assigned_to_id} if req.assigned_to_id else set())
        await notify(
            session, recipients, kind="comment", title=f"New comment on {req.reference}",
            body=body.message[:200], link=link_for(req), skip=principal.id,
        )
    await session.commit()
    return await detail(session, principal, await load(session, req.id))


__all__ = ["router", "load_visible", "is_operator"]
