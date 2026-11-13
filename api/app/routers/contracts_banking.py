"""Phase 2.7 — lease & staff-house contracts, lessors, rental monitoring; corporate cards and banking cases."""

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import or_, select

from ..core import admin_ids, audit, bad_request, conflict, forbidden, next_reference, not_found, notify, now
from ..models import Attachment, Employee
from ..models_ops3 import BANK_CASE_TYPES, CONTRACT_TYPES, BankingCase, Contract, ContractEvent, CorporateCard, Lessor, RentPayment
from ..ops_common import check_version, company_for, count, day, days_until, employee_in, money, scoped
from ..security import Principal, Session, Staff
from ..serialize import attachment_out, iso, person

contracts = APIRouter(prefix="/api/v1/contracts", tags=["contracts"])
banking = APIRouter(prefix="/api/v1/banking", tags=["banking"])

TYPE_LABEL = {"office_lease": "Office lease", "staff_house": "Staff house", "other": "Other contract"}


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    for dd in (d.day, 30, 29, 28):
        try:
            return date(y, m, dd)
        except ValueError:
            continue
    return d


def contract_status(c: Contract) -> str:
    if c.status in ("renewed", "terminated"):
        return c.status
    n = days_until(c.end_date)
    if n is not None and n < 0:
        return "expired"
    if n is not None and n <= (c.renewal_notice_days or 60):
        return "for_renewal"
    return "active"


def lessor_out(l: Lessor) -> dict:
    return {"id": l.id, "company": {"id": l.company.id, "code": l.company.code}, "name": l.name, "contact_person": l.contact_person, "phone": l.phone, "email": l.email, "address": l.address, "notes": l.notes}


def contract_out(c: Contract) -> dict:
    return {
        "id": c.id, "reference": c.reference, "company": {"id": c.company.id, "code": c.company.code, "name": c.company.name}, "contract_type": c.contract_type,
        "type_label": TYPE_LABEL.get(c.contract_type, c.contract_type), "title": c.title, "property_name": c.property_name, "location": c.location,
        "lessor": {"id": c.lessor.id, "name": c.lessor.name} if c.lessor else None, "start_date": day(c.start_date), "end_date": day(c.end_date),
        "covered_year": f"{c.start_date.year}" + (f"–{c.end_date.year}" if c.end_date.year != c.start_date.year else ""),
        "monthly_rent_php": money(c.monthly_rent_php), "deposit_php": money(c.deposit_php), "rent_due_day": c.rent_due_day, "renewal_notice_days": c.renewal_notice_days,
        "renewal_due": day(c.end_date - timedelta(days=c.renewal_notice_days or 60)), "days_left": days_until(c.end_date), "occupants": c.occupants,
        "status": c.status, "external_reference": c.external_reference, "responsible": person(c.responsible), "notes": c.notes,
        "renewed_from_id": c.renewed_from_id, "version": c.version, "updated_at": iso(c.updated_at),
    }


def rent_out(r: RentPayment, c: Contract | None = None) -> dict:
    return {
        "id": r.id, "reference": r.reference, "contract": {"id": c.id, "reference": c.reference, "title": c.title, "lessor": c.lessor.name if c.lessor else None} if c else {"id": r.contract_id},
        "period": r.period, "amount_php": money(r.amount_php), "due_date": day(r.due_date), "days_left": days_until(r.due_date), "status": r.status,
        "finance_reference": r.finance_reference, "sent_at": iso(r.sent_at), "paid_at": iso(r.paid_at),
    }


async def clog(session, principal: Principal | None, c: Contract, type_: str, message: str | None = None, data: dict | None = None):
    session.add(ContractEvent(contract_id=c.id, type=type_, message=message, actor_id=principal.id if principal else None))
    await audit(session, actor_id=principal.id if principal else None, action=f"contracts.{type_}", entity_type="contract", entity_id=c.id, entity_ref=c.reference, company_id=c.company_id, data=data or {"message": message})


# ------------------------------------------------------------------ lessors


class LessorIn(BaseModel):
    company_id: int | None = None
    name: str = Field(..., min_length=1, max_length=200)
    contact_person: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=200)
    address: str | None = Field(None, max_length=400)
    notes: str | None = Field(None, max_length=4000)

    @field_validator("email")
    @classmethod
    def mail(cls, v):
        if v and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v.strip()):
            raise ValueError("Enter a valid email address")
        return v.strip() if v else v


