"""Shared 13F loaders, fuzzy search, and analyses.

Data layout (task container): <data_root>/<quarter>/{COVERPAGE,INFOTABLE,SUMMARYPAGE,SUBMISSION}.tsv
with data_root=/root and quarter folders such as 2025-q2 (filings 01-JUN..31-AUG-2025, period
30-JUN-2025) and 2025-q3 (period 30-SEP-2025). All files are tab-separated with a header row.

Importable by the step scripts; also usable directly:
    python3 f13lib.py search-fund --keywords bridgewater --quarter 2025-q2 [--topk 10]
    python3 f13lib.py search-fund --accession_number 0001172661-25-003151 --quarter 2025-q2
    python3 f13lib.py search-stock --keywords palantir [--quarter 2025-q2] [--topk 10]
    python3 f13lib.py fund-summary --accession_number A --quarter 2025-q3
    python3 f13lib.py compare --accession_number A --quarter 2025-q3 --baseline_accession_number B --baseline_quarter 2025-q2
    python3 f13lib.py top-holders --cusip 69608A108 --quarter 2025-q3 [--topk 10]
Add --data_root DIR to point elsewhere (default /root, or $F13_DATA_ROOT).
"""
import json
import os
import re
import sys

import pandas as pd
from rapidfuzz import fuzz, process, utils

DEFAULT_DATA_ROOT = os.environ.get("F13_DATA_ROOT", "/root")
CHUNK = 500_000
INFO_COLS = ["ACCESSION_NUMBER", "NAMEOFISSUER", "TITLEOFCLASS", "CUSIP", "VALUE",
             "SSHPRNAMT", "SSHPRNAMTTYPE", "PUTCALL"]
HOLDINGS_TYPES = {"13F HOLDINGS REPORT", "13F COMBINATION REPORT"}
ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")

_HERE = os.path.dirname(os.path.abspath(__file__))
_CLASSES_PATH = os.path.join(_HERE, "..", "assets", "stock_title_classes.json")


def load_title_classes(raw=None):
    """Return {mode: set(lowercase titles)} from assets/stock_title_classes.json content."""
    if raw is None:
        with open(_CLASSES_PATH) as f:
            raw = f.read()
    data = json.loads(raw) if isinstance(raw, str) else raw
    return {k: set(v) for k, v in data.items() if isinstance(v, list)}


class F13Error(Exception):
    pass


def quarter_dir(data_root, quarter):
    path = os.path.join(data_root, quarter)
    if not os.path.isdir(path):
        avail = sorted(d for d in os.listdir(data_root)
                       if os.path.isfile(os.path.join(data_root, d, "COVERPAGE.tsv"))) \
            if os.path.isdir(data_root) else []
        raise F13Error(f"No 13F folder for quarter '{quarter}' under {data_root}. Available: {avail}")
    return path


def read_table(data_root, quarter, name, usecols=None):
    return pd.read_csv(os.path.join(quarter_dir(data_root, quarter), f"{name}.tsv"),
                       sep="\t", dtype=str, usecols=usecols, keep_default_na=False)


def iter_infotable(data_root, quarter):
    path = os.path.join(quarter_dir(data_root, quarter), "INFOTABLE.tsv")
    for chunk in pd.read_csv(path, sep="\t", dtype=str, usecols=INFO_COLS,
                             keep_default_na=False, chunksize=CHUNK):
        chunk["CUSIP"] = chunk["CUSIP"].str.upper().str.strip()
        chunk["VALUE"] = pd.to_numeric(chunk["VALUE"], errors="coerce").fillna(0.0)
        chunk["SSHPRNAMT"] = pd.to_numeric(chunk["SSHPRNAMT"], errors="coerce").fillna(0.0)
        yield chunk


