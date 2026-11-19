"""Phase 2.3 — asset registry, assignment, transfers, repairs and receiving proof."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.exc import IntegrityError

from ..core import audit, bad_request, conflict, forbidden, next_reference, not_found, notify, now
from ..models import Attachment, Employee, Request, RequestKind, RequestStatus as S
from ..models_ops import Asset, AssetCondition, AssetEvent, AssetRepair, AssetStatus, Receipt, RepairStatus
from ..ops_common import check_version, company_for, count, day, department_in, employee_in, money, scoped
from ..security import CurrentPrincipal, Principal, Session, Staff
from ..asset_ids import MAX_PER_REGISTRATION, clean_serials, ensure_serial, next_serial, serial_in_use
from ..serialize import attachment_out, iso, person
from .photos import not_photo, photo_url
from ..proofs import proof_out, proofs_for, save_proof
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
        "issue_ref": a.issue_ref,
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


class AssetCreate(AssetIn):
    # How many identical items to register. Each becomes its own record with its own serial number.
    count: int = Field(1, ge=1, le=MAX_PER_REGISTRATION)
    # Manufacturer serials, one per item, in order. Items without one get an automatic serial.
    serial_numbers: list[str] = Field(default_factory=list, max_length=MAX_PER_REGISTRATION)


class AssetPatch(AssetIn):
    version: int


def validate_asset(body: AssetIn):
    if body.purchase_date and body.purchase_date > date.today():
        raise bad_request({"message": "Purchase date cannot be in the future", "fields": {"purchase_date": "In the future"}})


async def serial_taken(session, serial: str | None, exclude: int | None = None) -> bool:
    return bool(serial) and await serial_in_use(session, serial, exclude)


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
    grouped: bool = False,
    sort: Literal["updated", "name", "category", "status", "holder", "condition"] = "updated",
    dir: Literal["asc", "desc"] | None = None,
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
    # Newest first by default; names and the rest A to Z.
    desc_ = (dir or ("desc" if sort == "updated" else "asc")) == "desc"
    holder_alias = aliased(Employee)
    if sort == "holder":
        stmt = stmt.outerjoin(holder_alias, holder_alias.id == Asset.holder_id)
    col = {
        "updated": Asset.updated_at, "name": func.lower(Asset.name), "category": Asset.category, "status": Asset.status,
        "condition": Asset.condition, "holder": func.lower(holder_alias.name),
    }[sort]
    order = (col.desc() if desc_ else col.asc(), Asset.id.desc() if desc_ else Asset.id.asc())
    if grouped:
        # One entry per issuance (same items handed to one person together), and one per set of
        # identical items not issued to anyone. Each entry lists its members.
        groups: dict[tuple, list[Asset]] = {}
        for a in (await session.execute(stmt.order_by(*order))).scalars():
            key = ("issue", a.issue_ref) if a.holder_id and a.issue_ref else ("one", a.id) if a.holder_id else ("stock", a.company_id, a.name.strip().lower(), a.category, a.status, a.condition)
            groups.setdefault(key, []).append(a)
        entries = list(groups.values())
        page_rows = entries[(page - 1) * page_size : page * page_size]
        items = []
        for g in page_rows:
            g.sort(key=lambda x: x.id)
            out = asset_out(g[0])
            if len(g) > 1:
                out["group"] = {"count": len(g), "members": [{"id": x.id, "reference": x.reference, "serial_number": x.serial_number, "acknowledged": bool(x.acknowledged_at)} for x in g]}
            items.append(out)
        total, rows = len(entries), None
    else:
        total = await count(session, stmt)
        rows = (await session.execute(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size))).scalars()
        items = [asset_out(a) for a in rows]
    summary = {}
    for st in AssetStatus:
        summary[st.value] = await count(session, select(Asset).where(Asset.company_id.in_(principal.company_ids), Asset.status == st))
    summary["unacknowledged"] = await count(
        session, select(Asset).where(Asset.company_id.in_(principal.company_ids), Asset.holder_id.is_not(None), Asset.acknowledged_at.is_(None))
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size, "summary": summary}


@router.post("/assets", status_code=201)
async def create_asset(body: AssetCreate, principal: Staff, session: Session) -> dict:
    """Register one or more identical items. Each gets its own record and serial number, so each can be issued on its own."""
    validate_asset(body)
    cid = await company_for(session, principal, body.company_id)
    await department_in(session, body.department_id, cid)
    # Older clients sent "quantity" for several identical items: treat it as the number of records.
    n = body.count if body.count > 1 or body.quantity <= 1 else min(body.quantity, MAX_PER_REGISTRATION)
    serials = clean_serials(body.serial_numbers) or clean_serials([body.serial_number] if body.serial_number else [])
    if len(serials) > n:
        raise bad_request({"message": f"{len(serials)} serial numbers for {n} item{'s' if n != 1 else ''}: remove the extra ones or raise the quantity", "fields": {"serial_numbers": f"At most {n}"}})
    dupes = sorted({x for x in serials if serials.count(x) > 1})
    if dupes:
        raise bad_request({"message": f"Serial {dupes[0]} is entered twice", "fields": {"serial_numbers": "Each serial once"}})
    for sn in serials:
        if await serial_taken(session, sn):
            raise conflict(f"Serial number {sn} is already registered")
    data = body.model_dump(exclude={"company_id", "count", "serial_numbers", "serial_number", "quantity"})
    created: list[Asset] = []
    for idx in range(n):
        a = Asset(reference=await next_reference(session, "AST"), company_id=cid, quantity=1, serial_number=serials[idx] if idx < len(serials) else None, **data)
        await ensure_serial(session, a)
        session.add(a)
        try:
            await session.flush()
        except IntegrityError:
            raise conflict(f"Serial number {a.serial_number} is already registered")
        note = f"Registered as {CONDITION_LABEL[a.condition]}" + (f" (item {idx + 1} of {n})" if n > 1 else "")
        await log(session, a, principal, "registered", note, data={"serial": a.serial_number, "automatic_serial": idx >= len(serials)})
        created.append(a)
    await session.commit()
    first = asset_out(await scoped(session, Asset, created[0].id, principal))
    return {**first, "created": [{"id": a.id, "reference": a.reference, "serial_number": a.serial_number} for a in created]}


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
    together = []
    if a.holder_id and a.issue_ref:
        together = (await session.execute(select(Asset).where(Asset.issue_ref == a.issue_ref, Asset.holder_id == a.holder_id).order_by(Asset.id))).scalars().all()
    spare = 0
    if staff and not a.holder_id and a.status == AssetStatus.in_stock:
        spare = await count(session, identical_in_stock(a))
    ev_list = list(events)
    proofs = await proofs_for(session, "asset_event", [e.id for e in ev_list])
    return {
        **asset_out(a),
        "issued_together": [{"id": x.id, "reference": x.reference, "name": x.name, "serial_number": x.serial_number, "acknowledged": bool(x.acknowledged_at)} for x in together] if len(together) > 1 else [],
        "identical_in_stock": spare,
        "events": [
            {"id": e.id, "type": e.type, "message": e.message, "actor": person(e.actor), "from_holder": person(e.from_holder), "to_holder": person(e.to_holder), "at": iso(e.at), "proofs": proofs.get(e.id, [])}
            for e in ev_list
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
    if not body.serial_number:  # cleared: keep the current one (every asset has a serial)
        body.serial_number = a.serial_number or await next_serial(session, a.company_id, body.category)
    for k, v in body.model_dump(exclude={"company_id", "version", "quantity", "unit"}).items():
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
    # Hand over this item and (count - 1) identical ones still in stock, as one issuance.
    count: int = Field(1, ge=1, le=MAX_PER_REGISTRATION)
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


def identical_in_stock(a: Asset):
    """Other records of the same item, in stock and not issued: they can be handed over together."""
    return select(Asset).where(
        Asset.company_id == a.company_id, Asset.id != a.id, Asset.name == a.name, Asset.category == a.category,
        Asset.status == AssetStatus.in_stock, Asset.holder_id.is_(None),
    )


async def issue_together(session, principal: Principal, assets: list[Asset], emp: Employee, *, when: date, condition=None, note: str | None = None) -> str:
    """Hand one or more items to one person as a single issuance: one reference, one notification,
    one acknowledgement and one issuance form for the set."""
    ref = await next_reference(session, "ISS")
    n = len(assets)
    for a in assets:
        a.holder_id = emp.id
        a.issued_by_id = principal.id
        a.date_issued = when
        a.acknowledged_at = None
        a.issue_ref = ref
        a.status = AssetStatus.assigned
        if condition:
            a.condition = condition
        if emp.department_id:
            a.department_id = emp.department_id
        a.version += 1
        msg = note or f"Issued to {emp.name}"
        await log(session, a, principal, "assigned", msg + (f" ({ref}, {n} items)" if n > 1 else f" ({ref})"), to=emp.id, data={"condition": a.condition, "issue_ref": ref, "items": n})
    first = assets[0]
    what = f"{first.name} × {n}" if n > 1 else first.name
    serials = f"{assets[0].serial_number} to {assets[-1].serial_number}" if n > 1 else first.reference
    await notify(
        session, {emp.id}, kind="task_assignment", title=f"Please acknowledge: {what}",
        body=f"{ref}: {serials} {'were' if n > 1 else 'was'} issued to you. Confirm you received {'them' if n > 1 else 'it'}.", link=f"/asset/{first.id}",
    )
    return ref


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
    items = [a]
    if body.count > 1:
        others = (await session.execute(identical_in_stock(a).order_by(Asset.id).limit(body.count - 1))).scalars().all()
        if len(others) < body.count - 1:
            have = len(others) + 1
            raise bad_request({"message": f"Only {have} of these {'is' if have == 1 else 'are'} in stock", "fields": {"count": f"At most {have}"}})
        items += list(others)
    await issue_together(session, principal, items, emp, when=body.date_issued or date.today(), condition=body.condition, note=body.note)
    await session.commit()
    return await asset_detail(session, principal, await scoped(session, Asset, a.id, principal))


class BulkIssueIn(BaseModel):
    asset_ids: list[int] = Field(..., min_length=1, max_length=MAX_PER_REGISTRATION)
    employee_id: int
    date_issued: date | None = None
    condition: AssetCondition | None = None
    note: str | None = Field(None, max_length=2000)


@router.post("/assets/issue")
async def issue_selected(body: BulkIssueIn, principal: Staff, session: Session) -> dict:
    """Hand the selected items to one person as one issuance: one acknowledgement, one issuance form."""
    ids = list(dict.fromkeys(body.asset_ids))
    items = [await scoped(session, Asset, i, principal) for i in ids]
    if len({a.company_id for a in items}) > 1:
        raise bad_request({"message": "Choose items from one company at a time"})
    blocked = [a.reference for a in items if a.holder_id or a.status != AssetStatus.in_stock]
    if blocked:
        raise conflict(f"Only items in stock can be issued. Not available: {', '.join(blocked[:5])}{'…' if len(blocked) > 5 else ''}")
    if body.date_issued and body.date_issued > date.today():
        raise bad_request({"message": "Issue date cannot be in the future", "fields": {"date_issued": "In the future"}})
    emp = await employee_in(session, body.employee_id, items[0].company_id, "employee_id")
    items.sort(key=lambda a: a.id)
    ref = await issue_together(session, principal, items, emp, when=body.date_issued or date.today(), condition=body.condition, note=body.note)
    await session.flush()
    ev = (await session.execute(select(AssetEvent).where(AssetEvent.asset_id == items[0].id).order_by(AssetEvent.id.desc()).limit(1))).scalar_one()
    await session.commit()
    return {"issue_ref": ref, "count": len(items), "first_id": items[0].id, "event_id": ev.id, "holder": person(emp)}


@router.post("/assets/{asset_id}/acknowledge")
async def acknowledge(asset_id: int, principal: CurrentPrincipal, session: Session) -> dict:
    a = await load_asset_for(session, principal, asset_id)
    if a.holder_id != principal.id:
        raise forbidden("Only the person holding this asset can acknowledge it")
    if a.acknowledged_at:
        raise conflict("Already acknowledged")
    # Everything handed over together is acknowledged together.
    items = [a]
    if a.issue_ref:
        items = (await session.execute(select(Asset).where(Asset.issue_ref == a.issue_ref, Asset.holder_id == principal.id, Asset.acknowledged_at.is_(None)).order_by(Asset.id))).scalars().all()
    at = now()
    for x in items:
        x.acknowledged_at = at
        x.version += 1
        await log(session, x, principal, "acknowledged", "Receipt acknowledged by holder" + (f" ({a.issue_ref}, {len(items)} items)" if len(items) > 1 else ""))
    if a.issued_by_id:
        what = f"{a.name} × {len(items)}" if len(items) > 1 else a.name
        await notify(session, {a.issued_by_id}, kind="fulfillment_confirmation", title=f"Acknowledged: {what}", body=f"{principal.employee.name} confirmed receipt of {a.issue_ref or a.reference}.", link=f"/asset/{a.id}")
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
    a.issue_ref = None
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
        a.issue_ref = await next_reference(session, "ISS")
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
            if len(serials) > line.quantity:
                errors[f"lines.{idx}.serial_numbers"] = f"{len(serials)} serial numbers for {line.quantity} items"
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
            serials = clean_serials(line.serial_numbers)
            for n in range(line.quantity):
                serial, qty = (serials[n] if n < len(serials) else None), 1
                a = Asset(
                    reference=await next_reference(session, "AST"), company_id=req.company_id, department_id=req.department_id,
                    name=item.item_name, category=line.category or item.item_category or "Other", serial_number=serial,
                    brand=item.brand, model=item.model, quantity=qty, unit=item.unit, condition=AssetCondition.brand_new,
                    purchase_date=receipt.received_on, purchase_reference=body.delivery_reference or req.reference,
                    purpose=req.purpose, request_id=req.id,
                )
                await ensure_serial(session, a)
                session.add(a)
                await session.flush()
                await log(session, a, principal, "received", f"Received on {receipt.reference} for {req.reference}", data={"receipt": receipt.reference})
                registered.append({"id": a.id, "reference": a.reference, "serial_number": a.serial_number})
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


# ------------------------------------------------------------------ consumables registered as assets
# Things counted in pieces (clips, pens, tumblers) don't need one record and serial per piece.
# This moves every record of the item into Consumables & Stock as one stock line: the pieces in stock
# become its balance, and pieces already issued are recorded as issued to their holders, by quantity.


class ToStockIn(BaseModel):
    unit: str = Field("pc", min_length=1, max_length=40)
    location: str = Field(..., min_length=1, max_length=120)


async def _same_item(session, a: Asset) -> list[Asset]:
    rows = (await session.execute(select(Asset).where(Asset.company_id == a.company_id, Asset.category == a.category, Asset.status != AssetStatus.retired).order_by(Asset.id))).scalars().all()
    key = a.name.strip().lower()
    return [x for x in rows if x.name.strip().lower() == key]


async def _to_stock_plan(session, a: Asset) -> dict:
    group = await _same_item(session, a)
    ids = [x.id for x in group]
    blocked = None
    if any(x.status == AssetStatus.under_repair for x in group):
        blocked = "One of them is under repair. Finish the repair first."
    elif (await session.execute(select(AssetRepair.id).where(AssetRepair.asset_id.in_(ids)).limit(1))).first():
        blocked = "One of them has a repair history, so it stays an asset."
    holders: dict[int, dict] = {}
    for x in group:
        if x.holder_id:
            h = holders.setdefault(x.holder_id, {"holder": person(x.holder), "quantity": 0})
            h["quantity"] += 1
    return {
        "group": group,
        "out": {
            "name": a.name, "count": len(group), "in_stock": sum(1 for x in group if not x.holder_id),
            "issued": list(holders.values()), "location": next((x.location for x in group if x.location), None), "blocked": blocked,
        },
    }


@router.get("/assets/{asset_id}/to-stock")
async def to_stock_preview(asset_id: int, principal: Staff, session: Session) -> dict:
    a = await scoped(session, Asset, asset_id, principal)
    return (await _to_stock_plan(session, a))["out"]


@router.post("/assets/{asset_id}/to-stock")
async def to_stock(asset_id: int, body: ToStockIn, principal: Staff, session: Session) -> dict:
    from ..models_ops3 import InventoryItem
    from .inventory import can_adjust, drop_assets, move, next_item_code, rehome_files

    if not can_adjust(principal):
        raise forbidden("Moving items into Consumables & Stock needs Admin or delegated inventory control")
    a = await scoped(session, Asset, asset_id, principal)
    plan = await _to_stock_plan(session, a)
    if plan["out"]["blocked"]:
        raise conflict(plan["out"]["blocked"])
    group: list[Asset] = plan["group"]
    location = body.location.strip()
    # Join an existing stock line of the same item at that location, or start one.
    item = None
    for i in (await session.execute(select(InventoryItem).where(InventoryItem.company_id == a.company_id, InventoryItem.location == location))).scalars():
        if i.name.strip().lower() == a.name.strip().lower():
            item = i
            break
    if item is None:
        item = InventoryItem(
            company_id=a.company_id, item_code=await next_item_code(session, a.company_id, "Consumables"), name=a.name.strip(), category="Consumables",
            brand=a.brand, model=a.model, unit=body.unit.strip(), location=location, on_hand=0, reserved=0, reorder_level=0, reorder_quantity=0,
        )
        session.add(item)
        await session.flush()
    first, last = group[0].reference, group[-1].reference
    await move(session, principal, item, "stock_in", len(group), reason=f"Moved from the asset registry ({first}{' to ' + last if len(group) > 1 else ''})")
    by_holder: dict[int, list[Asset]] = {}
    for x in group:
        if x.holder_id:
            by_holder.setdefault(x.holder_id, []).append(x)
    for holder_id, xs in by_holder.items():
        refs = sorted({x.issue_ref for x in xs if x.issue_ref})
        note = "Issued earlier" + (f" ({', '.join(refs)})" if refs else "")
        await move(session, principal, item, "issue", -len(xs), reason=note, issued_to_id=holder_id)
    # Photos and files go with it. The same photo saved on every record is kept once.
    await rehome_files(session, [x.id for x in group], item)
    await audit(
        session, actor_id=principal.id, action="asset.moved_to_stock", entity_type="inventory_item", entity_id=item.id, entity_ref=item.item_code, company_id=item.company_id,
        data={"assets": [x.reference for x in group], "serials": [x.serial_number for x in group], "issued": {str(k): len(v) for k, v in by_holder.items()}},
    )
    await drop_assets(session, group)
    await session.commit()
    return {"item_id": item.id, "item_code": item.item_code, "moved": len(group), "issued": sum(len(v) for v in by_holder.values())}


@router.get("/me/supplies")
async def my_supplies(principal: CurrentPrincipal, session: Session) -> list[dict]:
    """Consumables handed to me and brought back, by quantity (from the stock cards)."""
    from ..models_ops3 import InventoryItem, StockMovement

    rows = (await session.execute(select(StockMovement).where(StockMovement.issued_to_id == principal.id, StockMovement.kind.in_(["issue", "return"])).order_by(StockMovement.id.desc()).limit(100))).scalars().all()
    items = {i.id: i for i in (await session.execute(select(InventoryItem).where(InventoryItem.id.in_([m.item_id for m in rows] or [0])))).scalars()}
    return [
        {"id": m.id, "reference": m.reference, "name": items[m.item_id].name, "item_code": items[m.item_id].item_code, "photo": photo_url(items[m.item_id].photo_id),
         "kind": m.kind, "quantity": abs(m.quantity), "unit": items[m.item_id].unit, "note": m.reason, "at": iso(m.at), "by": person(m.actor)}
        for m in rows
    ]


# ------------------------------------------------------------------ one history entry, with photo proof


@router.get("/assets/events/{event_id}")
async def get_asset_event(event_id: int, principal: CurrentPrincipal, session: Session) -> dict:
    e = await session.get(AssetEvent, event_id)
    if e is None:
        raise not_found()
    a = await load_asset_for(session, principal, e.asset_id)
    staff = principal.is_staff and a.company_id in principal.company_ids
    return {
        "id": e.id, "type": e.type, "message": e.message, "actor": person(e.actor), "from_holder": person(e.from_holder), "to_holder": person(e.to_holder), "at": iso(e.at),
        "data": {k: v for k, v in (e.data or {}).items() if k in ("condition", "issue_ref", "items", "reason")},
        "asset": {"id": a.id, "reference": a.reference, "name": a.name, "serial_number": a.serial_number, "photo": photo_url(a.photo_id)},
        "proofs": (await proofs_for(session, "asset_event", [e.id])).get(e.id, []),
        "can_add_proof": staff or a.holder_id == principal.id,
    }


@router.post("/assets/events/{event_id}/proof", status_code=201)
async def add_asset_event_proof(event_id: int, principal: CurrentPrincipal, session: Session, file: UploadFile = File(...), meta: str | None = Form(None)) -> dict:
    e = await session.get(AssetEvent, event_id)
    if e is None:
        raise not_found()
    a = await load_asset_for(session, principal, e.asset_id)
    if not (principal.is_staff and a.company_id in principal.company_ids) and a.holder_id != principal.id:
        raise forbidden("Only Executive Admin staff or the person holding it can add photos")
    att = await save_proof(session, principal, "asset_event", e.id, a.reference, file, meta)
    await audit(session, actor_id=principal.id, action="asset.proof_add", entity_type="asset", entity_id=a.id, entity_ref=a.reference, company_id=a.company_id, data={"event": e.id, "photo": att.id, "source": att.meta.get("source")})
    await session.commit()
    return proof_out(att)
