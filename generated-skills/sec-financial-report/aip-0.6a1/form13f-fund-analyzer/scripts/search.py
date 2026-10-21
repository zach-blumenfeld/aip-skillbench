"""Fuzzy-search 13F filers (COVERPAGE) and securities (INFOTABLE) by possibly inaccurate names.

stdin state: data_root, quarter, baseline_quarter, fund_queries, stock_queries, topk
stdout: fund_candidates, stock_candidates
"""
import re

import pandas as pd
from rapidfuzz import fuzz, process, utils

from f13common import emit, fail, iter_infotable, load_coverpage, main_period, quarter_dir, read_state

SCORE_WINDOW = 2.0  # filer names scoring within this of the best are treated as tied
ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
STOCK_SCORE_WINDOW = 15.0  # issuer-name variants ("PALANTIR TECHNOLOGIES IN", "... CL A") score lower


def filing_aggregates(qdir, want_names):
    """Per accession: holdings rows and total VALUE. Per CUSIP (if want_names): issuer names,
    filing count and total value."""
    per_acc = []
    per_cusip_name = []
    for ch in iter_infotable(qdir, ["ACCESSION_NUMBER", "NAMEOFISSUER", "CUSIP", "VALUE"]
                             if want_names else ["ACCESSION_NUMBER", "VALUE"]):
        per_acc.append(ch.groupby("ACCESSION_NUMBER")["VALUE"].agg(["size", "sum"]))
        if want_names:
            ch["NAME_L"] = ch["NAMEOFISSUER"].str.strip().str.lower()
            per_cusip_name.append(ch.groupby(["CUSIP", "NAME_L"]).agg(
                n=("ACCESSION_NUMBER", "nunique"), v=("VALUE", "sum")))
    acc = pd.concat(per_acc).groupby(level=0).sum()
    cn = pd.concat(per_cusip_name).groupby(level=[0, 1]).sum() if want_names else None
    return acc, cn


def search_funds(cp, acc, period, query, topk):
    if ACCESSION_RE.match(query.strip()):
        # Exact lookup: a known accession number resolves to its one filer (score 100).
        hit = cp[cp["ACCESSION_NUMBER"] == query.strip()]
        if hit.empty:
            return {"period": period, "candidates": [], "suggested_name": None,
                    "suggested_accession": None, "ambiguous": True,
                    "note": f"accession {query.strip()} not in this quarter's COVERPAGE.tsv"}
        matches = [(hit.iloc[0]["FILINGMANAGER_NAME"], 100.0, 0)]
    else:
        names = cp["FILINGMANAGER_NAME"].unique().tolist()
        matches = process.extract(query, names, scorer=fuzz.WRatio, processor=utils.default_process,
                                  limit=max(topk * 3, 15))
    cands = []
    for name, score, _ in matches:
        rows = cp[cp["FILINGMANAGER_NAME"] == name]
        filings, older = [], 0
        for _, r in rows.iterrows():
            if r["REPORTCALENDARORQUARTER"] != period:
                older += 1
                continue
            a = r["ACCESSION_NUMBER"]
            n, v = (int(acc.loc[a, "size"]), float(acc.loc[a, "sum"])) if a in acc.index else (0, 0.0)
            filings.append({"accession_number": a, "period": r["REPORTCALENDARORQUARTER"],
                            "report_type": r["REPORTTYPE"],
                            "is_amendment": r["ISAMENDMENT"] == "Y",
                            "amendment_type": r["AMENDMENTTYPE"],
                            "n_holdings": n, "total_value": v})
        holdings = [f for f in filings if not f["is_amendment"] and f["n_holdings"] > 0
                    and "NOTICE" not in f["report_type"].upper()]
        first = rows.iloc[0]
        cands.append({"name": name, "score": round(float(score), 3),
                      "location": ", ".join(x for x in (first.get("FILINGMANAGER_STREET1", ""),
                                                         first.get("FILINGMANAGER_CITY", ""),
                                                         first.get("FILINGMANAGER_STATEORCOUNTRY", "")) if x),
                      "form13f_file_number": first.get("FORM13FFILENUMBER", ""),
                      "filings": filings,
                      "filings_for_other_periods": older,
                      "best_holdings_filing": max(holdings, key=lambda f: f["total_value"])
                      ["accession_number"] if holdings else None,
                      "_value": max((f["total_value"] for f in holdings), default=-1.0)})
    best = cands[0]["score"] if cands else 0.0
    tied = [c for c in cands if c["score"] >= best - SCORE_WINDOW and c["best_holdings_filing"]]
    pick = max(tied, key=lambda c: (c["score"], c["_value"])) if tied else None
    for c in cands:
        c.pop("_value")
    shown = cands[:topk]
    if pick and pick not in shown:
        shown.append(pick)
    return {"period": period, "candidates": shown,
            "suggested_name": pick["name"] if pick else None,
            "suggested_accession": pick["best_holdings_filing"] if pick else None,
            "ambiguous": pick is None or len(tied) > 1}


