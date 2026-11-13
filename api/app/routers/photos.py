"""Item photos for assets, vehicles and stock items: what the item looks like, like a shop listing.

Photos are stored as attachments with purpose "photo". Every upload is re-encoded on the server:
it is turned upright, resized (long side 1600 px), stripped of all metadata (camera, time, GPS
location) and given a 480 px thumbnail. The record keeps its main photo in `photo_id`, so lists
can show it without another query. Viewing a photo is not audited (unlike document downloads):
item photos are not sensitive and lists load many thumbnails. Adding, removing and changing the
main photo are audited.
"""

import hashlib
import io
import secrets
from typing import Literal

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select

from ..config import get_settings
from ..core import audit, bad_request, forbidden, not_found
from ..models import Attachment
from ..security import CurrentPrincipal, Session
from ..serialize import iso, person
from .attachments import owner_access, storage_dir

router = APIRouter(prefix="/api/v1", tags=["photos"])

PURPOSE = "photo"
MAX_PHOTOS = 8
FULL_PX = 1600
THUMB_PX = 480
Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs early

OwnerType = Literal["asset", "vehicle", "inventory_item"]


def not_photo():
    """Filter for the "Files" lists: item photos have their own gallery."""
    return (Attachment.purpose.is_(None)) | (Attachment.purpose != PURPOSE)


def photo_url(photo_id: int | None, size: Literal["thumb", "full"] = "thumb") -> str | None:
    return f"/api/v1/photos/{photo_id}?size={size}" if photo_id else None


def photo_out(a: Attachment, cover_id: int | None) -> dict:
    return {
        "id": a.id,
        "thumb": photo_url(a.id, "thumb"),
        "full": photo_url(a.id, "full"),
        "main": a.id == cover_id,
        "uploaded_by": person(a.uploaded_by),
        "uploaded_at": iso(a.uploaded_at),
    }


def _encode(img: Image.Image, px: int, quality: int) -> bytes:
    copy = img.copy()
    copy.thumbnail((px, px), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    copy.save(out, "JPEG", quality=quality, optimize=True, progressive=True)  # no exif= → no metadata kept
    return out.getvalue()


def process(data: bytes) -> tuple[bytes, bytes]:
    """Upright, resized, metadata-free JPEG plus its thumbnail."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Image.DecompressionBombError:
        raise bad_request({"message": "This photo is too large. Take it again at a normal camera setting."})
    except (UnidentifiedImageError, OSError):
        raise bad_request({"message": "This file isn't a photo we can read. Use a JPEG, PNG or WebP image."})
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        img = bg
    elif img.mode == "L":
        img = img.convert("RGB")
    return _encode(img, FULL_PX, 82), _encode(img, THUMB_PX, 78)


async def _photos(session, owner_type: str, owner_id: int) -> list[Attachment]:
    stmt = select(Attachment).where(Attachment.owner_type == owner_type, Attachment.owner_id == owner_id, Attachment.purpose == PURPOSE)
    return list((await session.execute(stmt.order_by(Attachment.id))).scalars())


async def _photo(session, principal, photo_id: int, *, write: bool) -> tuple[Attachment, object]:
    att = await session.get(Attachment, photo_id)
    if att is None or att.purpose != PURPOSE:
        raise not_found()
    owner = await owner_access(session, principal, att.owner_type, att.owner_id, write=write)
    return att, owner


def _need_staff(principal) -> None:
    if not principal.is_staff:
        raise forbidden("Only Admin and Assistants can change item photos")


@router.get("/photos")
async def list_photos(principal: CurrentPrincipal, session: Session, owner_type: OwnerType, owner_id: int) -> list[dict]:
    owner = await owner_access(session, principal, owner_type, owner_id, write=False)
    return [photo_out(a, owner.photo_id) for a in await _photos(session, owner_type, owner_id)]


@router.post("/photos", status_code=201)
async def add_photo(
    principal: CurrentPrincipal,
    session: Session,
    owner_type: OwnerType = Form(...),
    owner_id: int = Form(...),
    file: UploadFile = File(...),
) -> dict:
    _need_staff(principal)
    owner = await owner_access(session, principal, owner_type, owner_id, write=True)
    if len(await _photos(session, owner_type, owner_id)) >= MAX_PHOTOS:
        raise bad_request({"message": f"An item can have at most {MAX_PHOTOS} photos. Remove one first."})
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
        owner_type=owner_type, owner_id=owner_id, filename=f"{getattr(owner, 'reference', None) or getattr(owner, 'item_code', 'item')}-photo.jpg",
        content_type="image/jpeg", size=len(full), storage_key=key, sha256=hashlib.sha256(full).hexdigest(),
        uploaded_by_id=principal.id, purpose=PURPOSE,
    )
    session.add(att)
    await session.flush()
    if owner.photo_id is None:
        owner.photo_id = att.id
    await audit(
        session, actor_id=principal.id, action="photo.add", entity_type=owner_type, entity_id=owner_id,
        entity_ref=getattr(owner, "reference", None), company_id=getattr(owner, "company_id", None), data={"photo": att.id, "size": len(full)},
    )
    await session.commit()
    await session.refresh(att)
    return photo_out(att, owner.photo_id)


@router.get("/photos/{photo_id}")
async def get_photo(photo_id: int, principal: CurrentPrincipal, session: Session, size: Literal["thumb", "full"] = Query("thumb")):
    att, _ = await _photo(session, principal, photo_id, write=False)
    path = storage_dir() / (f"{att.storage_key}_t" if size == "thumb" else att.storage_key)
    if not path.exists():
        raise not_found("The stored photo is missing")
    # A photo id never changes content, so the browser may keep it (privately) for a day.
    return FileResponse(path, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400"})


@router.post("/photos/{photo_id}/main")
async def set_main(photo_id: int, principal: CurrentPrincipal, session: Session) -> dict:
    _need_staff(principal)
    att, owner = await _photo(session, principal, photo_id, write=True)
    owner.photo_id = att.id
    await audit(
        session, actor_id=principal.id, action="photo.main", entity_type=att.owner_type, entity_id=att.owner_id,
        entity_ref=getattr(owner, "reference", None), company_id=getattr(owner, "company_id", None), data={"photo": att.id},
    )
    await session.commit()
    return {"main": att.id}


@router.delete("/photos/{photo_id}", status_code=204)
async def remove_photo(photo_id: int, principal: CurrentPrincipal, session: Session) -> None:
    _need_staff(principal)
    att, owner = await _photo(session, principal, photo_id, write=True)
    if owner.photo_id == att.id:
        rest = [a for a in await _photos(session, att.owner_type, att.owner_id) if a.id != att.id]
        owner.photo_id = rest[0].id if rest else None
    await audit(
        session, actor_id=principal.id, action="photo.remove", entity_type=att.owner_type, entity_id=att.owner_id,
        entity_ref=getattr(owner, "reference", None), company_id=getattr(owner, "company_id", None), data={"photo": att.id},
    )
    for k in (att.storage_key, f"{att.storage_key}_t"):
        (storage_dir() / k).unlink(missing_ok=True)
    await session.delete(att)
    await session.commit()
