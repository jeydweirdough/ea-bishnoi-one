"""
Request lifecycle and approval routing.

Every status change goes through `move()`, which checks the transition table,
writes the timeline event and the audit event in the same transaction.
"""

from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .core import admin_ids, audit, aware, bad_request, conflict, forbidden, notify, now
from .models import (
    ApprovalDelegation,
    ApprovalStep,
    Employee,
    Priority,
    Request,
    RequestEvent,
    RequestKind,
    RequestStatus as S,
    Role,
    SlaPolicy,
    StepStatus,
    WorkflowTemplate,
)
from .security import Principal

PRIORITY_ORDER = [Priority.low, Priority.normal, Priority.high, Priority.critical]

# Allowed transitions. Anything else is rejected with 409.
TRANSITIONS: dict[str, set[str]] = {
    S.draft: {S.submitted, S.cancelled},
    S.submitted: {S.under_review, S.approved, S.returned, S.rejected, S.cancelled},
    S.under_review: {S.under_review, S.approved, S.returned, S.rejected, S.cancelled},
    S.returned: {S.submitted, S.under_review, S.cancelled},
    S.approved: {S.in_progress, S.cancelled},
    S.in_progress: {S.awaiting_finance, S.fulfilled, S.cancelled},
    S.awaiting_finance: {S.in_progress, S.fulfilled, S.cancelled},
    S.fulfilled: {S.closed, S.in_progress},
    S.rejected: set(),
    S.closed: set(),
    S.cancelled: set(),
}

OPEN = {S.submitted, S.under_review, S.returned, S.approved, S.in_progress, S.awaiting_finance}
IN_APPROVAL = {S.submitted, S.under_review, S.returned}
TERMINAL = {S.rejected, S.closed, S.cancelled}
WITHDRAWABLE = {S.draft, S.submitted, S.under_review, S.returned}

KIND_LABEL = {
    RequestKind.concern: "Concern",
    RequestKind.supplies: "Supply request",
    RequestKind.asset: "Asset request",
    RequestKind.local_purchase: "Local purchase",
    RequestKind.repair: "Repair / maintenance",
    RequestKind.other: "Other request",
}


def link_for(req: Request) -> str:
    return f"/r/{req.id}"


def rank(priority: str | None) -> int:
    try:
        return PRIORITY_ORDER.index(Priority(priority or "normal"))
    except ValueError:
        return 1


# ------------------------------------------------------------------ scope


def scope_filter(principal: Principal):
    """SQL filter for requests the principal may see."""
    own = Request.requester_id == principal.id
    if principal.is_admin:
        return or_(own, Request.company_id.in_(principal.company_ids))
    if principal.role is Role.assistant:
        return or_(own, (Request.assigned_to_id == principal.id) & Request.company_id.in_(principal.company_ids))
    return own


async def approver_scope_ids(session: AsyncSession, principal: Principal) -> set[int]:
    """Employees whose approval steps this principal may act on: self (if granted) and active delegators."""
    ids: set[int] = {principal.id} if principal.approver else set()
    today = date.today()
    rows = await session.execute(
        select(ApprovalDelegation.delegator_id).where(
            ApprovalDelegation.delegate_id == principal.id,
            ApprovalDelegation.revoked.is_(False),
            ApprovalDelegation.starts_on <= today,
            ApprovalDelegation.ends_on >= today,
        )
    )
    ids |= {r for (r,) in rows}
    return ids


def current_step(req: Request) -> ApprovalStep | None:
    return next((s for s in req.steps if s.status in (StepStatus.pending, StepStatus.returned)), None)


async def can_view(session: AsyncSession, principal: Principal, req: Request) -> bool:
    if req.requester_id == principal.id:
        return True
    if principal.is_admin and req.company_id in principal.company_ids:
        return True
    if principal.role is Role.assistant and req.assigned_to_id == principal.id and req.company_id in principal.company_ids:
        return True
    # Approvers see the requests routed to them (current or past steps).
    scope = await approver_scope_ids(session, principal)
    return any(s.approver_id in scope and s.status != StepStatus.waiting for s in req.steps) or any(
        s.decided_by_id == principal.id for s in req.steps
    )


