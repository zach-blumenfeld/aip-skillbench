#!/usr/bin/env python3
"""Verify the built web app in headless Chromium against the input CSV.

Requires: Python >= 3.8, the `playwright` pip package with Chromium installed
(the task Dockerfile installs both). Standard library otherwise. Imports the
column-mapping and number-format helpers from scripts/build_app.py.

Usage (run from the skill folder):
  python3 scripts/verify_app.py --out /root/output --data-dir /root/data \
      [--descriptions stock-descriptions.csv] [--col name="full name" ...] \
      [--etf-sector ETF] [--static-only]

Checks the app twice: opened as file://.../index.html and served over
http://127.0.0.1. Prints one PASS/FAIL line per check; exit 0 only if all pass.
"""
import argparse
import functools
import http.server
import os
import sys
import threading

sys.dont_write_bytecode = True  # keep the skill folder clean
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_app as B  # noqa: E402

RESULTS = []
TABLE_HEADERS = ["Ticker symbol", "Full company name", "Sector", "Market cap"]


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, (" -- " + detail) if detail and not ok else ""))
    return ok


def expected_rows(data_dir, desc, overrides, etf_sector):
    headers, rows = B.read_csv(desc)
    m = B.resolve_columns(headers, overrides)
    missing = [r for r in B.REQUIRED if not m[r]]
    if missing:
        B.die("cannot map %s; pass --col" % missing)
    out = []
    for r in rows:
        t = (r.get(m["ticker"]) or "").strip()
        if not t:
            continue
        cap = B.parse_cap(r.get(m["marketCap"]))
        out.append({
            "ticker": t,
            "name": (r.get(m["name"]) or "").strip(),
            "sector": (r.get(m["sector"]) or "").strip() or "Unknown",
            "cap": cap,
            "capText": B.format_cap(cap),
            "etf": B.is_etf(r, m, etf_sector),
        })
    return out


def static_checks(out_dir, data_dir):
    need = ["index.html", "js/d3.v6.min.js", "js/visualization.js", "css/style.css", "data"]
    missing = [p for p in need if not os.path.exists(os.path.join(out_dir, p))]
    check("required output files exist", not missing, "missing: %s" % missing)
    d3p = os.path.join(out_dir, "js", "d3.v6.min.js")
    if os.path.isfile(d3p):
        with open(d3p, encoding="utf-8", errors="replace") as f:
            head = f.read(120)
        check("js/d3.v6.min.js is D3 v6", "v6." in head, head.splitlines()[0] if head else "empty")
    html_p = os.path.join(out_dir, "index.html")
    if os.path.isfile(html_p):
        with open(html_p, encoding="utf-8") as f:
            html = f.read()
        refs = ["js/d3.v6.min.js", "js/visualization.js", "css/style.css"]
        check("index.html links d3, visualization.js, style.css",
              all(r in html for r in refs), "missing refs: %s" % [r for r in refs if r not in html])
        check("index.html loads no remote scripts (offline)",
              "src=\"http" not in html and "src='http" not in html)
    src = []
    for root, _d, files in os.walk(data_dir):
        for f in files:
            p = os.path.join(root, f)
            src.append((os.path.relpath(p, data_dir), os.path.getsize(p)))
    bad = [rel for rel, size in src
           if not os.path.isfile(os.path.join(out_dir, "data", rel))
           or os.path.getsize(os.path.join(out_dir, "data", rel)) != size]
    check("all input data copied to output/data/ (%d files)" % len(src), not bad, "missing/different: %s" % bad[:10])


