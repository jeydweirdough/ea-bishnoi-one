"""Phase 2.5 — government registrations, renewals, assignment, BOC cases, calendar, documents, reminders."""

from datetime import date, timedelta


def d(days):
    return (date.today() + timedelta(days=days)).isoformat()


def me_id(user):
    return user.get("/api/v1/me").json()["employee"]["id"]


def reg(user, **kw):
    body = {"document_name": "Mayor's Permit — Makati HQ", "registration_type": "Business Permit", "registration_number": "BP-2026-1188", "registration_date": d(-340), "validity_years": 1}
    body.update(kw)
    return user.post("/api/v1/compliance/registrations", body)


def test_create_and_validate(users):
    admin, carlo = users["admin"], users["carlo"]
    r = reg(admin)
    assert r.status_code == 201, r.text
    x = r.json()
    reg_date = date.today() - timedelta(days=340)
    assert x["reference"].startswith("EA-CMP-") and x["expiry_date"] == reg_date.replace(year=reg_date.year + 1).isoformat()
    assert x["status"] == "for_renewal" and x["days_left"] <= 60  # expiry computed from date + validity
    assert reg(admin, registration_type="Made up").status_code == 422
    assert reg(admin, expiry_date=d(-400)).status_code == 422  # expiry before registration
    assert reg(admin, registration_date=d(-10), validity_years=1, due_date=d(500)).status_code == 422  # due after expiry
    assert reg(carlo).status_code == 403
    assert admin.get("/api/v1/compliance/registrations?group=business-permits").json()["total"] >= 1
    assert admin.get("/api/v1/compliance/registrations?group=sec-gis").json()["total"] == 0


def test_renew_assign_and_status(users):
    admin, bea = users["admin"], users["assistant"]
    x = reg(admin, document_name="SEC Certificate of Registration", registration_type="SEC", registration_date=d(-1800), validity_years=5).json()
    assert x["status"] == "for_renewal"
    assert admin.post(f"/api/v1/compliance/registrations/{x['id']}/renew", {"registration_date": d(1)}).status_code == 422  # future
    assert admin.post(f"/api/v1/compliance/registrations/{x['id']}/renew", {"registration_date": d(0), "expiry_date": d(-5)}).status_code == 422
    r = admin.post(f"/api/v1/compliance/registrations/{x['id']}/renew", {"registration_date": d(0), "registration_number": "CS2026-77", "cost_php": "3500"})
    assert r.status_code == 200 and r.json()["status"] == "ongoing" and r.json()["registration_number"] == "CS2026-77"
    detail = admin.get(f"/api/v1/compliance/registrations/{x['id']}").json()
    assert detail["renewals"][0]["cost_php"] == "3500.00"
    # assignment creates a linked task
    r = admin.post(f"/api/v1/compliance/registrations/{x['id']}/assign-renewal", {"assignee_id": me_id(bea)})
    assert r.status_code == 200 and r.json()["responsible"]["employee_no"] == "EA-0002"
    tasks = bea.get("/api/v1/tasks?view=mine").json()["items"]
    assert any(t["source_module"] == "compliance" and t["source_record_id"] == x["id"] for t in tasks)
    assert admin.post(f"/api/v1/compliance/registrations/{x['id']}/assign-renewal", {"assignee_id": me_id(users["carlo"])}).status_code == 422
    # only Admin terminates / voids
    assert bea.post(f"/api/v1/compliance/registrations/{x['id']}/status", {"status": "void", "reason": "dup"}).status_code == 403
    assert admin.post(f"/api/v1/compliance/registrations/{x['id']}/status", {"status": "terminated", "reason": "Entity dissolved"}).json()["status"] == "terminated"
    assert admin.post(f"/api/v1/compliance/registrations/{x['id']}/renew", {"registration_date": d(0)}).status_code == 409


def test_expiry_sweep_and_reminders(users):
    admin = users["admin"]
    x = reg(admin, document_name="Fire safety inspection certificate", registration_type="Fire Extinguishers", registration_date=d(-400), validity_years=1, responsible_id=me_id(users["assistant"])).json()
    assert x["status"] == "expired"
    y = reg(admin, document_name="Pest control certificate", registration_type="Pest Control", registration_date=d(-360), validity_years=1).json()
    admin.post("/api/v1/admin/escalations/run")
    admin.post("/api/v1/admin/escalations/run")
    notes = admin.get("/api/v1/notifications?page_size=100").json()["items"]
    assert len([n for n in notes if "Pest control certificate" in n["title"]]) == 1
    assert any("Fire safety" in n["title"] for n in users["assistant"].get("/api/v1/notifications?page_size=100").json()["items"])
    due = admin.get("/api/v1/compliance/registrations?due_within=30").json()
    assert any(i["id"] == y["id"] for i in due["items"])


def test_boc_cases(users):
    admin, gio = users["admin"], users["gio"]
    r = admin.post("/api/v1/compliance/boc", {"direction": "import", "description": "Lab reagents from Singapore", "bill_of_lading": "BL-SG-9921", "eta": d(10), "officer_id": me_id(users["assistant"])})
    assert r.status_code == 201
    c = r.json()
    assert c["reference"].startswith("EA-BOC-") and c["status"] == "draft"
    assert admin.post(f"/api/v1/compliance/boc/{c['id']}/events", {}).status_code == 422
    r = admin.post(f"/api/v1/compliance/boc/{c['id']}/events", {"milestone": "lodged", "note": "Entry lodged, E2M ref 55021"})
    assert r.json()["status"] == "lodged" and r.json()["next"] == ["assessment"]
    assert admin.post(f"/api/v1/compliance/boc/{c['id']}/events", {"milestone": "draft"}).status_code == 409  # forward only
    assert admin.post(f"/api/v1/compliance/boc/{c['id']}/events", {"milestone": "cancelled"}).status_code == 422  # reason needed
    assert admin.post(f"/api/v1/compliance/boc/{c['id']}/events", {"note": "Broker asked for commercial invoice"}).status_code == 200
    assert gio.get(f"/api/v1/compliance/boc/{c['id']}").status_code == 403
    cal = admin.get("/api/v1/compliance/calendar?months=2").json()
    assert any(i["module"] == "boc" for i in cal) and any(i["module"] == "compliance" for i in cal)


def test_compliance_documents(users, client):
    admin = users["admin"]
    x = reg(admin, document_name="GIS 2026", registration_type="GIS", registration_date=d(-30), validity_years=1).json()
    up = client.post("/api/v1/attachments", headers=admin.h, data={"owner_type": "registration", "owner_id": str(x["id"])}, files={"file": ("gis.pdf", b"%PDF-1.4\n", "application/pdf")})
    assert up.status_code == 201, up.text
    docs = admin.get("/api/v1/compliance/documents").json()
    assert any(dd["filename"] == "gis.pdf" and dd["owner"]["href"] == f"/registration/{x['id']}" for dd in docs)
    assert users["carlo"].get(up.json()["url"]).status_code == 404