def is_operator(principal: Principal, req: Request) -> bool:
    """May process the request (status changes after approval)."""
    if req.company_id not in principal.company_ids:
        return False
    return principal.is_admin or (principal.role is Role.assistant and req.assigned_to_id == principal.id)


async def allowed_actions(session: AsyncSession, principal: Principal, req: Request) -> list[str]:
    acts: list[str] = []
    owner = req.requester_id == principal.id
    st = req.status
    if owner:
        if st in (S.draft, S.returned):
            acts.append("edit")
        if st == S.draft:
            acts += ["submit", "delete"]
        if st == S.returned:
            acts.append("resubmit")
        if st in WITHDRAWABLE and st != S.draft:
            acts.append("withdraw")
        if st == S.fulfilled:
            acts.append("confirm")
    step = current_step(req)
    if step and step.status == StepStatus.pending and st in (S.submitted, S.under_review) and not owner:
        if step.approver_id in await approver_scope_ids(session, principal):
            acts += ["approve", "reject", "return"]
    if principal.is_staff and req.company_id in principal.company_ids and st not in (S.draft,):
        if principal.can("assign") and st not in TERMINAL:
            acts.append("assign")
        if principal.can("set_priority") and st not in TERMINAL:
            acts.append("set_priority")
        if is_operator(principal, req):
            if st == S.approved:
                acts.append("start")
            if st == S.in_progress:
                acts += ["await_finance", "fulfill"]
            if st == S.awaiting_finance:
                acts += ["finance_done", "fulfill"]
            if st == S.fulfilled:
                acts += ["close", "reopen"]
        if principal.is_admin and st not in TERMINAL:
            acts.append("cancel")
        if principal.is_admin and step and step.status == StepStatus.pending:
            acts.append("reassign_step")
    if st != S.draft or owner:
        acts.append("comment")
    if owner or principal.is_staff:
        if st in (S.draft, S.returned, S.submitted, S.under_review, S.approved, S.in_progress, S.awaiting_finance):
            acts.append("attach")
    return acts


# ------------------------------------------------------------------ events


async def event(
    session: AsyncSession,
    req: Request,
    actor: Principal | None,
    type_: str,
    message: str | None = None,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    internal: bool = False,
) -> None:
    session.add(
        RequestEvent(
            request_id=req.id,
            actor_id=actor.id if actor else None,
            type=type_,
            message=message,
            from_status=from_status,
            to_status=to_status,
            internal=internal,
        )
    )


async def move(session: AsyncSession, req: Request, actor: Principal | None, to: str, type_: str, message: str | None = None):
    frm = req.status
    if to not in TRANSITIONS.get(frm, set()):
        raise conflict(f"A request that is {frm.replace('_', ' ')} cannot move to {to.replace('_', ' ')}")
    req.status = to
    req.version += 1
    if to in (S.closed, S.cancelled, S.rejected):
        req.closed_at = now()
    if actor and actor.id != req.requester_id and req.first_response_at is None and frm != S.draft:
        req.first_response_at = now()
    await event(session, req, actor, type_, message, from_status=frm, to_status=to)
    await audit(
        session,
        actor_id=actor.id if actor else None,
        action=f"request.{type_}",
        entity_type="request",
        entity_id=req.id,
        entity_ref=req.reference,
        company_id=req.company_id,
        data={"from": frm, "to": to, **({"message": message} if message else {})},
    )


# ------------------------------------------------------------------ validation


def validate_for_submit(req: Request) -> None:
    errors: dict[str, str] = {}
    if not req.subject.strip():
        errors["subject"] = "Add a subject"
    if req.kind in (RequestKind.concern, RequestKind.repair, RequestKind.other):
        if not req.category:
            errors["category"] = "Choose a category"
        if not req.description.strip():
            errors["description"] = "Describe the concern"
    if req.kind in (RequestKind.supplies, RequestKind.asset, RequestKind.local_purchase):
        if not req.items:
            errors["items"] = "Add at least one item"
        for i, it in enumerate(req.items):
            if not it.item_name.strip():
                errors[f"items.{i}.item_name"] = "Item name is required"
            if it.quantity < 1:
                errors[f"items.{i}.quantity"] = "Quantity must be at least 1"
            if not it.unit.strip():
                errors[f"items.{i}.unit"] = "Unit is required"
        if not (req.purpose or "").strip():
            errors["purpose"] = "State the purpose"
        if not req.needed_by:
            errors["needed_by"] = "Set the required date"
    if req.needed_by and req.needed_by < date.today():
        errors["needed_by"] = "Required date cannot be in the past"
    if errors:
        raise bad_request({"message": "Some fields need attention", "fields": errors})


