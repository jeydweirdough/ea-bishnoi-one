"""
Field schema registry (EXECUTIVE-ADMIN.md §15–17, §24).

One definition per dataset drives the Excel/CSV templates, automatic field mapping,
import validation, create/update processing and exports. Field names are the stable
canonical identifiers; labels and synonyms only help people and mapping.

Protected values (approval decisions, audit history, signatures, payment confirmations,
workflow states and restricted personal data) are never importable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from .core import next_reference
from .models import Company, Department, Employee, Request, RequestItem, RequestKind, Role, Task
from .models_ops import Asset, AssetCondition, FleetCard, RfidAccount, Vehicle
from .models_ops2 import FlightBooking, GovRegistration, TravelDocument
from .models_ops3 import BankingCase, Contract, CorporateCard, InventoryItem, Lessor
from .security import Principal


class RowError(Exception):
    def __init__(self, column: str | None, message: str, expected: str | None = None, suggestion: str | None = None):
        super().__init__(message)
        self.column, self.message, self.expected, self.suggestion = column, message, expected, suggestion


@dataclass
class F:
    name: str
    label: str
    type: str = "str"  # str | int | decimal | date | bool | choice
    required: bool = False
    choices: list[str] | None = None
    importable: bool = True
    exportable: bool = True
    sensitive: bool = False
    synonyms: list[str] = field(default_factory=list)
    example: Any = None
    help: str | None = None


@dataclass
class Dataset:
    key: str
    label: str
    model: Any
    fields: list[F]
    importable: bool
    match_keys: list[str]  # canonical fields usable to find existing records, in priority order
    export_row: Callable[[Any], dict]
    can_read: Callable[[Principal], bool]
    can_write: Callable[[Principal], bool]
    create: Callable[..., Awaitable[Any]] | None = None
    update: Callable[..., Awaitable[Any]] | None = None
    find: Callable[..., Awaitable[Any]] | None = None
    date_field: str | None = None
    status_attr: str | None = "status"
    note: str | None = None
    sample: dict = field(default_factory=dict)

    def field(self, name: str) -> F | None:
        return next((f for f in self.fields if f.name == name), None)


# ------------------------------------------------------------------ value parsing


def blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def parse(f: F, raw) -> Any:
    """Typed value from a cell. Raises RowError with a helpful expectation."""
    if blank(raw):
        if f.required:
            raise RowError(f.name, f"{f.label} is required", expected=f.help or f.type)
        return None
    if isinstance(raw, str):
        raw = raw.strip()
    try:
        if f.type == "int":
            if isinstance(raw, float) and raw.is_integer():
                return int(raw)
            v = int(str(raw).replace(",", ""))
            return v
        if f.type == "decimal":
            v = Decimal(str(raw).replace(",", "").replace("₱", "").replace("PHP", "").strip())
            if not v.is_finite():
                raise InvalidOperation
            return v.quantize(Decimal("0.01"))
        if f.type == "date":
            if isinstance(raw, datetime):
                return raw.date()
            if isinstance(raw, date):
                return raw
            s = str(raw)
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%d %b %Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(s, fmt).date()
                except ValueError:
                    continue
            raise ValueError
        if f.type == "bool":
            s = str(raw).strip().lower()
            if s in ("yes", "y", "true", "1"):
                return True
            if s in ("no", "n", "false", "0"):
                return False
            raise ValueError
        if f.type == "choice":
            s = str(raw).strip()
            for c in f.choices or []:
                if s.lower() == c.lower() or s.lower().replace(" ", "_") == c.lower():
                    return c
            raise RowError(f.name, f"“{s}” is not an accepted value for {f.label}", expected=", ".join(f.choices or []), suggestion=closest(s, f.choices or []))
        return str(raw)[:4000]
    except RowError:
        raise
    except (ValueError, InvalidOperation, TypeError):
        expected = {"int": "a whole number", "decimal": "a number, e.g. 1500.00", "date": "a date, e.g. 2026-11-30", "bool": "Yes or No"}.get(f.type, f.type)
        raise RowError(f.name, f"{f.label} has an invalid value", expected=expected)


def closest(value: str, options: list[str]) -> str | None:
    import difflib

    m = difflib.get_close_matches(value.lower(), [o.lower() for o in options], n=1, cutoff=0.6)
    return next((o for o in options if m and o.lower() == m[0]), None)


# ------------------------------------------------------------------ resolvers (codes → records, company-isolated)


async def company_id(session, principal: Principal, code: str | None) -> int:
    if blank(code):
        return principal.employee.company_id
    c = (await session.execute(select(Company).where(Company.code == str(code).strip().upper()))).scalar_one_or_none()
    if c is None:
        raise RowError("company_code", f"Unknown company code “{code}”", expected="GPI or 2MG")
    if c.id not in principal.company_ids:
        raise RowError("company_code", f"You have no access to company {c.code}")
    return c.id


async def employee_id(session, value, cid: int, column: str, *, staff: bool = False) -> int | None:
    if blank(value):
        return None
    e = (await session.execute(select(Employee).where(Employee.employee_no == str(value).strip().upper()))).scalar_one_or_none()
    if e is None or not e.active:
        raise RowError(column, f"Unknown employee ID “{value}”", expected="An employee number such as EA-0101")
    comp = await session.get(Company, cid)
    if e.company_id != cid and comp.code not in (e.company_access or []):
        raise RowError(column, f"{e.name} is not in company {comp.code}")
    if staff and e.role not in (Role.admin, Role.assistant):
        raise RowError(column, f"{e.name} is not an Admin or Assistant user")
    return e.id


async def department_id(session, value, cid: int) -> int | None:
    if blank(value):
        return None
    d = (await session.execute(select(Department).where(Department.company_id == cid, Department.code == str(value).strip().upper()))).scalar_one_or_none()
    if d is None:
        raise RowError("department_code", f"Unknown department code “{value}” in this company")
    return d.id


async def vehicle_id(session, value, cid: int) -> int | None:
    if blank(value):
        return None
    v = str(value).strip().upper()
    rec = (await session.execute(select(Vehicle).where(Vehicle.company_id == cid, (Vehicle.reference == v) | (Vehicle.plate_number == v) | (Vehicle.conduction_sticker == v)))).scalar_one_or_none()
    if rec is None:
        raise RowError("vehicle_id", f"No vehicle “{value}” in this company", expected="Vehicle reference or plate number")
    return rec.id


def code_of(c: Company | None) -> str | None:
    return c.code if c else None


def emp_no(e: Employee | None) -> str | None:
    return e.employee_no if e else None


def pyd(model: type[BaseModel], payload: dict) -> BaseModel:
    """Run the module's own validation and turn the first error into a RowError on the right column."""
    try:
        return model(**payload)
    except ValidationError as e:
        err = e.errors()[0]
        col = str(err["loc"][0]) if err.get("loc") else None
        msg = err["msg"].replace("Value error, ", "")
        raise RowError(col, msg)


