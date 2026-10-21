#!/usr/bin/env python3
"""OCR every receipt image in a folder and extract its date and total amount.

aip mode: one JSON object on stdin {"state": {"image_dir": ...}}; prints
{"records": [...], "flagged": [...], "needs_review": bool}.
CLI mode: python3 extract_receipts.py <image_dir>  (prints the same JSON).

Each image is OCRed with Tesseract in several passes (grayscale / 2x upscale +
autocontrast / upscale + binarize, each with --psm 4 and --psm 6). Date and total
are extracted from every pass independently and the most-voted value wins, which
absorbs most single-pass misreads ("1000" for "10.00", "38/02/18" for "28/02/18").
"""
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VARIANTS = ["gray", "up", "upbin"]
PSMS = [4, 6]

# --- total amount -----------------------------------------------------------
# Keyword priority, most specific first (task hint). Level 5 (bare AMOUNT) is the
# weakest because item-table headers also say AMOUNT.
TOT = r"T[O0]T[A4][L1I!|](?!S)"
LEVELS = [
    (1, re.compile(r"GRAND\s*" + TOT)),
    (2, re.compile(TOT + r"\s*[:.]?\s*\(?\s*R[MN]\b")),
    (3, re.compile(TOT + r"\s*AMOUNT")),
    (4, re.compile(r"\b" + TOT + r"|\b(?:AMOUNT|BALANCE)\s*DUE\b|\bNETT?\s*" + TOT)),
    (5, re.compile(r"\bAMOUNT\b")),
]
# Lines with these are subtotals/taxes/payments, never the total.
EXCLUDE = re.compile(
    r"SUB\s*-?\s*" + TOT + r"|\bTAX|\bGST\b|\bSST\b|DISCOUNT|CHANGE|CASH\s*TENDERED"
    r"|\bQTY\b|QUANTITY|\bITEMS?\b|\bEXCL|SAVING|POINT|\bCASH\b|\bVISA\b|MASTER|CARD"
)
# "Total incl. GST 17.76" is the total: GST/TAX/SST alone does not exclude a line
# that says the amount INCLUDES it.
INCLUSIVE = re.compile(r"[I1L\[|]NC(?:LUSIVE|LUDING|LUDES|L|\]|\.|\b)")
SUMMARY = re.compile(r"(GST|TAX|SST)\s*SUMMARY|SUMMARY\s*(AMOUNT|CODE)")
ROUNDED = re.compile(r"ROUND|\bADJ|AFTER")

AMOUNT_RE = re.compile(
    r"(?<![\d.,])("
    r"\d{1,3}(?:,\d{3})+\.\d{2}"          # 1,234.56
    r"|\d+\s?[.,:]\s?\d{2}"                # 12.30 / 12,30 / 12 .30 / 12:30
    r"|\d+\s\d{2}(?=\s*[A-Z|]?\s*$)"       # 10 00 at line end (printed without point)
    r")(?![\d])"
)


def parse_amount(tok):
    tok = tok.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d{2}", tok):
        tok = tok.replace(",", "")
    elif re.fullmatch(r"\d+\d{2}", tok) and not re.search(r"[.,:]", tok):
        tok = tok[:-2] + "." + tok[-2:]
    else:
        tok = re.sub(r"[.,:]", ".", tok)
    try:
        return f"{float(tok):.2f}"
    except ValueError:
        return None


def last_amount(text):
    vals = [parse_amount(m.group(1)) for m in AMOUNT_RE.finditer(text)]
    vals = [v for v in vals if v is not None]
    return vals[-1] if vals else None


def is_excluded(line):
    if not EXCLUDE.search(line):
        return False
    # a rounded/adjusted total that mentions GST is still the payable total
    if INCLUSIVE.search(line) or ROUNDED.search(line):
        rest = EXCLUDE.sub(lambda m: "" if re.match(r"\bTAX|\bGST|\bSST", m.group(0)) else m.group(0), line)
        return bool(EXCLUDE.search(rest))
    return True


