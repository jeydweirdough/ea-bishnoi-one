"""
Phase 2.9 — official documents (EXECUTIVE-ADMIN.md §19–22).

Each template turns one real record into a printable, signature-ready PDF with a control
number (EA-<TYPE>-<YEAR>-<NNNN>), version, status and history. A document never claims an
approval or signature that did not happen: approval lines are filled only from recorded
approval steps, unapproved documents carry a DRAFT watermark, and "Signed" requires an
uploaded signed copy (a scan is not treated as a verified electronic signature).
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Awaitable, Callable

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..config import get_settings
from ..core import aware, audit, bad_request, conflict, forbidden, not_found, now
from ..models import Attachment, Company, DocumentSequence, Employee, Request, RequestStatus as S, Task
from ..models_ops import Asset, AssetEvent, AssetRepair, FinanceRequest, FleetCard, Receipt, Vehicle, VehicleService
from ..models_ops2 import BocCase, FlightBooking, GovRegistration, HotelReservation
from ..models_ops3 import BankingCase, Contract, DocumentEvent, GeneratedDocument, InventoryCount, InventoryItem, StockMovement
from ..pdf import Column, DocSpec, Signature, fmt, render
from ..security import CurrentPrincipal, Principal, Session, Staff
from ..serialize import attachment_out, iso, person
from ..workflow import can_view

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# Document types and their control-number prefixes (configurable here; distinct from record references).
DOC_TYPES = {
    "REQ": "Request forms", "PR": "Purchase requests", "PO": "Purchase orders", "MEMO": "Approval memos", "ASF": "Asset forms", "MNT": "Maintenance forms",
    "FLT": "Fleet forms", "CMP": "Compliance forms", "TRV": "Travel forms", "CON": "Contract forms", "BNK": "Banking forms", "ADM": "Administrative reports", "INV": "Inventory forms",
}

ITEM_COLS = [Column("n", "#", "number", 0.4), Column("item", "Item / description", "text", 3.4), Column("brand", "Brand / model", "text", 1.8), Column("qty", "Qty", "number", 0.7), Column("unit", "Unit", "text", 0.8), Column("received", "Received", "number", 0.9)]


# Records whose "approved" state comes from a recorded approval decision (request route, bank decision).
APPROVAL_BACKED = {"request", "banking"}


@dataclass
class Template:
    key: str
    title: str
    group: str
    doc_type: str
    related: str  # request | asset | asset_repair | receipt | vehicle | vehicle_service | fleet_card | finance | registration | boc | flight | hotel | contract | banking | task | inventory_item | inventory_count | stock_movement | period
    build: Callable[..., Awaitable[DocSpec]]
    applies: Callable[[object], str | None] = lambda r: None  # returns a reason when not applicable
    employee_ok: bool = False  # requesters may generate it for their own record


# ------------------------------------------------------------------ helpers


async def company_of(session, company_id: int | None) -> Company | None:
    return await session.get(Company, company_id) if company_id else None


def base(t: Template, company: Company | None, **kw) -> DocSpec:
    return DocSpec(title=t.title, company_name=company.name if company else "Bishnoi One", company_address=company.address if company else None, issue_date=date.today(), **kw)


def step_signatures(req: Request) -> list[Signature]:
    sigs = [Signature("Prepared by", req.requester.name, req.requester.designation, req.department.name if req.department else None, f"Submitted in Executive Admin {fmt(aware(req.submitted_at))}" if req.submitted_at else None)]
    for st in req.steps:
        if st.status == "skipped":
            continue
        recorded = None
        if st.status == "approved" and st.decided_at:
            who = st.decided_by.name if st.decided_by else ""
            recorded = f"Approved in Executive Admin by {who}, {fmt(aware(st.decided_at))}"
        sigs.append(Signature(f"Approved by — {st.name}", (st.approver.name if st.approver else None), st.approver.designation if st.approver else None, None, recorded))
    return sigs


def req_status(req: Request) -> tuple[str, str | None]:
    """(document status, watermark) from the real request state."""
    if req.status == S.draft:
        return "draft", "DRAFT"
    if req.status in (S.submitted, S.under_review, S.returned):
        return "for_approval", "FOR APPROVAL"
    if req.status == S.rejected:
        return "rejected", "REJECTED"
    if req.status == S.cancelled:
        return "rejected", "CANCELLED"
    return "approved", None


def req_info(req: Request) -> list[tuple]:
    return [
        ("Request reference", req.reference), ("Requested by", f"{req.requester.name} ({req.requester.employee_no})"), ("Department", req.department.name if req.department else "—"),
        ("Company", req.company.name), ("Priority", req.priority.title()), ("Needed by", req.needed_by), ("Status", req.status.replace("_", " ").title()),
        ("Submitted", aware(req.submitted_at) if req.submitted_at else None),
    ]


def items_rows(req: Request) -> list[dict]:
    return [{"n": i + 1, "item": it.item_name + (f" — {it.description}" if it.description else ""), "brand": " ".join(x for x in (it.brand, it.model) if x), "qty": it.quantity, "unit": it.unit, "received": it.received_quantity} for i, it in enumerate(req.items)]


def approval_table(req: Request) -> tuple:
    rows = [{"stage": s.name, "approver": s.approver.name if s.approver else "—", "decision": s.status.title(), "by": s.decided_by.name if s.decided_by else "—", "when": aware(s.decided_at) if s.decided_at else None, "comment": s.comment or ""} for s in req.steps]
    return ("table", "Approval record", [Column("stage", "Stage", "text", 1.6), Column("approver", "Approver", "text", 1.6), Column("decision", "Decision", "text", 1), Column("by", "Decided by", "text", 1.5), Column("when", "When", "text", 1.6), Column("comment", "Comment", "text", 2.4)], rows, None)


# ------------------------------------------------------------------ builders: requests


def b_request_form(kind_label: str):
    async def build(t: Template, s, p, req: Request):
        status, wm = req_status(req)
        secs = [("text", "Subject", req.subject)]
        if req.items:
            secs.append(("table", "Items requested", ITEM_COLS, items_rows(req), {"qty": sum(i.quantity for i in req.items)}))
        if req.description:
            secs.append(("text", "Details", req.description))
        if req.purpose:
            secs.append(("text", "Purpose / justification", req.purpose))
        if req.location or req.delivery_location:
            secs.append(("info", None, [("Location", req.location), ("Deliver to", req.delivery_location)]))
        if req.steps:
            secs.append(approval_table(req))
        return base(t, req.company, reference=req.reference, status_label=status.replace("_", " ").title(), watermark=wm, info=req_info(req), sections=secs, signatures=step_signatures(req)), status

    return build


async def b_purchase_order(t, s, p, req: Request):
    status, wm = req_status(req)
    secs = [
        ("info", "Supplier", [("Supplier", "To be confirmed by Executive Admin"), ("Delivery to", req.delivery_location or req.location or req.company.name), ("Required date", req.needed_by), ("Purpose", req.purpose)]),
        ("table", "Order lines", ITEM_COLS[:-1], items_rows(req), {"qty": sum(i.quantity for i in req.items)}),
        ("text", "Terms", "Deliver to the address above with a delivery receipt referencing this PO number. Payment is processed by Finance on presentation of a valid invoice."),
    ]
    sigs = [Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin")] + [x for x in step_signatures(req)[1:]]
    return base(t, req.company, reference=req.reference, status_label=status.replace("_", " ").title(), watermark=wm, info=req_info(req)[:4], sections=secs, signatures=sigs), status


async def b_approval_memo(t, s, p, req: Request):
    status, wm = req_status(req)
    decided = [x for x in req.steps if x.decided_at]
    outcome = {"approved": "has been APPROVED", "rejected": "has been REJECTED"}.get(status, "is still in approval")
    body = f"This memo records that request {req.reference} — “{req.subject}”, submitted by {req.requester.name} ({req.department.name if req.department else 'no department'}) — {outcome}."
    if decided:
        body += f" The last decision was made by {decided[-1].decided_by.name if decided[-1].decided_by else 'an approver'} on {fmt(aware(decided[-1].decided_at))}."
    secs = [("text", None, body), approval_table(req)]
    return base(t, req.company, reference=req.reference, status_label=status.replace("_", " ").title(), watermark=wm, info=req_info(req)[:6], sections=secs, signatures=[Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin")]), status


async def b_concern_resolution(t, s, p, req: Request):
    from ..models import RequestEvent

    events = (await s.execute(select(RequestEvent).where(RequestEvent.request_id == req.id, RequestEvent.type.in_(["fulfilled", "confirmed", "closed"])).order_by(RequestEvent.at))).scalars().all()
    resolution = next((e.message for e in events if e.type == "fulfilled"), None)
    confirmed = next((e for e in events if e.type == "confirmed"), None)
    status = "approved" if req.status in (S.fulfilled, S.closed) else "draft"
    secs = [("text", "Concern", f"{req.subject}\n{req.description}"), ("text", "Resolution", resolution or "Not resolved yet."), approval_table(req)]
    sigs = [Signature("Resolved by", req.assigned_to.name if req.assigned_to else None, req.assigned_to.designation if req.assigned_to else None, "Executive Admin"), Signature("Acknowledged by", req.requester.name, req.requester.designation, req.department.name if req.department else None, f"Confirmed in Executive Admin {fmt(aware(confirmed.at))}" if confirmed else None)]
    return base(t, req.company, reference=req.reference, status_label=req.status.replace("_", " ").title(), watermark=None if status == "approved" else "NOT RESOLVED", info=req_info(req), sections=secs, signatures=sigs), status


# ------------------------------------------------------------------ builders: assets & maintenance


def asset_pairs(a: Asset) -> list[tuple]:
    return [("Asset tag", a.reference), ("Description", a.name), ("Category", a.category), ("Brand / model", " ".join(x for x in (a.brand, a.model) if x) or "—"), ("Serial number", a.serial_number), ("Quantity", f"{a.quantity} {a.unit}"), ("Condition", a.condition.replace("_", " ").title()), ("Location", a.location)]


async def _last_event(s, a: Asset, types: list[str]) -> AssetEvent | None:
    return (await s.execute(select(AssetEvent).where(AssetEvent.asset_id == a.id, AssetEvent.type.in_(types)).order_by(AssetEvent.at.desc(), AssetEvent.id.desc()))).scalars().first()


def b_asset_movement(kind: str):
    async def build(t, s, p, a: Asset):
        ev = await _last_event(s, a, {"issuance": ["assigned", "transferred"], "transfer": ["transferred"], "return": ["returned"], "turnover": ["acknowledged", "assigned"]}[kind])
        holder = a.holder
        info = [("Issued to" if kind != "return" else "Returned by", (holder.name if holder else (ev.from_holder.name if ev and ev.from_holder else "—"))), ("Department", a.department.name if a.department else "—"), ("Date", aware(ev.at).date() if ev else date.today()), ("Event", ev.message if ev else "—")]
        secs = [("info", "Asset", asset_pairs(a))]
        many = False
        if kind in ("issuance", "turnover") and a.holder_id and a.issue_ref:
            # Handed over together: one form lists every item in the issuance.
            together = (await s.execute(select(Asset).where(Asset.issue_ref == a.issue_ref, Asset.holder_id == a.holder_id).order_by(Asset.id))).scalars().all()
            if len(together) > 1:
                info.insert(0, ("Issuance", a.issue_ref))
                rows = [{"n": i + 1, "ref": x.reference, "item": x.name, "serial": x.serial_number or "—", "cond": (x.condition or "").replace("_", " ").capitalize()} for i, x in enumerate(together)]
                cols = [Column("n", "#", "number", 0.4), Column("ref", "Asset", "text", 1.6), Column("item", "Item", "text", 2.4), Column("serial", "Serial number", "text", 1.8), Column("cond", "Condition", "text", 1.1)]
                secs = [("table", f"Items issued ({len(together)})", cols, rows, None)]
                many = True
        cert = {
            "issuance": "I acknowledge receipt of the asset described above in the stated condition. I will use it for company purposes, take reasonable care of it, report damage or loss promptly, and return it on request.",
            "transfer": "The asset above was transferred as recorded. The receiving person accepts responsibility for it from the date of transfer.",
            "return": "The asset above was returned to Executive Admin in the condition stated.",
            "turnover": "I confirm the turnover of the asset above and accept accountability for its care and return.",
        }[kind]
        if many:
            cert = cert.replace("the asset described above", "the items listed above").replace("the asset above", "the items above").replace("use it", "use them").replace("care of it", "care of them").replace("return it", "return them")
        ack = f"Acknowledged in Executive Admin {fmt(aware(a.acknowledged_at))}" if a.acknowledged_at and kind in ("issuance", "turnover") else None
        sigs = [Signature("Issued by" if kind != "return" else "Received by", (a.issued_by.name if a.issued_by and kind != "return" else p.employee.name), None, "Executive Admin"), Signature("Received by" if kind != "return" else "Returned by", holder.name if holder and kind != "return" else (ev.from_holder.name if ev and ev.from_holder else None), holder.designation if holder and kind != "return" else None, None, ack)]
        return base(t, a.company, reference=a.reference, status_label="Issued" if ev else "Draft", info=info, sections=secs, certification=cert, signatures=sigs), "approved" if ev else "draft"

    return build


async def b_receiving(t, s, p, r: Receipt):
    req = await s.get(Request, r.request_id)
    rows = [{"n": i + 1, "item": l["item_name"], "brand": ", ".join(a["reference"] + (f" SN {a['serial_number']}" if a.get("serial_number") else "") for a in l.get("assets", [])) or "—", "qty": l["quantity"], "unit": l["unit"], "received": l["quantity"]} for i, l in enumerate(r.lines)]
    cols = [Column("n", "#", "number", 0.4), Column("item", "Item", "text", 3), Column("brand", "Registered as", "text", 2.4), Column("qty", "Qty", "number", 0.7), Column("unit", "Unit", "text", 0.8)]
    info = [("Receipt", r.reference), ("Request", req.reference if req else "—"), ("Received on", r.received_on), ("Delivery receipt no.", r.delivery_reference), ("Supplier", r.supplier), ("Received by", r.received_by.name)]
    sigs = [Signature("Received by", r.received_by.name, r.received_by.designation, "Executive Admin", f"Recorded in Executive Admin {fmt(aware(r.created_at))}"), Signature("Delivered by", None, None, r.supplier)]
    return base(t, r.company, reference=r.reference, status_label="Received", info=info, sections=[("table", "Items received", cols, rows, {"qty": sum(l["quantity"] for l in r.lines)})], certification="The items above were received in good order unless noted.", signatures=sigs), "approved"


def b_repair(kind: str):
    async def build(t, s, p, r: AssetRepair):
        a = r.asset
        done = r.status == "completed"
        info = [("Repair", r.reference), ("Asset", f"{a.reference} · {a.name}"), ("Serial", a.serial_number), ("Opened", aware(r.opened_at).date()), ("Provider", r.provider), ("Status", r.status.replace("_", " ").title()), ("Cost", r.cost_php and fmt(r.cost_php, "money")), ("Completed", aware(r.completed_at).date() if r.completed_at else None)]
        secs = [("text", "Problem reported", r.issue)]
        if kind in ("completion", "authorization") and r.notes:
            secs.append(("text", "Notes", r.notes))
        if kind == "completion":
            secs.append(("text", "Outcome", f"Condition after repair: {(r.outcome_condition or '—').replace('_', ' ').title()}" if done else "Repair not completed yet."))
        role2 = {"request": "Approved by", "job_order": "Accepted by (provider)", "authorization": "Authorized by", "completion": "Accepted by"}[kind]
        sigs = [Signature("Requested by" if kind == "request" else "Prepared by", r.opened_by.name, r.opened_by.designation, "Executive Admin"), Signature(role2, None)]
        status = "approved" if (kind != "completion" or done) else "draft"
        return base(t, a.company, reference=r.reference, status_label=r.status.replace("_", " ").title(), watermark=None if status == "approved" else "NOT COMPLETED", info=info, sections=secs, signatures=sigs), status

    return build


# ------------------------------------------------------------------ builders: fleet


def veh_pairs(v: Vehicle) -> list[tuple]:
    return [("Vehicle", f"{v.make} {v.model} {v.year_model or ''}".strip()), ("Plate", v.plate_number or "—"), ("Conduction sticker", v.conduction_sticker), ("Type", v.vehicle_type), ("Color", v.color), ("Registered owner", v.owner_name), ("Odometer", f"{v.odometer_km:,} km" if v.odometer_km else None), ("Reference", v.reference)]


async def b_vehicle_assignment(t, s, p, v: Vehicle):
    d = v.assigned_driver
    secs = [("info", "Vehicle", veh_pairs(v)), ("info", "Assignment", [("Assigned driver", d.name if d else "—"), ("Department", d.department.name if d and d.department else "—"), ("Registration valid until", v.registration_renewal_date), ("Insurance valid until", v.insurance_expiry_date)])]
    cert = "The driver acknowledges custody of the vehicle above, agrees to use it for company business, observe traffic laws, and report incidents, damage and maintenance needs promptly."
    return base(t, v.company, reference=v.reference, status_label="Issued" if d else "Draft", watermark=None if d else "NO DRIVER ASSIGNED", info=[], sections=secs, certification=cert, signatures=[Signature("Issued by", p.employee.name, p.employee.designation, "Executive Admin"), Signature("Received by", d.name if d else None, d.designation if d else None)]), "approved" if d else "draft"


async def b_renewal_checklist(t, s, p, v: Vehicle):
    items = [("Current OR/CR copy on file", True), ("Insurance policy (CTPL / comprehensive) valid", bool(v.insurance_expiry_date and v.insurance_expiry_date > date.today())), ("Emission test result", False), ("LTO registration fees prepared (request to Finance)", False), ("Stencil of chassis and engine numbers, if required", False), ("Updated OR/CR filed in Executive Admin", False)]
    secs = [("info", "Vehicle", veh_pairs(v)), ("info", "Dates", [("Registration renewal", v.registration_renewal_date), ("Insurance expiry", v.insurance_expiry_date), ("Next PMS", v.next_pms_date)]), ("checklist", "Renewal checklist", items)]
    return base(t, v.company, reference=v.reference, status_label="Checklist", info=[], sections=secs, signatures=[Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin"), Signature("Checked by")]), "draft"


def b_service(kind: str):
    async def build(t, s, p, x: VehicleService):
        v = x.vehicle
        info = [("Service", x.reference), ("Type", "PMS" if x.kind == "pms" else x.kind.title()), ("Date", x.service_date), ("Provider", x.provider), ("Odometer", f"{x.odometer_km:,} km" if x.odometer_km else None), ("Cost", x.cost_php and fmt(x.cost_php, "money")), ("Next service", x.next_service_date), ("Status", x.status.title())]
        secs = [("info", "Vehicle", veh_pairs(v)[:4]), ("text", "Work requested / done", x.description)]
        if x.parts:
            secs.append(("text", "Parts", x.parts))
        done = x.status == "done"
        role2 = {"request": "Approved by", "job_order": "Accepted by (provider)", "completion": "Accepted by", "receiving": "Received by"}[kind]
        status = "approved" if (kind in ("request", "job_order") or done) else "draft"
        return base(t, v.company, reference=x.reference, status_label=x.status.title(), watermark=None if status == "approved" else "NOT COMPLETED", info=info, sections=secs, signatures=[Signature("Prepared by", x.created_by.name, x.created_by.designation, "Executive Admin"), Signature(role2)]), status

    return build


async def b_fleet_card_request(t, s, p, c: FleetCard):
    info = [("Card", f"{c.provider} •••• {c.card_last4}".replace("•", "*")), ("Vehicle", c.vehicle.label if c.vehicle else "—"), ("Card holder", c.assigned_user.name if c.assigned_user else "—"), ("Fuel type", c.fuel_type), ("Monthly limit", fmt(c.configured_amount_php, "money")), ("Billing cycle", c.billing_cycle.title()), ("Status", c.monitoring_status.title())]
    return base(t, c.company, reference=c.reference, status_label=c.monitoring_status.title(), info=info, sections=[("text", "Request", "Issue / maintain the fleet card above for the vehicle and card holder named. Statements are handed to Finance monthly through Executive Admin.")], signatures=[Signature("Requested by", p.employee.name, p.employee.designation, "Executive Admin"), Signature("Approved by")]), "draft"


async def b_rfid_payment(t, s, p, f: FinanceRequest):
    acct = f.rfid_account
    info = [("Reference", f.reference), ("Account", f"{acct.provider} {acct.account_reference}" if acct else "—"), ("Vehicle", f.vehicle.label if f.vehicle else "—"), ("Amount", fmt(f.amount_php, "money")), ("Status", {"draft": "Draft", "sent": "With Finance", "paid": "Paid", "rejected": "Rejected", "cancelled": "Cancelled"}[f.status]), ("Finance reference", f.finance_reference)]
    status = "approved" if f.status == "paid" else "for_approval" if f.status == "sent" else "draft"
    sigs = [Signature("Requested by", f.created_by.name, f.created_by.designation, "Executive Admin", f"Sent to Finance {fmt(aware(f.sent_at))}" if f.sent_at else None), Signature("Paid by (Finance)", None, None, "Finance", f"Payment {f.finance_reference} recorded {fmt(aware(f.paid_at))}" if f.paid_at else None)]
    return base(t, f.company, reference=f.reference, status_label=info[4][1], watermark=None if status == "approved" else "NOT YET PAID", info=info, sections=[("text", "Request", f"Reload the RFID account above with {fmt(f.amount_php, 'money')}." + (f"\n{f.notes}" if f.notes else ""))], signatures=sigs), status


# ------------------------------------------------------------------ builders: compliance


def reg_pairs(r: GovRegistration) -> list[tuple]:
    return [("Document", r.document_name), ("Type", r.registration_type), ("Registration no.", r.registration_number), ("Registered", r.registration_date), ("Valid for", f"{r.validity_years} year(s)" if r.validity_years else None), ("Expires", r.expiry_date), ("Filing due", r.due_date), ("Responsible", r.responsible.name if r.responsible else None)]


async def b_reg_renewal(t, s, p, r: GovRegistration):
    secs = [("info", "Registration", reg_pairs(r)), ("text", "Request", f"Request approval to file the renewal of {r.document_name} before {fmt(r.due_date or r.expiry_date)}. Fees will be requested from Finance once the assessment is known.")]
    return base(t, r.company, reference=r.reference, status_label=r.status.replace("_", " ").title(), info=[], sections=secs, signatures=[Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin"), Signature("Recommended by"), Signature("Approved by")]), "draft"


async def b_gov_checklist(t, s, p, r: GovRegistration):
    base_items = {"Business Permit": ["Barangay clearance", "Previous Mayor's permit", "Audited financial statements / gross sales declaration", "Lease contract or proof of address", "Fire safety inspection certificate", "Sanitary permit"], "SEC": ["Latest GIS", "Audited financial statements", "Board resolution, if amendments"], "GIS": ["Updated list of directors and officers", "Stockholders' list", "Secretary's certificate"], "Bureau of Customs": ["Importer/broker accreditation documents", "BIR registration", "Latest GIS", "Bank certificate"], "Pest Control": ["Service provider license", "Treatment schedule", "Certificate of treatment"], "Fire Extinguishers": ["Refill / maintenance certificate", "Inventory of extinguishers", "Fire safety inspection certificate"]}
    items = [(x, False) for x in base_items.get(r.registration_type, ["Previous certificate", "Application form", "Supporting documents"])]
    return base(t, r.company, reference=r.reference, status_label="Checklist", info=[], sections=[("info", "Registration", reg_pairs(r)), ("checklist", "Documents to prepare", items)], signatures=[Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin"), Signature("Checked by")]), "draft"


async def b_boc_checklist(t, s, p, c: BocCase):
    items = [("Commercial invoice", False), ("Packing list", False), ("Bill of lading / airway bill" + (f" ({c.bill_of_lading})" if c.bill_of_lading else ""), bool(c.bill_of_lading)), ("Import/export entry" + (f" ({c.entry_number})" if c.entry_number else ""), bool(c.entry_number)), ("Permits or clearances for regulated goods (FDA, etc.)", False), ("Broker authorization", bool(c.broker)), ("Proof of duties and taxes paid", c.status in ("duties_paid", "released", "delivered", "closed"))]
    info = [("Case", c.reference), ("Direction", c.direction.title()), ("Goods", c.description), ("ETA", c.eta), ("Officer", c.officer.name if c.officer else None), ("Milestone", c.status.replace("_", " ").title())]
    return base(t, None, reference=c.reference, status_label=c.status.replace("_", " ").title(), info=info, sections=[("checklist", "Customs documents", items)], signatures=[Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin"), Signature("Checked by (broker)")]), "draft"


# ------------------------------------------------------------------ builders: travel


def flight_pairs(f: FlightBooking) -> list[tuple]:
    gender = {"male": "Male", "female": "Female"}.get(f.passenger.gender or "")
    age = f.passenger.age
    return [("Traveler", f"{f.passenger.name} ({f.passenger.employee_no})"), ("Sex / Age", " · ".join(x for x in (gender, f"{age} years" if age is not None else None) if x) or None), ("Department", f.passenger.department.name if f.passenger.department else None), ("Route", f"{f.origin} → {f.destination}"), ("Travel", f"{f.travel_type.title()}" + (f" · {f.destination_country}" if f.travel_type == "international" else "")), ("Departure", f.departure_date), ("Return", f.return_date), ("Airline", f.airline), ("Booking ref. (PNR)", f.booking_reference)]


async def _checklist(s, f: FlightBooking):
    from .travel import requirements_for

    reqs = await requirements_for(s, f.travel_type, f.destination_country)
    return [(r.name, bool((f.checklist or {}).get(str(r.id), {}).get("done"))) for r in reqs]


def b_flight(kind: str):
    async def build(t, s, p, f: FlightBooking):
        booked = f.status in ("booked", "ticketed", "completed")
        secs = [("info", "Trip", flight_pairs(f))]
        if f.purpose:
            secs.append(("text", "Purpose of travel", f.purpose))
        if kind in ("checklist", "authorization"):
            secs.append(("checklist", "Travel requirements", await _checklist(s, f)))
        status = "approved" if (kind in ("summary",) and booked) or kind == "checklist" else "draft"
        if kind == "authorization":
            status = "approved" if f.status in ("booked", "ticketed", "completed") else "for_approval"
        sigs = {"authorization": [Signature("Requested by", f.passenger.name, f.passenger.designation), Signature("Recommended by"), Signature("Approved by")], "memo": [Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin"), Signature("Approved by")]}.get(kind, [Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin")])
        wm = None if status == "approved" or kind in ("memo", "checklist") else ("NOT YET BOOKED" if kind == "summary" else "FOR APPROVAL")
        if kind == "memo":
            secs.insert(0, ("text", None, f"This memo requests approval for {f.passenger.name}'s {f.travel_type} travel to {f.destination} from {fmt(f.departure_date)} to {fmt(f.return_date)}."))
        return base(t, f.company, reference=f.reference, status_label=f.status.title(), watermark=wm, info=[], sections=secs, signatures=sigs), status

    return build


async def b_hotel(t, s, p, h: HotelReservation):
    info = [("Guest", h.guest.name), ("Hotel", h.hotel), ("City", h.destination), ("Check-in", h.check_in), ("Check-out", h.check_out), ("Nights", (h.check_out - h.check_in).days), ("Confirmation", h.booking_reference), ("Cost reference", h.cost_reference)]
    booked = h.status in ("booked", "completed")
    return base(t, h.company, reference=h.reference, status_label=h.status.title(), watermark=None if booked else "NOT YET BOOKED", info=info, sections=[("text", "Notes", h.notes or "—")], signatures=[Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin")]), "approved" if booked else "draft"


# ------------------------------------------------------------------ builders: contracts & banking


def con_pairs(c: Contract) -> list[tuple]:
    return [("Contract", f"{c.reference} · {c.title}"), ("Type", c.contract_type.replace("_", " ").title()), ("Property / site", c.property_name), ("Location", c.location), ("Lessor", c.lessor.name if c.lessor else None), ("Term", f"{fmt(c.start_date)} to {fmt(c.end_date)}"), ("Monthly rent", c.monthly_rent_php and fmt(c.monthly_rent_php, "money")), ("Deposit", c.deposit_php and fmt(c.deposit_php, "money"))]


def b_contract(kind: str):
    async def build(t, s, p, c: Contract):
        body = {
            "renewal_request": f"Request approval to renew the {c.contract_type.replace('_', ' ')} above, which ends on {fmt(c.end_date)}. Proposed term and rate to be confirmed with the lessor before signing.",
            "renewal_memo": f"This memo records the renewal decision for {c.title}. The current term ends on {fmt(c.end_date)}." + (" The contract has been renewed." if c.status == "renewed" else ""),
        }[kind]
        sigs = [Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin"), Signature("Recommended by"), Signature("Approved by")]
        return base(t, c.company, reference=c.reference, status_label=c.status.replace("_", " ").title(), info=[], sections=[("info", "Contract", con_pairs(c)), ("text", None, body)], signatures=sigs), "draft"

    return build


def b_bank(kind: str):
    async def build(t, s, p, b: BankingCase):
        info = [("Case", b.reference), ("Bank", b.bank), ("Type", b.case_type.replace("_", " ").title()), ("Subject", b.subject), ("Account / card", f"**** {b.account_last4 or (b.card.card_last4 if b.card else '')}" if (b.account_last4 or b.card) else None), ("Responsible", b.responsible.name if b.responsible else None), ("Application date", b.application_date), ("Renewal date", b.renewal_date)]
        secs = [("checklist", "Requirements", [(r["name"], r.get("done")) for r in b.requirements])] if b.requirements else []
        secs.append(("text", "Notes", (b.notes or "—")))
        sigs = [Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin"), Signature("Approved by")]
        status = "approved" if b.status in ("approved", "completed") else "for_approval" if b.status == "submitted" else "draft"
        return base(t, b.company, reference=b.reference, status_label=b.status.title(), watermark=None if status == "approved" or kind == "checklist" else "FOR APPROVAL", info=info, sections=secs, certification="No card numbers, CVV, PINs or online-banking credentials are recorded on this form.", signatures=sigs), status

    return build


# ------------------------------------------------------------------ builders: administration & inventory


async def b_task_completion(t, s, p, x: Task):
    done = x.status == "done"
    info = [("Task", x.reference), ("Title", x.title), ("Assigned to", x.assignee.name if x.assignee else None), ("Due", x.due_date), ("Priority", x.priority.title()), ("Completed", aware(x.completed_at) if x.completed_at else None)]
    secs = [("text", "Details", x.description or "—"), ("text", "Completion report", x.completion_note or "Not completed yet.")]
    sigs = [Signature("Completed by", x.assignee.name if x.assignee else None, x.assignee.designation if x.assignee else None, None, f"Marked done in Executive Admin {fmt(aware(x.completed_at))}" if done else None), Signature("Reviewed by", x.created_by.name, x.created_by.designation)]
    return base(t, x.company, reference=x.reference, status_label=x.status.replace("_", " ").title(), watermark=None if done else "NOT COMPLETED", info=info, sections=secs, signatures=sigs), "approved" if done else "draft"


async def b_stock_card(t, s, p, i: InventoryItem):
    moves = (await s.execute(select(StockMovement).where(StockMovement.item_id == i.id, StockMovement.kind.notin_(["reserve", "release"])).order_by(StockMovement.id))).scalars().all()
    rows = [{"date": aware(m.at).date(), "ref": m.reference, "kind": m.kind.replace("_", " "), "in": m.quantity if m.quantity > 0 else None, "out": -m.quantity if m.quantity < 0 else None, "balance": m.balance_after, "by": m.actor.name, "note": m.reason or (m.issued_to.name if m.issued_to else "")} for m in moves]
    cols = [Column("date", "Date", "date", 1), Column("ref", "Reference", "text", 1.5), Column("kind", "Movement", "text", 1.2), Column("in", "In", "number", 0.6), Column("out", "Out", "number", 0.6), Column("balance", "Balance", "number", 0.8), Column("by", "By", "text", 1.3), Column("note", "Note", "text", 2.2)]
    info = [("Item code", i.item_code), ("Item", i.name), ("Location", i.location), ("Unit", i.unit), ("On hand", i.on_hand), ("Reserved", i.reserved), ("Reorder level", i.reorder_level), ("Unit cost", fmt(i.unit_cost_php, "money"))]
    return base(t, i.company, reference=i.item_code, status_label="Current", info=info, sections=[("table", "Movements", cols, rows, None)], signatures=[Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin")]), "approved"


async def b_count_sheet(t, s, p, c: InventoryCount):
    rows = [{"code": l["item_code"], "name": l["name"], "location": l["location"], "unit": l["unit"], "expected": l["expected"] if c.status != "open" else None, "counted": l.get("counted"), "variance": (l["counted"] - l["expected"]) if l.get("counted") is not None and c.status != "open" else None} for l in c.lines]
    cols = [Column("code", "Item code", "text", 1.2), Column("name", "Item", "text", 2.8), Column("location", "Location", "text", 1.4), Column("unit", "Unit", "text", 0.7), Column("expected", "System qty", "number", 0.9), Column("counted", "Counted", "number", 0.9), Column("variance", "Variance", "number", 0.9)]
    info = [("Count", c.reference), ("Location", c.location or "All locations"), ("Started", aware(c.started_at)), ("Started by", c.started_by.name), ("Status", c.status.title()), ("Posted by", c.posted_by.name if c.posted_by else None)]
    sigs = [Signature("Counted by", c.started_by.name, c.started_by.designation), Signature("Verified by"), Signature("Posted by", c.posted_by.name if c.posted_by else None, None, None, f"Posted in Executive Admin {fmt(aware(c.posted_at))}" if c.posted_at else None)]
    return base(t, await company_of(s, c.company_id), reference=c.reference, status_label=c.status.title(), watermark=None if c.status == "posted" else ("COUNT IN PROGRESS" if c.status == "open" else None), info=info, sections=[("table", "Count lines", cols, rows, None)], signatures=sigs), "approved" if c.status == "posted" else "draft"


def b_movement(kind: str):
    async def build(t, s, p, m: StockMovement):
        i = await s.get(InventoryItem, m.item_id)
        info = [("Movement", m.reference), ("Date", aware(m.at)), ("Item", f"{i.item_code} · {i.name}"), ("Location", i.location), ("Quantity", f"{abs(m.quantity)} {i.unit}"), ("Type", m.kind.replace("_", " ").title()), ("Issued to" if kind == "issuance" else "Reason", (m.issued_to.name if m.issued_to else None) if kind == "issuance" else m.reason), ("Balance after", m.balance_after)]
        sigs = [Signature("Issued by" if kind == "issuance" else "Prepared by", m.actor.name, m.actor.designation, "Executive Admin", f"Recorded in Executive Admin {fmt(aware(m.at))}"), Signature("Received by" if kind == "issuance" else "Approved by", m.issued_to.name if kind == "issuance" and m.issued_to else None)]
        return base(t, await company_of(s, m.company_id), reference=m.reference, status_label="Recorded", info=info, sections=[], signatures=sigs), "approved"

    return build


# ------------------------------------------------------------------ builders: period reports


def b_period(kind: str):
    async def build(t, s, p, period: date):
        from .reports import Params, executive, run_report

        start = period.replace(day=1)
        end = (start.replace(day=28) + __import__("datetime").timedelta(days=4)).replace(day=1) - __import__("datetime").timedelta(days=1)
        prm = Params(start, end, None, 60)
        co = await company_of(s, p.employee.company_id)
        secs = []
        if kind in ("monthly", "executive"):
            m = await executive(principal=p, session=s)
            secs.append(("info", "Key indicators (live)", [("Open requests", m["total_open_requests"]), ("In approval", m["pending_approvals"]), ("Overdue requests", m["overdue_requests"]), ("High / urgent open", m["priority_concerns"]), ("Upcoming renewals (30–60 days)", m["upcoming_renewals"]), ("Active assets", m["active_assets"]), ("Assets under repair", m["assets_under_repair"]), ("Fleet maintenance due", m["fleet_maintenance_due"]), ("Expiring government documents", m["expiring_government_documents"]), ("Contract renewals", m["contract_renewals"]), ("Travel bookings in progress", m["travel_requests"]), ("Task completion this month", f"{m['task_completion']['done']} of {m['task_completion']['due']}")]))
            for key in (["requests_by_department", "sla_performance"] if kind == "monthly" else ["requests_by_company", "sla_performance", "expiring_documents"]):
                rep, rows, totals = await run_report(s, p, key, prm)
                secs.append(("table", rep.title, rep.columns, rows, totals))
        if kind == "compliance":
            for key in ("expiring_documents", "government_registrations", "boc_cases"):
                rep, rows, totals = await run_report(s, p, key, Params(start, end, None, 90))
                secs.append(("table", rep.title, rep.columns[:7], rows, totals))
        if kind == "contracts":
            for key in ("expiring_contracts", "monthly_rental_summary"):
                rep, rows, totals = await run_report(s, p, key, Params(start, end, None, 120))
                secs.append(("table", rep.title, rep.columns, rows, totals))
        info = [("Period", f"{start:%B %Y}"), ("Prepared by", p.employee.name), ("Generated", now())]
        return DocSpec(title=t.title, company_name=co.name if co else "Bishnoi One", issue_date=date.today(), reference=f"{start:%Y-%m}", status_label="Report", info=info, sections=secs, signatures=[Signature("Prepared by", p.employee.name, p.employee.designation, "Executive Admin"), Signature("Reviewed by")], landscape=True), "approved"

    return build


# ------------------------------------------------------------------ registry


def need(cond, why):
    return lambda r: None if cond(r) else why


ITEM_REQ = ("supplies", "asset", "local_purchase")
TEMPLATES: list[Template] = [
    Template("supply_request_form", "Supply Request Form", "Requests and Purchases", "REQ", "request", b_request_form("Supply"), need(lambda r: r.kind == "supplies", "Only for supply requests"), employee_ok=True),
    Template("asset_request_form", "Asset Request Form", "Requests and Purchases", "REQ", "request", b_request_form("Asset"), need(lambda r: r.kind == "asset", "Only for asset requests"), employee_ok=True),
    Template("purchase_request", "Purchase Request", "Requests and Purchases", "PR", "request", b_request_form("Purchase"), need(lambda r: r.kind in ITEM_REQ, "Only for item requests")),
    Template("purchase_order", "Purchase Order", "Requests and Purchases", "PO", "request", b_purchase_order, need(lambda r: r.kind in ITEM_REQ and r.status in (S.approved, S.in_progress, S.awaiting_finance, S.fulfilled, S.closed), "Only after an item request is approved")),
    Template("local_purchase_request", "Local Purchase Request", "Requests and Purchases", "PR", "request", b_request_form("Local purchase"), need(lambda r: r.kind == "local_purchase", "Only for local purchases")),
    Template("request_approval_memo", "Request Approval Memo", "Requests and Purchases", "MEMO", "request", b_approval_memo, need(lambda r: r.status not in (S.draft,) and bool(r.steps), "Only for submitted requests with an approval route")),
    Template("employee_concern_resolution_form", "Employee Concern Resolution Form", "Administration", "ADM", "request", b_concern_resolution, need(lambda r: r.kind in ("concern", "repair", "other"), "Only for concerns"), employee_ok=True),
    Template("asset_issuance_form", "Asset Issuance Form", "Assets", "ASF", "asset", b_asset_movement("issuance"), need(lambda a: a.holder_id, "Only for issued assets")),
    Template("asset_transfer_form", "Asset Transfer Form", "Assets", "ASF", "asset", b_asset_movement("transfer")),
    Template("asset_return_form", "Asset Return Form", "Assets", "ASF", "asset", b_asset_movement("return")),
    Template("asset_turnover_acknowledgment", "Asset Turnover Acknowledgment", "Assets", "ASF", "asset", b_asset_movement("turnover"), need(lambda a: a.holder_id, "Only for issued assets")),
    Template("asset_receiving_form", "Asset Receiving Form", "Assets", "ASF", "receipt", b_receiving),
    Template("equipment_repair_request", "Equipment Repair Request", "Assets", "MNT", "asset_repair", b_repair("request")),
    Template("maintenance_job_order", "Maintenance Job Order", "Maintenance", "MNT", "asset_repair", b_repair("job_order")),
    Template("repair_authorization", "Repair Authorization", "Maintenance", "MNT", "asset_repair", b_repair("authorization")),
    Template("maintenance_completion_report", "Maintenance Completion Report", "Maintenance", "MNT", "asset_repair", b_repair("completion")),
    Template("vehicle_maintenance_request", "Vehicle Maintenance Request", "Fleet", "FLT", "vehicle_service", b_service("request")),
    Template("vehicle_job_order", "Maintenance Job Order (Vehicle)", "Maintenance", "MNT", "vehicle_service", b_service("job_order")),
    Template("vehicle_completion_report", "Maintenance Completion Report (Vehicle)", "Maintenance", "MNT", "vehicle_service", b_service("completion")),
    Template("service_receiving_form", "Service Receiving Form", "Maintenance", "MNT", "vehicle_service", b_service("receiving"), need(lambda x: x.status == "done", "Only after the service is done")),
    Template("vehicle_assignment_form", "Vehicle Assignment Form", "Fleet", "FLT", "vehicle", b_vehicle_assignment),
    Template("vehicle_renewal_checklist", "Vehicle Renewal Checklist", "Fleet", "FLT", "vehicle", b_renewal_checklist),
    Template("fleet_card_request", "Fleet Card Request", "Fleet", "FLT", "fleet_card", b_fleet_card_request),
    Template("rfid_payment_request", "RFID Payment Request", "Fleet", "FLT", "finance", b_rfid_payment, need(lambda f: f.kind == "rfid_reload", "Only for RFID reloads")),
    Template("registration_renewal_request", "Registration Renewal Request", "Corporate Compliance", "CMP", "registration", b_reg_renewal),
    Template("government_document_checklist", "Government Document Checklist", "Corporate Compliance", "CMP", "registration", b_gov_checklist),
    Template("boc_document_checklist", "BOC Document Checklist", "Corporate Compliance", "CMP", "boc", b_boc_checklist),
    Template("compliance_monitoring_report", "Compliance Monitoring Report", "Corporate Compliance", "CMP", "period", b_period("compliance")),
    Template("travel_authorization", "Travel Authorization", "Travel", "TRV", "flight", b_flight("authorization")),
    Template("flight_booking_summary", "Flight Booking Summary", "Travel", "TRV", "flight", b_flight("summary")),
    Template("visa_requirements_checklist", "Visa Requirements Checklist", "Travel", "TRV", "flight", b_flight("checklist")),
    Template("travel_approval_memo", "Travel Approval Memo", "Travel", "TRV", "flight", b_flight("memo")),
    Template("hotel_booking_summary", "Hotel Booking Summary", "Travel", "TRV", "hotel", b_hotel),
    Template("lease_renewal_request", "Lease Renewal Request", "Contracts", "CON", "contract", b_contract("renewal_request"), need(lambda c: c.contract_type in ("office_lease", "staff_house"), "Only for leases")),
    Template("contract_renewal_memo", "Contract Renewal Memo", "Contracts", "CON", "contract", b_contract("renewal_memo")),
    Template("contract_monitoring_report", "Contract Monitoring Report", "Contracts", "CON", "period", b_period("contracts")),
    Template("corporate_card_request", "Corporate Card Request", "Banking", "BNK", "banking", b_bank("request"), need(lambda b: b.case_type == "card_request", "Only for card requests")),
    Template("bank_account_application_checklist", "Bank Account Application Checklist", "Banking", "BNK", "banking", b_bank("checklist"), need(lambda b: b.case_type == "account_application", "Only for account applications")),
    Template("credit_card_renewal_request", "Credit Card Renewal Request", "Banking", "BNK", "banking", b_bank("request"), need(lambda b: b.case_type == "card_renewal", "Only for card renewals")),
    Template("banking_documentation_request", "Banking Documentation Request", "Banking", "BNK", "banking", b_bank("request"), need(lambda b: b.case_type in ("documentation", "bank_renewal"), "Only for documentation cases")),
    Template("task_completion_report", "Task Completion Report", "Administration", "ADM", "task", b_task_completion),
    Template("monthly_administrative_report", "Monthly Administrative Report", "Administration", "ADM", "period", b_period("monthly")),
    Template("executive_summary_report", "Executive Summary Report", "Administration", "ADM", "period", b_period("executive")),
    Template("stock_card", "Stock Card", "Consumables & Stock", "INV", "inventory_item", b_stock_card),
    Template("inventory_count_sheet", "Inventory Count Sheet", "Consumables & Stock", "INV", "inventory_count", b_count_sheet),
    Template("inventory_issuance_slip", "Inventory Issuance Slip", "Consumables & Stock", "INV", "stock_movement", b_movement("issuance"), need(lambda m: m.kind == "issue", "Only for issues")),
    Template("stock_adjustment_form", "Stock Adjustment / Write-off Form", "Consumables & Stock", "INV", "stock_movement", b_movement("adjustment"), need(lambda m: m.kind in ("adjustment", "write_off"), "Only for adjustments and write-offs")),
]
BY_KEY = {t.key: t for t in TEMPLATES}

MODELS = {
    "request": Request, "asset": Asset, "asset_repair": AssetRepair, "receipt": Receipt, "vehicle": Vehicle, "vehicle_service": VehicleService, "fleet_card": FleetCard,
    "finance": FinanceRequest, "registration": GovRegistration, "boc": BocCase, "flight": FlightBooking, "hotel": HotelReservation, "contract": Contract,
    "banking": BankingCase, "task": Task, "inventory_item": InventoryItem, "inventory_count": InventoryCount, "stock_movement": StockMovement,
}


def company_id_of(rec) -> int | None:
    if hasattr(rec, "company_id"):
        return rec.company_id
    if isinstance(rec, AssetRepair):
        return rec.asset.company_id
    if isinstance(rec, VehicleService):
        return rec.vehicle.company_id
    return None


async def load_related(session, principal: Principal, related: str, related_id: int, t: Template | None = None):
    """Load the record behind a document and check the caller may see it."""
    if related == "period":
        try:
            y, m = divmod(related_id, 100)
            return date(y, m, 1)
        except ValueError:
            raise bad_request("Period must be YYYYMM")
    model = MODELS.get(related)
    if model is None:
        raise bad_request("Unknown record type")
    rec = await session.get(model, related_id)
    if rec is None:
        raise not_found()
    if related == "request":
        if not await can_view(session, principal, rec):
            raise not_found()
        if not principal.is_staff:
            # Employees may only see forms for their own requests, and only the employee-facing ones.
            if rec.requester_id != principal.id or (t is not None and not t.employee_ok):
                raise forbidden("This document is prepared by Executive Admin")
        return rec
    if not principal.is_staff or company_id_of(rec) not in principal.company_ids:
        raise not_found()
    if related == "banking" and not (principal.is_admin or principal.delegated("banking")):
        raise not_found()
    return rec


async def next_control(session, doc_type: str) -> str:
    year = now().year
    key = f"D-{doc_type}"[:16]
    seq = (await session.execute(select(DocumentSequence).where(DocumentSequence.doc_type == key, DocumentSequence.year == year).with_for_update())).scalar_one_or_none()
    if seq is None:
        seq = DocumentSequence(doc_type=key, year=year, last_value=0)
        session.add(seq)
        await session.flush()
    seq.last_value += 1
    return f"EA-{doc_type}-{year}-{seq.last_value:04d}"


def doc_out(d: GeneratedDocument) -> dict:
    t = BY_KEY.get(d.template_key)
    return {
        "id": d.id, "control_number": d.control_number, "version": d.version, "template_key": d.template_key, "title": d.title, "group": t.group if t else None,
        "related_type": d.related_type, "related_id": d.related_id, "related_ref": d.related_ref, "status": d.status, "signature_status": d.signature_status,
        "paper": d.paper, "size": d.size, "sha256": d.sha256, "generated_by": person(d.generated_by), "generated_at": iso(d.generated_at), "issued_at": iso(d.issued_at),
        "void_reason": d.void_reason, "url": f"/api/v1/documents/{d.id}/file",
    }


async def devent(session, d: GeneratedDocument, principal: Principal, type_: str, note: str | None = None):
    session.add(DocumentEvent(document_id=d.id, type=type_, note=note, actor_id=principal.id))
    await audit(session, actor_id=principal.id, action=f"document.{type_}", entity_type="document", entity_id=d.id, entity_ref=f"{d.control_number} v{d.version}", company_id=d.company_id, data={"template": d.template_key, "note": note})


# ------------------------------------------------------------------ endpoints


@router.get("/templates")
async def templates(principal: CurrentPrincipal, session: Session, related_type: str | None = None, related_id: int | None = None) -> list[dict]:
    out = []
    rec = None
    if related_type and related_id:
        rec = await load_related(session, principal, related_type, related_id)
    for t in TEMPLATES:
        if related_type and t.related != related_type:
            continue
        if not principal.is_staff and not t.employee_ok:
            continue
        reason = t.applies(rec) if rec is not None and t.related != "period" else None
        existing = None
        if rec is not None:
            existing = (await session.execute(select(GeneratedDocument).where(GeneratedDocument.template_key == t.key, GeneratedDocument.related_type == t.related, GeneratedDocument.related_id == related_id, GeneratedDocument.status != "superseded").order_by(GeneratedDocument.id.desc()))).scalars().first()
        out.append({"key": t.key, "title": t.title, "group": t.group, "related": t.related, "available": reason is None, "reason": reason, "latest": doc_out(existing) if existing else None})
    return out


class GenerateIn(BaseModel):
    template_key: str
    related_id: int
    paper: str = Field("A4", pattern="^(A4|Letter)$")


@router.post("", status_code=201)
async def generate(body: GenerateIn, principal: CurrentPrincipal, session: Session) -> dict:
    t = BY_KEY.get(body.template_key)
    if t is None:
        raise not_found("Unknown template")
    rec = await load_related(session, principal, t.related, body.related_id, t)
    if t.related != "period":
        why = t.applies(rec)
        if why:
            raise conflict(why)
    elif not principal.is_staff:
        raise forbidden()
    spec, status = await t.build(t, session, principal, rec)
    if status == "approved" and t.related not in APPROVAL_BACKED:
        # Complete, but nobody approved it: never label it "Approved".
        status = "final"
    spec.paper = body.paper
    prev = (await session.execute(select(GeneratedDocument).where(GeneratedDocument.template_key == t.key, GeneratedDocument.related_type == t.related, GeneratedDocument.related_id == body.related_id).order_by(GeneratedDocument.version.desc()))).scalars().first()
    control = prev.control_number if prev else await next_control(session, t.doc_type)
    version = (prev.version + 1) if prev else 1
    spec.control_number = control
    spec.version = version
    pdf = render(spec)
    key = secrets.token_hex(16)
    get_settings().upload_dir.mkdir(parents=True, exist_ok=True)
    (get_settings().upload_dir / key).write_bytes(pdf)
    d = GeneratedDocument(
        control_number=control, version=version, template_key=t.key, title=t.title, related_type=t.related, related_id=body.related_id,
        related_ref=getattr(rec, "reference", None) or getattr(rec, "item_code", None) or (rec.strftime("%Y-%m") if isinstance(rec, date) else None),
        company_id=(principal.employee.company_id if isinstance(rec, date) else company_id_of(rec)), status=status, paper=body.paper, storage_key=key,
        sha256=hashlib.sha256(pdf).hexdigest(), size=len(pdf), generated_by_id=principal.id,
    )
    session.add(d)
    await session.flush()
    if prev and prev.status not in ("voided", "superseded"):
        prev.status = "superseded"
        await devent(session, prev, principal, "superseded", f"Replaced by version {version}")
    await devent(session, d, principal, "generated", f"{t.title} v{version}")
    await session.commit()
    return doc_out(d)


@router.get("")
async def register(principal: Staff, session: Session, q: str | None = None, status: str | None = None, related_type: str | None = None, related_id: int | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> dict:
    stmt = select(GeneratedDocument).where((GeneratedDocument.company_id.in_(principal.company_ids)) | GeneratedDocument.company_id.is_(None))
    if status:
        stmt = stmt.where(GeneratedDocument.status == status)
    else:
        stmt = stmt.where(GeneratedDocument.status != "superseded")
    if related_type:
        stmt = stmt.where(GeneratedDocument.related_type == related_type)
    if related_id:
        stmt = stmt.where(GeneratedDocument.related_id == related_id)
    rows = list((await session.execute(stmt.order_by(GeneratedDocument.id.desc()))).scalars())
    if not (principal.is_admin or principal.delegated("banking")):
        rows = [d for d in rows if d.related_type != "banking"]
    if q:
        ql = q.lower()
        rows = [d for d in rows if ql in f"{d.control_number} {d.title} {d.related_ref}".lower()]
    return {"items": [doc_out(d) for d in rows[(page - 1) * page_size : page * page_size]], "total": len(rows), "page": page, "page_size": page_size}


async def own_doc(session, principal: Principal, doc_id: int) -> GeneratedDocument:
    d = await session.get(GeneratedDocument, doc_id)
    if d is None:
        raise not_found()
    t = BY_KEY.get(d.template_key)
    if d.related_type == "period":
        if not principal.is_staff or (d.company_id not in principal.company_ids):
            raise not_found()
        return d
    await load_related(session, principal, d.related_type, d.related_id, t)
    return d


@router.get("/{doc_id}")
async def get_doc(doc_id: int, principal: CurrentPrincipal, session: Session) -> dict:
    d = await own_doc(session, principal, doc_id)
    versions = (await session.execute(select(GeneratedDocument).where(GeneratedDocument.control_number == d.control_number).order_by(GeneratedDocument.version.desc()))).scalars().all()
    events = (await session.execute(select(DocumentEvent).where(DocumentEvent.document_id.in_([v.id for v in versions])).order_by(DocumentEvent.at.desc()))).scalars().all()
    signed = await session.get(Attachment, d.signed_copy_id) if d.signed_copy_id else None
    return {
        **doc_out(d), "versions": [doc_out(v) for v in versions], "signed_copy": attachment_out(signed) if signed else None,
        "events": [{"id": e.id, "type": e.type, "note": e.note, "actor": person(e.actor), "at": iso(e.at), "document_id": e.document_id} for e in events],
    }


@router.get("/{doc_id}/file")
async def file(doc_id: int, principal: CurrentPrincipal, session: Session, inline: bool = True):
    d = await own_doc(session, principal, doc_id)
    data = (get_settings().upload_dir / d.storage_key).read_bytes()
    if hashlib.sha256(data).hexdigest() != d.sha256:
        raise conflict("The stored document failed its integrity check")
    await devent(session, d, principal, "downloaded")
    await session.commit()
    name = f"{d.control_number}-v{d.version}.pdf"
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{name}"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


class VoidIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


@router.post("/{doc_id}/issue")
async def issue(doc_id: int, principal: Staff, session: Session) -> dict:
    d = await own_doc(session, principal, doc_id)
    if d.status not in ("approved", "final"):
        raise conflict("Only approved or final documents can be issued. Documents for records still in approval or incomplete stay drafts.")
    d.status = "issued"
    d.issued_at = now()
    await devent(session, d, principal, "issued")
    await session.commit()
    return doc_out(d)


@router.post("/{doc_id}/void")
async def void(doc_id: int, body: VoidIn, principal: Staff, session: Session) -> dict:
    if not principal.is_admin:
        raise forbidden("Only Admin can void a document")
    d = await own_doc(session, principal, doc_id)
    if d.status in ("voided", "superseded"):
        raise conflict(f"This document is already {d.status}")
    d.status = "voided"
    d.void_reason = body.reason
    await devent(session, d, principal, "voided", body.reason)
    await session.commit()
    return doc_out(d)


@router.post("/{doc_id}/signed")
async def signed(doc_id: int, principal: Staff, session: Session, file: UploadFile = File(...), note: str | None = Form(None)) -> dict:
    """Attach the scanned, wet-signed copy. Recorded as a signed copy, not as a verified e-signature."""
    from .attachments import validate as validate_file

    d = await own_doc(session, principal, doc_id)
    if d.status != "issued":
        raise conflict("Issue the document before recording its signed copy")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if not data or len(data) > limit:
        raise bad_request({"message": f"Upload a file up to {get_settings().max_upload_mb} MB"})
    name, ctype = validate_file(file.filename or "signed.pdf", data[:512])
    key = secrets.token_hex(16)
    (get_settings().upload_dir / key).write_bytes(data)
    att = Attachment(owner_type="document", owner_id=d.id, filename=name, content_type=ctype, size=len(data), storage_key=key, sha256=hashlib.sha256(data).hexdigest(), uploaded_by_id=principal.id, purpose="signed_copy")
    session.add(att)
    await session.flush()
    d.signed_copy_id = att.id
    d.status = "signed"
    d.signature_status = "signed"
    await devent(session, d, principal, "signed", note or f"Signed copy uploaded ({name})")
    await session.commit()
    return doc_out(d)
