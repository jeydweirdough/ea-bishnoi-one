"""Phase 2.1 — employee concerns, supply requests, attachments, tracking, notifications."""

from datetime import date, timedelta

SOON = (date.today() + timedelta(days=3)).isoformat()


def concern(**kw):
    body = {
        "kind": "concern", "category": "Facilities", "subject": "Aircon leaking in sales area",
        "description": "Water drips onto desks near the window.", "location": "2F Sales", "requested_priority": "high",
    }
    body.update(kw)
    return body


def supplies(**kw):
    body = {
        "kind": "supplies", "subject": "Printer supplies", "purpose": "Monthly reports", "needed_by": SOON,
        "delivery_location": "2F Sales", "items": [
            {"item_name": "Bond paper A4", "quantity": 5, "unit": "ream", "item_category": "Office supplies"},
            {"item_name": "Toner 85A", "quantity": 1, "unit": "pc", "brand": "HP", "model": "CE285A"},
        ],
    }
    body.update(kw)
    return body


def test_unauthenticated_is_rejected(client):
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers={"X-EA-User": "NOPE"}).status_code == 401


def test_draft_edit_submit_concern(users):
    carlo = users["carlo"]
    r = carlo.post("/api/v1/requests", concern(subject="Draft concern"))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "draft" and d["reference"].startswith("EA-REQ-")
    assert {"edit", "submit", "delete"} <= set(d["actions"])
    r = carlo.patch(f"/api/v1/requests/{d['id']}", {**concern(subject="Edited concern"), "version": d["version"]})
    assert r.status_code == 200 and r.json()["subject"] == "Edited concern"
    stale = carlo.patch(f"/api/v1/requests/{d['id']}", {**concern(), "version": d["version"]})
    assert stale.status_code == 409  # optimistic concurrency
    r = carlo.post(f"/api/v1/requests/{d['id']}/actions/submit", {})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "submitted"
    assert [s["name"] for s in d["steps"]] == ["Department Head", "Jasmine", "Ma'am Mira", "Ma'am Malhou"]
    assert d["steps"][0]["approver"]["employee_no"] == "EA-0102"  # Sales head
    assert d["steps"][0]["status"] == "pending"
    assert d["resolution_due_at"] is not None


def test_invalid_submissions(users):
    carlo = users["carlo"]
    assert carlo.post("/api/v1/requests", {"kind": "concern", "subject": "", "description": ""}).status_code == 422
    r = carlo.post("/api/v1/requests", concern(category=None, submit=True))
    assert r.status_code == 422 and "category" in r.json()["detail"]["fields"]
    r = carlo.post("/api/v1/requests", supplies(items=[{"item_name": "", "quantity": 0, "unit": ""}], submit=True))
    fields = r.json()["detail"]["fields"]
    assert r.status_code == 422 and "items.0.item_name" in fields and "items.0.quantity" in fields
    r = carlo.post("/api/v1/requests", supplies(needed_by="2020-01-01", submit=True))
    assert r.status_code == 422 and "needed_by" in r.json()["detail"]["fields"]
    assert carlo.post("/api/v1/requests", concern(kind="nonsense")).status_code == 422


def test_supply_request_multi_item_and_duplicate_guard(users):
    carlo = users["carlo"]
    body = supplies(submit=True, client_token="tok-supply-1")
    a = carlo.post("/api/v1/requests", body)
    b = carlo.post("/api/v1/requests", body)
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["id"] == b.json()["id"]  # same token, same record
    d = a.json()
    assert len(d["items"]) == 2 and d["items"][1]["brand"] == "HP"
    assert [s["name"] for s in d["steps"]] == ["Approval Head", "COO", "Sir Naresh"]
    assert users["eli"].post("/api/v1/requests", body).status_code == 409


def test_repair_category_routes_to_repair_queue(users):
    d = users["carlo"].post("/api/v1/requests", concern(category="Damaged equipment", submit=True)).json()
    assert d["kind"] == "repair"


def test_employee_sees_own_only(users):
    carlo_req = users["carlo"].post("/api/v1/requests", concern(submit=True)).json()
    eli = users["eli"]
    assert eli.get(f"/api/v1/requests/{carlo_req['id']}").status_code == 404
    mine = eli.get("/api/v1/requests").json()
    assert all(r["requester"]["employee_no"] == "EA-0103" for r in mine["items"])
    assert eli.get("/api/v1/requests?scope=all").status_code == 403
    assert eli.get("/api/v1/admin/audit").status_code == 403
    assert eli.get("/api/v1/tasks").status_code == 403


def test_withdraw_and_delete(users):
    carlo = users["carlo"]
    d = carlo.post("/api/v1/requests", concern(submit=True)).json()
    r = carlo.post(f"/api/v1/requests/{d['id']}/actions/withdraw", {"message": "Fixed itself"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert carlo.post(f"/api/v1/requests/{d['id']}/actions/withdraw", {}).status_code == 409
    draft = carlo.post("/api/v1/requests", concern()).json()
    assert carlo.delete(f"/api/v1/requests/{draft['id']}").status_code == 204
    assert carlo.get(f"/api/v1/requests/{draft['id']}").status_code == 404


def _upload(client, user, rid, name, data, ctype):
    return client.post(
        "/api/v1/attachments", headers=user.h,
        data={"owner_type": "request", "owner_id": str(rid), "purpose": "evidence"},
        files={"file": (name, data, ctype)},
    )


def test_attachments(users, client):
    carlo = users["carlo"]
    d = carlo.post("/api/v1/requests", concern()).json()
    pdf = b"%PDF-1.4\n%test\n"
    r = _upload(client, carlo, d["id"], "photo.pdf", pdf, "application/pdf")
    assert r.status_code == 201, r.text
    att = r.json()
    assert _upload(client, carlo, d["id"], "fake.png", b"not a png", "image/png").status_code == 422
    assert _upload(client, carlo, d["id"], "run.exe", b"MZ....", "application/octet-stream").status_code == 422
    assert _upload(client, carlo, d["id"], "e.txt", b"", "text/plain").status_code == 422
    got = carlo.get(att["url"])
    assert got.status_code == 200 and got.content == pdf
    assert users["eli"].get(att["url"]).status_code == 404
    assert _upload(client, users["eli"], d["id"], "x.pdf", pdf, "application/pdf").status_code == 404
    detail = carlo.get(f"/api/v1/requests/{d['id']}").json()
    assert detail["attachments"][0]["filename"] == "photo.pdf"
    assert carlo.delete(att["url"]).status_code == 204


def test_notifications_and_stats(users):
    dana = users["dana"]
    n = dana.get("/api/v1/notifications").json()
    assert n["total"] >= 1 and any(i["kind"] == "approval_required" for i in n["items"])
    first = n["items"][0]
    assert dana.post(f"/api/v1/notifications/{first['id']}/read").json()["read"] is True
    assert users["carlo"].post(f"/api/v1/notifications/{first['id']}/read").status_code == 404
    assert dana.post("/api/v1/notifications/read-all").status_code == 200
    assert dana.get("/api/v1/me").json()["unread_notifications"] == 0
    stats = users["carlo"].get("/api/v1/requests/stats").json()
    assert stats["in_approval"] >= 1 and stats["total"] >= stats["in_approval"]