def search_stocks(cn, query, topk):
    """Rank CUSIPs by how many filings name them with a close match to the query. Filers
    mistype names and CUSIPs, so one stray row (a "PALANTIR" label on another CUSIP, a
    one-letter issuer name) must not outrank the CUSIP thousands of filings agree on."""
    names = [n for n in cn.index.get_level_values(1).unique().tolist() if len(n) >= 3]
    matches = process.extract(query, names, scorer=fuzz.WRatio, processor=utils.default_process,
                              limit=max(topk * 20, 100))
    best = matches[0][1] if matches else 0.0
    floor = max(best - STOCK_SCORE_WINDOW, 70.0)
    score_of = {m[0]: float(m[1]) for m in matches if m[1] >= floor}
    sub = cn[cn.index.get_level_values(1).isin(score_of)].reset_index()
    sub["score"] = sub["NAME_L"].map(score_of)
    rows = []
    for cusip, g in sub.groupby("CUSIP"):
        allg = cn.loc[cusip]
        matched = int(g["n"].sum())
        total = int(allg["n"].sum())
        rows.append({"cusip": cusip, "score": round(g["score"].max(), 3),
                     "name": g.sort_values("n", ascending=False)["NAME_L"].iloc[0],
                     "matching_filings": matched, "n_filings": total,
                     "matched_share": round(matched / total, 4) if total else 0.0,
                     "total_value": float(allg["v"].sum())})
    rows.sort(key=lambda r: (r["matching_filings"], r["score"]), reverse=True)
    pick = rows[0] if rows else None
    ambiguous = pick is None or any(r["matching_filings"] >= 0.25 * pick["matching_filings"]
                                    for r in rows[1:])
    return {"candidates": rows[:topk], "suggested_cusip": pick["cusip"] if pick else None,
            "suggested_name": pick["name"] if pick else None, "ambiguous": ambiguous}


def main():
    s = read_state()
    data_root = s.get("data_root") or "/root"
    quarter = s.get("quarter")
    if not quarter:
        fail("quarter is required (e.g. 2025-q3)")
    quarters = [quarter] + ([s["baseline_quarter"]] if s.get("baseline_quarter") else [])
    fund_queries = [q for q in (s.get("fund_queries") or []) if str(q).strip()]
    stock_queries = [q for q in (s.get("stock_queries") or []) if str(q).strip()]
    topk = int(s.get("topk") or 5)

    fund_candidates = {q: {} for q in fund_queries}
    stock_candidates = {}
    for qtr in quarters:
        qdir = quarter_dir(data_root, qtr)
        want_names = qtr == quarter and bool(stock_queries)
        if not fund_queries and not want_names:
            continue
        cp = load_coverpage(qdir)
        period = main_period(cp)
        acc, cn = filing_aggregates(qdir, want_names)
        for fq in fund_queries:
            fund_candidates[fq][qtr] = search_funds(cp, acc, period, fq, topk)
        if want_names:
            for sq in stock_queries:
                stock_candidates[sq] = {"quarter": qtr, **search_stocks(cn, sq, topk)}
    emit({"fund_candidates": fund_candidates, "stock_candidates": stock_candidates})


if __name__ == "__main__":
    main()
