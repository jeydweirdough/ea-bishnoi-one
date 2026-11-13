"""Attachments: validated on type, signature and size; downloads re-check access and are audited."""

import hashlib
import secrets
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from ..config import get_settings
from ..core import audit, bad_request, conflict, forbidden, not_found
from ..models import Attachment, Request, RequestStatus as S, Task
from ..security import CurrentPrincipal, Principal, Session
from ..workflow import allowed_actions, can_view, event

router = APIRouter(prefix="/api/v1", tags=["attachments"])

# extension → (content type, accepted leading signatures; None = text, checked for NUL bytes)
ALLOWED: dict[str, tuple[str, list[bytes] | None]] = {
    ".pdf": ("application/pdf", [b"%PDF-"]),
    ".png": ("image/png", [b"\x89PNG\r\n\x1a\n"]),
    ".jpg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".jpeg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".webp": ("image/webp", [b"RIFF"]),
    ".heic": ("image/heic", [b"\x00\x00\x00"]),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", [b"PK\x03\x04"]),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", [b"PK\x03\x04"]),
    ".csv": ("text/csv", None),
    ".txt": ("text/plain", None),
}


def storage_dir() -> Path:
    d = get_settings().upload_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


async def owner_access(session, principal: Principal, owner_type: str, owner_id: int, *, write: bool):
    """Returns the owning record after checking the caller may read (or write) its attachments."""
    if owner_type == "request":
        req = await session.get(Request, owner_id)
        if req is None or not await can_view(session, principal, req):
            raise not_found()
        if write and "attach" not in await allowed_actions(session, principal, req):
            raise conflict("Attachments can no longer be added to this request")
        return req
    if owner_type == "task":
        task = await session.get(Task, owner_id)
        if task is None or not principal.is_staff or task.company_id not in principal.company_ids:
            raise not_found()
        if not principal.is_admin and principal.id not in (task.assignee_id, task.created_by_id):
            raise not_found()
        return task
    if owner_type == "document":
        from .documents import own_doc

        if write:
            raise conflict("Signed copies are added from the document itself")
        return await own_doc(session, principal, owner_id)
    if owner_type in ("contract", "banking", "inventory_item"):
        from ..models_ops3 import BankingCase, Contract, InventoryItem

        model = {"contract": Contract, "banking": BankingCase, "inventory_item": InventoryItem}[owner_type]
        rec = await session.get(model, owner_id)
        if rec is None or not principal.is_staff or rec.company_id not in principal.company_ids:
            raise not_found()
        if owner_type == "banking" and not (principal.is_admin or principal.delegated("banking")):
            raise not_found()
        return rec
    if owner_type in ("registration", "boc", "flight", "travel_document"):
        from ..models_ops2 import BocCase, FlightBooking, GovRegistration, TravelDocument
        from .travel import can_see_documents

        model = {"registration": GovRegistration, "boc": BocCase, "flight": FlightBooking, "travel_document": TravelDocument}[owner_type]
        rec = await session.get(model, owner_id)
        if rec is None or not principal.is_staff or rec.company_id not in principal.company_ids:
            raise not_found()
        if owner_type == "travel_document" and not can_see_documents(principal):
            raise not_found()
        return rec
    if owner_type in ("asset", "vehicle"):
        from ..models_ops import Asset, Vehicle

        model = Asset if owner_type == "asset" else Vehicle
        rec = await session.get(model, owner_id)
        if rec is None:
            raise not_found()
        staff_ok = principal.is_staff and rec.company_id in principal.company_ids
        holder_ok = owner_type == "asset" and not write and rec.holder_id == principal.id
        if not (staff_ok or holder_ok):
            raise not_found()
        return rec
    raise bad_request("Unknown attachment owner")


def validate(name: str, head: bytes) -> tuple[str, str]:
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED:
        raise bad_request({"message": f"{ext or 'This file type'} is not accepted. Use PDF, images, Word, Excel, CSV or text."})
    ctype, sigs = ALLOWED[ext]
    if sigs is None:
        if b"\x00" in head:
            raise bad_request({"message": "The file content does not match its type"})
    elif not any(head.startswith(s) for s in sigs):
        raise bad_request({"message": "The file content does not match its type"})
    safe = "".join(c for c in Path(name).name if c.isalnum() or c in " ._-()").strip() or f"file{ext}"
    return safe[:200], ctype


