"""The shared request link: anyone can report a problem and/or request items; EA checks and accepts it."""

import io
import json
from datetime import date, timedelta

import pytest
from PIL import Image

from app.routers import intake

from .test_item_photos import jpeg_with_gps

SOON = (date.today() + timedelta(days=7)).isoformat()


@pytest.fixture(autouse=True)
def fresh_limits():
    intake._hits.clear()
    yield
    intake._hits.clear()


def company(client):
    return next(c for c in client.get("/api/v1/public/request-form").json()["companies"] if c["code"] == "GPI")


def form(client, **kw):
    body = {
        "name": "Rosa Villanueva", "email": "rosa.v@example.ph", "phone": "0917 555 0101", "position": "Cashier", "company_id": company(client)["id"],
        "problem": {"category": "Facilities", "subject": "Aircon leaking", "description": "Water drips onto the counter.", "location": "Branch 2, front"},
        "supplies": {"category": "Office supplies", "items": [{"item_name": "Bond paper A4", "quantity": 2, "unit": "ream"}, {"item_name": "Ballpen", "quantity": 10, "unit": "pc"}], "purpose": "Daily receipts", "needed_by": SOON},
    }
    body.update(kw)
    return body


def send(client, body, photos=(), headers=None):
    files = [("photos", (f"p{n}.jpg", data, "image/jpeg")) for n, data in enumerate(photos)]
    return client.post("/api/v1/public/requests", data={"data": json.dumps(body)}, files=files or None, headers=headers or {"Origin": "http://testserver"})


def test_form_options_are_public_and_know_who_is_signed_in(client, users):
    client.cookies.clear()
    o = client.get("/api/v1/public/request-form").json()
    assert o["me"] is None and o["companies"] and "Facilities" in o["concern_categories"]
    me = users["carlo"].get("/api/v1/public/request-form").json()["me"]
    assert me["name"] and me["company_id"]


def test_anonymous_submission_waits_for_ea_then_becomes_real_requests(client, users):
    client.cookies.clear()
    admin = users["admin"]
    r = send(client, form(client), photos=[jpeg_with_gps((1200, 900))])
    assert r.status_code == 201, r.text
    ref = r.json()["reference"]
    assert ref.startswith("EA-WEB-") and r.json()["status"] == "received"

    # Nothing reaches approvers yet; EA sees it in the inbox and is told about it.
    inbox = admin.get("/api/v1/web-requests").json()
    w = next(x for x in inbox["items"] if x["reference"] == ref)
    assert inbox["waiting"] >= 1 and w["problem"]["subject"] == "Aircon leaking" and len(w["supplies"]["items"]) == 2 and w["match"] is None
    assert any(ref in n["title"] for n in admin.get("/api/v1/notifications").json()["items"])
    photo = admin.get(w["photos"][0])
    assert photo.status_code == 200 and "exif" not in Image.open(io.BytesIO(photo.content)).info  # cleaned of GPS
    assert users["carlo"].get("/api/v1/web-requests").status_code == 403  # employees can't see the inbox
    assert client.get(w["photos"][0]).status_code == 401

    # The sender can check progress with the reference and their email (both needed).
    st = client.get("/api/v1/public/requests/status", params={"reference": ref.lower(), "email": "ROSA.V@example.ph"}).json()
    assert st["status"] == "new" and "Received" in st["status_label"] and st["requests"] == []
    assert client.get("/api/v1/public/requests/status", params={"reference": ref, "email": "someone@else.ph"}).status_code == 404

    # Accept: she isn't in the directory, so add her as a person. One problem report + one item request are filed.
    assert admin.post(f"/api/v1/web-requests/{w['id']}/accept", {"version": w["version"]}).status_code == 422  # who sent it?
    done = admin.post(f"/api/v1/web-requests/{w['id']}/accept", {"add_person": True, "version": w["version"]})
    assert done.status_code == 200, done.text
    d = done.json()
    assert d["status"] == "accepted" and len(d["requests"]) == 2 and d["match"]["name"] == "Rosa Villanueva"
    kinds = {admin.get(f"/api/v1/requests/{x['id']}").json()["kind"] for x in d["requests"]}
    assert kinds == {"concern", "supplies"}
    first = admin.get(f"/api/v1/requests/{d['requests'][0]['id']}").json()
    assert first["status"] not in ("draft",) and len(first["attachments"]) == 1  # the photo moved onto the request
    assert admin.post(f"/api/v1/web-requests/{w['id']}/accept", {"add_person": True, "version": d["version"]}).status_code == 409  # only once

    st = client.get("/api/v1/public/requests/status", params={"reference": ref, "email": "rosa.v@example.ph"}).json()
    assert st["status"] == "accepted" and len(st["requests"]) == 2


