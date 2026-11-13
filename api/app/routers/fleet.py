"""Phase 2.4 — vehicles, registration & insurance, PMS & repairs, fleet cards, RFID, Finance hand-offs."""

import re
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from ..core import admin_ids, audit, bad_request, conflict, forbidden, next_reference, not_found, notify, now
from ..models import Attachment
from ..models_ops import AppSetting, FinanceRequest, FinanceStatus, FleetCard, RfidAccount, Vehicle, VehicleRenewal, VehicleService, VehicleStatus
from ..ops_common import check_version, company_for, count, day, days_until, employee_in, money, scoped
from ..security import AdminOnly, Principal, Session, Staff
from ..serialize import attachment_out, iso, person
from .photos import not_photo, photo_url

router = APIRouter(prefix="/api/v1/fleet", tags=["fleet"])

VEHICLE_TYPES = ["Sedan", "SUV", "Van", "Pickup", "Truck", "Motorcycle", "Other"]
FUEL_TYPES = ["Diesel", "Unleaded", "Premium", "Electric"]
RFID_PROVIDERS = ["Autosweep", "Easytrip"]
DEFAULT_LIMIT_KEY = "fleet.default_card_limit_php"
DEFAULT_LIMIT = Decimal("10000")  # EXECUTIVE-ADMIN.md §9.3: initial configurable example, not a universal limit


def vehicle_out(v: Vehicle) -> dict:
    return {
        "id": v.id,
        "photo": photo_url(v.photo_id),
        "reference": v.reference,
        "label": v.label,
        "company": {"id": v.company.id, "code": v.company.code, "name": v.company.name},
        "vehicle_type": v.vehicle_type,
        "make": v.make,
        "model": v.model,
        "year_model": v.year_model,
        "color": v.color,
        "plate_number": v.plate_number,
        "conduction_sticker": v.conduction_sticker,
        "owner_name": v.owner_name,
        "assigned_driver": person(v.assigned_driver),
        "registration_renewal_date": day(v.registration_renewal_date),
        "insurance_expiry_date": day(v.insurance_expiry_date),
        "insurer": v.insurer,
        "policy_number": v.policy_number,
        "next_pms_date": day(v.next_pms_date),
        "odometer_km": v.odometer_km,
        "status": v.status,
        "notes": v.notes,
        "due": {
            "registration": days_until(v.registration_renewal_date),
            "insurance": days_until(v.insurance_expiry_date),
            "pms": days_until(v.next_pms_date),
        },
        "version": v.version,
        "updated_at": iso(v.updated_at),
    }


def mini(v: Vehicle | None) -> dict | None:
    return {"id": v.id, "reference": v.reference, "label": v.label, "plate_number": v.plate_number} if v else None


def service_out(s: VehicleService) -> dict:
    return {
        "id": s.id, "reference": s.reference, "vehicle": mini(s.vehicle), "kind": s.kind, "status": s.status,
        "service_date": day(s.service_date), "provider": s.provider, "description": s.description, "parts": s.parts,
        "cost_php": money(s.cost_php), "odometer_km": s.odometer_km, "next_service_date": day(s.next_service_date),
        "created_by": person(s.created_by), "created_at": iso(s.created_at),
    }


def card_out(c: FleetCard) -> dict:
    return {
        "id": c.id, "reference": c.reference, "company": {"id": c.company.id, "code": c.company.code}, "vehicle": mini(c.vehicle),
        "provider": c.provider, "card_masked": f"•••• {c.card_last4}", "fuel_type": c.fuel_type, "assigned_user": person(c.assigned_user),
        "configured_amount_php": money(c.configured_amount_php), "billing_cycle": c.billing_cycle, "monitoring_status": c.monitoring_status, "notes": c.notes,
    }


def rfid_out(r: RfidAccount) -> dict:
    return {
        "id": r.id, "company": {"id": r.company.id, "code": r.company.code}, "vehicle": mini(r.vehicle), "provider": r.provider,
        "account_reference": r.account_reference, "balance_php": money(r.balance_php), "low_balance_php": money(r.low_balance_php),
        "low": r.balance_php < r.low_balance_php, "monitoring_status": r.monitoring_status,
    }


