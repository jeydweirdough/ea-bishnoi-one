"""The shared request link (/request): one place where anyone can report a problem, request items, or both.

- Signed in: the request is filed straight away as the signed-in person and starts its approval route.
- Not signed in: the person types their details. The submission waits in "From the request link" until
  Admin or an Assistant confirms who sent it and accepts it (filing the real request for that person) or
  declines it. Nothing reaches approvers before a person on the EA team has looked at it.

The public endpoints are rate-limited per address, take only what the form asks for, and keep photos
re-encoded without metadata. The status check needs both the reference and the email it was sent with.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, Query, Request as HttpRequest, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import func, or_, select

from ..auth import client_ip
from ..config import get_settings
from ..core import audit, bad_request, conflict, next_reference, not_found, notify, now
from ..models import (
    Attachment,
    Company,
    Department,
    Employee,
    Priority,
    Request,
    RequestKind,
    RequestStatus as S,
    Role,
    WebRequest,
)
from ..security import Principal, Session, Staff, get_principal
from ..serialize import iso, person
from ..workflow import event, submit
from .attachments import storage_dir
from .photos import process
from .requests import CONCERN_CATEGORIES, SUPPLY_CATEGORIES, UNITS, RequestIn, apply_fields

router = APIRouter(prefix="/api/v1", tags=["request link"])

MAX_PHOTOS = 4
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STATUS_LABEL = {
    S.draft: "Draft",
    S.submitted: "Submitted",
    S.under_review: "Waiting for approval",
    S.returned: "Returned for more information",
    S.approved: "Approved",
    S.rejected: "Not approved",
    S.in_progress: "Being worked on",
    S.fulfilled: "Done",
    S.closed: "Closed",
    S.awaiting_finance: "Waiting for Finance",
    S.cancelled: "Cancelled",
}

# ------------------------------------------------------------------ rate limits (in-process; the API runs one worker)

_hits: dict[str, deque] = defaultdict(deque)
LIMITS = {"submit": (6, 15 * 60), "status": (30, 15 * 60)}


def throttle(kind: str, ip: str) -> None:
    n, window = LIMITS[kind]
    q = _hits[f"{kind}:{ip}"]
    cutoff = time.monotonic() - window
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= n:
        raise HTTPException(429, {"message": "Too many tries from this connection. Please wait a few minutes and try again."})
    q.append(time.monotonic())


async def optional_principal(request: HttpRequest, session) -> Principal | None:
    """The signed-in person, if any. The form works for everyone, so being signed out is not an error."""
    try:
        return await get_principal(request, session, request.cookies.get("ea_user"), request.headers.get("x-ea-user"), request.cookies.get("ea_session"))
    except HTTPException:
        return None


# ------------------------------------------------------------------ form


class ItemLine(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=300)
    quantity: int = Field(1, ge=1, le=10000)
    unit: str = Field("pc", min_length=1, max_length=40)
    description: str | None = Field(None, max_length=1000)


class ProblemIn(BaseModel):
    category: str = Field(..., max_length=120)
    subject: str = Field(..., min_length=1, max_length=300)
    description: str = Field(..., min_length=1, max_length=5000)
    location: str | None = Field(None, max_length=300)
    related_item: str | None = Field(None, max_length=300)

    @field_validator("category")
    @classmethod
    def known(cls, v):
        if v not in CONCERN_CATEGORIES:
            raise ValueError("Choose a category from the list")
        return v


class SuppliesIn(BaseModel):
    category: str = Field("Office supplies", max_length=120)
    items: list[ItemLine] = Field(..., min_length=1, max_length=30)
    purpose: str = Field(..., min_length=1, max_length=2000)
    needed_by: date
    delivery_location: str | None = Field(None, max_length=300)

    @field_validator("category")
    @classmethod
    def known(cls, v):
        if v not in SUPPLY_CATEGORIES:
            raise ValueError("Choose a category from the list")
        return v


class LinkForm(BaseModel):
    name: str = Field("", max_length=200)
    email: str = Field("", max_length=254)
    phone: str | None = Field(None, max_length=40)
    position: str | None = Field(None, max_length=120)
    company_id: int | None = None
    department_id: int | None = None
    problem: ProblemIn | None = None
    supplies: SuppliesIn | None = None
    urgent: bool = False
    # Left empty by people; filled in by bots that complete every field.
    website: str = Field("", max_length=200)

    @field_validator("name", "email", "phone", "position")
    @classmethod
    def strip(cls, v):
        return v.strip() if isinstance(v, str) else v


def field_errors(e: ValidationError) -> dict[str, str]:
    out = {}
    for err in e.errors():
        key = ".".join(str(x) for x in err["loc"])
        msg = err["msg"].removeprefix("Value error, ")
        if err["type"] == "missing" or (err["type"] == "string_too_short" and (err.get("ctx") or {}).get("min_length") == 1):
            msg = "Required"
        elif err["type"] == "too_short" and key.endswith("items"):
            msg = "Add at least one item"
        out[key] = msg
    return out


@router.get("/public/request-form")
async def form_options(request: HttpRequest, session: Session) -> dict:
    p = await optional_principal(request, session)
    companies = (await session.execute(select(Company).order_by(Company.code))).scalars().all()
    depts = (await session.execute(select(Department).order_by(Department.name))).scalars().all()
    me = None
    if p:
        e = p.employee
        me = {"name": e.name, "email": e.email, "company": e.company.name, "company_id": e.company_id, "department": e.department.name if e.department else None, "department_id": e.department_id}
    return {
        "companies": [{"id": c.id, "code": c.code, "name": c.name} for c in companies],
        "departments": [{"id": d.id, "name": d.name, "company_id": d.company_id} for d in depts],
        "concern_categories": CONCERN_CATEGORIES,
        "supply_categories": SUPPLY_CATEGORIES,
        "units": UNITS,
        "me": me,
        "max_photos": MAX_PHOTOS,
    }


def problem_request(p: ProblemIn, urgent: bool) -> RequestIn:
    return RequestIn(
        kind=RequestKind.concern, category=p.category, subject=p.subject.strip(), description=p.description.strip(), location=p.location,
        related_asset=p.related_item, requested_priority=Priority.high if urgent else Priority.normal, submit=True,
    )


def supplies_request(s: SuppliesIn, urgent: bool) -> RequestIn:
    first = s.items[0].item_name.strip()
    subject = first if len(s.items) == 1 else f"{first} and {len(s.items) - 1} more"
    return RequestIn(
        kind=RequestKind.supplies, category=s.category, subject=subject[:300], purpose=s.purpose.strip(), needed_by=s.needed_by,
        delivery_location=s.delivery_location, requested_priority=Priority.high if urgent else Priority.normal,
        items=[{"item_name": i.item_name.strip(), "quantity": i.quantity, "unit": i.unit, "description": i.description} for i in s.items], submit=True,
    )


async def file_requests(session, actor: Principal, employee: Employee, bodies: list[RequestIn], *, department_id: int | None, note: str) -> list[Request]:
    """Create and submit the requests for `employee`. Runs the same checks and approval route as the app's own forms."""
    made = []
    for body in bodies:
        req = Request(
            reference=await next_reference(session, "REQ"), company_id=employee.company_id, department_id=employee.department_id or department_id,
            requester_id=employee.id, status=S.draft,
        )
        session.add(req)
        apply_fields(req, body)
        await session.flush()
        await event(session, req, actor, "created", note)
        await audit(session, actor_id=actor.id, action="request.create", entity_type="request", entity_id=req.id, entity_ref=req.reference, company_id=req.company_id, data={"kind": req.kind, "via": "request_link"})
        await session.flush()
        req = (await session.execute(select(Request).where(Request.id == req.id).execution_options(populate_existing=True))).scalar_one()
        await submit(session, actor, req)
        made.append(req)
    return made


