"""Response shapes. Kept explicit so sensitive columns never leak by accident."""

from .core import aware, now
from .models import ApprovalStep, Attachment, Employee, Notification, Request, RequestEvent, Task
from .workflow import IN_APPROVAL, KIND_LABEL, OPEN, current_step


def iso(dt):
    dt = aware(dt) if hasattr(dt, "hour") else dt
    return dt.isoformat() if dt else None


def person(e: Employee | None) -> dict | None:
    if e is None:
        return None
    return {
        "id": e.id,
        "employee_no": e.employee_no,
        "name": e.name,
        "designation": e.designation,
        "department": e.department.name if e.department else None,
    }


def step_out(s: ApprovalStep) -> dict:
    return {
        "id": s.id,
        "position": s.position,
        "name": s.name,
        "status": s.status,
        "approver": person(s.approver),
        "decided_by": person(s.decided_by),
        "decided_at": iso(s.decided_at),
        "activated_at": iso(s.activated_at),
        "comment": s.comment,
        "note": s.note,
    }


def sla_state(r: Request) -> str | None:
    if r.status not in OPEN:
        return None
    due = aware(r.resolution_due_at)
    if not due:
        return None
    t = now()
    if t > due:
        return "overdue"
    total = (due - aware(r.submitted_at)).total_seconds() if r.submitted_at else 0
    if total and (due - t).total_seconds() < total * 0.25:
        return "due_soon"
    return "on_track"


def request_summary(r: Request) -> dict:
    step = current_step(r) if r.status in IN_APPROVAL else None
    return {
        "id": r.id,
        "reference": r.reference,
        "kind": r.kind,
        "kind_label": KIND_LABEL.get(r.kind, r.kind),
        "category": r.category,
        "subject": r.subject,
        "status": r.status,
        "priority": r.priority,
        "requested_priority": r.requested_priority,
        "company": {"id": r.company.id, "code": r.company.code, "name": r.company.name},
        "department": {"id": r.department.id, "name": r.department.name} if r.department else None,
        "requester": person(r.requester),
        "assigned_to": person(r.assigned_to),
        "needed_by": r.needed_by.isoformat() if r.needed_by else None,
        "created_at": iso(r.created_at),
        "updated_at": iso(r.updated_at),
        "submitted_at": iso(r.submitted_at),
        "resolution_due_at": iso(r.resolution_due_at),
        "response_due_at": iso(r.response_due_at),
        "sla": sla_state(r),
        "escalation_level": r.escalation_level,
        "item_count": len(r.items),
        "current_step": step_out(step) if step else None,
        "steps_total": len([s for s in r.steps if s.status != "skipped"]),
        "steps_done": len([s for s in r.steps if s.status == "approved"]),
    }


def event_out(e: RequestEvent) -> dict:
    return {
        "id": e.id,
        "type": e.type,
        "message": e.message,
        "from_status": e.from_status,
        "to_status": e.to_status,
        "internal": e.internal,
        "actor": person(e.actor),
        "at": iso(e.at),
    }


def attachment_out(a: Attachment) -> dict:
    return {
        "id": a.id,
        "filename": a.filename,
        "content_type": a.content_type,
        "size": a.size,
        "uploaded_by": person(a.uploaded_by),
        "uploaded_at": iso(a.uploaded_at),
        "purpose": a.purpose,
        "url": f"/api/v1/attachments/{a.id}",
    }


def request_detail(
    r: Request, events: list[RequestEvent], attachments: list[Attachment], actions: list[str], staff: bool, dept_head: Employee | None
) -> dict:
    return {
        **request_summary(r),
        "description": r.description,
        "location": r.location,
        "related_asset": r.related_asset,
        "purpose": r.purpose,
        "delivery_location": r.delivery_location,
        "fulfillment_status": r.fulfillment_status,
        "department_head": person(dept_head),
        "first_response_at": iso(r.first_response_at),
        "closed_at": iso(r.closed_at),
        "version": r.version,
        "items": [
            {
                "id": i.id,
                "item_name": i.item_name,
                "item_category": i.item_category,
                "description": i.description,
                "brand": i.brand,
                "model": i.model,
                "quantity": i.quantity,
                "unit": i.unit,
                "received_quantity": i.received_quantity,
            }
            for i in r.items
        ],
        "steps": [step_out(s) for s in r.steps],
        "timeline": [event_out(e) for e in events if staff or not e.internal],
        "attachments": [attachment_out(a) for a in attachments],
        "actions": actions,
    }


def notification_out(n: Notification) -> dict:
    return {
        "id": n.id,
        "kind": n.kind,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "created_at": iso(n.created_at),
        "read": n.read_at is not None,
    }


def task_out(t: Task) -> dict:
    from datetime import date

    return {
        "id": t.id,
        "reference": t.reference,
        "title": t.title,
        "description": t.description,
        "company": {"id": t.company.id, "code": t.company.code, "name": t.company.name},
        "assignee": person(t.assignee),
        "created_by": person(t.created_by),
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "overdue": bool(t.due_date and t.due_date < date.today() and t.status in ("open", "in_progress")),
        "priority": t.priority,
        "status": t.status,
        "recurrence": t.recurrence,
        "source_module": t.source_module,
        "source_record_id": t.source_record_id,
        "completion_note": t.completion_note,
        "completed_at": iso(t.completed_at),
        "created_at": iso(t.created_at),
    }
