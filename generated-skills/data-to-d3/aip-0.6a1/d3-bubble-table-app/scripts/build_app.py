#!/usr/bin/env python3
"""Build the linked bubble-chart + table D3 v6 web app from a stock data folder.

AIP mode: one JSON object on stdin {"state": {"data_dir", "output_dir", ...}, ...};
prints {"data_profile": {...}, "build_report": {...}} on stdout.
CLI mode:  python3 build_app.py --data-dir /root/data --output-dir /root/output

Writes:
  <output_dir>/index.html
  <output_dir>/css/style.css
  <output_dir>/js/d3.v6.min.js      (vendored D3 v6.7.0, no CDN)
  <output_dir>/js/visualization.js  (template + column config + embedded fallback rows)
  <output_dir>/data/...             (verbatim copy of every file under data_dir)
Stdlib only.
"""
import argparse
import csv
import json
import os
import re
import shutil
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
APP = os.path.join(SKILL, "assets", "app")
D3_VENDORED = os.path.join(SKILL, "assets", "vendor", "d3.v6.min.js")
D3_URLS = [
    "https://cdn.jsdelivr.net/npm/d3@6.7.0/dist/d3.min.js",
    "https://unpkg.com/d3@6.7.0/dist/d3.min.js",
    "https://d3js.org/d3.v6.min.js",
]

# Column aliases, compared after lowercasing and stripping non-alphanumerics.
ALIASES = {
    "ticker": ["ticker", "symbol", "tickersymbol", "ticker_symbol"],
    "name": ["fullname", "companyname", "longname", "name", "shortname", "company", "security"],
    "sector": ["sector", "gicssector", "industry"],
    "marketCap": ["marketcap", "marketcapitalization", "mktcap", "cap"],
    "country": ["country"],
    "website": ["website", "url", "web"],
}
REQUIRED = ["ticker", "name", "sector", "marketCap"]

# Fixed categorical palette (colorblind-friendly Tableau 10 order) -> stable colors.
PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2",
           "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]

WIDTH, HEIGHT = 700, 620


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return reader.fieldnames or [], rows


def map_columns(fieldnames):
    by_norm = {}
    for fn in fieldnames:
        by_norm.setdefault(norm(fn), fn)
    mapping = {}
    for key, aliases in ALIASES.items():
        for a in aliases:
            if norm(a) in by_norm:
                mapping[key] = by_norm[norm(a)]
                break
    return mapping


def find_descriptions(data_dir):
    """The top-level CSV whose header maps ticker+sector+marketCap (prefer *descr*)."""
    cands = sorted(f for f in os.listdir(data_dir)
                   if f.lower().endswith(".csv") and os.path.isfile(os.path.join(data_dir, f)))
    cands.sort(key=lambda f: (0 if "descr" in f.lower() else 1, f))
    tried = []
    for f in cands:
        fields, _ = read_csv(os.path.join(data_dir, f))
        m = map_columns(fields)
        tried.append(f"{f}: {fields[:12]}")
        if all(k in m for k in REQUIRED):
            return f
    sys.exit(f"build_app: no CSV in {data_dir} has ticker/name/sector/marketCap columns. "
             f"Tried: {tried or 'no top-level .csv files'}")


def to_float(v):
    try:
        x = float(str(v).strip())
        return x if x == x and x > 0 else None
    except (TypeError, ValueError):
        return None


def profile(data_dir, desc_file):
    fields, rows = read_csv(os.path.join(data_dir, desc_file))
    cmap = map_columns(fields)
    recs = []
    for r in rows:
        t = (r.get(cmap["ticker"]) or "").strip()
        if not t:
            continue
        cap = to_float(r.get(cmap["marketCap"]))
        sector = (r.get(cmap["sector"]) or "").strip() or "Unknown"
        recs.append({"ticker": t, "name": (r.get(cmap["name"]) or "").strip(), "sector": sector,
                     "marketCap": cap, "isETF": sector.upper() == "ETF" or cap is None})
    sectors = {}
    for x in recs:
        sectors[x["sector"]] = sectors.get(x["sector"], 0) + 1
    # price-history folder(s): subdirectories holding CSVs, matched to tickers case-insensitively
    price_dirs, price_files, price_paths = [], {}, {}
    for d in sorted(os.listdir(data_dir)):
        p = os.path.join(data_dir, d)
        if os.path.isdir(p):
            files = sorted(f for f in os.listdir(p) if f.lower().endswith(".csv"))
            if files:
                price_dirs.append(d)
                for f in files:
                    price_files[os.path.splitext(f)[0].upper()] = f"{d}/{f}"
    # ticker (upper case) -> app-relative path, for the rows that have a file
    for t in [x["ticker"] for x in recs]:
        if t.upper() in price_files:
            price_paths[t.upper()] = "data/" + price_files[t.upper()]
    tickers = [x["ticker"] for x in recs]
    warnings = []
    dup = sorted({t for t in tickers if tickers.count(t) > 1})
    if dup:
        warnings.append(f"duplicate tickers: {dup}")
    no_sector = [x["ticker"] for x in recs if x["sector"] == "Unknown"]
    if no_sector:
        warnings.append(f"rows without sector (shown as 'Unknown'): {no_sector}")
    mixed = [x["ticker"] for x in recs if x["sector"].upper() != "ETF" and x["marketCap"] is None]
    if mixed:
        warnings.append(f"non-ETF rows without market cap (treated like ETFs: uniform size, no tooltip): {mixed}")
    return fields, cmap, recs, {
        "descriptions_file": desc_file,
        "columns": [f for f in fields if f],
        "column_map": cmap,
        "n_rows": len(recs),
        "sectors": sectors,
        "no_market_cap_tickers": [x["ticker"] for x in recs if x["isETF"]],
        "price_history_dirs": price_dirs,
        "tickers_without_price_file": [t for t in tickers if t.upper() not in price_files],
        "price_files_without_ticker": sorted(v for k, v in price_files.items()
                                             if k not in {t.upper() for t in tickers}),
        "warnings": warnings,
    }, price_paths