async def read_photos(photos: list[UploadFile]) -> list[bytes]:
    if len(photos) > MAX_PHOTOS:
        raise bad_request({"message": f"Add at most {MAX_PHOTOS} photos", "fields": {"photos": f"At most {MAX_PHOTOS}"}})
    limit = get_settings().max_upload_mb * 1024 * 1024
    out = []
    for f in photos:
        data = await f.read(limit + 1)
        if not data:
            continue
        if len(data) > limit:
            raise bad_request({"message": f"Photos must be {get_settings().max_upload_mb} MB or smaller", "fields": {"photos": "Too large"}})
        out.append(process(data)[0])  # re-encoded: upright, resized, no metadata
    return out


def store(full: bytes) -> dict:
    key = secrets.token_hex(16)
    (storage_dir() / key).write_bytes(full)
    return {"key": key, "size": len(full)}


async def attach_photos(session, req: Request, photos: list[dict], uploader_id: int, ref: str) -> None:
    import hashlib

    for n, ph in enumerate(photos, 1):
        data = (storage_dir() / ph["key"]).read_bytes() if (storage_dir() / ph["key"]).exists() else b""
        if not data:
            continue
        session.add(Attachment(
            owner_type="request", owner_id=req.id, filename=f"{ref}-photo-{n}.jpg", content_type="image/jpeg", size=len(data),
            storage_key=ph["key"], sha256=hashlib.sha256(data).hexdigest(), uploaded_by_id=uploader_id, purpose="evidence",
        ))


