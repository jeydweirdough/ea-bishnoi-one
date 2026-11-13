"""Phase 2.2 — approval routing, decisions, delegation, assignment, priority, SLA, tasks, audit."""

import asyncio
from datetime import date, datetime, timedelta, timezone

from .test_phase21_employee_requests import concern, supplies


def approve(user, rid, **kw):
    return user.post(f"/api/v1/requests/{rid}/actions/approve", kw or {})


def me_id(user):
    return user.get("/api/v1/me").json()["employee"]["id"]


def test_full_concern_chain_to_closed(users):
    carlo, admin = users["carlo"], users["admin"]
    rid = carlo.post("/api/v1/requests", concern(submit=True)).json()["id"]
    assert approve(users["jasmine"], rid).status_code == 404  # not routed to them yet, so not visible
    assert approve(admin, rid).status_code == 403  # Admin is not automatically an approver
    assert approve(carlo, rid).status_code == 403  # own request
    inbox = users["dana"].get("/api/v1/approvals/inbox").json()
    assert any(i["request"]["id"] == rid for i in inbox["items"])
    r = approve(users["dana"], rid, message="OK")
    assert r.status_code == 200 and r.json()["status"] == "under_review"
    for who in ("jasmine", "mira"):
        assert approve(users[who], rid).json()["status"] == "under_review"
    assert approve(users["malhou"], rid).json()["status"] == "approved"
    assert approve(users["malhou"], rid).status_code in (403, 409)
    assert admin.post(f"/api/v1/requests/{rid}/actions/fulfill", {"message": "x"}).status_code == 403
    assert admin.post(f"/api/v1/requests/{rid}/actions/start", {}).json()["status"] == "in_progress"
    assert admin.post(f"/api/v1/requests/{rid}/actions/fulfill", {}).status_code == 422
    assert admin.post(f"/api/v1/requests/{rid}/actions/fulfill", {"message": "Aircon serviced"}).json()["status"] == "fulfilled"
    r = carlo.post(f"/api/v1/requests/{rid}/actions/confirm", {"message": "Thanks"})
    assert r.json()["status"] == "closed"
    types = [e["type"] for e in r.json()["timeline"]]
    assert {"submitted", "approved", "fulfilled", "confirmed"} <= set(types)


def test_finance_handoff(users):
    admin = users["admin"]
    rid = users["carlo"].post("/api/v1/requests", supplies(submit=True, requested_priority="high")).json()["id"]
    for who in ("dana", "coo", "naresh"):
        approve(users[who], rid)
    admin.post(f"/api/v1/requests/{rid}/actions/start", {})
    assert admin.post(f"/api/v1/requests/{rid}/actions/await_finance", {}).json()["status"] == "awaiting_finance"
    assert admin.post(f"/api/v1/requests/{rid}/actions/close", {}).status_code == 403  # invalid from awaiting_finance
    assert admin.post(f"/api/v1/requests/{rid}/actions/finance_done", {}).json()["status"] == "in_progress"


def test_return_for_correction_and_resubmit(users):
    carlo = users["carlo"]
    rid = carlo.post("/api/v1/requests", supplies(submit=True)).json()["id"]
    assert users["dana"].post(f"/api/v1/requests/{rid}/actions/return", {}).status_code == 422
    r = users["dana"].post(f"/api/v1/requests/{rid}/actions/return", {"message": "Which toner model?"})
    assert r.json()["status"] == "returned"
    assert "resubmit" in carlo.get(f"/api/v1/requests/{rid}").json()["actions"]
    assert carlo.post(f"/api/v1/requests/{rid}/actions/resubmit", {}).status_code == 422
    d = carlo.post(f"/api/v1/requests/{rid}/actions/resubmit", {"message": "CE285A, as listed"}).json()
    assert d["status"] == "submitted" and d["steps"][0]["status"] == "pending"
    assert approve(users["dana"], rid).json()["status"] == "under_review"
    r = users["coo"].post(f"/api/v1/requests/{rid}/actions/reject", {"message": "Use existing stock"})
    assert r.json()["status"] == "rejected"
    assert carlo.post(f"/api/v1/requests/{rid}/actions/withdraw", {}).status_code == 409


def test_delegation(users):
    carlo, jasmine, assistant = users["carlo"], users["jasmine"], users["assistant"]
    today = date.today().isoformat()
    later = (date.today() + timedelta(days=5)).isoformat()
    assert carlo.post("/api/v1/approvals/delegations", {"delegate_id": 1, "starts_on": today, "ends_on": later}).status_code == 403
    me = assistant.get("/api/v1/me").json()
    assert me["approver"] is False and me["navigation"]["approval_inbox"] is False
    r = jasmine.post("/api/v1/approvals/delegations", {"delegate_id": me["employee"]["id"], "starts_on": today, "ends_on": later, "reason": "Leave"})
    assert r.status_code == 201 and r.json()["state"] == "active"
    rid = carlo.post("/api/v1/requests", concern(submit=True)).json()["id"]
    approve(users["dana"], rid)
    assert assistant.get("/api/v1/me").json()["navigation"]["approval_inbox"] is True
    r = approve(assistant, rid, message="Covering for Jasmine")
    assert r.status_code == 200
    step = r.json()["steps"][1]
    assert step["status"] == "approved" and step["decided_by"]["employee_no"] == "EA-0002"
    did = jasmine.get("/api/v1/approvals/delegations").json()["given"][0]["id"]
    assert jasmine.post(f"/api/v1/approvals/delegations/{did}/revoke").json()["state"] == "revoked"
    assert assistant.get("/api/v1/approvals/inbox").status_code == 403


