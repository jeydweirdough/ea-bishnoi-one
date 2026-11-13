"""Production sign-in: email + password accounts created by Admin, sessions, lockout, same-origin writes."""

import pytest

from app.config import get_settings

ORIGIN = "https://ea.bishnoi.ai"
H = {"Origin": ORIGIN}


@pytest.fixture
def production(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "env", "production")
    monkeypatch.setattr(s, "public_origin", ORIGIN)
    yield s


def company_id(users):
    return users["admin"].get("/api/v1/me").json()["employee"]["company"]["id"]


def new_account(users, email, role="employee", **kw):
    # Created while still in development mode (the dev admin header is accepted there).
    r = users["admin"].post("/api/v1/admin/users", {"name": kw.pop("name", "Test Person"), "email": email, "role": role, "company_id": company_id(users), **kw})
    assert r.status_code == 201, r.text
    return r.json()


def login(client, email, password, origin=ORIGIN):
    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers={"Origin": origin})
    # The cookie is Secure (https only); the test client talks plain http, so carry it over by hand.
    if r.cookies.get("ea_session"):
        client.cookies.set("ea_session", r.cookies["ea_session"])
    return r


def test_admin_creates_account_with_one_time_password(users, client, production):
    get_settings().env = "development"
    acct = new_account(users, "Rina.Lopez@Getmeds.ph", name="Rina Lopez")
    temp = acct["temporary_password"]
    assert len(temp) == 12 and acct["email"] == "rina.lopez@getmeds.ph" and acct["sign_in"]["must_change_password"]
    assert users["admin"].get("/api/v1/admin/users?q=rina").json()[0].get("temporary_password") is None  # shown once only
    assert users["admin"].post("/api/v1/admin/users", {"name": "Dup", "email": "rina.lopez@getmeds.ph", "company_id": company_id(users)}).status_code == 409
    assert users["carlo"].post("/api/v1/admin/users", {"name": "X", "email": "x@getmeds.ph", "company_id": company_id(users)}).status_code == 403
    get_settings().env = "production"

    # The development shortcuts are ignored in production.
    client.cookies.clear()
    assert client.get("/api/v1/me", headers={"X-EA-User": "EA-0001"}).status_code == 401
    assert client.get("/api/v1/dev/users").status_code in (403, 404)

    r = login(client, "rina.lopez@getmeds.ph", temp)
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    cookie = r.headers["set-cookie"]
    assert "ea_session=" in cookie and "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    # Until the temporary password is changed, only /me and sign-in work.
    assert client.get("/api/v1/me").status_code == 200
    blocked = client.get("/api/v1/requests")
    assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "password_change_required"
    bad = client.post("/api/v1/auth/password", json={"current_password": temp, "new_password": "short"}, headers=H)
    assert bad.status_code == 422
    ok = client.post("/api/v1/auth/password", json={"current_password": temp, "new_password": "Bishnoi-Admin-2026"}, headers=H)
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False
    assert client.get("/api/v1/requests").status_code == 200
    # Sign out ends the session on the server.
    assert client.post("/api/v1/auth/logout", headers=H).status_code == 204
    assert client.get("/api/v1/me").status_code == 401
    assert login(client, "RINA.LOPEZ@getmeds.ph", "Bishnoi-Admin-2026").status_code == 200  # email is case-insensitive


