"""Phase 2.6 — flights, hotels, configurable travel requirements, passports and visas (sensitive)."""

import re
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import or_, select

from ..core import admin_ids, audit, bad_request, conflict, forbidden, next_reference, not_found, notify, now
from ..models import Attachment, Employee
from ..models_ops2 import FLIGHT_STATUSES, FlightBooking, HotelReservation, TravelDocument, TravelRequirement
from ..ops_common import check_version, company_for, day, days_until, employee_in, scoped
from ..security import AdminOnly, CurrentPrincipal, Principal, Session, Staff
from ..serialize import attachment_out, iso, person

router = APIRouter(prefix="/api/v1/travel", tags=["travel"])

FLIGHT_FLOW = {
    "requested": {"booked", "cancelled"},
    "booked": {"ticketed", "cancelled"},
    "ticketed": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}
HOTEL_FLOW = {"requested": {"booked", "cancelled"}, "booked": {"completed", "cancelled"}, "completed": set(), "cancelled": set()}


def can_see_documents(p: Principal) -> bool:
    """Passports and visas: Admin, or an Assistant explicitly delegated travel-document access."""
    return p.is_admin or (p.is_staff and p.delegated("travel_documents"))


async def requirements_for(session, travel_type: str, country: str | None) -> list[TravelRequirement]:
    rows = (await session.execute(select(TravelRequirement).where(TravelRequirement.active.is_(True), TravelRequirement.travel_type == travel_type).order_by(TravelRequirement.position, TravelRequirement.id))).scalars()
    c = (country or "").strip().lower()
    return [r for r in rows if r.country is None or r.country.strip().lower() == c]


def req_out(r: TravelRequirement) -> dict:
    return {"id": r.id, "travel_type": r.travel_type, "country": r.country, "name": r.name, "description": r.description, "active": r.active, "position": r.position}


async def flight_out(session, f: FlightBooking, with_checklist: bool = True) -> dict:
    out = {
        "id": f.id, "reference": f.reference, "company": {"id": f.company.id, "code": f.company.code}, "passenger": person(f.passenger),
        "travel_type": f.travel_type, "origin": f.origin, "destination": f.destination, "destination_country": f.destination_country,
        "departure_date": day(f.departure_date), "return_date": day(f.return_date), "airline": f.airline, "booking_reference": f.booking_reference,
        "status": f.status, "purpose": f.purpose, "notes": f.notes, "days_to_departure": days_until(f.departure_date), "updated_at": iso(f.updated_at),
    }
    if with_checklist:
        reqs = await requirements_for(session, f.travel_type, f.destination_country)
        items = [{**req_out(r), "done": bool((f.checklist or {}).get(str(r.id), {}).get("done"))} for r in reqs]
        out["checklist"] = items
        out["checklist_done"] = sum(1 for i in items if i["done"])
        out["checklist_total"] = len(items)
    return out


def hotel_out(h: HotelReservation) -> dict:
    return {
        "id": h.id, "reference": h.reference, "company": {"id": h.company.id, "code": h.company.code}, "guest": person(h.guest), "flight_id": h.flight_id,
        "hotel": h.hotel, "destination": h.destination, "check_in": day(h.check_in), "check_out": day(h.check_out), "nights": (h.check_out - h.check_in).days,
        "booking_reference": h.booking_reference, "status": h.status, "cost_reference": h.cost_reference, "notes": h.notes,
    }


def doc_out(d: TravelDocument) -> dict:
    return {
        "id": d.id, "reference": d.reference, "company": {"id": d.company.id, "code": d.company.code}, "employee": person(d.employee),
        "doc_type": d.doc_type, "holder_kind": d.holder_kind, "visa_type": d.visa_type, "country": d.country,
        "number_masked": f"•••• {d.number_last4}" if d.number_last4 else None, "application_date": day(d.application_date),
        "issue_date": day(d.issue_date), "expiry_date": day(d.expiry_date), "renewal_date": day(d.renewal_date),
        "days_to_expiry": days_until(d.expiry_date), "status": d.status, "responsible": person(d.responsible), "notes": d.notes, "version": d.version,
    }