# ------------------------------------------------------------------ routing


async def template_for(session: AsyncSession, kind: str) -> WorkflowTemplate | None:
    rows = (await session.execute(select(WorkflowTemplate).where(WorkflowTemplate.active.is_(True)))).scalars().all()
    return next((t for t in rows if kind in (t.kinds or [])), None)


async def apply_sla(session: AsyncSession, req: Request) -> None:
    if not req.submitted_at:
        return
    policy = (await session.execute(select(SlaPolicy).where(SlaPolicy.priority == req.priority))).scalar_one_or_none()
    if policy:
        start = aware(req.submitted_at)
        req.response_due_at = start + timedelta(hours=policy.response_hours)
        req.resolution_due_at = start + timedelta(hours=policy.resolution_hours)


async def build_route(session: AsyncSession, req: Request) -> None:
    """Snapshot the workflow template into approval steps for this request."""
    tpl = await template_for(session, req.kind)
    req.workflow_id = tpl.id if tpl else None
    req.steps.clear()
    await session.flush()
    if not tpl:
        return
    pos = 0
    for stage in tpl.stages:
        if not stage.active:
            continue
        if stage.min_priority and rank(req.priority) < rank(stage.min_priority):
            continue
        approver_id = stage.approver_id
        note = None
        if stage.approver_type == "department_head":
            approver_id = req.department.head_id if req.department else None
            if approver_id is None:
                note = "No department head on record — an Admin must assign an approver"
        step = ApprovalStep(position=pos, name=stage.name, approver_id=approver_id, note=note)
        if approver_id is not None and approver_id == req.requester_id:
            step.status = StepStatus.skipped
            step.note = "Skipped: the requester cannot approve their own request"
        req.steps.append(step)
        pos += 1


async def activate_next(session: AsyncSession, req: Request, actor: Principal | None) -> bool:
    """Open the next waiting step. Returns False when no approval step remains."""
    nxt = next((s for s in req.steps if s.status == StepStatus.waiting), None)
    if nxt is None:
        return False
    nxt.status = StepStatus.pending
    nxt.activated_at = now()
    if nxt.approver_id:
        recipients = {nxt.approver_id}
        rows = await session.execute(
            select(ApprovalDelegation.delegate_id).where(
                ApprovalDelegation.delegator_id == nxt.approver_id,
                ApprovalDelegation.revoked.is_(False),
                ApprovalDelegation.starts_on <= date.today(),
                ApprovalDelegation.ends_on >= date.today(),
            )
        )
        recipients |= {r for (r,) in rows}
        await notify(
            session,
            recipients,
            kind="approval_required",
            title=f"Approval needed: {req.reference}",
            body=f"{req.subject} — {nxt.name}",
            link=link_for(req),
        )
    else:
        await notify(
            session,
            await admin_ids(session, req.company_id),
            kind="approval_required",
            title=f"Approver missing: {req.reference}",
            body=f"Stage “{nxt.name}” has no approver. Assign one to keep the request moving.",
            link=link_for(req),
        )
    return True


