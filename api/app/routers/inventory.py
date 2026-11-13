"""Phase 2.3a — equipment inventory: stock lines, movements, reservations, reorders and counts."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from ..core import admin_ids, audit, bad_request, conflict, forbidden, next_reference, not_found, notify, now
from ..models import Request, RequestItem, RequestKind, RequestStatus as S
from ..models_ops import Asset, AssetCondition, AssetEvent, AssetStatus
from ..models_ops3 import INV_CATEGORIES, InventoryCount, InventoryItem, StockMovement, StockReservation
from ..ops_common import check_version, company_for, count, day, employee_in, money, scoped
from ..security import Principal, Session, Staff
from ..serialize import iso, person
from .photos import photo_url
from ..workflow import event as request_event, is_operator

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


def can_adjust(p: Principal) -> bool:
    """Item set-up, adjustments and count posting: Admin, or an Assistant delegated inventory control."""
    return p.is_admin or (p.is_staff and p.delegated("inventory_adjust"))


def item_out(i: InventoryItem) -> dict:
    return {
        "id": i.id, "photo": photo_url(i.photo_id), "company": {"id": i.company.id, "code": i.company.code}, "item_code": i.item_code, "name": i.name, "category": i.category,
        "brand": i.brand, "model": i.model, "unit": i.unit, "location": i.location, "on_hand": i.on_hand, "reserved": i.reserved,
        "available": i.available, "reorder_level": i.reorder_level, "reorder_quantity": i.reorder_quantity, "unit_cost_php": money(i.unit_cost_php),
        "value_php": money((i.unit_cost_php or Decimal(0)) * i.on_hand), "supplier": i.supplier, "serialized_on_issue": i.serialized_on_issue,
        "last_counted_on": day(i.last_counted_on), "status": i.status, "remarks": i.remarks, "low": i.status == "active" and i.available <= i.reorder_level,
        "version": i.version, "updated_at": iso(i.updated_at),
    }


def movement_out(m: StockMovement) -> dict:
    return {
        "id": m.id, "reference": m.reference, "item_id": m.item_id, "kind": m.kind, "quantity": m.quantity, "balance_after": m.balance_after,
        "request_id": m.request_id, "receipt_id": m.receipt_id, "issued_to": person(m.issued_to), "reason": m.reason, "actor": person(m.actor), "at": iso(m.at),
    }


async def move(session, principal: Principal, item: InventoryItem, kind: str, qty: int, *, reason=None, request_id=None, receipt_id=None, issued_to_id=None, counterpart=None) -> StockMovement:
    """Single place that changes on_hand. Refuses to go negative or below what is reserved."""
    new = item.on_hand + qty
    if new < 0:
        raise conflict(f"Only {item.on_hand} {item.unit} on hand at {item.location}")
    if qty < 0 and new < item.reserved:
        raise conflict(f"{item.reserved} {item.unit} are reserved for requests; release them first")
    item.on_hand = new
    item.version += 1
    m = StockMovement(
        reference=await next_reference(session, "INV"), item_id=item.id, company_id=item.company_id, kind=kind, quantity=qty, balance_after=new,
        request_id=request_id, receipt_id=receipt_id, issued_to_id=issued_to_id, counterpart_item_id=counterpart, reason=reason, actor_id=principal.id,
    )
    session.add(m)
    await audit(session, actor_id=principal.id, action=f"inventory.{kind}", entity_type="inventory_item", entity_id=item.id, entity_ref=item.item_code, company_id=item.company_id, data={"quantity": qty, "balance": new, "location": item.location, "reason": reason})
    return m


@router.get("/options")
async def options(principal: Staff, session: Session) -> dict:
    locs = sorted({x for (x,) in (await session.execute(select(InventoryItem.location).where(InventoryItem.company_id.in_(principal.company_ids)))).all()})
    return {"categories": INV_CATEGORIES, "locations": locs, "can_adjust": can_adjust(principal), "can_write_off": principal.is_admin}


# ------------------------------------------------------------------ items


class ItemIn(BaseModel):
    company_id: int | None = None
    item_code: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=300)
    category: str = "Equipment"
    brand: str | None = Field(None, max_length=120)
    model: str | None = Field(None, max_length=120)
    unit: str = Field("pc", min_length=1, max_length=40)
    location: str = Field(..., min_length=1, max_length=120)
    opening_quantity: int = Field(0, ge=0, le=10_000_000)
    reorder_level: int = Field(0, ge=0, le=10_000_000)
    reorder_quantity: int = Field(0, ge=0, le=10_000_000)
    unit_cost_php: Decimal | None = Field(None, ge=0, le=Decimal("99999999"))
    supplier: str | None = Field(None, max_length=200)
    serialized_on_issue: bool = False
    status: Literal["active", "discontinued"] = "active"
    remarks: str | None = Field(None, max_length=4000)

    @field_validator("item_code")
    @classmethod
    def code(cls, v):
        return v.strip().upper()

    @field_validator("location")
    @classmethod
    def loc(cls, v):
        return v.strip()

    @field_validator("category")
    @classmethod
    def cat(cls, v):
        if v not in INV_CATEGORIES:
            raise ValueError(f"Category must be one of: {', '.join(INV_CATEGORIES)}")
        return v


class ItemPatch(ItemIn):
    version: int


@router.get("/items")
async def list_items(
    principal: Staff, session: Session, q: str | None = Query(None, max_length=200), category: str | None = None, location: str | None = None,
    low: bool = False, status: str | None = "active", page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
) -> dict:
    stmt = select(InventoryItem).where(InventoryItem.company_id.in_(principal.company_ids))
    if category:
        stmt = stmt.where(InventoryItem.category == category)
    if location:
        stmt = stmt.where(InventoryItem.location == location)
    if status:
        stmt = stmt.where(InventoryItem.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(InventoryItem.item_code.ilike(like), InventoryItem.name.ilike(like), InventoryItem.brand.ilike(like), InventoryItem.model.ilike(like)))
    rows = list((await session.execute(stmt.order_by(InventoryItem.name, InventoryItem.location))).scalars())
    if low:
        rows = [i for i in rows if i.available <= i.reorder_level]
    everything = list((await session.execute(select(InventoryItem).where(InventoryItem.company_id.in_(principal.company_ids), InventoryItem.status == "active"))).scalars())
    summary = {
        "lines": len(everything),
        "low": sum(1 for i in everything if i.available <= i.reorder_level),
        "reserved": sum(i.reserved for i in everything),
        "value_php": money(sum(((i.unit_cost_php or Decimal(0)) * i.on_hand for i in everything), Decimal(0))),
    }
    return {"items": [item_out(i) for i in rows[(page - 1) * page_size : page * page_size]], "total": len(rows), "page": page, "page_size": page_size, "summary": summary}


@router.post("/items", status_code=201)
async def create_item(body: ItemIn, principal: Staff, session: Session) -> dict:
    if not can_adjust(principal):
        raise forbidden("Setting up inventory items needs Admin or delegated inventory control")
    cid = await company_for(session, principal, body.company_id)
    dup = await session.execute(select(InventoryItem.id).where(InventoryItem.company_id == cid, InventoryItem.item_code == body.item_code, InventoryItem.location == body.location))
    if dup.first():
        raise conflict(f"{body.item_code} already has a stock line at {body.location}")
    i = InventoryItem(company_id=cid, on_hand=0, reserved=0, **body.model_dump(exclude={"company_id", "opening_quantity"}))
    session.add(i)
    try:
        await session.flush()
    except IntegrityError:
        raise conflict(f"{body.item_code} already has a stock line at {body.location}")
    if body.opening_quantity:
        await move(session, principal, i, "stock_in", body.opening_quantity, reason="Opening balance")
    await audit(session, actor_id=principal.id, action="inventory.item_create", entity_type="inventory_item", entity_id=i.id, entity_ref=i.item_code, company_id=cid, data={"location": i.location})
    await session.commit()
    return item_out(await scoped(session, InventoryItem, i.id, principal))


@router.get("/items/{item_id}")
async def get_item(item_id: int, principal: Staff, session: Session) -> dict:
    i = await scoped(session, InventoryItem, item_id, principal)
    moves = (await session.execute(select(StockMovement).where(StockMovement.item_id == i.id).order_by(StockMovement.id.desc()).limit(200))).scalars()
    res = (await session.execute(select(StockReservation).where(StockReservation.item_id == i.id, StockReservation.status == "reserved"))).scalars().all()
    reqs = {r.id: r for r in (await session.execute(select(Request).where(Request.id.in_([x.request_id for x in res] or [0])))).scalars()}
    other = (await session.execute(select(InventoryItem).where(InventoryItem.company_id == i.company_id, InventoryItem.item_code == i.item_code, InventoryItem.id != i.id))).scalars()
    return {
        **item_out(i),
        "movements": [movement_out(m) for m in moves],
        "reservations": [{"id": r.id, "quantity": r.quantity, "request": {"id": r.request_id, "reference": reqs[r.request_id].reference, "subject": reqs[r.request_id].subject, "requester": person(reqs[r.request_id].requester)}} for r in res],
        "other_locations": [{"id": o.id, "location": o.location, "on_hand": o.on_hand, "available": o.available} for o in other],
        "can_adjust": can_adjust(principal),
        "can_write_off": principal.is_admin,
    }


@router.patch("/items/{item_id}")
async def update_item(item_id: int, body: ItemPatch, principal: Staff, session: Session) -> dict:
    if not can_adjust(principal):
        raise forbidden("Editing inventory items needs Admin or delegated inventory control")
    i = await scoped(session, InventoryItem, item_id, principal)
    check_version(i, body.version)
    if body.item_code != i.item_code or body.location != i.location:
        dup = await session.execute(select(InventoryItem.id).where(InventoryItem.company_id == i.company_id, InventoryItem.item_code == body.item_code, InventoryItem.location == body.location, InventoryItem.id != i.id))
        if dup.first():
            raise conflict(f"{body.item_code} already has a stock line at {body.location}")
        if body.location != i.location and i.on_hand:
            raise bad_request({"message": "Use a transfer to move stock to another location", "fields": {"location": "Use transfer"}})
    changed = {}
    for k, v in body.model_dump(exclude={"company_id", "version", "opening_quantity"}).items():
        if getattr(i, k) != v:
            changed[k] = str(v)
            setattr(i, k, v)
    i.version += 1
    await audit(session, actor_id=principal.id, action="inventory.item_update", entity_type="inventory_item", entity_id=i.id, entity_ref=i.item_code, company_id=i.company_id, data=changed)
    await session.commit()
    return item_out(await scoped(session, InventoryItem, i.id, principal))


class MoveIn(BaseModel):
    kind: Literal["stock_in", "issue", "return", "transfer", "adjustment", "write_off"]
    quantity: int = Field(..., ge=1, le=10_000_000)
    direction: Literal["add", "remove"] = "add"  # adjustments only
    issued_to_id: int | None = None
    to_location: str | None = Field(None, max_length=120)
    reason: str | None = Field(None, max_length=2000)


@router.post("/items/{item_id}/move")
async def move_stock(item_id: int, body: MoveIn, principal: Staff, session: Session) -> dict:
    i = await scoped(session, InventoryItem, item_id, principal)
    if i.status == "discontinued" and body.kind in ("stock_in", "return"):
        raise conflict("This item is discontinued")
    reason = (body.reason or "").strip() or None
    if body.kind in ("adjustment", "write_off") and not reason:
        raise bad_request({"message": "A reason is required", "fields": {"reason": "Required"}})
    if body.kind == "adjustment" and not can_adjust(principal):
        raise forbidden("Adjustments need Admin or delegated inventory control")
    if body.kind == "write_off" and not principal.is_admin:
        raise forbidden("Only Admin can write off stock")
    if body.kind == "issue":
        if body.issued_to_id is None:
            raise bad_request({"message": "Choose who receives it", "fields": {"issued_to_id": "Required"}})
        if body.quantity > i.available:
            raise conflict(f"Only {i.available} {i.unit} available ({i.reserved} reserved)")
        emp = await employee_in(session, body.issued_to_id, i.company_id, "issued_to_id")
        await move(session, principal, i, "issue", -body.quantity, reason=reason, issued_to_id=emp.id)
        await issue_assets(session, principal, i, body.quantity, emp.id, None)
    elif body.kind == "transfer":
        dest_loc = (body.to_location or "").strip()
        if not dest_loc or dest_loc == i.location:
            raise bad_request({"message": "Choose a different location", "fields": {"to_location": "Required"}})
        if body.quantity > i.available:
            raise conflict(f"Only {i.available} {i.unit} available to transfer")
        dest = (await session.execute(select(InventoryItem).where(InventoryItem.company_id == i.company_id, InventoryItem.item_code == i.item_code, InventoryItem.location == dest_loc))).scalar_one_or_none()
        if dest is None:
            dest = InventoryItem(
                company_id=i.company_id, item_code=i.item_code, name=i.name, category=i.category, brand=i.brand, model=i.model, unit=i.unit, location=dest_loc,
                on_hand=0, reserved=0, reorder_level=0, reorder_quantity=0, unit_cost_php=i.unit_cost_php, supplier=i.supplier, serialized_on_issue=i.serialized_on_issue,
            )
            session.add(dest)
            await session.flush()
        await move(session, principal, i, "transfer_out", -body.quantity, reason=reason or f"To {dest_loc}", counterpart=dest.id)
        await move(session, principal, dest, "transfer_in", body.quantity, reason=reason or f"From {i.location}", counterpart=i.id)
    elif body.kind == "adjustment":
        await move(session, principal, i, "adjustment", body.quantity if body.direction == "add" else -body.quantity, reason=reason)
    elif body.kind == "write_off":
        await move(session, principal, i, "write_off", -body.quantity, reason=reason)
    else:  # stock_in, return
        await move(session, principal, i, body.kind, body.quantity, reason=reason)
    await session.commit()
    return await get_item(i.id, principal, session)


async def issue_assets(session, principal: Principal, item: InventoryItem, qty: int, holder_id: int, request: Request | None):
    """Serialized-on-issue items become individual asset records held by the recipient."""
    if not item.serialized_on_issue:
        return
    for _ in range(qty):
        a = Asset(
            reference=await next_reference(session, "AST"), company_id=item.company_id, name=item.name, category="IT equipment" if item.category == "Equipment" else "Other",
            brand=item.brand, model=item.model, quantity=1, unit=item.unit, condition=AssetCondition.brand_new, status=AssetStatus.assigned, holder_id=holder_id,
            issued_by_id=principal.id, date_issued=date.today(), purchase_reference=item.item_code, request_id=request.id if request else None,
        )
        session.add(a)
        await session.flush()
        session.add(AssetEvent(asset_id=a.id, type="assigned", message=f"Issued from inventory {item.item_code} ({item.location})", actor_id=principal.id, to_holder_id=holder_id))
        await notify(session, {holder_id}, kind="task_assignment", title=f"Please acknowledge: {a.name}", body=f"{a.reference} was issued to you.", link=f"/asset/{a.id}")


# ------------------------------------------------------------------ requests to fill (reserve / issue)


ITEM_KINDS = [RequestKind.supplies, RequestKind.asset, RequestKind.local_purchase]


@router.get("/requests")
async def requests_to_fill(principal: Staff, session: Session) -> list[dict]:
    rows = (await session.execute(select(Request).where(Request.kind.in_(ITEM_KINDS), Request.status.in_([S.approved, S.in_progress]), Request.company_id.in_(principal.company_ids)))).scalars().all()
    out = []
    for req in rows:
        if not is_operator(principal, req):
            continue
        res = (await session.execute(select(StockReservation).where(StockReservation.request_id == req.id, StockReservation.status != "released"))).scalars().all()
        lines = []
        for it in req.items:
            mine = [r for r in res if r.request_item_id == it.id]
            covered = sum(r.quantity for r in mine)
            stock = (await session.execute(select(InventoryItem).where(InventoryItem.company_id == req.company_id, InventoryItem.status == "active", or_(InventoryItem.name.ilike(f"%{it.item_name}%"), InventoryItem.item_code.ilike(it.item_name))))).scalars().all()
            lines.append({
                "id": it.id, "item_name": it.item_name, "quantity": it.quantity, "unit": it.unit, "covered": covered, "received": it.received_quantity,
                "reservations": [{"id": r.id, "quantity": r.quantity, "status": r.status, "item_id": r.item_id} for r in mine],
                "matches": [{"id": s.id, "item_code": s.item_code, "name": s.name, "location": s.location, "available": s.available, "unit": s.unit} for s in stock],
            })
        if any(l["covered"] < l["quantity"] for l in lines) or any(r["status"] == "reserved" for l in lines for r in l["reservations"]):
            out.append({"request": {"id": req.id, "reference": req.reference, "subject": req.subject, "requester": person(req.requester), "status": req.status}, "lines": lines})
    return out


class ReserveIn(BaseModel):
    request_item_id: int
    item_id: int
    quantity: int = Field(..., ge=1, le=10_000_000)


@router.post("/reserve", status_code=201)
async def reserve(body: ReserveIn, principal: Staff, session: Session) -> dict:
    ri = await session.get(RequestItem, body.request_item_id)
    if ri is None:
        raise not_found()
    req = await session.get(Request, ri.request_id)
    if req.company_id not in principal.company_ids or not is_operator(principal, req):
        raise not_found()
    if req.status not in (S.approved, S.in_progress):
        raise conflict("Only approved requests can reserve stock")
    i = await scoped(session, InventoryItem, body.item_id, principal)
    if i.company_id != req.company_id:
        raise bad_request({"message": "That stock belongs to another company", "fields": {"item_id": "Wrong company"}})
    already = sum(r.quantity for r in (await session.execute(select(StockReservation).where(StockReservation.request_item_id == ri.id, StockReservation.status != "released"))).scalars())
    if already + body.quantity > ri.quantity:
        raise conflict(f"The request asks for {ri.quantity} {ri.unit}; {already} already covered")
    if body.quantity > i.available:
        raise conflict(f"Only {i.available} {i.unit} available at {i.location}")
    r = StockReservation(item_id=i.id, request_id=req.id, request_item_id=ri.id, quantity=body.quantity, created_by_id=principal.id)
    session.add(r)
    i.reserved += body.quantity
    i.version += 1
    session.add(StockMovement(reference=await next_reference(session, "INV"), item_id=i.id, company_id=i.company_id, kind="reserve", quantity=0, balance_after=i.on_hand, request_id=req.id, reason=f"Reserved {body.quantity} for {req.reference}", actor_id=principal.id))
    await request_event(session, req, principal, "reserved", f"{body.quantity} {i.unit} {i.name} reserved from {i.location}")
    await audit(session, actor_id=principal.id, action="inventory.reserve", entity_type="inventory_item", entity_id=i.id, entity_ref=i.item_code, company_id=i.company_id, data={"request": req.reference, "quantity": body.quantity})
    await session.commit()
    return {"id": r.id, "status": r.status}


@router.post("/reservations/{res_id}/{action}")
async def reservation_action(res_id: int, action: Literal["issue", "release"], principal: Staff, session: Session) -> dict:
    r = await session.get(StockReservation, res_id)
    if r is None:
        raise not_found()
    i = await scoped(session, InventoryItem, r.item_id, principal)
    req = await session.get(Request, r.request_id)
    if not is_operator(principal, req):
        raise not_found()
    if r.status != "reserved":
        raise conflict(f"This reservation is already {r.status}")
    i.reserved -= r.quantity
    if action == "release":
        r.status = "released"
        i.version += 1
        session.add(StockMovement(reference=await next_reference(session, "INV"), item_id=i.id, company_id=i.company_id, kind="release", quantity=0, balance_after=i.on_hand, request_id=req.id, reason=f"Released reservation for {req.reference}", actor_id=principal.id))
        await request_event(session, req, principal, "reservation_released", f"{r.quantity} {i.unit} {i.name} released")
    else:
        r.status = "issued"
        await move(session, principal, i, "issue", -r.quantity, request_id=req.id, issued_to_id=req.requester_id, reason=f"Issued for {req.reference}")
        ri = await session.get(RequestItem, r.request_item_id)
        ri.received_quantity = min(ri.quantity, ri.received_quantity + r.quantity)
        await issue_assets(session, principal, i, r.quantity, req.requester_id, req)
        done = all(x.received_quantity >= x.quantity for x in req.items)
        req.fulfillment_status = "Issued from stock" if done else "Partially issued"
        req.version += 1
        await request_event(session, req, principal, "issued", f"{r.quantity} {i.unit} {i.name} issued from {i.location}")
        await notify(session, {req.requester_id}, kind="fulfillment_confirmation", title=f"Ready for you: {i.name}", body=f"{r.quantity} {i.unit} issued for {req.reference}", link=f"/r/{req.id}")
    await audit(session, actor_id=principal.id, action=f"inventory.reservation_{action}", entity_type="inventory_item", entity_id=i.id, entity_ref=i.item_code, company_id=i.company_id, data={"request": req.reference, "quantity": r.quantity})
    await session.commit()
    return {"id": r.id, "status": r.status}


class ReorderIn(BaseModel):
    item_ids: list[int] = Field(..., min_length=1, max_length=100)


@router.post("/reorder", status_code=201)
async def reorder(body: ReorderIn, principal: Staff, session: Session) -> dict:
    """Drafts a Local Purchase request (owned by the caller) for the chosen low-stock lines."""
    items = [await scoped(session, InventoryItem, x, principal) for x in body.item_ids]
    companies = {i.company_id for i in items}
    if len(companies) != 1:
        raise bad_request("Reorder one company at a time")
    req = Request(
        reference=await next_reference(session, "REQ"), kind=RequestKind.local_purchase, company_id=items[0].company_id, department_id=principal.employee.department_id,
        requester_id=principal.id, status=S.draft, subject=f"Restock: {items[0].name}" + (f" + {len(items) - 1} more" if len(items) > 1 else ""),
        purpose="Replenish inventory below reorder level", description="Drafted from Equipment Inventory reorder suggestions.",
    )
    for n, i in enumerate(items):
        qty = i.reorder_quantity or max(1, i.reorder_level * 2 - i.available)
        req.items.append(RequestItem(position=n, item_name=i.name, item_category=i.category, brand=i.brand, model=i.model, quantity=qty, unit=i.unit, description=f"{i.item_code} for {i.location}"))
    session.add(req)
    await session.flush()
    await request_event(session, req, principal, "created", "Draft from inventory reorder")
    await audit(session, actor_id=principal.id, action="inventory.reorder_draft", entity_type="request", entity_id=req.id, entity_ref=req.reference, company_id=req.company_id, data={"items": [i.item_code for i in items]})
    await session.commit()
    return {"request_id": req.id, "reference": req.reference}


# ------------------------------------------------------------------ physical counts


def count_out(c: InventoryCount) -> dict:
    lines = c.lines or []
    variance = [l for l in lines if l.get("counted") is not None and l["counted"] != l["expected"]]
    value = sum(Decimal(str(l.get("unit_cost") or 0)) * (l["counted"] - l["expected"]) for l in variance)
    return {
        "id": c.id, "reference": c.reference, "location": c.location, "status": c.status, "lines": lines, "notes": c.notes,
        "counted": sum(1 for l in lines if l.get("counted") is not None), "total": len(lines), "variances": len(variance), "variance_value_php": money(value),
        "started_by": person(c.started_by), "started_at": iso(c.started_at), "submitted_at": iso(c.submitted_at), "posted_by": person(c.posted_by), "posted_at": iso(c.posted_at),
    }


class CountIn(BaseModel):
    company_id: int | None = None
    location: str | None = Field(None, max_length=120)


@router.get("/counts")
async def list_counts(principal: Staff, session: Session) -> list[dict]:
    rows = (await session.execute(select(InventoryCount).where(InventoryCount.company_id.in_(principal.company_ids)).order_by(InventoryCount.id.desc()))).scalars()
    return [count_out(c) for c in rows]


@router.post("/counts", status_code=201)
async def start_count(body: CountIn, principal: Staff, session: Session) -> dict:
    cid = await company_for(session, principal, body.company_id)
    stmt = select(InventoryItem).where(InventoryItem.company_id == cid, InventoryItem.status == "active")
    if body.location:
        stmt = stmt.where(InventoryItem.location == body.location)
    items = (await session.execute(stmt.order_by(InventoryItem.location, InventoryItem.name))).scalars().all()
    if not items:
        raise bad_request("No active stock lines to count there")
    c = InventoryCount(
        reference=await next_reference(session, "CNT"), company_id=cid, location=body.location, started_by_id=principal.id,
        lines=[{"item_id": i.id, "item_code": i.item_code, "name": i.name, "location": i.location, "unit": i.unit, "expected": i.on_hand, "counted": None, "unit_cost": money(i.unit_cost_php)} for i in items],
    )
    session.add(c)
    await session.flush()
    await audit(session, actor_id=principal.id, action="inventory.count_start", entity_type="inventory_count", entity_id=c.id, entity_ref=c.reference, company_id=cid, data={"location": body.location, "lines": len(items)})
    await session.commit()
    return count_out(c)


class CountLines(BaseModel):
    lines: list[dict] = Field(..., max_length=5000)  # [{item_id, counted}]
    notes: str | None = Field(None, max_length=4000)


@router.put("/counts/{count_id}")
async def save_count(count_id: int, body: CountLines, principal: Staff, session: Session) -> dict:
    c = await scoped(session, InventoryCount, count_id, principal)
    if c.status != "open":
        raise conflict("This count is no longer open")
    counted = {int(x["item_id"]): x.get("counted") for x in body.lines}
    lines = []
    for l in c.lines:
        v = counted.get(l["item_id"], l.get("counted"))
        if v is not None:
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise bad_request({"message": f"Counted quantity for {l['item_code']} must be a whole number", "fields": {str(l["item_id"]): "Not a number"}})
            if v < 0:
                raise bad_request({"message": "Counts cannot be negative", "fields": {str(l["item_id"]): "Negative"}})
        lines.append({**l, "counted": v})
    c.lines = lines
    c.notes = body.notes if body.notes is not None else c.notes
    await session.commit()
    return count_out(c)


@router.post("/counts/{count_id}/{action}")
async def count_action(count_id: int, action: Literal["submit", "post", "cancel"], principal: Staff, session: Session) -> dict:
    c = await scoped(session, InventoryCount, count_id, principal)
    if action == "submit":
        if c.status != "open":
            raise conflict("Only open counts can be submitted")
        missing = [l["item_code"] for l in c.lines if l.get("counted") is None]
        if missing:
            raise bad_request({"message": f"{len(missing)} line(s) not counted yet", "fields": {"lines": ", ".join(missing[:10])}})
        c.status = "submitted"
        c.submitted_at = now()
        if not can_adjust(principal):
            await notify(session, await admin_ids(session, c.company_id), kind="approval_required", title=f"Count ready to post: {c.reference}", link="/assets/inventory")
    elif action == "post":
        if not can_adjust(principal):
            raise forbidden("Posting a count needs Admin or delegated inventory control")
        if c.status != "submitted":
            raise conflict("Submit the count before posting it")
        for l in c.lines:
            diff = l["counted"] - l["expected"]
            item = await scoped(session, InventoryItem, l["item_id"], principal)
            item.last_counted_on = date.today()
            if diff:
                if item.on_hand + diff < item.reserved:
                    raise conflict(f"{item.item_code}: the count leaves less than the {item.reserved} reserved; release reservations first")
                await move(session, principal, item, "adjustment", diff, reason=f"Count {c.reference}: expected {l['expected']}, counted {l['counted']}")
        c.status = "posted"
        c.posted_by_id = principal.id
        c.posted_at = now()
    else:
        if c.status not in ("open", "submitted"):
            raise conflict("This count is closed")
        c.status = "cancelled"
    await audit(session, actor_id=principal.id, action=f"inventory.count_{action}", entity_type="inventory_count", entity_id=c.id, entity_ref=c.reference, company_id=c.company_id)
    await session.commit()
    return count_out(await scoped(session, InventoryCount, c.id, principal))


# ------------------------------------------------------------------ movements log & reminders


@router.get("/movements")
async def movements(principal: Staff, session: Session, kind: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> dict:
    stmt = select(StockMovement).where(StockMovement.company_id.in_(principal.company_ids), StockMovement.kind.notin_(["reserve", "release"]))
    if kind:
        stmt = stmt.where(StockMovement.kind == kind)
    total = await count(session, stmt)
    rows = (await session.execute(stmt.order_by(StockMovement.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    items = {i.id: i for i in (await session.execute(select(InventoryItem).where(InventoryItem.id.in_([m.item_id for m in rows] or [0])))).scalars()}
    return {"items": [{**movement_out(m), "item": {"id": m.item_id, "item_code": items[m.item_id].item_code, "name": items[m.item_id].name, "location": items[m.item_id].location, "unit": items[m.item_id].unit}} for m in rows], "total": total, "page": page, "page_size": page_size}


async def stock_in_from_receipt(session, principal: Principal, item_id: int, qty: int, receipt_id: int, request_id: int):
    item = await scoped(session, InventoryItem, item_id, principal)
    await move(session, principal, item, "stock_in", qty, receipt_id=receipt_id, request_id=request_id, reason="Delivery received")


async def inventory_reminders(session) -> int:
    sent = 0
    rows = (await session.execute(select(InventoryItem).where(InventoryItem.status == "active", InventoryItem.reorder_level > 0))).scalars().all()
    for i in rows:
        if i.available <= i.reorder_level:
            await notify(
                session, await admin_ids(session, i.company_id), kind="renewal_warning", title=f"Low stock: {i.name} ({i.location})",
                body=f"{i.available} {i.unit} available, reorder level {i.reorder_level}", link="/assets/inventory", dedupe_key=f"inv-low:{i.id}:{i.on_hand}:{i.reserved}",
            )
            sent += 1
    return sent