async def log(session, principal: Principal | None, action: str, entity_type: str, rec, data: dict | None = None):
    await audit(session, actor_id=principal.id if principal else None, action=f"travel.{action}", entity_type=entity_type, entity_id=rec.id, entity_ref=rec.reference, company_id=rec.company_id, data=data or {})


# ------------------------------------------------------------------ requirements (configurable)


class ReqIn(BaseModel):
    travel_type: Literal["domestic", "international"]
    country: str | None = Field(None, max_length=80)
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    active: bool = True
    position: int = Field(0, ge=0, le=1000)


@router.get("/requirements")
async def list_requirements(principal: Staff, session: Session) -> list[dict]:
    rows = (await session.execute(select(TravelRequirement).order_by(TravelRequirement.travel_type, TravelRequirement.country.is_not(None), TravelRequirement.country, TravelRequirement.position))).scalars()
    return [req_out(r) for r in rows]


@router.post("/requirements", status_code=201)
async def create_requirement(body: ReqIn, principal: AdminOnly, session: Session) -> dict:
    r = TravelRequirement(**{**body.model_dump(), "country": (body.country or "").strip() or None})
    session.add(r)
    await session.flush()
    await audit(session, actor_id=principal.id, action="travel.requirement_create", entity_type="travel_requirement", entity_id=r.id, data=body.model_dump())
    await session.commit()
    return req_out(r)


@router.patch("/requirements/{req_id}")
async def update_requirement(req_id: int, body: ReqIn, principal: AdminOnly, session: Session) -> dict:
    r = await session.get(TravelRequirement, req_id)
    if r is None:
        raise not_found()
    for k, v in body.model_dump().items():
        setattr(r, k, (v or "").strip() or None if k == "country" else v)
    await audit(session, actor_id=principal.id, action="travel.requirement_update", entity_type="travel_requirement", entity_id=r.id, data=body.model_dump())
    await session.commit()
    return req_out(r)


# ------------------------------------------------------------------ flights


class FlightIn(BaseModel):
    company_id: int | None = None
    passenger_id: int
    travel_type: Literal["domestic", "international"]
    origin: str = Field(..., min_length=2, max_length=120)
    destination: str = Field(..., min_length=2, max_length=120)
    destination_country: str | None = Field(None, max_length=80)
    departure_date: date
    return_date: date | None = None
    airline: str | None = Field(None, max_length=120)
    booking_reference: str | None = Field(None, max_length=40)
    purpose: str | None = Field(None, max_length=4000)
    notes: str | None = Field(None, max_length=4000)

    @model_validator(mode="after")
    def check(self):
        if self.return_date and self.return_date < self.departure_date:
            raise ValueError("Return cannot be before departure")
        if self.travel_type == "international" and not (self.destination_country or "").strip():
            raise ValueError("International travel needs the destination country")
        if self.travel_type == "domestic":
            self.destination_country = "Philippines"
        if self.booking_reference:
            self.booking_reference = self.booking_reference.strip().upper()
        return self


@router.get("/flights")
async def list_flights(
    principal: Staff, session: Session, state: Literal["upcoming", "past", "all"] = "upcoming", q: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
) -> dict:
    stmt = select(FlightBooking).where(FlightBooking.company_id.in_(principal.company_ids))
    today = date.today()
    if state == "upcoming":
        stmt = stmt.where(FlightBooking.status.notin_(["completed", "cancelled"]), or_(FlightBooking.return_date >= today, FlightBooking.departure_date >= today))
    elif state == "past":
        stmt = stmt.where(or_(FlightBooking.status.in_(["completed", "cancelled"]), (FlightBooking.departure_date < today) & or_(FlightBooking.return_date.is_(None), FlightBooking.return_date < today)))
    if q:
        like = f"%{q}%"
        stmt = stmt.join(Employee, Employee.id == FlightBooking.passenger_id).where(or_(FlightBooking.destination.ilike(like), FlightBooking.booking_reference.ilike(like), FlightBooking.reference.ilike(like), Employee.name.ilike(like)))
    rows = list((await session.execute(stmt.order_by(FlightBooking.departure_date.asc() if state == "upcoming" else FlightBooking.departure_date.desc()))).scalars())
    page_rows = rows[(page - 1) * page_size : page * page_size]
    return {"items": [await flight_out(session, f) for f in page_rows], "total": len(rows), "page": page, "page_size": page_size}