def filings_table(data_root, quarter):
    """COVERPAGE joined with SUMMARYPAGE and SUBMISSION: one row per accession number."""
    cover = read_table(data_root, quarter, "COVERPAGE")
    summ = read_table(data_root, quarter, "SUMMARYPAGE",
                      ["ACCESSION_NUMBER", "TABLEENTRYTOTAL", "TABLEVALUETOTAL"])
    sub = read_table(data_root, quarter, "SUBMISSION",
                     ["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK"])
    df = cover.merge(summ, on="ACCESSION_NUMBER", how="left").merge(sub, on="ACCESSION_NUMBER", how="left")
    return df.fillna("")


def main_period(filings):
    """The report period most filings in this quarter folder cover (late filings carry older periods)."""
    return filings["REPORTCALENDARORQUARTER"].value_counts().idxmax()


def _filing_record(row, period):
    is_amend = row["ISAMENDMENT"] == "Y"
    rec = {
        "accession_number": row["ACCESSION_NUMBER"],
        "report_period": row["REPORTCALENDARORQUARTER"],
        "filing_date": row["FILING_DATE"],
        "submission_type": row["SUBMISSIONTYPE"],
        "report_type": row["REPORTTYPE"],
        "is_amendment": is_amend,
        "amendment_type": row["AMENDMENTTYPE"],
        "manager_name": row["FILINGMANAGER_NAME"],
        "street": row["FILINGMANAGER_STREET1"],
        "city": row["FILINGMANAGER_CITY"],
        "state_or_country": row["FILINGMANAGER_STATEORCOUNTRY"],
        "form13f_file_number": row["FORM13FFILENUMBER"],
        "cik": row["CIK"],
        "table_entry_total": row["TABLEENTRYTOTAL"],
        "table_value_total": row["TABLEVALUETOTAL"],
    }
    rec["usable"] = (not is_amend and row["REPORTTYPE"] in HOLDINGS_TYPES
                     and row["REPORTCALENDARORQUARTER"] == period)
    return rec


def _pick(records):
    """Default filing for one manager: original (non-amendment) holdings report for the main period,
    largest table if several. Falls back to the original skill's rule (first non-amendment)."""
    usable = [r for r in records if r["usable"]]
    if usable:
        return max(usable, key=lambda r: float(r["table_entry_total"] or 0))["accession_number"]
    non_amend = [r for r in records if not r["is_amendment"]]
    return (non_amend or records)[0]["accession_number"]


def search_fund(keywords, quarter, topk=10, data_root=DEFAULT_DATA_ROOT, filings=None):
    """Fuzzy (WRatio, case-insensitive) match of keywords against FILINGMANAGER_NAME, or an exact
    accession-number lookup when keywords is an accession number."""
    filings = filings_table(data_root, quarter) if filings is None else filings
    period = main_period(filings)
    kw = keywords.strip()
    if ACCESSION_RE.match(kw):
        hit = filings[filings["ACCESSION_NUMBER"] == kw]
        if hit.empty:
            return {"query": kw, "quarter": quarter, "main_period": period, "matches": [],
                    "note": f"No fund found with ACCESSION_NUMBER = {kw} in quarter {quarter}"}
        rec = _filing_record(hit.iloc[0], period)
        return {"query": kw, "quarter": quarter, "main_period": period,
                "matches": [{"rank": 1, "score": 100.0, "manager_name": rec["manager_name"],
                             "suggested_accession_number": kw, "filings": [rec]}]}
    choices = filings["FILINGMANAGER_NAME"].unique().tolist()
    hits = process.extract(kw, choices, scorer=fuzz.WRatio, processor=utils.default_process, limit=topk)
    matches = []
    for name, score, _ in hits:
        rows = filings[filings["FILINGMANAGER_NAME"] == name]
        records = [_filing_record(r, period) for _, r in rows.iterrows()]
        n_other = sum(r["report_period"] != period for r in records)
        if n_other < len(records):  # keep the output small: late older-period filings are only counted
            records = [r for r in records if r["report_period"] == period]
        size = max((float(r["table_value_total"] or 0) for r in records if r["usable"]), default=-1.0)
        matches.append({"score": round(float(score), 3), "manager_name": name, "has_holdings_report": size >= 0,
                        "holdings_value": size if size >= 0 else None,
                        "suggested_accession_number": _pick(records), "filings": records,
                        "other_period_filings": n_other if n_other < len(rows) else 0})
    # Equal scores are common (e.g. "berkshire" → three managers at 90); put holdings filers and larger ones first.
    matches.sort(key=lambda m: (-m["score"], -(m["holdings_value"] or -1)))
    for i, m in enumerate(matches):
        m["rank"] = i + 1
    return {"query": kw, "quarter": quarter, "main_period": period, "matches": matches}


