"""Photo proof on transactions: stock movements (issue, use, receive, return, transfer, adjust, write-off)
and asset events (issued, returned, transferred, sent for repair, retired).

A proof photo is an attachment with purpose "proof", re-encoded like item photos (upright, resized,
no hidden camera or GPS data). What the photo shows stays in it: photos taken with the in-app camera
carry a visible stamp (date, time and, if the person allowed it, the location), and the same facts are
kept with the photo so they can be shown next to it. Photos picked from the gallery are marked as
uploaded, so nobody mistakes them for a photo taken on the spot.
"""

import hashlib
import json
import secrets
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from .config import get_settings
from .core import bad_request, not_found
from .models import Attachment
from .security import CurrentPrincipal, Session
from .serialize import iso, person

PROOF = "proof"
MAX_PROOFS = 6
OwnerType = Literal["stock_movement", "asset_event"]

router = APIRouter(prefix="/api/v1", tags=["proofs"])


class ProofMeta(BaseModel):
    source: Literal["camera", "upload"] = "upload"
    taken_at: datetime | None = None
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    accuracy_m: float | None = Field(None, ge=0, le=100000)


def parse_meta(raw: str | None) -> dict:
    if not raw:
        return ProofMeta().model_dump(mode="json")
    try:
        m = ProofMeta.model_validate(json.loads(raw))
    except (ValueError, ValidationError):
        raise bad_request({"message": "The photo details could not be read"})
    if (m.lat is None) != (m.lng is None):
        m.lat = m.lng = m.accuracy_m = None
    return m.model_dump(mode="json")


def proof_out(a: Attachment) -> dict:
    return {
        "id": a.id,
        "thumb": f"/api/v1/proofs/{a.id}?size=thumb",
        "full": f"/api/v1/proofs/{a.id}?size=full",
        "meta": a.meta or {"source": "upload"},
        "uploaded_by": person(a.uploaded_by),
        "uploaded_at": iso(a.uploaded_at),
    }


async def proofs_for(session, owner_type: str, ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    if ids:
        rows = await session.execute(select(Attachment).where(Attachment.owner_type == owner_type, Attachment.owner_id.in_(ids), Attachment.purpose == PROOF).order_by(Attachment.id))
        for a in rows.scalars():
            out.setdefault(a.owner_id, []).append(proof_out(a))
    return out


async def save_proof(session, principal, owner_type: str, owner_id: int, reference: str, file: UploadFile, meta: str | None) -> Attachment:
    from .routers.attachments import storage_dir
    from .routers.photos import process

    if len((await proofs_for(session, owner_type, [owner_id])).get(owner_id, [])) >= MAX_PROOFS:
        raise bad_request({"message": f"At most {MAX_PROOFS} photos per transaction"})
    info = parse_meta(meta)
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if not data:
        raise bad_request({"message": "The photo is empty"})
    if len(data) > limit:
        raise bad_request({"message": f"Photos must be {get_settings().max_upload_mb} MB or smaller"})
    full, thumb = process(data)
    key = secrets.token_hex(16)
    (storage_dir() / key).write_bytes(full)
    (storage_dir() / f"{key}_t").write_bytes(thumb)
    att = Attachment(
        owner_type=owner_type, owner_id=owner_id, filename=f"{reference}-proof.jpg", content_type="image/jpeg", size=len(full),
        storage_key=key, sha256=hashlib.sha256(full).hexdigest(), uploaded_by_id=principal.id, purpose=PROOF, meta=info,
    )
    session.add(att)
    await session.flush()
    await session.refresh(att)
    return att


async def check_read(session, principal, att: Attachment) -> None:
    """Staff of the company see proofs; for asset events, so does the person holding the asset."""
    if att.owner_type == "stock_movement":
        from .models_ops3 import InventoryItem, StockMovement
        from .ops_common import scoped

        if not principal.is_staff:
            raise not_found()
        m = await session.get(StockMovement, att.owner_id)
        if m is None:
            raise not_found()
        await scoped(session, InventoryItem, m.item_id, principal)
    elif att.owner_type == "asset_event":
        from .models_ops import AssetEvent
        from .routers.assets import load_asset_for

        ev = await session.get(AssetEvent, att.owner_id)
        if ev is None:
            raise not_found()
        await load_asset_for(session, principal, ev.asset_id)
    else:
        raise not_found()


@router.get("/proofs/{photo_id}")
async def get_proof(photo_id: int, principal: CurrentPrincipal, session: Session, size: Literal["thumb", "full"] = Query("thumb")):
    from .routers.attachments import storage_dir

    att = await session.get(Attachment, photo_id)
    if att is None or att.purpose != PROOF:
        raise not_found()
    await check_read(session, principal, att)
    path = storage_dir() / (f"{att.storage_key}_t" if size == "thumb" else att.storage_key)
    if not path.exists():
        raise not_found("The stored photo is missing")
    return FileResponse(path, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400"})