@router.post("/flights", status_code=201)
async def create_flight(body: FlightIn, principal: Staff, session: Session) -> dict:
    cid = await company_for(session, principal, body.company_id)
    await employee_in(session, body.passenger_id, cid, "passenger_id")
    if body.departure_date < date.today():
        raise bad_request({"message": "Departure is in the past", "fields": {"departure_date": "In the past"}})
    f = FlightBooking(reference=await next_reference(session, "TRV"), company_id=cid, created_by_id=principal.id, checklist={}, **body.model_dump(exclude={"company_id"}))
    session.add(f)
    await session.flush()
    await log(session, principal, "flight_create", "flight", f, {"route": f"{f.origin}–{f.destination}", "departure": day(f.departure_date)})
    await session.commit()
    return await flight_out(session, await scoped(session, FlightBooking, f.id, principal))


@router.get("/flights/{flight_id}")
async def get_flight(flight_id: int, principal: Staff, session: Session) -> dict:
    f = await scoped(session, FlightBooking, flight_id, principal)
    atts = (await session.execute(select(Attachment).where(Attachment.owner_type == "flight", Attachment.owner_id == f.id))).scalars()
    hotels = (await session.execute(select(HotelReservation).where(HotelReservation.flight_id == f.id))).scalars()
    return {**await flight_out(session, f), "attachments": [attachment_out(a) for a in atts], "hotels": [hotel_out(h) for h in hotels]}


@router.patch("/flights/{flight_id}")
async def update_flight(flight_id: int, body: FlightIn, principal: Staff, session: Session) -> dict:
    f = await scoped(session, FlightBooking, flight_id, principal)
    if f.status in ("completed", "cancelled"):
        raise conflict("Closed bookings cannot be edited")
    await employee_in(session, body.passenger_id, f.company_id, "passenger_id")
    changed = {}
    for k, v in body.model_dump(exclude={"company_id"}).items():
        if getattr(f, k) != v:
            changed[k] = str(v)
            setattr(f, k, v)
    await log(session, principal, "flight_update", "flight", f, changed)
    await session.commit()
    return await flight_out(session, await scoped(session, FlightBooking, f.id, principal))


class ChecklistIn(BaseModel):
    done: bool


@router.put("/flights/{flight_id}/checklist/{req_id}")
async def tick(flight_id: int, req_id: int, body: ChecklistIn, principal: Staff, session: Session) -> dict:
    f = await scoped(session, FlightBooking, flight_id, principal, lock=True)  # concurrent ticks must not overwrite each other
    if req_id not in {r.id for r in await requirements_for(session, f.travel_type, f.destination_country)}:
        raise not_found("That requirement does not apply to this trip")
    cl = dict(f.checklist or {})
    cl[str(req_id)] = {"done": body.done, "by": principal.id, "at": now().isoformat()}
    f.checklist = cl
    await log(session, principal, "checklist", "flight", f, {"requirement": req_id, "done": body.done})
    await session.commit()
    return await flight_out(session, await scoped(session, FlightBooking, f.id, principal))


class FlightStatusIn(BaseModel):
    status: Literal["booked", "ticketed", "completed", "cancelled"]
    booking_reference: str | None = Field(None, max_length=40)
    airline: str | None = Field(None, max_length=120)
    reason: str | None = Field(None, max_length=2000)


