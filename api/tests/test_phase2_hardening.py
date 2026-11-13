"""Phase 2 hardening (§29): large record sets, PDF page breaks, import retries."""

import io
import re
import time

from openpyxl import Workbook, load_workbook
from pypdf import PdfReader

N = 3000  # stock lines in the large-set test


def xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload(client, user, dataset, data, name="file.xlsx", mode="create"):
    return client.post("/api/v1/imports", headers=user.h, data={"dataset": dataset, "mode": mode}, files={"file": (name, data, "application/octet-stream")})


def pages(pdf: bytes) -> list[str]:
    return [p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages]


def assert_numbered(texts: list[str]):
    total = len(texts)
    for n, t in enumerate(texts, 1):
        assert f"Page {n} of {total}" in t, f"page {n} footer missing"


# ---------------------------------------------------------------- large record sets


def test_large_import_pagination_and_export(users, client):
    admin = users["admin"]
    header = ["Item Code", "Item Name", "Storage Location", "Quantity on Hand", "Unit", "Category", "Unit Cost (PHP)"]
    rows = [header] + [[f"BULK-{n:05d}", f"Bulk item {n:05d}", "Bulk warehouse", n % 50, "pc", "Supplies", "12.50"] for n in range(N)]
    t0 = time.perf_counter()
    job = upload(client, admin, "inventory", xlsx(rows))
    assert job.status_code == 201, job.text
    job = job.json()
    assert job["summary"]["rows"] == N
    mapping = {h: v["field"] for h, v in job["summary"]["suggestions"].items()}
    assert None not in mapping.values()
    v = admin.post(f"/api/v1/imports/{job['id']}/validate", {"mapping": mapping}).json()
    assert v["summary"]["create"] == N and v["summary"]["error"] == 0
    c = admin.post(f"/api/v1/imports/{job['id']}/commit", {}).json()
    elapsed = time.perf_counter() - t0
    assert c["status"] == "committed" and c["results"]["create"] == N
    assert elapsed < 120, f"{N}-row import took {elapsed:.1f}s"

    # pagination: stable, complete, no overlaps
    seen = set()
    page, size = 1, 500
    while True:
        r = admin.get(f"/api/v1/inventory/items?q=BULK-&page={page}&page_size={size}").json()
        assert r["total"] == N
        codes = [i["item_code"] for i in r["items"]]
        assert not (seen & set(codes))
        seen |= set(codes)
        if len(codes) < size:
            break
        page += 1
    assert len(seen) == N
    assert admin.get(f"/api/v1/inventory/items?q=BULK-&page=999&page_size={size}").json()["items"] == []
    assert admin.get("/api/v1/inventory/items?page_size=501").status_code == 422  # page size is capped

    # export: every row, typed, with totals
    x = client.get("/api/v1/exports/inventory?format=xlsx", headers=admin.h)
    assert x.status_code == 200
    ws = load_workbook(io.BytesIO(x.content)).worksheets[0]
    codes = {ws.cell(r, 1).value for r in range(2, ws.max_row + 1)}
    assert {f"BULK-{n:05d}" for n in range(N)} <= codes
    csv = client.get("/api/v1/exports/inventory?format=csv", headers=admin.h)
    assert csv.content.decode("utf-8-sig").count("BULK-") >= N

    # a file over the row limit is refused before anything is written
    big = upload(client, admin, "inventory", xlsx([header] + [[f"OVER-{n}", "x", "y", 1, "pc", "Supplies", ""] for n in range(5001)]))
    assert big.status_code in (400, 422) and "5000" in big.text
    assert admin.get("/api/v1/inventory/items?q=OVER-").json()["total"] == 0


def test_large_pdf_report_breaks_pages_cleanly(users, client):
    admin = users["admin"]
    p = client.get("/api/v1/exports/inventory?format=pdf", headers=admin.h)
    assert p.status_code == 200 and p.content.startswith(b"%PDF")
    texts = pages(p.content)
    assert len(texts) > 10  # thousands of rows → many pages
    assert_numbered(texts)
    for n, t in enumerate(texts, 1):
        assert "Item Code" in t, f"column header not repeated on page {n}"  # repeatRows=1
    # no row is lost or duplicated across page breaks
    found = re.findall(r"BULK-\d{5}", "\n".join(texts))
    assert len(found) == len(set(found)) and len(set(found)) == N


# ---------------------------------------------------------------- official documents across pages


def test_multi_page_official_document(users, client):
    admin = users["admin"]
    me = admin.get("/api/v1/me").json()["employee"]["id"]
    i = admin.post("/api/v1/inventory/items", {"name": "Page-break toner", "item_code": "PGB-1", "category": "Supplies", "location": "HQ", "unit": "pc", "opening_quantity": 500}).json()
    for n in range(120):
        r = admin.post(f"/api/v1/inventory/items/{i['id']}/move", {"kind": "issue", "quantity": 1, "issued_to_id": me, "reason": f"Line {n:03d}"})
        assert r.status_code == 200, r.text
    for paper, size in (("A4", (595, 842)), ("Letter", (612, 792))):
        d = admin.post("/api/v1/documents", {"template_key": "stock_card", "related_id": i["id"], "paper": paper}).json()
        pdf = client.get(d["url"], headers=admin.h).content
        reader = PdfReader(io.BytesIO(pdf))
        box = reader.pages[0].mediabox
        assert (round(float(box.width)), round(float(box.height))) == size
        texts = pages(pdf)
        assert len(texts) >= 3
        assert_numbered(texts)
        for n, t in enumerate(texts, 1):
            assert "Reference" in t and "Balance" in t, f"table header missing on page {n}"
            if n > 1:
                assert d["control_number"] in t, f"control number missing on page {n}"  # running header
        joined = "\n".join(texts)
        lines = re.findall(r"Line \d{3}", joined)
        assert len(lines) == 120 and len(set(lines)) == 120  # every movement once
        # the signature block stays whole on the last page
        assert "PREPARED BY" in texts[-1].upper() and all("PREPARED BY" not in t.upper() for t in texts[:-1])
        assert d["status"] == "final"