async def find_by(session, principal, model, attr: str, value):
    if blank(value):
        return None
    v = str(value).strip()
    col = getattr(model, attr)
    stmt = select(model).where(col == (v.upper() if attr in ("reference", "serial_number", "plate_number", "item_code", "employee_no") else v))
    if hasattr(model, "company_id"):
        stmt = stmt.where(model.company_id.in_(principal.company_ids))
    return (await session.execute(stmt)).scalars().first()


# ------------------------------------------------------------------ permissions

staff = lambda p: p.is_staff  # noqa: E731
admin = lambda p: p.is_admin  # noqa: E731
inv_write = lambda p: p.is_admin or (p.is_staff and p.delegated("inventory_adjust"))  # noqa: E731
bank_read = lambda p: p.is_admin or (p.is_staff and p.delegated("banking"))  # noqa: E731
travel_docs = lambda p: p.is_admin or (p.is_staff and p.delegated("travel_documents"))  # noqa: E731

# ------------------------------------------------------------------ datasets

COND = [c.value for c in AssetCondition]


def _asset_row(a: Asset) -> dict:
    return {
        "asset_id": a.reference, "company_code": code_of(a.company), "asset_name": a.name, "asset_category": a.category, "brand": a.brand, "model": a.model,
        "serial_number": a.serial_number, "condition": a.condition, "status": a.status, "department_code": a.department.code if a.department else None,
        "location": a.location, "issued_by_employee_id": emp_no(a.issued_by), "issued_to_employee_id": emp_no(a.holder), "issued_date": a.date_issued,
        "quantity": a.quantity, "unit": a.unit, "purchase_date": a.purchase_date, "receiving_reference": a.purchase_reference, "purpose": a.purpose, "remarks": a.remarks,
    }


async def _asset_payload(session, principal, v: dict) -> tuple[int, dict]:
    from .routers.assets import AssetIn

    cid = await company_id(session, principal, v.get("company_code"))
    payload = {
        "company_id": cid, "department_id": await department_id(session, v.get("department_code"), cid), "name": v.get("asset_name"), "category": v.get("asset_category"),
        "serial_number": v.get("serial_number"), "brand": v.get("brand"), "model": v.get("model"), "quantity": v.get("quantity") or 1, "unit": v.get("unit") or "unit",
        "condition": v.get("condition") or "brand_new", "location": v.get("location"), "purchase_date": v.get("purchase_date"), "purchase_reference": v.get("receiving_reference"),
        "purpose": v.get("purpose"), "remarks": v.get("remarks"),
    }
    return cid, pyd(AssetIn, payload).model_dump()


async def _asset_create(session, principal, v: dict):
    cid, p = await _asset_payload(session, principal, v)
    if p["serial_number"] and (await session.execute(select(Asset.id).where(Asset.serial_number == p["serial_number"]))).first():
        raise RowError("serial_number", f"Serial {p['serial_number']} is already registered", suggestion="Use Update mode to change the existing asset")
    a = Asset(reference=await next_reference(session, "AST"), **p)
    session.add(a)
    return a


async def _asset_update(session, principal, a: Asset, v: dict):
    cid, p = await _asset_payload(session, principal, v)
    if cid != a.company_id:
        raise RowError("company_code", "An import cannot move an asset to another company")
    if p["serial_number"] and (await session.execute(select(Asset.id).where(Asset.serial_number == p["serial_number"], Asset.id != a.id))).first():
        raise RowError("serial_number", f"Serial {p['serial_number']} belongs to another asset")
    for k, val in p.items():
        if k != "company_id":
            setattr(a, k, val)
    a.version += 1
    return a


async def _asset_find(session, principal, key, value, row=None):
    return await find_by(session, principal, Asset, {"asset_id": "reference", "serial_number": "serial_number"}[key], value)


ASSETS = Dataset(
    key="assets", label="Asset Registry", model=Asset, importable=True, match_keys=["asset_id", "serial_number"], date_field="purchase_date",
    fields=[
        F("asset_id", "Asset ID", synonyms=["asset tag", "tag", "asset no", "reference"], importable=False, help="Leave empty for new assets; used to update existing ones"),
        F("company_code", "Company", synonyms=["company"], example="GPI"),
        F("asset_name", "Asset Name", required=True, synonyms=["name", "item", "description"], example="Lenovo ThinkPad T14"),
        F("asset_category", "Category", required=True, synonyms=["category", "type"], example="IT equipment"),
        F("brand", "Brand", synonyms=["brand name", "make"], example="Lenovo"),
        F("model", "Model", synonyms=["model name", "model no"], example="T14 Gen 4"),
        F("serial_number", "Serial Number", synonyms=["serial no", "serial", "s/n", "sn"], example="PF-3XK91"),
        F("condition", "Condition", "choice", choices=COND, example="brand_new"),
        F("status", "Status", importable=False),
        F("department_code", "Department", synonyms=["department", "dept"], example="SAL"),
        F("location", "Location", synonyms=["site", "room"], example="2F Sales"),
        F("issued_by_employee_id", "Issued By", importable=False),
        F("issued_to_employee_id", "Issued To", importable=False, help="Use Asset Assignment to issue assets"),
        F("issued_date", "Date Issued", "date", importable=False),
        F("quantity", "Quantity", "int", synonyms=["qty"], example=1),
        F("unit", "Unit", example="unit"),
        F("purchase_date", "Purchase Date", "date", synonyms=["date purchased"], example="2026-01-15"),
        F("receiving_reference", "Receiving / Purchase Reference", synonyms=["purchase reference", "po", "dr", "or"], example="PO-2026-0101"),
        F("purpose", "Purpose"),
        F("remarks", "Remarks", synonyms=["notes"]),
    ],
    export_row=_asset_row, can_read=staff, can_write=staff, create=_asset_create, update=_asset_update, find=_asset_find,
    note="Issuing, returning and transferring are done in the app so that acknowledgements stay in the history.",
)