def stock_universe(data_root, quarter):
    """One row per CUSIP: most common issuer name and class title, filer count, total non-option value."""
    parts = []
    for c in iter_infotable(data_root, quarter):
        c = c[c["PUTCALL"] == ""]
        parts.append(c.groupby(["CUSIP", "NAMEOFISSUER", "TITLEOFCLASS"], sort=False)
                     .agg(n=("ACCESSION_NUMBER", "size"), value=("VALUE", "sum")).reset_index())
    df = pd.concat(parts).groupby(["CUSIP", "NAMEOFISSUER", "TITLEOFCLASS"], sort=False).sum().reset_index()
    df = df.sort_values("n", ascending=False)
    top = df.drop_duplicates("CUSIP").set_index("CUSIP")
    tot = df.groupby("CUSIP").agg(rows=("n", "sum"), value=("value", "sum"))
    out = top[["NAMEOFISSUER", "TITLEOFCLASS"]].join(tot)
    out["name_lower"] = out["NAMEOFISSUER"].str.lower()
    return out.reset_index()


def search_stock(keywords, quarter="2025-q2", topk=10, data_root=DEFAULT_DATA_ROOT, universe=None):
    """Fuzzy (WRatio) match of keywords against issuer names; ties broken by total reported value."""
    uni = stock_universe(data_root, quarter) if universe is None else universe
    kw = keywords.strip()
    if re.fullmatch(r"[0-9A-Za-z]{9}", kw) and (uni["CUSIP"] == kw.upper()).any():
        uni = uni[uni["CUSIP"] == kw.upper()]
        hits = [(n, 100.0, i) for i, n in zip(uni.index, uni["name_lower"])]
    else:
        hits = process.extract(kw.lower(), uni["name_lower"], scorer=fuzz.WRatio,
                               processor=utils.default_process, limit=max(topk * 5, 50))
    rows = []
    for name, score, idx in hits:
        r = uni.loc[idx]
        rows.append({"name": name, "cusip": r["CUSIP"], "title_of_class": r["TITLEOFCLASS"],
                     "score": round(float(score), 3), "infotable_rows": int(r["rows"]),
                     "total_value_excl_options": float(r["value"])})
    rows.sort(key=lambda x: (-x["score"], -x["total_value_excl_options"]))
    rows = rows[:topk]
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return {"query": kw, "quarter": quarter, "matches": rows}


def _fund_rows(data_root, quarter, accession_number):
    parts = [c[c["ACCESSION_NUMBER"] == accession_number] for c in iter_infotable(data_root, quarter)]
    return pd.concat(parts)