def test_missing_department_head_is_flagged_and_reassignable(users):
    bea, admin = users["assistant"], users["admin"]  # Executive Admin dept has no head on record
    d = bea.post("/api/v1/requests", concern(submit=True)).json()
    step = d["steps"][0]
    assert step["approver"] is None and "department head" in step["note"]
    assert "reassign_step" in admin.get(f"/api/v1/requests/{d['id']}").json()["actions"]
    ivy = admin.get("/api/v1/directory?approvers=true&q=Ivy").json()[0]
    r = admin.post(f"/api/v1/requests/{d['id']}/actions/reassign_step", {"step_id": step["id"], "approver_id": ivy["id"]})
    assert r.status_code == 200 and r.json()["steps"][0]["approver"]["name"] == "Ivy Tan"
    carlo_id = me_id(users["carlo"])
    bad = admin.post(f"/api/v1/requests/{d['id']}/actions/reassign_step", {"step_id": step["id"], "approver_id": carlo_id})
    assert bad.status_code == 422  # no approval grant


def test_assignment_priority_and_scopes(users):
    carlo, admin, bea = users["carlo"], users["admin"], users["assistant"]
    rid = carlo.post("/api/v1/requests", concern(submit=True, requested_priority="normal")).json()["id"]
    assert bea.get(f"/api/v1/requests/{rid}").status_code == 404  # not assigned yet
    bea_id = me_id(bea)
    r = admin.post(f"/api/v1/requests/{rid}/actions/assign", {"assignee_id": bea_id})
    assert r.status_code == 200 and r.json()["assigned_to"]["employee_no"] == "EA-0002"
    d = bea.get(f"/api/v1/requests/{rid}").json()
    assert "assign" not in d["actions"] and "set_priority" not in d["actions"]
    assert bea.post(f"/api/v1/requests/{rid}/actions/set_priority", {"priority": "critical"}).status_code == 403
    assert admin.post(f"/api/v1/requests/{rid}/actions/assign", {"assignee_id": me_id(carlo)}).status_code == 422
    before = admin.get(f"/api/v1/requests/{rid}").json()["resolution_due_at"]
    r = admin.post(f"/api/v1/requests/{rid}/actions/set_priority", {"priority": "critical", "message": "Safety"})
    assert r.json()["priority"] == "critical" and r.json()["resolution_due_at"] < before
    admin.put(f"/api/v1/admin/users/{bea_id}/grants", {"can_approve": False, "assign": True, "set_priority": True, "company_access": ["GPI"]})
    assert "set_priority" in bea.get(f"/api/v1/requests/{rid}").json()["actions"]
    queue = bea.get("/api/v1/requests?scope=all").json()
    for i in queue["items"]:
        assert i["requester"]["employee_no"] == "EA-0002" or i["assigned_to"]["employee_no"] == "EA-0002"
    admin.put(f"/api/v1/admin/users/{bea_id}/grants", {"can_approve": False, "assign": False, "set_priority": False, "company_access": ["GPI"]})


def test_cross_company_isolation(users):
    gio, bea, admin = users["gio"], users["assistant"], users["admin"]
    d = gio.post("/api/v1/requests", concern(submit=True)).json()
    assert d["company"]["code"] == "2MG" and d["steps"][0]["approver"]["employee_no"] == "EA-0302"
    assert admin.get(f"/api/v1/requests/{d['id']}").status_code == 200
    assert admin.post(f"/api/v1/requests/{d['id']}/actions/assign", {"assignee_id": me_id(bea)}).status_code == 422
    assert bea.get(f"/api/v1/requests/{d['id']}").status_code == 404
    assert bea.get("/api/v1/requests?scope=all&company=2MG").json()["total"] == 0
    assert approve(users["dana"], d["id"]).status_code == 404  # other company's approver cannot even see it