def _inv_row(i: InventoryItem) -> dict:
    return {
        "item_code": i.item_code, "company_code": code_of(i.company), "item_name": i.name, "category": i.category, "brand": i.brand, "model": i.model, "unit": i.unit,
        "storage_location": i.location, "quantity_on_hand": i.on_hand, "reserved": i.reserved, "available": i.available, "reorder_level": i.reorder_level,
        "reorder_quantity": i.reorder_quantity, "unit_cost_php": i.unit_cost_php, "value_php": (i.unit_cost_php or Decimal(0)) * i.on_hand, "preferred_supplier": i.supplier,
        "serialized_on_issue": "Yes" if i.serialized_on_issue else "No", "status": i.status,
    }


async def _inv_payload(session, principal, v):
    from .routers.inventory import ItemIn

    cid = await company_id(session, principal, v.get("company_code"))
    p = {
        "company_id": cid, "item_code": v.get("item_code"), "name": v.get("item_name"), "category": v.get("category") or "Equipment", "brand": v.get("brand"), "model": v.get("model"),
        "unit": v.get("unit") or "pc", "location": v.get("storage_location"), "opening_quantity": v.get("quantity_on_hand") or 0, "reorder_level": v.get("reorder_level") or 0,
        "reorder_quantity": v.get("reorder_quantity") or 0, "unit_cost_php": v.get("unit_cost_php"), "supplier": v.get("preferred_supplier"),
        "serialized_on_issue": v.get("serialized_on_issue") in (True, "Yes", "yes", "Y", "true"), "status": v.get("status") or "active",
    }
    return cid, pyd(ItemIn, p).model_dump()


async def _inv_create(session, principal, v):
    from .routers.inventory import move

    cid, p = await _inv_payload(session, principal, v)
    if (await session.execute(select(InventoryItem.id).where(InventoryItem.company_id == cid, InventoryItem.item_code == p["item_code"], InventoryItem.location == p["location"]))).first():
        raise RowError("item_code", f"{p['item_code']} already has a stock line at {p['location']}", suggestion="Use Update mode")
    qty = p.pop("opening_quantity")
    i = InventoryItem(on_hand=0, reserved=0, **p)
    session.add(i)
    await session.flush()
    if qty:
        await move(session, principal, i, "stock_in", qty, reason="Opening balance (import)")
    return i


async def _inv_update(session, principal, i: InventoryItem, v):
    from .routers.inventory import move

    cid, p = await _inv_payload(session, principal, v)
    if p["location"] != i.location or cid != i.company_id:
        raise RowError("storage_location", "Imports cannot move stock; use a transfer")
    qty = p.pop("opening_quantity")
    for k, val in p.items():
        if k not in ("company_id",):
            setattr(i, k, val)
    if v.get("quantity_on_hand") is not None and qty != i.on_hand:
        await move(session, principal, i, "adjustment", qty - i.on_hand, reason="Quantity set by import")
    i.version += 1
    return i


async def _inv_find(session, principal, key, value, row=None):
    stmt = select(InventoryItem).where(InventoryItem.company_id.in_(principal.company_ids), InventoryItem.item_code == str(value).strip().upper())
    if row and not blank(row.get("storage_location")):
        stmt = stmt.where(InventoryItem.location == str(row["storage_location"]).strip())
    return (await session.execute(stmt)).scalars().first()


INVENTORY = Dataset(
    key="inventory", label="Equipment Inventory", model=InventoryItem, importable=True, match_keys=["item_code"],
    fields=[
        F("item_code", "Item Code", required=True, synonyms=["sku", "code", "item no"], example="TNR-85A"),
        F("company_code", "Company", synonyms=["company"], example="GPI"),
        F("item_name", "Item Name", required=True, synonyms=["name", "item", "description"], example="HP 85A toner"),
        F("category", "Category", "choice", choices=["Equipment", "Supplies", "Spare Parts", "Consumables"], example="Supplies"),
        F("brand", "Brand", example="HP"),
        F("model", "Model", example="CE285A"),
        F("unit", "Unit", example="pc"),
        F("storage_location", "Storage Location", required=True, synonyms=["location", "warehouse", "storeroom"], example="HQ stockroom"),
        F("quantity_on_hand", "Quantity on Hand", "int", synonyms=["qty", "quantity", "on hand", "stock"], example=12, help="New lines: opening stock. Update mode: sets the count (logged as an adjustment)"),
        F("reserved", "Reserved", "int", importable=False),
        F("available", "Available", "int", importable=False),
        F("reorder_level", "Reorder Level", "int", synonyms=["min", "minimum"], example=4),
        F("reorder_quantity", "Reorder Quantity", "int", synonyms=["reorder qty"], example=10),
        F("unit_cost_php", "Unit Cost (PHP)", "decimal", synonyms=["unit cost", "cost", "price"], example="2450.00"),
        F("value_php", "Value (PHP)", "decimal", importable=False),
        F("preferred_supplier", "Preferred Supplier", synonyms=["supplier", "vendor"], example="Octagon"),
        F("serialized_on_issue", "Serialized on Issue", "bool", example="No"),
        F("status", "Status", "choice", choices=["active", "discontinued"], example="active"),
    ],
    export_row=_inv_row, can_read=staff, can_write=inv_write, create=_inv_create, update=_inv_update, find=_inv_find,
)


def _veh_row(v: Vehicle) -> dict:
    return {
        "vehicle_id": v.reference, "company_code": code_of(v.company), "vehicle_type": v.vehicle_type, "make": v.make, "model": v.model, "year_model": v.year_model,
        "plate_number": v.plate_number, "conduction_sticker": v.conduction_sticker, "color": v.color, "owner_name": v.owner_name, "assigned_driver_employee_id": emp_no(v.assigned_driver),
        "registration_renewal_date": v.registration_renewal_date, "insurance_expiry_date": v.insurance_expiry_date, "next_pms_date": v.next_pms_date, "odometer_km": v.odometer_km, "status": v.status,
    }


async def _veh_payload(session, principal, v):
    from .routers.fleet import VehicleIn

    cid = await company_id(session, principal, v.get("company_code"))
    p = {
        "company_id": cid, "vehicle_type": v.get("vehicle_type"), "make": v.get("make"), "model": v.get("model"), "year_model": v.get("year_model"), "color": v.get("color"),
        "plate_number": v.get("plate_number"), "conduction_sticker": v.get("conduction_sticker"), "owner_name": v.get("owner_name"),
        "assigned_driver_id": await employee_id(session, v.get("assigned_driver_employee_id"), cid, "assigned_driver_employee_id"),
        "registration_renewal_date": v.get("registration_renewal_date"), "insurance_expiry_date": v.get("insurance_expiry_date"), "next_pms_date": v.get("next_pms_date"),
        "odometer_km": v.get("odometer_km"), "status": v.get("status") or "active",
    }
    m = pyd(VehicleIn, p).model_dump()
    if not m["plate_number"] and not m["conduction_sticker"]:
        raise RowError("plate_number", "Enter a plate number or conduction sticker")
    return cid, m