def find_total(text):
    """Best keyword level in one OCR pass and its hits, in line order:
    (level, [(value, is_rounded_line, how), ...]) or (None, [])."""
    lines = [l.upper() for l in text.splitlines()]
    # GST/tax summary tables follow the totals and repeat "Total" rows; ignore them.
    cut = next((i for i, l in enumerate(lines) if SUMMARY.search(l)), len(lines))
    lines = lines[:cut]
    for level, kw in LEVELS:
        hits = []
        for i, line in enumerate(lines):
            m = kw.search(line)
            if not m or is_excluded(line):
                continue
            after = line[m.end():]
            val, how = last_amount(after), "same-line"
            if val is None and not re.search(r"\d", after):
                # keyword and amount split across two lines: last number on next line
                nxt = next((l for l in lines[i + 1:] if l.strip()), "")
                val, how = last_amount(nxt), "next-line"
            if val is not None:
                hits.append((val, bool(ROUNDED.search(line)), how))
        if hits:
            return level, hits
    return None, []


def pick(hits):
    """The pass's answer: the last rounded/adjusted total if any, else the last hit
    (the payable total is printed after intermediate excl./incl. totals)."""
    rounded = [h for h in hits if h[1]]
    return (rounded or hits)[-1]


# --- date -------------------------------------------------------------------
MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
MON = r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*"
DATE_RES = [
    ("ymd", re.compile(r"(?<!\d)(20\d{2})\s?[/\-.]\s?(\d{1,2})\s?[/\-.]\s?(\d{1,2})(?!\d)")),
    ("dmy", re.compile(r"(?<!\d)(\d{1,2})\s?[/\-.]\s?(\d{1,2})\s?[/\-.]\s?(\d{4}|\d{2})(?!\d)")),
    ("dMy", re.compile(r"(?<!\d)(\d{1,2})[\s\-/.,]*" + MON + r"[\s\-/.,]*(\d{4}|\d{2})(?!\d)")),
    ("Mdy", re.compile(MON + r"[\s\-/.]*(\d{1,2})(?:ST|ND|RD|TH)?[\s,\-/.]+(\d{4})(?!\d)")),
]


def valid(y, m, d):
    import datetime
    if y < 100:
        y += 2000
    if not 2000 <= y <= 2035:
        return None
    try:
        return datetime.date(y, m, d).isoformat()
    except ValueError:
        return None


def overlapping(rx, line):
    """Groups of every match starting at any position ("#19- 18/01/2018" must
    still yield 18/01/2018 after the false start at 19-18/01)."""
    out, pos = [], 0
    while True:
        m = rx.search(line, pos)
        if not m:
            return out
        out.append(m.groups())
        pos = m.start() + 1


def find_dates(text):
    """All plausible ISO dates in one OCR pass, as (iso, on_date_line)."""
    out = []
    for line in text.upper().splitlines():
        dl = bool(re.search(r"DATE|DATA|DTE", line))
        for kind, rx in DATE_RES:
            for g in overlapping(rx, line):
                if kind == "ymd":
                    iso = valid(int(g[0]), int(g[1]), int(g[2]))
                elif kind == "dmy":
                    a, b, y = int(g[0]), int(g[1]), int(g[2])
                    # Malaysian/UK receipts are day-first; swap only when that is impossible.
                    iso = valid(y, b, a) or (valid(y, a, b) if b > 12 and a <= 12 else None)
                    if not iso and b > 12 and str(b)[0] in "689":
                        # OCR reads a leading 0 of the month as 6/8/9 ("19/62/2018")
                        iso = valid(y, int("0" + str(b)[1]), a)
                elif kind == "dMy":
                    iso = valid(int(g[2]), MONTHS[g[1][:3]], int(g[0]))
                else:
                    iso = valid(int(g[2]), MONTHS[g[0][:3]], int(g[1]))
                if iso:
                    out.append((iso, dl))
    return out