@contracts.get("/lessors")
async def list_lessors(principal: Staff, session: Session, q: str | None = None) -> list[dict]:
    stmt = select(Lessor).where(Lessor.company_id.in_(principal.company_ids))
    if q:
        stmt = stmt.where(Lessor.name.ilike(f"%{q}%"))
    rows = (await session.execute(stmt.order_by(Lessor.name))).scalars().all()
    out = []
    for l in rows:
        cs = (await session.execute(select(Contract).where(Contract.lessor_id == l.id, Contract.status.notin_(["renewed", "terminated"])))).scalars().all()
        out.append({**lessor_out(l), "active_contracts": len(cs), "monthly_rent_php": money(sum((c.monthly_rent_php or Decimal(0) for c in cs), Decimal(0))), "sites": [c.property_name or c.title for c in cs]})
    return out


@contracts.post("/lessors", status_code=201)
async def create_lessor(body: LessorIn, principal: Staff, session: Session) -> dict:
    cid = await company_for(session, principal, body.company_id)
    dup = await session.execute(select(Lessor.id).where(Lessor.company_id == cid, Lessor.name.ilike(body.name.strip())))
    if dup.first():
        raise conflict(f"{body.name} is already a lessor")
    l = Lessor(company_id=cid, **body.model_dump(exclude={"company_id"}))
    session.add(l)
    await session.flush()
    await audit(session, actor_id=principal.id, action="contracts.lessor_create", entity_type="lessor", entity_id=l.id, entity_ref=l.name, company_id=cid)
    await session.commit()
    return lessor_out(await scoped(session, Lessor, l.id, principal))


@contracts.patch("/lessors/{lessor_id}")
async def update_lessor(lessor_id: int, body: LessorIn, principal: Staff, session: Session) -> dict:
    l = await scoped(session, Lessor, lessor_id, principal)
    for k, v in body.model_dump(exclude={"company_id"}).items():
        setattr(l, k, v)
    await audit(session, actor_id=principal.id, action="contracts.lessor_update", entity_type="lessor", entity_id=l.id, entity_ref=l.name, company_id=l.company_id)
    await session.commit()
    return lessor_out(await scoped(session, Lessor, l.id, principal))


# ------------------------------------------------------------------ contracts


class ContractIn(BaseModel):
    company_id: int | None = None
    contract_type: Literal["office_lease", "staff_house", "other"]
    title: str = Field(..., min_length=1, max_length=300)
    property_name: str | None = Field(None, max_length=200)
    location: str | None = Field(None, max_length=300)
    lessor_id: int | None = None
    start_date: date
    end_date: date
    monthly_rent_php: Decimal | None = Field(None, ge=0, le=Decimal("999999999"))
    deposit_php: Decimal | None = Field(None, ge=0, le=Decimal("999999999"))
    rent_due_day: int | None = Field(None, ge=1, le=31)
    renewal_notice_days: int = Field(60, ge=0, le=365)
    occupants: str | None = Field(None, max_length=4000)
    external_reference: str | None = Field(None, max_length=120)
    responsible_id: int | None = None
    notes: str | None = Field(None, max_length=4000)

    @model_validator(mode="after")
    def dates(self):
        if self.end_date <= self.start_date:
            raise ValueError("End date must be after the start date")
        return self


class ContractPatch(ContractIn):
    version: int


async def lessor_in(session, lessor_id: int | None, company_id: int):
    if lessor_id is None:
        return None
    l = await session.get(Lessor, lessor_id)
    if l is None or l.company_id != company_id:
        raise bad_request({"message": "That lessor belongs to another company", "fields": {"lessor_id": "Wrong company"}})
    return l


@contracts.get("")
async def list_contracts(
    principal: Staff, session: Session, contract_type: str | None = None, status: list[str] = Query(default_factory=list),
    due_within: int | None = Query(None, ge=0, le=730), q: str | None = None, include_history: bool = False,
) -> dict:
    stmt = select(Contract).where(Contract.company_id.in_(principal.company_ids))
    if contract_type:
        stmt = stmt.where(Contract.contract_type == contract_type)
    if status:
        stmt = stmt.where(Contract.status.in_(status))
    elif not include_history:
        stmt = stmt.where(Contract.status.notin_(["renewed"]))
    if q:
        like = f"%{q}%"
        stmt = stmt.outerjoin(Lessor, Lessor.id == Contract.lessor_id).where(or_(Contract.title.ilike(like), Contract.reference.ilike(like), Contract.property_name.ilike(like), Lessor.name.ilike(like)))
    rows = list((await session.execute(stmt.order_by(Contract.end_date))).scalars())
    if due_within is not None:
        rows = [c for c in rows if c.status in ("active", "for_renewal", "expired") and (days_until(c.end_date) or 0) <= due_within]
    live = [c for c in (await session.execute(select(Contract).where(Contract.company_id.in_(principal.company_ids), Contract.status.in_(["active", "for_renewal", "expired"])))).scalars()]
    summary = {
        "active": sum(1 for c in live if c.status == "active"), "for_renewal": sum(1 for c in live if c.status == "for_renewal"), "expired": sum(1 for c in live if c.status == "expired"),
        "monthly_rent_php": money(sum((c.monthly_rent_php or Decimal(0) for c in live if c.status != "expired"), Decimal(0))),
    }
    return {"items": [contract_out(c) for c in rows], "total": len(rows), "summary": summary}