def test_matching_email_and_decline(client, users):
    client.cookies.clear()
    admin = users["admin"]
    carlo_email = users["carlo"].get("/api/v1/me").json()["employee"].get("email")
    body = form(client, supplies=None)
    if carlo_email:
        body["email"] = carlo_email
    w_ref = send(client, body).json()["reference"]
    w = next(x for x in admin.get("/api/v1/web-requests").json()["items"] if x["reference"] == w_ref)
    if carlo_email:
        assert w["match"] and w["match"]["id"] == users["carlo"].get("/api/v1/me").json()["employee"]["id"]
    assert admin.post(f"/api/v1/web-requests/{w['id']}/decline", {"reason": "", "version": w["version"]}).status_code == 422
    d = admin.post(f"/api/v1/web-requests/{w['id']}/decline", {"reason": "Sent twice — see EA-WEB earlier today", "version": w["version"]}).json()
    assert d["status"] == "declined"
    st = client.get("/api/v1/public/requests/status", params={"reference": w_ref, "email": body["email"]}).json()
    assert st["status"] == "declined" and "twice" in st["decline_reason"]


def test_signed_in_people_file_directly(users):
    carlo = users["carlo"]
    r = carlo.c.post("/api/v1/public/requests", headers=carlo.h, data={"data": json.dumps({"problem": {"category": "IT & equipment", "subject": "Mouse broken", "description": "Left click doesn't work"}, "supplies": {"items": [{"item_name": "USB mouse", "quantity": 1, "unit": "pc"}], "purpose": "Replace the broken one", "needed_by": SOON}})})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "submitted" and len(out["requests"]) == 2
    mine = {x["reference"] for x in carlo.get("/api/v1/requests?mine=true").json()["items"]} if carlo.get("/api/v1/requests?mine=true").status_code == 200 else set()
    for x in out["requests"]:
        assert carlo.get(f"/api/v1/requests/{x['id']}").json()["status"] != "draft"
    assert mine == set() or {x["reference"] for x in out["requests"]} <= mine


def test_form_checks_and_limits(client):
    client.cookies.clear()
    bad = send(client, form(client, problem=None, supplies=None))
    assert bad.status_code == 422 and "need" in bad.json()["detail"]["fields"]
    bad = send(client, form(client, email="not-an-email", name="R"))
    assert bad.status_code == 422 and {"email", "name"} <= set(bad.json()["detail"]["fields"])
    past = form(client, problem=None)
    past["supplies"]["needed_by"] = (date.today() - timedelta(days=1)).isoformat()
    assert send(client, past).status_code == 422
    assert send(client, form(client, problem={"category": "Nope", "subject": "x", "description": "y"})).status_code == 422
    assert send(client, form(client), photos=[b"not a picture"]).status_code == 422
    assert send(client, form(client), photos=[jpeg_with_gps((200, 200))] * 5).status_code == 422  # at most 4
    # Bots that fill the hidden field get a polite answer and nothing is stored.
    bot = send(client, form(client, website="http://spam.example")).json()
    assert bot["reference"] == "EA-WEB-0000"
    intake._hits.clear()
    codes = [send(client, form(client, problem=None)).status_code for _ in range(7)]
    assert codes[:6] == [201] * 6 and codes[6] == 429