def finance_out(f: FinanceRequest) -> dict:
    return {
        "id": f.id, "reference": f.reference, "company": {"id": f.company.id, "code": f.company.code}, "kind": f.kind,
        "vehicle": mini(f.vehicle), "fleet_card": card_out(f.fleet_card) if f.fleet_card else None,
        "rfid_account": rfid_out(f.rfid_account) if f.rfid_account else None, "period": f.period, "amount_php": money(f.amount_php),
        "status": f.status, "finance_reference": f.finance_reference, "notes": f.notes, "created_by": person(f.created_by),
        "created_at": iso(f.created_at), "sent_at": iso(f.sent_at), "paid_at": iso(f.paid_at),
    }


async def default_limit(session) -> Decimal:
    s = await session.get(AppSetting, DEFAULT_LIMIT_KEY)
    return Decimal(str(s.value.get("amount"))) if s and s.value.get("amount") is not None else DEFAULT_LIMIT


async def log(session, principal: Principal, action: str, entity_type: str, entity_id: int, ref: str, company_id: int, data: dict | None = None):
    await audit(session, actor_id=principal.id, action=f"fleet.{action}", entity_type=entity_type, entity_id=entity_id, entity_ref=ref, company_id=company_id, data=data or {})


def plate(v: str | None) -> str | None:
    v = re.sub(r"\s+", " ", (v or "").strip().upper())
    return v or None


# ------------------------------------------------------------------ options


@router.get("/options")
async def options(principal: Staff, session: Session) -> dict:
    return {
        "vehicle_types": VEHICLE_TYPES,
        "fuel_types": FUEL_TYPES,
        "rfid_providers": RFID_PROVIDERS,
        "statuses": [s.value for s in VehicleStatus],
        "default_card_limit_php": money(await default_limit(session)),
    }


class LimitIn(BaseModel):
    amount_php: Decimal = Field(..., gt=0, le=Decimal("10000000"))


@router.put("/settings/default-card-limit")
async def set_default_limit(body: LimitIn, principal: AdminOnly, session: Session) -> dict:
    s = await session.get(AppSetting, DEFAULT_LIMIT_KEY)
    before = s.value.get("amount") if s else None
    if s is None:
        s = AppSetting(key=DEFAULT_LIMIT_KEY, value={})
        session.add(s)
    s.value = {"amount": str(body.amount_php)}
    await audit(session, actor_id=principal.id, action="fleet.default_limit", entity_type="setting", entity_ref=DEFAULT_LIMIT_KEY, data={"before": before, "after": str(body.amount_php)})
    await session.commit()
    return {"default_card_limit_php": money(body.amount_php)}


# ------------------------------------------------------------------ vehicles


class VehicleIn(BaseModel):
    company_id: int | None = None
    vehicle_type: str = Field(..., min_length=1, max_length=60)
    make: str = Field(..., min_length=1, max_length=80)
    model: str = Field(..., min_length=1, max_length=80)
    year_model: int | None = Field(None, ge=1950, le=2100)
    color: str | None = Field(None, max_length=40)
    plate_number: str | None = Field(None, max_length=20)
    conduction_sticker: str | None = Field(None, max_length=20)
    owner_name: str | None = Field(None, max_length=200)
    assigned_driver_id: int | None = None
    registration_renewal_date: date | None = None
    insurance_expiry_date: date | None = None
    insurer: str | None = Field(None, max_length=120)
    policy_number: str | None = Field(None, max_length=80)
    next_pms_date: date | None = None
    odometer_km: int | None = Field(None, ge=0, le=5_000_000)
    status: VehicleStatus = VehicleStatus.active
    notes: str | None = Field(None, max_length=4000)

    @field_validator("plate_number", "conduction_sticker")
    @classmethod
    def norm(cls, v):
        return plate(v)


class VehiclePatch(VehicleIn):
    version: int


async def unique_ids(session, body: VehicleIn, exclude: int | None = None):
    if not body.plate_number and not body.conduction_sticker:
        raise bad_request({"message": "Enter a plate number or conduction sticker", "fields": {"plate_number": "Plate or conduction sticker required"}})
    if body.year_model and body.year_model > date.today().year + 1:
        raise bad_request({"message": "Year model is too far ahead", "fields": {"year_model": "Check the year"}})
    for field in ("plate_number", "conduction_sticker"):
        v = getattr(body, field)
        if not v:
            continue
        stmt = select(Vehicle.id).where(getattr(Vehicle, field) == v)
        if exclude:
            stmt = stmt.where(Vehicle.id != exclude)
        if (await session.execute(stmt)).first():
            raise conflict(f"{'Plate number' if field == 'plate_number' else 'Conduction sticker'} {v} is already registered")