@router.post("/attachments", status_code=201)
async def upload(
    principal: CurrentPrincipal,
    session: Session,
    owner_type: Literal["request", "task", "asset", "vehicle", "registration", "boc", "flight", "travel_document", "contract", "banking", "inventory_item"] = Form(...),
    owner_id: int = Form(...),
    purpose: str | None = Form(None),
    file: UploadFile = File(...),
) -> dict:
    owner = await owner_access(session, principal, owner_type, owner_id, write=True)
    settings = get_settings()
    count = (
        await session.execute(
            select(func.count()).where(Attachment.owner_type == owner_type, Attachment.owner_id == owner_id, (Attachment.purpose.is_(None)) | (Attachment.purpose != "photo"))
        )
    ).scalar_one()
    if count >= settings.max_attachments_per_record:
        raise bad_request({"message": f"A record can hold at most {settings.max_attachments_per_record} attachments"})
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) == 0:
        raise bad_request({"message": "The file is empty"})
    if len(data) > limit:
        raise bad_request({"message": f"Files must be {settings.max_upload_mb} MB or smaller"})
    filename, ctype = validate(file.filename or "file", data[:512])
    key = secrets.token_hex(16)
    (storage_dir() / key).write_bytes(data)
    att = Attachment(
        owner_type=owner_type,
        owner_id=owner_id,
        filename=filename,
        content_type=ctype,
        size=len(data),
        storage_key=key,
        sha256=hashlib.sha256(data).hexdigest(),
        uploaded_by_id=principal.id,
        purpose=(purpose or None) and purpose[:60],
    )
    session.add(att)
    company_id = getattr(owner, "company_id", None)
    ref = getattr(owner, "reference", None)
    if owner_type == "request":
        await event(session, owner, principal, "attachment", f"Attached {filename}")
    await audit(
        session, actor_id=principal.id, action="attachment.upload", entity_type=owner_type, entity_id=owner_id,
        entity_ref=ref, company_id=company_id, data={"filename": filename, "size": len(data), "sha256": att.sha256},
    )
    await session.commit()
    from ..serialize import attachment_out

    await session.refresh(att)
    return attachment_out(att)


@router.get("/attachments/{attachment_id}")
async def download(attachment_id: int, principal: CurrentPrincipal, session: Session, inline: bool = False):
    att = await session.get(Attachment, attachment_id)
    if att is None:
        raise not_found()
    owner = await owner_access(session, principal, att.owner_type, att.owner_id, write=False)
    path = storage_dir() / att.storage_key
    if not path.exists():
        raise not_found("The stored file is missing")
    await audit(
        session, actor_id=principal.id, action="attachment.download", entity_type=att.owner_type, entity_id=att.owner_id,
        entity_ref=getattr(owner, "reference", None), company_id=getattr(owner, "company_id", None), data={"attachment": att.id},
    )
    await session.commit()
    disposition = "inline" if inline and att.content_type in ("application/pdf", "image/png", "image/jpeg", "image/webp") else "attachment"
    return FileResponse(
        path, media_type=att.content_type, filename=att.filename, content_disposition_type=disposition,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
async def remove(attachment_id: int, principal: CurrentPrincipal, session: Session) -> None:
    att = await session.get(Attachment, attachment_id)
    if att is None:
        raise not_found()
    owner = await owner_access(session, principal, att.owner_type, att.owner_id, write=False)
    editable = att.owner_type == "request" and owner.status in (S.draft, S.returned)
    if att.uploaded_by_id != principal.id or (att.owner_type == "request" and not editable):
        raise forbidden("Attachments can only be removed by their uploader while the request is editable")
    await audit(
        session, actor_id=principal.id, action="attachment.delete", entity_type=att.owner_type, entity_id=att.owner_id,
        entity_ref=getattr(owner, "reference", None), company_id=getattr(owner, "company_id", None), data={"filename": att.filename},
    )
    if att.owner_type == "request":
        await event(session, owner, principal, "attachment", f"Removed {att.filename}")
    (storage_dir() / att.storage_key).unlink(missing_ok=True)
    await session.delete(att)
    await session.commit()
