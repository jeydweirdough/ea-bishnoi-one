"""Phase 2.4 — vehicles, renewals, services, fleet cards, RFID and Finance hand-offs."""

from datetime import date, timedelta


def soon(days):
    return (date.today() + timedelta(days=days)).isoformat()


def vehicle(user, **kw):
    body = {"vehicle_type": "Van", "make": "Toyota", "model": "Hiace", "year_model": 2022, "plate_number": "nab 1234", "registration_renewal_date": soon(5), "insurance_expiry_date": soon(40), "next_pms_date": soon(20), "odometer_km": 15000}
    body.update(kw)
    return user.post("/api/v1/fleet/vehicles", body)


def test_vehicle_registry(users):
    admin, carlo = users["admin"], users["carlo"]
    r = vehicle(admin)
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["plate_number"] == "NAB 1234" and v["due"]["registration"] == 5 and v["reference"].startswith("EA-FLT-")
    assert vehicle(admin).status_code == 409  # duplicate plate
    assert vehicle(admin, plate_number=None, conduction_sticker=None).status_code == 422
    assert vehicle(admin, plate_number="ZZZ 9", year_model=1900).status_code == 422
    assert vehicle(carlo, plate_number="ABC 1").status_code == 403
    assert admin.get("/api/v1/fleet/vehicles?due_within=10").json()["total"] >= 1
    stale = admin.patch(f"/api/v1/fleet/vehicles/{v['id']}", {**{k: v[k] for k in ("vehicle_type", "make", "model", "plate_number")}, "version": 99})
    assert stale.status_code == 409
    assert users["assistant"].patch(f"/api/v1/fleet/vehicles/{v['id']}", {"vehicle_type": "Van", "make": "Toyota", "model": "Hiace", "plate_number": "NAB 1234", "status": "disposed", "version": v["version"]}).status_code == 403


def test_renewals_and_reminders(users):
    admin = users["admin"]
    v = vehicle(admin, plate_number="RNW 1").json()
    assert admin.post(f"/api/v1/fleet/vehicles/{v['id']}/renew", {"kind": "registration", "new_date": date.today().isoformat()}).status_code == 422
    r = admin.post(f"/api/v1/fleet/vehicles/{v['id']}/renew", {"kind": "registration", "new_date": soon(370), "reference": "OR-778"})
    assert r.status_code == 200 and r.json()["due"]["registration"] == 370
    detail = admin.get(f"/api/v1/fleet/vehicles/{v['id']}").json()
    assert detail["renewals"][0]["reference"] == "OR-778"
    due = admin.get("/api/v1/fleet/renewals?within=45").json()
    assert any(x["vehicle"]["id"] == v["id"] and x["kind"] == "insurance" for x in due)
    admin.post("/api/v1/admin/escalations/run")
    first = admin.get("/api/v1/notifications?page_size=100").json()["items"]
    warn = [n for n in first if n["kind"] == "renewal_warning" and "NAB 1234" in n["title"] and "Registration" in n["title"]]
    assert len(warn) == 1
    admin.post("/api/v1/admin/escalations/run")
    again = admin.get("/api/v1/notifications?page_size=100").json()["items"]
    assert len([n for n in again if n["kind"] == "renewal_warning" and "NAB 1234" in n["title"] and "Registration" in n["title"]]) == 1


def test_services(users):
    admin = users["admin"]
    v = vehicle(admin, plate_number="SVC 1").json()
    r = admin.post(f"/api/v1/fleet/vehicles/{v['id']}/services", {"kind": "pms", "service_date": date.today().isoformat(), "description": "10k PMS", "cost_php": "4500", "odometer_km": 15500, "next_service_date": soon(180)})
    assert r.status_code == 201 and r.json()["reference"].startswith("EA-MNT-")
    after = admin.get(f"/api/v1/fleet/vehicles/{v['id']}").json()
    assert after["odometer_km"] == 15500 and after["due"]["pms"] == 180
    assert admin.post(f"/api/v1/fleet/vehicles/{v['id']}/services", {"kind": "repair", "service_date": date.today().isoformat(), "description": "x", "odometer_km": 100}).status_code == 422
    sched = admin.post(f"/api/v1/fleet/vehicles/{v['id']}/services", {"kind": "repair", "status": "scheduled", "service_date": soon(2), "description": "Aircon repair"}).json()
    assert admin.get(f"/api/v1/fleet/vehicles/{v['id']}").json()["status"] == "under_maintenance"
    done = admin.post(f"/api/v1/fleet/services/{sched['id']}/complete", {"cost_php": "8000"})
    assert done.json()["status"] == "done"
    assert admin.get(f"/api/v1/fleet/vehicles/{v['id']}").json()["status"] == "active"
    assert admin.post(f"/api/v1/fleet/services/{sched['id']}/complete", {}).status_code == 409


