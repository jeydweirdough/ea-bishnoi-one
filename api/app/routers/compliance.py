"""Phase 2.5 — government registrations, renewals, BOC import/export cases, renewal calendar, documents."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select

from ..core import admin_ids, audit, bad_request, conflict, forbidden, next_reference, not_found, notify
from ..models import Attachment, Task
from ..models_ops import Vehicle, VehicleStatus
from ..models_ops2 import BOC_MILESTONES, REG_STATUSES, REG_TYPES, BocCase, BocEvent, GovRegistration, RegistrationRenewal
from ..ops_common import check_version, company_for, count, day, days_until, employee_in, money, scoped
from ..security import Principal, Session, Staff
from ..serialize import attachment_out, iso, person

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])

TYPE_GROUPS = {"sec-gis": ["SEC", "GIS"], "business-permits": ["Business Permit"]}
WARN_DAYS = 60


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year + years, day=28)


def anchor(r: GovRegistration) -> date | None:
    return r.due_date or r.expiry_date


def reg_out(r: GovRegistration) -> dict:
    return {
        "id": r.id,
        "reference": r.reference,
        "company": {"id": r.company.id, "code": r.company.code, "name": r.company.name},
        "document_name": r.document_name,
        "registration_type": r.registration_type,
        "registration_number": r.registration_number,
        "registration_date": day(r.registration_date),
        "validity_years": r.validity_years,
        "expiry_date": day(r.expiry_date),
        "due_date": day(r.due_date),
        "days_left": days_until(anchor(r)),
        "responsible": person(r.responsible),
        "status": r.status,
        "site": r.site,
        "notes": r.notes,
        "version": r.version,
        "updated_at": iso(r.updated_at),
    }


async def log(session, principal: Principal | None, action: str, entity_type: str, rec, data: dict | None = None):
    await audit(
        session, actor_id=principal.id if principal else None, action=f"compliance.{action}", entity_type=entity_type,
        entity_id=rec.id, entity_ref=rec.reference, company_id=rec.company_id, data=data or {},
    )


@router.get("/options")
async def options(principal: Staff) -> dict:
    return {"registration_types": REG_TYPES, "statuses": REG_STATUSES, "boc_milestones": BOC_MILESTONES}


# ------------------------------------------------------------------ registrations


class RegIn(BaseModel):
    company_id: int | None = None
    document_name: str = Field(..., min_length=1, max_length=300)
    registration_type: str = Field(..., min_length=1, max_length=60)
    registration_number: str | None = Field(None, max_length=120)
    registration_date: date | None = None
    validity_years: int | None = Field(None, ge=1, le=50)
    expiry_date: date | None = None
    due_date: date | None = None
    responsible_id: int | None = None
    site: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=4000)

    @model_validator(mode="after")
    def dates(self):
        if self.registration_type not in REG_TYPES:
            raise ValueError("Choose a registration type from the list")
        if self.expiry_date is None and self.registration_date and self.validity_years:
            self.expiry_date = add_years(self.registration_date, self.validity_years)
        if self.registration_date and self.expiry_date and self.expiry_date <= self.registration_date:
            raise ValueError("Expiry must be after the registration date")
        if self.due_date and self.expiry_date and self.due_date > self.expiry_date:
            raise ValueError("The filing due date cannot be after expiry")
        return self


class RegPatch(RegIn):
    version: int


def status_for(r: GovRegistration) -> str:
    """Ongoing records move to For renewal inside the warning window and to Expired after expiry."""
    if r.status not in ("ongoing", "for_renewal"):
        return r.status
    if r.expiry_date and r.expiry_date < date.today():
        return "expired"
    n = days_until(anchor(r))
    if n is not None and n <= WARN_DAYS:
        return "for_renewal"
    return "ongoing"


@router.get("/registrations")
async def list_registrations(
    principal: Staff,
    session: Session,
    group: Literal["all", "sec-gis", "business-permits"] = "all",
    registration_type: str | None = None,
    status: list[str] = Query(default_factory=list),
    due_within: int | None = Query(None, ge=0, le=730),
    q: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict:
    stmt = select(GovRegistration).where(GovRegistration.company_id.in_(principal.company_ids))
    if group in TYPE_GROUPS:
        stmt = stmt.where(GovRegistration.registration_type.in_(TYPE_GROUPS[group]))
    if registration_type:
        stmt = stmt.where(GovRegistration.registration_type == registration_type)
    if status:
        stmt = stmt.where(GovRegistration.status.in_(status))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(GovRegistration.document_name.ilike(like), GovRegistration.registration_number.ilike(like), GovRegistration.reference.ilike(like)))
    rows = list((await session.execute(stmt)).scalars())
    if due_within is not None:
        rows = [r for r in rows if (n := days_until(anchor(r))) is not None and n <= due_within and r.status in ("ongoing", "for_renewal", "expired")]
    rows.sort(key=lambda r: (anchor(r) is None, anchor(r) or date.max))
    summary = {s: 0 for s in REG_STATUSES}
    for r in (await session.execute(select(GovRegistration).where(GovRegistration.company_id.in_(principal.company_ids)))).scalars():
        summary[r.status] = summary.get(r.status, 0) + 1
    return {"items": [reg_out(r) for r in rows[(page - 1) * page_size : page * page_size]], "total": len(rows), "page": page, "page_size": page_size, "summary": summary}


@router.post("/registrations", status_code=201)
async def create_registration(body: RegIn, principal: Staff, session: Session) -> dict:
    cid = await company_for(session, principal, body.company_id)
    await employee_in(session, body.responsible_id, cid, "responsible_id")
    r = GovRegistration(reference=await next_reference(session, "CMP"), company_id=cid, status="ongoing", **body.model_dump(exclude={"company_id"}))
    r.status = status_for(r)
    session.add(r)
    await session.flush()
    await log(session, principal, "registration_create", "registration", r, {"type": r.registration_type, "expiry": day(r.expiry_date)})
    await session.commit()
    return reg_out(await scoped(session, GovRegistration, r.id, principal))


@router.get("/registrations/{reg_id}")
async def get_registration(reg_id: int, principal: Staff, session: Session) -> dict:
    r = await scoped(session, GovRegistration, reg_id, principal)
    renewals = (await session.execute(select(RegistrationRenewal).where(RegistrationRenewal.registration_id == r.id).order_by(RegistrationRenewal.at.desc()))).scalars()
    atts = (await session.execute(select(Attachment).where(Attachment.owner_type == "registration", Attachment.owner_id == r.id))).scalars()
    tasks = (await session.execute(select(Task).where(Task.source_module == "compliance", Task.source_record_id == r.id).order_by(Task.id.desc()))).scalars()
    return {
        **reg_out(r),
        "renewals": [
            {
                "id": x.id, "previous_expiry": day(x.previous_expiry), "registration_date": day(x.registration_date), "new_expiry": day(x.new_expiry),
                "registration_number": x.registration_number, "cost_php": money(x.cost_php), "notes": x.notes, "filed_by": person(x.filed_by), "at": iso(x.at),
            }
            for x in renewals
        ],
        "attachments": [attachment_out(a) for a in atts],
        "tasks": [{"id": t.id, "reference": t.reference, "title": t.title, "status": t.status, "due_date": day(t.due_date), "assignee": person(t.assignee)} for t in tasks],
    }


@router.patch("/registrations/{reg_id}")
async def update_registration(reg_id: int, body: RegPatch, principal: Staff, session: Session) -> dict:
    r = await scoped(session, GovRegistration, reg_id, principal)
    check_version(r, body.version)
    if r.status in ("terminated", "void"):
        raise conflict("Terminated or void records cannot be edited")
    await employee_in(session, body.responsible_id, r.company_id, "responsible_id")
    changed = {}
    for k, v in body.model_dump(exclude={"company_id", "version"}).items():
        if getattr(r, k) != v:
            changed[k] = str(v)
            setattr(r, k, v)
    r.status = status_for(r)
    r.version += 1
    await log(session, principal, "registration_update", "registration", r, changed)
    await session.commit()
    return reg_out(await scoped(session, GovRegistration, r.id, principal))


class RenewIn(BaseModel):
    registration_date: date
    validity_years: int | None = Field(None, ge=1, le=50)
    expiry_date: date | None = None
    due_date: date | None = None
    registration_number: str | None = Field(None, max_length=120)
    cost_php: Decimal | None = Field(None, ge=0, le=Decimal("99999999"))
    notes: str | None = Field(None, max_length=4000)


@router.post("/registrations/{reg_id}/renew")
async def renew(reg_id: int, body: RenewIn, principal: Staff, session: Session) -> dict:
    r = await scoped(session, GovRegistration, reg_id, principal)
    if r.status in ("terminated", "void"):
        raise conflict("Terminated or void records cannot be renewed")
    if body.registration_date > date.today():
        raise bad_request({"message": "The renewal date cannot be in the future", "fields": {"registration_date": "In the future"}})
    years = body.validity_years or r.validity_years
    expiry = body.expiry_date or (add_years(body.registration_date, years) if years else None)
    if not expiry:
        raise bad_request({"message": "Enter the new expiry date or the years of validity", "fields": {"expiry_date": "Required"}})
    if expiry <= date.today() or (r.expiry_date and expiry <= r.expiry_date):
        raise bad_request({"message": "The new expiry must be later than today and the current expiry", "fields": {"expiry_date": "Too early"}})
    if body.due_date and body.due_date > expiry:
        raise bad_request({"message": "The filing due date cannot be after expiry", "fields": {"due_date": "After expiry"}})
    session.add(
        RegistrationRenewal(
            registration_id=r.id, previous_expiry=r.expiry_date, registration_date=body.registration_date, new_expiry=expiry, new_due=body.due_date,
            registration_number=body.registration_number, cost_php=body.cost_php, notes=body.notes, filed_by_id=principal.id,
        )
    )
    prev = r.expiry_date
    r.registration_date = body.registration_date
    r.validity_years = years
    r.expiry_date = expiry
    r.due_date = body.due_date
    if body.registration_number:
        r.registration_number = body.registration_number
    r.status = "ongoing"
    r.status = status_for(r)
    r.version += 1
    await log(session, principal, "registration_renewed", "registration", r, {"from": day(prev), "to": day(expiry), "cost_php": money(body.cost_php)})
    await session.commit()
    return reg_out(await scoped(session, GovRegistration, r.id, principal))


class AssignIn(BaseModel):
    assignee_id: int
    due_date: date | None = None
    note: str | None = Field(None, max_length=2000)


@router.post("/registrations/{reg_id}/assign-renewal")
async def assign_renewal(reg_id: int, body: AssignIn, principal: Staff, session: Session) -> dict:
    """Renewal assignment: makes a task for the person filing the renewal and sets them responsible."""
    r = await scoped(session, GovRegistration, reg_id, principal)
    from ..models import Role

    emp = await employee_in(session, body.assignee_id, r.company_id, "assignee_id")
    if emp.role not in (Role.admin, Role.assistant):
        raise bad_request({"message": "Renewals can be assigned to Admin or Assistant users", "fields": {"assignee_id": "Not staff"}})
    if emp.id != principal.id and not principal.can("assign"):
        raise forbidden("Assistants can only take renewals themselves unless delegated")
    t = Task(
        reference=await next_reference(session, "TSK"), company_id=r.company_id, title=f"Renew {r.document_name}",
        description=body.note or f"{r.registration_type} {r.registration_number or ''}".strip(), assignee_id=emp.id, created_by_id=principal.id,
        due_date=body.due_date or anchor(r), priority="high" if (days_until(anchor(r)) or 99) <= 14 else "normal",
        source_module="compliance", source_record_id=r.id,
    )
    session.add(t)
    r.responsible_id = emp.id
    r.version += 1
    await session.flush()
    await log(session, principal, "renewal_assigned", "registration", r, {"assignee": emp.employee_no, "task": t.reference})
    await notify(session, {emp.id}, kind="task_assignment", title=f"Renewal assigned: {r.document_name}", body=f"Due {day(t.due_date)}", link=f"/registration/{r.id}", skip=principal.id)
    await session.commit()
    return reg_out(await scoped(session, GovRegistration, r.id, principal))


class StatusIn(BaseModel):
    status: Literal["completed", "terminated", "void"]
    reason: str = Field(..., min_length=1, max_length=2000)


@router.post("/registrations/{reg_id}/status")
async def set_status(reg_id: int, body: StatusIn, principal: Staff, session: Session) -> dict:
    r = await scoped(session, GovRegistration, reg_id, principal)
    if body.status in ("terminated", "void") and not principal.is_admin:
        raise forbidden("Only Admin can terminate or void a registration")
    if r.status in ("terminated", "void"):
        raise conflict("This record is already closed")
    prev = r.status
    r.status = body.status
    r.notes = ((r.notes or "") + f"\n{body.status}: {body.reason}").strip()
    r.version += 1
    await log(session, principal, f"registration_{body.status}", "registration", r, {"from": prev, "reason": body.reason})
    await session.commit()
    return reg_out(await scoped(session, GovRegistration, r.id, principal))


# ------------------------------------------------------------------ BOC import / export


def boc_out(c: BocCase) -> dict:
    return {
        "id": c.id, "reference": c.reference, "company": {"id": c.company.id, "code": c.company.code}, "direction": c.direction,
        "shipment_reference": c.shipment_reference, "bill_of_lading": c.bill_of_lading, "entry_number": c.entry_number, "description": c.description,
        "counterparty": c.counterparty, "origin": c.origin, "destination": c.destination, "eta": day(c.eta), "broker": c.broker,
        "officer": person(c.officer), "status": c.status, "updated_at": iso(c.updated_at),
    }


class BocIn(BaseModel):
    company_id: int | None = None
    direction: Literal["import", "export"]
    description: str = Field(..., min_length=1, max_length=4000)
    shipment_reference: str | None = Field(None, max_length=120)
    bill_of_lading: str | None = Field(None, max_length=120)
    entry_number: str | None = Field(None, max_length=120)
    counterparty: str | None = Field(None, max_length=200)
    origin: str | None = Field(None, max_length=120)
    destination: str | None = Field(None, max_length=120)
    eta: date | None = None
    broker: str | None = Field(None, max_length=200)
    officer_id: int | None = None


@router.get("/boc")
async def list_boc(principal: Staff, session: Session, state: Literal["open", "closed", "all"] = "open", direction: str | None = None, q: str | None = None) -> list[dict]:
    stmt = select(BocCase).where(BocCase.company_id.in_(principal.company_ids))
    if state == "open":
        stmt = stmt.where(BocCase.status.notin_(["closed", "cancelled"]))
    elif state == "closed":
        stmt = stmt.where(BocCase.status.in_(["closed", "cancelled"]))
    if direction:
        stmt = stmt.where(BocCase.direction == direction)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(BocCase.reference.ilike(like), BocCase.shipment_reference.ilike(like), BocCase.bill_of_lading.ilike(like), BocCase.entry_number.ilike(like), BocCase.description.ilike(like)))
    rows = (await session.execute(stmt.order_by(BocCase.eta.is_(None), BocCase.eta, BocCase.id.desc()))).scalars()
    return [boc_out(c) for c in rows]


@router.post("/boc", status_code=201)
async def create_boc(body: BocIn, principal: Staff, session: Session) -> dict:
    cid = await company_for(session, principal, body.company_id)
    await employee_in(session, body.officer_id, cid, "officer_id")
    c = BocCase(reference=await next_reference(session, "BOC"), company_id=cid, created_by_id=principal.id, **body.model_dump(exclude={"company_id"}))
    session.add(c)
    await session.flush()
    session.add(BocEvent(case_id=c.id, milestone="draft", note="Case opened", actor_id=principal.id))
    await log(session, principal, "boc_create", "boc", c, {"direction": c.direction})
    if c.officer_id:
        await notify(session, {c.officer_id}, kind="task_assignment", title=f"BOC case assigned: {c.reference}", body=c.description[:200], link=f"/boc/{c.id}", skip=principal.id)
    await session.commit()
    return boc_out(await scoped(session, BocCase, c.id, principal))


@router.get("/boc/{case_id}")
async def get_boc(case_id: int, principal: Staff, session: Session) -> dict:
    c = await scoped(session, BocCase, case_id, principal)
    events = (await session.execute(select(BocEvent).where(BocEvent.case_id == c.id).order_by(BocEvent.at.desc(), BocEvent.id.desc()))).scalars()
    atts = (await session.execute(select(Attachment).where(Attachment.owner_type == "boc", Attachment.owner_id == c.id))).scalars()
    return {
        **boc_out(c),
        "events": [{"id": e.id, "milestone": e.milestone, "note": e.note, "actor": person(e.actor), "at": iso(e.at)} for e in events],
        "attachments": [attachment_out(a) for a in atts],
        "next": [m for m in BOC_MILESTONES if BOC_MILESTONES.index(m) > BOC_MILESTONES.index(c.status) and m != "cancelled"][:1] if c.status not in ("closed", "cancelled") else [],
    }


@router.patch("/boc/{case_id}")
async def update_boc(case_id: int, body: BocIn, principal: Staff, session: Session) -> dict:
    c = await scoped(session, BocCase, case_id, principal)
    if c.status in ("closed", "cancelled"):
        raise conflict("Closed cases cannot be edited")
    await employee_in(session, body.officer_id, c.company_id, "officer_id")
    changed = {}
    for k, v in body.model_dump(exclude={"company_id"}).items():
        if getattr(c, k) != v:
            changed[k] = str(v)
            setattr(c, k, v)
    await log(session, principal, "boc_update", "boc", c, changed)
    await session.commit()
    return boc_out(await scoped(session, BocCase, c.id, principal))


class MilestoneIn(BaseModel):
    milestone: str | None = None
    note: str | None = Field(None, max_length=4000)


@router.post("/boc/{case_id}/events")
async def boc_event(case_id: int, body: MilestoneIn, principal: Staff, session: Session) -> dict:
    c = await scoped(session, BocCase, case_id, principal)
    if c.status in ("closed", "cancelled"):
        raise conflict("This case is closed")
    if body.milestone:
        if body.milestone not in BOC_MILESTONES:
            raise bad_request({"message": "Unknown milestone", "fields": {"milestone": "Unknown"}})
        if body.milestone != "cancelled" and BOC_MILESTONES.index(body.milestone) <= BOC_MILESTONES.index(c.status):
            raise conflict("Milestones only move forward")
        if body.milestone == "cancelled" and not (body.note or "").strip():
            raise bad_request({"message": "Say why the case is cancelled", "fields": {"note": "Required"}})
        c.status = body.milestone
    elif not (body.note or "").strip():
        raise bad_request({"message": "Add a note or a milestone", "fields": {"note": "Required"}})
    session.add(BocEvent(case_id=c.id, milestone=body.milestone, note=body.note, actor_id=principal.id))
    await log(session, principal, "boc_event", "boc", c, {"milestone": body.milestone, "note": body.note})
    await session.commit()
    return await get_boc(c.id, principal, session)


# ------------------------------------------------------------------ calendar & documents


@router.get("/calendar")
async def calendar(principal: Staff, session: Session, months: int = Query(12, ge=1, le=36), include_overdue: bool = True) -> list[dict]:
    """Every dated obligation: registration due/expiry dates, BOC ETAs, vehicle registration/insurance/PMS."""
    end = date.today() + timedelta(days=31 * months)
    out = []
    regs = (await session.execute(select(GovRegistration).where(GovRegistration.company_id.in_(principal.company_ids), GovRegistration.status.in_(["ongoing", "for_renewal", "expired"])))).scalars()
    for r in regs:
        for kind, d in (("filing due", r.due_date), ("expires", r.expiry_date)):
            if d and d <= end and (include_overdue or d >= date.today()):
                out.append({"date": day(d), "days": days_until(d), "kind": kind, "module": "compliance", "title": r.document_name, "subtitle": r.registration_type, "company": r.company.code, "href": f"/registration/{r.id}"})
    for c in (await session.execute(select(BocCase).where(BocCase.company_id.in_(principal.company_ids), BocCase.status.notin_(["closed", "cancelled", "delivered"])))).scalars():
        if c.eta and c.eta <= end:
            out.append({"date": day(c.eta), "days": days_until(c.eta), "kind": "ETA", "module": "boc", "title": c.description[:80], "subtitle": f"BOC {c.direction}", "company": c.company.code, "href": f"/boc/{c.id}"})
    for v in (await session.execute(select(Vehicle).where(Vehicle.company_id.in_(principal.company_ids), Vehicle.status.in_([VehicleStatus.active, VehicleStatus.under_maintenance])))).scalars():
        for kind, d in (("registration", v.registration_renewal_date), ("insurance", v.insurance_expiry_date)):
            if d and d <= end and (include_overdue or d >= date.today()):
                out.append({"date": day(d), "days": days_until(d), "kind": kind, "module": "fleet", "title": v.label, "subtitle": "Vehicle", "company": v.company.code, "href": f"/vehicle/{v.id}"})
    from ..models_ops3 import Contract

    for k in (await session.execute(select(Contract).where(Contract.company_id.in_(principal.company_ids), Contract.status.in_(["active", "for_renewal", "expired"])))).scalars():
        if k.end_date <= end and (include_overdue or k.end_date >= date.today()):
            out.append({"date": day(k.end_date), "days": days_until(k.end_date), "kind": "ends", "module": "contract", "title": k.title, "subtitle": "Lease" if k.contract_type != "other" else "Contract", "company": k.company.code, "href": f"/contract/{k.id}"})
    out.sort(key=lambda x: x["date"])
    return out


@router.get("/documents")
async def documents(principal: Staff, session: Session, q: str | None = None) -> list[dict]:
    regs = {r.id: r for r in (await session.execute(select(GovRegistration).where(GovRegistration.company_id.in_(principal.company_ids)))).scalars()}
    cases = {c.id: c for c in (await session.execute(select(BocCase).where(BocCase.company_id.in_(principal.company_ids)))).scalars()}
    stmt = select(Attachment).where(
        or_(
            (Attachment.owner_type == "registration") & Attachment.owner_id.in_(list(regs) or [0]),
            (Attachment.owner_type == "boc") & Attachment.owner_id.in_(list(cases) or [0]),
        )
    )
    if q:
        stmt = stmt.where(Attachment.filename.ilike(f"%{q}%"))
    out = []
    for a in (await session.execute(stmt.order_by(Attachment.uploaded_at.desc()))).scalars():
        owner = regs.get(a.owner_id) if a.owner_type == "registration" else cases.get(a.owner_id)
        label = owner.document_name if a.owner_type == "registration" else f"BOC {owner.direction}: {owner.description[:60]}"
        href = f"/registration/{owner.id}" if a.owner_type == "registration" else f"/boc/{owner.id}"
        out.append({**attachment_out(a), "owner": {"type": a.owner_type, "reference": owner.reference, "label": label, "href": href}})
    return out


# ------------------------------------------------------------------ reminders (sweep)


async def compliance_reminders(session) -> int:
    sent = 0
    # Expired records keep getting the overdue reminder until they are renewed or closed.
    for r in (await session.execute(select(GovRegistration).where(GovRegistration.status.in_(["ongoing", "for_renewal", "expired"])))).scalars().all():
        new = status_for(r)
        if new != r.status:
            r.status = new
            await audit(session, actor_id=None, action=f"compliance.auto_{new}", entity_type="registration", entity_id=r.id, entity_ref=r.reference, company_id=r.company_id)
        d = anchor(r)
        n = days_until(d)
        if n is None or n > WARN_DAYS:
            continue
        band = 0 if n <= 0 else 7 if n <= 7 else 30 if n <= 30 else 60
        when = "is overdue" if n < 0 else "is due today" if n == 0 else f"is due in {n} days"
        recipients = await admin_ids(session, r.company_id) | ({r.responsible_id} if r.responsible_id else set())
        await notify(
            session, recipients, kind="renewal_warning", title=f"{r.registration_type} renewal {when}: {r.document_name}",
            body=f"{r.reference} · {d.isoformat()}", link=f"/registration/{r.id}", dedupe_key=f"cmp:{r.id}:{d.isoformat()}:{band}",
        )
        sent += 1
    return sent
