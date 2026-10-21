#!/usr/bin/env python3
"""SEC Form 13F bulk-data analysis: fuzzy fund/stock search, fund summary, quarter-over-quarter
change, and top holders of a stock.

Requires: python>=3.9, pandas (tested 2.3.3), rapidfuzz (tested 3.14.3).

Data layout: <data_root>/<quarter>/{COVERPAGE,SUBMISSION,SUMMARYPAGE,INFOTABLE}.tsv, e.g.
/root/2025-q3/INFOTABLE.tsv. --data_root defaults to /root; --quarter is the folder name.

Subcommands:
  search-fund   --quarter Q (--keywords TEXT | --accession_number ACC) [--topk 10]
  search-stock  --quarter Q --keywords TEXT [--topk 10] [--all_classes]
  fund          --quarter Q --accession_number ACC[,ACC...]
  compare       --quarter Q --accession_number ACC --baseline_quarter Q0 --baseline_accession_number ACC0 [--topk 10]
  holders       --quarter Q --cusip CUSIP [--topk 10] [--include_options]
"""
import argparse
import os
import sys

import pandas as pd

try:
    from rapidfuzz import fuzz, process, utils
except ImportError:  # pragma: no cover
    sys.exit("ERROR: rapidfuzz is not installed (pip install rapidfuzz). Also needs pandas.")

# TITLEOFCLASS values (lower-cased) that count as a stock holding. This is the list the source
# skill wrote out; the source code lost 16 of these entries to missing commas (see source/README.md).
STOCK_TITLE_CLASSES = {
    "com", "common stock", "cl a", "com new", "class a", "stock", "common", "com cl a", "com shs",
    "sponsored adr", "sponsored ads", "adr", "equity", "cmn", "cl b", "ord shs", "cl a com",
    "class a com", "cap stk cl a", "comm stk", "cl b new", "cap stk cl c", "cl a new",
    "foreign stock", "shs cl a",
}
INFO_COLS = ["ACCESSION_NUMBER", "NAMEOFISSUER", "TITLEOFCLASS", "CUSIP", "VALUE", "SSHPRNAMT",
             "SSHPRNAMTTYPE", "PUTCALL"]


# ---------------------------------------------------------------- loaders
def qdir(root, quarter):
    d = os.path.join(root, quarter)
    if not os.path.isdir(d):
        avail = sorted(x for x in os.listdir(root) if os.path.isdir(os.path.join(root, x))) if os.path.isdir(root) else []
        sys.exit(f"ERROR: quarter folder {d} not found. Folders under {root}: {avail}")
    return d


def read_tsv(root, quarter, name, **kw):
    path = os.path.join(qdir(root, quarter), f"{name}.tsv")
    if not os.path.isfile(path):
        sys.exit(f"ERROR: {path} not found")
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=True, **kw)


def load_filings(root, quarter):
    """COVERPAGE joined with SUBMISSION and SUMMARYPAGE: one row per filing (accession)."""
    cover = read_tsv(root, quarter, "COVERPAGE")
    sub = read_tsv(root, quarter, "SUBMISSION")[["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK"]]
    summ = read_tsv(root, quarter, "SUMMARYPAGE")[["ACCESSION_NUMBER", "TABLEENTRYTOTAL", "TABLEVALUETOTAL"]]
    f = cover.merge(sub, on="ACCESSION_NUMBER", how="left").merge(summ, on="ACCESSION_NUMBER", how="left")
    # ISAMENDMENT is 'Y', 'N' or blank; blank means an original filing (e.g. Renaissance Technologies).
    f["IS_AMEND"] = f["ISAMENDMENT"].fillna("N").str.upper().eq("Y")
    f["FILED"] = pd.to_datetime(f["FILING_DATE"], format="%d-%b-%Y", errors="coerce")
    f["TABLEVALUETOTAL"] = pd.to_numeric(f["TABLEVALUETOTAL"], errors="coerce")
    f["TABLEENTRYTOTAL"] = pd.to_numeric(f["TABLEENTRYTOTAL"], errors="coerce")
    f["CIK"] = f["CIK"].fillna(f["FORM13FFILENUMBER"]).fillna(f["FILINGMANAGER_NAME"])
    return f