async def _veh_unique(session, m, exclude=None):
    for k in ("plate_number", "conduction_sticker"):
        if m.get(k):
            stmt = select(Vehicle.id).where(getattr(Vehicle, k) == m[k])
            if exclude:
                stmt = stmt.where(Vehicle.id != exclude)
            if (await session.execute(stmt)).first():
                raise RowError(k, f"{m[k]} is already registered", suggestion="Use Update mode")


async def _veh_create(session, principal, v):
    cid, m = await _veh_payload(session, principal, v)
    await _veh_unique(session, m)
    rec = Vehicle(reference=await next_reference(session, "FLT"), **m)
    session.add(rec)
    return rec


async def _veh_update(session, principal, rec, v):
    cid, m = await _veh_payload(session, principal, v)
    if cid != rec.company_id:
        raise RowError("company_code", "An import cannot move a vehicle to another company")
    if m["status"] == "disposed" and not principal.is_admin:
        raise RowError("status", "Only Admin can mark a vehicle disposed")
    await _veh_unique(session, m, rec.id)
    for k, val in m.items():
        if k != "company_id":
            setattr(rec, k, val)
    rec.version += 1
    return rec


async def _veh_find(session, principal, key, value, row=None):
    return await find_by(session, principal, Vehicle, {"vehicle_id": "reference", "plate_number": "plate_number"}[key], value)


VEHICLES = Dataset(
    key="vehicles", label="Vehicle Registry", model=Vehicle, importable=True, match_keys=["vehicle_id", "plate_number"], date_field="registration_renewal_date",
    fields=[
        F("vehicle_id", "Vehicle ID", importable=False, synonyms=["reference"]),
        F("company_code", "Company", synonyms=["company"], example="GPI"),
        F("vehicle_type", "Vehicle Type", required=True, synonyms=["type"], example="Van"),
        F("make", "Make", required=True, synonyms=["brand"], example="Toyota"),
        F("model", "Model", required=True, example="Hiace"),
        F("year_model", "Year Model", "int", synonyms=["year"], example=2022),
        F("plate_number", "Plate Number", synonyms=["plate no", "plate"], example="NAB 1234"),
        F("conduction_sticker", "Conduction Sticker", synonyms=["cs"], example=""),
        F("color", "Color", example="White"),
        F("owner_name", "Registered Owner", synonyms=["owner"], example="Getmeds Philippines Inc."),
        F("assigned_driver_employee_id", "Assigned Driver", synonyms=["driver"], example="EA-0103"),
        F("registration_renewal_date", "Registration Renewal Date", "date", synonyms=["registration"], example="2027-03-31"),
        F("insurance_expiry_date", "Insurance Expiry Date", "date", synonyms=["insurance"], example="2027-01-15"),
        F("next_pms_date", "Next PMS Date", "date", synonyms=["pms"], example="2026-12-20"),
        F("odometer_km", "Odometer (km)", "int", synonyms=["odometer", "mileage"], example=15000),
        F("status", "Status", "choice", choices=["active", "under_maintenance", "inactive", "disposed"], example="active"),
    ],
    export_row=_veh_row, can_read=staff, can_write=staff, create=_veh_create, update=_veh_update, find=_veh_find,
)


def _fleetcard_row(c: FleetCard) -> dict:
    return {
        "card_id": c.reference, "company_code": code_of(c.company), "vehicle_id": c.vehicle.reference if c.vehicle else None, "plate_number": c.vehicle.plate_number if c.vehicle else None,
        "account_type": "fleet_card", "provider": c.provider, "account_reference": f"****{c.card_last4}", "fuel_type": c.fuel_type,
        "configured_limit_php": c.configured_amount_php, "billing_cycle": c.billing_cycle, "monitoring_status": c.monitoring_status,
    }


def _rfid_row(r: RfidAccount) -> dict:
    return {
        "card_id": None, "company_code": code_of(r.company), "vehicle_id": r.vehicle.reference if r.vehicle else None, "plate_number": r.vehicle.plate_number if r.vehicle else None,
        "account_type": "rfid", "provider": r.provider, "account_reference": r.account_reference, "fuel_type": None, "configured_limit_php": r.balance_php,
        "billing_cycle": None, "monitoring_status": r.monitoring_status,
    }


async def _fleetcard_create(session, principal, v):
    cid = await company_id(session, principal, v.get("company_code"))
    vid = await vehicle_id(session, v.get("vehicle_id") or v.get("plate_number"), cid)
    if (v.get("account_type") or "fleet_card") == "rfid":
        from .routers.fleet import RfidIn

        m = pyd(RfidIn, {"company_id": cid, "vehicle_id": vid, "provider": v.get("provider"), "account_reference": v.get("account_reference"), "balance_php": v.get("configured_limit_php") or 0}).model_dump()
        if (await session.execute(select(RfidAccount.id).where(RfidAccount.provider == m["provider"], RfidAccount.account_reference == m["account_reference"]))).first():
            raise RowError("account_reference", "That RFID account is already registered")
        rec = RfidAccount(**m)
        session.add(rec)
        return rec
    from .routers.fleet import CardIn, default_limit

    m = pyd(CardIn, {"company_id": cid, "vehicle_id": vid, "provider": v.get("provider") or "Shell", "card_number_last4": v.get("account_reference"), "fuel_type": v.get("fuel_type"), "configured_amount_php": v.get("configured_limit_php"), "billing_cycle": v.get("billing_cycle") or "monthly", "monitoring_status": v.get("monitoring_status") or "active"}).model_dump()
    rec = FleetCard(
        reference=await next_reference(session, "FCD"), company_id=cid, vehicle_id=vid, provider=m["provider"], card_last4=m["card_number_last4"], fuel_type=m["fuel_type"],
        configured_amount_php=m["configured_amount_php"] or await default_limit(session), billing_cycle=m["billing_cycle"], monitoring_status=m["monitoring_status"],
    )
    session.add(rec)
    return rec


