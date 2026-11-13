"""
Phase 2.8 — one reusable import/export engine (EXECUTIVE-ADMIN.md §15–17, §24).

Templates → upload → sheet & header detection → suggested mapping → manual corrections →
validation & duplicate detection → preview of create/update → transaction-safe commit →
results → error report / annotated workbook. Exports in XLSX, CSV and PDF.
"""

import csv
import difflib
import hashlib
import io
import re
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..config import get_settings
from ..core import audit, bad_request, conflict, forbidden, next_reference, not_found, now
from ..datasets import DATASETS, Dataset, F, RowError, blank, export_records, parse
from ..models import Company
from ..models_ops3 import ImportJob
from ..pdf import Column, table_report
from ..security import Principal, Session, Staff
from ..serialize import iso, person

router = APIRouter(prefix="/api/v1", tags=["import-export"])

TEMPLATE_VERSION = "2026.11"
MAX_ROWS = 5000
HEAD_FILL = PatternFill("solid", fgColor="111111")
REQ_FILL = PatternFill("solid", fgColor="EEF3D9")
ERR_FILL = PatternFill("solid", fgColor="FDF0EE")
MONEY_FMT = '"PHP" #,##0.00'


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def dataset_for(key: str, principal: Principal, write: bool = False) -> Dataset:
    ds = DATASETS.get(key)
    if ds is None:
        raise not_found("Unknown dataset")
    if not ds.can_read(principal):
        raise forbidden("You cannot export this data")
    if write and not (ds.importable and ds.can_write(principal)):
        raise forbidden("You cannot import this data")
    return ds


# ------------------------------------------------------------------ catalogue & templates


@router.get("/datasets")
async def datasets(principal: Staff) -> list[dict]:
    return [
        {
            "key": d.key, "label": d.label, "importable": d.importable and d.can_write(principal), "exportable": True, "note": d.note, "match_keys": d.match_keys,
            "fields": [{"name": f.name, "label": f.label, "type": f.type, "required": f.required, "importable": f.importable, "choices": f.choices, "help": f.help} for f in d.fields],
        }
        for d in DATASETS.values()
        if d.can_read(principal)
    ]


