"""Fund summaries, quarter-over-quarter holding changes, and top holders of a stock from 13F data.

stdin state: data_root, quarter, baseline_quarter, selection, topk
  selection = {"funds": {<label>: {<quarter>: <accession_number>}}, "stocks": {<label>: <cusip>}}
stdout: fund_summaries, holding_changes, top_holders
"""
import os

import pandas as pd

from f13common import (TITLE_CLASS_OF_STOCKS, emit, fail, is_share_position, iter_infotable,
                       load_coverpage, main_period, quarter_dir, read_state)


def load_rows(qdir, accessions, cusips):
    keep = []
    for ch in iter_infotable(qdir):
        m = ch["ACCESSION_NUMBER"].isin(accessions) | ch["CUSIP"].isin(cusips)
        if m.any():
            keep.append(ch[m])
    if not keep:
        return pd.DataFrame(columns=list(ch.columns))
    return pd.concat(keep, ignore_index=True)


def summary_page(qdir):
    p = os.path.join(qdir, "SUMMARYPAGE.tsv")
    if not os.path.isfile(p):
        return None
    return pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False).set_index("ACCESSION_NUMBER")


def fund_summary(rows, acc, cp, sp):
    d = rows[rows["ACCESSION_NUMBER"] == acc]
    meta = cp[cp["ACCESSION_NUMBER"] == acc]
    if meta.empty:
        fail(f"accession {acc} is not in this quarter's COVERPAGE.tsv")
    meta = meta.iloc[0]
    shares = d[is_share_position(d)]
    titled = d[d["TITLEOFCLASS"].str.strip().str.lower().isin(TITLE_CLASS_OF_STOCKS)]
    out = {
        "accession_number": acc,
        "manager_name": meta["FILINGMANAGER_NAME"],
        "period": meta["REPORTCALENDARORQUARTER"],
        "report_type": meta["REPORTTYPE"],
        "is_amendment": meta["ISAMENDMENT"] == "Y",
        "total_holdings": int(len(d)),
        "aum": float(d["VALUE"].sum()),
        "distinct_cusips": int(d["CUSIP"].nunique()),
        "stock_holdings": int(shares["CUSIP"].nunique()),
        "stock_value": float(shares["VALUE"].sum()),
        "option_rows": int((d["PUTCALL"] != "").sum()),
        "principal_amount_rows": int((d["SSHPRNAMTTYPE"] == "PRN").sum()),
        "title_list_stock_rows": int(len(titled)),
        "title_list_stock_value": float(titled["VALUE"].sum()),
    }
    if sp is not None and acc in sp.index:
        out["summarypage_entry_total"] = sp.loc[acc, "TABLEENTRYTOTAL"]
        out["summarypage_value_total"] = sp.loc[acc, "TABLEVALUETOTAL"]
    if d.empty:
        out["warning"] = "no INFOTABLE rows for this accession (a 13F NOTICE files no holdings)"
    return out


def by_cusip(d):
    return d.groupby("CUSIP").agg(NAME=("NAMEOFISSUER", "first"), VALUE=("VALUE", "sum"),
                                  SHARES=("SSHPRNAMT", "sum"))


def compare(cur, base, n):
    m = cur.join(base, how="outer", rsuffix="_BASE")
    m["NAME"] = m["NAME"].fillna(m["NAME_BASE"])
    for c in ("VALUE", "VALUE_BASE", "SHARES", "SHARES_BASE"):
        m[c] = m[c].fillna(0.0)
    m["ABS_CHANGE"] = m["VALUE"] - m["VALUE_BASE"]
    m = m.sort_values("ABS_CHANGE", ascending=False)

    def rec(cusip, r):
        return {"cusip": cusip, "name": r["NAME"], "value_base": float(r["VALUE_BASE"]),
                "value": float(r["VALUE"]), "abs_change": float(r["ABS_CHANGE"]),
                "pct_change": (float(r["ABS_CHANGE"] / r["VALUE_BASE"]) if r["VALUE_BASE"] else None),
                "shares_base": float(r["SHARES_BASE"]), "shares": float(r["SHARES"]),
                "status": "new" if r["VALUE_BASE"] == 0 else ("exited" if r["VALUE"] == 0 else "held")}
    up = m[m["ABS_CHANGE"] > 0].head(n)
    down = m[m["ABS_CHANGE"] < 0].tail(n)[::-1]
    return {"top_increases": [rec(c, r) for c, r in up.iterrows()],
            "top_decreases": [rec(c, r) for c, r in down.iterrows()],
            "n_new_positions": int(((m["VALUE_BASE"] == 0) & (m["VALUE"] > 0)).sum()),
            "n_exited_positions": int(((m["VALUE"] == 0) & (m["VALUE_BASE"] > 0)).sum())}