FLEET_ACCOUNTS = Dataset(
    key="fleet_accounts", label="Fleet Cards & RFID", model=FleetCard, importable=True, match_keys=[],
    fields=[
        F("card_id", "Card ID", importable=False),
        F("company_code", "Company", example="GPI"),
        F("vehicle_id", "Vehicle", synonyms=["vehicle", "plate"], example="NAB 1234"),
        F("plate_number", "Plate Number", importable=False),
        F("account_type", "Account Type", "choice", choices=["fleet_card", "rfid"], required=True, example="fleet_card"),
        F("provider", "Provider", required=True, example="Shell"),
        F("account_reference", "Account / Card Reference", required=True, synonyms=["card number", "account"], example="1234", help="Fleet cards: last 4 digits only"),
        F("fuel_type", "Fuel Type", example="Diesel"),
        F("configured_limit_php", "Configured Limit / Balance (PHP)", "decimal", synonyms=["limit", "amount"], example="10000.00"),
        F("billing_cycle", "Billing Cycle", "choice", choices=["monthly", "biweekly", "weekly"], example="monthly"),
        F("monitoring_status", "Monitoring Status", "choice", choices=["active", "suspended", "cancelled"], example="active"),
    ],
    export_row=_fleetcard_row, can_read=staff, can_write=staff, create=_fleetcard_create, status_attr="monitoring_status",
    note="Create-only: card limits and statuses are changed in the app. RFID accounts export in the same sheet.",
)


def _reg_row(r: GovRegistration) -> dict:
    return {
        "document_id": r.reference, "company_code": code_of(r.company), "document_name": r.document_name, "registration_type": r.registration_type,
        "registration_number": r.registration_number, "registration_date": r.registration_date, "validity_years": r.validity_years, "expiry_date": r.expiry_date,
        "due_date": r.due_date, "responsible_employee_id": emp_no(r.responsible), "status": r.status, "site": r.site, "notes": r.notes,
    }


async def _reg_payload(session, principal, v):
    from .models_ops2 import REG_TYPES
    from .routers.compliance import RegIn

    cid = await company_id(session, principal, v.get("company_code"))
    t = v.get("registration_type")
    if t and t not in REG_TYPES:
        raise RowError("registration_type", f"“{t}” is not a registration type", expected=", ".join(REG_TYPES), suggestion=closest(t, REG_TYPES))
    p = {
        "company_id": cid, "document_name": v.get("document_name"), "registration_type": t, "registration_number": v.get("registration_number"),
        "registration_date": v.get("registration_date"), "validity_years": v.get("validity_years"), "expiry_date": v.get("expiry_date"), "due_date": v.get("due_date"),
        "responsible_id": await employee_id(session, v.get("responsible_employee_id"), cid, "responsible_employee_id"), "site": v.get("site"), "notes": v.get("notes"),
    }
    return cid, pyd(RegIn, p).model_dump()


async def _reg_create(session, principal, v):
    from .routers.compliance import status_for

    cid, m = await _reg_payload(session, principal, v)
    r = GovRegistration(reference=await next_reference(session, "CMP"), status="ongoing", **m)
    r.status = status_for(r)
    session.add(r)
    return r


async def _reg_update(session, principal, r, v):
    from .routers.compliance import status_for

    if r.status in ("terminated", "void"):
        raise RowError(None, "Terminated or void records cannot be changed")
    cid, m = await _reg_payload(session, principal, v)
    for k, val in m.items():
        if k != "company_id":
            setattr(r, k, val)
    r.status = status_for(r)
    r.version += 1
    return r


REGISTRATIONS = Dataset(
    key="registrations", label="Government Registrations", model=GovRegistration, importable=True, match_keys=["document_id"], date_field="expiry_date",
    fields=[
        F("document_id", "Document ID", importable=False, synonyms=["reference"]),
        F("company_code", "Company", example="GPI"),
        F("document_name", "Document Name", required=True, synonyms=["document", "name"], example="Mayor's Permit — Makati HQ"),
        F("registration_type", "Registration Type", required=True, synonyms=["type"], example="Business Permit"),
        F("registration_number", "Registration Number", synonyms=["reg no", "number"], example="BP-2026-1188"),
        F("registration_date", "Registration Date", "date", synonyms=["registered"], example="2026-01-20"),
        F("validity_years", "Years of Validity", "int", synonyms=["validity"], example=1),
        F("expiry_date", "Expiry Date", "date", synonyms=["expiry", "expires"], example=""),
        F("due_date", "Due Date", "date", synonyms=["filing due"], example="2026-12-20"),
        F("responsible_employee_id", "Responsible Employee", synonyms=["responsible"], example="EA-0002"),
        F("status", "Status", importable=False),
        F("site", "Site", example="Makati HQ"),
        F("notes", "Notes"),
    ],
    export_row=_reg_row, can_read=staff, can_write=staff, create=_reg_create, update=_reg_update, find=lambda s, p, k, v, row=None: find_by(s, p, GovRegistration, "reference", v),
)


def _contract_row(c: Contract) -> dict:
    return {
        "contract_reference": c.reference, "company_code": code_of(c.company), "contract_type": c.contract_type, "title": c.title, "site": c.property_name, "location": c.location,
        "lessor_name": c.lessor.name if c.lessor else None, "start_date": c.start_date, "end_date": c.end_date, "covered_year": f"{c.start_date.year}-{c.end_date.year}",
        "monthly_rent_php": c.monthly_rent_php, "deposit_php": c.deposit_php, "rent_due_day": c.rent_due_day, "renewal_due_date": c.end_date and date.fromordinal(c.end_date.toordinal() - (c.renewal_notice_days or 60)),
        "responsible_employee_id": emp_no(c.responsible), "external_reference": c.external_reference, "status": c.status,
    }


async def _contract_payload(session, principal, v):
    from .routers.contracts_banking import ContractIn

    cid = await company_id(session, principal, v.get("company_code"))
    lid = None
    if not blank(v.get("lessor_name")):
        l = (await session.execute(select(Lessor).where(Lessor.company_id == cid, Lessor.name.ilike(str(v["lessor_name"]).strip())))).scalar_one_or_none()
        if l is None:
            raise RowError("lessor_name", f"No lessor named “{v['lessor_name']}”", suggestion="Import Lessors first, or add the lessor in the app")
        lid = l.id
    p = {
        "company_id": cid, "contract_type": v.get("contract_type"), "title": v.get("title"), "property_name": v.get("site"), "location": v.get("location"), "lessor_id": lid,
        "start_date": v.get("start_date"), "end_date": v.get("end_date"), "monthly_rent_php": v.get("monthly_rent_php"), "deposit_php": v.get("deposit_php"),
        "rent_due_day": v.get("rent_due_day"), "responsible_id": await employee_id(session, v.get("responsible_employee_id"), cid, "responsible_employee_id"),
        "external_reference": v.get("external_reference"),
    }
    return cid, pyd(ContractIn, p).model_dump()


async def _contract_create(session, principal, v):
    from .routers.contracts_banking import contract_status

    cid, m = await _contract_payload(session, principal, v)
    c = Contract(reference=await next_reference(session, "CON"), status="active", **m)
    c.status = contract_status(c)
    session.add(c)
    return c