async def finish_approval(session: AsyncSession, req: Request, actor: Principal | None) -> None:
    await move(session, req, actor, S.approved, "approved")
    if req.assigned_to_id is None:
        policy = (await session.execute(select(SlaPolicy).where(SlaPolicy.priority == req.priority))).scalar_one_or_none()
        if policy and policy.default_assignee_id:
            req.assigned_to_id = policy.default_assignee_id
            await event(session, req, None, "assigned", "Assigned by priority rule")
            await notify(
                session,
                {policy.default_assignee_id},
                kind="task_assignment",
                title=f"Assigned to you: {req.reference}",
                body=req.subject,
                link=link_for(req),
            )
    await notify(
        session,
        {req.requester_id},
        kind="approval_decision",
        title=f"Approved: {req.reference}",
        body="Executive Admin will now process your request.",
        link=link_for(req),
    )
    await notify(
        session,
        await admin_ids(session, req.company_id) | ({req.assigned_to_id} if req.assigned_to_id else set()),
        kind="new_request",
        title=f"Ready for processing: {req.reference}",
        body=req.subject,
        link=link_for(req),
        skip=actor.id if actor else None,
    )


async def submit(session: AsyncSession, principal: Principal, req: Request, *, resubmit_message: str | None = None):
    validate_for_submit(req)
    if req.status == S.draft:
        req.submitted_at = now()
        await apply_sla(session, req)
        await build_route(session, req)
        await move(session, req, principal, S.submitted, "submitted")
        await notify(
            session,
            await admin_ids(session, req.company_id),
            kind="new_request",
            title=f"New {KIND_LABEL.get(req.kind, 'request').lower()}: {req.reference}",
            body=f"{req.requester.name} — {req.subject}",
            link=link_for(req),
            skip=principal.id,
        )
        if not await activate_next(session, req, principal):
            await finish_approval(session, req, None)
        return
    if req.status == S.returned:
        if not (resubmit_message or "").strip():
            raise bad_request({"message": "Reply to the clarification before resubmitting", "fields": {"message": "Required"}})
        step = next((s for s in req.steps if s.status == StepStatus.returned), None)
        has_progress = any(s.status == StepStatus.approved for s in req.steps)
        await move(session, req, principal, S.under_review if has_progress else S.submitted, "resubmitted", resubmit_message)
        if step:
            step.status = StepStatus.waiting
            step.decided_at = None
            step.decided_by_id = None
            # keep the previous comment in the timeline; clear it on the step
            step.comment = None
            await activate_next(session, req, principal)
        return
    raise conflict("Only drafts and returned requests can be submitted")


async def decide(session: AsyncSession, principal: Principal, req: Request, decision: str, comment: str | None):
    step = current_step(req)
    if req.status not in (S.submitted, S.under_review) or not step or step.status != StepStatus.pending:
        raise conflict("This request is not waiting for an approval decision")
    if req.requester_id == principal.id:
        raise forbidden("You cannot decide on your own request")
    if step.approver_id not in await approver_scope_ids(session, principal):
        raise forbidden("This approval stage is not assigned to you")
    comment = (comment or "").strip() or None
    if decision in ("reject", "return") and not comment:
        raise bad_request({"message": "A reason is required", "fields": {"comment": "Required"}})
    step.decided_at = now()
    step.decided_by_id = principal.id
    step.comment = comment
    on_behalf = step.approver_id != principal.id
    suffix = f" (on behalf of {step.approver.name})" if on_behalf and step.approver else ""
    if decision == "approve":
        step.status = StepStatus.approved
        await event(session, req, principal, "step_approved", f"{step.name}{suffix}" + (f" — {comment}" if comment else ""))
        await audit(
            session,
            actor_id=principal.id,
            action="approval.approve",
            entity_type="request",
            entity_id=req.id,
            entity_ref=req.reference,
            company_id=req.company_id,
            data={"stage": step.name, "on_behalf_of": step.approver_id if on_behalf else None, "comment": comment},
        )
        if await activate_next(session, req, principal):
            await move(session, req, principal, S.under_review, "stage_advanced", f"Moved past {step.name}")
            await notify(
                session,
                {req.requester_id},
                kind="approval_decision",
                title=f"{step.name} approved: {req.reference}",
                body="Your request moved to the next approval stage.",
                link=link_for(req),
            )
        else:
            await finish_approval(session, req, principal)
    elif decision == "reject":
        step.status = StepStatus.rejected
        await move(session, req, principal, S.rejected, "rejected", f"{step.name}: {comment}{suffix}")
        await notify(
            session,
            {req.requester_id},
            kind="approval_decision",
            title=f"Rejected: {req.reference}",
            body=comment,
            link=link_for(req),
        )
    elif decision == "return":
        step.status = StepStatus.returned
        await move(session, req, principal, S.returned, "returned", f"{step.name}: {comment}{suffix}")
        await notify(
            session,
            {req.requester_id},
            kind="approval_decision",
            title=f"Clarification requested: {req.reference}",
            body=comment,
            link=link_for(req),
        )
    else:
        raise bad_request("Unknown decision")


