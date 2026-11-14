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
    # Five of the same item: five records, each its own serial (typed ones first, then automatic ones).
    five = new_asset(admin, name="Office chair", category="Furniture", count=5, serial_numbers=["CH-1", "ch-2"])
    assert five.status_code == 201, five.text
    made = five.json()["created"]
    assert len(made) == 5 and [m["serial_number"] for m in made[:2]] == ["CH-1", "CH-2"]
    autos = [m["serial_number"] for m in made[2:]]
    assert all(x.startswith("GPI-FN-") for x in autos) and len(set(autos)) == 3
    assert all(admin.get(f"/api/v1/assets/{m['id']}").json()["quantity"] == 1 for m in made)
    # The old form sent quantity with one serial: that now registers that many items instead of failing.
    old = new_asset(admin, serial_number="PF-0002", quantity=3)
    assert old.status_code == 201 and len(old.json()["created"]) == 3 and old.json()["serial_number"] == "PF-0002"
    assert new_asset(admin, count=2, serial_numbers=["A1", "A2", "A3"]).status_code == 422  # more serials than items
    assert new_asset(admin, count=2, serial_numbers=["B1", "b1"]).status_code == 422  # same serial twice
    # No serial typed: one is issued automatically and never reused.
    auto = new_asset(admin).json()
    assert auto["serial_number"].startswith("GPI-IT-")
    patched = admin.patch(f"/api/v1/assets/{auto['id']}", {**{k: auto[k] for k in ("name", "category", "brand", "model")}, "serial_number": "", "version": auto["version"]})
    assert patched.status_code == 200 and patched.json()["serial_number"] == auto["serial_number"]  # clearing keeps it
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
    bad = admin.post("/api/v1/receiving", {"request_id": req["id"], "lines": [{"item_id": item, "quantity": 1, "register_asset": True, "serial_numbers": ["MN-1", "MN-9"]}]})
    assert bad.status_code == 422  # more serials than items
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


def test_issue_several_as_one_issuance(users, client):
    """Five of the same item to one person: one issuance, one notification, one acknowledgement, one form."""
    import io

    from pypdf import PdfReader

    admin, carlo = users["admin"], users["carlo"]
    made = new_asset(admin, name="Binder clip", category="Other", count=6).json()["created"]
    first = made[0]["id"]
    d = admin.get(f"/api/v1/assets/{first}").json()
    assert d["identical_in_stock"] == 5
    assert admin.post(f"/api/v1/assets/{first}/assign", {"employee_id": me_id(carlo), "count": 7}).status_code == 422  # only 6 in stock
    before = len(carlo.get("/api/v1/notifications").json()["items"])
    r = admin.post(f"/api/v1/assets/{first}/assign", {"employee_id": me_id(carlo), "count": 5})
    assert r.status_code == 200, r.text
    d = r.json()
    ref = d["issue_ref"]
    assert ref.startswith("EA-ISS-") and len(d["issued_together"]) == 5
    held = [a for a in carlo.get("/api/v1/me/assets").json() if a["name"] == "Binder clip"]
    assert len(held) == 5 and {a["issue_ref"] for a in held} == {ref}
    notes = carlo.get("/api/v1/notifications").json()["items"]
    assert len(notes) == before + 1 and "Binder clip × 5" in notes[0]["title"]
    # The sixth stays in stock; the registry shows two entries, not six.
    g = admin.get("/api/v1/assets?q=Binder clip&grouped=true").json()
    assert g["total"] == 2
    issued = next(x for x in g["items"] if x["holder"])
    assert issued["group"]["count"] == 5 and len({m["serial_number"] for m in issued["group"]["members"]}) == 5
    assert admin.get("/api/v1/assets?q=Binder clip").json()["total"] == 6  # ungrouped list unchanged
    # One issuance form lists all five.
    doc = admin.post("/api/v1/documents", {"template_key": "asset_issuance_form", "related_id": first}).json()
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(client.get(doc["url"], headers=admin.h).content)).pages)
    assert "Items issued (5)" in text and ref in text and all(m["serial_number"] in text for m in issued["group"]["members"])
    # Acknowledging one acknowledges the set.
    other = issued["group"]["members"][3]["id"]
    a = carlo.post(f"/api/v1/assets/{other}/acknowledge").json()
    assert all(x["acknowledged"] for x in a["issued_together"])
    assert all(x["acknowledged_at"] for x in carlo.get("/api/v1/me/assets").json() if x["issue_ref"] == ref)
    # Returning one takes it out of the issuance.
    admin.post(f"/api/v1/assets/{other}/return", {"condition": "used"})
    assert len(admin.get(f"/api/v1/assets/{first}").json()["issued_together"]) == 4


def test_earlier_issues_are_grouped_on_start(users, client):
    """Assets issued one by one before issuance references existed are grouped by person, item and day."""
    from sqlalchemy import update

    from app.asset_ids import backfill_issue_refs
    from app.db import session_factory
    from app.models_ops import Asset

    admin, eli = users["admin"], users["eli"]
    made = new_asset(admin, name="Stapler", category="Office equipment", count=3).json()["created"]
    for m in made:  # the old way: one at a time
        admin.post(f"/api/v1/assets/{m['id']}/assign", {"employee_id": me_id(eli)})
    ids = [m["id"] for m in made]
    assert len({admin.get(f"/api/v1/assets/{i}").json()["issue_ref"] for i in ids}) == 3

    async def legacy_then_backfill():
        async with session_factory()() as s:
            await s.execute(update(Asset).where(Asset.id.in_(ids)).values(issue_ref=None))
            await s.commit()
            return await backfill_issue_refs(s)

    assert client.portal.call(legacy_then_backfill) >= 1
    refs = {admin.get(f"/api/v1/assets/{i}").json()["issue_ref"] for i in ids}
    assert len(refs) == 1 and None not in refs
    g = admin.get("/api/v1/assets?q=Stapler&grouped=true").json()
    assert g["total"] == 1 and g["items"][0]["group"]["count"] == 3
    # One acknowledgement covers all three.
    eli.post(f"/api/v1/assets/{ids[1]}/acknowledge")
    assert all(admin.get(f"/api/v1/assets/{i}").json()["acknowledged_at"] for i in ids)