@contracts.post("", status_code=201)
async def create_contract(body: ContractIn, principal: Staff, session: Session) -> dict:
    cid = await company_for(session, principal, body.company_id)
    await lessor_in(session, body.lessor_id, cid)
    await employee_in(session, body.responsible_id, cid, "responsible_id")
    c = Contract(reference=await next_reference(session, "CON"), company_id=cid, status="active", **body.model_dump(exclude={"company_id"}))
    c.status = contract_status(c)
    session.add(c)
    await session.flush()
    await clog(session, principal, c, "created", f"{TYPE_LABEL[c.contract_type]} {day(c.start_date)} to {day(c.end_date)}")
    await session.commit()
    return contract_out(await scoped(session, Contract, c.id, principal))


@contracts.get("/{contract_id}")
async def get_contract(contract_id: int, principal: Staff, session: Session) -> dict:
    c = await scoped(session, Contract, contract_id, principal)
    events = (await session.execute(select(ContractEvent).where(ContractEvent.contract_id == c.id).order_by(ContractEvent.at.desc(), ContractEvent.id.desc()))).scalars()
    rents = (await session.execute(select(RentPayment).where(RentPayment.contract_id == c.id).order_by(RentPayment.period.desc()))).scalars()
    atts = (await session.execute(select(Attachment).where(Attachment.owner_type == "contract", Attachment.owner_id == c.id))).scalars()
    chain = []
    prev = c.renewed_from_id
    while prev:
        p = await session.get(Contract, prev)
        if p is None:
            break
        chain.append({"id": p.id, "reference": p.reference, "start_date": day(p.start_date), "end_date": day(p.end_date), "monthly_rent_php": money(p.monthly_rent_php)})
        prev = p.renewed_from_id
    nxt = (await session.execute(select(Contract).where(Contract.renewed_from_id == c.id))).scalar_one_or_none()
    return {
        **contract_out(c),
        "events": [{"id": e.id, "type": e.type, "message": e.message, "actor": person(e.actor), "at": iso(e.at)} for e in events],
        "rent_payments": [rent_out(r) for r in rents],
        "attachments": [attachment_out(a) for a in atts],
        "history": chain,
        "renewed_to": {"id": nxt.id, "reference": nxt.reference} if nxt else None,
    }


@contracts.patch("/{contract_id}")
async def update_contract(contract_id: int, body: ContractPatch, principal: Staff, session: Session) -> dict:
    c = await scoped(session, Contract, contract_id, principal)
    check_version(c, body.version)
    if c.status in ("renewed", "terminated"):
        raise conflict("Renewed or terminated contracts are history and cannot be edited")
    await lessor_in(session, body.lessor_id, c.company_id)
    await employee_in(session, body.responsible_id, c.company_id, "responsible_id")
    changed = {}
    for k, v in body.model_dump(exclude={"company_id", "version"}).items():
        if getattr(c, k) != v:
            changed[k] = str(v)
            setattr(c, k, v)
    c.status = contract_status(c)
    c.version += 1
    if changed:
        await clog(session, principal, c, "updated", ", ".join(changed), changed)
    await session.commit()
    return contract_out(await scoped(session, Contract, c.id, principal))


class RenewIn(BaseModel):
    start_date: date
    end_date: date
    monthly_rent_php: Decimal | None = Field(None, ge=0, le=Decimal("999999999"))
    notes: str | None = Field(None, max_length=4000)
    external_reference: str | None = Field(None, max_length=120)

    @model_validator(mode="after")
    def dates(self):
        if self.end_date <= self.start_date:
            raise ValueError("End date must be after the start date")
        return self