async def _contract_update(session, principal, c, v):
    from .routers.contracts_banking import contract_status

    if c.status in ("renewed", "terminated"):
        raise RowError(None, "Renewed or terminated contracts are history and cannot be changed")
    cid, m = await _contract_payload(session, principal, v)
    for k, val in m.items():
        if k != "company_id":
            setattr(c, k, val)
    c.status = contract_status(c)
    c.version += 1
    return c


CONTRACTS = Dataset(
    key="contracts", label="Contracts", model=Contract, importable=True, match_keys=["contract_reference"], date_field="end_date",
    fields=[
        F("contract_reference", "Contract Reference", importable=False, synonyms=["contract id", "reference"]),
        F("company_code", "Company", example="GPI"),
        F("contract_type", "Contract Type", "choice", required=True, choices=["office_lease", "staff_house", "other"], synonyms=["type"], example="office_lease"),
        F("title", "Title", required=True, synonyms=["contract", "name"], example="HQ office lease, 12F"),
        F("site", "Site / Property", synonyms=["property", "site"], example="Ayala Tower One"),
        F("location", "Location", synonyms=["address"], example="Makati City"),
        F("lessor_name", "Lessor Name", synonyms=["lessor", "landlord"], example="Ayala Land Inc."),
        F("start_date", "Start Date", "date", required=True, synonyms=["start"], example="2026-01-01"),
        F("end_date", "End Date", "date", required=True, synonyms=["end", "expiry"], example="2027-12-31"),
        F("covered_year", "Covered Year", importable=False),
        F("monthly_rent_php", "Monthly Rent (PHP)", "decimal", synonyms=["monthly rental", "rent"], example="185000.00"),
        F("deposit_php", "Deposit (PHP)", "decimal", synonyms=["deposit"], example="370000.00"),
        F("rent_due_day", "Rent Due Day", "int", synonyms=["due day"], example=5),
        F("renewal_due_date", "Renewal Due Date", "date", importable=False),
        F("responsible_employee_id", "Responsible Employee", example="EA-0001"),
        F("external_reference", "Bishnoi One Contracts Reference", synonyms=["external reference"], example=""),
        F("status", "Status", importable=False),
    ],
    export_row=_contract_row, can_read=staff, can_write=staff, create=_contract_create, update=_contract_update, find=lambda s, p, k, v, row=None: find_by(s, p, Contract, "reference", v),
)


def _lessor_row(l: Lessor) -> dict:
    return {"lessor_name": l.name, "company_code": code_of(l.company), "contact_person": l.contact_person, "phone": l.phone, "email": l.email, "address": l.address, "notes": l.notes}


async def _lessor_payload(session, principal, v):
    from .routers.contracts_banking import LessorIn

    cid = await company_id(session, principal, v.get("company_code"))
    return cid, pyd(LessorIn, {"company_id": cid, "name": v.get("lessor_name"), "contact_person": v.get("contact_person"), "phone": v.get("phone"), "email": v.get("email"), "address": v.get("address"), "notes": v.get("notes")}).model_dump()


async def _lessor_create(session, principal, v):
    cid, m = await _lessor_payload(session, principal, v)
    if (await session.execute(select(Lessor.id).where(Lessor.company_id == cid, Lessor.name.ilike(m["name"])))).first():
        raise RowError("lessor_name", f"{m['name']} already exists", suggestion="Use Update mode")
    rec = Lessor(**m)
    session.add(rec)
    return rec


async def _lessor_update(session, principal, rec, v):
    cid, m = await _lessor_payload(session, principal, v)
    for k, val in m.items():
        if k != "company_id":
            setattr(rec, k, val)
    return rec


async def _lessor_find(session, principal, key, value, row=None):
    return (await session.execute(select(Lessor).where(Lessor.company_id.in_(principal.company_ids), Lessor.name.ilike(str(value).strip())))).scalars().first()


LESSORS = Dataset(
    key="lessors", label="Lessors", model=Lessor, importable=True, match_keys=["lessor_name"], status_attr=None,
    fields=[
        F("lessor_name", "Lessor Name", required=True, synonyms=["lessor", "name", "landlord"], example="Ayala Land Inc."),
        F("company_code", "Company", example="GPI"),
        F("contact_person", "Contact Person", synonyms=["contact"], example="Ana Lim"),
        F("phone", "Phone", synonyms=["mobile", "tel"], example="0917 555 0101"),
        F("email", "Email", example="leasing@example.com"),
        F("address", "Address"),
        F("notes", "Notes"),
    ],
    export_row=_lessor_row, can_read=staff, can_write=staff, create=_lessor_create, update=_lessor_update, find=_lessor_find,
)


def _task_row(t: Task) -> dict:
    return {
        "task_reference": t.reference, "company_code": code_of(t.company), "task_title": t.title, "assigned_employee_id": emp_no(t.assignee), "due_date": t.due_date,
        "priority": t.priority, "source_module": t.source_module, "source_record_id": t.source_record_id, "status": t.status, "notes": t.description,
    }


async def _task_payload(session, principal, v):
    cid = await company_id(session, principal, v.get("company_code"))
    aid = await employee_id(session, v.get("assigned_employee_id"), cid, "assigned_employee_id", staff=True)
    if aid and aid != principal.id and not principal.can("assign"):
        raise RowError("assigned_employee_id", "Assistants can only import tasks for themselves unless delegated")
    if not v.get("task_title"):
        raise RowError("task_title", "Task title is required")
    return cid, {"company_id": cid, "title": v["task_title"], "assignee_id": aid, "due_date": v.get("due_date"), "priority": v.get("priority") or "normal", "source_module": v.get("source_module"), "source_record_id": v.get("source_record_id"), "description": v.get("notes")}


async def _task_create(session, principal, v):
    cid, m = await _task_payload(session, principal, v)
    status = v.get("status") or "open"
    if status in ("done",):
        raise RowError("status", "Completed tasks cannot be imported; completion needs evidence in the app")
    t = Task(reference=await next_reference(session, "TSK"), created_by_id=principal.id, status=status, **m)
    session.add(t)
    return t


async def _task_update(session, principal, t, v):
    if t.status in ("done", "cancelled"):
        raise RowError(None, "Closed tasks cannot be changed by import")
    cid, m = await _task_payload(session, principal, v)
    for k, val in m.items():
        if k != "company_id":
            setattr(t, k, val)
    if v.get("status") in ("open", "in_progress", "cancelled"):
        t.status = v["status"]
    return t


