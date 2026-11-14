"""Phase 2.3a — equipment inventory: items, movements, reservations from requests, reorders, counts."""

from datetime import date, timedelta

from .test_phase21_employee_requests import supplies


def me_id(user):
    return user.get("/api/v1/me").json()["employee"]["id"]


def item(user, **kw):
    body = {"item_code": "tnr-85a", "name": "HP 85A toner", "category": "Supplies", "unit": "pc", "location": "HQ stockroom", "opening_quantity": 10, "reorder_level": 3, "reorder_quantity": 10, "unit_cost_php": "2450.00"}
    body.update(kw)
    return user.post("/api/v1/inventory/items", body)


def test_items_and_permissions(users):
    admin, bea, carlo = users["admin"], users["assistant"], users["carlo"]
    r = item(admin)
    assert r.status_code == 201, r.text
    i = r.json()
    assert i["item_code"] == "TNR-85A" and i["on_hand"] == 10 and i["value_php"] == "24500.00"
    assert item(admin).status_code == 409  # same code, same location
    assert item(admin, location="2F cabinet", opening_quantity=0).status_code == 201  # same code, other location is fine
    assert item(admin, category="Food").status_code == 422
    assert item(bea, item_code="X1", location="A").status_code == 403  # set-up needs inventory control
    assert carlo.get("/api/v1/inventory/items").status_code == 403
    assert bea.get("/api/v1/inventory/items").json()["summary"]["lines"] >= 2


def test_movements_rules(users):
    admin, bea = users["admin"], users["assistant"]
    i = item(admin, item_code="MOUSE", name="USB mouse", category="Equipment", opening_quantity=5, reorder_level=2).json()
    url = f"/api/v1/inventory/items/{i['id']}/move"
    assert admin.post(url, {"kind": "issue", "quantity": 9, "issued_to_id": me_id(users["eli"])}).status_code == 409  # never negative
    assert admin.post(url, {"kind": "issue", "quantity": 1}).status_code == 422  # recipient needed
    d = admin.post(url, {"kind": "issue", "quantity": 2, "issued_to_id": me_id(users["eli"])}).json()
    assert d["on_hand"] == 3
    assert admin.post(url, {"kind": "adjustment", "quantity": 1, "direction": "remove"}).status_code == 422  # reason
    assert bea.post(url, {"kind": "adjustment", "quantity": 1, "reason": "x"}).status_code == 403
    assert bea.post(url, {"kind": "write_off", "quantity": 1, "reason": "broken"}).status_code == 403
    d = admin.post(url, {"kind": "write_off", "quantity": 1, "reason": "Cable cut"}).json()
    assert d["on_hand"] == 2
    t = bea.post(url, {"kind": "transfer", "quantity": 1, "to_location": "Cebu office"}).json()
    assert t["on_hand"] == 1 and t["other_locations"][0]["location"] == "Cebu office" and t["other_locations"][0]["on_hand"] == 1
    kinds = [m["kind"] for m in t["movements"]]
    assert kinds[:3] == ["transfer_out", "write_off", "issue"]
    admin.post("/api/v1/admin/escalations/run")
    assert any("Low stock: USB mouse" in n["title"] for n in admin.get("/api/v1/notifications?page_size=100").json()["items"])