@router.get("/vehicles")
async def list_vehicles(
    principal: Staff,
    session: Session,
    q: str | None = Query(None, max_length=200),
    status: list[str] = Query(default_factory=list),
    due_within: int | None = Query(None, ge=0, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict:
    stmt = select(Vehicle).where(Vehicle.company_id.in_(principal.company_ids))
    if status:
        stmt = stmt.where(Vehicle.status.in_(status))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Vehicle.reference.ilike(like), Vehicle.plate_number.ilike(like), Vehicle.conduction_sticker.ilike(like), Vehicle.make.ilike(like), Vehicle.model.ilike(like)))
    rows = list((await session.execute(stmt.order_by(Vehicle.make, Vehicle.model))).scalars())
    if due_within is not None:
        def soonest(v: Vehicle):
            ds = [d for d in (days_until(v.registration_renewal_date), days_until(v.insurance_expiry_date), days_until(v.next_pms_date)) if d is not None]
            return min(ds) if ds else None
        rows = [v for v in rows if (s := soonest(v)) is not None and s <= due_within]
        rows.sort(key=lambda v: soonest(v))
    total = len(rows)
    page_rows = rows[(page - 1) * page_size : page * page_size]
    return {"items": [vehicle_out(v) for v in page_rows], "total": total, "page": page, "page_size": page_size}


@router.post("/vehicles", status_code=201)
async def create_vehicle(body: VehicleIn, principal: Staff, session: Session) -> dict:
    cid = await company_for(session, principal, body.company_id)
    await unique_ids(session, body)
    await employee_in(session, body.assigned_driver_id, cid, "assigned_driver_id")
    v = Vehicle(reference=await next_reference(session, "FLT"), company_id=cid, **body.model_dump(exclude={"company_id"}))
    session.add(v)
    try:
        await session.flush()
    except IntegrityError:
        raise conflict("Plate number or conduction sticker is already registered")
    await log(session, principal, "vehicle_create", "vehicle", v.id, v.reference, cid, {"label": v.label})
    await session.commit()
    return vehicle_out(await scoped(session, Vehicle, v.id, principal))


