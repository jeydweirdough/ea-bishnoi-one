"""Automatic asset serial numbers.

Every asset has a serial number. When the manufacturer's serial isn't entered, the system issues one:
<COMPANY>-<CATEGORY>-<NNNNN>, e.g. GPI-IT-00012. The number never resets, so IDs stay unique for life.
"""

from __future__ import annotations

from sqlalchemy import select

from .models import Company, DocumentSequence
from .models_ops import Asset

CATEGORY_CODE = {
    "IT equipment": "IT",
    "Office equipment": "OE",
    "Furniture": "FN",
    "Appliance": "AP",
    "Mobile device": "MD",
    "Tools": "TL",
    "Other": "OT",
}
MAX_PER_REGISTRATION = 200


def category_code(category: str | None) -> str:
    if category in CATEGORY_CODE:
        return CATEGORY_CODE[category]
    letters = "".join(ch for ch in (category or "") if ch.isalpha()).upper()
    return (letters[:2] or "OT").ljust(2, "X")


async def serial_in_use(session, serial: str, exclude: int | None = None) -> bool:
    stmt = select(Asset.id).where(Asset.serial_number == serial)
    if exclude:
        stmt = stmt.where(Asset.id != exclude)
    return (await session.execute(stmt)).first() is not None


async def next_serial(session, company_id: int, category: str | None) -> str:
    company = await session.get(Company, company_id)
    code = (company.code if company else "EA").upper()
    cat = category_code(category)
    doc_type = f"SN-{code}-{cat}"[:16]
    seq = (
        await session.execute(select(DocumentSequence).where(DocumentSequence.doc_type == doc_type, DocumentSequence.year == 0).with_for_update())
    ).scalar_one_or_none()
    if seq is None:
        seq = DocumentSequence(doc_type=doc_type, year=0, last_value=0)
        session.add(seq)
        await session.flush()
    while True:  # skip a number someone typed in by hand
        seq.last_value += 1
        serial = f"{code}-{cat}-{seq.last_value:05d}"
        if not await serial_in_use(session, serial):
            return serial


async def ensure_serial(session, a: Asset) -> None:
    if not a.serial_number:
        a.serial_number = await next_serial(session, a.company_id, a.category)


def clean_serials(values: list[str] | None) -> list[str]:
    return [s.strip().upper() for s in (values or []) if s and s.strip()]


async def backfill_serials(session) -> int:
    """Give every asset without a serial number an automatic one (assets registered before this existed)."""
    rows = (await session.execute(select(Asset).where(Asset.serial_number.is_(None)).order_by(Asset.id))).scalars().all()
    for a in rows:
        await ensure_serial(session, a)
    if rows:
        await session.commit()
    return len(rows)


async def backfill_issue_refs(session) -> int:
    """Items issued before issuance references existed: the same item handed to the same person on the
    same day becomes one issuance, so it shows as one entry and is acknowledged once."""
    from .core import next_reference

    rows = (await session.execute(select(Asset).where(Asset.holder_id.is_not(None), Asset.issue_ref.is_(None)).order_by(Asset.id))).scalars().all()
    groups: dict[tuple, list[Asset]] = {}
    for a in rows:
        groups.setdefault((a.company_id, a.holder_id, a.name.strip().lower(), a.category, a.date_issued), []).append(a)
    for items in groups.values():
        ref = await next_reference(session, "ISS")
        for a in items:
            a.issue_ref = ref
    if rows:
        await session.commit()
    return len(groups)
