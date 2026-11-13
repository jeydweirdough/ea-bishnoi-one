"""Document reading (OCR): upload a file, get proposed values for the form. Nothing is saved by the scan."""

import io

from PIL import Image, ImageDraw, ImageFont


def picture(lines, size=(1240, 900)):
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for y, text, px, *mono in lines:
        d.text((80, y), text, fill="black", font=ImageFont.truetype("C:/Windows/Fonts/" + ("consola.ttf" if mono else "arial.ttf"), px))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def text_pdf(rows):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 780
    for t in rows:
        c.drawString(60, y, t)
        y -= 24
    c.save()
    return buf.getvalue()


def scan(client, user, kind, data, name):
    return client.post("/api/v1/scan", headers=user.h, data={"kind": kind}, files={"file": (name, data, "application/octet-stream")})


def val(r, key):
    return r["fields"].get(key, {}).get("value")


def test_permit_photo_fills_registration(users, client):
    admin = users["admin"]
    img = picture([(60, "Republic of the Philippines", 30), (190, "MAYOR'S PERMIT", 56), (290, "Permit No.: BP-2026-01188", 32),
                   (350, "Business Name: GETMEDS PHILIPPINES INC.", 32), (410, "Date Issued: January 15, 2026", 32), (470, "Valid Until: December 31, 2026", 32)])
    r = scan(client, admin, "registration", img, "permit.jpg".replace(".jpg", ".png"))
    assert r.status_code == 200, r.text
    r = r.json()
    assert r["method"] == "ocr"
    assert val(r, "document_name") == "Mayor's Permit"
    assert val(r, "registration_type") == "Business Permit"
    assert val(r, "registration_number") == "BP-2026-01188"
    assert val(r, "registration_date") == "2026-01-15" and val(r, "expiry_date") == "2026-12-31"
    assert r["fields"]["expiry_date"]["confidence"] >= 0.8
    assert r["matched"]["holder_name"]["company"] == "GPI"  # recognised as one of our companies
    # the scan saves nothing and logs no document values
    log = admin.get("/api/v1/admin/audit?action=document.scan&page_size=5").json()["items"]
    assert log and "BP-2026" not in str(log[0]) and "registration_number" in str(log[0])


def test_text_pdf_uses_its_text_layer(users, client):
    admin = users["admin"]
    pdf = text_pdf(["SECURITIES AND EXCHANGE COMMISSION", "CERTIFICATE OF INCORPORATION", "Company Reg. No. CS201912345", "was duly registered on 14 March 2019."])
    r = scan(client, admin, "registration", pdf, "sec.pdf").json()
    assert r["method"] == "text-layer"
    assert val(r, "registration_type") == "SEC" and val(r, "registration_number") == "CS201912345" and val(r, "registration_date") == "2019-03-14"


def test_passport_matches_employee_and_keeps_only_last4(users, client):
    admin, bea = users["admin"], users["assistant"]
    img = picture([(60, "REPUBLIKA NG PILIPINAS / PASSPORT", 34), (100, "Passport No.: P7712345A", 28), (140, "Surname: DIAZ", 28), (190, "Given names: CARLO", 28),
                   (240, "Date of issue: 05 FEB 2022", 28), (290, "Date of expiry: 04 FEB 2032", 28),
                   (600, "P<PHLDIAZ<<CARLO<<<<<<<<<<<<<<<<<<<<<<<<<<<<<", 40, True)], (1400, 760))
    assert scan(client, bea, "travel_document", img, "passport.png").status_code == 403  # needs the travel-documents grant
    r = scan(client, admin, "travel_document", img, "passport.png").json()
    carlo_id = users["carlo"].get("/api/v1/me").json()["employee"]["id"]
    assert val(r, "employee_id") == str(carlo_id)
    assert val(r, "number_last4") == "345A" and "P7712345A" not in str(r)  # never the full number
    assert val(r, "expiry_date") == "2032-02-04" and val(r, "issue_date") == "2022-02-05" and val(r, "country") == "Philippines"
    assert r["document_kind"] == "passport"