@contracts.post("/{contract_id}/renew", status_code=201)
async def renew_contract(contract_id: int, body: RenewIn, principal: Staff, session: Session) -> dict:
    c = await scoped(session, Contract, contract_id, principal)
    if c.status in ("renewed", "terminated"):
        raise conflict("This contract was already renewed or terminated")
    if body.start_date < c.start_date:
        raise bad_request({"message": "The renewal cannot start before the current term", "fields": {"start_date": "Too early"}})
    n = Contract(
        reference=await next_reference(session, "CON"), company_id=c.company_id, contract_type=c.contract_type, title=c.title, property_name=c.property_name,
        location=c.location, lessor_id=c.lessor_id, start_date=body.start_date, end_date=body.end_date,
        monthly_rent_php=body.monthly_rent_php if body.monthly_rent_php is not None else c.monthly_rent_php, deposit_php=c.deposit_php,
        rent_due_day=c.rent_due_day, renewal_notice_days=c.renewal_notice_days, occupants=c.occupants, external_reference=body.external_reference or c.external_reference,
        responsible_id=c.responsible_id, notes=body.notes, renewed_from_id=c.id, status="active",
    )
    n.status = contract_status(n)
    session.add(n)
    c.status = "renewed"
    c.version += 1
    await session.flush()
    change = ""
    if c.monthly_rent_php is not None and n.monthly_rent_php is not None and n.monthly_rent_php != c.monthly_rent_php:
        change = f"; rent {money(c.monthly_rent_php)} → {money(n.monthly_rent_php)}"
    await clog(session, principal, c, "renewed", f"Renewed as {n.reference}{change}")
    await clog(session, principal, n, "created", f"Renewal of {c.reference}: {day(n.start_date)} to {day(n.end_date)}{change}")
    await session.commit()
    return contract_out(await scoped(session, Contract, n.id, principal))


class TerminateIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)
    effective_date: date | None = None


@contracts.post("/{contract_id}/terminate")
async def terminate(contract_id: int, body: TerminateIn, principal: Staff, session: Session) -> dict:
    if not principal.is_admin:
        raise forbidden("Only Admin can terminate a contract")
    c = await scoped(session, Contract, contract_id, principal)
    if c.status in ("renewed", "terminated"):
        raise conflict("This contract is already closed")
    c.status = "terminated"
    if body.effective_date and body.effective_date < c.end_date:
        c.end_date = body.effective_date
    c.version += 1
    await clog(session, principal, c, "terminated", body.reason)
    await session.commit()
    return contract_out(await scoped(session, Contract, c.id, principal))


# ---- rental monitoring


class PrepareIn(BaseModel):
    period: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


@contracts.get("/rent/payments")
async def rent_payments(principal: Staff, session: Session, period: str | None = None, status: list[str] = Query(default_factory=list)) -> list[dict]:
    stmt = select(RentPayment).where(RentPayment.company_id.in_(principal.company_ids))
    if period:
        stmt = stmt.where(RentPayment.period == period)
    if status:
        stmt = stmt.where(RentPayment.status.in_(status))
    rows = (await session.execute(stmt.order_by(RentPayment.due_date))).scalars().all()
    cs = {c.id: c for c in (await session.execute(select(Contract).where(Contract.id.in_([r.contract_id for r in rows] or [0])))).scalars()}
    return [rent_out(r, cs.get(r.contract_id)) for r in rows]


@contracts.post("/rent/prepare")
async def prepare_month(body: PrepareIn, principal: Staff, session: Session) -> dict:
    """Creates the month's rent lines for every active contract with a monthly rent (idempotent)."""
    y, m = map(int, body.period.split("-"))
    first, last = date(y, m, 1), add_months(date(y, m, 1), 1) - timedelta(days=1)
    created = 0
    rows = (await session.execute(select(Contract).where(Contract.company_id.in_(principal.company_ids), Contract.status.in_(["active", "for_renewal"]), Contract.monthly_rent_php.is_not(None)))).scalars().all()
    for c in rows:
        if c.start_date > last or c.end_date < first:
            continue
        exists = (await session.execute(select(RentPayment.id).where(RentPayment.contract_id == c.id, RentPayment.period == body.period))).first()
        if exists:
            continue
        dd = min(c.rent_due_day or 1, last.day)
        session.add(RentPayment(reference=await next_reference(session, "RNT"), contract_id=c.id, company_id=c.company_id, period=body.period, amount_php=c.monthly_rent_php, due_date=date(y, m, dd), created_by_id=principal.id))
        created += 1
    await audit(session, actor_id=principal.id, action="contracts.rent_prepare", entity_type="rent", entity_ref=body.period, data={"created": created})
    await session.commit()
    return {"created": created}