def get_d3():
    if os.path.isfile(D3_VENDORED):
        with open(D3_VENDORED, "rb") as f:
            return f.read(), "vendored assets/vendor/d3.v6.min.js"
    for url in D3_URLS:
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                body = r.read()
            if b"d3js.org v6" in body[:200]:
                return body, url
        except Exception:
            continue
    sys.exit("build_app: vendored D3 missing and every download URL failed: " + ", ".join(D3_URLS))


def build(data_dir, output_dir, title=None):
    data_dir = os.path.abspath(data_dir)
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(data_dir):
        sys.exit(f"build_app: data_dir not found: {data_dir}")
    desc = find_descriptions(data_dir)
    fields, cmap, recs, prof, price_paths = profile(data_dir, desc)
    if not recs:
        sys.exit(f"build_app: {desc} has no rows with a ticker")

    for sub in ("js", "css", "data"):
        os.makedirs(os.path.join(output_dir, sub), exist_ok=True)

    # data/: copy the provided input data verbatim (structure preserved)
    out_data = os.path.join(output_dir, "data")
    if os.path.commonpath([data_dir, out_data]) != out_data:
        shutil.copytree(data_dir, out_data, dirs_exist_ok=True)

    d3_bytes, d3_src = get_d3()
    with open(os.path.join(output_dir, "js", "d3.v6.min.js"), "wb") as f:
        f.write(d3_bytes)

    # Embedded fallback = raw rows restricted to the mapped columns (same shape d3.csv yields).
    keep = [v for v in cmap.values()]
    _, raw_rows = read_csv(os.path.join(data_dir, desc))
    embedded = [{k: r.get(k, "") for k in keep} for r in raw_rows]
    config = {
        "dataPath": "data/" + desc,
        "columns": cmap,
        "width": WIDTH,
        "height": HEIGHT,
        "palette": PALETTE,
        "priceFiles": price_paths,
    }
    with open(os.path.join(APP, "visualization.js"), encoding="utf-8") as f:
        js = f.read()
    js = js.replace("__APP_CONFIG__", json.dumps(config, indent=4))
    js = js.replace("__EMBEDDED_ROWS__", json.dumps(embedded, separators=(",", ":")))
    with open(os.path.join(output_dir, "js", "visualization.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write(js)

    title = title or "Stock Market Overview: Sectors, Market Cap and Details"
    with open(os.path.join(APP, "index.html"), encoding="utf-8") as f:
        html = f.read().replace("__TITLE__", title)
    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    shutil.copyfile(os.path.join(APP, "style.css"), os.path.join(output_dir, "css", "style.css"))

    written = []
    for root, _, files in os.walk(output_dir):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), output_dir)
            if not rel.startswith("data" + os.sep):
                written.append(rel)
    n_data = sum(len(fs) for _, _, fs in os.walk(out_data))
    report = {
        "output_dir": output_dir,
        "files": sorted(written),
        "data_files_copied": n_data,
        "d3_source": d3_src,
        "data_path_in_app": config["dataPath"],
        "bubbles": len(recs),
        "table_rows": len(recs),
        "sectors": list(prof["sectors"].keys()),
        "uniform_size_no_tooltip": prof["no_market_cap_tickers"],
    }
    return prof, report


def main():
    if len(sys.argv) > 1:
        ap = argparse.ArgumentParser()
        ap.add_argument("--data-dir", required=True)
        ap.add_argument("--output-dir", required=True)
        ap.add_argument("--title")
        a = ap.parse_args()
        prof, report = build(a.data_dir, a.output_dir, a.title)
    else:
        payload = json.load(sys.stdin)
        st = payload.get("state", {})
        prof, report = build(st["data_dir"], st["output_dir"])
    json.dump({"data_profile": prof, "build_report": report}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
