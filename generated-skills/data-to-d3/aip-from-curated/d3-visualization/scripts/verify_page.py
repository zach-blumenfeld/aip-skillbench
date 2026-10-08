"""Verify a generated D3 page: offline, deterministic, renders, and its interactions work.

State in:  page_manifest {html_path, js_paths, css_paths, d3_path, d3_version, svg_path?, png_path?,
           expect {svg_selector, mark_selector, mark_count, key_attr, tooltip_selector,
           tooltip_included_keys, tooltip_excluded_keys, tooltip_contains_key (default true: tooltip text
           must include the key), table_row_selector, table_row_count, linked, no_overlap,
           within_bounds (both geometry checks apply to <circle> marks only), label_selector}}
           (every expect key optional)
State out: verify_status "pass" | "fail", verification {failures, warnings, checks, browser_checked}

Static checks always run. Browser checks run when Python Playwright + Chromium are importable
(the task container installs them); otherwise they are reported as skipped in warnings.
"""
import functools
import http.server
import os
import re
import threading

from d3common import d3_header_version, emit, read_stdin

SRC_RE = re.compile(r"<script[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)
HREF_RE = re.compile(r"<link[^>]*\bhref\s*=\s*[\"']([^\"']+)[\"']", re.I)
INLINE_RE = re.compile(r"<script(?![^>]*\bsrc)[^>]*>(.*?)</script>", re.I | re.S)


def read(p):
    with open(p, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def static_checks(m, failures, warnings, checks):
    html = m.get("html_path")
    if not html or not os.path.isfile(html):
        failures.append(f"html_path not found: {html!r}")
        return []
    text = read(html)
    base = os.path.dirname(html)
    refs = SRC_RE.findall(text) + HREF_RE.findall(text)
    local_js = []
    d3_seen_at, first_user_js_at = None, None
    for i, ref in enumerate(SRC_RE.findall(text)):
        if re.match(r"^(https?:)?//", ref):
            failures.append(f"remote script {ref} (CDN); vendor it locally")
            continue
        p = os.path.normpath(os.path.join(base, ref.split("?")[0]))
        if not os.path.isfile(p):
            failures.append(f"script src {ref} does not exist at {p}")
            continue
        v = d3_header_version(p)
        if v:
            d3_seen_at = i if d3_seen_at is None else d3_seen_at
            want = str(m.get("d3_version") or "").lstrip("v").split(".")[0]
            checks.append(f"d3 {v} loaded from {ref}")
            if want and v.split(".")[0] != want:
                failures.append(f"page loads d3 {v} but the task/manifest asks for major version {want}")
        else:
            local_js.append(p)
            if first_user_js_at is None and "d3." in read(p):
                first_user_js_at = i
    for ref in HREF_RE.findall(text):
        if re.match(r"^(https?:)?//", ref):
            failures.append(f"remote stylesheet/link {ref}; keep the page offline")
        elif not os.path.isfile(os.path.normpath(os.path.join(base, ref.split("?")[0]))):
            failures.append(f"link href {ref} does not exist")
    if d3_seen_at is None and "d3." in text + "".join(read(p) for p in local_js):
        failures.append("page uses d3 but no local d3 bundle is loaded by a <script src>")
    if d3_seen_at is not None and first_user_js_at is not None and first_user_js_at < d3_seen_at:
        failures.append("a script using d3 is loaded before the d3 bundle")
    code = "\n".join(read(p) for p in local_js) + "\n".join(INLINE_RE.findall(text))
    if re.search(r"Math\.random\s*\(", code):
        failures.append("Math.random() used; output must be deterministic")
    if re.search(r"d3\.random", code):
        failures.append("d3-random used; output must be deterministic")
    if re.search(r"\.transition\s*\(", code):
        warnings.append(".transition() used; no animations by default unless the task asks for them")
    if re.search(r"Date\.now\s*\(|new Date\(\s*\)", code):
        warnings.append("current-time call found; output may differ between runs")
    if "forceSimulation" in code and not re.search(r"\.tick\s*\(", code):
        warnings.append("force simulation without a fixed tick loop; run exactly N ticks and stop")
    for p in [html] + local_js + [c for c in (m.get("css_paths") or []) if os.path.isfile(c)]:
        if "\r\n" in read(p):
            failures.append(f"CRLF line endings in {p}; use LF")
    css = "\n".join(read(c) for c in (m.get("css_paths") or []) if os.path.isfile(c)) + \
        "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.S | re.I))
    if (m.get("expect") or {}).get("tooltip_selector") or ".tooltip" in css:
        if ".tooltip.visible" not in css.replace(" ", ""):
            warnings.append("no .tooltip.visible CSS rule; toggle tooltips with a .visible class")
        if "pointer-events:none" not in css.replace(" ", ""):
            warnings.append("tooltip lacks pointer-events: none; it can block mouse events")
    checks.append(f"static: {len(refs)} local refs checked")
    return local_js


def serve(directory):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass
    handler = functools.partial(Quiet, directory=directory)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


GEOM_JS = """(sel) => {
  const svg = document.querySelector(sel.svg) || document.querySelector('svg');
  if (!svg) return null;
  const vb = svg.viewBox && svg.viewBox.baseVal && svg.viewBox.baseVal.width ? svg.viewBox.baseVal : null;
  const W = vb ? vb.width : parseFloat(svg.getAttribute('width')), H = vb ? vb.height : parseFloat(svg.getAttribute('height'));
  const cs = Array.from(document.querySelectorAll(sel.marks)).filter(c => c.tagName.toLowerCase() === 'circle')
    .map(c => ({k: c.getAttribute(sel.key) || '', x: +c.getAttribute('cx'), y: +c.getAttribute('cy'), r: +c.getAttribute('r')}));
  return {W, H, hasSize: !!(svg.getAttribute('width') && svg.getAttribute('height')) || !!vb, cs};
}"""


def tooltip_state(page, sel):
    return page.evaluate("""(s) => { const t = document.querySelector(s); if (!t) return null;
      const st = getComputedStyle(t);
      return {cls: t.className.toString(), op: parseFloat(st.opacity), disp: st.display, vis: st.visibility, text: t.textContent}; }""", sel)


def tip_visible(t):
    return bool(t) and ("visible" in t["cls"].split() or t["op"] > 0.5) and t["disp"] != "none" and t["vis"] != "hidden" and t["op"] > 0


def hover(page, selector):
    loc = page.locator(selector).first
    try:
        loc.hover(timeout=2000)
    except Exception:  # covered by another mark: dispatch the event at its centre instead
        page.eval_on_selector(selector, """el => { const b = el.getBoundingClientRect();
          el.dispatchEvent(new MouseEvent('mouseover', {bubbles: true, clientX: b.x + b.width/2, clientY: b.y + b.height/2}));
          el.dispatchEvent(new MouseEvent('mousemove', {bubbles: true, clientX: b.x + b.width/2, clientY: b.y + b.height/2})); }""")


def unhover(page, selector):
    page.mouse.move(1, 1)
    page.eval_on_selector(selector, "el => el.dispatchEvent(new MouseEvent('mouseout', {bubbles: true}))")


def click(page, selector):
    try:
        page.locator(selector).first.click(timeout=2000)
    except Exception:
        page.eval_on_selector(selector, "el => el.dispatchEvent(new MouseEvent('click', {bubbles: true}))")


def is_marked(page, selector):
    return page.eval_on_selector(selector, """el => el.classList.contains('selected') || el.classList.contains('highlighted')
      || el.classList.contains('active')""")


def browser_checks(m, failures, warnings, checks):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        warnings.append("browser checks skipped: python playwright not importable (static checks only)")
        return False
    e = m.get("expect") or {}
    html = os.path.abspath(m["html_path"])
    svg_sel = e.get("svg_selector") or "svg"
    text = read(html)
    dirs = [os.path.dirname(html)] + [os.path.dirname(os.path.normpath(os.path.join(os.path.dirname(html), r.split("?")[0])))
                                      for r in SRC_RE.findall(text) + HREF_RE.findall(text) if not re.match(r"^(https?:)?//", r)]
    root = os.path.commonpath(dirs)  # serve high enough that ../vendor style refs resolve
    srv = serve(root)
    url_http = f"http://127.0.0.1:{srv.server_address[1]}/{os.path.relpath(html, root).replace(os.sep, '/')}"
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as ex:  # noqa: BLE001
                warnings.append(f"browser checks skipped: chromium failed to launch ({str(ex).splitlines()[0]})")
                return False
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errs = []
            page.on("pageerror", lambda ex: errs.append(f"pageerror: {ex}"))
            page.on("console", lambda msg: errs.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None)
            renders = {}
            for label, url in (("file", "file://" + html), ("http", url_http), ("http-reload", url_http)):
                page.goto(url, wait_until="load")
                try:
                    page.wait_for_selector(svg_sel, timeout=10000)
                    if e.get("mark_selector"):
                        page.wait_for_selector(e["mark_selector"], timeout=10000, state="attached")
                except Exception:  # noqa: BLE001
                    failures.append(f"{label}: {svg_sel} / marks never rendered")
                    continue
                renders[label] = page.eval_on_selector(svg_sel, "el => el.outerHTML")
            errs = [x for x in errs if "favicon" not in x]
            if errs:
                failures.append("browser errors: " + " | ".join(sorted(set(errs))[:6]))
            if len(set(renders.values())) > 1:
                failures.append(f"SVG differs between loads ({', '.join(renders)}): rendering is not deterministic")
            elif renders:
                checks.append(f"identical SVG across {len(renders)} loads")
            if "http" not in renders:
                return True
            if "file" not in renders:
                warnings.append("page does not render from file:// (d3.csv/fetch is blocked there); embed data if the task opens the file directly")
            geo = page.evaluate(GEOM_JS, {"svg": svg_sel, "marks": e.get("mark_selector") or "svg circle",
                                         "key": e.get("key_attr") or "data-key"})
            if geo and not geo["hasSize"]:
                failures.append("svg has neither fixed width/height nor viewBox")
            n = page.locator(e["mark_selector"]).count() if e.get("mark_selector") else None
            if e.get("mark_count") is not None:
                (checks if n == e["mark_count"] else failures).append(f"marks: {n} rendered, expected {e['mark_count']}")
            if e.get("label_selector"):
                nl = page.locator(e["label_selector"]).count()
                if e.get("mark_count") is not None and nl != e["mark_count"]:
                    failures.append(f"labels: {nl} rendered, expected {e['mark_count']}")
            cs = (geo or {}).get("cs") or []
            if e.get("within_bounds") and cs:
                out = [c["k"] for c in cs if c["x"] - c["r"] < -0.5 or c["y"] - c["r"] < -0.5
                       or c["x"] + c["r"] > geo["W"] + 0.5 or c["y"] + c["r"] > geo["H"] + 0.5]
                (failures.append(f"marks outside the svg: {out[:8]}") if out else checks.append("all circles inside svg"))
            if e.get("no_overlap") and cs:
                ov = [(a["k"], b["k"]) for i, a in enumerate(cs) for b in cs[i + 1:]
                      if ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5 < a["r"] + b["r"] - 0.5]
                (failures.append(f"{len(ov)} overlapping circle pairs, e.g. {ov[:4]}") if ov else checks.append("no overlapping circles"))
            if e.get("table_row_selector") and e.get("table_row_count") is not None:
                nr = page.locator(e["table_row_selector"]).count()
                (checks if nr == e["table_row_count"] else failures).append(f"table rows: {nr}, expected {e['table_row_count']}")
            ka, ms, tsel = e.get("key_attr") or "data-key", e.get("mark_selector"), e.get("tooltip_selector")
            if tsel and ms:
                for k in e.get("tooltip_included_keys") or []:
                    s = f'{ms}[{ka}="{k}"]'
                    if not page.locator(s).count():
                        failures.append(f"no mark for key {k}")
                        continue
                    hover(page, s)
                    t = tooltip_state(page, tsel)
                    if not tip_visible(t):
                        failures.append(f"tooltip not visible on hover of {k}: {t}")
                    elif e.get("tooltip_contains_key", True) and str(k) not in (t["text"] or ""):
                        failures.append(f"tooltip for {k} does not mention it: {t['text']!r}")
                    unhover(page, s)
                    t = tooltip_state(page, tsel)
                    if tip_visible(t):
                        failures.append(f"tooltip stays visible after mouseout of {k}")
                for k in e.get("tooltip_excluded_keys") or []:
                    s = f'{ms}[{ka}="{k}"]'
                    if not page.locator(s).count():
                        failures.append(f"no mark for excluded key {k}")
                        continue
                    hover(page, s)
                    if tip_visible(tooltip_state(page, tsel)):
                        failures.append(f"tooltip shown for excluded key {k}")
                    unhover(page, s)
                checks.append(f"tooltip shown for {e.get('tooltip_included_keys') or []}, hidden after mouseout, never shown for excluded {e.get('tooltip_excluded_keys') or []} (see failures otherwise)")
            rs = e.get("table_row_selector")
            if e.get("linked") and ms and rs:
                keys = (e.get("tooltip_included_keys") or []) + (e.get("tooltip_excluded_keys") or [])
                if len(keys) >= 2:
                    k1, k2 = keys[0], keys[-1]
                    click(page, f'{ms}[{ka}="{k1}"]')
                    if not is_marked(page, f'{rs}[{ka}="{k1}"]'):
                        failures.append(f"clicking bubble {k1} did not highlight its table row")
                    if not is_marked(page, f'{ms}[{ka}="{k1}"]'):
                        failures.append(f"clicking bubble {k1} did not mark the bubble itself")
                    click(page, f'{rs}[{ka}="{k2}"]')
                    if not is_marked(page, f'{ms}[{ka}="{k2}"]'):
                        failures.append(f"clicking row {k2} did not highlight its bubble")
                    if is_marked(page, f'{rs}[{ka}="{k1}"]'):
                        failures.append(f"previous selection {k1} stayed highlighted after selecting {k2}")
                    checks.append(f"linking checked: click mark {k1} -> row marked, click row {k2} -> mark marked, previous cleared (see failures otherwise)")
            if m.get("svg_path") and "http" in renders:
                page.goto(url_http, wait_until="load")
                page.wait_for_selector(svg_sel)
                css = "\n".join(open(c, encoding="utf-8").read() for c in (m.get("css_paths") or []) if os.path.isfile(c))
                svg = page.eval_on_selector(svg_sel, """(el, css) => { const c = el.cloneNode(true);
                  c.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
                  const st = document.createElementNS('http://www.w3.org/2000/svg', 'style'); st.textContent = css;
                  c.insertBefore(st, c.firstChild); return c.outerHTML; }""", css)
                os.makedirs(os.path.dirname(os.path.abspath(m["svg_path"])), exist_ok=True)
                with open(m["svg_path"], "w", encoding="utf-8", newline="\n") as f:
                    f.write(svg + "\n")
                checks.append(f"exported {m['svg_path']}")
            if m.get("png_path") and "http" in renders:
                os.makedirs(os.path.dirname(os.path.abspath(m["png_path"])), exist_ok=True)
                page.locator(svg_sel).first.screenshot(path=m["png_path"])
                checks.append(f"exported {m['png_path']}")
            browser.close()
    finally:
        srv.shutdown()
    return True


def main():
    state, _ = read_stdin()
    m = state.get("page_manifest") or {}
    failures, warnings, checks = [], [], []
    br = state.get("build_report") or {}
    failures += [f"build: {x}" for x in br.get("errors") or []]
    static_checks(m, failures, warnings, checks)
    browser = False
    if not failures or all(not f.startswith("html_path") for f in failures):
        try:
            browser = browser_checks(m, failures, warnings, checks) if m.get("html_path") and os.path.isfile(m["html_path"]) else False
        except Exception as ex:  # noqa: BLE001
            warnings.append(f"browser checks aborted: {type(ex).__name__}: {str(ex).splitlines()[0] if str(ex) else ''}")
    emit({"verify_status": "fail" if failures else "pass",
          "verification": {"failures": failures, "warnings": warnings, "checks": checks, "browser_checked": browser}})


if __name__ == "__main__":
    main()
