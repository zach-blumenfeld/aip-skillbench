#!/usr/bin/env python3
"""Inspect stock data and build the D3 v6 bubble-chart + linked-table web app.

Requires: Python >= 3.8, standard library only. Uses the vendored
assets/d3.v6.min.js (falls back to downloading d3@6.7.0 with urllib/curl only
if that file is missing).

Usage (run from the skill folder):
  python3 scripts/build_app.py inspect --data-dir /root/data
  python3 scripts/build_app.py build --data-dir /root/data --out /root/output \
      [--descriptions stock-descriptions.csv] [--col name="full name" ...] \
      [--etf-sector ETF] [--title "Stock Market Overview"]

inspect -> JSON on stdout: columns, resolved column mapping, sectors, ETF rows,
           price-history files matched per ticker, warnings.
build   -> copies the data into <out>/data/, writes <out>/index.html,
           <out>/css/style.css, <out>/js/visualization.js, <out>/js/d3.v6.min.js.
"""
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(SKILL_DIR, "assets")
TEMPLATES = os.path.join(ASSETS, "templates")
D3_VENDORED = os.path.join(ASSETS, "d3.v6.min.js")
D3_URLS = [
    "https://cdn.jsdelivr.net/npm/d3@6.7.0/dist/d3.min.js",
    "https://unpkg.com/d3@6.7.0/dist/d3.min.js",
    "https://d3js.org/d3.v6.min.js",
]

# Candidate header names per role (compared after lower-casing and removing
# spaces, underscores and dashes). First match wins.
CANDIDATES = {
    "ticker": ["ticker", "symbol", "tickersymbol", "stock", "code"],
    "name": ["fullname", "name", "longname", "companyname", "company", "shortname", "security"],
    "sector": ["sector", "gicssector", "category", "industry", "assetclass"],
    "marketCap": ["marketcap", "marketcapitalization", "mktcap", "cap"],
    "country": ["country"],
    "website": ["website", "url", "web"],
}
REQUIRED = ["ticker", "name", "sector", "marketCap"]
# Only these columns are embedded into visualization.js (keeps it small).
ROLES = ["ticker", "name", "sector", "marketCap", "country", "website"]


def die(msg):
    sys.stderr.write("ERROR: " + msg + "\n")
    sys.exit(2)


def norm(h):
    return re.sub(r"[\s_\-]+", "", (h or "").strip().lower())


def find_descriptions(data_dir, explicit):
    if explicit:
        p = explicit if os.path.isabs(explicit) else os.path.join(data_dir, explicit)
        if not os.path.isfile(p):
            die("descriptions file not found: %s" % p)
        return p
    default = os.path.join(data_dir, "stock-descriptions.csv")
    if os.path.isfile(default):
        return default
    top = sorted(f for f in os.listdir(data_dir)
                 if f.lower().endswith(".csv") and os.path.isfile(os.path.join(data_dir, f)))
    if len(top) == 1:
        return os.path.join(data_dir, top[0])
    die("cannot pick the descriptions CSV in %s (top-level CSVs: %s); pass --descriptions"
        % (data_dir, top or "none"))


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return reader.fieldnames or [], rows


def resolve_columns(headers, overrides):
    mapping = {}
    by_norm = {}
    for h in headers:
        by_norm.setdefault(norm(h), h)
    for role in ROLES:
        if role in overrides:
            if overrides[role] not in headers:
                die("--col %s=%r: no such column; columns are %s" % (role, overrides[role], headers))
            mapping[role] = overrides[role]
            continue
        for cand in CANDIDATES[role]:
            if cand in by_norm and by_norm[cand] not in mapping.values():
                mapping[role] = by_norm[cand]
                break
        else:
            mapping[role] = None
    return mapping


def parse_cap(v):
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if x > 0 and x == x and x != float("inf") else None


def format_cap(num):
    """Mirror of formatMarketCap() in visualization.js."""
    if num is None:
        return "-"
    a = abs(num)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            s = "%.2f%s" % (a / div, suf)
            break
    else:
        s = "%.2f" % a
    return "-" + s if num < 0 else s


def is_etf(row, mapping, etf_sector):
    g = lambda role: (row.get(mapping[role]) or "").strip() if mapping.get(role) else ""
    sector = g("sector")
    if sector.upper() == etf_sector.upper():
        return True
    return parse_cap(g("marketCap")) is None and not g("country") and not g("website")