class RentAction(BaseModel):
    finance_reference: str | None = Field(None, max_length=120)
    reason: str | None = Field(None, max_length=2000)


RENT_FLOW = {"send": ({"due"}, "sent"), "paid": ({"sent"}, "paid"), "cancel": ({"due", "sent"}, "cancelled")}


@contracts.post("/rent/payments/{payment_id}/{action}")
async def rent_action(payment_id: int, action: str, body: RentAction, principal: Staff, session: Session) -> dict:
    if action not in RENT_FLOW:
        raise not_found()
    r = await scoped(session, RentPayment, payment_id, principal)
    allowed, to = RENT_FLOW[action]
    if r.status not in allowed:
        raise conflict(f"A {r.status} rent line cannot be marked {to}")
    if action == "paid" and not (body.finance_reference or "").strip():
        raise bad_request({"message": "Enter Finance's payment reference", "fields": {"finance_reference": "Required"}})
    if action == "cancel" and not (body.reason or "").strip():
        raise bad_request({"message": "Give a reason", "fields": {"reason": "Required"}})
    r.status = to
    if action == "send":
        r.sent_at = now()
    if action == "paid":
        r.paid_at = now()
        r.finance_reference = body.finance_reference.strip()
    c = await session.get(Contract, r.contract_id)
    await clog(session, principal, c, f"rent_{to}", f"{r.period} {money(r.amount_php)}" + (f" · {r.finance_reference}" if r.finance_reference else "") + (f" · {body.reason}" if body.reason else ""))
    await session.commit()
    return rent_out(r, c)


# ------------------------------------------------------------------ banking (restricted)


def bank_guard(p: Principal):
    if not (p.is_admin or (p.is_staff and p.delegated("banking"))):
        raise forbidden("Banking records need explicit authorization")


def no_secrets(v: str | None) -> str | None:
    """Notes must never carry card numbers, CVV or PINs."""
    if v and re.search(r"\b\d{12,19}\b|\bcvv\b|\bcvc\b|\bpin\b", v, re.I):
        raise ValueError("Do not record card numbers, CVV or PINs in notes")
    return v


def last4(v: str | None, field: str) -> str | None:
    if v is None or not str(v).strip():
        return None
    digits = re.sub(r"\D", "", str(v))
    if len(digits) != 4:
        raise ValueError(f"Enter only the last 4 digits of the {field}")
    return digits


def card_out(c: CorporateCard) -> dict:
    exp = date(c.expiry_year, c.expiry_month, 1)
    end = add_months(exp, 1) - timedelta(days=1)
    return {
        "id": c.id, "reference": c.reference, "company": {"id": c.company.id, "code": c.company.code}, "bank": c.bank, "card_type": c.card_type,
        "card_masked": f"•••• {c.card_last4}", "custodian": person(c.custodian), "expiry": f"{c.expiry_month:02d}/{c.expiry_year}", "expiry_date": day(end),
        "days_to_expiry": days_until(end), "credit_limit_php": money(c.credit_limit_php), "status": c.status, "notes": c.notes,
    }


DEFAULT_REQUIREMENTS = {
    "account_application": ["Board resolution / Secretary's certificate", "SEC registration and articles", "Latest GIS", "Valid IDs of authorized signatories", "Specimen signature cards", "BIR Certificate of Registration", "Mayor's permit"],
    "card_request": ["Card application form", "Approval memo", "Custodian's valid ID", "Credit limit approval"],
    "card_renewal": ["Renewal or replacement request", "Custodian confirmed", "Old card surrendered or destroyed"],
    "bank_renewal": ["Updated signatory documents", "Latest GIS", "KYC update form"],
    "documentation": [],
    "finance_coordination": [],
}
CASE_LABEL = {"card_request": "Corporate card request", "card_renewal": "Card renewal", "account_application": "Bank account application", "documentation": "Bank documentation", "bank_renewal": "Bank renewal", "finance_coordination": "Finance coordination"}


def case_out(b: BankingCase) -> dict:
    reqs = b.requirements or []
    return {
        "id": b.id, "reference": b.reference, "company": {"id": b.company.id, "code": b.company.code}, "bank": b.bank, "case_type": b.case_type,
        "type_label": CASE_LABEL.get(b.case_type, b.case_type), "subject": b.subject, "account_masked": f"•••• {b.account_last4}" if b.account_last4 else None,
        "card": card_out(b.card) if b.card else None, "responsible": person(b.responsible), "application_date": day(b.application_date), "renewal_date": day(b.renewal_date),
        "days_to_renewal": days_until(b.renewal_date), "requirements": reqs, "requirements_done": sum(1 for r in reqs if r.get("done")), "status": b.status,
        "finance_status": b.finance_status, "finance_reference": b.finance_reference, "notes": b.notes, "updated_at": iso(b.updated_at),
    }


