"""Phase 2.3a — equipment inventory: stock lines, movements, reservations, reorders and counts."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete as sa_delete, or_, select, update as sa_update
from sqlalchemy.exc import IntegrityError

from ..core import admin_ids, audit, bad_request, conflict, forbidden, next_reference, not_found, notify, now
from ..models import Request, RequestItem, RequestKind, RequestStatus as S
from ..models_ops import Asset, AssetCondition, AssetEvent, AssetStatus
from ..models_ops3 import INV_CATEGORIES, InventoryCount, InventoryItem, StockMovement, StockReservation
from ..ops_common import check_version, company_for, count, day, employee_in, money, scoped
from ..security import Principal, Session, Staff
from ..serialize import iso, person
from ..models import Attachment
from .attachments import storage_dir
from .photos import photo_url
from ..proofs import get_proof, proof_out, proofs_for as _proofs_for, save_proof
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


def movement_out(m: StockMovement, proofs: dict[int, list[dict]] | None = None) -> dict:
    return {
        "proofs": (proofs or {}).get(m.id, []),
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
    # Empty: numbered automatically, e.g. GPI-CS-0007.
    item_code: str = Field("", max_length=40)
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

    @field_validator("item_code", mode="before")
    @classmethod
    def code(cls, v):
        # The form sends null for an empty field: that means "number it automatically".
        return (v or "").strip().upper() if isinstance(v, str) or v is None else v

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


ITEM_CODE_PREFIX = {"Equipment": "EQ", "Supplies": "SU", "Spare Parts": "SP", "Consumables": "CS"}


async def next_item_code(session, company_id: int, category: str) -> str:
    from ..models import Company, DocumentSequence

    company = await session.get(Company, company_id)
    code = (company.code if company else "EA").upper()
    prefix = ITEM_CODE_PREFIX.get(category, "IT")
    doc_type = f"IC-{code}-{prefix}"[:16]
    seq = (await session.execute(select(DocumentSequence).where(DocumentSequence.doc_type == doc_type, DocumentSequence.year == 0).with_for_update())).scalar_one_or_none()
    if seq is None:
        seq = DocumentSequence(doc_type=doc_type, year=0, last_value=0)
        session.add(seq)
        await session.flush()
    while True:
        seq.last_value += 1
        candidate = f"{code}-{prefix}-{seq.last_value:04d}"
        if not (await session.execute(select(InventoryItem.id).where(InventoryItem.company_id == company_id, InventoryItem.item_code == candidate))).first():
            return candidate


@router.get("/items")
async def list_items(
    principal: Staff, session: Session, q: str | None = Query(None, max_length=200), category: str | None = None, location: str | None = None,
    low: bool = False, status: str | None = "active", page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
    sort: Literal["name", "category", "location", "available", "on_hand", "value", "updated"] = "name", dir: Literal["asc", "desc"] | None = None,
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
    key = {
        "name": lambda i: (i.name.lower(), i.location.lower()), "category": lambda i: (i.category, i.name.lower()), "location": lambda i: (i.location.lower(), i.name.lower()),
        "available": lambda i: (i.available, i.name.lower()), "on_hand": lambda i: (i.on_hand, i.name.lower()),
        "value": lambda i: ((i.unit_cost_php or Decimal(0)) * i.on_hand, i.name.lower()), "updated": lambda i: (i.updated_at, i.id),
    }[sort]
    rows.sort(key=key, reverse=(dir or ("desc" if sort in ("updated", "value") else "asc")) == "desc")
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
    if not body.item_code:
        body.item_code = await next_item_code(session, cid, body.category)
    dup = await session.execute(select(InventoryItem.id).where(InventoryItem.company_id == cid, InventoryItem.item_code == body.item_code, InventoryItem.location == body.location))
    if dup.first():
        raise conflict(f"{body.item_code} already has a stock line at {body.location}")
    i = InventoryItem(company_id=cid, on_hand=0, reserved=0, **body.model_dump(exclude={"company_id", "opening_quantity", "serialized_on_issue"}))
    session.add(i)
    try:
        await session.flush()
    except IntegrityError:
        raise conflict(f"{body.item_code} already has a stock line at {body.location}")
    opening = None
    if body.opening_quantity:
        opening = await move(session, principal, i, "stock_in", body.opening_quantity, reason="Opening balance")
        await session.flush()
    await audit(session, actor_id=principal.id, action="inventory.item_create", entity_type="inventory_item", entity_id=i.id, entity_ref=i.item_code, company_id=cid, data={"location": i.location})
    await session.commit()
    # The opening movement can take a proof-of-receipt photo right after.
    return {**item_out(await scoped(session, InventoryItem, i.id, principal)), "opening_movement_id": opening.id if opening else None}


@router.get("/items/{item_id}")
async def get_item(item_id: int, principal: Staff, session: Session) -> dict:
    i = await scoped(session, InventoryItem, item_id, principal)
    moves = (await session.execute(select(StockMovement).where(StockMovement.item_id == i.id).order_by(StockMovement.id.desc()).limit(200))).scalars()
    res = (await session.execute(select(StockReservation).where(StockReservation.item_id == i.id, StockReservation.status == "reserved"))).scalars().all()
    reqs = {r.id: r for r in (await session.execute(select(Request).where(Request.id.in_([x.request_id for x in res] or [0])))).scalars()}
    other = (await session.execute(select(InventoryItem).where(InventoryItem.company_id == i.company_id, InventoryItem.item_code == i.item_code, InventoryItem.id != i.id))).scalars()
    moves = list(moves)
    proofs = await proofs_for(session, [m.id for m in moves])
    every = (await session.execute(select(StockMovement).where(StockMovement.item_id == i.id, StockMovement.kind.in_(["issue", "return"])))).scalars().all()
    return {
        **item_out(i),
        "movements": [movement_out(m, proofs) for m in moves],
        "holders": sorted(holders_of(every).values(), key=lambda h: h["person"]["name"]),
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
    body.item_code = body.item_code or i.item_code  # cleared: keep the current code
    if body.item_code != i.item_code or body.location != i.location:
        dup = await session.execute(select(InventoryItem.id).where(InventoryItem.company_id == i.company_id, InventoryItem.item_code == body.item_code, InventoryItem.location == body.location, InventoryItem.id != i.id))
        if dup.first():
            raise conflict(f"{body.item_code} already has a stock line at {body.location}")
        if body.location != i.location and i.on_hand:
            raise bad_request({"message": "Use a transfer to move stock to another location", "fields": {"location": "Use transfer"}})
    changed = {}
    for k, v in body.model_dump(exclude={"company_id", "version", "opening_quantity", "serialized_on_issue"}).items():
        if getattr(i, k) != v:
            changed[k] = str(v)
            setattr(i, k, v)
    i.version += 1
    await audit(session, actor_id=principal.id, action="inventory.item_update", entity_type="inventory_item", entity_id=i.id, entity_ref=i.item_code, company_id=i.company_id, data=changed)
    await session.commit()
    return item_out(await scoped(session, InventoryItem, i.id, principal))


class MoveIn(BaseModel):
    # "use": consumed in the office (pantry, cleaning, printing) rather than handed to one person.
    kind: Literal["stock_in", "issue", "use", "return", "transfer", "adjustment", "write_off"]
    quantity: int = Field(..., ge=1, le=10_000_000)
    direction: Literal["add", "remove"] = "add"  # adjustments only
    issued_to_id: int | None = None  # issue: who receives it; return: who brought it back
    to_location: str | None = Field(None, max_length=120)
    reason: str | None = Field(None, max_length=2000)


@router.post("/items/{item_id}/move")
async def move_stock(item_id: int, body: MoveIn, principal: Staff, session: Session) -> dict:
    i = await scoped(session, InventoryItem, item_id, principal)
    if i.status == "discontinued" and body.kind in ("stock_in", "return"):
        raise conflict("This item is discontinued")
    reason = (body.reason or "").strip() or None
    if body.kind in ("adjustment", "write_off", "use") and not reason:
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
    elif body.kind == "use":
        if body.quantity > i.available:
            raise conflict(f"Only {i.available} {i.unit} available ({i.reserved} reserved)")
        await move(session, principal, i, "use", -body.quantity, reason=reason)
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
    elif body.kind == "return":
        by = (await employee_in(session, body.issued_to_id, i.company_id, "issued_to_id")).id if body.issued_to_id else None
        if by:
            every = (await session.execute(select(StockMovement).where(StockMovement.item_id == i.id, StockMovement.kind.in_(["issue", "return"])))).scalars().all()
            held = holders_of(every).get(by)
            if held and body.quantity > held["quantity"]:
                raise bad_request({"message": f"{held['person']['name']} has only {held['quantity']} {i.unit}", "fields": {"quantity": f"{held['person']['name']} has only {held['quantity']} {i.unit}"}})
        await move(session, principal, i, "return", body.quantity, reason=reason, issued_to_id=by)
    else:  # stock_in
        await move(session, principal, i, body.kind, body.quantity, reason=reason)
    await session.commit()
    return await get_item(i.id, principal, session)


# ------------------------------------------------------------------ transactions: details and photo proof


async def proofs_for(session, movement_ids: list[int]) -> dict[int, list[dict]]:
    return await _proofs_for(session, "stock_movement", movement_ids)


def holders_of(moves) -> dict[int, dict]:
    """Who still has pieces of this stock line: issued to them minus returned by them."""
    out: dict[int, dict] = {}
    for m in moves:
        if m.issued_to_id and m.kind in ("issue", "return"):
            h = out.setdefault(m.issued_to_id, {"person": person(m.issued_to), "quantity": 0})
            h["quantity"] -= m.quantity  # issues are negative, returns positive
    return {k: v for k, v in out.items() if v["quantity"] > 0}


@router.get("/movements/{movement_id}")
async def get_movement(movement_id: int, principal: Staff, session: Session) -> dict:
    """One transaction on a stock card, with its photo proof."""
    m = await session.get(StockMovement, movement_id)
    if m is None:
        raise not_found()
    item = await scoped(session, InventoryItem, m.item_id, principal)
    req = await session.get(Request, m.request_id) if m.request_id else None
    other = await session.get(InventoryItem, m.counterpart_item_id) if m.counterpart_item_id else None
    return {
        **movement_out(m, await proofs_for(session, [m.id])),
        "item": {"id": item.id, "item_code": item.item_code, "name": item.name, "location": item.location, "unit": item.unit, "photo": photo_url(item.photo_id)},
        "request": {"id": req.id, "reference": req.reference, "subject": req.subject} if req else None,
        "counterpart": {"id": other.id, "location": other.location} if other else None,
    }


@router.post("/movements/{movement_id}/proof", status_code=201)
async def add_proof(movement_id: int, principal: Staff, session: Session, file: UploadFile = File(...), meta: str | None = Form(None)) -> dict:
    m = await session.get(StockMovement, movement_id)
    if m is None or m.kind in ("reserve", "release"):
        raise not_found()
    item = await scoped(session, InventoryItem, m.item_id, principal)
    att = await save_proof(session, principal, "stock_movement", m.id, m.reference, file, meta)
    await audit(session, actor_id=principal.id, action="inventory.proof_add", entity_type="inventory_item", entity_id=item.id, entity_ref=item.item_code, company_id=item.company_id, data={"movement": m.reference, "photo": att.id, "source": att.meta.get("source")})
    await session.commit()
    return proof_out(att)


@router.get("/proofs/{photo_id}")
async def get_proof_old_link(photo_id: int, principal: Staff, session: Session, size: Literal["thumb", "full"] = Query("thumb")):
    """Links made before proofs moved to /api/v1/proofs."""
    return await get_proof(photo_id, principal, session, size)


async def rehome_files(session, asset_ids: list[int], item: InventoryItem) -> None:
    """Photos and files of asset records go to the stock item. The same photo saved on several records is kept once."""
    from .attachments import storage_dir
    from .photos import MAX_PHOTOS, PURPOSE as PHOTO

    if not asset_ids:
        return
    atts = (await session.execute(select(Attachment).where(Attachment.owner_type == "asset", Attachment.owner_id.in_(asset_ids)).order_by(Attachment.id))).scalars().all()
    have = {x.sha256 for x in (await session.execute(select(Attachment).where(Attachment.owner_type == "inventory_item", Attachment.owner_id == item.id))).scalars()}
    photos = len((await session.execute(select(Attachment.id).where(Attachment.owner_type == "inventory_item", Attachment.owner_id == item.id, Attachment.purpose == PHOTO))).all())
    for att in atts:
        if att.sha256 in have or (att.purpose == PHOTO and photos >= MAX_PHOTOS):
            for k in (att.storage_key, f"{att.storage_key}_t"):
                (storage_dir() / k).unlink(missing_ok=True)
            await session.delete(att)
            continue
        have.add(att.sha256)
        att.owner_type, att.owner_id = "inventory_item", item.id
        if att.purpose == PHOTO:
            photos += 1
            if item.photo_id is None:
                item.photo_id = att.id


async def drop_assets(session, assets: list[Asset]) -> None:
    for a in assets:
        await session.execute(sa_delete(AssetEvent).where(AssetEvent.asset_id == a.id))
        await session.delete(a)


async def fold_stock_assets(session) -> int:
    """One record per counted item: the stock line.

    Issuing from stock used to be able to also create one asset record per piece ("Register as an asset
    when issued"). Those records duplicated the stock card, and returning one never reached the stock.
    Each such record is folded back: if it is still with someone, the stock card already shows it as
    issued, so the record goes; if it came back, the stock card gets the return (+1, by that person).
    Photos and files move to the stock item; the old references stay in the audit log.
    """
    from types import SimpleNamespace

    from ..models_ops import AssetRepair

    evs = (await session.execute(select(AssetEvent).where(AssetEvent.type == "assigned", AssetEvent.message.like("Issued from inventory %")).order_by(AssetEvent.id))).scalars().all()
    folded = 0
    for ev in evs:
        a = await session.get(Asset, ev.asset_id)
        if a is None:
            continue
        msg = ev.message or ""
        code = msg.split(" ")[3] if len(msg.split(" ")) > 3 else None
        loc = msg.split("(", 1)[1].split(")", 1)[0] if "(" in msg else None
        items = (await session.execute(select(InventoryItem).where(InventoryItem.company_id == a.company_id, InventoryItem.item_code == code))).scalars().all()
        item = next((x for x in items if x.location == loc), items[0] if items else None)
        if item is None or (await session.execute(select(AssetRepair.id).where(AssetRepair.asset_id == a.id).limit(1))).first():
            continue
        ret = None
        if not a.holder_id and a.status != AssetStatus.retired:
            ret = (await session.execute(select(AssetEvent).where(AssetEvent.asset_id == a.id, AssetEvent.type == "returned").order_by(AssetEvent.id.desc()).limit(1))).scalar_one_or_none()
            actor = SimpleNamespace(id=(ret.actor_id if ret and ret.actor_id else ev.actor_id or a.issued_by_id))
            m = await move(session, actor, item, "return", 1, reason="Returned" + (f": {ret.message}" if ret and ret.message else ""), issued_to_id=ret.from_holder_id if ret else None)
            if ret:
                m.at = ret.at
        await rehome_files(session, [a.id], item)
        await audit(
            session, actor_id=None, action="inventory.asset_record_folded", entity_type="inventory_item", entity_id=item.id, entity_ref=item.item_code, company_id=item.company_id,
            data={"asset": a.reference, "serial": a.serial_number, "holder_id": a.holder_id, "returned": bool(ret)},
        )
        await drop_assets(session, [a])
        folded += 1
    await session.execute(sa_update(InventoryItem).where(InventoryItem.serialized_on_issue.is_(True)).values(serialized_on_issue=False))
    await session.commit()
    return folded


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
        purpose="Replenish inventory below reorder level", description="Drafted from Consumables & Stock reorder suggestions.",
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
    proofs = await proofs_for(session, [m.id for m in rows])
    return {"items": [{**movement_out(m, proofs), "item": {"id": m.item_id, "item_code": items[m.item_id].item_code, "name": items[m.item_id].name, "location": items[m.item_id].location, "unit": items[m.item_id].unit}} for m in rows], "total": total, "page": page, "page_size": page_size}


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
