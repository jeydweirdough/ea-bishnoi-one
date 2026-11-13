"""Phase 2.3 — asset registry, assignment, acknowledgement, transfer, repair, receiving."""

from datetime import date, timedelta

from .test_phase21_employee_requests import supplies


def me_id(user):
    return user.get("/api/v1/me").json()["employee"]["id"]


def new_asset(user, **kw):
    body = {"name": "Laptop", "category": "IT equipment", "brand": "Lenovo", "model": "T14", "serial_number": None}
    body.update(kw)
    return user.post("/api/v1/assets", body)


def test_register_and_unique_serial(users):
    admin = users["admin"]
    r = new_asset(admin, serial_number="pf-0001")
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["reference"].startswith("EA-AST-") and a["serial_number"] == "PF-0001" and a["status"] == "in_stock"
    assert new_asset(admin, serial_number="PF-0001").status_code == 409  # case-insensitive duplicate
    assert new_asset(admin, serial_number="PF-0002", quantity=3).status_code == 422  # serialized means one item
    assert new_asset(admin, name="").status_code == 422
    assert new_asset(admin, purchase_date=(date.today() + timedelta(days=2)).isoformat()).status_code == 422
    assert new_asset(users["carlo"]).status_code == 403  # employees cannot register
    listed = admin.get("/api/v1/assets?q=PF-0001").json()
    assert listed["total"] == 1


def test_assign_acknowledge_return(users):
    admin, carlo, eli = users["admin"], users["carlo"], users["eli"]
    a = new_asset(admin, serial_number="PF-0100").json()
    r = admin.post(f"/api/v1/assets/{a['id']}/assign", {"employee_id": me_id(carlo), "note": "Issued for field work"})
    assert r.status_code == 200 and r.json()["status"] == "assigned" and r.json()["awaiting_acknowledgement"]
    assert admin.post(f"/api/v1/assets/{a['id']}/assign", {"employee_id": me_id(eli)}).status_code == 409  # already issued
    # holder sees it, others don't
    assert any(x["id"] == a["id"] for x in carlo.get("/api/v1/me/assets").json())
    assert eli.get(f"/api/v1/assets/{a['id']}").status_code == 404
    assert eli.post(f"/api/v1/assets/{a['id']}/acknowledge").status_code == 404
    d = carlo.get(f"/api/v1/assets/{a['id']}").json()
    assert d["actions"] == ["acknowledge"]
    assert carlo.post(f"/api/v1/assets/{a['id']}/acknowledge").json()["acknowledged_at"]
    assert carlo.post(f"/api/v1/assets/{a['id']}/acknowledge").status_code == 409
    assert carlo.post(f"/api/v1/assets/{a['id']}/return", {"condition": "used"}).status_code == 403
    r = admin.post(f"/api/v1/assets/{a['id']}/return", {"condition": "used", "note": "Resigned"})
    assert r.json()["status"] == "in_stock" and r.json()["holder"] is None and r.json()["condition"] == "used"
    types = [e["type"] for e in r.json()["events"]]
    assert types[:4] == ["returned", "acknowledged", "assigned", "registered"]


def test_transfer_and_cross_company(users):
    admin, gio, bea = users["admin"], users["gio"], users["assistant"]
    a = new_asset(admin, serial_number="PF-0200").json()
    assert admin.post(f"/api/v1/assets/{a['id']}/transfer", {"reason": "x"}).status_code == 422
    assert admin.post(f"/api/v1/assets/{a['id']}/transfer", {"employee_id": me_id(gio), "reason": "x"}).status_code == 422  # 2MG person
    r = admin.post(f"/api/v1/assets/{a['id']}/transfer", {"employee_id": me_id(users["eli"]), "location": "3F IT", "reason": "Replacement unit"})
    assert r.status_code == 200 and r.json()["holder"]["employee_no"] == "EA-0103" and r.json()["location"] == "3F IT"
    # a 2MG asset is invisible to the GPI-only assistant
    m = admin.post("/api/v1/assets", {"name": "Printer", "category": "Office equipment", "company_id": gio.get("/api/v1/me").json()["employee"]["company"]["id"]}).json()
    assert bea.get(f"/api/v1/assets/{m['id']}").status_code == 404
    assert all(x["company"]["code"] == "GPI" for x in bea.get("/api/v1/assets").json()["items"])