TASKS = Dataset(
    key="tasks", label="Tasks", model=Task, importable=True, match_keys=["task_reference"], date_field="due_date",
    fields=[
        F("task_reference", "Task Reference", importable=False, synonyms=["reference"]),
        F("company_code", "Company", example="GPI"),
        F("task_title", "Task Title", required=True, synonyms=["title", "task"], example="Collect fire safety certificate"),
        F("assigned_employee_id", "Assigned Employee", synonyms=["assignee", "assigned to"], example="EA-0002"),
        F("due_date", "Due Date", "date", synonyms=["due"], example="2026-11-30"),
        F("priority", "Priority", "choice", choices=["low", "normal", "high", "critical"], example="normal"),
        F("source_module", "Source Module", example="compliance"),
        F("source_record_id", "Source Record ID", "int", example=""),
        F("status", "Status", "choice", choices=["open", "in_progress", "cancelled", "done"], example="open"),
        F("notes", "Notes", synonyms=["description", "details"]),
    ],
    export_row=_task_row, can_read=staff, can_write=staff, create=_task_create, update=_task_update, find=lambda s, p, k, v, row=None: find_by(s, p, Task, "reference", v),
)


def _req_row(r: Request) -> dict:
    return {
        "request_id": r.reference, "request_type": r.kind, "company_code": code_of(r.company), "department_code": r.department.code if r.department else None,
        "requester_employee_id": emp_no(r.requester), "subject": r.subject, "description": r.description, "priority": r.priority, "needed_by_date": r.needed_by,
        "assigned_employee_id": emp_no(r.assigned_to), "status": r.status, "submitted_at": r.submitted_at.replace(tzinfo=None) if r.submitted_at else None,
        "items": "; ".join(f"{i.quantity} {i.unit} {i.item_name}" for i in r.items),
    }


async def _req_create(session, principal, v):
    from .routers.requests import RequestIn

    cid = await company_id(session, principal, v.get("company_code"))
    rid = await employee_id(session, v.get("requester_employee_id"), cid, "requester_employee_id") or principal.id
    emp = await session.get(Employee, rid)
    kind = v.get("request_type") or "concern"
    payload = {"kind": kind, "subject": v.get("subject") or "", "description": v.get("description") or "", "requested_priority": v.get("priority") or "normal", "needed_by": v.get("needed_by_date")}
    m = pyd(RequestIn, payload)
    if not m.subject:
        raise RowError("subject", "Subject is required")
    r = Request(
        reference=await next_reference(session, "REQ"), kind=m.kind, company_id=cid, department_id=await department_id(session, v.get("department_code"), cid) or emp.department_id,
        requester_id=rid, subject=m.subject, description=m.description, requested_priority=m.requested_priority, needed_by=m.needed_by, status="draft",
    )
    if kind in ("supplies", "asset", "local_purchase") and not blank(v.get("items")):
        for n, part in enumerate([p.strip() for p in str(v["items"]).split(";") if p.strip()]):
            mm = re.match(r"^(\d+)\s+(\S+)\s+(.+)$", part)
            if not mm:
                raise RowError("items", f"“{part}” should look like “5 ream Bond paper”")
            r.items.append(RequestItem(position=n, item_name=mm.group(3), quantity=int(mm.group(1)), unit=mm.group(2)))
    session.add(r)
    return r


REQUESTS = Dataset(
    key="requests", label="Requests & Concerns", model=Request, importable=True, match_keys=[], date_field="needed_by",
    fields=[
        F("request_id", "Request ID", importable=False, synonyms=["reference"]),
        F("request_type", "Request Type", "choice", required=True, choices=[k.value for k in RequestKind], synonyms=["type", "kind"], example="concern"),
        F("company_code", "Company", example="GPI"),
        F("department_code", "Department", example="SAL"),
        F("requester_employee_id", "Requester", synonyms=["requester", "employee id", "employee"], example="EA-0101"),
        F("subject", "Subject", required=True, example="Aircon leaking in sales area"),
        F("description", "Description", example="Water drips onto desks"),
        F("priority", "Priority", "choice", choices=["low", "normal", "high", "critical"], example="normal"),
        F("needed_by_date", "Needed By", "date", synonyms=["needed by", "required date"], example="2026-12-01"),
        F("assigned_employee_id", "Assigned Employee", importable=False),
        F("status", "Status", importable=False),
        F("submitted_at", "Submitted", "date", importable=False),
        F("items", "Items", synonyms=["item list"], example="", help="Item requests: “5 ream Bond paper; 1 pc Toner 85A”"),
    ],
    export_row=_req_row, can_read=staff, can_write=staff, create=_req_create,
    note="Imported requests arrive as drafts owned by the requester, who submits them so approvals run normally.",
)


def _card_row(c: CorporateCard) -> dict:
    return {
        "card_reference": c.reference, "company_code": code_of(c.company), "bank_name": c.bank, "card_type": c.card_type, "masked_card_last4": c.card_last4,
        "custodian_employee_id": emp_no(c.custodian), "expiry_month": c.expiry_month, "expiry_year": c.expiry_year, "credit_limit_php": c.credit_limit_php, "status": c.status,
    }


async def _card_create(session, principal, v):
    from .routers.contracts_banking import CardIn

    cid = await company_id(session, principal, v.get("company_code"))
    m = pyd(CardIn, {"company_id": cid, "bank": v.get("bank_name"), "card_type": v.get("card_type") or "credit", "card_last4": v.get("masked_card_last4"), "custodian_id": await employee_id(session, v.get("custodian_employee_id"), cid, "custodian_employee_id"), "expiry_month": v.get("expiry_month"), "expiry_year": v.get("expiry_year"), "credit_limit_php": v.get("credit_limit_php")}).model_dump()
    if (await session.execute(select(CorporateCard.id).where(CorporateCard.bank == m["bank"], CorporateCard.card_last4 == m["card_last4"], CorporateCard.custodian_id == m["custodian_id"]))).first():
        raise RowError("masked_card_last4", "That card is already registered for this custodian")
    rec = CorporateCard(reference=await next_reference(session, "CRD"), **m)
    session.add(rec)
    return rec