# --- OCR --------------------------------------------------------------------
def prepare(img, variant):
    g = ImageOps.grayscale(ImageOps.exif_transpose(img))
    if variant == "gray":
        return g
    s = 2.0 if max(g.size) < 2000 else 1.5
    up = ImageOps.autocontrast(g.resize((int(g.width * s), int(g.height * s)), Image.LANCZOS))
    return up if variant == "up" else up.point(lambda p: 255 if p > 150 else 0)


def ocr_pass(path, variant, psm):
    try:
        with Image.open(path) as img:
            return pytesseract.image_to_string(prepare(img, variant), config=f"--psm {psm}")
    except Exception:
        return ""


def vote(values):
    c = Counter(v for v in values if v is not None)
    if not c:
        return None, 0.0
    best, n = c.most_common(1)[0]
    return best, n / len(values)


def analyse(path, texts):
    passes = [find_total(t) for t in texts]
    best_level = min((lv for lv, _ in passes if lv is not None), default=None)
    top = [(pick(h), h) for lv, h in passes if lv is not None and lv == best_level]
    score = Counter()
    for (val, _, _), hits in top:
        score[val] += 1
        # a value printed after a competing total in the same pass is the later, final one
        if any(h[0] != val for h in hits):
            score[val] += 1
    # tie-break: how many passes show the value anywhere (subtotal, payment, item lines)
    support = {v: sum(bool(re.search(r"(?<![\d.])" + re.escape(v) + r"(?!\d)", t.replace(",", ".")))
                      for t in texts) for v in score}
    total = max(score, key=lambda v: (score[v], support[v])) if score else None
    share = (sum(1 for (v, _, _), _ in top if v == total) / len(top)) if top else 0.0
    hows = {how for (v, _, how), _ in top if v == total}
    votes = Counter(v for (v, _, _), _ in top)

    date_votes = Counter()
    for t in texts:
        seen = set()
        for iso, dl in find_dates(t):
            if iso not in seen:
                date_votes[iso] += 2 if dl else 1
                seen.add(iso)
    date = date_votes.most_common(1)[0][0] if date_votes else None
    dshare = date_votes[date] / sum(date_votes.values()) if date else 0.0

    reasons = []
    if date is None:
        reasons.append("no date found")
    elif dshare < 0.6:
        reasons.append("passes disagree on date")
    if total is None:
        reasons.append("no total found")
    else:
        if share < 0.75:
            reasons.append("passes disagree on total")
        if best_level >= 4 and len(top) < 3:
            reasons.append("total only from a weak keyword in few passes")
        if hows == {"next-line"}:
            reasons.append("total taken from the line after the keyword")
    return {
        "filename": path.name,
        "date": date,
        "total_amount": total,
        "total_keyword_level": best_level,
        "total_votes": dict(votes),
        "date_votes": dict(date_votes.most_common(4)),
        "review_reasons": reasons,
    }


def run(image_dir):
    d = Path(image_dir)
    if not d.is_dir():
        raise SystemExit(f"image_dir not found or not a directory: {image_dir}")
    paths = sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not paths:
        raise SystemExit(f"no image files in {image_dir}")
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")  # one core per tesseract; parallelise passes instead
    jobs = [(p, v, s) for p in paths for v in VARIANTS for s in PSMS]
    with ThreadPoolExecutor(max_workers=max(2, os.cpu_count() or 2)) as ex:
        texts = list(ex.map(lambda j: ocr_pass(*j), jobs))
    k = len(VARIANTS) * len(PSMS)
    records = [analyse(p, texts[i * k:(i + 1) * k]) for i, p in enumerate(paths)]
    flagged = [r["filename"] for r in records if r["review_reasons"]]
    return {"records": records, "flagged": flagged, "needs_review": bool(flagged)}


def main():
    if len(sys.argv) > 1:
        print(json.dumps(run(sys.argv[1]), indent=1))
        return
    payload = json.load(sys.stdin)
    print(json.dumps(run(payload["state"]["image_dir"])))


if __name__ == "__main__":
    main()
