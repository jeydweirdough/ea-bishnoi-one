"""Phase 2.8 — templates, upload, mapping, validation, commit, error reports, exports."""

import csv
import io

from openpyxl import Workbook, load_workbook


def xlsx(rows, sheet="Data"):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload(client, user, dataset, data, name="file.xlsx", mode="create"):
    return client.post("/api/v1/imports", headers=user.h, data={"dataset": dataset, "mode": mode}, files={"file": (name, data, "application/octet-stream")})


def test_catalogue_and_template(users, client):
    admin, carlo = users["admin"], users["carlo"]
    cat = admin.get("/api/v1/datasets").json()
    keys = {d["key"] for d in cat}
    assert {"assets", "inventory", "vehicles", "registrations", "contracts", "tasks"} <= keys
    assert carlo.get("/api/v1/datasets").status_code == 403
    t = client.get("/api/v1/datasets/assets/template", headers=admin.h)
    assert t.status_code == 200
    wb = load_workbook(io.BytesIO(t.content))
    assert {"Data", "Instructions", "Allowed values", "Template info"} <= set(wb.sheetnames)
    assert wb["Data"].cell(1, 1).value == "company_code"  # asset_id is not importable
    csvt = client.get("/api/v1/datasets/vehicles/template?format=csv", headers=admin.h)
    assert csvt.content.startswith(b"\xef\xbb\xbf") and b"plate_number" in csvt.content


def test_mapping_validation_and_commit(users, client):
    admin = users["admin"]
    data = xlsx([
        ["Note: asset list from IT"],
        ["Asset Name", "Category", "Serial No.", "Brand Name", "Model Name", "Company", "Dept", "Purchase Date", "Mystery"],
        ["Dell Latitude 5440", "IT equipment", "DL-1001", "Dell", "5440", "GPI", "IT", "2026-03-01", "x"],
        ["Dell Latitude 5440", "IT equipment", "DL-1002", "Dell", "5440", "GPI", "IT", "not a date", "x"],
        ["Dell Latitude 5440", "IT equipment", "DL-1001", "Dell", "5440", "GPI", "IT", "2026-03-01", "x"],
        ["HP Monitor", "IT equipment", "=1+1", "HP", "", "GPI", "", "", ""],
        ["Mac mini", "IT equipment", "MM-77", "Apple", "", "ZZZ", "", "", ""],
    ])
    up = upload(client, admin, "assets", data)
    assert up.status_code == 201, up.text
    job = up.json()
    sug = job["summary"]["suggestions"]
    assert sug["Serial No."]["field"] == "serial_number" and sug["Brand Name"]["field"] == "brand" and sug["Mystery"]["field"] is None
    assert job["summary"]["rows"] == 5 and job["headers"][0] == "Asset Name"  # header row found below the note
    mapping = {h: v["field"] for h, v in sug.items()}
    mapping["Dept"] = "department_code"
    assert admin.post(f"/api/v1/imports/{job['id']}/validate", {"mapping": {**mapping, "Mystery": "status"}}).status_code == 422  # protected field
    v = admin.post(f"/api/v1/imports/{job['id']}/validate", {"mapping": mapping}).json()
    assert v["summary"]["create"] == 1 and v["summary"]["error"] == 4
    errors = {i["row"]: i["error"] for i in v["issues"]}
    assert "invalid value" in errors[4] and "Duplicate of row 3" in errors[5] and "Formulas" in errors[6] and "Unknown company" in errors[7]
    assert admin.post(f"/api/v1/imports/{job['id']}/commit", {}).status_code == 409  # errors present
    rep = client.get(f"/api/v1/imports/{job['id']}/errors", headers=admin.h)
    wb = load_workbook(io.BytesIO(rep.content))
    assert wb["Errors"].cell(1, 2).value == "Row Number" and wb["Errors"].max_row == 5
    ann = client.get(f"/api/v1/imports/{job['id']}/errors?format=annotated", headers=admin.h)
    assert load_workbook(io.BytesIO(ann.content)).active.cell(1, 10).value == "Import errors"
    c = admin.post(f"/api/v1/imports/{job['id']}/commit", {"skip_invalid": True}).json()
    assert c["status"] == "committed" and c["results"]["create"] == 1
    again = admin.post(f"/api/v1/imports/{job['id']}/commit", {"skip_invalid": True}).json()
    assert again["results"] == c["results"]  # idempotent retry
    assert admin.get("/api/v1/assets?q=DL-1001").json()["total"] == 1
    # same file again → flagged as already imported, and the serial is now a duplicate
    up2 = upload(client, admin, "assets", data).json()
    assert up2["summary"]["duplicate_of"] == c["reference"]
    audit = admin.get("/api/v1/admin/audit?action=import&page_size=50").json()["items"]
    assert any(a["action"] == "import.commit" for a in audit)


