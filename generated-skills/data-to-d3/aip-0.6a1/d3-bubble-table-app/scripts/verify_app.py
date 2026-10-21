#!/usr/bin/env python3
"""Verify the built web app against the task's requirements, in headless Chromium.

AIP mode: stdin {"state": {"data_dir", "output_dir"}, ...} ->
          stdout {"verify_passed": bool, "verify_report": {...}}
CLI mode: python3 verify_app.py --data-dir /root/data --output-dir /root/output
          (prints the same JSON; exit code 0 always, read verify_passed)

Checks: required files and a verbatim data copy; page renders over http:// and
file:// without console errors; one bubble + one ticker label per row; one legend
item per sector; no bubble overlap; every bubble inside the SVG; clusters by sector
and centred; chart and table side by side; table headers/rows/market-cap format;
tooltip on a stock (ticker, name, sector) and none on an ETF; click bubble -> row
selected and click row -> bubble selected.
"""
import argparse
import csv
import functools
import http.server
import json
import math
import os
import re
import sys
import threading

HEADERS = ["Ticker symbol", "Full company name", "Sector", "Market cap"]
CAP_RE = re.compile(r"^\d+(\.\d+)?[KMBT]?$")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_app import find_descriptions, profile  # noqa: E402


class Report:
    def __init__(self):
        self.checks = []

    def add(self, name, ok, detail=""):
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return ok

    @property
    def failures(self):
        return [c for c in self.checks if not c["ok"]]


def static_checks(rep, data_dir, out):
    for rel in ["index.html", "js/d3.v6.min.js", "js/visualization.js", "css/style.css"]:
        rep.add(f"file {rel}", os.path.isfile(os.path.join(out, rel)), "missing" if not os.path.isfile(os.path.join(out, rel)) else "")
    d3p = os.path.join(out, "js/d3.v6.min.js")
    if os.path.isfile(d3p):
        with open(d3p, "rb") as f:
            head = f.read(300)
        rep.add("d3 is v6", b"v6." in head, head[:60].decode("utf-8", "replace"))
    missing = []
    for root, _, files in os.walk(data_dir):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), data_dir)
            dst = os.path.join(out, "data", rel)
            if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(os.path.join(root, fn)):
                missing.append(rel)
    rep.add("data/ is a complete copy of the input data", not missing, f"missing/different: {missing[:10]}" if missing else "")
    ip = os.path.join(out, "index.html")
    if os.path.isfile(ip):
        html = open(ip, encoding="utf-8").read()
        for ref in ["js/d3.v6.min.js", "js/visualization.js", "css/style.css"]:
            rep.add(f"index.html links {ref}", ref in html)
        rep.add("no CDN script tags", not re.search(r"<script[^>]+src=[\"']https?://", html))


JS_STATE = r"""
() => {
  const svg = document.querySelector('#chart svg');
  const sb = svg.getBoundingClientRect();
  const bubbles = Array.from(document.querySelectorAll('circle.bubble')).map(c => {
    const r = c.getBoundingClientRect();
    return {ticker: c.getAttribute('data-ticker'), sector: c.getAttribute('data-sector'),
            x: r.x + r.width / 2, y: r.y + r.height / 2, r: r.width / 2};
  });
  const labels = Array.from(document.querySelectorAll('text.bubble-label')).map(t => t.textContent.trim());
  const legend = Array.from(document.querySelectorAll('.legend-item')).map(g => g.textContent.trim());
  const headers = Array.from(document.querySelectorAll('#data-table thead th')).map(th => th.textContent.trim());
  const rows = Array.from(document.querySelectorAll('#data-table tbody tr')).map(tr =>
      Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim()));
  const rect = s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; };
  return {svg: {x: sb.x, y: sb.y, w: sb.width, h: sb.height}, bubbles, labels, legend, headers, rows,
          chart: rect('#chart svg'), table: rect('#data-table') , tableBox: rect('#table-container')};
}
"""


