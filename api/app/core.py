"""Cross-cutting helpers: audit trail, notifications, document numbering, errors."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditEvent, DocumentSequence, Employee, Notification, Role


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def bad_request(detail: str | dict) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def forbidden(detail: str = "You do not have permission for this action") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail)


def not_found(detail: str = "Record not found") -> HTTPException:
    # Used for records outside the caller's scope too, so existence is not leaked.
    return HTTPException(status.HTTP_404_NOT_FOUND, detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail)


async def audit(
    session: AsyncSession,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    entity_ref: str | None = None,
    company_id: int | None = None,
    data: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_ref=entity_ref,
            company_id=company_id,
            data=data or {},
        )
    )


async def notify(
    session: AsyncSession,
    recipient_ids: set[int] | list[int],
    *,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    dedupe_key: str | None = None,
    skip: int | None = None,
) -> None:
    for rid in set(recipient_ids):
        if rid is None or rid == skip:
            continue
        key = f"{dedupe_key}:{rid}" if dedupe_key else None
        if key and (await session.execute(select(Notification.id).where(Notification.dedupe_key == key))).first():
            continue
        session.add(Notification(recipient_id=rid, kind=kind, title=title, body=body, link=link, dedupe_key=key))


async def admin_ids(session: AsyncSession, company_id: int) -> set[int]:
    rows = (await session.execute(select(Employee).where(Employee.role == Role.admin, Employee.active.is_(True)))).scalars()
    from .models import Company

    code = (await session.execute(select(Company.code).where(Company.id == company_id))).scalar_one_or_none()
    return {e.id for e in rows if e.company_id == company_id or (code and code in (e.company_access or []))}


async def next_reference(session: AsyncSession, doc_type: str) -> str:
    """EA-<TYPE>-<YEAR>-<NNNN>. Row-locked on Postgres; SQLite serialises writers."""
    year = now().year
    seq = (
        await session.execute(
            select(DocumentSequence)
            .where(DocumentSequence.doc_type == doc_type, DocumentSequence.year == year)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if seq is None:
        seq = DocumentSequence(doc_type=doc_type, year=year, last_value=0)
        session.add(seq)
        await session.flush()
    seq.last_value += 1
    return f"EA-{doc_type}-{year}-{seq.last_value:04d}"