async def staff_ids(session, company_id: int) -> set[int]:
    code = (await session.execute(select(Company.code).where(Company.id == company_id))).scalar_one_or_none()
    rows = (await session.execute(select(Employee).where(Employee.role.in_([Role.admin, Role.assistant]), Employee.active.is_(True), Employee.source != "added"))).scalars()
    return {e.id for e in rows if e.company_id == company_id or (code and code in (e.company_access or []))}


@router.post("/public/requests", status_code=201)
async def submit_link(request: HttpRequest, session: Session, data: str = Form(...), photos: list[UploadFile] = File(default_factory=list)) -> dict:
    try:
        raw = json.loads(data)
        if not isinstance(raw, dict):
            raise ValueError
    except ValueError:
        raise bad_request({"message": "The form could not be read"})
    if raw.get("website"):  # a bot filled the hidden field: accept quietly, keep nothing
        return {"reference": "EA-WEB-0000", "status": "received", "requests": []}
    principal = await optional_principal(request, session)
    # Report every problem at once: the form part and, when signed out, the "about you" part.
    fields: dict[str, str] = {}
    form = None
    try:
        form = LinkForm.model_validate(raw)
    except ValidationError as e:
        fields = field_errors(e)
    if principal is None:
        if len(str(raw.get("name") or "").strip()) < 2:
            fields["name"] = "Enter your full name"
        if not EMAIL.match(str(raw.get("email") or "").strip()):
            fields["email"] = "Enter a valid email address"
        if raw.get("company_id") in (None, ""):
            fields["company_id"] = "Choose your company"
    if not raw.get("problem") and not raw.get("supplies"):
        fields["need"] = "Choose at least one"
    if form and form.supplies and form.supplies.needed_by < date.today():
        fields["supplies.needed_by"] = "Cannot be in the past"
    if fields or form is None:
        only_need = set(fields) == {"need"}
        raise bad_request({"message": "Choose what you need: report a problem, request items, or both" if only_need else "Some fields need attention", "fields": fields})
    throttle("submit", client_ip(request))
    images = await read_photos(photos)
    bodies = [b for b in (problem_request(form.problem, form.urgent) if form.problem else None, supplies_request(form.supplies, form.urgent) if form.supplies else None) if b]

    if principal is not None:
        # Signed in: they are who they say they are. File it now.
        made = await file_requests(session, principal, principal.employee, bodies, department_id=None, note="Sent from the request link")
        if images:
            stored = [store(x) for x in images]
            await attach_photos(session, made[0], stored, principal.id, made[0].reference)
        await session.commit()
        return {"reference": made[0].reference, "status": "submitted", "requests": [{"id": r.id, "reference": r.reference, "status": STATUS_LABEL.get(r.status, r.status)} for r in made]}

    company = await session.get(Company, form.company_id)
    if company is None:
        raise bad_request({"message": "Choose your company", "fields": {"company_id": "Unknown company"}})
    if form.department_id is not None:
        dept = await session.get(Department, form.department_id)
        if dept is None or dept.company_id != company.id:
            raise bad_request({"message": "Choose a department of your company", "fields": {"department_id": "Not in this company"}})
    email = form.email.lower()
    match = (await session.execute(select(Employee).where(func.lower(Employee.email) == email, Employee.active.is_(True)))).scalars().first()
    w = WebRequest(
        reference=await next_reference(session, "WEB"), company_id=company.id, department_id=form.department_id, name=form.name, email=email,
        phone=form.phone or None, position=form.position or None, urgent=form.urgent,
        problem=form.problem.model_dump() if form.problem else None,
        supplies=form.supplies.model_dump(mode="json") if form.supplies else None,
        photos=[store(x) for x in images], employee_id=match.id if match else None,
    )
    session.add(w)
    await session.flush()
    await audit(session, actor_id=None, action="request_link.receive", entity_type="web_request", entity_id=w.id, entity_ref=w.reference, company_id=company.id, data={"problem": bool(form.problem), "items": bool(form.supplies), "photos": len(images)})
    what = " and ".join(x for x in ("a problem report" if form.problem else "", "an item request" if form.supplies else "") if x)
    await notify(session, await staff_ids(session, company.id), kind="new_request", title=f"From the request link: {w.reference}", body=f"{w.name} sent {what}. Check who sent it, then accept or decline.", link=f"/requests/from-link?id={w.id}")
    await session.commit()
    return {"reference": w.reference, "status": "received", "requests": []}


