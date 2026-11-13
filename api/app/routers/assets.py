"""Phase 2.3 — asset registry, assignment, transfers, repairs and receiving proof."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from ..core import audit, bad_request, conflict, forbidden, next_reference, not_found, notify, now
from ..models import Attachment, Employee, Request, RequestKind, RequestStatus as S
from ..models_ops import Asset, AssetCondition, AssetEvent, AssetRepair, AssetStatus, Receipt, RepairStatus
from ..ops_common import check_version, company_for, count, day, department_in, employee_in, money, scoped
from ..security import CurrentPrincipal, Principal, Session, Staff
from ..serialize import attachment_out, iso, person
from .photos import not_photo, photo_url
from ..workflow import event as request_event, is_operator

router = APIRouter(prefix="/api/v1", tags=["assets"])

CATEGORIES = ["IT equipment", "Office equipment", "Furniture", "Appliance", "Mobile device", "Tools", "Other"]
CONDITION_LABEL = {
    "brand_new": "Brand new",
    "used": "Used",
    "for_repair": "For repair",
    "damaged": "Damaged",
    "unserviceable": "Unserviceable",
}


def asset_out(a: Asset) -> dict:
    return {
        "id": a.id,
        "photo": photo_url(a.photo_id),
        "reference": a.reference,
        "name": a.name,
        "category": a.category,
        "serial_number": a.serial_number,
        "brand": a.brand,
        "model": a.model,
        "quantity": a.quantity,
        "unit": a.unit,
        "condition": a.condition,
        "status": a.status,
        "location": a.location,
        "company": {"id": a.company.id, "code": a.company.code, "name": a.company.name},
        "department": {"id": a.department.id, "name": a.department.name} if a.department else None,
        "holder": person(a.holder),
        "issued_by": person(a.issued_by),
        "date_issued": day(a.date_issued),
        "acknowledged_at": iso(a.acknowledged_at),
        "awaiting_acknowledgement": bool(a.holder_id and not a.acknowledged_at),
        "purchase_date": day(a.purchase_date),
        "purchase_reference": a.purchase_reference,
        "description": a.description,
        "purpose": a.purpose,
        "remarks": a.remarks,
        "request_id": a.request_id,
        "updated_at": iso(a.updated_at),
        "version": a.version,
    }


def repair_out(r: AssetRepair) -> dict:
    return {
        "id": r.id,
        "reference": r.reference,
        "asset": {"id": r.asset.id, "reference": r.asset.reference, "name": r.asset.name, "serial_number": r.asset.serial_number},
        "request_id": r.request_id,
        "issue": r.issue,
        "provider": r.provider,
        "cost_php": money(r.cost_php),
        "status": r.status,
        "outcome_condition": r.outcome_condition,
        "notes": r.notes,
        "opened_by": person(r.opened_by),
        "opened_at": iso(r.opened_at),
        "completed_at": iso(r.completed_at),
    }


async def log(session, a: Asset, principal: Principal | None, type_: str, message: str | None = None, *, frm=None, to=None, data=None):
    session.add(
        AssetEvent(
            asset_id=a.id, type=type_, message=message, actor_id=principal.id if principal else None,
            from_holder_id=frm, to_holder_id=to, data=data or {},
        )
    )
    await audit(
        session, actor_id=principal.id if principal else None, action=f"asset.{type_}", entity_type="asset",
        entity_id=a.id, entity_ref=a.reference, company_id=a.company_id, data={"message": message, **(data or {})},
    )


# ------------------------------------------------------------------ registry


class AssetIn(BaseModel):
    company_id: int | None = None
    department_id: int | None = None
    name: str = Field(..., min_length=1, max_length=300)
    category: str = Field(..., min_length=1, max_length=120)
    serial_number: str | None = Field(None, max_length=120)
    brand: str | None = Field(None, max_length=120)
    model: str | None = Field(None, max_length=120)
    quantity: int = Field(1, ge=1, le=100000)
    unit: str = Field("unit", max_length=40)
    condition: AssetCondition = AssetCondition.brand_new
    location: str | None = Field(None, max_length=300)
    purchase_date: date | None = None
    purchase_reference: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=4000)
    purpose: str | None = Field(None, max_length=4000)
    remarks: str | None = Field(None, max_length=4000)

    @field_validator("serial_number")
    @classmethod
    def norm_serial(cls, v):
        v = (v or "").strip().upper()
        return v or None


class AssetPatch(AssetIn):
    version: int


def validate_asset(body: AssetIn):
    if body.serial_number and body.quantity != 1:
        raise bad_request({"message": "A serialized asset is one item: set quantity to 1", "fields": {"quantity": "Must be 1 when a serial number is set"}})
    if body.purchase_date and body.purchase_date > date.today():
        raise bad_request({"message": "Purchase date cannot be in the future", "fields": {"purchase_date": "In the future"}})


async def serial_taken(session, serial: str | None, exclude: int | None = None) -> bool:
    if not serial:
        return False
    stmt = select(Asset.id).where(Asset.serial_number == serial)
    if exclude:
        stmt = stmt.where(Asset.id != exclude)
    return (await session.execute(stmt)).first() is not None


@router.get("/assets/options")
async def asset_options(principal: Staff) -> dict:
    return {"categories": CATEGORIES, "conditions": [{"value": k, "label": v} for k, v in CONDITION_LABEL.items()], "statuses": [s.value for s in AssetStatus]}


@router.get("/assets")
async def list_assets(
    principal: Staff,
    session: Session,
    q: str | None = Query(None, max_length=200),
    status: list[str] = Query(default_factory=list),
    condition: list[str] = Query(default_factory=list),
    category: str | None = None,
    holder: Literal["any", "assigned", "unassigned", "unacknowledged"] = "any",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> dict:
    stmt = select(Asset).where(Asset.company_id.in_(principal.company_ids))
    if status:
        stmt = stmt.where(Asset.status.in_(status))
    if condition:
        stmt = stmt.where(Asset.condition.in_(condition))
    if category:
        stmt = stmt.where(Asset.category == category)
    if holder == "assigned":
        stmt = stmt.where(Asset.holder_id.is_not(None))
    elif holder == "unassigned":
        stmt = stmt.where(Asset.holder_id.is_(None), Asset.status != AssetStatus.retired)
    elif holder == "unacknowledged":
        stmt = stmt.where(Asset.holder_id.is_not(None), Asset.acknowledged_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.outerjoin(Employee, Employee.id == Asset.holder_id).where(
            or_(Asset.reference.ilike(like), Asset.name.ilike(like), Asset.serial_number.ilike(like), Asset.brand.ilike(like), Asset.model.ilike(like), Employee.name.ilike(like))
        )
    total = await count(session, stmt)
    rows = (await session.execute(stmt.order_by(Asset.updated_at.desc(), Asset.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars()
    summary = {}
    for st in AssetStatus:
        summary[st.value] = await count(session, select(Asset).where(Asset.company_id.in_(principal.company_ids), Asset.status == st))
    summary["unacknowledged"] = await count(
        session, select(Asset).where(Asset.company_id.in_(principal.company_ids), Asset.holder_id.is_not(None), Asset.acknowledged_at.is_(None))
    )
    return {"items": [asset_out(a) for a in rows], "total": total, "page": page, "page_size": page_size, "summary": summary}


@router.post("/assets", status_code=201)
async def create_asset(body: AssetIn, principal: Staff, session: Session) -> dict:
    validate_asset(body)
    cid = await company_for(session, principal, body.company_id)
    await department_in(session, body.department_id, cid)
    if await serial_taken(session, body.serial_number):
        raise conflict(f"Serial number {body.serial_number} is already registered")
    data = body.model_dump(exclude={"company_id"})
    a = Asset(reference=await next_reference(session, "AST"), company_id=cid, **data)
    session.add(a)
    try:
        await session.flush()
    except IntegrityError:
        raise conflict(f"Serial number {body.serial_number} is already registered")
    await log(session, a, principal, "registered", f"Registered as {CONDITION_LABEL[a.condition]}")
    await session.commit()
    return asset_out(await scoped(session, Asset, a.id, principal))


async def asset_detail(session, principal: Principal, a: Asset) -> dict:
    events = (await session.execute(select(AssetEvent).where(AssetEvent.asset_id == a.id).order_by(AssetEvent.at.desc(), AssetEvent.id.desc()))).scalars()
    repairs = (await session.execute(select(AssetRepair).where(AssetRepair.asset_id == a.id).order_by(AssetRepair.id.desc()))).scalars()
    atts = (await session.execute(select(Attachment).where(Attachment.owner_type == "asset", Attachment.owner_id == a.id, not_photo()))).scalars()
    staff = principal.is_staff and a.company_id in principal.company_ids
    actions = []
    if staff:
        if a.status != AssetStatus.retired:
            actions += ["edit", "transfer", "attach"]
            actions.append("return" if a.holder_id else "assign")
            if a.status != AssetStatus.under_repair:
                actions.append("repair")
            if principal.is_admin:
                actions.append("retire")
    if a.holder_id == principal.id and not a.acknowledged_at:
        actions.append("acknowledge")
    return {
        **asset_out(a),
        "events": [
            {"id": e.id, "type": e.type, "message": e.message, "actor": person(e.actor), "from_holder": person(e.from_holder), "to_holder": person(e.to_holder), "at": iso(e.at)}
            for e in events
        ],
        "repairs": [repair_out(r) for r in repairs],
        "attachments": [attachment_out(x) for x in atts],
        "actions": actions,
    }


async def load_asset_for(session, principal: Principal, asset_id: int) -> Asset:
    a = (await session.execute(select(Asset).where(Asset.id == asset_id).execution_options(populate_existing=True))).scalar_one_or_none()
    if a is None:
        raise not_found()
    if principal.is_staff and a.company_id in principal.company_ids:
        return a
    if a.holder_id == principal.id:
        return a
    raise not_found()


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: int, principal: CurrentPrincipal, session: Session) -> dict:
    return await asset_detail(session, principal, await load_asset_for(session, principal, asset_id))


@router.patch("/assets/{asset_id}")
async def update_asset(asset_id: int, body: AssetPatch, principal: Staff, session: Session) -> dict:
    a = await scoped(session, Asset, asset_id, principal)
    if a.status == AssetStatus.retired:
        raise conflict("Retired assets cannot be edited")
    check_version(a, body.version)
    validate_asset(body)
    if body.company_id and body.company_id != a.company_id:
        raise bad_request({"message": "Use a transfer to move an asset to another company", "fields": {"company_id": "Use transfer"}})
    await department_in(session, body.department_id, a.company_id)
    if await serial_taken(session, body.serial_number, exclude=a.id):
        raise conflict(f"Serial number {body.serial_number} is already registered")
    changed = {}
    for k, v in body.model_dump(exclude={"company_id", "version"}).items():
        if getattr(a, k) != v:
            changed[k] = str(v)
            setattr(a, k, v)
    a.version += 1
    if changed:
        await log(session, a, principal, "updated", ", ".join(changed), data={"changed": list(changed)})
    await session.commit()
    return await asset_detail(session, principal, await scoped(session, Asset, a.id, principal))


class AssignIn(BaseModel):
    employee_id: int
    date_issued: date | None = None
    condition: AssetCondition | None = None
    note: str | None = Field(None, max_length=2000)


class ReturnIn(BaseModel):
    condition: AssetCondition
    note: str | None = Field(None, max_length=2000)


class TransferIn(BaseModel):
    employee_id: int | None = None
    department_id: int | None = None
    location: str | None = Field(None, max_length=300)
    reason: str = Field(..., min_length=1, max_length=2000)


class RetireIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class RepairIn(BaseModel):
    issue: str = Field(..., min_length=1, max_length=4000)
    provider: str | None = Field(None, max_length=200)
    request_id: int | None = None


@router.post("/assets/{asset_id}/assign")
async def assign(asset_id: int, body: AssignIn, principal: Staff, session: Session) -> dict:
    a = await scoped(session, Asset, asset_id, principal)
    if a.status in (AssetStatus.retired, AssetStatus.under_repair):
        raise conflict(f"An asset that is {a.status.replace('_', ' ')} cannot be issued")
    if a.holder_id:
        raise conflict(f"Already issued to {a.holder.name}. Return or transfer it first.")
    emp = await employee_in(session, body.employee_id, a.company_id, "employee_id")
    if body.date_issued and body.date_issued > date.today():
        raise bad_request({"message": "Issue date cannot be in the future", "fields": {"date_issued": "In the future"}})
    a.holder_id = emp.id
    a.issued_by_id = principal.id
    a.date_issued = body.date_issued or date.today()
    a.acknowledged_at = None
    a.status = AssetStatus.assigned
    if body.condition:
        a.condition = body.condition
    if emp.department_id:
        a.department_id = emp.department_id
    a.version += 1
    await log(session, a, principal, "assigned", body.note or f"Issued to {emp.name}", to=emp.id, data={"condition": a.condition})
    await notify(
        session, {emp.id}, kind="task_assignment", title=f"Please acknowledge: {a.name}",
        body=f"{a.reference} was issued to you. Confirm you received it.", link=f"/asset/{a.id}",
    )
    await session.commit()
    return await asset_detail(session, principal, await scoped(session, Asset, a.id, principal))


@router.post("/assets/{asset_id}/acknowledge")
async def acknowledge(asset_id: int, principal: CurrentPrincipal, session: Session) -> dict:
    a = await load_asset_for(session, principal, asset_id)
    if a.holder_id != principal.id:
        raise forbidden("Only the person holding this asset can acknowledge it")
    if a.acknowledged_at:
        raise conflict("Already acknowledged")
    a.acknowledged_at = now()
    a.version += 1
    await log(session, a, principal, "acknowledged", "Receipt acknowledged by holder")
    if a.issued_by_id:
        await notify(session, {a.issued_by_id}, kind="fulfillment_confirmation", title=f"Acknowledged: {a.name}", body=f"{principal.employee.name} confirmed receipt of {a.reference}.", link=f"/asset/{a.id}")
    await session.commit()
    return await asset_detail(session, principal, await load_asset_for(session, principal, a.id))


@router.post("/assets/{asset_id}/return")
async def return_asset(asset_id: int, body: ReturnIn, principal: Staff, session: Session) -> dict:
    a = await scoped(session, Asset, asset_id, principal)
    if not a.holder_id:
        raise conflict("This asset is not issued to anyone")
    prev = a.holder_id
    a.holder_id = None
    a.acknowledged_at = None
    a.date_issued = None
    a.condition = body.condition
    a.status = AssetStatus.in_stock
    a.version += 1
    await log(session, a, principal, "returned", body.note or f"Returned as {CONDITION_LABEL[body.condition]}", frm=prev, data={"condition": body.condition})
    await session.commit()
    return await asset_detail(session, principal, await scoped(session, Asset, a.id, principal))


@router.post("/assets/{asset_id}/transfer")
async def transfer(asset_id: int, body: TransferIn, principal: Staff, session: Session) -> dict:
    a = await scoped(session, Asset, asset_id, principal)
    if a.status in (AssetStatus.retired, AssetStatus.under_repair):
        raise conflict(f"An asset that is {a.status.replace('_', ' ')} cannot be transferred")
    if body.employee_id is None and body.department_id is None and not body.location:
        raise bad_request({"message": "Choose a new holder, department or location", "fields": {"employee_id": "Required"}})
    prev_holder = a.holder_id
    parts = []
    if body.employee_id is not None:
        if body.employee_id == a.holder_id:
            raise bad_request({"message": "That person already holds it", "fields": {"employee_id": "Same holder"}})
        emp = await employee_in(session, body.employee_id, a.company_id, "employee_id")
        a.holder_id = emp.id
        a.issued_by_id = principal.id
        a.date_issued = date.today()
        a.acknowledged_at = None
        a.status = AssetStatus.assigned
        if emp.department_id and body.department_id is None:
            a.department_id = emp.department_id
        parts.append(f"to {emp.name}")
        await notify(session, {emp.id}, kind="task_assignment", title=f"Please acknowledge: {a.name}", body=f"{a.reference} was transferred to you.", link=f"/asset/{a.id}")
    if body.department_id is not None:
        d = await department_in(session, body.department_id, a.company_id)
        a.department_id = d.id
        parts.append(f"department {d.name}")
    if body.location:
        a.location = body.location
        parts.append(f"location {body.location}")
    a.version += 1
    await log(session, a, principal, "transferred", f"Moved {', '.join(parts)} — {body.reason}", frm=prev_holder, to=a.holder_id, data={"reason": body.reason})
    await session.commit()
    return await asset_detail(session, principal, await scoped(session, Asset, a.id, principal))


@router.post("/assets/{asset_id}/retire")
async def retire(asset_id: int, body: RetireIn, principal: Staff, session: Session) -> dict:
    if not principal.is_admin:
        raise forbidden("Only Admin can retire assets")
    a = await scoped(session, Asset, asset_id, principal)
    if a.status == AssetStatus.retired:
        raise conflict("Already retired")
    if a.holder_id:
        raise conflict("Return the asset before retiring it")
    a.status = AssetStatus.retired
    a.condition = AssetCondition.unserviceable if a.condition in (AssetCondition.damaged, AssetCondition.for_repair) else a.condition
    a.version += 1
    await log(session, a, principal, "retired", body.reason)
    await session.commit()
    return await asset_detail(session, principal, await scoped(session, Asset, a.id, principal))


# ------------------------------------------------------------------ employee view


@router.get("/me/assets")
async def my_assets(principal: CurrentPrincipal, session: Session) -> list[dict]:
    rows = (await session.execute(select(Asset).where(Asset.holder_id == principal.id).order_by(Asset.acknowledged_at.is_not(None), Asset.date_issued.desc()))).scalars()
    return [asset_out(a) for a in rows]


# ------------------------------------------------------------------ repairs


class RepairPatch(BaseModel):
    status: RepairStatus | None = None
    provider: str | None = Field(None, max_length=200)
    cost_php: Decimal | None = Field(None, ge=0, le=Decimal("99999999"))
    outcome_condition: AssetCondition | None = None
    notes: str | None = Field(None, max_length=4000)


@router.post("/assets/{asset_id}/repairs", status_code=201)
async def open_repair(asset_id: int, body: RepairIn, principal: Staff, session: Session) -> dict:
    a = await scoped(session, Asset, asset_id, principal)
    if a.status in (AssetStatus.retired, AssetStatus.under_repair):
        raise conflict(f"An asset that is {a.status.replace('_', ' ')} cannot go for repair")
    if body.request_id:
        req = await session.get(Request, body.request_id)
        if req is None or req.company_id != a.company_id:
            raise bad_request({"message": "Unknown request", "fields": {"request_id": "Not found"}})
    r = AssetRepair(reference=await next_reference(session, "MNT"), asset_id=a.id, request_id=body.request_id, issue=body.issue, provider=body.provider, opened_by_id=principal.id)
    session.add(r)
    a.status = AssetStatus.under_repair
    a.condition = AssetCondition.for_repair
    a.version += 1
    await session.flush()
    await log(session, a, principal, "repair_opened", f"{r.reference}: {body.issue}", data={"repair": r.reference})
    await session.commit()
    return repair_out((await session.execute(select(AssetRepair).where(AssetRepair.id == r.id))).scalar_one())


@router.get("/asset-repairs")
async def list_repairs(
    principal: Staff,
    session: Session,
    state: Literal["open", "closed", "all"] = "open",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> dict:
    stmt = select(AssetRepair).join(Asset, Asset.id == AssetRepair.asset_id).where(Asset.company_id.in_(principal.company_ids))
    if state == "open":
        stmt = stmt.where(AssetRepair.status.in_([RepairStatus.open, RepairStatus.in_repair]))
    elif state == "closed":
        stmt = stmt.where(AssetRepair.status.in_([RepairStatus.completed, RepairStatus.cancelled]))
    total = await count(session, stmt)
    rows = (await session.execute(stmt.order_by(AssetRepair.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars()
    return {"items": [repair_out(r) for r in rows], "total": total, "page": page, "page_size": page_size}


REPAIR_FLOW = {RepairStatus.open: {RepairStatus.in_repair, RepairStatus.completed, RepairStatus.cancelled}, RepairStatus.in_repair: {RepairStatus.completed, RepairStatus.cancelled}}


@router.patch("/asset-repairs/{repair_id}")
async def update_repair(repair_id: int, body: RepairPatch, principal: Staff, session: Session) -> dict:
    r = (await session.execute(select(AssetRepair).where(AssetRepair.id == repair_id).execution_options(populate_existing=True))).scalar_one_or_none()
    if r is None or r.asset.company_id not in principal.company_ids:
        raise not_found()
    if r.status in (RepairStatus.completed, RepairStatus.cancelled):
        raise conflict("This repair is closed")
    a = await scoped(session, Asset, r.asset_id, principal)
    for f in ("provider", "cost_php", "notes"):
        v = getattr(body, f)
        if v is not None:
            setattr(r, f, v)
    if body.status and body.status != r.status:
        if body.status not in REPAIR_FLOW.get(r.status, set()):
            raise conflict(f"A repair that is {r.status.replace('_', ' ')} cannot become {body.status.replace('_', ' ')}")
        if body.status == RepairStatus.completed and not body.outcome_condition:
            raise bad_request({"message": "Record the condition after repair", "fields": {"outcome_condition": "Required"}})
        r.status = body.status
        if body.status in (RepairStatus.completed, RepairStatus.cancelled):
            r.completed_at = now()
            r.outcome_condition = body.outcome_condition
            if body.outcome_condition:
                a.condition = body.outcome_condition
            a.status = AssetStatus.assigned if a.holder_id else AssetStatus.in_stock
            a.version += 1
            msg = f"{r.reference} {body.status}" + (f" — now {CONDITION_LABEL[body.outcome_condition]}" if body.outcome_condition else "")
            await log(session, a, principal, "repair_closed", msg, data={"repair": r.reference, "cost_php": money(r.cost_php)})
    await audit(session, actor_id=principal.id, action="asset.repair_update", entity_type="repair", entity_id=r.id, entity_ref=r.reference, company_id=a.company_id, data=body.model_dump(mode="json", exclude_none=True))
    await session.commit()
    return repair_out((await session.execute(select(AssetRepair).where(AssetRepair.id == r.id).execution_options(populate_existing=True))).scalar_one())


# ------------------------------------------------------------------ receiving


ITEM_KINDS = [RequestKind.supplies, RequestKind.asset, RequestKind.local_purchase]
RECEIVABLE = [S.approved, S.in_progress, S.awaiting_finance]


@router.get("/receiving/pending")
async def pending_deliveries(principal: Staff, session: Session) -> list[dict]:
    stmt = select(Request).where(Request.kind.in_(ITEM_KINDS), Request.status.in_(RECEIVABLE), Request.company_id.in_(principal.company_ids))
    out = []
    for req in (await session.execute(stmt.order_by(Request.needed_by.is_(None), Request.needed_by))).scalars():
        if not is_operator(principal, req):
            continue
        open_items = [i for i in req.items if i.received_quantity < i.quantity]
        if not open_items:
            continue
        out.append(
            {
                "request": {"id": req.id, "reference": req.reference, "subject": req.subject, "kind": req.kind, "status": req.status, "needed_by": day(req.needed_by), "requester": person(req.requester)},
                "items": [
                    {"id": i.id, "item_name": i.item_name, "brand": i.brand, "model": i.model, "quantity": i.quantity, "received_quantity": i.received_quantity, "unit": i.unit, "item_category": i.item_category}
                    for i in req.items
                ],
            }
        )
    return out


class ReceiptLine(BaseModel):
    item_id: int
    quantity: int = Field(..., ge=1, le=100000)
    register_asset: bool = False
    # Put the delivered quantity into an inventory stock line instead of (or as well as) registering assets.
    inventory_item_id: int | None = None
    category: str | None = Field(None, max_length=120)
    serial_numbers: list[str] = Field(default_factory=list, max_length=1000)


class ReceiptIn(BaseModel):
    request_id: int
    received_on: date | None = None
    delivery_reference: str | None = Field(None, max_length=120)
    supplier: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=4000)
    lines: list[ReceiptLine] = Field(..., min_length=1, max_length=200)


def receipt_out(r: Receipt, req: Request | None = None) -> dict:
    return {
        "id": r.id,
        "reference": r.reference,
        "request": {"id": req.id, "reference": req.reference, "subject": req.subject} if req else {"id": r.request_id},
        "received_by": person(r.received_by),
        "received_on": day(r.received_on),
        "delivery_reference": r.delivery_reference,
        "supplier": r.supplier,
        "notes": r.notes,
        "lines": r.lines,
        "created_at": iso(r.created_at),
    }


@router.post("/receiving", status_code=201)
async def receive(body: ReceiptIn, principal: Staff, session: Session) -> dict:
    req = (await session.execute(select(Request).where(Request.id == body.request_id).execution_options(populate_existing=True))).scalar_one_or_none()
    if req is None or req.company_id not in principal.company_ids or not is_operator(principal, req):
        raise not_found()
    if req.kind not in ITEM_KINDS:
        raise bad_request("Only item requests can be received")
    if req.status not in RECEIVABLE:
        raise conflict("Deliveries can be recorded only after approval and before fulfilment")
    if body.received_on and body.received_on > date.today():
        raise bad_request({"message": "Received date cannot be in the future", "fields": {"received_on": "In the future"}})
    items = {i.id: i for i in req.items}
    errors: dict[str, str] = {}
    seen_serials: set[str] = set()
    for idx, line in enumerate(body.lines):
        item = items.get(line.item_id)
        if item is None:
            errors[f"lines.{idx}.item_id"] = "Not an item of this request"
            continue
        remaining = item.quantity - item.received_quantity
        if line.quantity > remaining:
            errors[f"lines.{idx}.quantity"] = f"Only {remaining} {item.unit} still expected"
        serials = [s.strip().upper() for s in line.serial_numbers if s.strip()]
        if serials:
            if len(serials) != line.quantity:
                errors[f"lines.{idx}.serial_numbers"] = f"Enter {line.quantity} serial numbers, one per item"
            for s in serials:
                if s in seen_serials or await serial_taken(session, s):
                    errors[f"lines.{idx}.serial_numbers"] = f"Serial {s} is already registered"
                seen_serials.add(s)
        if line.register_asset and not (line.category or item.item_category):
            errors[f"lines.{idx}.category"] = "Choose a category to register it"
    if errors:
        raise bad_request({"message": "Some lines need attention", "fields": errors})

    receipt = Receipt(
        reference=await next_reference(session, "RCV"), company_id=req.company_id, request_id=req.id, received_by_id=principal.id,
        received_on=body.received_on or date.today(), delivery_reference=body.delivery_reference, supplier=body.supplier, notes=body.notes,
    )
    session.add(receipt)
    await session.flush()
    lines_out = []
    for line in body.lines:
        item = items[line.item_id]
        item.received_quantity += line.quantity
        registered = []
        if line.register_asset:
            serials = [s.strip().upper() for s in line.serial_numbers if s.strip()]
            batches = [(s, 1) for s in serials] if serials else [(None, line.quantity)]
            for serial, qty in batches:
                a = Asset(
                    reference=await next_reference(session, "AST"), company_id=req.company_id, department_id=req.department_id,
                    name=item.item_name, category=line.category or item.item_category or "Other", serial_number=serial,
                    brand=item.brand, model=item.model, quantity=qty, unit=item.unit, condition=AssetCondition.brand_new,
                    purchase_date=receipt.received_on, purchase_reference=body.delivery_reference or req.reference,
                    purpose=req.purpose, request_id=req.id,
                )
                session.add(a)
                await session.flush()
                await log(session, a, principal, "received", f"Received on {receipt.reference} for {req.reference}", data={"receipt": receipt.reference})
                registered.append({"id": a.id, "reference": a.reference, "serial_number": serial})
        stocked = None
        if line.inventory_item_id:
            from .inventory import stock_in_from_receipt

            await stock_in_from_receipt(session, principal, line.inventory_item_id, line.quantity, receipt.id, req.id)
            stocked = line.inventory_item_id
        lines_out.append({"item_id": item.id, "item_name": item.item_name, "quantity": line.quantity, "unit": item.unit, "assets": registered, "inventory_item_id": stocked})
    receipt.lines = lines_out
    complete = all(i.received_quantity >= i.quantity for i in req.items)
    req.fulfillment_status = "Received" if complete else "Partially received"
    req.version += 1
    summary = ", ".join(f"{l['quantity']} {l['unit']} {l['item_name']}" for l in lines_out)
    await request_event(session, req, principal, "received", f"{receipt.reference}: {summary}")
    await audit(session, actor_id=principal.id, action="receiving.record", entity_type="receipt", entity_id=receipt.id, entity_ref=receipt.reference, company_id=req.company_id, data={"request": req.reference, "lines": lines_out})
    await notify(session, {req.requester_id}, kind="fulfillment_confirmation", title=f"{'Delivered' if complete else 'Partly delivered'}: {req.reference}", body=summary, link=f"/r/{req.id}")
    await session.commit()
    return receipt_out(receipt, req)


@router.get("/receiving")
async def list_receipts(principal: Staff, session: Session, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)) -> dict:
    stmt = select(Receipt).where(Receipt.company_id.in_(principal.company_ids))
    total = await count(session, stmt)
    rows = (await session.execute(stmt.order_by(Receipt.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    reqs = {r.id: r for r in (await session.execute(select(Request).where(Request.id.in_([x.request_id for x in rows])))).scalars()} if rows else {}
    return {"items": [receipt_out(r, reqs.get(r.request_id)) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/asset-events")
async def asset_events(principal: Staff, session: Session, type: list[str] = Query(default_factory=list), page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)) -> dict:
    """Movement history across the register: assignments, returns, transfers."""
    stmt = select(AssetEvent).join(Asset, Asset.id == AssetEvent.asset_id).where(Asset.company_id.in_(principal.company_ids))
    if type:
        stmt = stmt.where(AssetEvent.type.in_(type))
    total = await count(session, stmt)
    rows = (await session.execute(stmt.order_by(AssetEvent.at.desc(), AssetEvent.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    assets = {a.id: a for a in (await session.execute(select(Asset).where(Asset.id.in_([e.asset_id for e in rows])))).scalars()} if rows else {}
    return {
        "items": [
            {
                "id": e.id, "type": e.type, "message": e.message, "actor": person(e.actor), "from_holder": person(e.from_holder), "to_holder": person(e.to_holder), "at": iso(e.at),
                "asset": {"id": e.asset_id, "reference": assets[e.asset_id].reference, "name": assets[e.asset_id].name},
            }
            for e in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }
