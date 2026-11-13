"""
Document reading (OCR) for "upload the file, the system fills the form".

- Text comes from a PDF's own text layer when it has one; scans, photos and image-only PDFs go through
  RapidOCR (ONNX models bundled with the package). Everything runs on this server: document contents
  are never sent to an outside service, never stored, and never logged.
- Extraction is rule-based and explainable: each field carries a confidence and the line it came from,
  so the form can ask the user to verify anything uncertain. Nothing is saved until the user confirms.
- Passport/visa numbers are reduced to their last 4 characters before they leave this module.
"""

from __future__ import annotations

import io
import re
import threading
from dataclasses import dataclass, field
from datetime import date

# ------------------------------------------------------------------ text

_engine = None
_lock = threading.Lock()


def _ocr():
    global _engine
    with _lock:
        if _engine is None:
            import logging

            from rapidocr import RapidOCR

            logging.getLogger("RapidOCR").setLevel(logging.WARNING)
            # 4 threads gave the steadiest timing (~5 s a page on a 16-thread laptop); more threads only added jitter.
            _engine = RapidOCR(params={"EngineConfig.onnxruntime.intra_op_num_threads": 4, "EngineConfig.onnxruntime.inter_op_num_threads": 1})
    return _engine


def warm_up() -> None:
    """Load the models ahead of the first upload (called in a background thread at startup)."""
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (640, 120), "white")
        ImageDraw.Draw(img).text((20, 40), "Valid until December 31, 2026", fill="black")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        _ocr()(buf.getvalue())  # runs detection and recognition once so their sessions are ready
    except Exception:  # pragma: no cover - warm-up is best effort
        pass


@dataclass
class Line:
    text: str
    score: float  # 0..1 recognition confidence (1.0 for a PDF text layer)


def _ocr_image(img) -> list[Line]:
    from PIL import Image

    if not isinstance(img, Image.Image):
        img = Image.open(io.BytesIO(img))
    img = img.convert("RGB")
    longest = max(img.size)
    if longest > 2200:  # phone photos: keep it fast without losing small print
        f = 2200 / longest
        img = img.resize((int(img.width * f), int(img.height * f)))
    elif longest < 1000:  # tiny scans read better upscaled
        f = 1400 / longest
        img = img.resize((int(img.width * f), int(img.height * f)))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    r = _ocr()(buf.getvalue())
    if not r or r.txts is None:
        return []
    # Rebuild reading order: group boxes into rows by their vertical centre, then left to right.
    items = []
    for box, txt, sc in zip(r.boxes, r.txts, r.scores):
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append(((min(ys) + max(ys)) / 2, min(xs), max(ys) - min(ys), str(txt), float(sc)))
    items.sort()
    rows: list[list] = []
    for it in items:
        if rows and abs(rows[-1][0][0] - it[0]) < max(8.0, 0.5 * it[2]):
            rows[-1].append(it)
        else:
            rows.append([it])
    out = []
    for row in rows:
        row.sort(key=lambda x: x[1])
        out.append(Line("  ".join(x[3] for x in row), min(x[4] for x in row)))
    return out


def read_lines(data: bytes, filename: str) -> tuple[list[Line], str]:
    """Return (lines, method). method: text-layer | ocr | none."""
    name = filename.lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:3])
            lines = [Line(t.strip(), 1.0) for t in text.splitlines() if t.strip()]
            if sum(len(x.text) for x in lines) >= 40:
                return lines, "text-layer"
        except Exception:
            pass
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        lines = []
        for i in range(min(len(pdf), 2)):
            lines += _ocr_image(pdf[i].render(scale=2.2).to_pil())
        return lines, "ocr" if lines else "none"
    lines = _ocr_image(data)
    return lines, "ocr" if lines else "none"


# ------------------------------------------------------------------ dates