@router.get("/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: int, principal: Staff, session: Session) -> dict:
    v = await scoped(session, Vehicle, vehicle_id, principal)
    services = (await session.execute(select(VehicleService).where(VehicleService.vehicle_id == v.id).order_by(VehicleService.service_date.desc()))).scalars()
    renewals = (await session.execute(select(VehicleRenewal).where(VehicleRenewal.vehicle_id == v.id).order_by(VehicleRenewal.at.desc()))).scalars()
    cards = (await session.execute(select(FleetCard).where(FleetCard.vehicle_id == v.id))).scalars()
    rfid = (await session.execute(select(RfidAccount).where(RfidAccount.vehicle_id == v.id))).scalars()
    atts = (await session.execute(select(Attachment).where(Attachment.owner_type == "vehicle", Attachment.owner_id == v.id, not_photo()))).scalars()
    return {
        **vehicle_out(v),
        "services": [service_out(s) for s in services],
        "renewals": [
            {"id": r.id, "kind": r.kind, "previous_date": day(r.previous_date), "new_date": day(r.new_date), "reference": r.reference, "cost_php": money(r.cost_php), "renewed_by": person(r.renewed_by), "at": iso(r.at)}
            for r in renewals
        ],
        "fleet_cards": [card_out(c) for c in cards],
        "rfid_accounts": [rfid_out(r) for r in rfid],
        "attachments": [attachment_out(a) for a in atts],
    }


@router.patch("/vehicles/{vehicle_id}")
async def update_vehicle(vehicle_id: int, body: VehiclePatch, principal: Staff, session: Session) -> dict:
    v = await scoped(session, Vehicle, vehicle_id, principal)
    check_version(v, body.version)
    if body.company_id and body.company_id != v.company_id:
        raise bad_request({"message": "A vehicle cannot move between companies here", "fields": {"company_id": "Not allowed"}})
    if body.status == VehicleStatus.disposed and not principal.is_admin:
        raise forbidden("Only Admin can mark a vehicle as disposed")
    await unique_ids(session, body, exclude=v.id)
    await employee_in(session, body.assigned_driver_id, v.company_id, "assigned_driver_id")
    changed = {}
    for k, val in body.model_dump(exclude={"company_id", "version"}).items():
        if getattr(v, k) != val:
            changed[k] = str(val)
            setattr(v, k, val)
    v.version += 1
    await log(session, principal, "vehicle_update", "vehicle", v.id, v.reference, v.company_id, changed)
    await session.commit()
    return vehicle_out(await scoped(session, Vehicle, v.id, principal))


class RenewIn(BaseModel):
    kind: Literal["registration", "insurance"]
    new_date: date
    reference: str | None = Field(None, max_length=120)
    cost_php: Decimal | None = Field(None, ge=0, le=Decimal("99999999"))
    insurer: str | None = Field(None, max_length=120)
    policy_number: str | None = Field(None, max_length=80)


@router.post("/vehicles/{vehicle_id}/renew")
async def renew(vehicle_id: int, body: RenewIn, principal: Staff, session: Session) -> dict:
    v = await scoped(session, Vehicle, vehicle_id, principal)
    field = "registration_renewal_date" if body.kind == "registration" else "insurance_expiry_date"
    prev = getattr(v, field)
    if body.new_date <= date.today() or (prev and body.new_date <= prev):
        raise bad_request({"message": "The new date must be later than today and the current date", "fields": {"new_date": "Too early"}})
    setattr(v, field, body.new_date)
    if body.kind == "insurance":
        v.insurer = body.insurer or v.insurer
        v.policy_number = body.policy_number or v.policy_number
    v.version += 1
    session.add(VehicleRenewal(vehicle_id=v.id, kind=body.kind, previous_date=prev, new_date=body.new_date, reference=body.reference, cost_php=body.cost_php, renewed_by_id=principal.id))
    await log(session, principal, f"{body.kind}_renewed", "vehicle", v.id, v.reference, v.company_id, {"from": day(prev), "to": day(body.new_date), "reference": body.reference})
    await session.commit()
    return vehicle_out(await scoped(session, Vehicle, v.id, principal))


@router.get("/renewals")
async def renewals(principal: Staff, session: Session, within: int = Query(60, ge=0, le=365)) -> list[dict]:
    """Every registration, insurance and PMS date due within N days (overdue included), soonest first."""
    rows = (await session.execute(select(Vehicle).where(Vehicle.company_id.in_(principal.company_ids), Vehicle.status.in_([VehicleStatus.active, VehicleStatus.under_maintenance])))).scalars()
    out = []
    for v in rows:
        for kind, d in (("registration", v.registration_renewal_date), ("insurance", v.insurance_expiry_date), ("pms", v.next_pms_date)):
            n = days_until(d)
            if n is not None and n <= within:
                out.append({"kind": kind, "date": day(d), "days": n, "vehicle": mini(v), "assigned_driver": person(v.assigned_driver)})
    out.sort(key=lambda x: x["days"])
    return out


# ------------------------------------------------------------------ PMS & repairs


class ServiceIn(BaseModel):
    kind: Literal["pms", "repair", "parts"]
    status: Literal["scheduled", "done"] = "done"
    service_date: date
    provider: str | None = Field(None, max_length=200)
    description: str = Field(..., min_length=1, max_length=4000)
    parts: str | None = Field(None, max_length=4000)
    cost_php: Decimal | None = Field(None, ge=0, le=Decimal("99999999"))
    odometer_km: int | None = Field(None, ge=0, le=5_000_000)
    next_service_date: date | None = None


@router.post("/vehicles/{vehicle_id}/services", status_code=201)
async def add_service(vehicle_id: int, body: ServiceIn, principal: Staff, session: Session) -> dict:
    v = await scoped(session, Vehicle, vehicle_id, principal)
    if body.status == "done" and body.service_date > date.today():
        raise bad_request({"message": "A completed service cannot be in the future", "fields": {"service_date": "In the future"}})
    if body.next_service_date and body.next_service_date <= body.service_date:
        raise bad_request({"message": "Next service must be after this one", "fields": {"next_service_date": "Too early"}})
    if body.odometer_km is not None and v.odometer_km is not None and body.status == "done" and body.odometer_km < v.odometer_km:
        raise bad_request({"message": f"Odometer is lower than the last reading ({v.odometer_km:,} km)", "fields": {"odometer_km": "Lower than before"}})
    s = VehicleService(reference=await next_reference(session, "MNT"), vehicle_id=v.id, created_by_id=principal.id, **body.model_dump())
    session.add(s)
    if body.status == "done":
        if body.odometer_km is not None:
            v.odometer_km = body.odometer_km
        if body.kind == "pms" and body.next_service_date:
            v.next_pms_date = body.next_service_date
        if v.status == VehicleStatus.under_maintenance:
            v.status = VehicleStatus.active
    elif body.kind == "repair":
        v.status = VehicleStatus.under_maintenance
    v.version += 1
    await session.flush()
    await log(session, principal, "service_record", "vehicle_service", s.id, s.reference, v.company_id, {"vehicle": v.reference, "kind": body.kind, "cost_php": money(body.cost_php)})
    await session.commit()
    return service_out((await session.execute(select(VehicleService).where(VehicleService.id == s.id))).scalar_one())


class ServiceDone(BaseModel):
    cost_php: Decimal | None = Field(None, ge=0, le=Decimal("99999999"))
    odometer_km: int | None = Field(None, ge=0, le=5_000_000)
    next_service_date: date | None = None
    parts: str | None = Field(None, max_length=4000)


@router.post("/services/{service_id}/complete")
async def complete_service(service_id: int, body: ServiceDone, principal: Staff, session: Session) -> dict:
    s = (await session.execute(select(VehicleService).where(VehicleService.id == service_id).execution_options(populate_existing=True))).scalar_one_or_none()
    if s is None or s.vehicle.company_id not in principal.company_ids:
        raise not_found()
    if s.status != "scheduled":
        raise conflict("Only scheduled services can be completed")
    v = await scoped(session, Vehicle, s.vehicle_id, principal)
    s.status = "done"
    s.service_date = min(s.service_date, date.today()) if s.service_date > date.today() else s.service_date
    for f in ("cost_php", "odometer_km", "next_service_date", "parts"):
        val = getattr(body, f)
        if val is not None:
            setattr(s, f, val)
    if s.odometer_km is not None:
        v.odometer_km = max(v.odometer_km or 0, s.odometer_km)
    if s.kind == "pms" and s.next_service_date:
        v.next_pms_date = s.next_service_date
    if v.status == VehicleStatus.under_maintenance:
        v.status = VehicleStatus.active
    v.version += 1
    await log(session, principal, "service_complete", "vehicle_service", s.id, s.reference, v.company_id, {"cost_php": money(s.cost_php)})
    await session.commit()
    return service_out((await session.execute(select(VehicleService).where(VehicleService.id == s.id).execution_options(populate_existing=True))).scalar_one())


@router.get("/services")
async def list_services(
    principal: Staff, session: Session, kind: str | None = None, status: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
) -> dict:
    stmt = select(VehicleService).join(Vehicle, Vehicle.id == VehicleService.vehicle_id).where(Vehicle.company_id.in_(principal.company_ids))
    if kind:
        stmt = stmt.where(VehicleService.kind == kind)
    if status:
        stmt = stmt.where(VehicleService.status == status)
    total = await count(session, stmt)
    rows = (await session.execute(stmt.order_by(VehicleService.service_date.desc(), VehicleService.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars()
    return {"items": [service_out(s) for s in rows], "total": total, "page": page, "page_size": page_size}


# ------------------------------------------------------------------ fleet cards


class CardIn(BaseModel):
    company_id: int | None = None
    vehicle_id: int | None = None
    provider: str = Field("Shell", min_length=1, max_length=60)
    card_number_last4: str = Field(..., description="Only the last four digits are accepted and stored")
    fuel_type: str | None = Field(None, max_length=40)
    assigned_user_id: int | None = None
    configured_amount_php: Decimal | None = Field(None, gt=0, le=Decimal("10000000"))
    billing_cycle: Literal["monthly", "biweekly", "weekly"] = "monthly"
    monitoring_status: Literal["active", "suspended", "cancelled"] = "active"
    notes: str | None = Field(None, max_length=4000)

    @field_validator("card_number_last4")
    @classmethod
    def last4(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v or "")
        if len(digits) != 4:
            raise ValueError("Enter only the last 4 digits of the card")
        return digits


async def vehicle_in(session, vehicle_id: int | None, company_id: int) -> Vehicle | None:
    if vehicle_id is None:
        return None
    v = await session.get(Vehicle, vehicle_id)
    if v is None or v.company_id != company_id:
        raise bad_request({"message": "That vehicle is not in this company", "fields": {"vehicle_id": "Wrong company"}})
    return v


@router.get("/cards")
async def list_cards(principal: Staff, session: Session) -> list[dict]:
    rows = (await session.execute(select(FleetCard).where(FleetCard.company_id.in_(principal.company_ids)).order_by(FleetCard.id.desc()))).scalars()
    return [card_out(c) for c in rows]


@router.post("/cards", status_code=201)
async def create_card(body: CardIn, principal: Staff, session: Session) -> dict:
    cid = await company_for(session, principal, body.company_id)
    await vehicle_in(session, body.vehicle_id, cid)
    await employee_in(session, body.assigned_user_id, cid, "assigned_user_id")
    amount = body.configured_amount_php or await default_limit(session)
    c = FleetCard(
        reference=await next_reference(session, "FCD"), company_id=cid, vehicle_id=body.vehicle_id, provider=body.provider, card_last4=body.card_number_last4,
        fuel_type=body.fuel_type, assigned_user_id=body.assigned_user_id, configured_amount_php=amount, billing_cycle=body.billing_cycle,
        monitoring_status=body.monitoring_status, notes=body.notes,
    )
    session.add(c)
    try:
        await session.flush()
    except IntegrityError:
        raise conflict("That card is already registered for this vehicle")
    await log(session, principal, "card_create", "fleet_card", c.id, c.reference, cid, {"card": f"****{c.card_last4}", "amount": money(amount)})
    await session.commit()
    return card_out(await scoped(session, FleetCard, c.id, principal))


class CardPatch(BaseModel):
    vehicle_id: int | None = None
    assigned_user_id: int | None = None
    configured_amount_php: Decimal | None = Field(None, gt=0, le=Decimal("10000000"))
    monitoring_status: Literal["active", "suspended", "cancelled"] | None = None
    fuel_type: str | None = Field(None, max_length=40)
    notes: str | None = Field(None, max_length=4000)


@router.patch("/cards/{card_id}")
async def update_card(card_id: int, body: CardPatch, principal: Staff, session: Session) -> dict:
    c = await scoped(session, FleetCard, card_id, principal)
    changes = body.model_dump(exclude_unset=True)
    if "vehicle_id" in changes:
        await vehicle_in(session, changes["vehicle_id"], c.company_id)
    if "assigned_user_id" in changes:
        await employee_in(session, changes["assigned_user_id"], c.company_id, "assigned_user_id")
    for k, val in changes.items():
        setattr(c, k, val)
    await log(session, principal, "card_update", "fleet_card", c.id, c.reference, c.company_id, {k: str(v) for k, v in changes.items()})
    await session.commit()
    return card_out(await scoped(session, FleetCard, c.id, principal))


# ------------------------------------------------------------------ RFID


class RfidIn(BaseModel):
    company_id: int | None = None
    vehicle_id: int | None = None
    provider: str = Field(..., min_length=1, max_length=60)
    account_reference: str = Field(..., min_length=3, max_length=60)
    balance_php: Decimal = Field(Decimal("0"), ge=0, le=Decimal("10000000"))
    low_balance_php: Decimal = Field(Decimal("500"), ge=0, le=Decimal("10000000"))


@router.get("/rfid")
async def list_rfid(principal: Staff, session: Session) -> list[dict]:
    rows = (await session.execute(select(RfidAccount).where(RfidAccount.company_id.in_(principal.company_ids)).order_by(RfidAccount.balance_php))).scalars()
    return [rfid_out(r) for r in rows]


@router.post("/rfid", status_code=201)
async def create_rfid(body: RfidIn, principal: Staff, session: Session) -> dict:
    cid = await company_for(session, principal, body.company_id)
    await vehicle_in(session, body.vehicle_id, cid)
    r = RfidAccount(company_id=cid, **body.model_dump(exclude={"company_id"}))
    session.add(r)
    try:
        await session.flush()
    except IntegrityError:
        raise conflict(f"{body.provider} account {body.account_reference} is already registered")
    await log(session, principal, "rfid_create", "rfid", r.id, r.account_reference, cid, {"provider": r.provider})
    await session.commit()
    return rfid_out(await scoped(session, RfidAccount, r.id, principal))


class BalanceIn(BaseModel):
    balance_php: Decimal = Field(..., ge=0, le=Decimal("10000000"))
    note: str | None = Field(None, max_length=400)


@router.post("/rfid/{account_id}/balance")
async def set_balance(account_id: int, body: BalanceIn, principal: Staff, session: Session) -> dict:
    """Record the balance read from the provider portal (monitoring, not a payment)."""
    r = await scoped(session, RfidAccount, account_id, principal)
    before = r.balance_php
    r.balance_php = body.balance_php
    await log(session, principal, "rfid_balance", "rfid", r.id, r.account_reference, r.company_id, {"before": money(before), "after": money(body.balance_php), "note": body.note})
    await session.commit()
    return rfid_out(await scoped(session, RfidAccount, r.id, principal))


# ------------------------------------------------------------------ Finance hand-offs


class FinanceIn(BaseModel):
    company_id: int | None = None
    kind: Literal["fleet_billing", "rfid_reload", "other"]
    fleet_card_id: int | None = None
    rfid_account_id: int | None = None
    vehicle_id: int | None = None
    period: str | None = Field(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount_php: Decimal = Field(..., gt=0, le=Decimal("10000000"))
    notes: str | None = Field(None, max_length=4000)
    send: bool = False


@router.get("/finance")
async def list_finance(
    principal: Staff, session: Session, status: list[str] = Query(default_factory=list), kind: str | None = None, period: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
) -> dict:
    stmt = select(FinanceRequest).where(FinanceRequest.company_id.in_(principal.company_ids))
    if status:
        stmt = stmt.where(FinanceRequest.status.in_(status))
    if kind:
        stmt = stmt.where(FinanceRequest.kind == kind)
    if period:
        stmt = stmt.where(FinanceRequest.period == period)
    total = await count(session, stmt)
    rows = (await session.execute(stmt.order_by(FinanceRequest.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars()
    return {"items": [finance_out(f) for f in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/finance", status_code=201)
async def create_finance(body: FinanceIn, principal: Staff, session: Session) -> dict:
    cid = await company_for(session, principal, body.company_id)
    vehicle_id = body.vehicle_id
    if body.kind == "fleet_billing":
        if not body.fleet_card_id:
            raise bad_request({"message": "Choose the fleet card", "fields": {"fleet_card_id": "Required"}})
        card = await scoped(session, FleetCard, body.fleet_card_id, principal)
        if card.company_id != cid:
            raise bad_request({"message": "That card is in another company", "fields": {"fleet_card_id": "Wrong company"}})
        if card.monitoring_status != "active":
            raise conflict("That card is not active")
        if not body.period:
            raise bad_request({"message": "Set the billing month", "fields": {"period": "Required"}})
        dup = await session.execute(
            select(FinanceRequest.id).where(FinanceRequest.fleet_card_id == card.id, FinanceRequest.period == body.period, FinanceRequest.status.notin_([FinanceStatus.cancelled, FinanceStatus.rejected]))
        )
        if dup.first():
            raise conflict(f"{body.period} billing for this card is already recorded")
        vehicle_id = vehicle_id or card.vehicle_id
    if body.kind == "rfid_reload":
        if not body.rfid_account_id:
            raise bad_request({"message": "Choose the RFID account", "fields": {"rfid_account_id": "Required"}})
        acct = await scoped(session, RfidAccount, body.rfid_account_id, principal)
        if acct.company_id != cid:
            raise bad_request({"message": "That account is in another company", "fields": {"rfid_account_id": "Wrong company"}})
        vehicle_id = vehicle_id or acct.vehicle_id
    f = FinanceRequest(
        reference=await next_reference(session, "FIN"), company_id=cid, kind=body.kind, fleet_card_id=body.fleet_card_id if body.kind == "fleet_billing" else None,
        rfid_account_id=body.rfid_account_id if body.kind == "rfid_reload" else None, vehicle_id=vehicle_id, period=body.period,
        amount_php=body.amount_php, notes=body.notes, created_by_id=principal.id,
    )
    if body.send:
        f.status = FinanceStatus.sent
        f.sent_at = now()
    session.add(f)
    await session.flush()
    await log(session, principal, "finance_create", "finance", f.id, f.reference, cid, {"kind": f.kind, "amount": money(f.amount_php), "status": f.status})
    await session.commit()
    return finance_out(await scoped(session, FinanceRequest, f.id, principal))


class FinanceAction(BaseModel):
    finance_reference: str | None = Field(None, max_length=120)
    reason: str | None = Field(None, max_length=2000)


FINANCE_FLOW = {
    "send": ({FinanceStatus.draft}, FinanceStatus.sent),
    "paid": ({FinanceStatus.sent}, FinanceStatus.paid),
    "reject": ({FinanceStatus.sent}, FinanceStatus.rejected),
    "cancel": ({FinanceStatus.draft, FinanceStatus.sent}, FinanceStatus.cancelled),
}


@router.post("/finance/{finance_id}/{action}")
async def finance_action(finance_id: int, action: str, body: FinanceAction, principal: Staff, session: Session) -> dict:
    if action not in FINANCE_FLOW:
        raise not_found()
    f = await scoped(session, FinanceRequest, finance_id, principal)
    allowed, to = FINANCE_FLOW[action]
    if f.status not in allowed:
        raise conflict(f"A {f.status} hand-off cannot be marked {to}")
    if action == "paid" and not (body.finance_reference or "").strip():
        raise bad_request({"message": "Enter Finance's payment reference", "fields": {"finance_reference": "Required"}})
    if action in ("reject", "cancel") and not (body.reason or "").strip():
        raise bad_request({"message": "Give a reason", "fields": {"reason": "Required"}})
    f.status = to
    if action == "send":
        f.sent_at = now()
    if action == "paid":
        f.paid_at = now()
        f.finance_reference = body.finance_reference.strip()
        if f.kind == "rfid_reload" and f.rfid_account_id:
            acct = await scoped(session, RfidAccount, f.rfid_account_id, principal)
            acct.balance_php = (acct.balance_php or Decimal("0")) + f.amount_php
            await log(session, principal, "rfid_reloaded", "rfid", acct.id, acct.account_reference, acct.company_id, {"amount": money(f.amount_php), "finance": f.finance_reference})
    if body.reason:
        f.notes = ((f.notes or "") + f"\n{action}: {body.reason}").strip()
    await log(session, principal, f"finance_{action}", "finance", f.id, f.reference, f.company_id, {"finance_reference": f.finance_reference, "reason": body.reason})
    if action in ("paid", "reject") and f.created_by_id != principal.id:
        await notify(session, {f.created_by_id}, kind="payment_status", title=f"Finance {'paid' if action == 'paid' else 'rejected'}: {f.reference}", body=body.finance_reference or body.reason, link="/fleet/fuel-billing")
    await session.commit()
    return finance_out(await scoped(session, FinanceRequest, f.id, principal))


# ------------------------------------------------------------------ reminders (called by the sweep)


async def fleet_reminders(session) -> int:
    """Renewal warnings at 30, 7 and 0 days; low RFID balances. De-duplicated per threshold."""
    sent = 0
    rows = (await session.execute(select(Vehicle).where(Vehicle.status.in_([VehicleStatus.active, VehicleStatus.under_maintenance])))).scalars().all()
    for v in rows:
        for kind, label, d in (("registration", "Registration", v.registration_renewal_date), ("insurance", "Insurance", v.insurance_expiry_date), ("pms", "PMS", v.next_pms_date)):
            n = days_until(d)
            if n is None or n > 30:
                continue
            band = 0 if n <= 0 else 7 if n <= 7 else 30
            when = "is overdue" if n < 0 else "is due today" if n == 0 else f"is due in {n} days"
            await notify(
                session, await admin_ids(session, v.company_id), kind="renewal_warning", title=f"{label} {when}: {v.label}",
                body=f"{v.reference} · {d.isoformat()}", link=f"/vehicle/{v.id}", dedupe_key=f"fleet:{kind}:{v.id}:{d.isoformat()}:{band}",
            )
            sent += 1
    for r in (await session.execute(select(RfidAccount).where(RfidAccount.monitoring_status == "active"))).scalars().all():
        if r.balance_php < r.low_balance_php:
            await notify(
                session, await admin_ids(session, r.company_id), kind="renewal_warning", title=f"Low RFID balance: {r.provider} {r.account_reference}",
                body=f"₱{r.balance_php:,.2f} left", link=f"/vehicle/{r.vehicle_id}" if r.vehicle_id else "/fleet/fuel-billing", dedupe_key=f"rfid-low:{r.id}:{r.balance_php}",
            )
            sent += 1
    return sent