def test_lease_matches_lessor(users, client):
    admin = users["admin"]
    lessor = admin.post("/api/v1/contracts/lessors", {"name": "Robinsons Land Corporation"}).json()
    img = picture([(60, "CONTRACT OF LEASE", 44), (150, "Lessor: Robinsons Land Corporation, a domestic corporation", 28),
                   (290, "Term: commencing on June 1, 2026 to May 31, 2027", 28), (350, "Monthly rental of PHP 185,000.00", 28)])
    r = scan(client, admin, "contract", img, "lease.png").json()
    assert val(r, "title") == "Contract of Lease"
    assert val(r, "lessor_id") == str(lessor["id"])
    assert val(r, "start_date") == "2026-06-01" and val(r, "end_date") == "2027-05-31" and val(r, "monthly_rent_php") == "185000.00"


def test_scan_rules(users, client):
    admin, carlo = users["admin"], users["carlo"]
    png = picture([(60, "x", 20)])
    assert scan(client, carlo, "registration", png, "a.png").status_code == 403  # employees don't register documents
    assert scan(client, admin, "registration", b"MZ...", "a.exe").status_code == 422
    assert scan(client, admin, "registration", b"not a png", "a.png").status_code == 422
    assert scan(client, admin, "bogus", png, "a.png").status_code == 422
    blank = scan(client, admin, "registration", picture([]), "blank.png").json()
    assert blank["fields"] == {} and blank["readable"] is False


def card_picture(lines):
    img = Image.new("RGB", (1012, 638), "white")
    d = ImageDraw.Draw(img)
    for x, y, text, px in lines:
        d.text((x, y), text, fill="black", font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf", px))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_fleet_card_photo(users, client):
    admin = users["admin"]
    v = admin.post("/api/v1/fleet/vehicles", {"vehicle_type": "Van", "make": "Toyota", "model": "Hiace", "plate_number": "FLC 4321"}).json()
    img = card_picture([(60, 50, "Shell", 64), (600, 70, "FLEET CARD", 40), (60, 300, "7077 1234 5678 9013", 58), (60, 400, "CARLO DIAZ", 36), (60, 520, "FLC 4321", 34), (700, 520, "DIESEL", 34)])
    r = scan(client, admin, "fleet_card", img, "card.png")
    assert r.status_code == 200, r.text
    r = r.json()
    assert val(r, "card_number_last4") == "9013" and "7077" not in r.__repr__()  # only the last 4 digits ever leave the server
    assert val(r, "provider") == "Shell" and val(r, "fuel_type") == "Diesel"
    assert val(r, "vehicle_id") == str(v["id"])
    assert val(r, "assigned_user_id") == str(users["carlo"].get("/api/v1/me").json()["employee"]["id"])


def test_corporate_card_photo_needs_banking_access(users, client):
    admin, bea = users["admin"], users["assistant"]
    img = card_picture([(60, 50, "BPI", 64), (560, 70, "Corporate Credit Card", 34), (60, 300, "4111 1111 1111 1111", 58), (60, 400, "VALID THRU 03/28", 32), (60, 470, "ALEX REYES", 36)])
    assert scan(client, bea, "corporate_card", img, "card.png").status_code == 403
    r = scan(client, admin, "corporate_card", img, "card.png").json()
    assert val(r, "card_last4") == "1111" and "4111 1111" not in str(r)
    assert val(r, "bank") == "BPI" and val(r, "expiry_month") == "3" and val(r, "expiry_year") == "2028"
    assert val(r, "custodian_id") == str(admin.get("/api/v1/me").json()["employee"]["id"])
    assert r["fields"]["card_last4"]["confidence"] >= 0.8  # passes the card-number checksum


def test_vehicle_orcr(users, client):
    admin = users["admin"]
    img = picture([(100, "LAND TRANSPORTATION OFFICE", 32), (160, "CERTIFICATE OF REGISTRATION", 38), (250, "Plate No.: NBC 5678", 28), (300, "Make: TOYOTA", 28),
                   (350, "Series: HIACE COMMUTER", 28), (400, "Year Model: 2022", 28), (450, "Color: PEARL WHITE", 28), (500, "Body Type: VAN", 28),
                   (550, "Owner's Name: GETMEDS PHILIPPINES INC.", 28), (600, "Registration valid until: June 30, 2027", 28)], (1240, 980))
    r = scan(client, admin, "vehicle", img, "orcr.png").json()
    got = {k: val(r, k) for k in ("plate_number", "make", "model", "year_model", "color", "vehicle_type", "owner_name", "registration_renewal_date")}
    assert got == {"plate_number": "NBC 5678", "make": "Toyota", "model": "Hiace Commuter", "year_model": "2022", "color": "Pearl White", "vehicle_type": "Van",
                   "owner_name": "Getmeds Philippines Inc", "registration_renewal_date": "2027-06-30"}