CORPORATE_CARDS = Dataset(
    key="corporate_cards", label="Corporate Cards", model=CorporateCard, importable=True, match_keys=[],
    fields=[
        F("card_reference", "Card Reference", importable=False),
        F("company_code", "Company", example="GPI"),
        F("bank_name", "Bank", required=True, synonyms=["bank"], example="BPI"),
        F("card_type", "Card Type", "choice", choices=["credit", "debit", "prepaid"], example="credit"),
        F("masked_card_last4", "Card (last 4 digits)", required=True, synonyms=["last 4", "card", "card number"], example="4821", help="Only the last 4 digits. Full numbers are rejected."),
        F("custodian_employee_id", "Custodian", required=True, synonyms=["custodian", "holder"], example="EA-0001"),
        F("expiry_month", "Expiry Month", "int", required=True, example=8),
        F("expiry_year", "Expiry Year", "int", required=True, example=2028),
        F("credit_limit_php", "Credit Limit (PHP)", "decimal", synonyms=["limit"], example="200000.00"),
        F("status", "Status", importable=False),
    ],
    export_row=_card_row, can_read=bank_read, can_write=bank_read, create=_card_create,
    note="Never import CVV, PINs, online-banking passwords or full card numbers.",
)


def _bank_case_row(b: BankingCase) -> dict:
    return {
        "case_reference": b.reference, "company_code": code_of(b.company), "case_type": b.case_type, "bank_name": b.bank, "request_subject": b.subject,
        "masked_card_last4": b.card.card_last4 if b.card else b.account_last4, "renewal_date": b.renewal_date, "finance_reference": b.finance_reference,
        "finance_status": b.finance_status, "status": b.status, "responsible_employee_id": emp_no(b.responsible),
    }


BANKING_CASES = Dataset(
    key="banking_cases", label="Banking Coordination", model=BankingCase, importable=False, match_keys=[],
    fields=[F(n, l, importable=False) for n, l in [("case_reference", "Case Reference"), ("company_code", "Company"), ("case_type", "Case Type"), ("bank_name", "Bank"), ("request_subject", "Subject"), ("masked_card_last4", "Account / Card (last 4)"), ("finance_reference", "Finance Reference"), ("finance_status", "Finance Status"), ("status", "Status"), ("responsible_employee_id", "Responsible")]]
    + [F("renewal_date", "Renewal Date", "date", importable=False)],
    export_row=_bank_case_row, can_read=bank_read, can_write=lambda p: False, date_field="renewal_date",
)


def _flight_row(f: FlightBooking) -> dict:
    return {
        "booking_id": f.reference, "company_code": code_of(f.company), "employee_id": emp_no(f.passenger), "record_type": f"flight_{f.travel_type}", "booking_reference": f.booking_reference,
        "origin": f.origin, "destination": f.destination, "travel_date": f.departure_date, "return_date": f.return_date, "airline": f.airline, "status": f.status,
    }


FLIGHTS = Dataset(
    key="flights", label="Flight Bookings", model=FlightBooking, importable=False, match_keys=[], date_field="departure_date",
    fields=[F(n, l, importable=False) for n, l in [("booking_id", "Booking ID"), ("company_code", "Company"), ("employee_id", "Passenger"), ("record_type", "Record Type"), ("booking_reference", "Booking Reference"), ("origin", "Origin"), ("destination", "Destination"), ("airline", "Airline"), ("status", "Status")]]
    + [F("travel_date", "Departure", "date", importable=False), F("return_date", "Return", "date", importable=False)],
    export_row=_flight_row, can_read=staff, can_write=lambda p: False,
)


def _travel_doc_row(d: TravelDocument) -> dict:
    return {
        "document_reference": d.reference, "company_code": code_of(d.company), "employee_id": emp_no(d.employee), "record_type": d.doc_type, "holder_kind": d.holder_kind,
        "visa_type": d.visa_type, "country": d.country, "passport_expiry_date": d.expiry_date if d.doc_type == "passport" else None,
        "visa_expiry_date": d.expiry_date if d.doc_type == "visa" else None, "status": d.status,
    }


TRAVEL_DOCUMENTS = Dataset(
    key="travel_documents", label="Passports & Visas (restricted)", model=TravelDocument, importable=False, match_keys=[], date_field="expiry_date",
    fields=[F(n, l, importable=False) for n, l in [("document_reference", "Reference"), ("company_code", "Company"), ("employee_id", "Employee"), ("record_type", "Record Type"), ("holder_kind", "Holder"), ("visa_type", "Visa Type"), ("country", "Country"), ("status", "Status")]]
    + [F("passport_expiry_date", "Passport Expiry", "date", importable=False), F("visa_expiry_date", "Visa Expiry", "date", importable=False)],
    export_row=_travel_doc_row, can_read=travel_docs, can_write=lambda p: False,
    note="Sensitive: document numbers and scans are never exported.",
)


DATASETS: dict[str, Dataset] = {d.key: d for d in [REQUESTS, ASSETS, INVENTORY, VEHICLES, FLEET_ACCOUNTS, REGISTRATIONS, CONTRACTS, LESSORS, CORPORATE_CARDS, TASKS, BANKING_CASES, FLIGHTS, TRAVEL_DOCUMENTS]}


async def export_records(session, principal: Principal, ds: Dataset, *, q=None, status=None, company=None, date_from=None, date_to=None, ids=None, assigned=None) -> list:
    """Authorized, company-scoped rows for a dataset with the standard export filters."""
    m = ds.model
    stmt = select(m).where(m.company_id.in_(principal.company_ids))
    if ds.key == "requests":
        from .workflow import scope_filter

        stmt = select(m).where(scope_filter(principal), m.status != "draft")
    if ds.key == "fleet_accounts":
        rows = list((await session.execute(stmt)).scalars()) + list((await session.execute(select(RfidAccount).where(RfidAccount.company_id.in_(principal.company_ids)))).scalars())
        return rows
    if ids:
        stmt = stmt.where(m.id.in_(ids))
    if company:
        c = (await session.execute(select(Company).where(Company.code == company.upper()))).scalar_one_or_none()
        stmt = stmt.where(m.company_id == (c.id if c else -1))
    if status and ds.status_attr and hasattr(m, ds.status_attr):
        stmt = stmt.where(getattr(m, ds.status_attr).in_(status))
    if ds.date_field and hasattr(m, ds.date_field):
        col = getattr(m, ds.date_field)
        if date_from:
            stmt = stmt.where(col >= date_from)
        if date_to:
            stmt = stmt.where(col <= date_to)
    if assigned:
        for attr in ("assigned_to_id", "assignee_id", "holder_id", "responsible_id"):
            if hasattr(m, attr):
                e = (await session.execute(select(Employee).where(Employee.employee_no == assigned.upper()))).scalar_one_or_none()
                stmt = stmt.where(getattr(m, attr) == (e.id if e else -1))
                break
    rows = list((await session.execute(stmt.order_by(m.id))).scalars())
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in " ".join(str(v) for v in ds.export_row(r).values() if v is not None).lower()]
    return rows