def fund_summary(accession_number, quarter, classes, mode="as_shipped", data_root=DEFAULT_DATA_ROOT,
                 rows=None, with_positions=False):
    """Mirror of one_fund_analysis.read_one_quarter_data: totals over all rows, stock totals over rows
    whose lowercased TITLEOFCLASS is in the stock list, per-CUSIP aggregation of the stock rows."""
    info = _fund_rows(data_root, quarter, accession_number) if rows is None else rows
    if info.empty:
        raise F13Error(f"No data found for ACCESSION_NUMBER = {accession_number} in quarter {quarter}")
    title = info["TITLEOFCLASS"].str.lower()
    out = {"accession_number": accession_number, "quarter": quarter,
           "total_holdings": int(info.shape[0]), "total_aum": round(float(info["VALUE"].sum()), 2),
           "stock_list_mode": mode}
    for m, cls in classes.items():
        st = info[title.isin(cls)]
        out[f"stock_holdings_{m}"] = int(st.shape[0])
        out[f"stock_aum_{m}"] = round(float(st["VALUE"].sum()), 2)
    out["stock_holdings"] = out[f"stock_holdings_{mode}"]
    out["stock_aum"] = out[f"stock_aum_{mode}"]
    out["distinct_cusips"] = int(info["CUSIP"].nunique())
    out["option_rows"] = int((info["PUTCALL"] != "").sum())
    out["option_value"] = round(float(info.loc[info["PUTCALL"] != "", "VALUE"].sum()), 2)
    st = info[title.isin(classes[mode])]
    if st.empty:
        raise F13Error(f"No stock rows (TITLEOFCLASS in the '{mode}' list) for ACCESSION_NUMBER = "
                       f"{accession_number} in quarter {quarter}; total_holdings={out['total_holdings']}")
    pos = st.groupby("CUSIP").agg(NAMEOFISSUER=("NAMEOFISSUER", "first"), TITLEOFCLASS=("TITLEOFCLASS", "first"),
                                  VALUE=("VALUE", "sum"), SHARES=("SSHPRNAMT", "sum"))
    top = pos.sort_values("VALUE", ascending=False).head(10)
    out["top_stock_positions"] = [{"cusip": c, "name": r["NAMEOFISSUER"], "value": round(float(r["VALUE"]), 2),
                                   "shares": float(r["SHARES"])} for c, r in top.iterrows()]
    return (out, pos) if with_positions else out


def compare(accession_number, quarter, baseline_accession_number, baseline_quarter, classes,
            mode="as_shipped", topn=10, data_root=DEFAULT_DATA_ROOT):
    """Mirror of one_fund_analysis comparison: outer-join stock positions on CUSIP, rank by change in
    market VALUE. PCT_CHANGE divides by the baseline value with 0 replaced by 1, as in the original."""
    cur, a = fund_summary(accession_number, quarter, classes, mode, data_root, with_positions=True)
    base, b = fund_summary(baseline_accession_number, baseline_quarter, classes, mode, data_root, with_positions=True)
    m = a.join(b, how="outer", lsuffix="", rsuffix="_base")
    m["VALUE"] = m["VALUE"].fillna(0)
    m["VALUE_base"] = m["VALUE_base"].fillna(0)
    m["SHARES"] = m["SHARES"].fillna(0)
    m["SHARES_base"] = m["SHARES_base"].fillna(0)
    m["NAMEOFISSUER"] = m["NAMEOFISSUER"].fillna(m["NAMEOFISSUER_base"])
    m["ABS_CHANGE"] = m["VALUE"] - m["VALUE_base"]
    m["PCT_CHANGE"] = m["ABS_CHANGE"] / m["VALUE_base"].replace(0, 1)
    m = m.sort_values("ABS_CHANGE", ascending=False)

    def rec(c, r):
        return {"cusip": c, "name": r["NAMEOFISSUER"], "abs_change": round(float(r["ABS_CHANGE"]), 2),
                "pct_change": round(float(r["PCT_CHANGE"]), 6), "value": round(float(r["VALUE"]), 2),
                "value_base": round(float(r["VALUE_base"]), 2), "shares": float(r["SHARES"]),
                "shares_base": float(r["SHARES_base"]), "share_change": float(r["SHARES"] - r["SHARES_base"]),
                "new_position": bool(r["VALUE_base"] == 0), "exited_position": bool(r["VALUE"] == 0)}

    buys = m[m["ABS_CHANGE"] > 0].head(topn)
    sells = m[m["ABS_CHANGE"] < 0].tail(topn)[::-1]
    return {"current": cur, "baseline": base,
            "aum_change": round(cur["total_aum"] - base["total_aum"], 2),
            "stock_aum_change": round(cur["stock_aum"] - base["stock_aum"], 2),
            "n_new_positions": int((m["VALUE_base"] == 0).sum()),
            "n_exited_positions": int((m["VALUE"] == 0).sum()),
            "top_buys": [rec(c, r) for c, r in buys.iterrows()],
            "top_sells": [rec(c, r) for c, r in sells.iterrows()]}


