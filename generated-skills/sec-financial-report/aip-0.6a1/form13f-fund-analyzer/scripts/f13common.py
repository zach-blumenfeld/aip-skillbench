"""Shared helpers for the SEC Form 13F dataset scripts (pandas only; rapidfuzz in search.py).

Dataset layout (SEC "Form 13F data sets", one folder per quarter, tab-separated):
  COVERPAGE.tsv   one row per filing: ACCESSION_NUMBER, REPORTCALENDARORQUARTER, ISAMENDMENT,
                  AMENDMENTTYPE, FILINGMANAGER_NAME, REPORTTYPE, ...
  INFOTABLE.tsv   one row per holding: ACCESSION_NUMBER, NAMEOFISSUER, TITLEOFCLASS, CUSIP,
                  VALUE (whole US dollars), SSHPRNAMT, SSHPRNAMTTYPE (SH/PRN), PUTCALL, ...
  SUMMARYPAGE.tsv TABLEENTRYTOTAL / TABLEVALUETOTAL per filing (cross-check).
"""
import json
import os
import sys

import pandas as pd

INFO_COLS = ["ACCESSION_NUMBER", "NAMEOFISSUER", "TITLEOFCLASS", "CUSIP", "VALUE",
             "SSHPRNAMT", "SSHPRNAMTTYPE", "PUTCALL"]
CHUNK = 400_000

# The source skill's common-stock TITLEOFCLASS list, with its missing commas fixed.
# Only used for a secondary, informational count: TITLEOFCLASS is free text and this list
# misses many real share classes ("shs", "ads", "ord", "com ser c", ...).
TITLE_CLASS_OF_STOCKS = [
    "com", "common stock", "cl a", "com new", "class a", "stock", "common", "com cl a",
    "com shs", "sponsored adr", "sponsored ads", "adr", "equity", "cmn", "cl b", "ord shs",
    "cl a com", "class a com", "cap stk cl a", "comm stk", "cl b new", "cap stk cl c",
    "cl a new", "foreign stock", "shs cl a",
]


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def read_state():
    raw = sys.stdin.read()
    if not raw.strip():
        fail("expected one JSON object on stdin")
    payload = json.loads(raw)
    return payload.get("state") or payload.get("currentState") or {}


def emit(obj):
    json.dump(obj, sys.stdout, default=_jsonable)
    sys.stdout.write("\n")


def _jsonable(o):
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"not JSON serializable: {type(o)}")


def quarter_dir(data_root, quarter):
    """Folder holding COVERPAGE.tsv/INFOTABLE.tsv for a quarter (e.g. /root/2025-q3).
    Accepts the quarter folder itself or one nested level (an unmoved zip folder)."""
    base = os.path.join(data_root, quarter) if quarter else data_root
    if os.path.isfile(os.path.join(base, "INFOTABLE.tsv")):
        return base
    if os.path.isdir(base):
        for sub in sorted(os.listdir(base)):
            p = os.path.join(base, sub)
            if os.path.isfile(os.path.join(p, "INFOTABLE.tsv")):
                return p
    fail(f"no INFOTABLE.tsv under {base}; pass data_root and quarter so that "
         f"<data_root>/<quarter>/INFOTABLE.tsv exists")


def load_coverpage(qdir):
    cp = pd.read_csv(os.path.join(qdir, "COVERPAGE.tsv"), sep="\t", dtype=str,
                     keep_default_na=False)
    for c in ("ISAMENDMENT", "AMENDMENTTYPE", "REPORTTYPE", "REPORTCALENDARORQUARTER",
              "FILINGMANAGER_NAME"):
        cp[c] = cp[c].fillna("").str.strip()
    return cp


def main_period(cp):
    """The report period most filings in this quarter's dataset cover (e.g. 30-SEP-2025).
    A quarterly dataset also carries late filings and amendments for older periods."""
    return cp["REPORTCALENDARORQUARTER"].value_counts().idxmax()


def iter_infotable(qdir, usecols=INFO_COLS):
    for chunk in pd.read_csv(os.path.join(qdir, "INFOTABLE.tsv"), sep="\t", dtype=str,
                             usecols=usecols, chunksize=CHUNK, keep_default_na=False):
        if "VALUE" in chunk:
            chunk["VALUE"] = pd.to_numeric(chunk["VALUE"], errors="coerce").fillna(0.0)
        if "CUSIP" in chunk:
            chunk["CUSIP"] = chunk["CUSIP"].str.strip().str.upper()
        if "PUTCALL" in chunk:
            chunk["PUTCALL"] = chunk["PUTCALL"].str.strip()
        if "SSHPRNAMTTYPE" in chunk:
            chunk["SSHPRNAMTTYPE"] = chunk["SSHPRNAMTTYPE"].str.strip().str.upper()
        if "SSHPRNAMT" in chunk:
            chunk["SSHPRNAMT"] = pd.to_numeric(chunk["SSHPRNAMT"], errors="coerce").fillna(0.0)
        yield chunk


def is_share_position(df):
    """Share (equity) positions: SSHPRNAMTTYPE SH and not a put/call option row."""
    return (df["SSHPRNAMTTYPE"] == "SH") & (df["PUTCALL"] == "")
