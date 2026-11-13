"""
Phase 2.9 — reports (EXECUTIVE-ADMIN.md §18) and database-backed dashboards (§25).

Every report reads real records inside the caller's company scope and can be exported to
Excel, CSV or PDF. Restricted reports (passports/visas) follow the same grants as their module.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Awaitable, Callable

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select

from ..core import aware, audit, forbidden, not_found, now
from ..models import ApprovalStep, AuditEvent, Department, Employee, Request, RequestStatus as S, SlaPolicy, Task, TaskStatus
from ..models_ops import Asset, AssetEvent, AssetRepair, FinanceRequest, FleetCard, Receipt, RfidAccount, Vehicle, VehicleService
from ..models_ops2 import BocCase, FlightBooking, GovRegistration, HotelReservation, TravelDocument
from ..models_ops3 import Contract, InventoryCount, InventoryItem, RentPayment, StockMovement
from ..ops_common import days_until
from ..pdf import Column, table_report
from ..security import CurrentPrincipal, Principal, Session, Staff
from ..workflow import IN_APPROVAL, OPEN, approver_scope_ids, scope_filter

router = APIRouter(prefix="/api/v1", tags=["reports"])


@dataclass
class Params:
    date_from: date | None
    date_to: date | None
    company: str | None
    within: int


@dataclass
class Report:
    key: str
    module: str
    title: str
    description: str
    columns: list[Column]
    run: Callable[..., Awaitable[list[dict]]]
    uses_dates: bool = False
    uses_within: bool = False
    restricted: Callable[[Principal], bool] | None = None
    totals: list[str] | None = None


def C(key, label, kind="text", width=None):
    return Column(key, label, kind, width)


def in_range(d, p: Params) -> bool:
    if d is None:
        return p.date_from is None and p.date_to is None
    if isinstance(d, datetime):
        d = aware(d).date()
    return (p.date_from is None or d >= p.date_from) and (p.date_to is None or d <= p.date_to)


async def _companies(session, pr: Principal, p: Params) -> set[int]:
    if p.company:
        from ..models import Company

        c = (await session.execute(select(Company).where(Company.code == p.company.upper()))).scalar_one_or_none()
        return {c.id} & pr.company_ids if c else set()
    return pr.company_ids


async def _requests(session, pr, p, extra=None) -> list[Request]:
    cids = await _companies(session, pr, p)
    stmt = select(Request).where(scope_filter(pr), Request.status != S.draft, Request.company_id.in_(cids))
    if extra is not None:
        stmt = stmt.where(extra)
    return [r for r in (await session.execute(stmt.order_by(Request.id))).scalars() if in_range(r.submitted_at or r.created_at, p)]


def req_row(r: Request) -> dict:
    return {
        "reference": r.reference, "type": r.kind.replace("_", " "), "subject": r.subject, "company": r.company.code, "department": r.department.name if r.department else None,
        "requester": r.requester.name, "priority": r.priority, "status": r.status.replace("_", " "), "owner": r.assigned_to.name if r.assigned_to else None,
        "submitted": aware(r.submitted_at).date() if r.submitted_at else None, "due": aware(r.resolution_due_at).date() if r.resolution_due_at else None,
    }


REQ_COLS = [C("reference", "Reference"), C("type", "Type"), C("subject", "Subject", width=3), C("department", "Department"), C("requester", "Requester"), C("priority", "Priority", width=1), C("status", "Status"), C("owner", "Owner"), C("submitted", "Submitted", "date"), C("due", "Resolve by", "date")]


async def r_register(s, pr, p):
    return [req_row(r) for r in await _requests(s, pr, p)]


async def r_pending(s, pr, p):
    return [req_row(r) for r in await _requests(s, pr, p, Request.status.in_(list(OPEN)))]


async def r_aging(s, pr, p):
    out = []
    for r in await _requests(s, pr, p, Request.status.in_(list(IN_APPROVAL))):
        step = next((x for x in r.steps if x.status in ("pending", "returned")), None)
        since = aware(step.activated_at) if step and step.activated_at else aware(r.submitted_at)
        age = (now() - since).days if since else None
        out.append({**req_row(r), "stage": step.name if step else None, "approver": step.approver.name if step and step.approver else "—", "waiting_days": age, "bucket": "0–2 days" if (age or 0) <= 2 else "3–7 days" if age <= 7 else "8+ days"})
    return sorted(out, key=lambda x: -(x["waiting_days"] or 0))


async def _group(s, pr, p, key):
    rows = await _requests(s, pr, p)
    g = defaultdict(Counter)
    for r in rows:
        k = key(r)
        g[k]["total"] += 1
        g[k]["open"] += r.status in OPEN
        g[k]["closed"] += r.status in (S.closed, S.fulfilled)
        g[k]["rejected"] += r.status == S.rejected
        g[k]["overdue"] += bool(r.status in OPEN and r.resolution_due_at and aware(r.resolution_due_at) < now())
    return [{"group": k or "—", **{x: v[x] for x in ("total", "open", "closed", "rejected", "overdue")}} for k, v in sorted(g.items(), key=lambda kv: -kv[1]["total"])]


GROUP_COLS = lambda label: [C("group", label, width=3), C("total", "Total", "number"), C("open", "Open", "number"), C("closed", "Completed", "number"), C("rejected", "Rejected", "number"), C("overdue", "Overdue", "number")]  # noqa: E731


async def r_by_dept(s, pr, p):
    return await _group(s, pr, p, lambda r: r.department.name if r.department else None)


async def r_by_company(s, pr, p):
    return await _group(s, pr, p, lambda r: r.company.name)


async def r_priority(s, pr, p):
    rows = await _requests(s, pr, p, Request.status.in_(list(OPEN)))
    return [req_row(r) for r in rows if r.priority in ("high", "critical") or (r.resolution_due_at and aware(r.resolution_due_at) < now())]


async def r_supply(s, pr, p):
    out = []
    for r in await _requests(s, pr, p, Request.kind.in_(["supplies", "asset", "local_purchase"])):
        for i in r.items:
            out.append({"reference": r.reference, "requester": r.requester.name, "department": r.department.name if r.department else None, "item": i.item_name, "quantity": i.quantity, "unit": i.unit, "received": i.received_quantity, "status": r.status.replace("_", " "), "fulfillment": r.fulfillment_status})
    return out


async def r_fulfillment(s, pr, p):
    out = []
    for r in await _requests(s, pr, p, Request.status.in_([S.fulfilled, S.closed])):
        days = (aware(r.closed_at or r.updated_at) - aware(r.submitted_at)).days if r.submitted_at else None
        out.append({**req_row(r), "days_to_close": days, "met_sla": "Yes" if r.resolution_due_at and aware(r.closed_at or r.updated_at) <= aware(r.resolution_due_at) else "No"})
    return out


# ---- assets & inventory


async def _assets(s, pr, p):
    cids = await _companies(s, pr, p)
    return list((await s.execute(select(Asset).where(Asset.company_id.in_(cids)).order_by(Asset.reference))).scalars())


def asset_row(a: Asset) -> dict:
    return {"reference": a.reference, "name": a.name, "category": a.category, "serial": a.serial_number, "condition": a.condition.replace("_", " "), "status": a.status.replace("_", " "), "holder": a.holder.name if a.holder else None, "department": a.department.name if a.department else None, "location": a.location, "issued": a.date_issued}


ASSET_COLS = [C("reference", "Asset tag"), C("name", "Asset", width=3), C("category", "Category"), C("serial", "Serial"), C("condition", "Condition"), C("status", "Status"), C("holder", "Holder"), C("department", "Department"), C("issued", "Issued", "date")]


async def a_registry(s, pr, p):
    return [asset_row(a) for a in await _assets(s, pr, p)]


async def a_assignment(s, pr, p):
    return [{**asset_row(a), "acknowledged": "Yes" if a.acknowledged_at else "No"} for a in await _assets(s, pr, p) if a.holder_id]


async def _asset_events(s, pr, p, types):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(AssetEvent, Asset).join(Asset, Asset.id == AssetEvent.asset_id).where(Asset.company_id.in_(cids), AssetEvent.type.in_(types)).order_by(AssetEvent.at.desc()))).all()
    return [{"date": aware(e.at).date(), "asset": a.reference, "name": a.name, "event": e.type.replace("_", " "), "from": e.from_holder.name if e.from_holder else None, "to": e.to_holder.name if e.to_holder else None, "by": e.actor.name if e.actor else "System", "note": e.message} for e, a in rows if in_range(e.at, p)]


EVENT_COLS = [C("date", "Date", "date"), C("asset", "Asset tag"), C("name", "Asset", width=2.5), C("event", "Event"), C("from", "From"), C("to", "To"), C("by", "By"), C("note", "Note", width=3)]


async def a_transfer(s, pr, p):
    return await _asset_events(s, pr, p, ["transferred", "assigned", "returned"])


async def a_repair(s, pr, p):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(AssetRepair).join(Asset, Asset.id == AssetRepair.asset_id).where(Asset.company_id.in_(cids)).order_by(AssetRepair.id.desc()))).scalars()
    return [{"reference": r.reference, "asset": r.asset.reference, "name": r.asset.name, "issue": r.issue, "provider": r.provider, "status": r.status.replace("_", " "), "cost": r.cost_php, "opened": aware(r.opened_at).date(), "completed": aware(r.completed_at).date() if r.completed_at else None} for r in rows if in_range(r.opened_at, p)]


async def a_receiving(s, pr, p):
    cids = await _companies(s, pr, p)
    out = []
    for r in (await s.execute(select(Receipt).where(Receipt.company_id.in_(cids)).order_by(Receipt.id.desc()))).scalars():
        if not in_range(r.received_on, p):
            continue
        for l in r.lines:
            out.append({"reference": r.reference, "date": r.received_on, "item": l["item_name"], "quantity": l["quantity"], "unit": l["unit"], "assets": ", ".join(a["reference"] for a in l.get("assets", [])), "dr": r.delivery_reference, "supplier": r.supplier, "by": r.received_by.name})
    return out


async def a_unreturned(s, pr, p):
    out = []
    for a in await _assets(s, pr, p):
        if not a.holder_id:
            continue
        reason = None
        if not a.holder.active:
            reason = "Holder is no longer active"
        elif not a.acknowledged_at and a.date_issued and (date.today() - a.date_issued).days > 7:
            reason = f"Not acknowledged after {(date.today() - a.date_issued).days} days"
        if reason:
            out.append({**asset_row(a), "reason": reason})
    return out


async def _inv(s, pr, p):
    cids = await _companies(s, pr, p)
    return list((await s.execute(select(InventoryItem).where(InventoryItem.company_id.in_(cids), InventoryItem.status == "active").order_by(InventoryItem.name, InventoryItem.location))).scalars())


def inv_row(i: InventoryItem) -> dict:
    return {"code": i.item_code, "name": i.name, "category": i.category, "location": i.location, "on_hand": i.on_hand, "reserved": i.reserved, "available": i.available, "reorder_level": i.reorder_level, "unit": i.unit, "unit_cost": i.unit_cost_php, "value": (i.unit_cost_php or Decimal(0)) * i.on_hand}


INV_COLS = [C("code", "Item code"), C("name", "Item", width=3), C("location", "Location"), C("on_hand", "On hand", "number"), C("reserved", "Reserved", "number"), C("available", "Available", "number"), C("reorder_level", "Reorder at", "number"), C("unit_cost", "Unit cost", "money"), C("value", "Value", "money")]


async def i_stock(s, pr, p):
    return [inv_row(i) for i in await _inv(s, pr, p)]


async def i_low(s, pr, p):
    return [{**inv_row(i), "suggested": i.reorder_quantity or max(1, i.reorder_level * 2 - i.available)} for i in await _inv(s, pr, p) if i.available <= i.reorder_level]


async def i_moves(s, pr, p):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(StockMovement, InventoryItem).join(InventoryItem, InventoryItem.id == StockMovement.item_id).where(StockMovement.company_id.in_(cids), StockMovement.kind.notin_(["reserve", "release"])).order_by(StockMovement.id.desc()))).all()
    return [{"date": aware(m.at).date(), "reference": m.reference, "code": i.item_code, "name": i.name, "location": i.location, "kind": m.kind.replace("_", " "), "quantity": m.quantity, "balance": m.balance_after, "to": m.issued_to.name if m.issued_to else None, "by": m.actor.name, "reason": m.reason} for m, i in rows if in_range(m.at, p)]


async def i_valuation(s, pr, p):
    g = defaultdict(lambda: {"lines": 0, "units": 0, "value": Decimal(0)})
    for i in await _inv(s, pr, p):
        x = g[(i.category, i.location)]
        x["lines"] += 1
        x["units"] += i.on_hand
        x["value"] += (i.unit_cost_php or Decimal(0)) * i.on_hand
    return [{"category": c, "location": l, **v} for (c, l), v in sorted(g.items())]


async def i_variance(s, pr, p):
    cids = await _companies(s, pr, p)
    out = []
    for c in (await s.execute(select(InventoryCount).where(InventoryCount.company_id.in_(cids), InventoryCount.status.in_(["submitted", "posted"])).order_by(InventoryCount.id.desc()))).scalars():
        if not in_range(c.started_at, p):
            continue
        for l in c.lines:
            if l.get("counted") is not None and l["counted"] != l["expected"]:
                diff = l["counted"] - l["expected"]
                out.append({"count": c.reference, "status": c.status, "code": l["item_code"], "name": l["name"], "location": l["location"], "expected": l["expected"], "counted": l["counted"], "variance": diff, "value": Decimal(str(l.get("unit_cost") or 0)) * diff})
    return out


async def i_by_dept(s, pr, p):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(StockMovement, InventoryItem).join(InventoryItem, InventoryItem.id == StockMovement.item_id).where(StockMovement.company_id.in_(cids), StockMovement.kind == "issue"))).all()
    g = defaultdict(lambda: {"issues": 0, "units": 0, "value": Decimal(0)})
    for m, i in rows:
        if not in_range(m.at, p):
            continue
        dept = m.issued_to.department.name if m.issued_to and m.issued_to.department else "—"
        g[dept]["issues"] += 1
        g[dept]["units"] += -m.quantity
        g[dept]["value"] += (i.unit_cost_php or Decimal(0)) * -m.quantity
    return [{"department": k, **v} for k, v in sorted(g.items(), key=lambda kv: -kv[1]["units"])]


# ---- fleet


async def _veh(s, pr, p):
    cids = await _companies(s, pr, p)
    return list((await s.execute(select(Vehicle).where(Vehicle.company_id.in_(cids)).order_by(Vehicle.make, Vehicle.model))).scalars())


def veh_row(v: Vehicle) -> dict:
    return {"reference": v.reference, "plate": v.plate_number or v.conduction_sticker, "vehicle": f"{v.make} {v.model}", "type": v.vehicle_type, "driver": v.assigned_driver.name if v.assigned_driver else None, "registration": v.registration_renewal_date, "insurance": v.insurance_expiry_date, "pms": v.next_pms_date, "odometer": v.odometer_km, "status": v.status.replace("_", " ")}


VEH_COLS = [C("plate", "Plate"), C("vehicle", "Vehicle", width=2.5), C("type", "Type"), C("driver", "Driver"), C("registration", "Registration", "date"), C("insurance", "Insurance", "date"), C("pms", "Next PMS", "date"), C("odometer", "Odometer", "number"), C("status", "Status")]


async def f_registry(s, pr, p):
    return [veh_row(v) for v in await _veh(s, pr, p)]


def _due(attr, label):
    async def run(s, pr, p):
        out = []
        for v in await _veh(s, pr, p):
            n = days_until(getattr(v, attr))
            if n is not None and n <= p.within and v.status in ("active", "under_maintenance"):
                out.append({**veh_row(v), "due": getattr(v, attr), "days": n, "what": label})
        return sorted(out, key=lambda x: x["days"])

    return run


DUE_COLS = [C("plate", "Plate"), C("vehicle", "Vehicle", width=2.5), C("driver", "Driver"), C("what", "Due item"), C("due", "Due date", "date"), C("days", "Days left", "number")]


async def f_cards(s, pr, p):
    cids = await _companies(s, pr, p)
    out = []
    for c in (await s.execute(select(FleetCard).where(FleetCard.company_id.in_(cids)))).scalars():
        bills = (await s.execute(select(FinanceRequest).where(FinanceRequest.fleet_card_id == c.id))).scalars().all()
        paid = sum((b.amount_php for b in bills if b.status == "paid" and in_range(b.paid_at, p)), Decimal(0))
        out.append({"card": f"{c.provider} ****{c.card_last4}", "vehicle": c.vehicle.label if c.vehicle else None, "limit": c.configured_amount_php, "billed": sum((b.amount_php for b in bills if b.status in ("sent", "paid") and in_range(b.created_at, p)), Decimal(0)), "paid": paid, "pending": sum(1 for b in bills if b.status == "sent"), "status": c.monitoring_status})
    return out


async def f_rfid(s, pr, p):
    cids = await _companies(s, pr, p)
    out = []
    for f in (await s.execute(select(FinanceRequest).where(FinanceRequest.company_id.in_(cids), FinanceRequest.kind == "rfid_reload").order_by(FinanceRequest.id.desc()))).scalars():
        if in_range(f.created_at, p):
            out.append({"reference": f.reference, "account": f"{f.rfid_account.provider} {f.rfid_account.account_reference}" if f.rfid_account else None, "vehicle": f.vehicle.label if f.vehicle else None, "amount": f.amount_php, "status": f.status, "finance_reference": f.finance_reference, "requested": aware(f.created_at).date(), "paid": aware(f.paid_at).date() if f.paid_at else None})
    return out


async def f_repairs(s, pr, p):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(VehicleService).join(Vehicle, Vehicle.id == VehicleService.vehicle_id).where(Vehicle.company_id.in_(cids)).order_by(VehicleService.service_date.desc()))).scalars()
    return [{"reference": x.reference, "vehicle": x.vehicle.label, "kind": x.kind.upper() if x.kind == "pms" else x.kind, "date": x.service_date, "description": x.description, "provider": x.provider, "odometer": x.odometer_km, "cost": x.cost_php, "status": x.status} for x in rows if in_range(x.service_date, p)]


# ---- compliance


async def _regs(s, pr, p, types=None):
    cids = await _companies(s, pr, p)
    stmt = select(GovRegistration).where(GovRegistration.company_id.in_(cids))
    if types:
        stmt = stmt.where(GovRegistration.registration_type.in_(types))
    return list((await s.execute(stmt.order_by(GovRegistration.expiry_date))).scalars())


def reg_row(r: GovRegistration) -> dict:
    return {"reference": r.reference, "document": r.document_name, "type": r.registration_type, "number": r.registration_number, "registered": r.registration_date, "expiry": r.expiry_date, "due": r.due_date, "days": days_until(r.due_date or r.expiry_date), "responsible": r.responsible.name if r.responsible else None, "status": r.status.replace("_", " ")}


REG_COLS = [C("document", "Document", width=3), C("type", "Type"), C("number", "Number"), C("expiry", "Expiry", "date"), C("due", "Filing due", "date"), C("days", "Days left", "number"), C("responsible", "Responsible"), C("status", "Status")]


async def c_regs(s, pr, p):
    return [reg_row(r) for r in await _regs(s, pr, p)]


async def c_expiring(s, pr, p):
    return [reg_row(r) for r in await _regs(s, pr, p) if r.status in ("ongoing", "for_renewal", "expired") and (days_until(r.due_date or r.expiry_date) or 9999) <= p.within]


async def c_calendar(s, pr, p):
    from .compliance import calendar

    items = await calendar(principal=pr, session=s, months=max(1, p.within // 30 or 1), include_overdue=True)
    return [{"date": date.fromisoformat(i["date"]), "days": i["days"], "module": i["module"], "what": i["kind"], "title": i["title"], "company": i["company"]} for i in items]


async def c_secgis(s, pr, p):
    return [reg_row(r) for r in await _regs(s, pr, p, ["SEC", "GIS"])]


async def c_permits(s, pr, p):
    return [reg_row(r) for r in await _regs(s, pr, p, ["Business Permit"])]


async def c_boc(s, pr, p):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(BocCase).where(BocCase.company_id.in_(cids)).order_by(BocCase.id.desc()))).scalars()
    return [{"reference": c.reference, "direction": c.direction, "goods": c.description, "bl": c.bill_of_lading, "entry": c.entry_number, "eta": c.eta, "officer": c.officer.name if c.officer else None, "status": c.status.replace("_", " ")} for c in rows if in_range(c.created_at, p)]


# ---- travel


async def t_flights(s, pr, p):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(FlightBooking).where(FlightBooking.company_id.in_(cids)).order_by(FlightBooking.departure_date))).scalars()
    return [{"reference": f.reference, "passenger": f.passenger.name, "type": f.travel_type, "route": f"{f.origin} → {f.destination}", "departure": f.departure_date, "return": f.return_date, "airline": f.airline, "pnr": f.booking_reference, "status": f.status} for f in rows if in_range(f.departure_date, p)]


async def t_hotels(s, pr, p):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(HotelReservation).where(HotelReservation.company_id.in_(cids)).order_by(HotelReservation.check_in))).scalars()
    return [{"reference": h.reference, "guest": h.guest.name, "hotel": h.hotel, "city": h.destination, "check_in": h.check_in, "check_out": h.check_out, "nights": (h.check_out - h.check_in).days, "confirmation": h.booking_reference, "status": h.status} for h in rows if in_range(h.check_in, p)]


async def t_employee(s, pr, p):
    g = defaultdict(lambda: {"trips": 0, "international": 0, "domestic": 0, "nights": 0})
    for f in await t_flights(s, pr, p):
        if f["status"] == "cancelled":
            continue
        x = g[f["passenger"]]
        x["trips"] += 1
        x[f["type"]] += 1
    for h in await t_hotels(s, pr, p):
        if h["status"] != "cancelled":
            g[h["guest"]]["nights"] += h["nights"]
    return [{"employee": k, **v} for k, v in sorted(g.items(), key=lambda kv: -kv[1]["trips"])]


def _docs(doc_type):
    async def run(s, pr, p):
        cids = await _companies(s, pr, p)
        rows = (await s.execute(select(TravelDocument).where(TravelDocument.company_id.in_(cids), TravelDocument.doc_type == doc_type, TravelDocument.status != "cancelled").order_by(TravelDocument.expiry_date))).scalars()
        out = [{"employee": d.employee.name, "holder": d.holder_kind, "type": d.visa_type or "Passport", "country": d.country, "expiry": d.expiry_date, "days": days_until(d.expiry_date), "status": d.status.replace("_", " "), "responsible": d.responsible.name if d.responsible else None} for d in rows if (days_until(d.expiry_date) or 9999) <= p.within]
        await audit(s, actor_id=pr.id, action="travel.documents_view", entity_type="travel_document", data={"report": doc_type, "count": len(out)})
        await s.commit()
        return out

    return run


DOC_COLS = [C("employee", "Employee"), C("holder", "Holder"), C("type", "Document", width=2), C("country", "Country"), C("expiry", "Expiry", "date"), C("days", "Days left", "number"), C("status", "Status"), C("responsible", "Responsible")]


# ---- contracts


async def _contracts(s, pr, p, live_only=True):
    cids = await _companies(s, pr, p)
    stmt = select(Contract).where(Contract.company_id.in_(cids))
    if live_only:
        stmt = stmt.where(Contract.status.in_(["active", "for_renewal", "expired"]))
    return list((await s.execute(stmt.order_by(Contract.end_date))).scalars())


def con_row(c: Contract) -> dict:
    return {"reference": c.reference, "title": c.title, "type": c.contract_type.replace("_", " "), "lessor": c.lessor.name if c.lessor else None, "start": c.start_date, "end": c.end_date, "days": days_until(c.end_date), "rent": c.monthly_rent_php, "status": c.status.replace("_", " ")}


CON_COLS = [C("reference", "Reference"), C("title", "Contract", width=3), C("type", "Type"), C("lessor", "Lessor", width=2), C("start", "Start", "date"), C("end", "End", "date"), C("days", "Days left", "number"), C("rent", "Monthly rent", "money"), C("status", "Status")]


async def k_register(s, pr, p):
    return [con_row(c) for c in await _contracts(s, pr, p, live_only=False)]


async def k_renewals(s, pr, p):
    return [con_row(c) for c in await _contracts(s, pr, p) if c.contract_type in ("office_lease", "staff_house") and (days_until(c.end_date) or 0) <= p.within]


async def k_expiring(s, pr, p):
    return [con_row(c) for c in await _contracts(s, pr, p) if (days_until(c.end_date) or 0) <= p.within]


async def k_rental(s, pr, p):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(RentPayment).where(RentPayment.company_id.in_(cids)).order_by(RentPayment.period.desc()))).scalars().all()
    g = defaultdict(lambda: {"lines": 0, "due": Decimal(0), "sent": Decimal(0), "paid": Decimal(0)})
    for r in rows:
        if not in_range(r.due_date, p) or r.status == "cancelled":
            continue
        x = g[r.period]
        x["lines"] += 1
        x[r.status] += r.amount_php
    return [{"period": k, **v, "total": v["due"] + v["sent"] + v["paid"]} for k, v in sorted(g.items(), reverse=True)]


# ---- administration


async def _tasks(s, pr, p):
    cids = await _companies(s, pr, p)
    stmt = select(Task).where(Task.company_id.in_(cids))
    if not pr.is_admin:
        stmt = stmt.where(or_(Task.assignee_id == pr.id, Task.created_by_id == pr.id))
    return list((await s.execute(stmt.order_by(Task.due_date.is_(None), Task.due_date))).scalars())


def task_row(t: Task) -> dict:
    return {"reference": t.reference, "title": t.title, "assignee": t.assignee.name if t.assignee else None, "due": t.due_date, "priority": t.priority, "status": t.status.replace("_", " "), "source": t.source_module, "completed": aware(t.completed_at).date() if t.completed_at else None}


TASK_COLS = [C("reference", "Reference"), C("title", "Task", width=3), C("assignee", "Assignee"), C("due", "Due", "date"), C("priority", "Priority"), C("status", "Status"), C("completed", "Completed", "date")]


async def x_assigned(s, pr, p):
    return [task_row(t) for t in await _tasks(s, pr, p) if t.status in (TaskStatus.open, TaskStatus.in_progress)]


async def x_overdue(s, pr, p):
    return [{**task_row(t), "days_overdue": (date.today() - t.due_date).days} for t in await _tasks(s, pr, p) if t.status in (TaskStatus.open, TaskStatus.in_progress) and t.due_date and t.due_date < date.today()]


async def x_sla(s, pr, p):
    rows = await _requests(s, pr, p)
    g = defaultdict(lambda: {"requests": 0, "responded_on_time": 0, "resolved_on_time": 0, "overdue_open": 0, "escalated": 0})
    for r in rows:
        x = g[r.priority]
        x["requests"] += 1
        if r.first_response_at and r.response_due_at and aware(r.first_response_at) <= aware(r.response_due_at):
            x["responded_on_time"] += 1
        end = r.closed_at if r.status in (S.closed, S.fulfilled) else None
        if end and r.resolution_due_at and aware(end) <= aware(r.resolution_due_at):
            x["resolved_on_time"] += 1
        if r.status in OPEN and r.resolution_due_at and aware(r.resolution_due_at) < now():
            x["overdue_open"] += 1
        x["escalated"] += r.escalation_level > 0
    order = ["critical", "high", "normal", "low"]
    return [{"priority": k, **v, "on_time_pct": round(100 * v["resolved_on_time"] / v["requests"]) if v["requests"] else None} for k, v in sorted(g.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 9)]


async def x_approvals(s, pr, p):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(ApprovalStep, Request).join(Request, Request.id == ApprovalStep.request_id).where(Request.company_id.in_(cids), ApprovalStep.decided_at.is_not(None)).order_by(ApprovalStep.decided_at.desc()))).all()
    return [{"date": aware(st.decided_at).date(), "request": r.reference, "subject": r.subject, "stage": st.name, "decision": st.status, "by": st.decided_by.name if st.decided_by else None, "for": st.approver.name if st.approver and st.decided_by and st.approver.id != st.decided_by.id else None, "comment": st.comment} for st, r in rows if in_range(st.decided_at, p) and (pr.is_admin or r.company_id in pr.company_ids)]


async def x_activity(s, pr, p):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(AuditEvent).where(or_(AuditEvent.company_id.is_(None), AuditEvent.company_id.in_(cids))).order_by(AuditEvent.id.desc()).limit(20000))).scalars()
    g = defaultdict(Counter)
    for a in rows:
        if in_range(a.at, p) and a.actor:
            g[a.actor.name][a.action.split(".")[0]] += 1
    mods = sorted({m for c in g.values() for m in c})
    return [{"person": k, "total": sum(v.values()), "modules": ", ".join(f"{m} {v[m]}" for m in mods if v[m])} for k, v in sorted(g.items(), key=lambda kv: -sum(kv[1].values()))]


async def x_audit(s, pr, p):
    cids = await _companies(s, pr, p)
    rows = (await s.execute(select(AuditEvent).where(or_(AuditEvent.company_id.is_(None), AuditEvent.company_id.in_(cids))).order_by(AuditEvent.id.desc()).limit(5000))).scalars()
    return [{"at": aware(a.at).replace(tzinfo=None), "actor": a.actor.name if a.actor else "System", "action": a.action, "record": a.entity_ref, "type": a.entity_type} for a in rows if in_range(a.at, p)]


admin_only = lambda p: p.is_admin  # noqa: E731
travel_docs = lambda p: p.is_admin or p.delegated("travel_documents")  # noqa: E731

REPORTS: list[Report] = [
    Report("request_register", "Requests", "Request Register", "Every request in your scope.", REQ_COLS, r_register, uses_dates=True),
    Report("pending_requests", "Requests", "Pending Requests", "Open requests: in approval or being processed.", REQ_COLS, r_pending, uses_dates=True),
    Report("approval_aging", "Requests", "Approval Aging", "How long each request has waited at its current approval stage.", [C("reference", "Reference"), C("subject", "Subject", width=3), C("stage", "Stage"), C("approver", "Approver"), C("waiting_days", "Days waiting", "number"), C("bucket", "Bucket"), C("priority", "Priority")], r_aging, uses_dates=True),
    Report("requests_by_department", "Requests", "Requests by Department", "Volume and outcome per department.", GROUP_COLS("Department"), r_by_dept, uses_dates=True, totals=["total", "open", "closed", "rejected", "overdue"]),
    Report("requests_by_company", "Requests", "Requests by Company", "Volume and outcome per company.", GROUP_COLS("Company"), r_by_company, uses_dates=True, totals=["total", "open", "closed", "rejected", "overdue"]),
    Report("priority_concerns", "Requests", "Priority Concerns", "Open High/Urgent requests and anything overdue.", REQ_COLS, r_priority, uses_dates=True),
    Report("supply_requests", "Requests", "Supply Requests", "Requested items, quantities and what has been received.", [C("reference", "Request"), C("requester", "Requester"), C("department", "Department"), C("item", "Item", width=3), C("quantity", "Qty", "number"), C("unit", "Unit"), C("received", "Received", "number"), C("status", "Status"), C("fulfillment", "Fulfillment")], r_supply, uses_dates=True, totals=["quantity", "received"]),
    Report("fulfillment", "Requests", "Fulfillment Report", "Completed requests, time to close and SLA outcome.", [C("reference", "Reference"), C("subject", "Subject", width=3), C("priority", "Priority"), C("owner", "Owner"), C("submitted", "Submitted", "date"), C("days_to_close", "Days to close", "number"), C("met_sla", "Met SLA")], r_fulfillment, uses_dates=True),
    Report("asset_registry", "Assets", "Asset Registry", "Every asset with condition, status and holder.", ASSET_COLS, a_registry),
    Report("asset_assignment", "Assets", "Asset Assignment", "Issued assets and acknowledgement status.", ASSET_COLS + [C("acknowledged", "Acknowledged")], a_assignment),
    Report("asset_transfer", "Assets", "Asset Transfer", "Issues, returns and transfers.", EVENT_COLS, a_transfer, uses_dates=True),
    Report("asset_repair", "Assets", "Asset Repair", "Repairs with provider, status and cost.", [C("reference", "Repair"), C("asset", "Asset tag"), C("name", "Asset", width=2), C("issue", "Issue", width=3), C("provider", "Provider"), C("status", "Status"), C("cost", "Cost", "money"), C("opened", "Opened", "date"), C("completed", "Completed", "date")], a_repair, uses_dates=True, totals=["cost"]),
    Report("asset_receiving", "Assets", "Asset Receiving", "Deliveries recorded against requests.", [C("reference", "Receipt"), C("date", "Date", "date"), C("item", "Item", width=3), C("quantity", "Qty", "number"), C("unit", "Unit"), C("assets", "Assets registered", width=2), C("dr", "DR no."), C("supplier", "Supplier"), C("by", "Received by")], a_receiving, uses_dates=True),
    Report("unreturned_assets", "Assets", "Unreturned Assets", "Assets held by inactive people, or not acknowledged after 7 days.", ASSET_COLS + [C("reason", "Reason", width=2.5)], a_unreturned),
    Report("stock_on_hand", "Inventory", "Stock on Hand", "Every active stock line with value.", INV_COLS, i_stock, totals=["on_hand", "reserved", "available", "value"]),
    Report("low_stock", "Inventory", "Low Stock / Reorder", "Lines at or below their reorder level, with a suggested order.", INV_COLS + [C("suggested", "Suggested order", "number")], i_low),
    Report("stock_movements", "Inventory", "Stock Movement Report", "Stock in, issues, transfers, adjustments and write-offs.", [C("date", "Date", "date"), C("reference", "Movement"), C("code", "Item code"), C("name", "Item", width=2.5), C("location", "Location"), C("kind", "Movement"), C("quantity", "Qty", "number"), C("balance", "Balance", "number"), C("to", "Issued to"), C("by", "By"), C("reason", "Reason", width=2)], i_moves, uses_dates=True),
    Report("inventory_valuation", "Inventory", "Inventory Valuation", "Units and value by category and location.", [C("category", "Category"), C("location", "Location", width=2), C("lines", "Lines", "number"), C("units", "Units", "number"), C("value", "Value", "money")], i_valuation, totals=["lines", "units", "value"]),
    Report("count_variance", "Inventory", "Inventory Count Variance", "Differences found in physical counts.", [C("count", "Count"), C("status", "Status"), C("code", "Item code"), C("name", "Item", width=2.5), C("location", "Location"), C("expected", "Expected", "number"), C("counted", "Counted", "number"), C("variance", "Variance", "number"), C("value", "Value", "money")], i_variance, uses_dates=True, totals=["variance", "value"]),
    Report("issuance_by_department", "Inventory", "Issuance by Department", "Stock issued to each department.", [C("department", "Department", width=2), C("issues", "Issues", "number"), C("units", "Units", "number"), C("value", "Value", "money")], i_by_dept, uses_dates=True, totals=["issues", "units", "value"]),
    Report("vehicle_registry", "Fleet", "Vehicle Registry", "Every vehicle with its key dates.", VEH_COLS, f_registry),
    Report("pms_due", "Fleet", "PMS Due Report", "Preventive maintenance due within the window.", DUE_COLS, _due("next_pms_date", "PMS"), uses_within=True),
    Report("insurance_expiry", "Fleet", "Insurance Expiry Report", "Insurance expiring within the window.", DUE_COLS, _due("insurance_expiry_date", "Insurance"), uses_within=True),
    Report("registration_renewal", "Fleet", "Vehicle Registration Renewal", "Registrations due within the window.", DUE_COLS, _due("registration_renewal_date", "Registration"), uses_within=True),
    Report("fleet_card_monitoring", "Fleet", "Fleet Card Monitoring", "Limits, statements billed and Finance payments per card.", [C("card", "Card"), C("vehicle", "Vehicle", width=2.5), C("limit", "Monthly limit", "money"), C("billed", "Billed", "money"), C("paid", "Paid", "money"), C("pending", "With Finance", "number"), C("status", "Status")], f_cards, uses_dates=True, totals=["billed", "paid"]),
    Report("rfid_payment_monitoring", "Fleet", "RFID Payment Monitoring", "RFID reloads handed to Finance and their payment status.", [C("reference", "Reference"), C("account", "Account", width=2), C("vehicle", "Vehicle", width=2), C("amount", "Amount", "money"), C("status", "Status"), C("finance_reference", "Finance ref."), C("requested", "Requested", "date"), C("paid", "Paid", "date")], f_rfid, uses_dates=True, totals=["amount"]),
    Report("fleet_repair_history", "Fleet", "Repair History", "PMS, repairs and parts per vehicle.", [C("reference", "Reference"), C("vehicle", "Vehicle", width=2.5), C("kind", "Type"), C("date", "Date", "date"), C("description", "Work done", width=3), C("provider", "Provider"), C("odometer", "Odometer", "number"), C("cost", "Cost", "money"), C("status", "Status")], f_repairs, uses_dates=True, totals=["cost"]),
    Report("government_registrations", "Compliance", "Government Registration Report", "Every registration with expiry and filing dates.", REG_COLS, c_regs),
    Report("expiring_documents", "Compliance", "Expiring Documents", "Registrations due or expiring within the window.", REG_COLS, c_expiring, uses_within=True),
    Report("renewal_calendar", "Compliance", "Renewal Calendar", "All dated obligations across compliance, customs, fleet and contracts.", [C("date", "Date", "date"), C("days", "Days left", "number"), C("module", "Module"), C("what", "What"), C("title", "Item", width=3), C("company", "Company")], c_calendar, uses_within=True),
    Report("sec_gis", "Compliance", "SEC / GIS Monitoring", "SEC registrations and GIS filings.", REG_COLS, c_secgis),
    Report("business_permits", "Compliance", "Business Permit Monitoring", "Business permits per site.", REG_COLS, c_permits),
    Report("boc_cases", "Compliance", "BOC Case Report", "Import and export cases and their milestones.", [C("reference", "Case"), C("direction", "Direction"), C("goods", "Goods", width=3), C("bl", "BL / AWB"), C("entry", "Entry no."), C("eta", "ETA", "date"), C("officer", "Officer"), C("status", "Milestone")], c_boc, uses_dates=True),
    Report("flight_bookings", "Travel", "Flight Booking Report", "Bookings by departure date.", [C("reference", "Reference"), C("passenger", "Passenger"), C("type", "Type"), C("route", "Route", width=3), C("departure", "Departure", "date"), C("return", "Return", "date"), C("airline", "Airline"), C("pnr", "PNR"), C("status", "Status")], t_flights, uses_dates=True),
    Report("hotel_reservations", "Travel", "Hotel Reservation Report", "Reservations by check-in date.", [C("reference", "Reference"), C("guest", "Guest"), C("hotel", "Hotel", width=2.5), C("city", "City"), C("check_in", "Check-in", "date"), C("check_out", "Check-out", "date"), C("nights", "Nights", "number"), C("confirmation", "Confirmation"), C("status", "Status")], t_hotels, uses_dates=True, totals=["nights"]),
    Report("employee_travel", "Travel", "Employee Travel Report", "Trips and hotel nights per employee.", [C("employee", "Employee", width=2.5), C("trips", "Trips", "number"), C("domestic", "Domestic", "number"), C("international", "International", "number"), C("nights", "Hotel nights", "number")], t_employee, uses_dates=True, totals=["trips", "domestic", "international", "nights"]),
    Report("visa_expiry", "Travel", "Visa Expiry Report", "Visas expiring within the window. Restricted and audited.", DOC_COLS, _docs("visa"), uses_within=True, restricted=travel_docs),
    Report("passport_renewal", "Travel", "Passport Renewal Report", "Passports expiring within the window. Restricted and audited.", DOC_COLS, _docs("passport"), uses_within=True, restricted=travel_docs),
    Report("contract_register", "Contracts", "Contract Register", "Every contract including history.", CON_COLS, k_register),
    Report("lease_renewals", "Contracts", "Lease Renewal Report", "Office and staff-house leases ending within the window.", CON_COLS, k_renewals, uses_within=True),
    Report("monthly_rental_summary", "Contracts", "Monthly Rental Summary", "Rent due, with Finance and paid per month.", [C("period", "Month"), C("lines", "Contracts", "number"), C("due", "Not sent", "money"), C("sent", "With Finance", "money"), C("paid", "Paid", "money"), C("total", "Total", "money")], k_rental, uses_dates=True, totals=["due", "sent", "paid", "total"]),
    Report("expiring_contracts", "Contracts", "Expiring Contracts", "All contracts ending within the window.", CON_COLS, k_expiring, uses_within=True),
    Report("assigned_tasks", "Administration", "Assigned Tasks", "Open tasks by assignee.", TASK_COLS, x_assigned),
    Report("overdue_tasks", "Administration", "Overdue Tasks", "Open tasks past their due date.", TASK_COLS + [C("days_overdue", "Days overdue", "number")], x_overdue),
    Report("sla_performance", "Administration", "SLA Performance", "Response and resolution against targets, per priority.", [C("priority", "Priority"), C("requests", "Requests", "number"), C("responded_on_time", "Responded on time", "number"), C("resolved_on_time", "Resolved on time", "number"), C("on_time_pct", "On-time %", "number"), C("overdue_open", "Overdue open", "number"), C("escalated", "Escalated", "number")], x_sla, uses_dates=True, totals=["requests", "responded_on_time", "resolved_on_time", "overdue_open", "escalated"]),
    Report("approval_history", "Administration", "Approval History", "Every approval decision with who acted and for whom.", [C("date", "Date", "date"), C("request", "Request"), C("subject", "Subject", width=2.5), C("stage", "Stage"), C("decision", "Decision"), C("by", "Decided by"), C("for", "On behalf of"), C("comment", "Comment", width=2.5)], x_approvals, uses_dates=True),
    Report("admin_activity", "Administration", "Administrative Activity Report", "Recorded actions per person and module.", [C("person", "Person", width=2), C("total", "Actions", "number"), C("modules", "By module", width=5)], x_activity, uses_dates=True, restricted=admin_only),
    Report("audit_report", "Administration", "Audit Report", "The audit trail for the period.", [C("at", "When", "date"), C("actor", "Who"), C("action", "Action", width=2), C("record", "Record"), C("type", "Type")], x_audit, uses_dates=True, restricted=admin_only),
]
BY_KEY = {r.key: r for r in REPORTS}


def _params(date_from, date_to, company, within) -> Params:
    return Params(date_from, date_to, company, within)


@router.get("/reports")
async def catalogue(principal: Staff) -> list[dict]:
    return [
        {"key": r.key, "module": r.module, "title": r.title, "description": r.description, "uses_dates": r.uses_dates, "uses_within": r.uses_within}
        for r in REPORTS
        if r.restricted is None or r.restricted(principal)
    ]


async def run_report(session, principal: Principal, key: str, p: Params) -> tuple[Report, list[dict], dict | None]:
    rep = BY_KEY.get(key)
    if rep is None:
        raise not_found("Unknown report")
    if rep.restricted and not rep.restricted(principal):
        raise forbidden("This report needs explicit authorization")
    rows = await rep.run(session, principal, p)
    totals = None
    if rep.totals and rows:
        totals = {k: sum((r.get(k) or 0) for r in rows) for k in rep.totals}
    return rep, rows, totals


def _json(v):
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


@router.get("/reports/{key}")
async def report(
    key: str, principal: Staff, session: Session, date_from: date | None = None, date_to: date | None = None, company: str | None = None, within: int = Query(60, ge=0, le=730),
) -> dict:
    rep, rows, totals = await run_report(session, principal, key, _params(date_from, date_to, company, within))
    return {
        "key": rep.key, "title": rep.title, "module": rep.module, "description": rep.description,
        "columns": [{"key": c.key, "label": c.label, "kind": c.kind} for c in rep.columns],
        "rows": [{k: _json(v) for k, v in r.items()} for r in rows[:1000]], "total_rows": len(rows),
        "totals": {k: _json(v) for k, v in (totals or {}).items()} or None,
    }


@router.get("/reports/{key}/export")
async def report_export(
    key: str, principal: Staff, session: Session, format: str = "xlsx", date_from: date | None = None, date_to: date | None = None, company: str | None = None, within: int = Query(60, ge=0, le=730),
):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    from .io import MONEY_FMT, _file, _xlsx_bytes, safe_csv, safe_xlsx

    p = _params(date_from, date_to, company, within)
    rep, rows, totals = await run_report(session, principal, key, p)
    filters = [f"Period: {date_from or 'start'} to {date_to or 'today'}"] if rep.uses_dates else []
    if rep.uses_within:
        filters.append(f"Window: next {within} days")
    if company:
        filters.append(f"Company: {company}")
    co = principal.employee.company.name if len(principal.company_ids) == 1 else "All authorized companies"
    await audit(session, actor_id=principal.id, action="report.export", entity_type="report", entity_ref=key, data={"format": format, "rows": len(rows)})
    await session.commit()
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    if format == "pdf":
        data = table_report(rep.title, co, rep.columns, rows, subtitle=filters, totals=totals, generated_by=principal.employee.name, land=len(rep.columns) > 5)
        return _file(data, f"{key}-{stamp}.pdf", "pdf")
    if format == "csv":
        import csv as _csv
        import io as _io

        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow([c.label for c in rep.columns])
        for r in rows:
            w.writerow([safe_csv(r.get(c.key)) for c in rep.columns])
        return _file(("﻿" + buf.getvalue()).encode("utf-8"), f"{key}-{stamp}.csv", "csv")
    wb = Workbook()
    ws = wb.active
    ws.title = rep.title[:31]
    ws.append([c.label for c in rep.columns])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([safe_xlsx(r.get(c.key)) for c in rep.columns])
    if totals:
        ws.append([("Total" if i == 0 else totals.get(c.key)) for i, c in enumerate(rep.columns)])
        for c in ws[ws.max_row]:
            c.font = Font(bold=True)
    for i, c in enumerate(rep.columns, 1):
        from openpyxl.utils import get_column_letter

        col = get_column_letter(i)
        ws.column_dimensions[col].width = 14 if c.kind != "text" else 24
        for cell in ws[col][1:]:
            if c.kind == "money":
                cell.number_format = MONEY_FMT
            elif c.kind == "date":
                cell.number_format = "yyyy-mm-dd"
    ws.freeze_panes = "A2"
    sm = wb.create_sheet("Summary")
    for row in (("Report", rep.title), ("Company", co), ("Records", len(rows)), ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")), ("Generated by", principal.employee.name), *[tuple(f.split(": ", 1)) for f in filters]):
        sm.append(row)
    return _file(_xlsx_bytes(wb), f"{key}-{stamp}.xlsx", "xlsx")


# ------------------------------------------------------------------ dashboards (§25)


@router.get("/dashboard/executive")
async def executive(principal: Staff, session: Session) -> dict:
    p = Params(None, None, None, 60)
    reqs = await _requests(session, principal, p)
    t = now()
    open_ = [r for r in reqs if r.status in OPEN]
    assets = await _assets(session, principal, p)
    vehicles = await _veh(session, principal, p)
    regs = await _regs(session, principal, p)
    cons = await _contracts(session, principal, p)
    cids = principal.company_ids
    flights = (await session.execute(select(FlightBooking).where(FlightBooking.company_id.in_(cids), FlightBooking.status.in_(["requested", "booked"])))).scalars().all()
    tasks = await _tasks(session, principal, p)
    month_start = date.today().replace(day=1)
    done_month = [x for x in tasks if x.status == TaskStatus.done and x.completed_at and aware(x.completed_at).date() >= month_start]
    due_month = [x for x in tasks if x.status != TaskStatus.cancelled and ((x.due_date and x.due_date >= month_start and x.due_date <= date.today()) or x in done_month)]
    inv = await _inv(session, principal, p)
    scope = await approver_scope_ids(session, principal)
    upcoming = sum(1 for v in vehicles if any((days_until(d) or 999) <= 30 for d in (v.registration_renewal_date, v.insurance_expiry_date))) + sum(1 for r in regs if r.status in ("ongoing", "for_renewal") and (days_until(r.due_date or r.expiry_date) or 999) <= 30) + sum(1 for c in cons if (days_until(c.end_date) or 999) <= 60)
    return {
        "total_open_requests": len(open_),
        "pending_approvals": sum(1 for r in reqs if r.status in IN_APPROVAL),
        "my_pending_approvals": (await session.execute(select(func.count()).where(ApprovalStep.status == "pending", ApprovalStep.approver_id.in_(scope or {0})))).scalar_one(),
        "overdue_requests": sum(1 for r in open_ if r.resolution_due_at and aware(r.resolution_due_at) < t),
        "priority_concerns": sum(1 for r in open_ if r.priority in ("high", "critical")),
        "upcoming_renewals": upcoming,
        "active_assets": sum(1 for a in assets if a.status in ("in_stock", "assigned")),
        "assets_under_repair": sum(1 for a in assets if a.status == "under_repair"),
        "fleet_maintenance_due": sum(1 for v in vehicles if v.status in ("active", "under_maintenance") and (days_until(v.next_pms_date) or 999) <= 30),
        "expiring_government_documents": sum(1 for r in regs if r.status in ("ongoing", "for_renewal", "expired") and (days_until(r.due_date or r.expiry_date) or 999) <= 60),
        "contract_renewals": sum(1 for c in cons if c.status in ("for_renewal", "expired")),
        "travel_requests": len(flights),
        "task_completion": {"done": len(done_month), "due": len(due_month), "pct": round(100 * len(done_month) / len(due_month)) if due_month else None},
        "low_stock": sum(1 for i in inv if i.available <= i.reorder_level and i.reorder_level > 0),
    }


@router.get("/dashboard/assistant")
async def assistant(principal: Staff, session: Session) -> dict:
    t = now()
    mine = (await session.execute(select(Request).where(Request.assigned_to_id == principal.id, Request.status.in_(list(OPEN))))).scalars().all()
    tasks = (await session.execute(select(Task).where(Task.assignee_id == principal.id, Task.status.in_([TaskStatus.open, TaskStatus.in_progress])))).scalars().all()
    regs = (await session.execute(select(GovRegistration).where(GovRegistration.responsible_id == principal.id, GovRegistration.status.in_(["ongoing", "for_renewal", "expired"])))).scalars().all()
    return {
        "assigned_requests": len(mine),
        "assigned_tasks": len(tasks),
        "overdue_follow_ups": sum(1 for r in mine if r.resolution_due_at and aware(r.resolution_due_at) < t) + sum(1 for x in tasks if x.due_date and x.due_date < date.today()),
        "pending_documents": sum(1 for r in mine if r.status == S.awaiting_finance),
        "upcoming_renewals": sum(1 for r in regs if (days_until(r.due_date or r.expiry_date) or 999) <= 60),
        "awaiting_coordination": sum(1 for r in mine if r.status in (S.approved,)),
    }