@router.get("/public/requests/status")
async def link_status(request: HttpRequest, session: Session, reference: str = Query(..., max_length=40), email: str = Query(..., max_length=254)) -> dict:
    throttle("status", client_ip(request))
    ref, mail = reference.strip().upper(), email.strip().lower()
    w = (await session.execute(select(WebRequest).where(WebRequest.reference == ref))).scalar_one_or_none()
    if w is None or w.email != mail:
        raise not_found("No request matches that reference and email")
    reqs = (await session.execute(select(Request).where(Request.id.in_(w.request_ids or [0])).order_by(Request.id))).scalars().all()
    label = {"new": "Received — the EA team will check it soon", "accepted": "Accepted and sent for approval", "declined": "Declined"}[w.status]
    return {
        "reference": w.reference,
        "received_at": iso(w.created_at),
        "status": w.status,
        "status_label": label,
        "decline_reason": w.decline_reason if w.status == "declined" else None,
        "requests": [{"reference": r.reference, "subject": r.subject, "status": STATUS_LABEL.get(r.status, r.status)} for r in reqs],
    }


# ------------------------------------------------------------------ EA inbox


def web_out(w: WebRequest, requests: list[Request] | None = None) -> dict:
    return {
        "id": w.id,
        "reference": w.reference,
        "name": w.name,
        "email": w.email,
        "phone": w.phone,
        "position": w.position,
        "company": {"id": w.company.id, "code": w.company.code, "name": w.company.name},
        "department": {"id": w.department.id, "name": w.department.name} if w.department else None,
        "problem": w.problem,
        "supplies": w.supplies,
        "urgent": w.urgent,
        "photos": [f"/api/v1/web-requests/{w.id}/photos/{n}" for n in range(len(w.photos or []))],
        "status": w.status,
        "match": person(w.employee),
        "requests": [{"id": r.id, "reference": r.reference, "subject": r.subject, "status": r.status} for r in (requests or [])],
        "handled_by": person(w.handled_by),
        "handled_at": iso(w.handled_at),
        "decline_reason": w.decline_reason,
        "created_at": iso(w.created_at),
        "version": w.version,
    }


async def load_web(session, principal: Principal, wid: int, *, lock: bool = False) -> WebRequest:
    stmt = select(WebRequest).where(WebRequest.id == wid).execution_options(populate_existing=True)
    if lock:
        stmt = stmt.with_for_update(of=WebRequest)
    w = (await session.execute(stmt)).scalar_one_or_none()
    if w is None or w.company_id not in principal.company_ids:
        raise not_found()
    return w


@router.get("/web-requests")
async def list_web(principal: Staff, session: Session, status: str = Query("new", pattern="^(new|accepted|declined|all)$"), q: str | None = Query(None, max_length=200)) -> dict:
    stmt = select(WebRequest).where(WebRequest.company_id.in_(principal.company_ids))
    if status != "all":
        stmt = stmt.where(WebRequest.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(WebRequest.reference.ilike(like), WebRequest.name.ilike(like), WebRequest.email.ilike(like)))
    rows = (await session.execute(stmt.order_by(WebRequest.created_at.desc()).limit(200))).scalars().all()
    waiting = (await session.execute(select(func.count()).select_from(WebRequest).where(WebRequest.company_id.in_(principal.company_ids), WebRequest.status == "new"))).scalar_one()
    return {"items": [web_out(w) for w in rows], "waiting": waiting}


