"""Administrative tasks: assignment, due dates, status, recurrence and completion evidence."""

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from ..core import audit, bad_request, conflict, forbidden, next_reference, not_found, notify, now
from ..models import Attachment, Company, Priority, Recurrence, Role, Task, TaskStatus
from ..security import Session, Staff
from ..serialize import attachment_out, task_out
from ..workflow import employee_or_404

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

STEP = {Recurrence.daily: timedelta(days=1), Recurrence.weekly: timedelta(weeks=1)}


def next_due(d: date, rec: str) -> date:
    if rec == Recurrence.monthly:
        m = d.month % 12 + 1
        y = d.year + (1 if m == 1 else 0)
        for day in (d.day, 30, 29, 28):
            try:
                return date(y, m, day)
            except ValueError:
                continue
    return d + STEP[Recurrence(rec)]


def scope(principal):
    base = Task.company_id.in_(principal.company_ids)
    if principal.is_admin:
        return base
    return base & or_(Task.assignee_id == principal.id, Task.created_by_id == principal.id)


async def load(session, principal, task_id: int) -> Task:
    t = (await session.execute(select(Task).where(Task.id == task_id, scope(principal)).execution_options(populate_existing=True))).scalar_one_or_none()
    if t is None:
        raise not_found()
    return t


class TaskIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(None, max_length=4000)
    company_id: int | None = None
    assignee_id: int | None = None
    due_date: date | None = None
    priority: Priority = Priority.normal
    recurrence: Recurrence = Recurrence.none
    source_module: str | None = Field(None, max_length=40)
    source_record_id: int | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=4000)
    assignee_id: int | None = None
    due_date: date | None = None
    priority: Priority | None = None
    recurrence: Recurrence | None = None
    status: Literal["open", "in_progress", "cancelled"] | None = None


class CompleteIn(BaseModel):
    note: str = Field(..., min_length=1, max_length=4000)