# ---------------------------------------------------------------- import retries


def test_import_retry_after_failed_commit(users, client):
    admin = users["admin"]
    data = xlsx([["Asset Name", "Category", "Serial No."], ["Retry laptop A", "IT equipment", "RTY-1"], ["Retry laptop B", "IT equipment", "RTY-2"]])
    job = upload(client, admin, "assets", data).json()
    mapping = {h: v["field"] for h, v in job["summary"]["suggestions"].items()}
    v = admin.post(f"/api/v1/imports/{job['id']}/validate", {"mapping": mapping}).json()
    assert v["summary"]["create"] == 2 and v["summary"]["error"] == 0

    # someone registers RTY-2 between the check and the commit
    assert admin.post("/api/v1/assets", {"name": "Registered meanwhile", "category": "IT equipment", "serial_number": "RTY-2"}).status_code == 201
    fail = admin.post(f"/api/v1/imports/{job['id']}/commit", {})
    assert fail.status_code == 409 and "nothing was imported" in fail.text
    assert admin.get("/api/v1/assets?q=RTY-1").json()["total"] == 0  # all-or-nothing
    j = admin.get(f"/api/v1/imports/{job['id']}").json()
    assert j["status"] == "failed" and any("RTY-2" in str(x.get("value")) or "erial" in x["error"] for x in j["issues"])
    assert admin.post(f"/api/v1/imports/{job['id']}/commit", {}).status_code == 409  # must re-check first

    # retry: check again, then import the good row
    v2 = admin.post(f"/api/v1/imports/{job['id']}/validate", {"mapping": mapping}).json()
    assert v2["summary"]["create"] == 1 and v2["summary"]["error"] == 1
    ok = admin.post(f"/api/v1/imports/{job['id']}/commit", {"skip_invalid": True}).json()
    assert ok["status"] == "committed" and ok["results"]["create"] == 1
    assert admin.post(f"/api/v1/imports/{job['id']}/commit", {"skip_invalid": True}).json()["results"] == ok["results"]
    assert admin.get("/api/v1/assets?q=RTY-1").json()["total"] == 1
    assert admin.get("/api/v1/assets?q=RTY-2").json()["total"] == 1  # only the one registered by hand


def test_import_retry_with_corrected_file_upserts(users, client):
    admin = users["admin"]
    header = ["Item Code", "Item Name", "Storage Location", "Quantity on Hand", "Unit"]
    first = xlsx([header, ["RTRY-1", "Retry cable", "HQ", 5, "pc"], ["RTRY-2", "Retry mouse", "HQ", "lots", "pc"]])
    j1 = upload(client, admin, "inventory", first).json()
    m = {h: v["field"] for h, v in j1["summary"]["suggestions"].items()}
    admin.post(f"/api/v1/imports/{j1['id']}/validate", {"mapping": m})
    assert admin.post(f"/api/v1/imports/{j1['id']}/commit", {"skip_invalid": True}).json()["results"]["create"] == 1

    # fix the bad row and send the whole file again in upsert mode: no duplicates, the fixed row is added
    fixed = xlsx([header, ["RTRY-1", "Retry cable", "HQ", 5, "pc"], ["RTRY-2", "Retry mouse", "HQ", 7, "pc"]])
    j2 = upload(client, admin, "inventory", fixed, mode="upsert").json()
    assert j2["summary"]["duplicate_of"] is None  # different file, not flagged
    v = admin.post(f"/api/v1/imports/{j2['id']}/validate", {"mapping": m, "match_key": "item_code"}).json()
    assert v["summary"]["create"] == 1 and v["summary"]["update"] == 1 and v["summary"]["error"] == 0
    admin.post(f"/api/v1/imports/{j2['id']}/commit", {})
    items = admin.get("/api/v1/inventory/items?q=RTRY-").json()["items"]
    assert sorted((i["item_code"], i["on_hand"]) for i in items) == [("RTRY-1", 5), ("RTRY-2", 7)]


def test_concurrent_checklist_ticks_are_not_lost(users, client):
    """Ticking several requirements at once (fast clicks) must keep every tick."""
    from concurrent.futures import ThreadPoolExecutor

    admin = users["admin"]
    c = admin.post("/api/v1/banking/cases", {"case_type": "account_application", "subject": "Concurrency check", "bank": "BPI"}).json()
    n = len(c["requirements"])
    assert n >= 5

    def tick(i):
        return client.put(f"/api/v1/banking/cases/{c['id']}/requirements", json={"index": i, "done": True}, headers=admin.h).status_code

    with ThreadPoolExecutor(max_workers=n) as pool:
        codes = list(pool.map(tick, range(n)))
    assert codes == [200] * n
    after = admin.get(f"/api/v1/banking/cases/{c['id']}").json()
    assert after["requirements_done"] == n
