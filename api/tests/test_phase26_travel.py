"""Phase 2.6 — flights with configurable requirements, hotels, passports and visas (sensitive)."""

from datetime import date, timedelta


def d(days):
    return (date.today() + timedelta(days=days)).isoformat()


def me_id(user):
    return user.get("/api/v1/me").json()["employee"]["id"]


def flight(user, passenger, **kw):
    body = {"passenger_id": passenger, "travel_type": "international", "origin": "MNL", "destination": "Singapore", "destination_country": "Singapore", "departure_date": d(14), "return_date": d(18), "purpose": "Supplier audit"}
    body.update(kw)
    return user.post("/api/v1/travel/flights", body)


def test_flight_lifecycle_and_checklist(users):
    admin, carlo = users["admin"], users["carlo"]
    pid = me_id(carlo)
    assert flight(admin, pid, destination_country=None).status_code == 422
    assert flight(admin, pid, return_date=d(10)).status_code == 422
    assert flight(admin, pid, departure_date=d(-1), return_date=None).status_code == 422
    assert flight(carlo, pid).status_code == 403
    f = flight(admin, pid).json()
    assert f["reference"].startswith("EA-TRV-") and f["checklist_total"] == 4 and f["checklist_done"] == 0
    assert admin.post(f"/api/v1/travel/flights/{f['id']}/status", {"status": "ticketed"}).status_code == 409
    assert admin.post(f"/api/v1/travel/flights/{f['id']}/status", {"status": "booked"}).status_code == 422  # PNR needed
    assert admin.post(f"/api/v1/travel/flights/{f['id']}/status", {"status": "booked", "booking_reference": "x7kq2p", "airline": "PAL"}).json()["booking_reference"] == "X7KQ2P"
    blocked = admin.post(f"/api/v1/travel/flights/{f['id']}/status", {"status": "ticketed"})
    assert blocked.status_code == 409 and "Passport" in blocked.json()["detail"]
    for item in f["checklist"]:
        admin.put(f"/api/v1/travel/flights/{f['id']}/checklist/{item['id']}", {"done": True})
    t = admin.post(f"/api/v1/travel/flights/{f['id']}/status", {"status": "ticketed"})
    assert t.status_code == 200 and t.json()["status"] == "ticketed"
    assert any("Flight ticketed" in n["title"] for n in carlo.get("/api/v1/notifications?page_size=50").json()["items"])
    mine = carlo.get("/api/v1/travel/me").json()
    assert mine["flights"][0]["id"] == f["id"]
    dom = flight(admin, pid, travel_type="domestic", destination="Cebu", destination_country=None).json()
    assert dom["destination_country"] == "Philippines" and dom["checklist_total"] == 1


def test_requirements_are_configurable(users):
    admin, bea = users["admin"], users["assistant"]
    assert bea.post("/api/v1/travel/requirements", {"travel_type": "international", "name": "x"}).status_code == 403
    r = admin.post("/api/v1/travel/requirements", {"travel_type": "international", "country": "Japan", "name": "Japan visa (visa-required nationality)"})
    assert r.status_code == 201
    pid = me_id(users["eli"])
    jp = flight(admin, pid, destination="Tokyo", destination_country="japan").json()
    sg = flight(admin, pid).json()
    assert jp["checklist_total"] == sg["checklist_total"] + 1
    admin.patch(f"/api/v1/travel/requirements/{r.json()['id']}", {"travel_type": "international", "country": "Japan", "name": "Japan visa", "active": False})
    jp2 = admin.get(f"/api/v1/travel/flights/{jp['id']}").json()
    assert jp2["checklist_total"] == sg["checklist_total"]


def test_hotels(users):
    admin = users["admin"]
    pid = me_id(users["carlo"])
    f = flight(admin, pid).json()
    assert admin.post("/api/v1/travel/hotels", {"guest_id": pid, "hotel": "Hotel A", "destination": "Singapore", "check_in": d(14), "check_out": d(14)}).status_code == 422
    h = admin.post("/api/v1/travel/hotels", {"guest_id": pid, "flight_id": f["id"], "hotel": "Hotel A", "destination": "Singapore", "check_in": d(14), "check_out": d(18)}).json()
    assert h["nights"] == 4 and h["reference"].startswith("EA-HTL-")
    assert admin.post(f"/api/v1/travel/hotels/{h['id']}/status", {"status": "booked"}).status_code == 422
    assert admin.post(f"/api/v1/travel/hotels/{h['id']}/status", {"status": "booked", "booking_reference": "CONF-8812"}).json()["status"] == "booked"
    assert admin.post(f"/api/v1/travel/hotels/{h['id']}/status", {"status": "booked"}).status_code == 409
    assert admin.get(f"/api/v1/travel/flights/{f['id']}").json()["hotels"][0]["id"] == h["id"]


def test_passports_and_visas_are_restricted(users, client):
    admin, bea, carlo = users["admin"], users["assistant"], users["carlo"]
    pid = me_id(carlo)
    body = {"employee_id": pid, "doc_type": "passport", "country": "Philippines", "number_last4": "P1234567A", "expiry_date": d(60)}
    assert admin.post("/api/v1/travel/documents", body).status_code == 422  # only last 4 accepted
    body["number_last4"] = "567A"
    p = admin.post("/api/v1/travel/documents", body)
    assert p.status_code == 201
    doc = p.json()
    assert doc["number_masked"] == "•••• 567A" and "567A" not in str({k: v for k, v in doc.items() if k != "number_masked"})
    assert admin.post("/api/v1/travel/documents", {**body, "doc_type": "visa"}).status_code == 422  # visa type needed
    v = admin.post("/api/v1/travel/documents", {"employee_id": pid, "doc_type": "visa", "holder_kind": "expat", "visa_type": "9(g) work visa", "country": "Philippines", "expiry_date": d(20)}).json()
    # Assistant without explicit delegation cannot see them
    assert bea.get("/api/v1/travel/documents").status_code == 403
    assert bea.get(f"/api/v1/travel/documents/{doc['id']}").status_code == 403
    assert client.post("/api/v1/attachments", headers=bea.h, data={"owner_type": "travel_document", "owner_id": str(doc["id"])}, files={"file": ("p.pdf", b"%PDF-1.4\n", "application/pdf")}).status_code == 404
    bea_id = me_id(bea)
    admin.put(f"/api/v1/admin/users/{bea_id}/grants", {"can_approve": False, "travel_documents": True, "company_access": ["GPI"]})
    assert bea.get("/api/v1/travel/documents?holder_kind=expat").json()[0]["id"] == v["id"]
    admin.put(f"/api/v1/admin/users/{bea_id}/grants", {"can_approve": False, "company_access": ["GPI"]})
    # every read is audited, and the audit never holds the number
    log = admin.get("/api/v1/admin/audit?action=travel&page_size=200").json()["items"]
    assert any(i["action"] == "travel.documents_view" for i in log)
    assert "567A" not in str(log)
    # holder sees own; expiry reminders reach Admin and the holder
    assert len(carlo.get("/api/v1/travel/me").json()["documents"]) == 2
    admin.post("/api/v1/admin/escalations/run")
    assert any("9(g) work visa" in n["title"] for n in admin.get("/api/v1/notifications?page_size=100").json()["items"])
    assert any("Your passport" in n["title"] for n in carlo.get("/api/v1/notifications?page_size=100").json()["items"])
    assert admin.get(f"/api/v1/travel/documents/{v['id']}").json()["status"] == "for_renewal"
    assert len(admin.get("/api/v1/travel/documents?expiring_within=30").json()) >= 1
