"""Phase 2.7 — contracts (leases, staff houses, lessors, renewals, rent) and banking (cards, cases)."""

from datetime import date, timedelta


def d(days):
    return (date.today() + timedelta(days=days)).isoformat()


def me_id(user):
    return user.get("/api/v1/me").json()["employee"]["id"]


def lessor(user, name="Ayala Land Inc."):
    r = user.post("/api/v1/contracts/lessors", {"name": name, "contact_person": "Ana Lim", "email": "leasing@example.com"})
    return r


def contract(user, lid, **kw):
    body = {"contract_type": "office_lease", "title": "HQ office lease, 12F", "property_name": "Ayala Tower One", "lessor_id": lid, "start_date": d(-300), "end_date": d(45), "monthly_rent_php": "185000.00", "rent_due_day": 5}
    body.update(kw)
    return user.post("/api/v1/contracts", body)


def test_lessors_and_contracts(users):
    admin, carlo = users["admin"], users["carlo"]
    l = lessor(admin).json()
    assert lessor(admin).status_code == 409
    assert admin.post("/api/v1/contracts/lessors", {"name": "X", "email": "not-an-email"}).status_code == 422
    c = contract(admin, l["id"])
    assert c.status_code == 201, c.text
    c = c.json()
    assert c["reference"].startswith("EA-CON-") and c["status"] == "for_renewal"  # within 60-day notice
    assert contract(admin, l["id"], end_date=d(-400)).status_code == 422
    assert contract(carlo, l["id"]).status_code == 403
    assert admin.get("/api/v1/contracts?contract_type=office_lease").json()["summary"]["monthly_rent_php"] == "185000.00"
    lst = admin.get("/api/v1/contracts/lessors").json()
    assert lst[0]["active_contracts"] == 1


def test_renewal_chain_and_terminate(users):
    admin, bea = users["admin"], users["assistant"]
    l = lessor(admin, "Staff House Owner").json()
    c = contract(admin, l["id"], contract_type="staff_house", title="Staff house, Pasig", end_date=d(20), occupants="3 sales staff").json()
    assert admin.post(f"/api/v1/contracts/{c['id']}/renew", {"start_date": d(-400), "end_date": d(400)}).status_code == 422
    n = admin.post(f"/api/v1/contracts/{c['id']}/renew", {"start_date": d(21), "end_date": d(386), "monthly_rent_php": "42000"}).json()
    assert n["status"] == "active" and n["renewed_from_id"] == c["id"] and n["monthly_rent_php"] == "42000.00"
    old = admin.get(f"/api/v1/contracts/{c['id']}").json()
    assert old["status"] == "renewed" and old["renewed_to"]["id"] == n["id"]
    assert admin.post(f"/api/v1/contracts/{c['id']}/renew", {"start_date": d(21), "end_date": d(386)}).status_code == 409
    assert admin.get(f"/api/v1/contracts/{n['id']}").json()["history"][0]["id"] == c["id"]
    assert bea.post(f"/api/v1/contracts/{n['id']}/terminate", {"reason": "x"}).status_code == 403
    assert admin.post(f"/api/v1/contracts/{n['id']}/terminate", {"reason": "Moved out"}).json()["status"] == "terminated"


def test_rent_monitoring(users):
    admin = users["admin"]
    l = lessor(admin, "Rent Lessor").json()
    c = contract(admin, l["id"], title="Warehouse lease", start_date=d(-60), end_date=d(300), monthly_rent_php="50000").json()
    period = date.today().strftime("%Y-%m")
    first = admin.post("/api/v1/contracts/rent/prepare", {"period": period}).json()
    again = admin.post("/api/v1/contracts/rent/prepare", {"period": period}).json()
    assert first["created"] >= 1 and again["created"] == 0  # idempotent
    rent = next(x for x in admin.get(f"/api/v1/contracts/rent/payments?period={period}").json() if x["contract"]["id"] == c["id"])
    assert admin.post(f"/api/v1/contracts/rent/payments/{rent['id']}/paid", {}).status_code == 409
    admin.post(f"/api/v1/contracts/rent/payments/{rent['id']}/send", {})
    assert admin.post(f"/api/v1/contracts/rent/payments/{rent['id']}/paid", {}).status_code == 422
    paid = admin.post(f"/api/v1/contracts/rent/payments/{rent['id']}/paid", {"finance_reference": "CV-2026-3001"}).json()
    assert paid["status"] == "paid"
    admin.post("/api/v1/admin/escalations/run")
    assert any("Office lease ends in" in n["title"] for n in admin.get("/api/v1/notifications?page_size=100").json()["items"])


def test_banking_restricted_and_masked(users):
    admin, bea = users["admin"], users["assistant"]
    assert bea.get("/api/v1/banking/cards").status_code == 403
    body = {"bank": "BPI", "card_last4": "4321 5678 9012 3456", "custodian_id": me_id(admin), "expiry_month": 1, "expiry_year": date.today().year + 1}
    assert admin.post("/api/v1/banking/cards", body).status_code == 422  # full number refused
    body["card_last4"] = "3456"
    assert admin.post("/api/v1/banking/cards", {**body, "notes": "CVV 123"}).status_code == 422
    card = admin.post("/api/v1/banking/cards", body)
    assert card.status_code == 201
    c = card.json()
    assert c["card_masked"] == "•••• 3456" and "card_last4" not in c
    exp = admin.post("/api/v1/banking/cards", {**body, "card_last4": "9999", "expiry_month": date.today().month, "expiry_year": date.today().year}).json()
    assert exp["days_to_expiry"] <= 31
    assert any(x["id"] == exp["id"] for x in admin.get("/api/v1/banking/cards?expiring_within=60").json())
    log = admin.get("/api/v1/admin/audit?action=banking&page_size=200").json()["items"]
    assert any(i["action"] == "banking.cards_view" for i in log) and "4321" not in str(log)


def test_banking_cases(users):
    admin, bea = users["admin"], users["assistant"]
    case = admin.post("/api/v1/banking/cases", {"bank": "BDO", "case_type": "account_application", "subject": "Payroll account for 2MG", "finance_status": "pending"}).json()
    assert case["reference"].startswith("EA-BNK-") and len(case["requirements"]) == 7
    url = f"/api/v1/banking/cases/{case['id']}"
    assert admin.post(f"{url}/action", {"action": "submit"}).status_code == 409  # requirements first
    for i in range(len(case["requirements"])):
        admin.put(f"{url}/requirements", {"index": i, "done": True})
    assert admin.post(f"{url}/action", {"action": "submit"}).json()["status"] == "submitted"
    assert admin.post(f"{url}/action", {"action": "complete"}).status_code == 409  # Finance pending
    admin.post(f"{url}/action", {"action": "finance_send"})
    assert admin.post(f"{url}/action", {"action": "finance_confirm"}).status_code == 422
    admin.post(f"{url}/action", {"action": "finance_confirm", "finance_reference": "FIN-77"})
    assert admin.post(f"{url}/action", {"action": "complete"}).json()["status"] == "completed"
    assert bea.get(url).status_code == 403
    bea_id = me_id(bea)
    admin.put(f"/api/v1/admin/users/{bea_id}/grants", {"can_approve": False, "banking": True, "company_access": ["GPI"]})
    assert bea.get(url).status_code == 200
    admin.put(f"/api/v1/admin/users/{bea_id}/grants", {"can_approve": False, "company_access": ["GPI"]})
