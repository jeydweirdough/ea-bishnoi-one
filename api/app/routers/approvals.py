"""Approval inbox, decision history and approval delegation."""

from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from ..core import audit, bad_request, forbidden, not_found, notify
from ..models import ApprovalDelegation, ApprovalStep, Request, StepStatus
from ..security import CurrentPrincipal, Session
from ..serialize import iso, person, request_summary, step_out
from ..workflow import approver_scope_ids, employee_or_404

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


@router.get("/inbox")
async def inbox(
    principal: CurrentPrincipal,
    session: Session,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    scope = await approver_scope_ids(session, principal)
    if not scope:
        raise forbidden("Approval duties have not been granted")
    stmt = (
        select(ApprovalStep)
        .join(Request, Request.id == ApprovalStep.request_id)
        .where(ApprovalStep.status == StepStatus.pending, ApprovalStep.approver_id.in_(scope), Request.requester_id != principal.id)
    )
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    steps = (
        await session.execute(stmt.order_by(ApprovalStep.activated_at.asc()).offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    items = []
    for s in steps:
        req = await session.get(Request, s.request_id)
        items.append(
            {
                "step": step_out(s),
                "request": request_summary(req),
                "on_behalf_of": person(s.approver) if s.approver_id != principal.id else None,
                "waiting_since": iso(s.activated_at),
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/history")
async def history(principal: CurrentPrincipal, session: Session, limit: int = Query(30, le=100)) -> list[dict]:
    steps = (
        await session.execute(
            select(ApprovalStep).where(ApprovalStep.decided_by_id == principal.id).order_by(ApprovalStep.decided_at.desc()).limit(limit)
        )
    ).scalars().all()
    out = []
    for s in steps:
        req = await session.get(Request, s.request_id)
        out.append({"step": step_out(s), "request": request_summary(req)})
    return out


class DelegationIn(BaseModel):
    delegate_id: int
    starts_on: date
    ends_on: date
    reason: str | None = Field(None, max_length=400)

    @model_validator(mode="after")
    def order(self):
        if self.ends_on < self.starts_on:
            raise ValueError("End date must be on or after the start date")
        return self


def delegation_out(d: ApprovalDelegation) -> dict:
    today = date.today()
    state = "revoked" if d.revoked else "scheduled" if d.starts_on > today else "ended" if d.ends_on < today else "active"
    return {
        "id": d.id,
        "delegator": person(d.delegator),
        "delegate": person(d.delegate),
        "starts_on": d.starts_on.isoformat(),
        "ends_on": d.ends_on.isoformat(),
        "reason": d.reason,
        "state": state,
    }


@router.get("/delegations")
async def delegations(principal: CurrentPrincipal, session: Session) -> dict:
    given = (
        await session.execute(select(ApprovalDelegation).where(ApprovalDelegation.delegator_id == principal.id).order_by(ApprovalDelegation.id.desc()))
    ).scalars()
    received = (
        await session.execute(select(ApprovalDelegation).where(ApprovalDelegation.delegate_id == principal.id).order_by(ApprovalDelegation.id.desc()))
    ).scalars()
    return {"given": [delegation_out(d) for d in given], "received": [delegation_out(d) for d in received]}


@router.post("/delegations", status_code=201)
async def create_delegation(body: DelegationIn, principal: CurrentPrincipal, session: Session) -> dict:
    if not principal.approver:
        raise forbidden("Only users with approval duties can delegate them")
    if body.delegate_id == principal.id:
        raise bad_request({"message": "Choose someone other than yourself", "fields": {"delegate_id": "Invalid"}})
    if body.ends_on < date.today():
        raise bad_request({"message": "The delegation would already have ended", "fields": {"ends_on": "In the past"}})
    delegate = await employee_or_404(session, body.delegate_id)
    d = ApprovalDelegation(delegator_id=principal.id, **body.model_dump())
    session.add(d)
    await session.flush()
    await audit(
        session, actor_id=principal.id, action="approval.delegate", entity_type="delegation", entity_id=d.id,
        company_id=principal.employee.company_id,
        data={"delegate": delegate.employee_no, "starts_on": body.starts_on.isoformat(), "ends_on": body.ends_on.isoformat()},
    )
    await notify(
        session, {delegate.id}, kind="approval_required", title=f"{principal.employee.name} delegated approvals to you",
        body=f"{body.starts_on.isoformat()} to {body.ends_on.isoformat()}", link="/inbox",
    )
    await session.commit()
    await session.refresh(d)
    return delegation_out(await session.get(ApprovalDelegation, d.id))


@router.post("/delegations/{delegation_id}/revoke")
async def revoke(delegation_id: int, principal: CurrentPrincipal, session: Session) -> dict:
    d = await session.get(ApprovalDelegation, delegation_id)
    if d is None or (d.delegator_id != principal.id and not principal.is_admin):
        raise not_found()
    d.revoked = True
    await audit(session, actor_id=principal.id, action="approval.delegate_revoke", entity_type="delegation", entity_id=d.id)
    await session.commit()
    return delegation_out(d)