async def blog(session, principal: Principal, rec, action: str, data: dict | None = None):
    await audit(session, actor_id=principal.id, action=f"banking.{action}", entity_type="banking", entity_id=rec.id, entity_ref=rec.reference, company_id=rec.company_id, data=data or {})


class CardIn(BaseModel):
    company_id: int | None = None
    bank: str = Field(..., min_length=1, max_length=120)
    card_type: Literal["credit", "debit", "prepaid"] = "credit"
    card_last4: str
    custodian_id: int
    expiry_month: int = Field(..., ge=1, le=12)
    expiry_year: int = Field(..., ge=2000, le=2100)
    credit_limit_php: Decimal | None = Field(None, ge=0, le=Decimal("999999999"))
    status: Literal["active", "blocked", "cancelled", "for_renewal", "expired"] = "active"
    notes: str | None = Field(None, max_length=4000)

    @field_validator("card_last4")
    @classmethod
    def mask(cls, v):
        out = last4(v, "card")
        if not out:
            raise ValueError("Enter the last 4 digits of the card")
        return out

    @field_validator("notes")
    @classmethod
    def secrets(cls, v):
        return no_secrets(v)


@banking.get("/cards")
async def list_cards(principal: Staff, session: Session, expiring_within: int | None = Query(None, ge=0, le=730), status: str | None = None) -> list[dict]:
    bank_guard(principal)
    stmt = select(CorporateCard).where(CorporateCard.company_id.in_(principal.company_ids))
    if status:
        stmt = stmt.where(CorporateCard.status == status)
    rows = [card_out(c) for c in (await session.execute(stmt.order_by(CorporateCard.expiry_year, CorporateCard.expiry_month))).scalars()]
    if expiring_within is not None:
        rows = [c for c in rows if c["days_to_expiry"] <= expiring_within and c["status"] not in ("cancelled",)]
    await audit(session, actor_id=principal.id, action="banking.cards_view", entity_type="banking", data={"count": len(rows)})
    await session.commit()
    return rows


@banking.post("/cards", status_code=201)
async def create_card(body: CardIn, principal: Staff, session: Session) -> dict:
    bank_guard(principal)
    cid = await company_for(session, principal, body.company_id)
    await employee_in(session, body.custodian_id, cid, "custodian_id")
    dup = await session.execute(select(CorporateCard.id).where(CorporateCard.bank == body.bank, CorporateCard.card_last4 == body.card_last4, CorporateCard.custodian_id == body.custodian_id))
    if dup.first():
        raise conflict("That card is already registered for this custodian")
    c = CorporateCard(reference=await next_reference(session, "CRD"), company_id=cid, **body.model_dump(exclude={"company_id"}))
    session.add(c)
    await session.flush()
    await blog(session, principal, c, "card_create", {"bank": c.bank, "card": f"****{c.card_last4}"})
    await session.commit()
    return card_out(await scoped(session, CorporateCard, c.id, principal))


class CardPatch(BaseModel):
    custodian_id: int | None = None
    expiry_month: int | None = Field(None, ge=1, le=12)
    expiry_year: int | None = Field(None, ge=2000, le=2100)
    credit_limit_php: Decimal | None = Field(None, ge=0, le=Decimal("999999999"))
    status: Literal["active", "blocked", "cancelled", "for_renewal", "expired"] | None = None
    notes: str | None = Field(None, max_length=4000)

    @field_validator("notes")
    @classmethod
    def secrets(cls, v):
        return no_secrets(v)


@banking.patch("/cards/{card_id}")
async def update_card(card_id: int, body: CardPatch, principal: Staff, session: Session) -> dict:
    bank_guard(principal)
    c = await scoped(session, CorporateCard, card_id, principal)
    changes = body.model_dump(exclude_unset=True)
    if "custodian_id" in changes:
        await employee_in(session, changes["custodian_id"], c.company_id, "custodian_id")
    for k, v in changes.items():
        setattr(c, k, v)
    await blog(session, principal, c, "card_update", {"changed": list(changes)})
    await session.commit()
    return card_out(await scoped(session, CorporateCard, c.id, principal))