def test_fleet_cards_masking_and_default(users):
    admin, bea = users["admin"], users["assistant"]
    v = vehicle(admin, plate_number="CRD 1").json()
    assert admin.post("/api/v1/fleet/cards", {"vehicle_id": v["id"], "card_number_last4": "7012 3456 7890 1234"}).status_code == 422  # full numbers refused
    r = admin.post("/api/v1/fleet/cards", {"vehicle_id": v["id"], "card_number_last4": "1234", "fuel_type": "Diesel"})
    assert r.status_code == 201
    c = r.json()
    assert c["card_masked"] == "•••• 1234" and c["configured_amount_php"] == "10000.00"
    assert "card_last4" not in c and "1234" not in str({k: c[k] for k in c if k != "card_masked"})
    assert bea.put("/api/v1/fleet/settings/default-card-limit", {"amount_php": "12000"}).status_code == 403
    assert admin.put("/api/v1/fleet/settings/default-card-limit", {"amount_php": "12000"}).status_code == 200
    c2 = admin.post("/api/v1/fleet/cards", {"vehicle_id": v["id"], "card_number_last4": "9999"}).json()
    assert c2["configured_amount_php"] == "12000.00"
    admin.put("/api/v1/fleet/settings/default-card-limit", {"amount_php": "10000"})


def test_finance_handoffs(users):
    admin = users["admin"]
    v = vehicle(admin, plate_number="FIN 1").json()
    card = admin.post("/api/v1/fleet/cards", {"vehicle_id": v["id"], "card_number_last4": "5555"}).json()
    assert admin.post("/api/v1/fleet/finance", {"kind": "fleet_billing", "fleet_card_id": card["id"], "amount_php": "9800"}).status_code == 422  # period required
    f = admin.post("/api/v1/fleet/finance", {"kind": "fleet_billing", "fleet_card_id": card["id"], "period": "2026-10", "amount_php": "9800.75", "send": True}).json()
    assert f["status"] == "sent" and f["amount_php"] == "9800.75"
    assert admin.post("/api/v1/fleet/finance", {"kind": "fleet_billing", "fleet_card_id": card["id"], "period": "2026-10", "amount_php": "1"}).status_code == 409  # duplicate month
    assert admin.post(f"/api/v1/fleet/finance/{f['id']}/paid", {}).status_code == 422  # Finance reference required
    paid = admin.post(f"/api/v1/fleet/finance/{f['id']}/paid", {"finance_reference": "CV-2026-1188"}).json()
    assert paid["status"] == "paid" and paid["finance_reference"] == "CV-2026-1188"
    assert admin.post(f"/api/v1/fleet/finance/{f['id']}/cancel", {"reason": "x"}).status_code == 409

    acct = admin.post("/api/v1/fleet/rfid", {"vehicle_id": v["id"], "provider": "Autosweep", "account_reference": "AS-889900", "balance_php": "200"}).json()
    assert acct["low"] is True
    assert admin.post("/api/v1/fleet/rfid", {"provider": "Autosweep", "account_reference": "AS-889900"}).status_code == 409
    reload = admin.post("/api/v1/fleet/finance", {"kind": "rfid_reload", "rfid_account_id": acct["id"], "amount_php": "1000"}).json()
    assert reload["status"] == "draft"
    admin.post(f"/api/v1/fleet/finance/{reload['id']}/send", {})
    admin.post(f"/api/v1/fleet/finance/{reload['id']}/paid", {"finance_reference": "CV-2026-1190"})
    acct2 = next(a for a in admin.get("/api/v1/fleet/rfid").json() if a["id"] == acct["id"])
    assert acct2["balance_php"] == "1200.00" and acct2["low"] is False
    log = admin.get("/api/v1/admin/audit?action=fleet&page_size=200").json()
    assert {"fleet.finance_paid", "fleet.rfid_reloaded", "fleet.card_create"} <= {i["action"] for i in log["items"]}
    assert users["carlo"].get("/api/v1/fleet/finance").status_code == 403
    assert users["gio"].get("/api/v1/fleet/vehicles").status_code == 403