def test_repair_cycle_and_retire(users):
    admin, bea = users["admin"], users["assistant"]
    a = new_asset(admin, serial_number="PF-0300").json()
    r = admin.post(f"/api/v1/assets/{a['id']}/repairs", {"issue": "Screen flickers", "provider": "Lenovo service"})
    assert r.status_code == 201
    rep = r.json()
    assert admin.get(f"/api/v1/assets/{a['id']}").json()["status"] == "under_repair"
    assert admin.post(f"/api/v1/assets/{a['id']}/assign", {"employee_id": me_id(users["carlo"])}).status_code == 409
    assert admin.patch(f"/api/v1/asset-repairs/{rep['id']}", {"status": "completed"}).status_code == 422  # outcome required
    r = admin.patch(f"/api/v1/asset-repairs/{rep['id']}", {"status": "completed", "outcome_condition": "used", "cost_php": "2500.50"})
    assert r.json()["status"] == "completed" and r.json()["cost_php"] == "2500.50"
    assert admin.get(f"/api/v1/assets/{a['id']}").json()["status"] == "in_stock"
    assert admin.patch(f"/api/v1/asset-repairs/{rep['id']}", {"status": "in_repair"}).status_code == 409
    assert bea.post(f"/api/v1/assets/{a['id']}/retire", {"reason": "old"}).status_code == 403
    assert admin.post(f"/api/v1/assets/{a['id']}/retire", {"reason": "Beyond economical repair"}).json()["status"] == "retired"
    assert admin.patch(f"/api/v1/assets/{a['id']}", {"name": "x", "category": "Other", "version": 99}).status_code in (409, 422)


def test_receiving_registers_assets(users):
    carlo, admin = users["carlo"], users["admin"]
    body = supplies(submit=True, kind="asset", items=[{"item_name": "Monitor 24in", "quantity": 2, "unit": "unit", "item_category": "IT equipment"}])
    req = carlo.post("/api/v1/requests", body).json()
    # not receivable before approval
    assert admin.post("/api/v1/receiving", {"request_id": req["id"], "lines": [{"item_id": req["items"][0]["id"], "quantity": 1}]}).status_code == 409
    for who in ("dana", "coo", "naresh"):
        assert users[who].post(f"/api/v1/requests/{req['id']}/actions/approve", {}).status_code == 200
    pending = admin.get("/api/v1/receiving/pending").json()
    assert any(p["request"]["id"] == req["id"] for p in pending)
    item = req["items"][0]["id"]
    assert admin.post("/api/v1/receiving", {"request_id": req["id"], "lines": [{"item_id": item, "quantity": 3}]}).status_code == 422  # too many
    bad = admin.post("/api/v1/receiving", {"request_id": req["id"], "lines": [{"item_id": item, "quantity": 2, "register_asset": True, "serial_numbers": ["MN-1"]}]})
    assert bad.status_code == 422  # one serial per unit
    r = admin.post("/api/v1/receiving", {"request_id": req["id"], "delivery_reference": "DR-5512", "lines": [{"item_id": item, "quantity": 1, "register_asset": True, "serial_numbers": ["MN-1"]}]})
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["reference"].startswith("EA-RCV-") and rec["lines"][0]["assets"][0]["serial_number"] == "MN-1"
    d = carlo.get(f"/api/v1/requests/{req['id']}").json()
    assert d["fulfillment_status"] == "Partially received" and d["items"][0]["received_quantity"] == 1
    admin.post("/api/v1/receiving", {"request_id": req["id"], "lines": [{"item_id": item, "quantity": 1, "register_asset": True, "serial_numbers": ["MN-2"]}]})
    d = carlo.get(f"/api/v1/requests/{req['id']}").json()
    assert d["fulfillment_status"] == "Received"
    assert not any(p["request"]["id"] == req["id"] for p in admin.get("/api/v1/receiving/pending").json())
    reg = admin.get("/api/v1/assets?q=MN-").json()
    assert reg["total"] == 2 and all(x["request_id"] == req["id"] for x in reg["items"])
    # Same serial cannot be received twice
    other = carlo.post("/api/v1/requests", body).json()
    for who in ("dana", "coo", "naresh"):
        users[who].post(f"/api/v1/requests/{other['id']}/actions/approve", {})
    dup = admin.post("/api/v1/receiving", {"request_id": other["id"], "lines": [{"item_id": other["items"][0]["id"], "quantity": 1, "register_asset": True, "serial_numbers": ["mn-1"]}]})
    assert dup.status_code == 422
    assert carlo.get("/api/v1/receiving").status_code == 403