def holding_change(rows_cur, acc_cur, rows_base, acc_base, n):
    cur = rows_cur[rows_cur["ACCESSION_NUMBER"] == acc_cur]
    base = rows_base[rows_base["ACCESSION_NUMBER"] == acc_base]
    t = lambda d: d[d["TITLEOFCLASS"].str.strip().str.lower().isin(TITLE_CLASS_OF_STOCKS)]
    out = compare(by_cusip(cur[is_share_position(cur)]), by_cusip(base[is_share_position(base)]), n)
    alt = compare(by_cusip(t(cur)), by_cusip(t(base)), n)
    out["title_list_top_increases"] = [r["cusip"] for r in alt["top_increases"]]
    return out


def top_holders(rows, cusip, cp, period, n):
    d = rows[rows["CUSIP"] == cusip].merge(
        cp[["ACCESSION_NUMBER", "FILINGMANAGER_NAME", "REPORTCALENDARORQUARTER", "REPORTTYPE",
            "ISAMENDMENT"]], on="ACCESSION_NUMBER", how="left")
    d = d[(d["REPORTCALENDARORQUARTER"] == period) & ~d["REPORTTYPE"].str.upper().str.contains("NOTICE", na=False)]

    def rank(sub):
        per_acc = sub.groupby(["ACCESSION_NUMBER", "FILINGMANAGER_NAME"], as_index=False).agg(
            value=("VALUE", "sum"), shares=("SSHPRNAMT", "sum"))
        # One manager can file an original plus amendments for the same period (some
        # "NEW HOLDINGS" amendments repeat the whole table): keep its largest filing, never sum.
        per_acc["MGR"] = per_acc["FILINGMANAGER_NAME"].str.strip().str.upper()
        best = per_acc.sort_values("value", ascending=False).drop_duplicates("MGR").head(n)
        return [{"rank": i + 1, "manager_name": r["FILINGMANAGER_NAME"],
                 "accession_number": r["ACCESSION_NUMBER"], "value": float(r["value"]),
                 "shares": float(r["shares"])} for i, (_, r) in enumerate(best.iterrows())]
    return {"cusip": cusip, "period": period, "n_filers": int(d["ACCESSION_NUMBER"].nunique()),
            "ranking": rank(d[is_share_position(d)]), "ranking_incl_options": rank(d)}


def main():
    s = read_state()
    data_root = s.get("data_root") or "/root"
    quarter = s.get("quarter")
    baseline = s.get("baseline_quarter") or ""
    sel = s.get("selection") or {}
    n = max(int(s.get("topk") or 5), 10)
    funds = sel.get("funds") or {}
    stocks = {k: str(v).strip().upper() for k, v in (sel.get("stocks") or {}).items() if v}
    if not quarter:
        fail("quarter is required")

    quarters = sorted({q for f in funds.values() for q in f} | {quarter})
    rows, cps, sps, periods = {}, {}, {}, {}
    for q in quarters:
        qdir = quarter_dir(data_root, q)
        accs = {a for f in funds.values() for qq, a in f.items() if qq == q and a}
        cus = set(stocks.values()) if q == quarter else set()
        cps[q] = load_coverpage(qdir)
        sps[q] = summary_page(qdir)
        periods[q] = main_period(cps[q])
        rows[q] = load_rows(qdir, accs, cus) if (accs or cus) else None

    fund_summaries, holding_changes, holders = {}, {}, {}
    for label, per_q in funds.items():
        fund_summaries[label] = {q: fund_summary(rows[q], a, cps[q], sps[q]) for q, a in per_q.items() if a}
        if baseline and per_q.get(quarter) and per_q.get(baseline):
            holding_changes[label] = {"from": baseline, "to": quarter, "basis": "share positions (SH, no put/call), summed per CUSIP",
                                      **holding_change(rows[quarter], per_q[quarter], rows[baseline], per_q[baseline], n)}
    for label, cusip in stocks.items():
        holders[label] = {"quarter": quarter, **top_holders(rows[quarter], cusip, cps[quarter], periods[quarter], n)}
    emit({"fund_summaries": fund_summaries, "holding_changes": holding_changes, "top_holders": holders})


if __name__ == "__main__":
    main()