def top_holders(cusip, quarter, topk=10, data_root=DEFAULT_DATA_ROOT, filings=None):
    """Mirror of holding_analysis.topk_managers: sum VALUE of all rows with this CUSIP per accession
    number, rank descending. Each holder is annotated with its cover-page details."""
    cusip = cusip.strip().upper()
    parts = [c[c["CUSIP"] == cusip] for c in iter_infotable(data_root, quarter)]
    rows = pd.concat(parts)
    if rows.empty:
        raise F13Error(f"CUSIP {cusip} not found in quarter {quarter}")
    rows = rows.assign(OPT=rows["VALUE"].where(rows["PUTCALL"] != "", 0.0))
    agg = rows.groupby("ACCESSION_NUMBER").agg(TOTAL_VALUE=("VALUE", "sum"), OPTION_VALUE=("OPT", "sum"),
                                               SHARES=("SSHPRNAMT", "sum"))
    agg = agg.sort_values("TOTAL_VALUE", ascending=False)
    filings = filings_table(data_root, quarter) if filings is None else filings
    period = main_period(filings)
    fi = filings.set_index("ACCESSION_NUMBER")
    out = []
    for i, (acc, r) in enumerate(agg.head(topk).iterrows()):
        f = fi.loc[acc] if acc in fi.index else None
        out.append({"rank": i + 1, "accession_number": acc, "holding_value": round(float(r["TOTAL_VALUE"]), 2),
                    "option_value_included": round(float(r["OPTION_VALUE"]), 2), "shares": float(r["SHARES"]),
                    "manager_name": None if f is None else f["FILINGMANAGER_NAME"],
                    "report_period": None if f is None else f["REPORTCALENDARORQUARTER"],
                    "is_amendment": None if f is None else f["ISAMENDMENT"] == "Y",
                    "off_period_or_amendment": None if f is None else
                    (f["ISAMENDMENT"] == "Y" or f["REPORTCALENDARORQUARTER"] != period)})
    names = rows["NAMEOFISSUER"].value_counts()
    return {"cusip": cusip, "quarter": quarter, "issuer_name": names.index[0], "n_holders": int(agg.shape[0]),
            "total_value_all_holders": round(float(agg["TOTAL_VALUE"].sum()), 2), "holders": out}


def _cli(argv):
    import argparse
    p = argparse.ArgumentParser(description="13F search and analysis")
    p.add_argument("command", choices=["search-fund", "search-stock", "fund-summary", "compare", "top-holders"])
    p.add_argument("--keywords", default="")
    p.add_argument("--accession_number", default="")
    p.add_argument("--quarter", default="2025-q2")
    p.add_argument("--baseline_accession_number", default="")
    p.add_argument("--baseline_quarter", default="")
    p.add_argument("--cusip", default="")
    p.add_argument("--topk", type=int, default=10)
    p.add_argument("--stock_list_mode", default="as_shipped")
    p.add_argument("--data_root", default=DEFAULT_DATA_ROOT)
    a = p.parse_args(argv)
    classes = load_title_classes()
    if a.command == "search-fund":
        res = search_fund(a.accession_number or a.keywords, a.quarter, a.topk, a.data_root)
    elif a.command == "search-stock":
        res = search_stock(a.keywords, a.quarter, a.topk, a.data_root)
    elif a.command == "fund-summary":
        res = fund_summary(a.accession_number, a.quarter, classes, a.stock_list_mode, a.data_root)
    elif a.command == "compare":
        res = compare(a.accession_number, a.quarter, a.baseline_accession_number, a.baseline_quarter,
                      classes, a.stock_list_mode, 10, a.data_root)
    else:
        res = top_holders(a.cusip, a.quarter, a.topk, a.data_root)
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    try:
        _cli(sys.argv[1:])
    except F13Error as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