def test_reserve_and_issue_from_request(users):
    admin, carlo = users["admin"], users["carlo"]
    stock = item(admin, item_code="PAPER-A4", name="Bond paper A4", unit="ream", opening_quantity=20, reorder_level=5).json()
    req = carlo.post("/api/v1/requests", supplies(submit=True, items=[{"item_name": "Bond paper A4", "quantity": 5, "unit": "ream"}])).json()
    for who in ("dana", "coo", "naresh"):
        users[who].post(f"/api/v1/requests/{req['id']}/actions/approve", {})
    todo = admin.get("/api/v1/inventory/requests").json()
    line = next(x for x in todo if x["request"]["id"] == req["id"])["lines"][0]
    assert any(m["id"] == stock["id"] for m in line["matches"])
    assert admin.post("/api/v1/inventory/reserve", {"request_item_id": line["id"], "item_id": stock["id"], "quantity": 6}).status_code == 409  # more than asked
    r = admin.post("/api/v1/inventory/reserve", {"request_item_id": line["id"], "item_id": stock["id"], "quantity": 5})
    assert r.status_code == 201
    s = admin.get(f"/api/v1/inventory/items/{stock['id']}").json()
    assert s["reserved"] == 5 and s["available"] == 15
    # reserved stock can't be written off
    assert admin.post(f"/api/v1/inventory/items/{stock['id']}/move", {"kind": "write_off", "quantity": 16, "reason": "x"}).status_code == 409
    assert admin.post(f"/api/v1/inventory/reservations/{r.json()['id']}/issue").json()["status"] == "issued"
    s = admin.get(f"/api/v1/inventory/items/{stock['id']}").json()
    assert s["on_hand"] == 15 and s["reserved"] == 0
    d = carlo.get(f"/api/v1/requests/{req['id']}").json()
    assert d["fulfillment_status"] == "Issued from stock" and d["items"][0]["received_quantity"] == 5


def test_serialized_issue_creates_assets(users):
    admin, eli = users["admin"], users["eli"]
    i = item(admin, item_code="MON-24", name="Monitor 24in", category="Equipment", opening_quantity=3, serialized_on_issue=True).json()
    admin.post(f"/api/v1/inventory/items/{i['id']}/move", {"kind": "issue", "quantity": 2, "issued_to_id": me_id(eli)})
    mine = eli.get("/api/v1/me/assets").json()
    assert len([a for a in mine if a["name"] == "Monitor 24in"]) == 2


def test_reorder_and_counts(users):
    admin, bea = users["admin"], users["assistant"]
    low = item(admin, item_code="INK-BLK", name="Ink black", opening_quantity=1, reorder_level=4, reorder_quantity=12).json()
    r = admin.post("/api/v1/inventory/reorder", {"item_ids": [low["id"]]})
    assert r.status_code == 201
    draft = admin.get(f"/api/v1/requests/{r.json()['request_id']}").json()
    assert draft["status"] == "draft" and draft["kind"] == "local_purchase" and draft["items"][0]["quantity"] == 12
    c = bea.post("/api/v1/inventory/counts", {"location": "HQ stockroom"}).json()
    assert c["reference"].startswith("EA-CNT-") and c["total"] >= 2
    assert bea.post(f"/api/v1/inventory/counts/{c['id']}/submit").status_code == 422  # not counted
    lines = [{"item_id": l["item_id"], "counted": l["expected"] - 1 if l["item_code"] == "INK-BLK" else l["expected"]} for l in c["lines"]]
    lines[0]["counted"] = -1
    assert bea.put(f"/api/v1/inventory/counts/{c['id']}", {"lines": lines}).status_code == 422
    lines[0]["counted"] = c["lines"][0]["expected"] - (1 if c["lines"][0]["item_code"] == "INK-BLK" else 0)
    saved = bea.put(f"/api/v1/inventory/counts/{c['id']}", {"lines": lines}).json()
    assert saved["variances"] == 1
    assert bea.post(f"/api/v1/inventory/counts/{c['id']}/submit").json()["status"] == "submitted"
    assert bea.post(f"/api/v1/inventory/counts/{c['id']}/post").status_code == 403
    posted = admin.post(f"/api/v1/inventory/counts/{c['id']}/post").json()
    assert posted["status"] == "posted"
    assert admin.get(f"/api/v1/inventory/items/{low['id']}").json()["on_hand"] == 0


def test_receiving_into_stock(users):
    admin, carlo = users["admin"], users["carlo"]
    stock = item(admin, item_code="STAPLER", name="Stapler", category="Supplies", opening_quantity=0, location="Receiving bay").json()
    req = carlo.post("/api/v1/requests", supplies(submit=True, items=[{"item_name": "Stapler", "quantity": 4, "unit": "pc"}])).json()
    for who in ("dana", "coo", "naresh"):
        users[who].post(f"/api/v1/requests/{req['id']}/actions/approve", {})
    r = admin.post("/api/v1/receiving", {"request_id": req["id"], "lines": [{"item_id": req["items"][0]["id"], "quantity": 4, "inventory_item_id": stock["id"]}]})
    assert r.status_code == 201, r.text
    assert admin.get(f"/api/v1/inventory/items/{stock['id']}").json()["on_hand"] == 4