def geometry_checks(rep, st, recs):
    tickers = [r["ticker"] for r in recs]
    sectors = sorted({r["sector"] for r in recs})
    b = st["bubbles"]
    rep.add("one bubble per row", len(b) == len(recs), f"{len(b)} bubbles vs {len(recs)} rows")
    rep.add("every ticker labelled inside its bubble", sorted(st["labels"]) == sorted(tickers),
            f"{len(st['labels'])} labels")
    rep.add("legend has one item per sector", sorted(st["legend"]) == sectors, f"{st['legend']} vs {sectors}")
    overlaps = []
    for i in range(len(b)):
        for j in range(i + 1, len(b)):
            d = math.hypot(b[i]["x"] - b[j]["x"], b[i]["y"] - b[j]["y"])
            if d < b[i]["r"] + b[j]["r"] - 0.5:
                overlaps.append(f"{b[i]['ticker']}/{b[j]['ticker']}")
    rep.add("no overlapping bubbles", not overlaps, f"{overlaps[:10]}")
    s = st["svg"]
    outside = [x["ticker"] for x in b if x["x"] - x["r"] < s["x"] - 0.5 or x["x"] + x["r"] > s["x"] + s["w"] + 0.5
               or x["y"] - x["r"] < s["y"] - 0.5 or x["y"] + x["r"] > s["y"] + s["h"] + 0.5]
    rep.add("all bubbles inside the SVG", not outside, f"{outside}")
    # clustering: each bubble nearer its own sector centroid than any other sector's
    cent = {}
    for sec in sectors:
        pts = [x for x in b if x["sector"] == sec]
        if pts:
            cent[sec] = (sum(p["x"] for p in pts) / len(pts), sum(p["y"] for p in pts) / len(pts))
    wrong = [x["ticker"] for x in b if cent and min(cent, key=lambda k: math.hypot(x["x"] - cent[k][0], x["y"] - cent[k][1])) != x["sector"]]
    rep.add("bubbles cluster by sector (>=90% nearest own centroid)", len(wrong) <= 0.1 * max(1, len(b)), f"misplaced: {wrong}")
    if b:
        x0 = min(x["x"] - x["r"] for x in b); x1 = max(x["x"] + x["r"] for x in b)
        y0 = min(x["y"] - x["r"] for x in b); y1 = max(x["y"] + x["r"] for x in b)
        off = abs((x0 + x1) / 2 - (s["x"] + s["w"] / 2)) / s["w"]
        fill = (x1 - x0) * (y1 - y0) / (s["w"] * s["h"])
        rep.add("clusters centred and compact", off < 0.1 and fill > 0.3,
                f"horizontal offset {off:.2%} of width, bubbles span {fill:.0%} of the SVG")
    c, t = st["chart"], st["tableBox"] or st["table"]
    side = c and t and t["x"] >= c["x"] + c["w"] - 1 and t["y"] < c["y"] + c["h"] and c["y"] < t["y"] + t["h"]
    rep.add("chart and table side by side horizontally", side, f"chart {c} table {t}")
    rep.add("table headers", st["headers"] == HEADERS, f"{st['headers']}")
    rep.add("table lists every row", len(st["rows"]) == len(recs), f"{len(st['rows'])} rows")
    by_t = {r["ticker"]: r for r in recs}
    bad = [row for row in st["rows"] if len(row) == 4 and row[0] in by_t and not by_t[row[0]]["isETF"]
           and not CAP_RE.match(row[3])]
    rep.add("market cap formatted like 1.64T / 193.22B", not bad, f"{bad[:5]}")
    big = max((r for r in recs if not r["isETF"]), key=lambda r: r["marketCap"], default=None)
    if big:
        row = next((x for x in st["rows"] if x and x[0] == big["ticker"]), None)
        cap = big["marketCap"]
        expect = next(f"{cap / d:.2f}{u}" for d, u in [(1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K"), (1, "")] if cap >= d)
        rep.add("largest market cap value correct", row is not None and row[3] == expect, f"{big['ticker']}: {row and row[3]} vs {expect}")


def interaction_checks(rep, page, recs):
    stock = next((r for r in recs if not r["isETF"]), None)
    etf = next((r for r in recs if r["isETF"]), None)
    tip = page.locator("#tooltip")

    def tip_visible():
        return page.evaluate("() => { const t = document.querySelector('#tooltip'); return !!t && t.classList.contains('visible') && parseFloat(getComputedStyle(t).opacity) > 0; }")

    if stock:
        page.mouse.move(1, 1)
        page.hover(f'circle.bubble[data-ticker="{stock["ticker"]}"]', timeout=5000)
        page.wait_for_timeout(350)
        txt = tip.inner_text() if tip.count() else ""
        ok = tip_visible() and stock["ticker"] in txt and stock["sector"] in txt and stock["name"][:20] in txt
        rep.add("tooltip on a stock shows ticker, name, sector", ok, f"{stock['ticker']}: {txt!r}")
        page.mouse.move(1, 1)
        page.wait_for_timeout(350)
        rep.add("tooltip hides on mouseout", not tip_visible())
    if etf:
        page.hover(f'circle.bubble[data-ticker="{etf["ticker"]}"]', timeout=5000)
        page.wait_for_timeout(350)
        rep.add("no tooltip on an ETF / no-market-cap bubble", not tip_visible(), etf["ticker"])
        page.mouse.move(1, 1)

    sel_rows = "() => Array.from(document.querySelectorAll('#data-table tbody tr.selected')).map(r => r.getAttribute('data-ticker'))"
    sel_bub = "() => Array.from(document.querySelectorAll('circle.bubble.selected')).map(c => c.getAttribute('data-ticker'))"
    in_table = page.evaluate("() => Array.from(document.querySelectorAll('#data-table tbody tr[data-ticker]')).map(r => r.getAttribute('data-ticker'))")
    linked = [r["ticker"] for r in recs if r["ticker"] in in_table]
    if not linked:
        rep.add("click bubble -> bubble and its table row highlighted", False, "no table row carries a data-ticker matching a bubble")
        rep.add("click row -> row and its bubble highlighted", False, "no table row carries a data-ticker matching a bubble")
        return
    a, b = linked[0], linked[-1]
    for name, sel, t in [("click bubble -> bubble and its table row highlighted", f'circle.bubble[data-ticker="{a}"]', a),
                         ("click row -> row and its bubble highlighted", f'#data-table tbody tr[data-ticker="{b}"]', b)]:
        try:
            page.click(sel, timeout=5000)
            rows, bubs = page.evaluate(sel_rows), page.evaluate(sel_bub)
            rep.add(name, rows == [t] and bubs == [t], f"rows {rows} bubbles {bubs}")
        except Exception as e:
            rep.add(name, False, f"{sel}: {str(e).splitlines()[0]}")


def browser_checks(rep, data_dir, out, recs):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # pragma: no cover
        rep.add("browser checks", False, f"playwright not importable: {e}")
        return False

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    handler = functools.partial(Quiet, directory=out)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/index.html"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1500, "height": 950})
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            try:
                page.wait_for_selector("body[data-rendered=true]", timeout=15000)
                rendered = True
            except Exception:
                rendered = False
            rep.add("renders over http://", rendered, url)
            rep.add("no console errors (http)", not errors, f"{errors[:5]}")
            if rendered:
                geometry_checks(rep, page.evaluate(JS_STATE), recs)
                try:
                    interaction_checks(rep, page, recs)
                except Exception as e:
                    rep.add("interaction checks ran", False, str(e).splitlines()[0])
            # file:// (double-click open): d3.csv fetch is blocked, embedded fallback must render
            fpage = browser.new_page(viewport={"width": 1500, "height": 950})
            ferrs = []
            fpage.on("pageerror", lambda e: ferrs.append(str(e)))
            fpage.goto("file://" + os.path.join(out, "index.html"))
            try:
                fpage.wait_for_selector("body[data-rendered=true]", timeout=15000)
                n = fpage.locator("circle.bubble").count()
            except Exception:
                n = 0
            rep.add("renders when opened from file://", n == len(recs) and not ferrs, f"{n} bubbles, errors {ferrs[:3]}")
            browser.close()
    finally:
        srv.shutdown()
    return True


def verify(data_dir, output_dir):
    data_dir, out = os.path.abspath(data_dir), os.path.abspath(output_dir)
    rep = Report()
    static_checks(rep, data_dir, out)
    _, _, recs, _, _ = profile(data_dir, find_descriptions(data_dir))
    browser = False
    if os.path.isfile(os.path.join(out, "index.html")):
        browser = browser_checks(rep, data_dir, out, recs)
    fails = rep.failures
    return not fails, {
        "browser_checked": browser,
        "n_checks": len(rep.checks),
        "n_failed": len(fails),
        "failures": fails,
        "checks": rep.checks,
    }


def main():
    if len(sys.argv) > 1:
        ap = argparse.ArgumentParser()
        ap.add_argument("--data-dir", required=True)
        ap.add_argument("--output-dir", required=True)
        a = ap.parse_args()
        ok, report = verify(a.data_dir, a.output_dir)
    else:
        st = json.load(sys.stdin).get("state", {})
        ok, report = verify(st["data_dir"], st["output_dir"])
    json.dump({"verify_passed": ok, "verify_report": report}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