@router.get("")
async def list_tasks(
    principal: Staff,
    session: Session,
    view: Literal["mine", "all", "created"] = "mine",
    status: list[str] = Query(default_factory=list),
    priority: list[str] = Query(default_factory=list),
    overdue: bool = False,
    q: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> dict:
    stmt = select(Task).where(scope(principal))
    if view == "mine":
        stmt = stmt.where(Task.assignee_id == principal.id)
    elif view == "created":
        stmt = stmt.where(Task.created_by_id == principal.id)
    if status:
        stmt = stmt.where(Task.status.in_(status))
    if priority:
        stmt = stmt.where(Task.priority.in_(priority))
    if overdue:
        stmt = stmt.where(Task.due_date < date.today(), Task.status.in_([TaskStatus.open, TaskStatus.in_progress]))
    if q:
        stmt = stmt.where(or_(Task.title.ilike(f"%{q}%"), Task.reference.ilike(f"%{q}%")))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(Task.status.in_([TaskStatus.done, TaskStatus.cancelled]), Task.due_date.is_(None), Task.due_date, Task.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars()
    counts = dict(
        (await session.execute(select(Task.status, func.count()).where(scope(principal), Task.assignee_id == principal.id).group_by(Task.status))).all()
    )
    overdue_n = (
        await session.execute(
            select(func.count()).where(
                scope(principal), Task.assignee_id == principal.id, Task.due_date < date.today(),
                Task.status.in_([TaskStatus.open, TaskStatus.in_progress]),
            )
        )
    ).scalar_one()
    return {
        "items": [task_out(t) for t in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "mine": {"open": counts.get("open", 0), "in_progress": counts.get("in_progress", 0), "done": counts.get("done", 0), "overdue": overdue_n},
    }


async def check_assignee(session, principal, assignee_id: int | None, company_id: int):
    if assignee_id is None:
        return None
    emp = await employee_or_404(session, assignee_id)
    if emp.role not in (Role.admin, Role.assistant):
        raise bad_request({"message": "Tasks can be assigned to Admin or Assistant users only", "fields": {"assignee_id": "Not staff"}})
    if not principal.is_admin and emp.id != principal.id and not principal.can("assign"):
        raise forbidden("Assistants can only assign tasks to themselves unless delegated")
    company = await session.get(Company, company_id)
    if emp.company_id != company_id and company.code not in (emp.company_access or []):
        raise bad_request({"message": "That user has no access to this company", "fields": {"assignee_id": "Wrong company"}})
    return emp


@router.post("", status_code=201)
async def create_task(body: TaskIn, principal: Staff, session: Session) -> dict:
    company_id = body.company_id or principal.employee.company_id
    if company_id not in principal.company_ids:
        raise forbidden("You have no access to that company")
    assignee_id = body.assignee_id if body.assignee_id is not None else (None if principal.is_admin else principal.id)
    emp = await check_assignee(session, principal, assignee_id, company_id)
    if body.recurrence != Recurrence.none and not body.due_date:
        raise bad_request({"message": "Recurring tasks need a due date", "fields": {"due_date": "Required"}})
    t = Task(
        reference=await next_reference(session, "TSK"),
        company_id=company_id,
        title=body.title.strip(),
        description=body.description,
        assignee_id=emp.id if emp else None,
        created_by_id=principal.id,
        due_date=body.due_date,
        priority=body.priority,
        recurrence=body.recurrence,
        source_module=body.source_module,
        source_record_id=body.source_record_id,
    )
    session.add(t)
    await session.flush()
    await audit(session, actor_id=principal.id, action="task.create", entity_type="task", entity_id=t.id, entity_ref=t.reference, company_id=company_id)
    if emp:
        await notify(session, {emp.id}, kind="task_assignment", title=f"New task: {t.title}", link=f"/administration/tasks?task={t.id}", skip=principal.id)
    await session.commit()
    return task_out(await load(session, principal, t.id))


@router.patch("/{task_id}")
async def update_task(task_id: int, body: TaskPatch, principal: Staff, session: Session) -> dict:
    t = await load(session, principal, task_id)
    if t.status in (TaskStatus.done, TaskStatus.cancelled) and body.status is None:
        raise conflict("Completed or cancelled tasks cannot be edited")
    changes = body.model_dump(exclude_unset=True)
    if "assignee_id" in changes and changes["assignee_id"] != t.assignee_id:
        emp = await check_assignee(session, principal, changes["assignee_id"], t.company_id)
        t.assignee_id = emp.id if emp else None
        if emp:
            await notify(session, {emp.id}, kind="task_assignment", title=f"Task assigned: {t.title}", link=f"/administration/tasks?task={t.id}", skip=principal.id)
    if "status" in changes:
        if changes["status"] == "cancelled" and not (principal.is_admin or t.created_by_id == principal.id):
            raise forbidden("Only Admin or the task creator can cancel a task")
        if t.status == TaskStatus.done:
            raise conflict("Completed tasks cannot change status")
        t.status = changes["status"]
    for f in ("title", "description", "due_date", "priority", "recurrence"):
        if f in changes and changes[f] is not None:
            setattr(t, f, changes[f])
    await audit(
        session, actor_id=principal.id, action="task.update", entity_type="task", entity_id=t.id, entity_ref=t.reference,
        company_id=t.company_id, data={k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return task_out(await load(session, principal, t.id))


@router.post("/{task_id}/complete")
async def complete(task_id: int, body: CompleteIn, principal: Staff, session: Session) -> dict:
    t = await load(session, principal, task_id)
    if t.status in (TaskStatus.done, TaskStatus.cancelled):
        raise conflict("This task is already closed")
    if not principal.is_admin and t.assignee_id != principal.id:
        raise forbidden("Only the assignee can complete this task")
    t.status = TaskStatus.done
    t.completion_note = body.note.strip()
    t.completed_at = now()
    nxt = None
    if t.recurrence != Recurrence.none and t.due_date:
        nxt = Task(
            reference=await next_reference(session, "TSK"),
            company_id=t.company_id,
            title=t.title,
            description=t.description,
            assignee_id=t.assignee_id,
            created_by_id=t.created_by_id,
            due_date=next_due(t.due_date, t.recurrence),
            priority=t.priority,
            recurrence=t.recurrence,
            source_module=t.source_module,
            source_record_id=t.source_record_id,
            parent_task_id=t.id,
        )
        session.add(nxt)
    await audit(
        session, actor_id=principal.id, action="task.complete", entity_type="task", entity_id=t.id, entity_ref=t.reference,
        company_id=t.company_id, data={"note": t.completion_note, "next": nxt.reference if nxt else None},
    )
    if t.created_by_id != principal.id:
        await notify(session, {t.created_by_id}, kind="task_assignment", title=f"Task completed: {t.title}", body=t.completion_note[:200], link=f"/administration/tasks?task={t.id}")
    await session.commit()
    return task_out(await load(session, principal, t.id))


@router.get("/{task_id}")
async def get_task(task_id: int, principal: Staff, session: Session) -> dict:
    t = await load(session, principal, task_id)
    atts = (await session.execute(select(Attachment).where(Attachment.owner_type == "task", Attachment.owner_id == t.id))).scalars()
    return {**task_out(t), "attachments": [attachment_out(a) for a in atts]}
