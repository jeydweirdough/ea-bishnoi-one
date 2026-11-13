"""
Read a document and propose form values: POST /api/v1/scan (multipart: kind, file).

Nothing is saved here. The caller fills the form with the proposal, the user reviews it, and the file is
attached to the record when the form is saved. Document text is never stored or logged; the audit trail
records only which fields were read.
"""

import asyncio
import re
from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile
from sqlalchemy import select

from .. import ocr
from ..core import audit, bad_request, forbidden
from ..models import Company, Employee
from ..models_ops import Vehicle
from ..models_ops3 import Lessor
from ..security import Session, Staff
from .contracts_banking import bank_guard
from .travel import can_see_documents

router = APIRouter(prefix="/api/v1", tags=["scan"])

MAX_BYTES = 10 * 1024 * 1024
SIGNATURES = {".pdf": [b"%PDF-"], ".png": [b"\x89PNG\r\n\x1a\n"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"], ".webp": [b"RIFF"]}
_one_at_a_time = asyncio.Semaphore(1)  # OCR is CPU-heavy; queue scans instead of starving the API

Kind = Literal["registration", "travel_document", "contract", "vehicle_renewal", "fleet_card", "corporate_card", "vehicle"]


def _tokens(s: str) -> set[str]:
    return {t for t in re.sub(r"[^a-z ]", " ", s.lower()).split() if len(t) > 1 and t not in {"inc", "corp", "corporation", "co", "the", "of", "and"}}


async def _match_employee(session, principal, name: str) -> Employee | None:
    want = _tokens(name)
    if len(want) < 2:
        return None
    rows = (await session.execute(select(Employee).where(Employee.active.is_(True), Employee.company_id.in_(principal.company_ids)))).scalars().all()
    hits = [e for e in rows if len(want & _tokens(e.name)) >= 2]
    return hits[0] if len(hits) == 1 else None


async def _match_lessor(session, principal, name: str) -> Lessor | None:
    want = _tokens(name)
    if not want:
        return None
    rows = (await session.execute(select(Lessor).where(Lessor.company_id.in_(principal.company_ids)))).scalars().all()
    scored = sorted(((len(want & _tokens(l.name)) / max(len(want), 1), l) for l in rows), key=lambda x: -x[0])
    return scored[0][1] if scored and scored[0][0] >= 0.6 else None


async def _match_company(session, principal, name: str) -> Company | None:
    want = _tokens(name)
    rows = (await session.execute(select(Company).where(Company.id.in_(principal.company_ids)))).scalars().all()
    for c in rows:
        have = _tokens(c.name)
        if have and len(want & have) >= max(1, len(have) - 1):
            return c
    return None


@router.post("/scan")
async def scan(principal: Staff, session: Session, kind: Kind = Form(...), file: UploadFile = File(...)) -> dict:
    if kind == "travel_document" and not can_see_documents(principal):
        raise forbidden("Passport and visa records need explicit access")
    if kind == "corporate_card":
        bank_guard(principal)
    name = (file.filename or "document").lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise bad_request({"message": "The file is larger than 10 MB"})
    if ext not in SIGNATURES:
        raise bad_request({"message": "Upload a PDF or an image (JPG, PNG or WebP) to read it automatically"})
    if not any(data.startswith(s) for s in SIGNATURES[ext]):
        raise bad_request({"message": "The file content does not match its type"})

    async with _one_at_a_time:
        try:
            lines, method = await asyncio.to_thread(ocr.read_lines, data, name)
        except Exception:
            raise bad_request({"message": "This file could not be read. Check that it opens, or enter the details manually."})
        result = ocr.extract(lines, kind)

    fields = {k: {"value": v.value, "confidence": v.confidence} for k, v in result.fields.items()}
    matched: dict[str, dict] = {}
    holder = fields.pop("holder_name", None)
    # Name parts, sex and date of birth: offered to "Add a person" when the holder is not in the list yet.
    person = {k: fields.pop(k)["value"] for k in ("first_name", "middle_name", "last_name", "gender", "birth_date") if k in fields}
    if kind == "travel_document" and holder:
        e = await _match_employee(session, principal, holder["value"])
        if e:
            fields["employee_id"] = {"value": str(e.id), "confidence": min(holder["confidence"], 0.9)}
            matched["employee_id"] = {"label": e.name}
        matched["holder_name"] = {"label": holder["value"]}
    if kind == "registration" and holder:
        c = await _match_company(session, principal, holder["value"])
        matched["holder_name"] = {"label": holder["value"], "company": c.code if c else None}
    if kind == "contract" and "lessor_name" in fields:
        ln = fields.pop("lessor_name")
        lessor = await _match_lessor(session, principal, ln["value"])
        if lessor:
            fields["lessor_id"] = {"value": str(lessor.id), "confidence": ln["confidence"]}
        matched["lessor_name"] = {"label": ln["value"], "matched": bool(lessor)}
    if kind in ("fleet_card", "corporate_card") and holder:
        e = await _match_employee(session, principal, holder["value"])
        target = "assigned_user_id" if kind == "fleet_card" else "custodian_id"
        if e:
            fields[target] = {"value": str(e.id), "confidence": min(holder["confidence"], 0.85)}
        matched["holder_name"] = {"label": holder["value"]}
    if kind == "fleet_card" and "plate_number" in fields:
        plate = fields.pop("plate_number")
        key = plate["value"].replace(" ", "").upper()
        rows = (await session.execute(select(Vehicle).where(Vehicle.company_id.in_(principal.company_ids)))).scalars().all()
        v = next((x for x in rows if (x.plate_number or "").replace(" ", "").upper() == key), None)
        if v:
            fields["vehicle_id"] = {"value": str(v.id), "confidence": plate["confidence"]}
        matched["plate_number"] = {"label": plate["value"], "matched": bool(v)}
    kind_hint = fields.pop("document_kind", None)

    await audit(session, actor_id=principal.id, action="document.scan", entity_type="scan", entity_id=None, entity_ref=kind, data={"method": method, "fields": sorted(fields)})
    await session.commit()
    return {
        "method": method,
        "readable": method != "none",
        "fields": fields,
        "matched": matched,
        "document_kind": kind_hint["value"] if kind_hint else None,
        "person": person if kind == "travel_document" and person.get("first_name") and person.get("last_name") and "employee_id" not in fields else None,
    }