def test_consumables_get_codes_and_record_use(users):
    admin, bea = users["admin"], users["assistant"]
    a = item(admin, item_code="", name="Dishwashing liquid", category="Consumables", unit="bottle", opening_quantity=6, reorder_level=2).json()
    b = item(admin, item_code=None, name="Trash bags", category="Consumables", unit="pack", opening_quantity=3).json()
    assert a["item_code"].startswith("GPI-CS-") and b["item_code"].startswith("GPI-CS-") and a["item_code"] != b["item_code"]
    url = f"/api/v1/inventory/items/{a['id']}/move"
    assert admin.post(url, {"kind": "use", "quantity": 1}).status_code == 422  # say what it was used for
    assert admin.post(url, {"kind": "use", "quantity": 9, "reason": "Pantry"}).status_code == 409  # never below zero
    d = bea.post(url, {"kind": "use", "quantity": 4, "reason": "Pantry, week 46"}).json()
    assert d["on_hand"] == 2 and d["low"] and d["movements"][0]["kind"] == "use" and d["movements"][0]["quantity"] == -4
    # Clearing the code on edit keeps it.
    e = admin.patch(f"/api/v1/inventory/items/{a['id']}", {**{k: d[k] for k in ("name", "category", "unit", "location", "reorder_level", "reorder_quantity")}, "item_code": None, "version": d["version"]})
    assert e.status_code == 200 and e.json()["item_code"] == a["item_code"]


def test_proof_of_receipt_photos(users):
    import io

    from PIL import Image

    from .test_item_photos import jpeg_with_gps

    admin, bea, carlo = users["admin"], users["assistant"], users["carlo"]
    i = item(admin, item_code=None, name="Alcohol 70%", category="Consumables", unit="bottle", opening_quantity=12).json()
    assert i["opening_movement_id"]
    up = lambda user, mid, data=None: user.c.post(f"/api/v1/inventory/movements/{mid}/proof", headers=user.h, files={"file": ("dr.jpg", data or jpeg_with_gps(), "image/jpeg")})
    r = up(admin, i["opening_movement_id"])
    assert r.status_code == 201, r.text
    # Receiving more: proof is optional, then added to that movement.
    d = bea.post(f"/api/v1/inventory/items/{i['id']}/move", {"kind": "stock_in", "quantity": 6, "reason": "DR 1182"}).json()
    got = d["movements"][0]
    assert got["kind"] == "stock_in" and got["proofs"] == []
    assert up(bea, got["id"]).status_code == 201
    d = bea.get(f"/api/v1/inventory/items/{i['id']}").json()
    assert len(d["movements"][0]["proofs"]) == 1 and len(d["movements"][1]["proofs"]) == 1
    # Stored clean: no camera or GPS data.
    full = admin.c.get(d["movements"][0]["proofs"][0]["full"], headers=admin.h)
    assert full.status_code == 200 and len(Image.open(io.BytesIO(full.content)).getexif()) == 0
    # Only stock that came in takes proof; at most 4; staff only; not a photo → refused.
    used = bea.post(f"/api/v1/inventory/items/{i['id']}/move", {"kind": "use", "quantity": 1, "reason": "Clinic"}).json()["movements"][0]
    assert up(bea, used["id"]).status_code == 422
    for _ in range(3):
        assert up(bea, got["id"]).status_code == 201
    assert up(bea, got["id"]).status_code == 422
    assert up(carlo, got["id"]).status_code == 403
    assert carlo.c.get(d["movements"][0]["proofs"][0]["thumb"], headers=carlo.h).status_code == 403
    assert up(bea, got["id"], b"not an image").status_code == 422
    # The movements log shows them too.
    log = bea.get("/api/v1/inventory/movements?kind=stock_in").json()["items"]
    assert any(len(m["proofs"]) == 4 for m in log)
