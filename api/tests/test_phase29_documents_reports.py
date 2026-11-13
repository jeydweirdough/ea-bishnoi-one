"""Phase 2.9 — official documents (control numbers, versions, states, signatures) and reports/dashboards."""

import io
from datetime import date

from openpyxl import load_workbook

from .test_phase21_employee_requests import concern, supplies


def test_request_documents_respect_approval(users, client):
    carlo, admin = users["carlo"], users["admin"]
    req = carlo.post("/api/v1/requests", supplies(submit=True)).json()
    tpls = carlo.get(f"/api/v1/documents/templates?related_type=request&related_id={req['id']}").json()
    keys = {t["key"]: t for t in tpls}
    assert "supply_request_form" in keys and "purchase_order" not in keys  # employees only get their own forms
    staff_tpls = {t["key"]: t for t in admin.get(f"/api/v1/documents/templates?related_type=request&related_id={req['id']}").json()}
    assert staff_tpls["purchase_order"]["available"] is False
    doc = carlo.post("/api/v1/documents", {"template_key": "supply_request_form", "related_id": req["id"]})
    assert doc.status_code == 201, doc.text
    d = doc.json()
    assert d["status"] == "for_approval" and d["control_number"].startswith("EA-REQ-")
    assert admin.post(f"/api/v1/documents/{d['id']}/issue").status_code == 409  # cannot issue before approval
    assert admin.post("/api/v1/documents", {"template_key": "purchase_order", "related_id": req["id"]}).status_code == 409
    pdf = client.get(d["url"], headers=carlo.h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert users["eli"].get(f"/api/v1/documents/{d['id']}").status_code == 404
    for who in ("dana", "coo", "naresh"):
        users[who].post(f"/api/v1/requests/{req['id']}/actions/approve", {})
    v2 = admin.post("/api/v1/documents", {"template_key": "supply_request_form", "related_id": req["id"]}).json()
    assert v2["control_number"] == d["control_number"] and v2["version"] == 2 and v2["status"] == "approved"
    first = admin.get(f"/api/v1/documents/{d['id']}").json()
    assert first["status"] == "superseded" and len(first["versions"]) == 2
    po = admin.post("/api/v1/documents", {"template_key": "purchase_order", "related_id": req["id"]}).json()
    assert po["control_number"].startswith("EA-PO-")
    assert admin.post(f"/api/v1/documents/{po['id']}/issue").json()["status"] == "issued"
    signed = client.post(f"/api/v1/documents/{po['id']}/signed", headers=admin.h, files={"file": ("signed.pdf", b"%PDF-1.4\n", "application/pdf")})
    assert signed.status_code == 200 and signed.json()["status"] == "signed"
    assert users["assistant"].post(f"/api/v1/documents/{po['id']}/void", {"reason": "x"}).status_code == 403
    assert admin.post(f"/api/v1/documents/{po['id']}/void", {"reason": "Supplier changed"}).json()["status"] == "voided"
    reg = admin.get("/api/v1/documents?q=EA-PO").json()
    assert reg["total"] >= 1
    events = admin.get(f"/api/v1/documents/{po['id']}").json()["events"]
    assert {"generated", "issued", "signed", "voided"} <= {e["type"] for e in events}


def test_many_templates_render(users):
    admin, carlo = users["admin"], users["carlo"]
    # concern with resolution
    c = carlo.post("/api/v1/requests", concern(submit=True)).json()
    for who in ("dana", "jasmine", "mira", "malhou"):
        users[who].post(f"/api/v1/requests/{c['id']}/actions/approve", {})
    admin.post(f"/api/v1/requests/{c['id']}/actions/start", {})
    admin.post(f"/api/v1/requests/{c['id']}/actions/fulfill", {"message": "Fixed"})
    out = admin.post("/api/v1/documents", {"template_key": "employee_concern_resolution_form", "related_id": c["id"]})
    assert out.status_code == 201 and out.json()["status"] == "approved"
    # asset, vehicle, registration, contract, period reports
    a = admin.post("/api/v1/assets", {"name": "Doc laptop", "category": "IT equipment", "serial_number": "DOC-1"}).json()
    admin.post(f"/api/v1/assets/{a['id']}/assign", {"employee_id": carlo.get("/api/v1/me").json()["employee"]["id"]})
    v = admin.post("/api/v1/fleet/vehicles", {"vehicle_type": "Van", "make": "Nissan", "model": "Urvan", "plate_number": "DOC 1"}).json()
    r = admin.post("/api/v1/compliance/registrations", {"document_name": "Doc permit", "registration_type": "Business Permit", "registration_date": "2026-01-10", "validity_years": 1}).json()
    l = admin.post("/api/v1/contracts/lessors", {"name": "Doc Lessor"}).json()
    k = admin.post("/api/v1/contracts", {"contract_type": "office_lease", "title": "Doc lease", "lessor_id": l["id"], "start_date": "2026-01-01", "end_date": "2027-12-31", "monthly_rent_php": "1000"}).json()
    period = int(date.today().strftime("%Y%m"))
    for key, rid in [("asset_issuance_form", a["id"]), ("vehicle_assignment_form", v["id"]), ("vehicle_renewal_checklist", v["id"]), ("registration_renewal_request", r["id"]), ("government_document_checklist", r["id"]), ("lease_renewal_request", k["id"]), ("monthly_administrative_report", period), ("executive_summary_report", period), ("compliance_monitoring_report", period), ("contract_monitoring_report", period)]:
        res = admin.post("/api/v1/documents", {"template_key": key, "related_id": rid, "paper": "Letter" if key.endswith("report") else "A4"})
        assert res.status_code == 201, (key, res.text)
    assert carlo.post("/api/v1/documents", {"template_key": "monthly_administrative_report", "related_id": period}).status_code in (403, 404)


def test_reports_catalogue_and_exports(users, client):
    admin, bea, carlo = users["admin"], users["assistant"], users["carlo"]
    cat = admin.get("/api/v1/reports").json()
    assert len(cat) >= 40 and {"Requests", "Assets", "Inventory", "Fleet", "Compliance", "Travel", "Contracts", "Administration"} <= {r["module"] for r in cat}
    assert "visa_expiry" not in {r["key"] for r in bea.get("/api/v1/reports").json()}
    assert carlo.get("/api/v1/reports").status_code == 403
    r = admin.get("/api/v1/reports/request_register").json()
    assert r["total_rows"] >= 1 and r["columns"][0]["key"] == "reference"
    for key in ["approval_aging", "requests_by_department", "sla_performance", "stock_on_hand", "asset_registry", "pms_due", "expiring_documents", "contract_register", "monthly_rental_summary", "approval_history", "admin_activity", "renewal_calendar", "employee_travel"]:
        res = admin.get(f"/api/v1/reports/{key}?within=400")
        assert res.status_code == 200, (key, res.text)
    assert bea.get("/api/v1/reports/audit_report").status_code == 403
    x = client.get("/api/v1/reports/requests_by_department/export?format=xlsx", headers=admin.h)
    wb = load_workbook(io.BytesIO(x.content))
    assert wb.active.cell(1, 1).value == "Department" and "Summary" in wb.sheetnames
    p = client.get("/api/v1/reports/stock_on_hand/export?format=pdf", headers=admin.h)
    assert p.content.startswith(b"%PDF")
    dash = admin.get("/api/v1/dashboard/executive").json()
    for k in ("total_open_requests", "pending_approvals", "overdue_requests", "priority_concerns", "upcoming_renewals", "active_assets", "assets_under_repair", "fleet_maintenance_due", "expiring_government_documents", "contract_renewals", "travel_requests", "task_completion"):
        assert k in dash
    assert bea.get("/api/v1/dashboard/assistant").status_code == 200


def test_non_approval_records_are_final_not_approved(users):
    admin = users["admin"]
    i = admin.post("/api/v1/inventory/items", {"name": "Doc toner", "item_code": "DOC-TNR", "category": "Supplies", "location": "HQ", "unit": "pc", "opening_quantity": 3}).json()
    d = admin.post("/api/v1/documents", {"template_key": "stock_card", "related_id": i["id"]}).json()
    assert d["status"] == "final"  # complete, but no approval happened — never labelled "Approved"
    assert admin.post(f"/api/v1/documents/{d['id']}/issue").json()["status"] == "issued"