async def run_escalations(session: AsyncSession) -> dict:
    """Overdue monitoring: escalate overdue requests and stalled approval steps once per level."""
    from .models import Task, TaskStatus

    t = now()
    escalated = 0
    policies = {p.priority: p for p in (await session.execute(select(SlaPolicy))).scalars()}
    rows = (await session.execute(select(Request).where(Request.status.in_(list(OPEN))))).scalars().all()
    for req in rows:
        due = aware(req.resolution_due_at)
        if due and t > due:
            every = max(1, (policies.get(req.priority).escalate_every_hours if policies.get(req.priority) else 24))
            level = 1 + int((t - due).total_seconds() // (every * 3600))
            if level > req.escalation_level:
                req.escalation_level = level
                req.escalated_at = t
                await event(session, req, None, "escalated", f"Overdue — escalation level {level}")
                await audit(
                    session,
                    actor_id=None,
                    action="request.escalated",
                    entity_type="request",
                    entity_id=req.id,
                    entity_ref=req.reference,
                    company_id=req.company_id,
                    data={"level": level},
                )
                await notify(
                    session,
                    await admin_ids(session, req.company_id) | ({req.assigned_to_id} if req.assigned_to_id else set()),
                    kind="overdue_notice",
                    title=f"Overdue (level {level}): {req.reference}",
                    body=req.subject,
                    link=link_for(req),
                    dedupe_key=f"overdue:{req.id}:{level}",
                )
                escalated += 1
        step = current_step(req)
        if step and step.status == StepStatus.pending and step.activated_at and step.approver_id:
            pol = policies.get(req.priority)
            if pol and t > aware(step.activated_at) + timedelta(hours=pol.response_hours):
                await notify(
                    session,
                    {step.approver_id},
                    kind="due_date_reminder",
                    title=f"Approval waiting: {req.reference}",
                    body=f"{step.name} has been waiting longer than the {pol.response_hours}h response target.",
                    link=link_for(req),
                    dedupe_key=f"approval-wait:{step.id}",
                )
    today = date.today()
    tasks = (
        await session.execute(select(Task).where(Task.status.in_([TaskStatus.open, TaskStatus.in_progress]), Task.due_date.is_not(None)))
    ).scalars()
    for task in tasks:
        if not task.assignee_id:
            continue
        if task.due_date < today:
            await notify(
                session,
                {task.assignee_id},
                kind="overdue_notice",
                title=f"Task overdue: {task.title}",
                link=f"/administration/tasks?task={task.id}",
                dedupe_key=f"task-overdue:{task.id}",
            )
        elif task.due_date <= today + timedelta(days=1):
            await notify(
                session,
                {task.assignee_id},
                kind="due_date_reminder",
                title=f"Task due {'today' if task.due_date == today else 'tomorrow'}: {task.title}",
                link=f"/administration/tasks?task={task.id}",
                dedupe_key=f"task-due:{task.id}:{task.due_date}",
            )
    from .routers.compliance import compliance_reminders
    from .routers.fleet import fleet_reminders
    from .routers.contracts_banking import contracts_banking_reminders
    from .routers.inventory import inventory_reminders
    from .routers.travel import travel_reminders

    reminders = (
        await fleet_reminders(session)
        + await compliance_reminders(session)
        + await travel_reminders(session)
        + await inventory_reminders(session)
        + await contracts_banking_reminders(session)
    )
    await session.commit()
    return {"escalated": escalated, "reminders": reminders}


async def employee_or_404(session: AsyncSession, employee_id: int) -> Employee:
    emp = await session.get(Employee, employee_id)
    if emp is None or not emp.active:
        raise bad_request({"message": "Unknown employee", "fields": {"employee_id": "Not found"}})
    return emp