@router.get("/web-requests/{wid}")
async def get_web(wid: int, principal: Staff, session: Session) -> dict:
    w = await load_web(session, principal, wid)
    reqs = (await session.execute(select(Request).where(Request.id.in_(w.request_ids or [0])).order_by(Request.id))).scalars().all()
    return web_out(w, list(reqs))


@router.get("/web-requests/{wid}/photos/{n}")
async def web_photo(wid: int, n: int, principal: Staff, session: Session):
    w = await load_web(session, principal, wid)
    if not 0 <= n < len(w.photos or []):
        raise not_found()
    path = storage_dir() / w.photos[n]["key"]
    if not path.exists():
        raise not_found("The stored photo is missing")
    return FileResponse(path, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})


class AcceptIn(BaseModel):
    # File it for this person (pre-chosen when the email matches someone), or add them as a new person.
    employee_id: int | None = None
    add_person: bool = False
    version: int


class DeclineIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)
    version: int


@router.post("/web-requests/{wid}/accept")
async def accept(wid: int, body: AcceptIn, principal: Staff, session: Session) -> dict:
    w = await load_web(session, principal, wid, lock=True)
    if w.status != "new":
        raise conflict("This was already handled")
    if w.version != body.version:
        raise conflict("Someone else changed this just now. Reload to see it.")
    if body.add_person:
        emp = Employee(
            employee_no=await next_reference(session, "PPL"), name=w.name, email=None, designation=w.position, company_id=w.company_id,
            department_id=w.department_id, role="employee", can_approve=False, delegations={}, company_access=[], active=True,
            source="added", added_by_id=principal.id,
        )
        session.add(emp)
        await session.flush()
        await audit(session, actor_id=principal.id, action="person.add", entity_type="employee", entity_id=emp.id, entity_ref=emp.employee_no, company_id=w.company_id, data={"name": w.name, "via": w.reference})
    elif body.employee_id:
        emp = await session.get(Employee, body.employee_id)
        if emp is None or not emp.active or emp.company_id not in principal.company_ids:
            raise bad_request({"message": "Choose someone from your companies", "fields": {"employee_id": "Not available"}})
    else:
        raise bad_request({"message": "Choose who sent it, or add them as a new person", "fields": {"employee_id": "Required"}})
    bodies = []
    if w.problem:
        bodies.append(problem_request(ProblemIn.model_validate(w.problem), w.urgent))
    if w.supplies:
        sup = SuppliesIn.model_validate(w.supplies)
        if sup.needed_by < date.today():
            sup.needed_by = date.today()
        bodies.append(supplies_request(sup, w.urgent))
    made = await file_requests(session, principal, emp, bodies, department_id=w.department_id, note=f"Sent through the request link ({w.reference}) by {w.name} <{w.email}>. Accepted by {principal.employee.name}.")
    if w.photos:
        await attach_photos(session, made[0], w.photos, principal.id, made[0].reference)
    w.status = "accepted"
    w.employee_id = emp.id
    w.request_ids = [r.id for r in made]
    w.handled_by_id = principal.id
    w.handled_at = now()
    w.version += 1
    await audit(session, actor_id=principal.id, action="request_link.accept", entity_type="web_request", entity_id=w.id, entity_ref=w.reference, company_id=w.company_id, data={"employee": emp.id, "requests": [r.reference for r in made]})
    await session.commit()
    return await get_web(w.id, principal, session)


@router.post("/web-requests/{wid}/decline")
async def decline(wid: int, body: DeclineIn, principal: Staff, session: Session) -> dict:
    w = await load_web(session, principal, wid, lock=True)
    if w.status != "new":
        raise conflict("This was already handled")
    if w.version != body.version:
        raise conflict("Someone else changed this just now. Reload to see it.")
    w.status = "declined"
    w.decline_reason = body.reason.strip()
    w.handled_by_id = principal.id
    w.handled_at = now()
    w.version += 1
    await audit(session, actor_id=principal.id, action="request_link.decline", entity_type="web_request", entity_id=w.id, entity_ref=w.reference, company_id=w.company_id, data={"reason": w.decline_reason})
    await session.commit()
    return await get_web(w.id, principal, session)
