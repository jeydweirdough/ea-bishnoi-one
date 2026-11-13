"""People who are not in the directory yet: added on forms, usable everywhere, never able to sign in."""

import io
from datetime import date

from PIL import Image, ImageDraw, ImageFont


def add(user, **body):
    return user.post("/api/v1/directory/people", body)


def test_add_person_with_birth_date(users):
    admin = users["admin"]
    r = add(admin, first_name="Maria", middle_name="Santos", last_name="Lopez", suffix=None, gender="female", birth_date="1990-07-14")
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["name"] == "Maria Santos Lopez" and p["added"] is True and p["gender"] == "female" and p["role"] == "employee" and p["approver"] is False
    today = date.today()
    assert p["age"] == today.year - 1990 - ((today.month, today.day) < (7, 14))
    d = admin.get(f"/api/v1/directory/people/{p['id']}").json()
    assert (d["first_name"], d["middle_name"], d["last_name"], d["birth_date"]) == ("Maria", "Santos", "Lopez", "1990-07-14")
    # shows up in pickers, flagged as added
    found = admin.get("/api/v1/directory?q=Lopez").json()
    assert any(x["id"] == p["id"] and x["added"] for x in found)


def test_age_only_and_suffix(users):
    admin = users["admin"]
    p = add(admin, first_name="Jose", last_name="Rizal", suffix="Jr.", gender="male", age=42).json()
    assert p["name"] == "Jose Rizal Jr." and p["age"] == 42


def test_duplicates_and_validation(users):
    admin = users["admin"]
    add(admin, first_name="Ana", last_name="Reyes")
    dup = add(admin, first_name="Ana", last_name="Reyes")
    assert dup.status_code == 409 and dup.json()["detail"]["existing_id"]
    assert add(admin, first_name="Ana", last_name="Reyes", allow_duplicate=True).status_code == 201
    assert add(admin, first_name="X", last_name="Y", birth_date="2999-01-01").status_code == 422
    assert add(admin, first_name="X", last_name="Y", age=300).status_code == 422
    assert add(admin, first_name="", last_name="Y").status_code == 422
    assert add(admin, first_name="X", last_name="Y", suffix="Esq.").status_code == 422


def test_added_people_cannot_sign_in_or_add(users, client):
    admin, carlo = users["admin"], users["carlo"]
    p = add(admin, first_name="Guest", last_name="Visitor").json()
    assert client.get("/api/v1/me", headers={"X-EA-User": p["employee_no"]}).status_code == 401
    sign_in = client.get("/api/v1/dev/users")
    assert sign_in.status_code == 200 and all(u["employee_no"] != p["employee_no"] for u in sign_in.json())  # not in "Sign in as"
    grants = admin.get("/api/v1/admin/users?q=Visitor")
    assert grants.status_code == 200 and all(x["id"] != p["id"] for x in grants.json())  # no access grants for added people
    assert add(carlo, first_name="Not", last_name="Allowed").status_code == 403


def test_added_passenger_flows_into_travel_pdf(users, client):
    admin = users["admin"]
    p = add(admin, first_name="Liza", last_name="Cruz", gender="female", age=35).json()
    f = admin.post("/api/v1/travel/flights", {"passenger_id": p["id"], "travel_type": "domestic", "origin": "Manila (MNL)", "destination": "Cebu (CEB)", "departure_date": "2027-01-10"})
    assert f.status_code == 201, f.text
    doc = admin.post("/api/v1/documents", {"template_key": "flight_booking_summary", "related_id": f.json()["id"]}).json()
    from pypdf import PdfReader

    text = "".join(pg.extract_text() for pg in PdfReader(io.BytesIO(client.get(doc["url"], headers=admin.h).content)).pages)
    assert "Liza Cruz" in text and "Female" in text and "35 years" in text


def test_unknown_passport_holder_is_offered_as_new_person(users, client):
    admin = users["admin"]
    img = Image.new("RGB", (1400, 760), "white")
    d = ImageDraw.Draw(img)
    for y, t, s in [(60, "REPUBLIKA NG PILIPINAS / PASSPORT", 34), (100, "Passport No.: P5512345B", 28), (140, "Surname: VILLANUEVA", 28), (190, "Given names: ROSARIO", 28),
                    (240, "Middle name: DELA PAZ", 28), (290, "Sex: F", 28), (340, "Date of birth: 12 MAR 1985", 28), (390, "Date of expiry: 11 MAR 2033", 28)]:
        d.text((80, y), t, fill="black", font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf", s))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    r = client.post("/api/v1/scan", headers=admin.h, data={"kind": "travel_document"}, files={"file": ("p.png", buf.getvalue(), "image/png")}).json()
    assert "employee_id" not in r["fields"]
    assert r["person"] == {"first_name": "Rosario", "middle_name": "Dela Paz", "last_name": "Villanueva", "gender": "female", "birth_date": "1985-03-12"}
    assert "P5512345B" not in str(r)