@router.post("/flights/{flight_id}/status")
async def flight_status(flight_id: int, body: FlightStatusIn, principal: Staff, session: Session) -> dict:
    f = await scoped(session, FlightBooking, flight_id, principal)
    if body.status not in FLIGHT_FLOW[f.status]:
        raise conflict(f"A {f.status} booking cannot become {body.status}")
    if body.status == "booked":
        ref = (body.booking_reference or f.booking_reference or "").strip().upper()
        if not ref:
            raise bad_request({"message": "Enter the airline booking reference (PNR)", "fields": {"booking_reference": "Required"}})
        f.booking_reference = ref
        f.airline = body.airline or f.airline
    if body.status == "ticketed":
        out = await flight_out(session, f)
        if out["checklist_done"] < out["checklist_total"]:
            missing = [i["name"] for i in out["checklist"] if not i["done"]]
            raise conflict(f"Complete the travel requirements first: {', '.join(missing)}")
    if body.status == "cancelled" and not (body.reason or "").strip():
        raise bad_request({"message": "Give a reason", "fields": {"reason": "Required"}})
    prev = f.status
    f.status = body.status
    if body.reason:
        f.notes = ((f.notes or "") + f"\n{body.status}: {body.reason}").strip()
    await log(session, principal, f"flight_{body.status}", "flight", f, {"from": prev, "booking_reference": f.booking_reference, "reason": body.reason})
    if body.status in ("booked", "ticketed", "cancelled"):
        await notify(
            session, {f.passenger_id}, kind="approval_decision", title=f"Flight {body.status}: {f.origin} → {f.destination}",
            body=f"{day(f.departure_date)}{' · ' + f.booking_reference if f.booking_reference else ''}", link="/me/travel", skip=principal.id,
        )
    await session.commit()
    return await flight_out(session, await scoped(session, FlightBooking, f.id, principal))


# ------------------------------------------------------------------ hotels


class HotelIn(BaseModel):
    company_id: int | None = None
    guest_id: int
    flight_id: int | None = None
    hotel: str = Field(..., min_length=1, max_length=200)
    destination: str = Field(..., min_length=1, max_length=120)
    check_in: date
    check_out: date
    booking_reference: str | None = Field(None, max_length=60)
    cost_reference: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=4000)

    @model_validator(mode="after")
    def nights(self):
        if self.check_out <= self.check_in:
            raise ValueError("Check-out must be after check-in")
        return self


@router.get("/hotels")
async def list_hotels(principal: Staff, session: Session, state: Literal["upcoming", "past", "all"] = "upcoming") -> list[dict]:
    stmt = select(HotelReservation).where(HotelReservation.company_id.in_(principal.company_ids))
    if state == "upcoming":
        stmt = stmt.where(HotelReservation.status.notin_(["completed", "cancelled"]), HotelReservation.check_out >= date.today())
    elif state == "past":
        stmt = stmt.where(or_(HotelReservation.status.in_(["completed", "cancelled"]), HotelReservation.check_out < date.today()))
    rows = (await session.execute(stmt.order_by(HotelReservation.check_in))).scalars()
    return [hotel_out(h) for h in rows]


@router.post("/hotels", status_code=201)
async def create_hotel(body: HotelIn, principal: Staff, session: Session) -> dict:
    cid = await company_for(session, principal, body.company_id)
    await employee_in(session, body.guest_id, cid, "guest_id")
    if body.flight_id:
        f = await scoped(session, FlightBooking, body.flight_id, principal)
        if f.company_id != cid:
            raise bad_request({"message": "That trip belongs to another company", "fields": {"flight_id": "Wrong company"}})
    h = HotelReservation(reference=await next_reference(session, "HTL"), company_id=cid, created_by_id=principal.id, **body.model_dump(exclude={"company_id"}))
    session.add(h)
    await session.flush()
    await log(session, principal, "hotel_create", "hotel", h, {"hotel": h.hotel, "check_in": day(h.check_in)})
    await session.commit()
    return hotel_out(await scoped(session, HotelReservation, h.id, principal))


class HotelStatusIn(BaseModel):
    status: Literal["booked", "completed", "cancelled"]
    booking_reference: str | None = Field(None, max_length=60)
    reason: str | None = Field(None, max_length=2000)


@router.post("/hotels/{hotel_id}/status")
async def hotel_status(hotel_id: int, body: HotelStatusIn, principal: Staff, session: Session) -> dict:
    h = await scoped(session, HotelReservation, hotel_id, principal)
    if body.status not in HOTEL_FLOW[h.status]:
        raise conflict(f"A {h.status} reservation cannot become {body.status}")
    if body.status == "booked":
        if not (body.booking_reference or h.booking_reference):
            raise bad_request({"message": "Enter the hotel confirmation number", "fields": {"booking_reference": "Required"}})
        h.booking_reference = body.booking_reference or h.booking_reference
    if body.status == "cancelled" and not (body.reason or "").strip():
        raise bad_request({"message": "Give a reason", "fields": {"reason": "Required"}})
    h.status = body.status
    await log(session, principal, f"hotel_{body.status}", "hotel", h, {"reason": body.reason})
    if body.status in ("booked", "cancelled"):
        await notify(session, {h.guest_id}, kind="approval_decision", title=f"Hotel {body.status}: {h.hotel}", body=f"{day(h.check_in)} – {day(h.check_out)}", link="/me/travel", skip=principal.id)
    await session.commit()
    return hotel_out(await scoped(session, HotelReservation, h.id, principal))