def main_period(filings):
    """The report period most filings in this folder cover (late filings for older periods also appear)."""
    return filings["REPORTCALENDARORQUARTER"].mode().iloc[0]


def effective_filings(filings):
    """Accessions that make up each filer's holdings for the folder's main period.

    Per filer (CIK), walk filings in filing order: an original or a RESTATEMENT amendment
    replaces the set; a NEW HOLDINGS amendment adds to it. Filers often label a full re-filing
    "NEW HOLDINGS" (JPMorgan Q3 2025: 32,847 of 32,847 entries again), so a NEW HOLDINGS amendment
    with at least half as many entries as the current set is treated as a restatement.
    13F NOTICE filings carry no holdings.
    """
    period = main_period(filings)
    f = filings[(filings["REPORTCALENDARORQUARTER"] == period) & (filings["REPORTTYPE"] != "13F NOTICE")]
    f = f.sort_values(["CIK", "FILED", "ACCESSION_NUMBER"])
    keep = []
    for _, g in f.groupby("CIK", sort=False):
        cur, cur_entries = [], 0
        for _, r in g.iterrows():
            n = 0 if pd.isna(r["TABLEENTRYTOTAL"]) else r["TABLEENTRYTOTAL"]
            if (cur and r["IS_AMEND"] and str(r["AMENDMENTTYPE"]).upper() == "NEW HOLDINGS"
                    and n < 0.5 * cur_entries):
                cur.append(r["ACCESSION_NUMBER"])
                cur_entries += n
            else:
                cur, cur_entries = [r["ACCESSION_NUMBER"]], n
        keep.extend(cur)
    return set(keep), period


def read_infotable(root, quarter, accessions=None):
    path = os.path.join(qdir(root, quarter), "INFOTABLE.tsv")
    if not os.path.isfile(path):
        sys.exit(f"ERROR: {path} not found")
    info = pd.read_csv(path, sep="\t", dtype=str, usecols=INFO_COLS)
    if accessions is not None:
        info = info[info["ACCESSION_NUMBER"].isin(accessions)].copy()
    info["VALUE"] = pd.to_numeric(info["VALUE"], errors="coerce").fillna(0.0)
    info["SSHPRNAMT"] = pd.to_numeric(info["SSHPRNAMT"], errors="coerce").fillna(0.0)
    info["CUSIP"] = info["CUSIP"].str.strip().str.upper()
    info["IS_OPTION"] = info["PUTCALL"].notna() & info["PUTCALL"].str.strip().ne("")
    info["IS_STOCK"] = info["TITLEOFCLASS"].fillna("").str.strip().str.lower().isin(STOCK_TITLE_CLASSES) & ~info["IS_OPTION"]
    return info


def split_acc(s):
    return [a.strip() for a in s.split(",") if a.strip()]


# ---------------------------------------------------------------- search-fund
def print_filing(r, rank, score, eff, period):
    flags = []
    if r["ACCESSION_NUMBER"] in eff:
        flags.append("EFFECTIVE")
    if r["REPORTCALENDARORQUARTER"] != period:
        flags.append("OTHER-PERIOD")
    if r["IS_AMEND"]:
        flags.append(f"AMENDMENT:{r['AMENDMENTTYPE'] if pd.notna(r['AMENDMENTTYPE']) else '?'}")
    if r["REPORTTYPE"] == "13F NOTICE":
        flags.append("NOTICE-NO-HOLDINGS")
    val = r["TABLEVALUETOTAL"]
    print(f"** Rank {rank} (score = {score:.3f}) [{' '.join(flags)}] **")
    print(f"  ACCESSION_NUMBER: {r['ACCESSION_NUMBER']}")
    print(f"  FILINGMANAGER_NAME: {r['FILINGMANAGER_NAME']}")
    print(f"  REPORTCALENDARORQUARTER: {r['REPORTCALENDARORQUARTER']}  FILING_DATE: {r['FILING_DATE']}  CIK: {r['CIK']}")
    print(f"  REPORTTYPE: {r['REPORTTYPE']}  ISAMENDMENT: {r['ISAMENDMENT'] if pd.notna(r['ISAMENDMENT']) else ''}")
    print(f"  ADDRESS: {r['FILINGMANAGER_STREET1']}, {r['FILINGMANAGER_CITY']}, {r['FILINGMANAGER_STATEORCOUNTRY']}")
    print(f"  FORM13FFILENUMBER: {r['FORM13FFILENUMBER']}")
    print(f"  SUMMARYPAGE: entries={'' if pd.isna(r['TABLEENTRYTOTAL']) else int(r['TABLEENTRYTOTAL'])}"
          f" value={'' if pd.isna(val) else f'{val:,.0f}'}")
    print()