MONTHS = {m: i for i, ms in enumerate([
    (), ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
    ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december"),
]) for m in ms}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_DATE_PATTERNS = [
    ("mdy", re.compile(_MON + r"\s*(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})", re.I)),
    ("dmy", re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s*(?:day\s+of\s+)?" + _MON + r"\s*,?\s*(\d{4})", re.I)),
    ("ymd", re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")),
    ("num", re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b")),
]


def _month(s: str) -> int:
    k = s.lower().rstrip(".")
    return MONTHS.get(k) or MONTHS[k[:3]]


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        if 1900 <= y <= 2100:
            return date(y, m, d)
    except ValueError:
        return None
    return None


def find_dates(text: str) -> list[tuple[int, int, date]]:
    """All dates in a line as (start, end, date). Numeric dates are read month-first (Philippine usage)."""
    found: list[tuple[int, int, date]] = []
    taken: list[tuple[int, int]] = []
    for kind, rx in _DATE_PATTERNS:
        for m in rx.finditer(text):
            if any(not (m.end() <= a or m.start() >= b) for a, b in taken):
                continue
            g = m.groups()
            if kind == "mdy":
                d = _mk(int(g[2]), _month(g[0]), int(g[1]))
            elif kind == "dmy":
                d = _mk(int(g[2]), _month(g[1]), int(g[0]))
            elif kind == "ymd":
                d = _mk(int(g[0]), int(g[1]), int(g[2]))
            else:
                a, b, y = int(g[0]), int(g[1]), int(g[2])
                d = _mk(y, a, b) if a <= 12 else _mk(y, b, a)
            if d:
                found.append((m.start(), m.end(), d))
                taken.append((m.start(), m.end()))
    return sorted(found)


ISSUE_RX = re.compile(r"(date\s*(of\s*)?(issue|issuance|registration|incorporation|approval)|issued(\s*(on|date))?|date\s*issued|registered(\s*on)?|date\s*registered|registration\s*date|incorporated(\s*on)?|valid\s*from|effective(ity)?(\s*date)?|commenc\w*|start(ing)?(\s*date)?|from)\s*[:.]?\s*$", re.I)
EXPIRY_RX = re.compile(r"(valid\s*(until|thru|through|up\s*to|till)|validity(\s*date)?|expir\w*(\s*date)?|date\s*of\s*expiry|good\s*until|until|ending|end\s*date|to|renew\w*\s*(on\s*or\s*)?before|on\s*or\s*before)\s*[:.]?\s*$", re.I)


@dataclass
class Found:
    value: str
    confidence: float
    source: str


@dataclass
class Result:
    fields: dict[str, Found] = field(default_factory=dict)

    def put(self, name: str, value, confidence: float, source: str):
        if value in (None, ""):
            return
        cur = self.fields.get(name)
        if cur is None or confidence > cur.confidence:
            self.fields[name] = Found(str(value), round(min(confidence, 0.99), 2), source[:160])


def _dates(lines: list[Line], res: Result, issue_key: str, expiry_key: str) -> None:
    unlabeled: list[tuple[date, Line]] = []
    for i, ln in enumerate(lines):
        ds = find_dates(ln.text)
        if not ds:
            continue
        # "from X to Y" / "X - Y" on one line → a period
        if len(ds) >= 2 and re.search(r"\b(to|until|thru|through)\b|\s[-–]\s", ln.text[ds[0][1]:ds[1][0]], re.I):
            res.put(issue_key, ds[0][2].isoformat(), 0.9 * ln.score, ln.text)
            res.put(expiry_key, ds[1][2].isoformat(), 0.9 * ln.score, ln.text)
            continue
        for start, _end, d in ds:
            before = ln.text[:start].strip()
            if not before or not re.search(r"[a-z]", before[-30:], re.I):
                before = lines[i - 1].text if i > 0 and not find_dates(lines[i - 1].text) else ""
            tail = before[-45:]
            if EXPIRY_RX.search(tail):
                res.put(expiry_key, d.isoformat(), 0.95 * ln.score, ln.text)
            elif ISSUE_RX.search(tail):
                res.put(issue_key, d.isoformat(), 0.95 * ln.score, ln.text)
            elif re.search(r"birth|dob|born", tail, re.I):
                continue
            else:
                unlabeled.append((d, ln))
    if unlabeled:
        uniq = sorted({d: ln for d, ln in unlabeled}.items())
        if expiry_key not in res.fields and len(uniq) >= 2:
            res.put(expiry_key, uniq[-1][0].isoformat(), 0.55, uniq[-1][1].text)
        if issue_key not in res.fields and (len(uniq) >= 2 or expiry_key in res.fields):
            first = uniq[0]
            if expiry_key not in res.fields or first[0].isoformat() < res.fields[expiry_key].value:
                res.put(issue_key, first[0].isoformat(), 0.5, first[1].text)


# ------------------------------------------------------------------ names and numbers

TITLE_WORDS = r"(permit|certificate|certification|registration|license|licence|clearance|accreditation|passport|visa|contract|lease|agreement|policy|information\s+sheet|receipt)"


def _title_case(s: str) -> str:
    small = {"of", "and", "the", "for", "to", "in", "on", "a", "an"}
    s = re.sub(r"\b(OF|AND|THE|FOR|ON)(?=[A-Z]{4,}\b)", r"\1 ", s)
    words = re.sub(r"\s+", " ", s.strip(" :-")).split(" ")
    out = []
    for n, w in enumerate(words):
        lw = w.lower()
        if w.isupper() and len(w) <= 4 and lw not in small and n > 0 and w not in ("FIRE", "INC", "CORP", "LTD", "CO"):  # acronyms: SEC, BIR, GIS
            out.append(w)
        elif lw in small and n > 0:
            out.append(lw)
        else:
            out.append(lw[:1].upper() + lw[1:])
    return " ".join(out).replace("'S ", "'s ")


def _title(lines: list[Line], res: Result) -> None:
    best = None
    for i, ln in enumerate(lines[:18]):
        t = ln.text.strip()
        if not re.search(TITLE_WORDS, t, re.I) or ":" in t or re.search(r"\bno\.?\b|number|#", t, re.I) or find_dates(t):
            continue
        if not (4 <= len(t) <= 70):
            continue
        score = (0.9 if t.isupper() else 0.75) - i * 0.01
        if best is None or score > best[0]:
            best = (score, t, ln)
    if best:
        res.put("document_name", _title_case(best[1]), best[0] * best[2].score, best[2].text)


_NO_RX = re.compile(r"(?:(permit|registration|reg|certificate|cert|fsic|license|licence|policy|o\.?\s*r|official\s+receipt|control|company\s+reg(?:istration)?|sec\s+reg(?:istration)?|tin|account|document|passport|visa|contract|lease|reference|ref)\.?\s*)?(?:no|number|num|#)\.?\s*[:.]?\s*([A-Z0-9][A-Z0-9\-/]{2,30}(?:\s[A-Z0-9\-]{1,10})?)", re.I)


def _number(lines: list[Line], res: Result, key: str, prefer: str | None = None) -> None:
    for i, ln in enumerate(lines):
        for m in _NO_RX.finditer(ln.text):
            label, val = (m.group(1) or ""), m.group(2).strip()
            if not re.search(r"\d", val) or find_dates(val):
                continue
            conf = 0.9 if label else 0.7
            if prefer and re.search(prefer, label or "", re.I):
                conf = 0.95
            res.put(key, val.rstrip(".,"), conf * ln.score, ln.text)


def _holder(lines: list[Line]) -> tuple[str, Line] | None:
    rx = re.compile(r"(business\s+name|registered\s+name|company\s+name|corporate\s+name|name\s+of\s+(business|company|corporation|establishment)|taxpayer|registrant|owner|grantee|issued\s+to)\s*[:.]?\s*(.+)", re.I)
    for ln in lines:
        m = rx.search(ln.text)
        if m and len(m.group(3).strip()) > 2:
            return m.group(3).strip(" :."), ln
    return None


REG_TYPES = [
    (r"bureau\s+of\s+customs|\bboc\b|importer|customs", "Bureau of Customs"),
    (r"general\s+information\s+sheet|\bgis\b", "GIS"),
    (r"securities\s+and\s+exchange|\bsec\b", "SEC"),
    (r"mayor'?s\s+permit|business\s+permit|business\s+plate|bplo", "Business Permit"),
    (r"pest\s+control|fumigation|termite", "Pest Control"),
    (r"fire\s+(safety|extinguisher|inspection)|\bfsic\b|bureau\s+of\s+fire", "Fire Extinguishers"),
]


# ------------------------------------------------------------------ passports (MRZ)

COUNTRIES = {"PHL": "Philippines", "JPN": "Japan", "USA": "United States", "CHN": "China", "IND": "India", "KOR": "South Korea", "SGP": "Singapore",
             "GBR": "United Kingdom", "AUS": "Australia", "CAN": "Canada", "HKG": "Hong Kong", "TWN": "Taiwan", "THA": "Thailand", "VNM": "Vietnam",
             "IDN": "Indonesia", "MYS": "Malaysia", "ARE": "United Arab Emirates", "SAU": "Saudi Arabia", "DEU": "Germany", "FRA": "France",
             "ITA": "Italy", "ESP": "Spain", "NLD": "Netherlands", "NZL": "New Zealand", "QAT": "Qatar", "KWT": "Kuwait"}


def _mrz(lines: list[Line], res: Result) -> bool:
    cand = [re.sub(r"\s+", "", ln.text).replace("«", "<").upper() for ln in lines]
    for i, l1 in enumerate(cand[:-1]):
        if not re.match(r"^P[<A-Z][A-Z<]{3}[A-Z<]{5,}", l1) or "<<" not in l1:
            continue
        country = COUNTRIES.get(l1[2:5].replace("<", ""), l1[2:5].replace("<", ""))
        names = l1[5:].split("<<", 1)
        surname = names[0].replace("<", " ").strip().title()
        given = re.sub(r"\s+", " ", names[1].replace("<", " ")).strip().title() if len(names) > 1 else ""
        src = "Machine-readable zone"
        res.put("holder_name", f"{given} {surname}".strip(), 0.95, src)
        res.put("last_name", surname, 0.95, src)
        if given:
            res.put("first_name", given, 0.9, src)
        res.put("country", country, 0.95, src)
        res.put("document_kind", "passport", 0.97, src)
        m = re.match(r"^([A-Z0-9<]{9})(\d)([A-Z<]{3})(\d{6})\d([MF<])(\d{6})", cand[i + 1])
        if m:  # line 2 is often the hardest to read; use it only when it parses cleanly
            res.put("number_last4", m.group(1).replace("<", "")[-4:], 0.95, src)
            yy, mm, dd = int(m.group(4)[:2]), int(m.group(4)[2:4]), int(m.group(4)[4:])
            dob = _mk(2000 + yy if 2000 + yy <= date.today().year else 1900 + yy, mm, dd)
            if dob:
                res.put("birth_date", dob.isoformat(), 0.95, src)
            if m.group(5) in "MF" and m.group(5) != "<":
                res.put("gender", "male" if m.group(5) == "M" else "female", 0.95, src)
            exp = _mk(2000 + int(m.group(6)[:2]), int(m.group(6)[2:4]), int(m.group(6)[4:]))
            if exp:
                res.put("expiry_date", exp.isoformat(), 0.97, src)
        return True
    return False


# ------------------------------------------------------------------ per document type

def extract(lines: list[Line], kind: str) -> Result:
    res = Result()
    text = "\n".join(ln.text for ln in lines)
    if kind == "registration":
        _title(lines, res)
        for rx, label in REG_TYPES:
            if re.search(rx, text, re.I):
                res.put("registration_type", label, 0.85, re.search(rx, text, re.I).group(0))
                break
        _number(lines, res, "registration_number", prefer=r"permit|registration|reg|certificate|cert|license|licence|sec")
        _dates(lines, res, "registration_date", "expiry_date")
        h = _holder(lines)
        if h:
            res.put("holder_name", h[0], 0.8 * h[1].score, h[1].text)
    elif kind == "travel_document":
        sur = next((re.search(r"surname\s*[:./]?\s*([A-Za-z' -]{2,40})", ln.text, re.I) for ln in lines if re.search(r"surname", ln.text, re.I)), None)
        giv = next((re.search(r"given\s*names?\s*[:./]?\s*([A-Za-z' -]{2,60})", ln.text, re.I) for ln in lines if re.search(r"given\s*name", ln.text, re.I)), None)
        mid = next((re.search(r"middle\s*name\s*[:./]?\s*([A-Za-z' -]{2,40})", ln.text, re.I) for ln in lines if re.search(r"middle\s*name", ln.text, re.I)), None)
        if sur and giv:
            res.put("holder_name", f"{giv.group(1).strip().title()} {sur.group(1).strip().title()}", 0.9, "Surname / Given names")
            res.put("first_name", giv.group(1).strip().title(), 0.92, "Given names")
            res.put("last_name", sur.group(1).strip().title(), 0.92, "Surname")
        if mid:
            res.put("middle_name", mid.group(1).strip().title(), 0.9, "Middle name")
        for ln in lines:
            m = re.search(r"\b(sex|gender)\s*[:./]?\s*(m|f|male|female)\b", ln.text, re.I)
            if m:
                res.put("gender", "male" if m.group(2).lower().startswith("m") else "female", 0.9 * ln.score, "Sex")
            if re.search(r"birth|\bdob\b", ln.text, re.I):
                ds = find_dates(ln.text)
                if ds:
                    res.put("birth_date", ds[0][2].isoformat(), 0.9 * ln.score, "Date of birth")
        for ln in lines:
            m = re.search(r"(passport|document|visa|control)\s*(no|number)\.?\s*[:./]?\s*([A-Z0-9]{5,12})", ln.text, re.I)
            if m:
                res.put("number_last4", m.group(3)[-4:], 0.9 * ln.score, "Document number")
        if not _mrz(lines, res):
            if re.search(r"\bvisa\b", text, re.I):
                res.put("document_kind", "visa", 0.8, "Visa")
            elif re.search(r"passport|pasaporte", text, re.I):
                res.put("document_kind", "passport", 0.8, "Passport")
            for ln in lines:
                m = re.search(r"(passport|document|visa|control)\s*(no|number)\.?\s*[:.]?\s*([A-Z0-9]{5,12})", ln.text, re.I)
                if m:
                    res.put("number_last4", m.group(3)[-4:], 0.85 * ln.score, "Document number")
            _dates(lines, res, "issue_date", "expiry_date")
            for ln in lines:
                m = re.search(r"(type\s+of\s+visa|visa\s+type|visa\s+category|category|class)\s*[:.]?\s*(.{2,40})", ln.text, re.I)
                if m:
                    res.put("visa_type", m.group(2).strip(" :."), 0.8 * ln.score, ln.text)
            for code, name in COUNTRIES.items():
                if re.search(rf"\b{re.escape(name)}\b|\b{code}\b", text, re.I) and name != "Philippines":
                    res.put("country", name, 0.6, name)
                    break
            else:
                if re.search(r"philippines|pilipinas", text, re.I):
                    res.put("country", "Philippines", 0.6, "Philippines")
            for ln in lines:
                m = re.search(r"(name|surname|holder)\s*[:.]\s*([A-Z][A-Za-z ,.'-]{3,60})", ln.text)
                if m:
                    res.put("holder_name", m.group(2).strip(" ,."), 0.7 * ln.score, ln.text)
        else:
            _dates(lines, res, "issue_date", "expiry_date")
    elif kind == "contract":
        for i, ln in enumerate(lines[:20]):
            if re.search(r"(contract|lease|agreement)", ln.text, re.I) and len(ln.text) <= 80 and not find_dates(ln.text):
                res.put("title", _title_case(ln.text), 0.8 * ln.score - i * 0.01, ln.text)
                break
        for ln in lines:
            m = re.search(r"(lessor|landlord|owner)\s*[:,]?\s*([A-Z][A-Za-z0-9 .,&'-]{3,80}?)(?:,|\(|$| hereinafter| with address| of legal age)", ln.text, re.I)
            if m and not re.search(r"^(and|the)\b", m.group(2), re.I):
                res.put("lessor_name", m.group(2).strip(" ,."), 0.75 * ln.score, ln.text)
                break
        for ln in lines:
            for label, key in ((r"monthly\s+rent(al)?|rent(al)?\s+(of|fee|amount)|per\s+month|a\s+month", "monthly_rent_php"), (r"(security\s+)?deposit", "deposit_php")):
                if re.search(label, ln.text, re.I):
                    m = re.search(r"(?:php|p|₱)\s*([\d,]+(?:\.\d{2})?)|([\d,]{4,}(?:\.\d{2})?)", ln.text, re.I)
                    if m:
                        res.put(key, (m.group(1) or m.group(2)).replace(",", ""), 0.85 * ln.score, ln.text)
        _dates(lines, res, "start_date", "end_date")
    elif kind == "vehicle_renewal":
        _number(lines, res, "reference", prefer=r"o\.?\s*r|official\s+receipt|policy|c\.?\s*r|registration")
        _dates(lines, res, "_issued", "new_date")
        res.fields.pop("_issued", None)
        for ln in lines:
            if re.search(r"total|amount|premium|paid", ln.text, re.I):
                m = re.search(r"(?:php|p|₱)\s*([\d,]+(?:\.\d{2})?)|([\d,]{3,}\.\d{2})", ln.text, re.I)
                if m:
                    res.put("cost_php", (m.group(1) or m.group(2)).replace(",", ""), 0.75 * ln.score, ln.text)
        for ln in lines:
            m = re.search(r"([A-Z][A-Za-z&.' ]{2,40}(insurance|assurance)( (co|corp|corporation|inc|company)\.?)?)", ln.text, re.I)
            if m:
                res.put("insurer", m.group(1).strip(), 0.75 * ln.score, ln.text)
                break
    elif kind in ("fleet_card", "corporate_card"):
        _card(lines, res, kind)
    elif kind == "vehicle":
        _orcr(lines, res)
    return res


# ------------------------------------------------------------------ payment and fleet cards

FUEL_PROVIDERS = ["Shell", "Petron", "Caltex", "Seaoil", "Phoenix", "Cleanfuel", "Total"]
BANKS = [("BDO", r"\bbdo\b|banco\s+de\s+oro"), ("BPI", r"\bbpi\b|bank\s+of\s+the\s+philippine\s+islands"), ("Metrobank", r"metrobank|metropolitan\s+bank"),
         ("Security Bank", r"security\s*bank"), ("UnionBank", r"union\s*bank"), ("RCBC", r"\brcbc\b"), ("PNB", r"\bpnb\b|philippine\s+national\s+bank"),
         ("LANDBANK", r"land\s*bank"), ("China Bank", r"china\s*bank"), ("EastWest", r"east\s*west"), ("HSBC", r"\bhsbc\b"), ("Citibank", r"citi\s*bank|\bciti\b"),
         ("AUB", r"\baub\b|asia\s+united"), ("Maybank", r"maybank"), ("PSBank", r"psbank")]
_CARD_WORDS = r"(valid|thru|through|from|good|member|since|expires?|exp|month|year|card|debit|credit|prepaid|platinum|gold|classic|business|corporate|fleet|visa|mastercard|jcb|amex|signature|world|electronic|bank|shell|petron|caltex|seaoil|phoenix|diesel|unleaded|premium)"


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total, alt = total + d, not alt
    return total % 10 == 0


def _card(lines: list[Line], res: Result, kind: str) -> None:
    """Card photos: only the LAST 4 digits leave this function. CVV/security codes are never read."""
    text = "\n".join(ln.text for ln in lines)
    for ln in lines:
        compact = re.sub(r"[^\d]", " ", ln.text)
        for m in re.finditer(r"(?:\d[ ]?){13,19}", compact):
            digits = re.sub(r"\D", "", m.group(0))
            if 13 <= len(digits) <= 19:
                conf = (0.95 if _luhn(digits) else 0.7) * ln.score
                res.put("card_number_last4" if kind == "fleet_card" else "card_last4", digits[-4:], conf, "Card number")
                break
    for ln in lines:
        m = re.search(r"(valid\s*thru|valid\s*through|good\s*thru|expires?|exp(iry)?\.?|until)\s*[:.]?\s*(\d{2})\s*[/\-.]\s*(\d{2,4})", ln.text, re.I) or re.search(r"\b(0[1-9]|1[0-2])\s*/\s*(\d{2})\b", ln.text)
        if m:
            mm, yy = (m.group(3), m.group(4)) if m.lastindex and m.lastindex >= 4 else (m.group(1), m.group(2))
            month, year = int(mm), int(yy) + (2000 if len(yy) == 2 else 0)
            if 1 <= month <= 12 and 2000 <= year <= 2100 and kind == "corporate_card":
                res.put("expiry_month", str(month), 0.9 * ln.score, "Valid thru")
                res.put("expiry_year", str(year), 0.9 * ln.score, "Valid thru")
            break
    # Holder: an embossed line of 2-4 words in capitals that is not a brand or card wording.
    for ln in lines:
        t = ln.text.strip()
        if re.fullmatch(r"[A-Z][A-Z.'-]+(?: [A-Z][A-Z.'-]+){1,3}", t) and not re.search(_CARD_WORDS, t, re.I) and not any(re.search(rx, t, re.I) for _, rx in BANKS):
            res.put("holder_name", t.title(), 0.75 * ln.score, "Card holder")
            break
    if kind == "fleet_card":
        for p in FUEL_PROVIDERS:
            if re.search(rf"\b{p}\b", text, re.I):
                res.put("provider", p, 0.9, p)
                break
        for f in ("Diesel", "Unleaded", "Premium"):
            if re.search(rf"\b{f}\b", text, re.I):
                res.put("fuel_type", f, 0.85, f)
                break
        for ln in lines:
            m = re.search(r"\b([A-Z]{3}\s?\d{3,4}|[A-Z]{2}\s?\d{4,5})\b", ln.text)
            if m and not re.search(r"\d{5,}", ln.text.replace(" ", "")[: m.start()] or ""):
                res.put("plate_number", re.sub(r"([A-Z]+)\s?(\d+)", r"\1 \2", m.group(1)), 0.8 * ln.score, "Plate")
                break
    else:
        for name, rx in BANKS:
            if re.search(rx, text, re.I):
                res.put("bank", name, 0.9, name)
                break
        if re.search(r"\bdebit\b", text, re.I):
            res.put("card_type", "debit", 0.85, "Debit")
        elif re.search(r"\bprepaid\b", text, re.I):
            res.put("card_type", "prepaid", 0.85, "Prepaid")
        elif re.search(r"\bcredit\b|platinum|gold|signature|world|business|corporate", text, re.I):
            res.put("card_type", "credit", 0.7, "Credit")


# ------------------------------------------------------------------ vehicle OR/CR (LTO)

def _orcr(lines: list[Line], res: Result) -> None:
    labels = [
        ("plate_number", r"plate\s*(no|number)\.?"),
        ("conduction_sticker", r"conduction\s*(sticker)?\s*(no|number)?\.?|c\.?\s*s\.?\s*no\.?"),
        ("make", r"\bmake\b|\bbrand\b"),
        ("model", r"\bseries\b|(?<!year )(?<!year)\bmodel\b(?!\s*year)"),
        ("year_model", r"year\s*model|model\s*year"),
        ("color", r"\bcolou?r\b"),
        ("owner_name", r"owner'?s?\s*name|registered\s*owner|\bowner\b"),
        ("body_type", r"body\s*type|type\s*of\s*body|classification"),
    ]
    for i, ln in enumerate(lines):
        for key, rx in labels:
            m = re.search(rf"({rx})\s*[:.]?\s*(.*)$", ln.text, re.I)
            if not m:
                continue
            val = m.group(m.lastindex).strip(" :.")
            # value cut at the next label on the same line
            for _, other in labels:
                cut = re.search(rf"\s({other})\s*[:.]", val, re.I)
                if cut:
                    val = val[: cut.start()].strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1].text.strip(" :.")
            if not val:
                continue
            if key == "year_model":
                y = re.search(r"(19|20)\d{2}", val)
                if y:
                    res.put(key, y.group(0), 0.9 * ln.score, ln.text)
            elif key == "plate_number":
                p = re.search(r"[A-Z]{2,3}\s?\d{3,5}", val.upper())
                if p:
                    res.put(key, re.sub(r"([A-Z]+)\s?(\d+)", r"\1 \2", p.group(0)), 0.9 * ln.score, ln.text)
            elif key == "body_type":
                for vt, rx2 in (("Van", r"van|uv\b|utility"), ("SUV", r"suv|sport\s*utility"), ("Pickup", r"pick\s*-?up"), ("Truck", r"truck"), ("Motorcycle", r"motor\s*cycle|mc\b"), ("Sedan", r"sedan|car\b")):
                    if re.search(rx2, val, re.I):
                        res.put("vehicle_type", vt, 0.8 * ln.score, ln.text)
                        break
            else:
                res.put(key, _title_case(val[:60]) if key in ("make", "model", "color", "owner_name") else val[:40], 0.85 * ln.score, ln.text)
    _dates(lines, res, "_registered", "registration_renewal_date")
    res.fields.pop("_registered", None)