def price_files(data_dir, desc_path):
    """Map lower-case ticker -> relative path of its price-history CSV."""
    found = {}
    for root, _dirs, files in os.walk(data_dir):
        for f in files:
            p = os.path.join(root, f)
            if not f.lower().endswith(".csv") or os.path.abspath(p) == os.path.abspath(desc_path):
                continue
            found[os.path.splitext(f)[0].lower()] = os.path.relpath(p, data_dir)
    return found


def analyse(data_dir, desc_path, overrides, etf_sector):
    headers, rows = read_csv(desc_path)
    mapping = resolve_columns(headers, overrides)
    warnings = []
    missing = [r for r in REQUIRED if not mapping[r]]
    if missing:
        warnings.append("required roles not mapped: %s -> pass --col role=Column" % missing)
    out = {
        "descriptions": os.path.relpath(desc_path, data_dir),
        "row_count": len(rows),
        "columns": headers,
        "mapping": mapping,
        "etf_sector_label": etf_sector,
    }
    if missing:
        out["warnings"] = warnings
        return out, rows, mapping
    tick = lambda r: (r.get(mapping["ticker"]) or "").strip()
    tickers = [tick(r) for r in rows]
    blank = [i for i, t in enumerate(tickers) if not t]
    if blank:
        warnings.append("rows with blank ticker (dropped from the chart): %s" % blank)
    dups = sorted({t for t in tickers if t and tickers.count(t) > 1})
    if dups:
        warnings.append("duplicate tickers (selection links by ticker): %s" % dups)
    sectors = {}
    etfs, no_cap_stocks, sample = [], [], []
    for r in rows:
        t = tick(r)
        if not t:
            continue
        s = (r.get(mapping["sector"]) or "").strip() or "Unknown"
        sectors[s] = sectors.get(s, 0) + 1
        cap = parse_cap(r.get(mapping["marketCap"]))
        if is_etf(r, mapping, etf_sector):
            etfs.append(t)
        elif cap is None:
            no_cap_stocks.append(t)
        if len(sample) < 5 and cap is not None:
            sample.append({"ticker": t, "marketCap": r.get(mapping["marketCap"]), "formatted": format_cap(cap)})
    if no_cap_stocks:
        warnings.append("non-ETF rows without market cap (drawn at ETF size, tooltip kept): %s" % no_cap_stocks)
    if not any(s.upper() == etf_sector.upper() for s in sectors) and etfs:
        warnings.append("no sector equals %r; ETFs were inferred from empty marketCap/country/website"
                        % etf_sector)
    if len(sectors) > 10:
        warnings.append("%d sectors > 10 colors in schemeCategory10; palette is extended" % len(sectors))
    pf = price_files(data_dir, desc_path)
    matched = {t: pf[t.lower()] for t in tickers if t and t.lower() in pf}
    case_mismatch = sorted(t for t, p in matched.items()
                           if os.path.splitext(os.path.basename(p))[0] != t)
    out.update({
        "sectors": dict(sorted(sectors.items())),
        "etf_tickers": etfs,
        "stocks_without_market_cap": no_cap_stocks,
        "sample_market_cap_format": sample,
        "price_history": {
            "files_found": len(pf),
            "matched": len(matched),
            "tickers_without_file": [t for t in tickers if t and t.lower() not in pf],
            "filename_case_differs_from_ticker": case_mismatch,
            "files_without_ticker": sorted(set(pf) - {t.lower() for t in tickers}),
        },
        "warnings": warnings,
    })
    return out, rows, mapping