class CaseIn(BaseModel):
    company_id: int | None = None
    bank: str = Field(..., min_length=1, max_length=120)
    case_type: str
    subject: str = Field(..., min_length=1, max_length=300)
    account_last4: str | None = None
    card_id: int | None = None
    responsible_id: int | None = None
    application_date: date | None = None
    renewal_date: date | None = None
    requirements: list[str] | None = None
    finance_status: Literal["not_needed", "pending"] = "not_needed"
    notes: str | None = Field(None, max_length=4000)

    @field_validator("case_type")
    @classmethod
    def ct(cls, v):
        if v not in BANK_CASE_TYPES:
            raise ValueError("Choose a case type from the list")
        return v

    @field_validator("account_last4")
    @classmethod
    def mask(cls, v):
        return last4(v, "account")

    @field_validator("notes")
    @classmethod
    def secrets(cls, v):
        return no_secrets(v)


@banking.get("/cases")
async def list_cases(principal: Staff, session: Session, case_type: list[str] = Query(default_factory=list), state: Literal["open", "closed", "all"] = "open", finance: bool = False) -> list[dict]:
    bank_guard(principal)
    stmt = select(BankingCase).where(BankingCase.company_id.in_(principal.company_ids))
    if case_type:
        stmt = stmt.where(BankingCase.case_type.in_(case_type))
    if state == "open":
        stmt = stmt.where(BankingCase.status.in_(["open", "submitted", "approved"]))
    elif state == "closed":
        stmt = stmt.where(BankingCase.status.in_(["completed", "rejected", "cancelled"]))
    if finance:
        stmt = stmt.where(BankingCase.finance_status != "not_needed")
    rows = (await session.execute(stmt.order_by(BankingCase.renewal_date.is_(None), BankingCase.renewal_date, BankingCase.id.desc()))).scalars()
    out = [case_out(b) for b in rows]
    await audit(session, actor_id=principal.id, action="banking.cases_view", entity_type="banking", data={"count": len(out)})
    await session.commit()
    return out


@banking.post("/cases", status_code=201)
async def create_case(body: CaseIn, principal: Staff, session: Session) -> dict:
    bank_guard(principal)
    cid = await company_for(session, principal, body.company_id)
    await employee_in(session, body.responsible_id, cid, "responsible_id")
    if body.card_id:
        card = await scoped(session, CorporateCard, body.card_id, principal)
        if card.company_id != cid:
            raise bad_request({"message": "That card is in another company", "fields": {"card_id": "Wrong company"}})
    names = body.requirements if body.requirements is not None else DEFAULT_REQUIREMENTS.get(body.case_type, [])
    b = BankingCase(
        reference=await next_reference(session, "BNK"), company_id=cid, created_by_id=principal.id, requirements=[{"name": n.strip(), "done": False} for n in names if n.strip()],
        **body.model_dump(exclude={"company_id", "requirements"}),
    )
    session.add(b)
    await session.flush()
    await blog(session, principal, b, "case_create", {"type": b.case_type, "bank": b.bank})
    await session.commit()
    return case_out(await scoped(session, BankingCase, b.id, principal))


@banking.get("/cases/{case_id}")
async def get_case(case_id: int, principal: Staff, session: Session) -> dict:
    bank_guard(principal)
    b = await scoped(session, BankingCase, case_id, principal)
    atts = (await session.execute(select(Attachment).where(Attachment.owner_type == "banking", Attachment.owner_id == b.id))).scalars()
    await blog(session, principal, b, "case_view")
    await session.commit()
    return {**case_out(b), "attachments": [attachment_out(a) for a in atts]}


class TickIn(BaseModel):
    index: int = Field(..., ge=0)
    done: bool


@banking.put("/cases/{case_id}/requirements")
async def tick_requirement(case_id: int, body: TickIn, principal: Staff, session: Session) -> dict:
    bank_guard(principal)
    b = await scoped(session, BankingCase, case_id, principal, lock=True)  # concurrent ticks must not overwrite each other
    reqs = list(b.requirements or [])
    if body.index >= len(reqs):
        raise not_found()
    reqs[body.index] = {**reqs[body.index], "done": body.done}
    b.requirements = reqs
    await blog(session, principal, b, "requirement", {"item": reqs[body.index]["name"], "done": body.done})
    await session.commit()
    return case_out(b)


class CaseAction(BaseModel):
    action: Literal["submit", "approve", "complete", "reject", "cancel", "finance_send", "finance_confirm", "finance_reject"]
    note: str | None = Field(None, max_length=2000)
    finance_reference: str | None = Field(None, max_length=120)