def cmd_search_fund(a):
    f = load_filings(a.data_root, a.quarter)
    eff, period = effective_filings(f)
    print(f"Quarter folder {a.quarter}: main report period {period}; {len(f)} filings\n")
    if a.accession_number:
        m = f[f["ACCESSION_NUMBER"] == a.accession_number.strip()]
        if m.empty:
            sys.exit(f"No fund found with ACCESSION_NUMBER = {a.accession_number} in quarter {a.quarter}")
        print_filing(m.iloc[0], 1, 100.0, eff, period)
        return
    if not a.keywords:
        sys.exit("ERROR: give --keywords or --accession_number")
    names = f["FILINGMANAGER_NAME"].dropna().unique().tolist()
    # default_process lower-cases and strips punctuation so "renaissance technologies" matches
    # "RENAISSANCE TECHNOLOGIES LLC".
    matches = process.extract(a.keywords, names, scorer=fuzz.WRatio, processor=utils.default_process,
                              limit=max(a.topk * 3, 30))
    rows = []
    for name, score, _ in matches:
        for _, r in f[f["FILINGMANAGER_NAME"] == name].iterrows():
            rows.append((score, r))
    # tie-break: effective holdings filings of the main period first, then bigger portfolios
    rows.sort(key=lambda x: (-round(x[0], 3), x[1]["ACCESSION_NUMBER"] not in eff,
                             -(0 if pd.isna(x[1]["TABLEVALUETOTAL"]) else x[1]["TABLEVALUETOTAL"])))
    for i, (score, r) in enumerate(rows[: a.topk]):
        print_filing(r, i + 1, score, eff, period)


# ---------------------------------------------------------------- search-stock
def cmd_search_stock(a):
    info = read_infotable(a.data_root, a.quarter)
    st = info[~info["IS_OPTION"]] if a.all_classes else info[info["IS_STOCK"]]
    st = st.assign(NAME=st["NAMEOFISSUER"].fillna("").str.strip().str.lower())
    agg = st.groupby("CUSIP").agg(NAME=("NAME", lambda s: s.mode().iloc[0]), FILINGS=("ACCESSION_NUMBER", "nunique"),
                                  TOTAL_VALUE=("VALUE", "sum")).reset_index()
    names = agg["NAME"].unique().tolist()
    matches = process.extract(a.keywords, names, scorer=fuzz.WRatio, processor=utils.default_process,
                              limit=max(a.topk * 3, 30))
    score_of = {n: s for n, s, _ in matches}
    cand = agg[agg["NAME"].isin(score_of)].copy()
    cand["SCORE"] = cand["NAME"].map(score_of).round(3)
    # Typo CUSIPs filed by a handful of managers share the real name; rank by score, then filer count.
    cand = cand.sort_values(["SCORE", "FILINGS", "TOTAL_VALUE"], ascending=[False, False, False]).head(a.topk)
    scope = "all title classes" if a.all_classes else "stock title classes only"
    print(f"Search results in {a.quarter} ({scope}, options excluded):")
    for i, (_, r) in enumerate(cand.iterrows()):
        print(f"** Rank {i+1} (score = {r['SCORE']:.3f}) **")
        print(f"  Name: {r['NAME']}")
        print(f"  CUSIP: {r['CUSIP']}  filings holding it: {r['FILINGS']}  total value: {r['TOTAL_VALUE']:,.0f}")
        print()
    if not cand.empty:
        best = cand.iloc[0]
        print(f"BEST_CUSIP: {best['CUSIP']} ({best['NAME']}, held in {best['FILINGS']} filings)")