JS_COLLECT = r"""
() => {
  const svg = document.querySelector('#chart svg') || document.querySelector('svg');
  const sr = svg.getBoundingClientRect();
  const circles = Array.from(svg.querySelectorAll('circle')).filter(c => c.closest('.legend') === null);
  const tickerOf = el => (el.__data__ && (el.__data__.ticker || (el.__data__.data && el.__data__.data.ticker)))
      || el.getAttribute('data-ticker') || '';
  const bubbles = circles.map(c => {
    const r = c.getBoundingClientRect();
    const g = c.parentNode;
    const t = g ? g.querySelector('text') : null;
    const tr = t ? t.getBoundingClientRect() : null;
    return {ticker: tickerOf(c), cx: r.x + r.width / 2, cy: r.y + r.height / 2, r: r.width / 2,
            fill: getComputedStyle(c).fill, label: t ? t.textContent.trim() : null,
            labelBox: tr ? [tr.x, tr.y, tr.width, tr.height] : null};
  });
  const legendEls = Array.from(document.querySelectorAll('[class*="legend"]'));
  const legendText = legendEls.map(e => e.textContent).join(' | ');
  const table = document.querySelector('table');
  const tr = table ? table.getBoundingClientRect() : null;
  const headers = table ? Array.from(table.querySelectorAll('thead th')).map(th => th.textContent.trim()) : [];
  const rows = table ? Array.from(table.querySelectorAll('tbody tr')).map(r =>
      Array.from(r.querySelectorAll('td')).map(td => td.textContent.trim())) : [];
  return {svg: [sr.x, sr.y, sr.width, sr.height], table: tr ? [tr.x, tr.y, tr.width, tr.height] : null,
          bubbles, legendText, headers, rows};
}
"""

JS_TOOLTIP = r"""
() => {
  const t = document.querySelector('#tooltip') || document.querySelector('.tooltip');
  if (!t) return {exists: false};
  const cs = getComputedStyle(t);
  const shown = cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.05;
  return {exists: true, shown, text: t.textContent, cls: t.className};
}
"""

JS_SELECTION = r"""
() => {
  const hl = el => /selected|highlight|active/.test(el.getAttribute('class') || '');
  const tickerOf = el => (el.__data__ && el.__data__.ticker) || el.getAttribute('data-ticker') || '';
  const rows = Array.from(document.querySelectorAll('table tbody tr')).filter(hl)
      .map(r => tickerOf(r) || (r.querySelector('td') || {}).textContent);
  const bubbles = Array.from(document.querySelectorAll('svg circle')).filter(hl).map(tickerOf);
  return {rows, bubbles};
}
"""