def test_consumable_moved_to_stock_by_quantity(users):
    """Clips registered one record per piece become one stock line counted in pieces."""
    from .test_item_photos import add as upload, jpeg_with_gps

    admin, bea, carlo = users["admin"], users["assistant"], users["carlo"]
    made = new_asset(admin, name="Clip", category="Other", count=5).json()["created"]
    for m in made:  # the same photo was saved on every record
        assert upload(admin, "asset", m["id"], jpeg_with_gps()).status_code == 201
    admin.post(f"/api/v1/assets/{made[2]['id']}/assign", {"employee_id": me_id(carlo), "count": 3})
    plan = admin.get(f"/api/v1/assets/{made[0]['id']}/to-stock").json()
    assert plan["count"] == 5 and plan["in_stock"] == 2 and plan["issued"][0]["quantity"] == 3 and plan["blocked"] is None
    assert carlo.post(f"/api/v1/assets/{made[0]['id']}/to-stock", {"location": "Supply cabinet"}).status_code == 403
    assert bea.post(f"/api/v1/assets/{made[0]['id']}/to-stock", {"location": "Supply cabinet"}).status_code == 403  # needs inventory control
    r = admin.post(f"/api/v1/assets/{made[0]['id']}/to-stock", {"location": "Supply cabinet", "unit": "pc"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["moved"] == 5 and out["issued"] == 3 and out["item_code"].startswith("GPI-CS-")
    item = admin.get(f"/api/v1/inventory/items/{out['item_id']}").json()
    assert item["on_hand"] == 2 and item["unit"] == "pc" and item["photo"]
    kinds = [(m["kind"], m["quantity"], (m["issued_to"] or {}).get("id")) for m in item["movements"]]
    assert kinds == [("issue", -3, me_id(carlo)), ("stock_in", 5, None)]
    assert len(admin.get(f"/api/v1/photos?owner_type=inventory_item&owner_id={out['item_id']}").json()) == 1  # duplicates kept once
    assert [x for x in admin.get("/api/v1/assets?q=Clip&page_size=100").json()["items"] if x["name"] == "Clip"] == []  # no longer per-piece records
    assert admin.get(f"/api/v1/assets/{made[0]['id']}").status_code == 404
    mine = carlo.get("/api/v1/me/supplies").json()
    assert mine[0]["name"] == "Clip" and mine[0]["quantity"] == 3 and mine[0]["unit"] == "pc"
    assert [a for a in carlo.get("/api/v1/me/assets").json() if a["name"] == "Clip"] == []
    # Later issues are by quantity on the stock card.
    d = admin.post(f"/api/v1/inventory/items/{out['item_id']}/move", {"kind": "issue", "quantity": 2, "issued_to_id": me_id(carlo)}).json()
    assert d["on_hand"] == 0 and carlo.get("/api/v1/me/supplies").json()[0]["quantity"] == 2
    # Something under repair stays an asset.
    lap = new_asset(admin, name="Repair laptop").json()
    admin.post(f"/api/v1/assets/{lap['id']}/repairs", {"issue": "Screen"})
    assert admin.get(f"/api/v1/assets/{lap['id']}/to-stock").json()["blocked"]
    assert admin.post(f"/api/v1/assets/{lap['id']}/to-stock", {"location": "X"}).status_code == 409



def test_asset_history_entries_take_photo_proof(users):
    import json

    from .test_item_photos import jpeg_with_gps

    admin, carlo, eli = users["admin"], users["carlo"], users["eli"]
    a = new_asset(admin, name="Proof laptop").json()
    d = admin.post(f"/api/v1/assets/{a['id']}/assign", {"employee_id": me_id(carlo)}).json()
    ev = d["events"][0]
    assert ev["type"] == "assigned" and ev["proofs"] == []
    up = lambda u, meta=None: u.c.post(f"/api/v1/assets/events/{ev['id']}/proof", headers=u.h, data={"meta": json.dumps(meta)} if meta else {}, files={"file": ("p.jpg", jpeg_with_gps(), "image/jpeg")})
    assert up(admin, {"source": "camera", "taken_at": "2026-11-14T09:00:00+08:00", "lat": 14.6, "lng": 121.0}).status_code == 201
    assert up(carlo).status_code == 201  # the holder can add a photo of what they received
    assert up(eli).status_code == 404  # not theirs
    one = carlo.get(f"/api/v1/assets/events/{ev['id']}").json()
    assert one["asset"]["name"] == "Proof laptop" and len(one["proofs"]) == 2 and one["proofs"][0]["meta"]["source"] == "camera" and one["proofs"][1]["meta"]["source"] == "upload"
    assert carlo.c.get(one["proofs"][0]["thumb"], headers=carlo.h).status_code == 200
    assert eli.c.get(one["proofs"][0]["thumb"], headers=eli.h).status_code == 404
    assert len(admin.get(f"/api/v1/assets/{a['id']}").json()["events"][0]["proofs"]) == 2