# ---------------------------------------------------------------- fund / compare
def fund_summary(root, quarter, accs):
    info = read_infotable(root, quarter, set(accs))
    if info.empty:
        sys.exit(f"ERROR: No data found for ACCESSION_NUMBER = {','.join(accs)} in quarter {quarter}")
    stock = info[info["IS_STOCK"]]
    summ = load_filings(root, quarter)
    summ = summ[summ["ACCESSION_NUMBER"].isin(accs)]
    print(f"Summary stats for quarter: {quarter}, accession_number: {','.join(accs)}")
    for _, r in summ.iterrows():
        print(f"- Filer: {r['FILINGMANAGER_NAME']} | period {r['REPORTCALENDARORQUARTER']} | {r['REPORTTYPE']}")
    print(f"- Total number of holdings (all rows): {info.shape[0]}")
    print(f"- Total AUM (sum of VALUE, US dollars): {info['VALUE'].sum():.2f}")
    print(f"- SUMMARYPAGE TABLEVALUETOTAL cross-check: {summ['TABLEVALUETOTAL'].sum():.2f}")
    print(f"- Option rows (put/call): {int(info['IS_OPTION'].sum())}")
    print(f"- Number of stock holdings (rows): {stock.shape[0]}")
    print(f"- Number of distinct stocks (CUSIPs): {stock['CUSIP'].nunique()}")
    print(f"- Total stock AUM: {stock['VALUE'].sum():.2f}")
    if stock.empty:
        sys.exit(f"ERROR: No stock holdings found for ACCESSION_NUMBER = {','.join(accs)} in quarter {quarter}")
    return stock.groupby("CUSIP").agg(NAMEOFISSUER=("NAMEOFISSUER", "first"), TITLEOFCLASS=("TITLEOFCLASS", "first"),
                                      VALUE=("VALUE", "sum"), SHARES=("SSHPRNAMT", "sum"))


def cmd_fund(a):
    fund_summary(a.data_root, a.quarter, split_acc(a.accession_number))


def cmd_compare(a):
    cur = fund_summary(a.data_root, a.quarter, split_acc(a.accession_number))
    print(f"\nPerforming comparative analysis using baseline quarter {a.baseline_quarter}")
    base = fund_summary(a.data_root, a.baseline_quarter, split_acc(a.baseline_accession_number))
    m = cur.join(base, how="outer", rsuffix="_base")
    m["VALUE"] = m["VALUE"].fillna(0)
    m["VALUE_base"] = m["VALUE_base"].fillna(0)
    m["SHARES"] = m["SHARES"].fillna(0)
    m["SHARES_base"] = m["SHARES_base"].fillna(0)
    m["NAMEOFISSUER"] = m["NAMEOFISSUER"].fillna(m["NAMEOFISSUER_base"])
    m["ABS_CHANGE"] = m["VALUE"] - m["VALUE_base"]
    m["PCT_CHANGE"] = m["ABS_CHANGE"] / m["VALUE_base"].replace(0, 1)  # avoid division by zero
    m["SHARE_CHANGE"] = m["SHARES"] - m["SHARES_base"]
    m = m.sort_values("ABS_CHANGE", ascending=False)

    def show(df):
        for i, (cusip, r) in enumerate(df.iterrows()):
            tag = " NEW" if r["VALUE_base"] == 0 else (" EXITED" if r["VALUE"] == 0 else "")
            pct = "n/a (new position)" if r["VALUE_base"] == 0 else f"{r['PCT_CHANGE']:.2%}"
            print(f"[{i+1}] CUSIP: {cusip}, Name: {r['NAMEOFISSUER']} | Abs change: {r['ABS_CHANGE']:.2f} | "
                  f"pct change: {pct} | share change: {r['SHARE_CHANGE']:,.0f}{tag}")

    buys = m[m["ABS_CHANGE"] > 0].head(a.topk)
    sells = m[m["ABS_CHANGE"] < 0].tail(a.topk)[::-1]
    print(f"\nTop {a.topk} Buys (largest dollar value increase) from {a.baseline_quarter} to {a.quarter}:")
    show(buys)
    print(f"\nTop {a.topk} Sells (largest dollar value decrease) from {a.baseline_quarter} to {a.quarter}:")
    show(sells)
    print(f"\nTOP_BUY_CUSIPS: {list(buys.index)}")
    print(f"TOP_SELL_CUSIPS: {list(sells.index)}")