def get_d3(dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isfile(D3_VENDORED):
        shutil.copyfile(D3_VENDORED, dest)
    else:
        for url in D3_URLS:
            try:
                with urllib.request.urlopen(url, timeout=30) as r, open(dest, "wb") as f:
                    f.write(r.read())
                break
            except Exception:
                if subprocess.call(["curl", "-fsSL", "-o", dest, url]) == 0:
                    break
        else:
            die("assets/d3.v6.min.js missing and download failed")
    with open(dest, encoding="utf-8", errors="replace") as f:
        head = f.read(200)
    if "v6." not in head:
        die("%s does not look like D3 v6 (header: %r)" % (dest, head[:80]))
    return head.splitlines()[0]


def fill(template_name, replacements):
    with open(os.path.join(TEMPLATES, template_name), encoding="utf-8") as f:
        text = f.read()
    for pattern, value in replacements:
        new, n = re.subn(pattern, lambda _m: value, text, flags=re.S)
        if n != 1:
            die("template %s: placeholder %s matched %d times" % (template_name, pattern, n))
        text = new
    return text


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def build(args, overrides):
    data_dir = os.path.abspath(args.data_dir)
    out_dir = os.path.abspath(args.out)
    desc_path = find_descriptions(data_dir, args.descriptions)
    info, rows, mapping = analyse(data_dir, desc_path, overrides, args.etf_sector)
    missing = [r for r in REQUIRED if not mapping[r]]
    if missing:
        die("required roles not mapped: %s; columns are %s; pass --col role=Column"
            % (missing, info["columns"]))
    if out_dir == data_dir or out_dir.startswith(data_dir + os.sep):
        die("--out must not be inside --data-dir")

    # 1. data -> <out>/data (verbatim copy, original file names kept)
    shutil.copytree(data_dir, os.path.join(out_dir, "data"), dirs_exist_ok=True)
    # 2. d3
    d3_header = get_d3(os.path.join(out_dir, "js", "d3.v6.min.js"))
    # 3. js with config + embedded rows
    rel_desc = "data/" + os.path.relpath(desc_path, data_dir).replace(os.sep, "/")
    config = {
        "dataFile": rel_desc,
        "columns": {k: v for k, v in mapping.items() if v},
        "etfSector": args.etf_sector,
    }
    embedded = [{mapping[k]: r.get(mapping[k], "") for k in ROLES if mapping[k]} for r in rows]
    js = fill("visualization.js", [
        (r"/\*__CONFIG__\*/.*?/\*__END_CONFIG__\*/", json.dumps(config, ensure_ascii=False)),
        (r"/\*__EMBEDDED_ROWS__\*/.*?/\*__END_ROWS__\*/",
         json.dumps(embedded, ensure_ascii=False, indent=0).replace("</", "<\\/")),
    ])
    write(os.path.join(out_dir, "js", "visualization.js"), js)
    # 4. html + css
    with open(os.path.join(TEMPLATES, "index.html"), encoding="utf-8") as f:
        html = f.read().replace("__TITLE__", args.title.replace("&", "&amp;").replace("<", "&lt;"))
    write(os.path.join(out_dir, "index.html"), html)
    with open(os.path.join(TEMPLATES, "style.css"), encoding="utf-8") as f:
        write(os.path.join(out_dir, "css", "style.css"), f.read())

    print(json.dumps({
        "out": out_dir,
        "files": ["index.html", "css/style.css", "js/visualization.js", "js/d3.v6.min.js", "data/"],
        "d3": d3_header,
        "dataFile": rel_desc,
        "mapping": mapping,
        "rows": len(rows),
        "sectors": info.get("sectors"),
        "etf_tickers": info.get("etf_tickers"),
        "warnings": info.get("warnings", []),
    }, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("inspect", "build"):
        p = sub.add_parser(name)
        p.add_argument("--data-dir", required=True)
        p.add_argument("--descriptions", help="descriptions CSV, relative to --data-dir (default: auto)")
        p.add_argument("--col", action="append", default=[], metavar="ROLE=COLUMN",
                       help="override column for role: %s" % ", ".join(ROLES))
        p.add_argument("--etf-sector", default="ETF", help="sector label marking ETFs (default ETF)")
        if name == "build":
            p.add_argument("--out", required=True)
            p.add_argument("--title", default="Stock Market Overview")
    args = ap.parse_args()
    overrides = {}
    for item in args.col:
        if "=" not in item:
            die("--col expects ROLE=COLUMN, got %r" % item)
        k, v = item.split("=", 1)
        if k not in ROLES:
            die("unknown role %r; roles: %s" % (k, ROLES))
        overrides[k] = v
    if not os.path.isdir(args.data_dir):
        die("data dir not found: %s" % args.data_dir)
    if args.cmd == "inspect":
        desc = find_descriptions(os.path.abspath(args.data_dir), args.descriptions)
        info, _rows, _m = analyse(os.path.abspath(args.data_dir), desc, overrides, args.etf_sector)
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        build(args, overrides)


if __name__ == "__main__":
    main()