def _xlsx_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _file(data: bytes, name: str, kind: str) -> Response:
    media = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "text/csv; charset=utf-8", "pdf": "application/pdf"}[kind]
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/datasets/{key}/template")
async def template(key: str, principal: Staff, session: Session, format: Literal["xlsx", "csv"] = "xlsx"):
    ds = dataset_for(key, principal, write=True)
    fields = [f for f in ds.fields if f.importable]
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f.name for f in fields])
        w.writerow(["" if f.example is None else f.example for f in fields])
        return _file(("﻿" + buf.getvalue()).encode("utf-8"), f"{key}-template.csv", "csv")
    wb = Workbook()
    data = wb.active
    data.title = "Data"
    for i, f in enumerate(fields, 1):
        c = data.cell(row=1, column=i, value=f.name)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HEAD_FILL
        data.cell(row=2, column=i, value=f.example).fill = REQ_FILL if f.required else PatternFill()
        data.column_dimensions[get_column_letter(i)].width = max(14, len(f.name) + 4)
    data.freeze_panes = "A2"
    ins = wb.create_sheet("Instructions")
    ins.append(["Field", "Label", "Required", "Type", "Allowed values", "Example", "Notes"])
    for f in fields:
        ins.append([f.name, f.label, "Yes" if f.required else "No", f.type, ", ".join(f.choices or []), "" if f.example is None else str(f.example), f.help or ""])
    for c in ins[1]:
        c.font = Font(bold=True)
    for col, w in zip("ABCDEFG", (26, 30, 10, 10, 40, 26, 60)):
        ins.column_dimensions[col].width = w
    ins.append([])
    ins.append(["Row 2 of the Data sheet is a sample; replace or delete it. Required columns are shaded in the sample row."])
    ins.append(["Formulas, macros and external links are never imported. Enter plain values."])
    if ds.note:
        ins.append([ds.note])
    choices = [f for f in fields if f.choices]
    if choices:
        av = wb.create_sheet("Allowed values")
        for i, f in enumerate(choices, 1):
            av.cell(row=1, column=i, value=f.name).font = Font(bold=True)
            for j, ch in enumerate(f.choices, 2):
                av.cell(row=j, column=i, value=ch)
            av.column_dimensions[get_column_letter(i)].width = max(16, len(f.name) + 4)
    meta = wb.create_sheet("Template info")
    for row in (("Dataset", ds.key), ("Label", ds.label), ("Template version", TEMPLATE_VERSION), ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")), ("Generated by", principal.employee.name)):
        meta.append(row)
    await audit(session, actor_id=principal.id, action="import.template_download", entity_type="dataset", entity_ref=key)
    await session.commit()
    return _file(_xlsx_bytes(wb), f"{key}-template.xlsx", "xlsx")


# ------------------------------------------------------------------ reading files


def _cell(v):
    if isinstance(v, str):
        return v.strip()
    return v


def read_sheets(data: bytes, filename: str) -> dict[str, list[list]]:
    """Returns {sheet: rows}. XLSX via openpyxl (no formula evaluation, no links); CSV with delimiter sniffing."""
    name = filename.lower()
    if name.endswith(".csv"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = [[_cell(c) for c in r] for r in csv.reader(io.StringIO(text), dialect)]
        return {"CSV": rows}
    if name.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
        except Exception:
            raise bad_request({"message": "The workbook could not be read. Save it as .xlsx or .csv and try again."})
        out = {}
        for ws in wb.worksheets:
            rows = []
            for r in ws.iter_rows(values_only=True):
                rows.append([_cell(c) for c in r])
                if len(rows) > MAX_ROWS + 20:
                    break
            out[ws.title] = rows
        wb.close()
        return out
    raise bad_request({"message": "Upload an .xlsx or .csv file. Macro-enabled and older Excel formats are not accepted."})


def header_row(rows: list[list]) -> int:
    for i, r in enumerate(rows[:15]):
        texts = [c for c in r if isinstance(c, str) and c.strip()]
        if len(texts) >= 2:
            return i
    return 0


def suggest(headers: list[str], ds: Dataset) -> dict:
    """Header → {field, confidence, ambiguous}. Exact name/label/synonym wins; otherwise fuzzy with ambiguity check."""
    fields = [f for f in ds.fields if f.importable]
    out, used = {}, set()
    for h in headers:
        if blank(h):
            continue
        nh = norm(h)
        exact = [f for f in fields if nh in {norm(f.name), norm(f.label), *(norm(s) for s in f.synonyms)}]
        if exact and exact[0].name not in used:
            out[h] = {"field": exact[0].name, "confidence": 1.0, "ambiguous": False}
            used.add(exact[0].name)
            continue
        scored = sorted(
            ((max(difflib.SequenceMatcher(None, nh, norm(x)).ratio() for x in [f.name, f.label, *f.synonyms]), f.name) for f in fields if f.name not in used),
            reverse=True,
        )
        if scored and scored[0][0] >= 0.78:
            amb = len(scored) > 1 and scored[0][0] - scored[1][0] < 0.06
            out[h] = {"field": scored[0][1], "confidence": round(scored[0][0], 2), "ambiguous": amb}
            used.add(scored[0][1])
        else:
            out[h] = {"field": None, "confidence": 0, "ambiguous": False}
    return out


def job_out(j: ImportJob, preview: list | None = None) -> dict:
    return {
        "id": j.id, "reference": j.reference, "dataset": j.dataset, "dataset_label": DATASETS[j.dataset].label if j.dataset in DATASETS else j.dataset, "mode": j.mode,
        "filename": j.filename, "sheet": j.sheet, "sheets": j.sheets, "headers": j.headers, "mapping": j.mapping, "status": j.status, "summary": j.summary,
        "issues": j.issues[:500], "issue_count": len(j.issues), "results": j.results, "created_by": person(j.created_by), "created_at": iso(j.created_at),
        "committed_at": iso(j.committed_at), **({"preview": preview} if preview is not None else {}),
    }


def _load(job: ImportJob) -> tuple[list, list[list]]:
    data = (get_settings().upload_dir / job.storage_key).read_bytes()
    sheets = read_sheets(data, job.filename)
    rows = sheets.get(job.sheet) or next(iter(sheets.values()))
    h = header_row(rows)
    headers = [str(c).strip() if c is not None else "" for c in rows[h]] if rows else []
    body = [r for r in rows[h + 1 :] if any(not blank(c) for c in r)]
    return headers, body, h


async def own_job(session, principal: Principal, job_id: int) -> ImportJob:
    j = await session.get(ImportJob, job_id)
    if j is None or (j.created_by_id != principal.id and not principal.is_admin):
        raise not_found()
    return j


# ------------------------------------------------------------------ import flow


@router.post("/imports", status_code=201)
async def upload(principal: Staff, session: Session, dataset: str = Form(...), mode: Literal["create", "update", "upsert"] = Form("create"), file: UploadFile = File(...)) -> dict:
    ds = dataset_for(dataset, principal, write=True)
    if mode != "create" and not ds.match_keys:
        raise bad_request({"message": f"{ds.label} can only be imported as new records", "fields": {"mode": "Create only"}})
    settings = get_settings()
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if not data:
        raise bad_request({"message": "The file is empty"})
    if len(data) > limit:
        raise bad_request({"message": f"Files must be {settings.max_upload_mb} MB or smaller"})
    sheets = read_sheets(data, file.filename or "upload")
    sheet = next((n for n, r in sheets.items() if n.lower() == "data"), next(iter(sheets)))
    key = secrets.token_hex(16)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / key).write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    j = ImportJob(reference=await next_reference(session, "IMP"), dataset=ds.key, mode=mode, filename=(file.filename or "upload")[:255], storage_key=key, sha256=sha, sheet=sheet, sheets=list(sheets), created_by_id=principal.id)
    session.add(j)
    await session.flush()
    headers, body, _ = _load(j)
    if len(body) > MAX_ROWS:
        raise bad_request({"message": f"Imports are limited to {MAX_ROWS} rows per file. Split the file and try again."})
    j.headers = headers
    sug = suggest(headers, ds)
    j.mapping = {h: v["field"] for h, v in sug.items() if v["field"]}
    prev = (await session.execute(select(ImportJob).where(ImportJob.sha256 == sha, ImportJob.dataset == ds.key, ImportJob.status == "committed"))).scalars().first()
    j.summary = {"rows": len(body), "suggestions": sug, "duplicate_of": prev.reference if prev else None}
    await audit(session, actor_id=principal.id, action="import.upload", entity_type="import", entity_id=j.id, entity_ref=j.reference, data={"dataset": ds.key, "file": j.filename, "rows": len(body), "sha256": sha})
    await session.commit()
    return job_out(j, preview=[dict(zip(headers, [str(c) if c is not None else "" for c in r])) for r in body[:10]])


class SheetIn(BaseModel):
    sheet: str


@router.post("/imports/{job_id}/sheet")
async def choose_sheet(job_id: int, body: SheetIn, principal: Staff, session: Session) -> dict:
    j = await own_job(session, principal, job_id)
    if j.status == "committed":
        raise conflict("This import is already committed")
    if body.sheet not in j.sheets:
        raise bad_request({"message": "Unknown worksheet", "fields": {"sheet": "Not found"}})
    j.sheet = body.sheet
    headers, rows, _ = _load(j)
    j.headers = headers
    sug = suggest(headers, DATASETS[j.dataset])
    j.mapping = {h: v["field"] for h, v in sug.items() if v["field"]}
    j.summary = {**(j.summary or {}), "rows": len(rows), "suggestions": sug}
    j.status = "uploaded"
    await session.commit()
    return job_out(j, preview=[dict(zip(headers, [str(c) if c is not None else "" for c in r])) for r in rows[:10]])


class MappingIn(BaseModel):
    mapping: dict[str, str | None]
    match_key: str | None = None


def _values(row: list, headers: list[str], mapping: dict, ds: Dataset, excel_row: int, sheet: str, issues: list) -> dict | None:
    """Parse one row into canonical values; records issues. Returns None when the row has errors."""
    v: dict = {}
    ok = True
    present = set()
    for idx, h in enumerate(headers):
        fname = mapping.get(h)
        if not fname:
            continue
        f = ds.field(fname)
        raw = row[idx] if idx < len(row) else None
        if isinstance(raw, str) and raw.startswith("=") and len(raw) > 1:
            issues.append({"sheet": sheet, "row": excel_row, "column": h, "value": raw, "error": "Formulas are not imported", "expected": "A plain value", "suggestion": "Paste values only", "severity": "error"})
            ok = False
            continue
        try:
            v[fname] = parse(f, raw)
            present.add(fname)
        except RowError as e:
            issues.append({"sheet": sheet, "row": excel_row, "column": h, "value": "" if raw is None else str(raw), "error": e.message, "expected": e.expected, "suggestion": e.suggestion, "severity": "error"})
            ok = False
    return v if ok else None


async def _plan(session, principal: Principal, j: ImportJob, ds: Dataset, match_key: str | None, *, commit: bool, skip_invalid: bool = False):
    headers, rows, h = _load(j)
    issues: list = []
    ops = {"create": 0, "update": 0, "skip": 0, "error": 0}
    preview, results = [], []
    seen: dict = {}
    for n, row in enumerate(rows):
        excel_row = h + 2 + n
        v = _values(row, headers, j.mapping, ds, excel_row, j.sheet, issues)
        if v is None:
            ops["error"] += 1
            continue
        # Duplicates inside the file
        dup_key = None
        for k in [*ds.match_keys, "serial_number", "plate_number", "item_code", "masked_card_last4", "document_name"]:
            if v.get(k) not in (None, ""):
                dup_key = (k, str(v[k]).upper(), str(v.get("storage_location") or ""))
                break
        if dup_key and dup_key in seen:
            issues.append({"sheet": j.sheet, "row": excel_row, "column": dup_key[0], "value": dup_key[1], "error": f"Duplicate of row {seen[dup_key]} in this file", "expected": "Each record once", "suggestion": "Remove the duplicate row", "severity": "error"})
            ops["error"] += 1
            continue
        if dup_key:
            seen[dup_key] = excel_row
        existing = None
        if j.mode in ("update", "upsert"):
            mk = match_key or (ds.match_keys[0] if ds.match_keys else None)
            if mk and v.get(mk) not in (None, ""):
                existing = await ds.find(session, principal, mk, v[mk], row=v)
            if existing is None and j.mode == "update":
                issues.append({"sheet": j.sheet, "row": excel_row, "column": mk, "value": str(v.get(mk) or ""), "error": "No existing record matches this row", "expected": f"An existing {mk}", "suggestion": "Use Create or Create-or-update mode", "severity": "error"})
                ops["error"] += 1
                continue
        op = "update" if existing is not None else "create"
        if op == "update":
            # Only mapped columns change; everything else keeps the record's current value.
            current = {k: x for k, x in ds.export_row(existing).items() if ds.field(k) and ds.field(k).importable}
            v = {**current, **{k: x for k, x in v.items() if x is not None}}
        else:
            missing = [f.label for f in ds.fields if f.required and f.importable and v.get(f.name) in (None, "")]
            if missing:
                issues.append({"sheet": j.sheet, "row": excel_row, "column": missing[0], "value": "", "error": f"Required for new records: {', '.join(missing)}", "expected": ", ".join(missing), "suggestion": "Fill in the column, or map it if it exists", "severity": "error"})
                ops["error"] += 1
                continue
        try:
            async with session.begin_nested():
                if op == "update":
                    rec = await ds.update(session, principal, existing, v)
                else:
                    rec = await ds.create(session, principal, v)
                await session.flush()
                ident = getattr(rec, "reference", None) or getattr(rec, "item_code", None) or getattr(rec, "name", None)
                if not commit:
                    raise _DryRun()
        except _DryRun:
            pass
        except RowError as e:
            col = next((hh for hh, ff in j.mapping.items() if ff == e.column), e.column)
            issues.append({"sheet": j.sheet, "row": excel_row, "column": col, "value": str(v.get(e.column) or "") if e.column else "", "error": e.message, "expected": e.expected, "suggestion": e.suggestion, "severity": "error"})
            ops["error"] += 1
            continue
        except Exception as e:  # database-level failure for this row only
            issues.append({"sheet": j.sheet, "row": excel_row, "column": None, "value": "", "error": f"Could not save this row ({type(e).__name__})", "expected": None, "suggestion": None, "severity": "error"})
            ops["error"] += 1
            continue
        ops[op] += 1
        if len(preview) < 50:
            preview.append({"row": excel_row, "operation": op, "values": {k: (str(x) if x is not None else None) for k, x in v.items()}})
        if commit:
            results.append({"row": excel_row, "operation": op, "id": rec.id, "reference": ident})
    return headers, ops, issues, preview, results


class _DryRun(Exception):
    pass


@router.post("/imports/{job_id}/validate")
async def validate(job_id: int, body: MappingIn, principal: Staff, session: Session) -> dict:
    j = await own_job(session, principal, job_id)
    if j.status == "committed":
        raise conflict("This import is already committed")
    ds = dataset_for(j.dataset, principal, write=True)
    mapping = {h: f for h, f in body.mapping.items() if f}
    unknown = [f for f in mapping.values() if not (ds.field(f) and ds.field(f).importable)]
    if unknown:
        raise bad_request({"message": f"These fields cannot be imported: {', '.join(unknown)}", "fields": {"mapping": "Protected or unknown field"}})
    targets = list(mapping.values())
    dupes = {f for f in targets if targets.count(f) > 1}
    if dupes:
        raise bad_request({"message": f"Two columns are mapped to {', '.join(dupes)}", "fields": {"mapping": "Map each field once"}})
    if body.match_key and body.match_key not in ds.match_keys:
        raise bad_request({"message": "That field cannot be used to match records", "fields": {"match_key": f"Use {', '.join(ds.match_keys)}"}})
    j.mapping = mapping
    _, ops, issues, preview, _ = await _plan(session, principal, j, ds, body.match_key, commit=False)
    j.issues = issues
    j.summary = {**(j.summary or {}), **ops, "match_key": body.match_key, "validated_at": now().isoformat()}
    j.status = "validated"
    await session.commit()
    return job_out(j, preview=preview)


class CommitIn(BaseModel):
    skip_invalid: bool = False


@router.post("/imports/{job_id}/commit")
async def commit(job_id: int, body: CommitIn, principal: Staff, session: Session) -> dict:
    j = await own_job(session, principal, job_id)
    if j.status == "committed":
        return job_out(j)  # idempotent retry: same results, nothing written twice
    if j.status != "validated":
        raise conflict("Validate the import before committing it")
    ds = dataset_for(j.dataset, principal, write=True)
    if (j.summary or {}).get("error") and not body.skip_invalid:
        raise conflict(f"{j.summary['error']} row(s) have errors. Fix them, or choose to skip those rows.")
    _, ops, issues, _, results = await _plan(session, principal, j, ds, (j.summary or {}).get("match_key"), commit=True)
    if ops["error"] and not body.skip_invalid:
        await session.rollback()
        j = await own_job(session, principal, job_id)
        j.issues = issues
        j.status = "failed"
        await session.commit()
        raise conflict("Some rows failed while saving; nothing was imported. Download the error report.")
    j.issues = issues
    j.results = {**ops, "records": results[:2000]}
    j.status = "committed"
    j.committed_at = now()
    await audit(session, actor_id=principal.id, action="import.commit", entity_type="import", entity_id=j.id, entity_ref=j.reference, data={"dataset": ds.key, "mode": j.mode, **ops})
    await session.commit()
    return job_out(j)


@router.get("/imports")
async def history(principal: Staff, session: Session, dataset: str | None = None) -> list[dict]:
    stmt = select(ImportJob)
    if not principal.is_admin:
        stmt = stmt.where(ImportJob.created_by_id == principal.id)
    if dataset:
        stmt = stmt.where(ImportJob.dataset == dataset)
    rows = (await session.execute(stmt.order_by(ImportJob.id.desc()).limit(50))).scalars()
    return [{k: v for k, v in job_out(j).items() if k not in ("issues",)} for j in rows]


@router.get("/imports/{job_id}")
async def get_job(job_id: int, principal: Staff, session: Session) -> dict:
    return job_out(await own_job(session, principal, job_id))


@router.get("/imports/{job_id}/errors")
async def error_report(job_id: int, principal: Staff, session: Session, format: Literal["xlsx", "csv", "annotated"] = "xlsx"):
    j = await own_job(session, principal, job_id)
    cols = ["sheet", "row", "column", "value", "error", "expected", "suggestion"]
    labels = ["Worksheet", "Row Number", "Column", "Original Value", "Error Description", "Expected Value", "Suggested Correction"]
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(labels)
        for i in j.issues:
            w.writerow([safe_csv(i.get(c)) for c in cols])
        return _file(("﻿" + buf.getvalue()).encode("utf-8"), f"{j.reference}-errors.csv", "csv")
    if format == "annotated":
        headers, rows, h = _load(j)
        wb = Workbook()
        ws = wb.active
        ws.title = "Annotated"
        ws.append(headers + ["Import errors"])
        for c in ws[1]:
            c.font = Font(bold=True)
        by_row: dict[int, list] = {}
        for i in j.issues:
            by_row.setdefault(i["row"], []).append(i)
        for n, r in enumerate(rows):
            excel_row = h + 2 + n
            problems = by_row.get(excel_row, [])
            ws.append([*(c if not isinstance(c, str) else c for c in r), "; ".join(f"{p['column']}: {p['error']}" for p in problems)])
            if problems:
                bad_cols = {p["column"] for p in problems}
                for ci, hd in enumerate(headers, 1):
                    if hd in bad_cols:
                        ws.cell(row=ws.max_row, column=ci).fill = ERR_FILL
                ws.cell(row=ws.max_row, column=len(headers) + 1).fill = ERR_FILL
        return _file(_xlsx_bytes(wb), f"{j.reference}-annotated.xlsx", "xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Errors"
    ws.append(labels)
    for c in ws[1]:
        c.font = Font(bold=True)
    for i in j.issues:
        ws.append([i.get(c) for c in cols])
    for col, w in zip("ABCDEFG", (12, 10, 22, 26, 50, 26, 36)):
        ws.column_dimensions[col].width = w
    return _file(_xlsx_bytes(wb), f"{j.reference}-errors.xlsx", "xlsx")


# ------------------------------------------------------------------ export


FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_csv(v) -> str:
    """CSV formula-injection protection: text that a spreadsheet would evaluate is prefixed with a quote."""
    if v is None:
        return ""
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    s = str(v)
    return "'" + s if s.startswith(FORMULA_START) else s


def safe_xlsx(v):
    if isinstance(v, str) and v.startswith(FORMULA_START):
        return "'" + v
    if isinstance(v, datetime) and v.tzinfo:
        return v.replace(tzinfo=None)
    return v


@router.get("/exports/{key}")
async def export(
    key: str, principal: Staff, session: Session, format: Literal["xlsx", "csv", "pdf"] = "xlsx", q: str | None = None,
    status: list[str] = Query(default_factory=list), company: str | None = None, date_from: date | None = None, date_to: date | None = None,
    ids: list[int] = Query(default_factory=list), assigned: str | None = None,
):
    ds = dataset_for(key, principal)
    if principal.role.value == "assistant" and ds.key in ("banking_cases", "corporate_cards", "travel_documents") and not ds.can_read(principal):
        raise forbidden()
    recs = await export_records(session, principal, ds, q=q, status=status or None, company=company, date_from=date_from, date_to=date_to, ids=ids or None, assigned=assigned)
    if ds.key == "fleet_accounts":
        from ..datasets import _rfid_row
        from ..models_ops import RfidAccount

        rows = [(_rfid_row(r) if isinstance(r, RfidAccount) else ds.export_row(r)) for r in recs]
    else:
        rows = [ds.export_row(r) for r in recs]
    fields = [f for f in ds.fields if f.exportable and not f.sensitive]
    filters = {k: v for k, v in {"search": q, "status": ",".join(status) if status else None, "company": company, "from": date_from, "to": date_to, "assigned": assigned, "selected": len(ids) if ids else None}.items() if v}
    company_name = await _company_name(session, principal, company)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    await audit(session, actor_id=principal.id, action="export.download", entity_type="dataset", entity_ref=ds.key, data={"format": format, "records": len(rows), "filters": {k: str(v) for k, v in filters.items()}})
    await session.commit()
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        w.writerow([f.label for f in fields])
        for r in rows:
            w.writerow([safe_csv(r.get(f.name)) for f in fields])
        return _file(("﻿" + buf.getvalue()).encode("utf-8"), f"{ds.key}-{stamp}.csv", "csv")
    if format == "pdf":
        cols = [Column(f.name, f.label, "money" if f.type == "decimal" else "date" if f.type == "date" else "number" if f.type == "int" else "text") for f in fields[:9]]
        totals = {f.name: sum((r.get(f.name) or Decimal(0)) for r in rows) for f in fields[:9] if f.type == "decimal"}
        sub = [f"{k.title()}: {v}" for k, v in filters.items()]
        data = table_report(ds.label, company_name, cols, rows, subtitle=sub, totals=totals or None, generated_by=principal.employee.name)
        return _file(data, f"{ds.key}-{stamp}.pdf", "pdf")
    wb = Workbook()
    ws = wb.active
    ws.title = ds.label[:31].replace("/", "-")
    ws.append([f.label for f in fields])
    for r in rows:
        ws.append([safe_xlsx(r.get(f.name)) for f in fields])
    for i, f in enumerate(fields, 1):
        letter = get_column_letter(i)
        ws.column_dimensions[letter].width = max(12, min(40, len(f.label) + 6))
        for cell in ws[letter][1:]:
            if f.type == "decimal":
                cell.number_format = MONEY_FMT
            elif f.type == "date":
                cell.number_format = "yyyy-mm-dd"
            elif f.type == "str" and isinstance(cell.value, str) and cell.value.isdigit():
                cell.number_format = "@"  # keep leading zeros
    money_cols = [i for i, f in enumerate(fields, 1) if f.type == "decimal"]
    if rows:
        ref = f"A1:{get_column_letter(len(fields))}{len(rows) + 1}"
        t = Table(displayName=re.sub(r"[^A-Za-z0-9]", "", ds.key.title()) or "Data", ref=ref)
        t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
        ws.add_table(t)
        if money_cols:
            total_row = len(rows) + 2
            ws.cell(row=total_row, column=1, value="Total").font = Font(bold=True)
            for ci in money_cols:
                c = ws.cell(row=total_row, column=ci, value=sum((r.get(fields[ci - 1].name) or Decimal(0)) for r in rows))
                c.number_format = MONEY_FMT
                c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    summ = wb.create_sheet("Summary")
    for row in (("Report", ds.label), ("Company", company_name), ("Records", len(rows)), ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")), ("Generated by", principal.employee.name), *[(f"Filter: {k}", str(v)) for k, v in filters.items()]):
        summ.append(row)
    summ.column_dimensions["A"].width = 22
    summ.column_dimensions["B"].width = 48
    for c in summ["A"]:
        c.font = Font(bold=True)
    for c in ws[1]:
        c.alignment = Alignment(wrap_text=True, vertical="top")
    return _file(_xlsx_bytes(wb), f"{ds.key}-{stamp}.xlsx", "xlsx")


async def _company_name(session, principal: Principal, code: str | None) -> str:
    if code:
        c = (await session.execute(select(Company).where(Company.code == code.upper()))).scalar_one_or_none()
        if c:
            return c.name
    return principal.employee.company.name if len(principal.company_ids) == 1 else "All authorized companies"


__all__ = ["router", "safe_csv", "F"]