def test_update_mode_and_csv(users, client):
    admin = users["admin"]
    admin.post("/api/v1/fleet/vehicles", {"vehicle_type": "Van", "make": "Toyota", "model": "Hiace", "plate_number": "IMP 100"})
    data = "Plate No.;Odometer;Insurance\nIMP 100;25000;2027-05-01\nNOPE 1;10;\n".encode("utf-8")
    job = upload(client, admin, "vehicles", data, name="v.csv", mode="update").json()
    mapping = {h: v["field"] for h, v in job["summary"]["suggestions"].items()}
    assert mapping == {"Plate No.": "plate_number", "Odometer": "odometer_km", "Insurance": "insurance_expiry_date"}
    v = admin.post(f"/api/v1/imports/{job['id']}/validate", {"mapping": mapping, "match_key": "plate_number"}).json()
    assert v["summary"]["update"] == 1 and v["summary"]["error"] == 1
    admin.post(f"/api/v1/imports/{job['id']}/commit", {"skip_invalid": True})
    veh = next(x for x in admin.get("/api/v1/fleet/vehicles?q=IMP").json()["items"])
    assert veh["odometer_km"] == 25000 and veh["insurance_expiry_date"] == "2027-05-01" and veh["make"] == "Toyota"  # unmapped fields untouched


def test_import_security(users, client):
    admin, carlo, bea = users["admin"], users["carlo"], users["assistant"]
    assert upload(client, carlo, "assets", xlsx([["a", "b"]])).status_code == 403
    assert upload(client, bea, "inventory", xlsx([["a", "b"]])).status_code == 403  # needs inventory control
    assert upload(client, admin, "assets", b"MZ fake", name="evil.xlsm").status_code == 422
    assert upload(client, admin, "assets", b"not really excel", name="x.xlsx").status_code == 422
    assert upload(client, admin, "flights", xlsx([["a", "b"]])).status_code == 403  # export-only dataset
    j = upload(client, admin, "assets", xlsx([["Asset Name", "Category"], ["x", "Other"]])).json()
    assert bea.get(f"/api/v1/imports/{j['id']}").status_code == 404  # other people's jobs


def test_exports(users, client):
    admin, bea = users["admin"], users["assistant"]
    admin.post("/api/v1/assets", {"name": "=HYPERLINK(\"http://x\")", "category": "Other", "serial_number": "0012345"})
    x = client.get("/api/v1/exports/assets?format=xlsx", headers=admin.h)
    assert x.status_code == 200
    wb = load_workbook(io.BytesIO(x.content))
    assert "Summary" in wb.sheetnames and wb["Summary"]["B3"].value >= 1
    ws = wb.worksheets[0]
    names = [ws.cell(r, 3).value for r in range(2, ws.max_row + 1)]
    assert any(isinstance(n, str) and n.startswith("'=") for n in names)  # formula neutralised
    c = client.get("/api/v1/exports/assets?format=csv", headers=admin.h)
    rows = list(csv.reader(io.StringIO(c.content.decode("utf-8-sig"))))
    assert rows[0][0] == "Asset ID" and any(r[2].startswith("'=") for r in rows[1:]) and any("0012345" in r for r in rows[1:])
    p = client.get("/api/v1/exports/assets?format=pdf", headers=admin.h)
    assert p.content.startswith(b"%PDF")
    assert client.get("/api/v1/exports/travel_documents?format=csv", headers=bea.h).status_code == 403
    assert client.get("/api/v1/exports/assets", headers=users["carlo"].h).status_code == 403
    log = admin.get("/api/v1/admin/audit?action=export&page_size=50").json()["items"]
    assert any(a["action"] == "export.download" for a in log)