def test_wrong_passwords_lock_the_account_and_admin_reset_unlocks(users, client, production):
    get_settings().env = "development"
    acct = new_account(users, "lock.test@getmeds.ph")
    get_settings().env = "production"
    unknown = login(client, "nobody@getmeds.ph", "whatever-123")
    wrong = login(client, "lock.test@getmeds.ph", "wrong-password-1")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"]["message"] == wrong.json()["detail"]["message"]  # never reveals which emails exist
    for _ in range(4):
        login(client, "lock.test@getmeds.ph", "wrong-password-1")
    locked = login(client, "lock.test@getmeds.ph", acct["temporary_password"])  # even the right password
    assert locked.status_code == 423 and "locked" in locked.json()["detail"]["message"]
    get_settings().env = "development"
    reset = users["admin"].post(f"/api/v1/admin/users/{acct['id']}/temporary-password").json()
    assert reset["sign_in"]["locked"] is False and reset["temporary_password"] != acct["temporary_password"]
    get_settings().env = "production"
    assert login(client, "lock.test@getmeds.ph", acct["temporary_password"]).status_code == 401  # old one no longer works
    assert login(client, "lock.test@getmeds.ph", reset["temporary_password"]).status_code == 200


def test_deactivating_signs_out_immediately_and_cross_site_writes_are_refused(users, client, production):
    get_settings().env = "development"
    acct = new_account(users, "leaver@getmeds.ph", role="assistant")
    get_settings().env = "production"
    login(client, "leaver@getmeds.ph", acct["temporary_password"])
    client.post("/api/v1/auth/password", json={"current_password": acct["temporary_password"], "new_password": "Leaving-Soon-2026"}, headers=H)
    assert client.get("/api/v1/assets").status_code == 200
    # A write from another site is refused even with a valid session cookie.
    forged = client.post("/api/v1/assets", json={"name": "X", "category": "IT equipment"}, headers={"Origin": "https://evil.example"})
    assert forged.status_code == 403
    assert client.post("/api/v1/assets", json={"name": "X", "category": "IT equipment"}).status_code == 403  # no Origin at all
    get_settings().env = "development"
    users["admin"].patch(f"/api/v1/admin/users/{acct['id']}", {"active": False})
    get_settings().env = "production"
    assert client.get("/api/v1/me").status_code == 401
    assert login(client, "leaver@getmeds.ph", "Leaving-Soon-2026").status_code == 401


def test_admin_cannot_lock_themselves_out(users):
    me = users["admin"].get("/api/v1/me").json()["employee"]["id"]
    assert users["admin"].patch(f"/api/v1/admin/users/{me}", {"active": False}).status_code == 422
    assert users["admin"].patch(f"/api/v1/admin/users/{me}", {"role": "employee"}).status_code == 422


def test_password_hashing():
    from app.auth import hash_password, password_problem, verify_password

    h = hash_password("Correct-Horse-9")
    assert h.startswith("scrypt$") and "Correct-Horse-9" not in h
    assert verify_password("Correct-Horse-9", h) and not verify_password("correct-horse-9", h)
    assert hash_password("Correct-Horse-9") != h  # salted
    assert password_problem("aaaaaaaaaaaa") and password_problem("short") and password_problem("me@getmeds.ph", "me@getmeds.ph")
    assert password_problem("Bishnoi-Admin-2026") is None


def test_admin_manages_departments_and_heads(users):
    admin = users["admin"]
    cid = company_id(users)
    d = admin.post("/api/v1/admin/departments", {"company_id": cid, "name": "Human Resources"})
    assert d.status_code == 201 and d.json()["code"] == "HR" and d.json()["head"] is None
    assert admin.post("/api/v1/admin/departments", {"company_id": cid, "name": "human resources"}).status_code == 409
    acct = new_account(users, "hr.head@getmeds.ph", name="Hazel Reyes")
    assert acct["can_approve"] is False
    r = admin.patch(f"/api/v1/admin/departments/{d.json()['id']}", {"head_id": acct["id"]})
    assert r.status_code == 200 and r.json()["head"]["name"] == "Hazel Reyes"
    # Heads approve the "Department Head" stage, so approval duties come with the role.
    assert next(u for u in admin.get("/api/v1/admin/users?q=hazel").json())["can_approve"] is True
    assert any(x["name"] == "Human Resources" and x["head"] for x in admin.get("/api/v1/admin/departments").json())
    assert users["assistant"].get("/api/v1/admin/departments").status_code == 403