# ------------------------------------------------------------------ passports & visas (sensitive)


class DocIn(BaseModel):
    company_id: int | None = None
    employee_id: int
    doc_type: Literal["passport", "visa"]
    holder_kind: Literal["employee", "expat"] = "employee"
    visa_type: str | None = Field(None, max_length=80)
    country: str = Field(..., min_length=2, max_length=80)
    number_last4: str | None = Field(None, description="Last four characters only")
    application_date: date | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    renewal_date: date | None = None
    status: Literal["applied", "active", "for_renewal", "expired", "cancelled"] = "active"
    responsible_id: int | None = None
    notes: str | None = Field(None, max_length=4000)

    @field_validator("number_last4")
    @classmethod
    def last4(cls, v):
        if v is None or not v.strip():
            return None
        v = re.sub(r"[^0-9A-Za-z]", "", v).upper()
        if len(v) != 4:
            raise ValueError("Enter only the last 4 characters of the document number")
        return v

    @model_validator(mode="after")
    def check(self):
        if self.doc_type == "visa" and not (self.visa_type or "").strip():
            raise ValueError("Enter the visa type")
        if self.issue_date and self.expiry_date and self.expiry_date <= self.issue_date:
            raise ValueError("Expiry must be after the issue date")
        if self.status != "applied" and not self.expiry_date:
            raise ValueError("Enter the expiry date")
        return self


class DocPatch(DocIn):
    version: int


def docs_guard(principal: Principal):
    if not can_see_documents(principal):
        raise forbidden("Passport and visa records need explicit authorization")


@router.get("/documents")
async def list_documents(
    principal: Staff, session: Session, doc_type: str | None = None, holder_kind: str | None = None,
    expiring_within: int | None = Query(None, ge=0, le=730), q: str | None = None,
) -> list[dict]:
    docs_guard(principal)
    stmt = select(TravelDocument).where(TravelDocument.company_id.in_(principal.company_ids))
    if doc_type:
        stmt = stmt.where(TravelDocument.doc_type == doc_type)
    if holder_kind:
        stmt = stmt.where(TravelDocument.holder_kind == holder_kind)
    if q:
        stmt = stmt.join(Employee, Employee.id == TravelDocument.employee_id).where(or_(Employee.name.ilike(f"%{q}%"), TravelDocument.country.ilike(f"%{q}%")))
    rows = list((await session.execute(stmt.order_by(TravelDocument.expiry_date.is_(None), TravelDocument.expiry_date))).scalars())
    if expiring_within is not None:
        rows = [d for d in rows if (n := days_until(d.expiry_date)) is not None and n <= expiring_within and d.status != "cancelled"]
    await audit(session, actor_id=principal.id, action="travel.documents_view", entity_type="travel_document", data={"count": len(rows), "doc_type": doc_type, "holder_kind": holder_kind})
    await session.commit()
    return [doc_out(d) for d in rows]


@router.post("/documents", status_code=201)
async def create_document(body: DocIn, principal: Staff, session: Session) -> dict:
    docs_guard(principal)
    cid = await company_for(session, principal, body.company_id)
    await employee_in(session, body.employee_id, cid, "employee_id")
    await employee_in(session, body.responsible_id, cid, "responsible_id")
    d = TravelDocument(reference=await next_reference(session, "TRD"), company_id=cid, **body.model_dump(exclude={"company_id"}))
    session.add(d)
    await session.flush()
    await log(session, principal, "document_create", "travel_document", d, {"doc_type": d.doc_type, "holder_kind": d.holder_kind, "country": d.country})
    await session.commit()
    return doc_out(await scoped(session, TravelDocument, d.id, principal))


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int, principal: Staff, session: Session) -> dict:
    docs_guard(principal)
    d = await scoped(session, TravelDocument, doc_id, principal)
    atts = (await session.execute(select(Attachment).where(Attachment.owner_type == "travel_document", Attachment.owner_id == d.id))).scalars()
    await log(session, principal, "document_view", "travel_document", d)
    await session.commit()
    return {**doc_out(d), "attachments": [attachment_out(a) for a in atts]}