def test_workflow_configuration(users):
    admin, bea = users["admin"], users["assistant"]
    items = next(w for w in admin.get("/api/v1/admin/workflows").json() if w["key"] == "items")
    stages = [
        {"name": s["name"], "approver_type": s["approver_type"], "approver_id": s["approver"]["id"] if s["approver"] else None}
        for s in items["stages"]
    ]
    body = {"name": items["name"], "description": items["description"], "kinds": items["kinds"], "active": True}
    url = f"/api/v1/admin/workflows/{items['id']}"
    assert bea.put(url, {**body, "stages": stages}).status_code == 403
    no_grant = stages + [{"name": "X", "approver_type": "employee", "approver_id": me_id(users["carlo"])}]
    assert admin.put(url, {**body, "stages": no_grant}).status_code == 422
    assert admin.put(url, {**body, "kinds": items["kinds"] + ["concern"], "stages": stages}).status_code == 422
    stages[2]["min_priority"] = "high"
    r = admin.put(url, {**body, "stages": stages})
    assert r.status_code == 200 and r.json()["stages"][2]["min_priority"] == "high"
    d = users["carlo"].post("/api/v1/requests", supplies(submit=True, requested_priority="normal")).json()
    assert [s["name"] for s in d["steps"]] == ["Approval Head", "COO"]
    approve(users["dana"], d["id"])
    assert approve(users["coo"], d["id"]).json()["status"] == "approved"
    stages[2]["min_priority"] = None
    assert admin.put(url, {**body, "stages": stages}).status_code == 200


def test_sla_and_escalation(users, client):
    admin = users["admin"]
    assert users["assistant"].put("/api/v1/admin/sla/low", {"response_hours": 1, "resolution_hours": 2}).status_code == 403
    assert admin.put("/api/v1/admin/sla/low", {"response_hours": 5, "resolution_hours": 2}).status_code == 422
    d = users["carlo"].post("/api/v1/requests", concern(submit=True, requested_priority="low")).json()

    from app.db import session_factory
    from app.models import Request

    async def backdate():
        async with session_factory()() as s:
            req = await s.get(Request, d["id"])
            req.resolution_due_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
            await s.commit()

    client.portal.call(backdate)  # on the app's own event loop (Postgres connections are bound to it)
    r = admin.post("/api/v1/admin/escalations/run")
    assert r.status_code == 200 and r.json()["escalated"] >= 1
    detail = admin.get(f"/api/v1/requests/{d['id']}").json()
    assert detail["escalation_level"] >= 1 and detail["sla"] == "overdue"
    assert admin.post("/api/v1/admin/escalations/run").json()["escalated"] == 0  # once per level
    n = admin.get("/api/v1/notifications?unread=true&page_size=100").json()
    assert len([i for i in n["items"] if i["kind"] == "overdue_notice" and d["reference"] in i["title"]]) == 1
    assert admin.get("/api/v1/requests?scope=all&sla=overdue").json()["total"] >= 1


def test_tasks(users):
    admin, bea, carlo = users["admin"], users["assistant"], users["carlo"]
    due = (date.today() + timedelta(days=7)).isoformat()
    r = admin.post("/api/v1/tasks", {"title": "Collect permits", "assignee_id": me_id(bea), "due_date": due, "recurrence": "monthly", "priority": "high"})
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["reference"].startswith("EA-TSK-")
    assert carlo.post("/api/v1/tasks", {"title": "x"}).status_code == 403
    assert bea.post("/api/v1/tasks", {"title": "x", "assignee_id": me_id(admin)}).status_code == 403
    assert admin.post("/api/v1/tasks", {"title": "x", "recurrence": "weekly"}).status_code == 422
    own = bea.post("/api/v1/tasks", {"title": "Follow up Finance"}).json()
    assert own["assignee"]["employee_no"] == "EA-0002"
    assert bea.post(f"/api/v1/tasks/{t['id']}/complete", {"note": ""}).status_code == 422
    assert bea.post(f"/api/v1/tasks/{t['id']}/complete", {"note": "Permits filed"}).json()["status"] == "done"
    mine = bea.get("/api/v1/tasks?view=mine").json()
    nxt = [i for i in mine["items"] if i["title"] == "Collect permits" and i["status"] == "open"]
    assert len(nxt) == 1 and nxt[0]["due_date"] > due  # recurrence spawned the next one
    assert bea.post(f"/api/v1/tasks/{t['id']}/complete", {"note": "again"}).status_code == 409
    assert bea.patch(f"/api/v1/tasks/{own['id']}", {"status": "in_progress"}).json()["status"] == "in_progress"
    assert users["gio"].get(f"/api/v1/tasks/{t['id']}").status_code == 403


def test_audit_is_recorded_and_read_only(users, client):
    admin = users["admin"]
    log = admin.get("/api/v1/admin/audit?page_size=200").json()
    actions = {i["action"] for i in log["items"]}
    assert {"request.create", "request.submitted", "approval.approve", "attachment.upload", "task.create"} <= actions
    assert users["assistant"].get("/api/v1/admin/audit").status_code == 403
    first = log["items"][0]["id"]
    assert client.delete(f"/api/v1/admin/audit/{first}", headers=admin.h).status_code in (404, 405)
    assert client.put(f"/api/v1/admin/audit/{first}", headers=admin.h, json={}).status_code in (404, 405)