CASE_FLOW = {
    "submit": ({"open"}, "submitted"),
    "approve": ({"submitted"}, "approved"),
    "complete": ({"open", "submitted", "approved"}, "completed"),
    "reject": ({"submitted"}, "rejected"),
    "cancel": ({"open", "submitted", "approved"}, "cancelled"),
}
FIN_FLOW = {"finance_send": ({"pending", "rejected"}, "sent"), "finance_confirm": ({"sent"}, "confirmed"), "finance_reject": ({"sent"}, "rejected")}


@banking.post("/cases/{case_id}/action")
async def case_action(case_id: int, body: CaseAction, principal: Staff, session: Session) -> dict:
    bank_guard(principal)
    b = await scoped(session, BankingCase, case_id, principal)
    note = (body.note or "").strip() or None
    if body.action in CASE_FLOW:
        allowed, to = CASE_FLOW[body.action]
        if b.status not in allowed:
            raise conflict(f"A {b.status} case cannot be marked {to}")
        if body.action == "submit" and any(not r.get("done") for r in (b.requirements or [])):
            missing = [r["name"] for r in b.requirements if not r.get("done")]
            raise conflict(f"Complete the requirements first: {', '.join(missing)}")
        if body.action in ("reject", "cancel") and not note:
            raise bad_request({"message": "Give a reason", "fields": {"note": "Required"}})
        if body.action == "complete" and b.finance_status in ("pending", "sent"):
            raise conflict("Finance has not confirmed yet")
        b.status = to
    else:
        allowed, to = FIN_FLOW[body.action]
        current = b.finance_status if b.finance_status != "not_needed" else "pending"
        if current not in allowed:
            raise conflict(f"Finance status {b.finance_status} cannot become {to}")
        if body.action == "finance_confirm" and not (body.finance_reference or "").strip():
            raise bad_request({"message": "Enter Finance's reference", "fields": {"finance_reference": "Required"}})
        b.finance_status = to
        if body.finance_reference:
            b.finance_reference = body.finance_reference.strip()
    if note:
        b.notes = ((b.notes or "") + f"\n{body.action}: {note}").strip()
    await blog(session, principal, b, body.action, {"note": note, "finance_reference": body.finance_reference})
    await session.commit()
    return case_out(await scoped(session, BankingCase, b.id, principal))


# ------------------------------------------------------------------ reminders (sweep)


async def contracts_banking_reminders(session) -> int:
    sent = 0
    for c in (await session.execute(select(Contract).where(Contract.status.in_(["active", "for_renewal", "expired"])))).scalars().all():
        new = contract_status(c)
        if new != c.status:
            c.status = new
        n = days_until(c.end_date)
        if n is None or n > (c.renewal_notice_days or 60):
            continue
        band = 0 if n <= 0 else 7 if n <= 7 else 30 if n <= 30 else 60
        when = "has ended" if n < 0 else "ends today" if n == 0 else f"ends in {n} days"
        await notify(
            session, await admin_ids(session, c.company_id) | ({c.responsible_id} if c.responsible_id else set()), kind="renewal_warning",
            title=f"{TYPE_LABEL[c.contract_type]} {when}: {c.title}", body=f"{c.reference} · {c.end_date.isoformat()}", link=f"/contract/{c.id}",
            dedupe_key=f"con:{c.id}:{c.end_date.isoformat()}:{band}",
        )
        sent += 1
    for r in (await session.execute(select(RentPayment).where(RentPayment.status == "due", RentPayment.due_date <= date.today() + timedelta(days=5)))).scalars().all():
        await notify(session, await admin_ids(session, r.company_id), kind="payment_status", title=f"Rent due {r.due_date.isoformat()}: {r.reference}", body=f"₱{r.amount_php:,.2f} not yet sent to Finance", link="/contracts/rent", dedupe_key=f"rent-due:{r.id}")
        sent += 1
    for k in (await session.execute(select(CorporateCard).where(CorporateCard.status.in_(["active", "for_renewal"])))).scalars().all():
        out = card_out(k)
        n = out["days_to_expiry"]
        if n is None or n > 60:
            continue
        if k.status == "active":
            k.status = "for_renewal"
        band = 0 if n <= 0 else 30 if n <= 30 else 60
        await notify(session, await admin_ids(session, k.company_id), kind="renewal_warning", title=f"Corporate card expiring {out['expiry']}: {k.bank} {out['card_masked']}", body=f"Custodian {k.custodian.name}", link="/banking/card-renewals", dedupe_key=f"card:{k.id}:{k.expiry_year}{k.expiry_month}:{band}")
        sent += 1
    return sent
