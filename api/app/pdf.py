"""
Document engine (EXECUTIVE-ADMIN.md §19): letterhead, control number, structured sections,
tables with repeated headers and totals, certification text, signature blocks, footer and
"Page X of Y". A4 or Letter. Built on ReportLab platypus so long tables break across pages.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, LETTER, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor("#111111")
INK2 = colors.HexColor("#474747")
INK3 = colors.HexColor("#6b6b6b")
LINE = colors.HexColor("#d9d9d9")
CANVAS = colors.HexColor("#f4f4f4")
ACCENT = colors.HexColor("#a6c23f")

S = {
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7.5, leading=10, textColor=INK3),
    "label": ParagraphStyle("label", fontName="Helvetica", fontSize=7.5, leading=10, textColor=INK3),
    "value": ParagraphStyle("value", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=INK),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=INK, spaceBefore=8, spaceAfter=4),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=INK, alignment=TA_CENTER, spaceBefore=4, spaceAfter=2),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK3, alignment=TA_CENTER),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10.5, textColor=INK),
    "cellr": ParagraphStyle("cellr", fontName="Helvetica", fontSize=8, leading=10.5, textColor=INK, alignment=TA_RIGHT),
    "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=INK2),
    "headr": ParagraphStyle("headr", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=INK2, alignment=TA_RIGHT),
}


def esc(v: Any) -> str:
    s = "" if v is None else str(v)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt(v: Any, kind: str | None = None) -> str:
    if v is None or v == "":
        return "—"
    if kind == "money" or isinstance(v, Decimal):
        try:
            return f"₱{Decimal(v):,.2f}".replace("₱", "PHP ")
        except Exception:
            return str(v)
    if isinstance(v, datetime):
        return v.strftime("%b %d, %Y %I:%M %p")
    if isinstance(v, date):
        return v.strftime("%b %d, %Y")
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return str(v)


@dataclass
class Column:
    key: str
    label: str
    kind: str = "text"  # text | money | number | date
    width: float | None = None  # relative weight


@dataclass
class Signature:
    role: str  # Prepared By, Approved By, …
    name: str | None = None
    designation: str | None = None
    department: str | None = None
    # Shown only when the event really happened, e.g. "Approved in Executive Admin, Nov 12, 2026 2:10 PM"
    recorded: str | None = None


@dataclass
class DocSpec:
    title: str
    company_name: str
    company_address: str | None = None
    control_number: str | None = None
    version: int = 1
    issue_date: date | None = None
    reference: str | None = None
    status_label: str | None = None
    info: list[tuple[str, Any]] = field(default_factory=list)
    sections: list[tuple] = field(default_factory=list)  # ("text", heading, body) | ("table", heading, columns, rows, totals) | ("checklist", heading, [(text, done)]) | ("info", heading, pairs)
    certification: str | None = None
    signatures: list[Signature] = field(default_factory=list)
    watermark: str | None = None
    paper: str = "A4"
    landscape: bool = False
    footer_note: str | None = None


class NumberedCanvas(rl_canvas.Canvas):
    """Two-pass canvas so every page can say “Page X of Y”."""

    def __init__(self, *args, **kwargs):
        self._meta = kwargs.pop("meta")
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._decorate(total)
            super().showPage()
        super().save()

    def _decorate(self, total: int):
        w, h = self._pagesize
        m = self._meta
        if m.get("watermark"):
            self.saveState()
            self.setFont("Helvetica-Bold", 54)
            self.setFillColor(colors.Color(0.07, 0.07, 0.07, alpha=0.07))
            self.translate(w / 2, h / 2)
            self.rotate(35)
            self.drawCentredString(0, 0, m["watermark"])
            self.restoreState()
        self.setStrokeColor(LINE)
        self.setLineWidth(0.5)
        self.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm)
        self.setFont("Helvetica", 7)
        self.setFillColor(INK3)
        left = m.get("footer") or "Executive Admin · Bishnoi One Corporate Services"
        self.drawString(18 * mm, 10 * mm, left[:140])
        self.drawRightString(w - 18 * mm, 10 * mm, f"Page {self._pageNumber} of {total}")
        if self._pageNumber > 1 and m.get("running"):
            self.drawRightString(w - 18 * mm, h - 10 * mm, m["running"])


def _pagesize(paper: str, land: bool):
    ps = LETTER if paper.upper() == "LETTER" else A4
    return landscape(ps) if land else ps


def _table(columns: list[Column], rows: list[dict], totals: dict | None, width: float) -> Table:
    weights = [c.width or (2.2 if c.kind == "text" else 1.2) for c in columns]
    scale = width / sum(weights)
    widths = [w * scale for w in weights]
    right = lambda c: c.kind in ("money", "number")  # noqa: E731
    data = [[Paragraph(esc(c.label), S["headr" if right(c) else "head"]) for c in columns]]
    for r in rows:
        data.append([Paragraph(esc(fmt(r.get(c.key), c.kind if c.kind == "money" else None)), S["cellr" if right(c) else "cell"]) for c in columns])
    if totals:
        data.append([Paragraph(f"<b>{esc(fmt(totals.get(c.key), c.kind if c.kind == 'money' else None)) if c.key in totals else ('Total' if i == 0 else '')}</b>", S["cellr" if right(c) else "cell"]) for i, c in enumerate(columns)])
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), CANVAS),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if totals:
        style.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, INK))
    t.setStyle(TableStyle(style))
    return t


def _pairs(pairs: list[tuple[str, Any]], width: float, cols: int = 2) -> Table:
    cells = [[Paragraph(esc(k), S["label"]), Paragraph(esc(fmt(v)), S["value"])] for k, v in pairs]
    rows = []
    for i in range(0, len(cells), cols):
        chunk = cells[i : i + cols]
        row = []
        for c in chunk:
            row += c
        while len(row) < cols * 2:
            row.append("")
        rows.append(row)
    unit = width / cols
    t = Table(rows, colWidths=[unit * 0.36, unit * 0.64] * cols)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def render(spec: DocSpec) -> bytes:
    buf = io.BytesIO()
    pagesize = _pagesize(spec.paper, spec.landscape)
    doc = SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=20 * mm, title=spec.title, author="Executive Admin")
    width = pagesize[0] - 36 * mm
    story: list = []

    # Letterhead
    head_left = [Paragraph(f"<b>{esc(spec.company_name)}</b>", ParagraphStyle("co", parent=S["body"], fontSize=12, leading=15))]
    if spec.company_address:
        head_left.append(Paragraph(esc(spec.company_address), S["small"]))
    head_left.append(Paragraph("Executive Admin · Corporate Services", S["small"]))
    right = []
    if spec.control_number:
        right.append(Paragraph(f"<b>Control No. {esc(spec.control_number)}</b>" + (f" · v{spec.version}" if spec.version > 1 else ""), ParagraphStyle("cn", parent=S["body"], alignment=TA_RIGHT)))
    if spec.issue_date:
        right.append(Paragraph(f"Date: {fmt(spec.issue_date)}", ParagraphStyle("d", parent=S["small"], alignment=TA_RIGHT)))
    if spec.reference:
        right.append(Paragraph(f"Ref: {esc(spec.reference)}", ParagraphStyle("r", parent=S["small"], alignment=TA_RIGHT)))
    if spec.status_label:
        right.append(Paragraph(f"Status: <b>{esc(spec.status_label)}</b>", ParagraphStyle("st", parent=S["small"], alignment=TA_RIGHT)))
    lh = Table([[head_left, right]], colWidths=[width * 0.6, width * 0.4])
    lh.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.6, INK), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [lh, Spacer(1, 10), Paragraph(esc(spec.title.upper()), S["title"]), Spacer(1, 8)]

    if spec.info:
        story += [_pairs(spec.info, width), Spacer(1, 6)]

    for sec in spec.sections:
        kind = sec[0]
        if kind == "text":
            _, heading, body = sec
            if heading:
                story.append(Paragraph(esc(heading), S["h2"]))
            for para in str(body or "—").split("\n"):
                story.append(Paragraph(esc(para) or "&nbsp;", S["body"]))
        elif kind == "table":
            _, heading, columns, rows, totals = sec
            if heading:
                story.append(Paragraph(esc(heading), S["h2"]))
            story.append(_table(columns, rows, totals, width) if rows else Paragraph("No records.", S["small"]))
        elif kind == "checklist":
            _, heading, items = sec
            story.append(Paragraph(esc(heading), S["h2"]))
            for text, done in items:
                story.append(Paragraph(f"{'[x]' if done else '[  ]'}&nbsp;&nbsp;{esc(text)}", S["body"]))
        elif kind == "info":
            _, heading, pairs = sec
            if heading:
                story.append(Paragraph(esc(heading), S["h2"]))
            story.append(_pairs(pairs, width))
        story.append(Spacer(1, 6))

    if spec.certification:
        story += [Spacer(1, 6), Paragraph(esc(spec.certification), S["body"])]

    if spec.signatures:
        cols = 3 if len(spec.signatures) >= 3 else len(spec.signatures)
        unit = width / cols
        blocks = []
        for sgn in spec.signatures:
            parts = [Spacer(1, 22), Table([[""]], colWidths=[unit - 14], rowHeights=[1], style=TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.8, INK)]))]
            parts.append(Paragraph(f"<b>{esc(sgn.name) if sgn.name else '&nbsp;'}</b>", S["body"]))
            sub = ", ".join(x for x in (sgn.designation, sgn.department) if x)
            if sub:
                parts.append(Paragraph(esc(sub), S["small"]))
            parts.append(Paragraph(f"<b>{esc(sgn.role.upper())}</b> · Signature over printed name / date", S["small"]))
            if sgn.recorded:
                parts.append(Paragraph(esc(sgn.recorded), ParagraphStyle("rec", parent=S["small"], textColor=INK2)))
            blocks.append(parts)
        rows = [blocks[i : i + cols] for i in range(0, len(blocks), cols)]
        for r in rows:
            while len(r) < cols:
                r.append("")
        sig = Table(rows, colWidths=[unit] * cols)
        sig.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
        story += [Spacer(1, 10), KeepTogether([sig])]

    meta = {"watermark": spec.watermark, "footer": spec.footer_note, "running": f"{spec.title} · {spec.control_number or ''}"}
    doc.build(story, canvasmaker=lambda *a, **k: NumberedCanvas(*a, meta=meta, **k))
    return buf.getvalue()


def table_report(title: str, company_name: str, columns: list[Column], rows: list[dict], *, subtitle: list[str] | None = None, totals: dict | None = None, generated_by: str | None = None, land: bool = True, paper: str = "A4") -> bytes:
    info = [("Generated", datetime.now()), ("Generated by", generated_by), ("Records", len(rows))]
    for line in subtitle or []:
        k, _, v = line.partition(": ")
        info.append((k, v))
    spec = DocSpec(title=title, company_name=company_name, issue_date=date.today(), info=info, sections=[("table", None, columns, rows, totals)], landscape=land, paper=paper)
    return render(spec)