@router.patch("/documents/{doc_id}")
async def update_document(doc_id: int, body: DocPatch, principal: Staff, session: Session) -> dict:
    docs_guard(principal)
    d = await scoped(session, TravelDocument, doc_id, principal)
    check_version(d, body.version)
    await employee_in(session, body.employee_id, d.company_id, "employee_id")
    await employee_in(session, body.responsible_id, d.company_id, "responsible_id")
    changed = []
    for k, v in body.model_dump(exclude={"company_id", "version"}).items():
        if getattr(d, k) != v:
            changed.append(k)
            setattr(d, k, v)
    d.version += 1
    # Field names only: the audit trail must not copy sensitive values.
    await log(session, principal, "document_update", "travel_document", d, {"changed": changed})
    await session.commit()
    return doc_out(await scoped(session, TravelDocument, d.id, principal))


# ------------------------------------------------------------------ employee view


@router.get("/me")
async def my_travel(principal: CurrentPrincipal, session: Session) -> dict:
    flights = (await session.execute(select(FlightBooking).where(FlightBooking.passenger_id == principal.id).order_by(FlightBooking.departure_date.desc()))).scalars()
    hotels = (await session.execute(select(HotelReservation).where(HotelReservation.guest_id == principal.id).order_by(HotelReservation.check_in.desc()))).scalars()
    docs = (await session.execute(select(TravelDocument).where(TravelDocument.employee_id == principal.id).order_by(TravelDocument.expiry_date))).scalars()
    return {
        "flights": [await flight_out(session, f) for f in flights],
        "hotels": [hotel_out(h) for h in hotels],
        "documents": [doc_out(d) for d in docs],
    }


# ------------------------------------------------------------------ reminders (sweep)


async def travel_reminders(session) -> int:
    sent = 0
    for d in (await session.execute(select(TravelDocument).where(TravelDocument.status.in_(["active", "for_renewal"])))).scalars().all():
        n = days_until(d.expiry_date)
        if n is None:
            continue
        if n < 0 and d.status != "expired":
            d.status = "expired"
        elif 0 <= n <= 90 and d.status == "active":
            d.status = "for_renewal"
        if n > 90:
            continue
        band = 0 if n <= 0 else 7 if n <= 7 else 30 if n <= 30 else 90
        label = "Passport" if d.doc_type == "passport" else f"{d.visa_type or 'Visa'}"
        when = "has expired" if n < 0 else "expires today" if n == 0 else f"expires in {n} days"
        # Recipients: Admins, the responsible person, and the holder. No document number in the message.
        await notify(
            session, await admin_ids(session, d.company_id) | ({d.responsible_id} if d.responsible_id else set()), kind="renewal_warning",
            title=f"{label} {when}: {d.employee.name}", body=f"{d.country} · {d.expiry_date.isoformat()}", link="/travel/renewals",
            dedupe_key=f"trd:{d.id}:{d.expiry_date.isoformat()}:{band}",
        )
        await notify(
            session, {d.employee_id}, kind="renewal_warning", title=f"Your {label.lower()} {when}", body=f"{d.country} · {d.expiry_date.isoformat()}",
            link="/me/travel", dedupe_key=f"trd-self:{d.id}:{d.expiry_date.isoformat()}:{band}",
        )
        sent += 1
    soon = date.today() + timedelta(days=3)
    for f in (await session.execute(select(FlightBooking).where(FlightBooking.status.in_(["requested", "booked"]), FlightBooking.departure_date <= soon, FlightBooking.departure_date >= date.today()))).scalars().all():
        await notify(
            session, {f.created_by_id}, kind="due_date_reminder", title=f"Departs in {days_until(f.departure_date)} days, not ticketed: {f.passenger.name}",
            body=f"{f.origin} → {f.destination}", link=f"/flight/{f.id}", dedupe_key=f"flt-unticketed:{f.id}",
        )
        sent += 1
    return sent