# ---------------------------------------------------------------- holders
def cmd_holders(a):
    filings = load_filings(a.data_root, a.quarter)
    eff, period = effective_filings(filings)
    info = read_infotable(a.data_root, a.quarter, eff)
    cusip = a.cusip.strip().upper()
    h = info[info["CUSIP"] == cusip]
    if not a.include_options:
        h = h[~h["IS_OPTION"]]
    if h.empty:
        sys.exit(f"ERROR: no holdings of CUSIP {cusip} in {a.quarter} (check the CUSIP with search-stock)")
    meta = filings.set_index("ACCESSION_NUMBER")
    h = h.assign(CIK=h["ACCESSION_NUMBER"].map(meta["CIK"]))
    g = h.groupby("CIK").agg(TOTAL_VALUE=("VALUE", "sum"), SHARES=("SSHPRNAMT", "sum"),
                             ACCESSIONS=("ACCESSION_NUMBER", lambda s: ",".join(sorted(set(s)))))
    g = g.sort_values("TOTAL_VALUE", ascending=False).head(a.topk)
    print(f"Top-{g.shape[0]} fund managers holding CUSIP {cusip} in quarter {a.quarter} "
          f"(period {period}; {'including' if a.include_options else 'excluding'} put/call rows; amendments resolved):")
    names = []
    for i, (cik, r) in enumerate(g.iterrows()):
        acc0 = r["ACCESSIONS"].split(",")[0]
        name = meta.loc[acc0, "FILINGMANAGER_NAME"]
        if isinstance(name, pd.Series):
            name = name.iloc[0]
        names.append(name)
        print(f"Rank {i+1}: {name} | accession number = {r['ACCESSIONS']} | Holding value = {r['TOTAL_VALUE']:.2f} "
              f"| shares = {r['SHARES']:,.0f}")
    print(f"\nTOP_MANAGER_NAMES: {names}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data_root", default="/root", help="folder holding the quarter folders (default /root)")
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("search-fund")
    s.add_argument("--quarter", required=True)
    s.add_argument("--keywords", default="")
    s.add_argument("--accession_number", default="")
    s.add_argument("--topk", type=int, default=10)
    s.set_defaults(fn=cmd_search_fund)

    s = sp.add_parser("search-stock")
    s.add_argument("--quarter", required=True)
    s.add_argument("--keywords", required=True)
    s.add_argument("--topk", type=int, default=10)
    s.add_argument("--all_classes", action="store_true",
                   help="search every non-option security, not just the stock title classes")
    s.set_defaults(fn=cmd_search_stock)

    s = sp.add_parser("fund")
    s.add_argument("--quarter", required=True)
    s.add_argument("--accession_number", required=True, help="one accession, or several comma-separated")
    s.set_defaults(fn=cmd_fund)

    s = sp.add_parser("compare")
    s.add_argument("--quarter", required=True)
    s.add_argument("--accession_number", required=True)
    s.add_argument("--baseline_quarter", required=True)
    s.add_argument("--baseline_accession_number", required=True)
    s.add_argument("--topk", type=int, default=10)
    s.set_defaults(fn=cmd_compare)

    s = sp.add_parser("holders")
    s.add_argument("--quarter", required=True)
    s.add_argument("--cusip", required=True)
    s.add_argument("--topk", type=int, default=10)
    s.add_argument("--include_options", action="store_true", help="also count put/call option rows")
    s.set_defaults(fn=cmd_holders)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