def browser_checks(page, url, exp, tag):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    try:
        page.wait_for_function("document.querySelectorAll('svg circle').length > 0 && "
                               "document.querySelectorAll('table tbody tr').length > 0", timeout=15000)
    except Exception as e:  # noqa: BLE001
        check("[%s] app renders bubbles and table rows" % tag, False, str(e).splitlines()[0])
        return
    page.wait_for_timeout(300)
    data = page.evaluate(JS_COLLECT)
    check("[%s] no JavaScript errors" % tag, not errors, "; ".join(errors[:3]))
    bubbles = data["bubbles"]
    by_t = {b["ticker"]: b for b in bubbles}
    tickers = [e["ticker"] for e in exp]
    check("[%s] one bubble per row (%d)" % (tag, len(exp)),
          len(bubbles) == len(exp) and set(by_t) == set(tickers),
          "bubbles=%d, missing=%s" % (len(bubbles), sorted(set(tickers) - set(by_t))[:10]))
    check("[%s] every bubble labelled with its ticker" % tag,
          all(b["label"] == b["ticker"] for b in bubbles),
          str([(b["ticker"], b["label"]) for b in bubbles if b["label"] != b["ticker"]][:5]))
    inside = [b["ticker"] for b in bubbles if b["labelBox"] and
              (b["labelBox"][2] > 2 * b["r"] + 1 or b["labelBox"][3] > 2 * b["r"] + 1)]
    check("[%s] labels fit inside bubbles" % tag, not inside, str(inside[:10]))
    overl = []
    for i in range(len(bubbles)):
        for j in range(i + 1, len(bubbles)):
            a, b = bubbles[i], bubbles[j]
            if ((a["cx"] - b["cx"]) ** 2 + (a["cy"] - b["cy"]) ** 2) ** 0.5 < a["r"] + b["r"] - 0.5:
                overl.append((a["ticker"], b["ticker"]))
    check("[%s] no overlapping bubbles" % tag, not overl, str(overl[:5]))
    sx, sy, sw, sh = data["svg"]
    out = [b["ticker"] for b in bubbles if b["cx"] - b["r"] < sx - 1 or b["cx"] + b["r"] > sx + sw + 1
           or b["cy"] - b["r"] < sy - 1 or b["cy"] + b["r"] > sy + sh + 1]
    check("[%s] all bubbles inside the SVG" % tag, not out, str(out[:10]))
    # centring
    if bubbles:
        x0 = min(b["cx"] - b["r"] for b in bubbles); x1 = max(b["cx"] + b["r"] for b in bubbles)
        y0 = min(b["cy"] - b["r"] for b in bubbles); y1 = max(b["cy"] + b["r"] for b in bubbles)
        dx = abs((x0 + x1) / 2 - (sx + sw / 2)) / sw; dy = abs((y0 + y1) / 2 - (sy + sh / 2)) / sh
        fill = max((x1 - x0) / sw, (y1 - y0) / sh)
        check("[%s] clusters centred and filling the chart" % tag, dx < 0.1 and dy < 0.1 and fill > 0.6,
              "offset x=%.2f y=%.2f fill=%.2f" % (dx, dy, fill))
    # sizes
    stocks = [e for e in exp if e["cap"] is not None and e["ticker"] in by_t]
    srt = sorted(stocks, key=lambda e: e["cap"])
    mono = all(by_t[a["ticker"]]["r"] <= by_t[b["ticker"]]["r"] + 0.01 for a, b in zip(srt, srt[1:]))
    check("[%s] larger market cap -> larger (or equal) bubble" % tag, mono and
          (len(srt) < 2 or by_t[srt[-1]["ticker"]]["r"] > by_t[srt[0]["ticker"]]["r"]))
    nocap = [by_t[e["ticker"]]["r"] for e in exp if e["cap"] is None and e["ticker"] in by_t]
    check("[%s] rows without market cap (ETFs) uniform size" % tag,
          not nocap or max(nocap) - min(nocap) < 0.01, "radii %s" % sorted(set(round(r, 2) for r in nocap)))
    # colors + clusters
    sectors = sorted({e["sector"] for e in exp})
    fills = {}
    for e in exp:
        if e["ticker"] in by_t:
            fills.setdefault(e["sector"], set()).add(by_t[e["ticker"]]["fill"])
    one = all(len(v) == 1 for v in fills.values())
    distinct = len({next(iter(v)) for v in fills.values()}) == len(fills) if one else False
    check("[%s] one distinct color per sector" % tag, one and distinct, str({k: sorted(v) for k, v in fills.items()}))
    cent = {}
    for s in sectors:
        mem = [by_t[e["ticker"]] for e in exp if e["sector"] == s and e["ticker"] in by_t]
        if mem:
            cent[s] = (sum(b["cx"] for b in mem) / len(mem), sum(b["cy"] for b in mem) / len(mem))
    ok_n = 0
    for e in exp:
        b = by_t.get(e["ticker"])
        if not b:
            continue
        near = min(cent, key=lambda s: (b["cx"] - cent[s][0]) ** 2 + (b["cy"] - cent[s][1]) ** 2)
        ok_n += near == e["sector"]
    frac = ok_n / max(1, len(bubbles))
    check("[%s] bubbles clustered by sector (nearest centroid = own sector)" % tag, frac >= 0.9, "%.0f%%" % (100 * frac))
    miss_leg = [s for s in sectors if s not in data["legendText"]]
    check("[%s] legend names every sector" % tag, not miss_leg, "missing %s" % miss_leg)
    # side by side
    t = data["table"]
    if t:
        side = t[0] >= sx + sw - 5 and t[1] < sy + sh and sy < t[1] + t[3]
        check("[%s] chart and table side by side horizontally" % tag, side, "svg=%s table=%s" % (data["svg"], t))
    check("[%s] table headers %s" % (tag, TABLE_HEADERS), data["headers"] == TABLE_HEADERS, str(data["headers"]))
    rows = {r[0]: r for r in data["rows"] if r}
    check("[%s] table lists every row (%d)" % (tag, len(exp)), len(data["rows"]) == len(exp) and set(rows) == set(tickers),
          "rows=%d" % len(data["rows"]))
    wrong = [(e["ticker"], rows.get(e["ticker"])) for e in exp if rows.get(e["ticker"]) and
             rows[e["ticker"]][1:4] != [e["name"], e["sector"], e["capText"]]]
    check("[%s] table name/sector/market cap match CSV (e.g. 1.64T)" % tag, not wrong, str(wrong[:3]))

    # tooltips: hover every bubble
    bad_tip = []
    page.mouse.move(0, 0)
    for e in exp:
        if e["ticker"] not in by_t:
            continue
        b = by_t[e["ticker"]]
        page.mouse.move(b["cx"], b["cy"])
        page.wait_for_timeout(260)
        tip = page.evaluate(JS_TOOLTIP)
        if not tip["exists"]:
            bad_tip.append("no #tooltip element")
            break
        if e["etf"]:
            if tip["shown"]:
                bad_tip.append("%s (ETF) shows tooltip" % e["ticker"])
        elif not tip["shown"] or not all(x in tip["text"] for x in (e["ticker"], e["name"], e["sector"])):
            bad_tip.append("%s tooltip shown=%s text=%r" % (e["ticker"], tip["shown"], tip["text"][:80]))
        page.mouse.move(0, 0)
        page.wait_for_timeout(30)
    check("[%s] tooltip: ticker+name+sector on stocks, none on ETFs" % tag, not bad_tip, "; ".join(bad_tip[:4]))

    # linked selection
    stock = next((e["ticker"] for e in exp if not e["etf"]), tickers[0])
    other = next((e["ticker"] for e in reversed(exp) if e["ticker"] != stock), stock)
    b = by_t[stock]
    page.mouse.click(b["cx"], b["cy"])
    page.wait_for_timeout(150)
    sel = page.evaluate(JS_SELECTION)
    check("[%s] click bubble %s -> its table row highlighted" % (tag, stock),
          sel["rows"] == [stock] and stock in sel["bubbles"], str(sel))
    page.locator("table tbody tr").filter(has=page.locator("td", has_text=other)).first.click()
    page.wait_for_timeout(150)
    sel = page.evaluate(JS_SELECTION)
    check("[%s] click row %s -> its bubble highlighted" % (tag, other),
          sel["bubbles"] == [other] and other in sel["rows"] and stock not in sel["rows"], str(sel))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--descriptions")
    ap.add_argument("--col", action="append", default=[], metavar="ROLE=COLUMN")
    ap.add_argument("--etf-sector", default="ETF")
    ap.add_argument("--static-only", action="store_true", help="skip browser checks")
    args = ap.parse_args()
    overrides = dict(c.split("=", 1) for c in args.col)
    out_dir, data_dir = os.path.abspath(args.out), os.path.abspath(args.data_dir)
    desc = B.find_descriptions(data_dir, args.descriptions)
    exp = expected_rows(data_dir, desc, overrides, args.etf_sector)
    static_checks(out_dir, data_dir)
    if not args.static_only:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            check("playwright importable (pip package 'playwright')", False,
                  "install it or rerun with --static-only and say browser checks were skipped")
        else:
            class Quiet(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *a):
                    pass
            handler = functools.partial(Quiet, directory=out_dir)
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(args=["--no-sandbox"])
                    for tag, url in (("file", "file://" + os.path.join(out_dir, "index.html")),
                                     ("http", "http://127.0.0.1:%d/index.html" % srv.server_address[1])):
                        page = browser.new_page(viewport={"width": 1400, "height": 900})
                        browser_checks(page, url, exp, tag)
                        page.close()
                    browser.close()
            finally:
                srv.shutdown()
    failed = RESULTS.count(False)
    print("\n%d checks, %d failed" % (len(RESULTS), failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
