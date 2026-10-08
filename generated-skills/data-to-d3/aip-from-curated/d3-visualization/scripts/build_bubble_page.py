"""Generate a deterministic, offline D3 page: clustered bubble chart + linked sortable table.

State in:  viz_spec (object, see assets/bubble-spec.md), data_profile (from profile-data)
Assets:    page-template (html), viz-template (js), style-template (css)
State out: build_status "ok" | "error", build_report {errors, warnings, defaults_applied,
           written}, page_manifest (paths + expectations for verify-page).
"""
import copy
import json
import os
import shutil

from d3common import (emit, find_column, find_file_for_key, is_missing, read_stdin, read_table,
                      resolve, to_number, vendor_d3, write_text)

DEFAULTS = {
    "title": None,
    "subtitle": "",
    "layout": "side-by-side",
    "output": {"html": "index.html", "js": "js/visualization.js", "css": "css/style.css",
               "d3": None, "d3_version": "6", "data_dir": "data", "copy_data": [],
               "svg": None, "png": None},
    "bubble": {"width": 800, "height": 600, "margin": {"top": 20, "right": 20, "bottom": 20, "left": 20},
               "radius_range": [5, 50], "missing_radius": 10, "padding": 2, "charge": -30,
               "cluster_strength": 0.5, "cluster_ring": 150, "ticks": 300, "relax_ticks": 120,
               "max_density": 0.55, "legend": True},
    "table": {"missing_text": "-", "sortable": True, "sort_by": None, "sort_ascending": True},
    "tooltip": {"exclude": []},
    "link": True,
    "series": None,
}


def merge_defaults(spec, defaults, path, applied):
    out = copy.deepcopy(spec) if isinstance(spec, dict) else {}
    for k, v in defaults.items():
        if k not in out or out[k] is None and v is not None:
            out[k] = copy.deepcopy(v)
            if v not in (None, [], ""):
                applied.append(f"{path}{k} = {json.dumps(v)}")
        elif isinstance(v, dict) and isinstance(out.get(k), dict) and k != "margin":
            out[k] = merge_defaults(out[k], v, f"{path}{k}.", applied)
    return out


def main():
    state, assets = read_stdin()
    raw = state.get("viz_spec") or {}
    errors, warnings, applied = [], [], []
    spec = merge_defaults(raw, DEFAULTS, "", applied)
    out = spec["output"]
    B, T = spec["bubble"], spec["table"]

    if not out.get("dir"):
        errors.append("output.dir is required (the folder the task wants the web app in)")
    data_spec = spec.get("data") or {}
    data_file = data_spec.get("file")
    if not data_file or not os.path.isfile(data_file):
        errors.append(f"data.file not found: {data_file!r}")
    if errors:
        return finish(errors, warnings, applied, None, [])

    cols, rows = read_table(data_file)

    def col(name, what, required=True):
        if not name:
            if required:
                errors.append(f"{what} is required; available columns: {[c for c in cols if c]}")
            return None
        c = find_column(cols, name)
        if c is None:
            errors.append(f"{what} column {name!r} not in {os.path.basename(data_file)}; available: {[c for c in cols if c]}")
        return c

    key = col(data_spec.get("key"), "data.key")
    size_f = col(B.get("size_field"), "bubble.size_field")
    color_f = col(B.get("color_field"), "bubble.color_field")
    cluster_f = col(B.get("cluster_field") or B.get("color_field"), "bubble.cluster_field")
    label_f = col(B.get("label_field") or data_spec.get("key"), "bubble.label_field", required=False)
    tt_fields = spec["tooltip"].get("fields") or []
    if not tt_fields:
        errors.append("tooltip.fields is required (list of {field, label?, format?, bold?})")
    for f in tt_fields:
        f["field"] = col(f.get("field"), "tooltip.fields[].field")
    for r in spec["tooltip"].get("exclude") or []:
        r["field"] = col(r.get("field"), "tooltip.exclude[].field")
    t_cols = T.get("columns") or []
    if not t_cols:
        errors.append("table.columns is required (list of {field, label, format?})")
    for c in t_cols:
        c["field"] = col(c.get("field"), "table.columns[].field")
        c.setdefault("label", c["field"])
    if T.get("sort_by"):
        T["sort_by"] = col(T["sort_by"], "table.sort_by")
    if errors:
        return finish(errors, warnings, applied, None, [])

    # key must be unique
    keys = [str(r.get(key)) for r in rows]
    dups = sorted({k for k in keys if keys.count(k) > 1})
    if dups:
        errors.append(f"data.key {key!r} is not unique: duplicates {dups[:10]}")
    sizes = [to_number(r.get(size_f)) for r in rows if not is_missing(r.get(size_f))]
    if any(s is None for s in sizes):
        errors.append(f"bubble.size_field {size_f!r} has non-numeric values")
    if not sizes:
        errors.append(f"bubble.size_field {size_f!r} has no values at all")
    rr = B.get("radius_range")
    if not (isinstance(rr, list) and len(rr) == 2 and 0 <= rr[0] < rr[1]):
        errors.append("bubble.radius_range must be [min, max] with 0 <= min < max")
    if errors:
        return finish(errors, warnings, applied, None, [])

    # which fields to embed, and which of them are numeric
    fields = []
    for f in [key, size_f, color_f, cluster_f, label_f] + [f["field"] for f in tt_fields] + \
             [c["field"] for c in t_cols] + [r["field"] for r in spec["tooltip"].get("exclude") or []]:
        if f and f not in fields:
            fields.append(f)
    numeric = [f for f in fields if all(to_number(r.get(f)) is not None for r in rows if not is_missing(r.get(f)))
               and any(not is_missing(r.get(f)) for r in rows) and f not in (key, color_f, cluster_f, label_f)]
    embedded = []
    for r in rows:
        e = {}
        for f in fields:
            v = r.get(f)
            if f in numeric:
                e[f] = to_number(v)
            else:
                e[f] = None if is_missing(v) else str(v)
        embedded.append(e)
    n_missing = sum(1 for r in rows if is_missing(r.get(size_f)))
    if n_missing:
        warnings.append(f"{n_missing} rows have no {size_f}; they get uniform radius {B['missing_radius']}")
    for c in t_cols:
        if c["field"] in numeric and not c.get("format"):
            c["format"] = "abbrev" if max(abs(to_number(r.get(c['field'])) or 0) for r in rows) >= 1e6 else "number"
            applied.append(f"table column {c['field']!r} format = {c['format']!r}")

    # paths
    base = out["dir"]
    html = resolve(base, out["html"])
    js = resolve(base, out["js"])
    css = resolve(base, out["css"])
    major = str(out.get("d3_version") or "6").lstrip("v").split(".")[0]
    d3_path = resolve(base, out.get("d3") or f"js/d3.v{major}.min.js")
    data_dir = resolve(base, out.get("data_dir") or "data")
    written = []

    try:
        d3_file, d3_ver, d3_src = vendor_d3(out.get("d3_version") or "6", d3_path)
    except Exception as e:  # noqa: BLE001
        errors.append(str(e))
        return finish(errors, warnings, applied, None, written)
    written.append(d3_file)

    copied_main = None
    for src in out.get("copy_data") or []:
        if not os.path.exists(src):
            warnings.append(f"copy_data source missing: {src}")
            continue
        dest = os.path.join(data_dir, os.path.basename(os.path.normpath(src)))
        if os.path.abspath(src) == os.path.abspath(dest):
            continue
        if os.path.isdir(src):
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            os.makedirs(data_dir, exist_ok=True)
            shutil.copyfile(src, dest)
        written.append(dest)
        if os.path.abspath(src) == os.path.abspath(data_file):
            copied_main = dest
    html_dir = os.path.dirname(html)
    rel = lambda p: os.path.relpath(p, html_dir).replace(os.sep, "/")
    data_url = rel(copied_main) if copied_main else rel(data_file)

    # optional per-key time series (e.g. price history per ticker), downsampled
    series_cfg, series_data = None, None
    S = spec.get("series")
    if S:
        sdir = S.get("dir")
        if not sdir or not os.path.isdir(sdir):
            errors.append(f"series.dir not found: {sdir!r}")
            return finish(errors, warnings, applied, None, written)
        series_data, missing_keys, fallbacks, used = {}, [], set(), {}
        want = S.get("value_column") or "Close"
        step = {"daily": 1, "weekly": 5, "monthly": 21}.get(S.get("resample") or "weekly", 5)
        for k in keys:
            fp = find_file_for_key(sdir, k)
            if not fp:
                missing_keys.append(k)
                continue
            scols, srows = read_table(fp)
            dc = find_column(scols, S.get("date_column") or "Date")
            vc = find_column(scols, want) or find_column(scols, "Close")
            if vc != find_column(scols, want):
                fallbacks.add(os.path.basename(fp))
                used[k] = vc
            if not dc or not vc:
                missing_keys.append(k)
                continue
            pts = [[str(r[dc])[:10], to_number(r[vc])] for r in srows if to_number(r.get(vc)) is not None]
            pts.sort(key=lambda p: p[0])
            if step > 1 and pts:
                pts = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
            series_data[k] = [[d, round(v, 4)] for d, v in pts]
        if missing_keys:
            warnings.append(f"no series file/columns for keys: {missing_keys}")
        if fallbacks:
            warnings.append(f"{want!r} missing in {sorted(fallbacks)[:8]}...; used 'Close' there")
        series_cfg = {"value_column": want, "width": S.get("width") or B["width"],
                      "height": S.get("height") or 260, "columns_used": used,
                      "placeholder": S.get("placeholder") or "Click a bubble or table row to see its history."}

    key_attr = "".join(ch if ch.isalnum() else "-" for ch in key.lower()).strip("-") or "key"
    config = {
        "key": key, "key_attr": key_attr, "data_url": data_url, "numeric_fields": numeric,
        "bubble": {**{k: B[k] for k in ("width", "height", "margin", "radius_range", "missing_radius", "padding",
                                          "charge", "cluster_strength", "cluster_ring", "ticks", "relax_ticks",
                                          "max_density", "legend")},
                   "size_field": size_f, "color_field": color_f, "cluster_field": cluster_f, "label_field": label_f},
        "tooltip": {"fields": tt_fields, "exclude": spec["tooltip"].get("exclude") or []},
        "table": {"columns": t_cols, "missing_text": T["missing_text"], "sortable": T["sortable"],
                  "sort_by": T.get("sort_by"), "sort_ascending": T.get("sort_ascending", True)},
        "link": bool(spec.get("link")),
        "series": series_cfg,
    }
    header = ("Generated by the d3-visualization skill (deterministic: fixed size/viewBox, sorted domains, "
              f"no randomness, fixed {B['ticks']}+{B['relax_ticks']} force ticks, no transitions; D3 {d3_ver} vendored "
              f"locally, no CDN). Data: {os.path.basename(data_file)} (embedded copy; fallback d3.csv('{data_url}')). "
              "Defaults applied: " + ("; ".join(applied) if applied else "none"))
    header = header.replace("*/", "* /")
    js_text = (assets["viz-template"]
               .replace("__HEADER_COMMENT__", header)
               .replace("__CONFIG__", json.dumps(config, indent=2, ensure_ascii=False))
               .replace("__ROWS__", json.dumps(embedded, ensure_ascii=False, separators=(",", ":")).replace("},{", "},\n    {"))
               .replace("__SERIES__", json.dumps(series_data, separators=(",", ":")) if series_data else "null"))
    title = spec.get("title") or f"{os.path.splitext(os.path.basename(data_file))[0]}: {size_f} by {color_f}"
    subtitle = spec.get("subtitle") or (f"Bubble size = {size_f}; color = {color_f}. Hover for details, click a bubble or row to link them.")
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html_text = (assets["page-template"]
                 .replace("__HEADER_COMMENT__", "Generated by the d3-visualization skill; open directly or serve this folder.")
                 .replace("__TITLE__", esc(title)).replace("__SUBTITLE__", esc(subtitle))
                 .replace("__CSS_HREF__", rel(css)).replace("__D3_SRC__", rel(d3_file)).replace("__JS_SRC__", rel(js))
                 .replace("__SERIES_DIV__", '\n            <div id="series-chart"></div>' if series_cfg else ""))
    css_text = (assets["style-template"].replace("__HEADER_COMMENT__", "Generated by the d3-visualization skill")
                .replace("__FLEX_DIRECTION__", "column" if spec.get("layout") == "stacked" else "row")
                .replace("__TABLE_MAX_HEIGHT__", str(int(B["height"] + (series_cfg["height"] + 12 if series_cfg else 0)))))
    for p, t in ((html, html_text), (js, js_text), (css, css_text)):
        write_text(p, t)
        written.append(p)

    excl = [e[key] for e in embedded if any(
        (r.get("missing") and e.get(r["field"]) is None) or
        ("equals" in r and str(e.get(r["field"])) == str(r["equals"])) or
        ("in" in r and str(e.get(r["field"])) in [str(x) for x in r["in"]])
        for r in config["tooltip"]["exclude"])]
    incl = [e[key] for e in embedded if e[key] not in excl]
    manifest = {
        "html_path": html, "js_paths": [d3_file, js], "css_paths": [css], "d3_path": d3_file,
        "d3_version": d3_ver, "svg_path": resolve(base, out.get("svg")), "png_path": resolve(base, out.get("png")),
        "expect": {
            "svg_selector": "#bubble-chart", "mark_selector": "#bubble-chart circle.bubble",
            "mark_count": len(embedded), "key_attr": "data-key",
            "tooltip_selector": "#tooltip", "tooltip_included_keys": incl[:3] + incl[-2:],
            "tooltip_excluded_keys": excl[:3],
            "table_row_selector": "#data-table tbody tr", "table_row_count": len(embedded),
            "linked": config["link"], "no_overlap": True, "within_bounds": True,
            "label_selector": "#bubble-chart text.bubble-label" if label_f else None,
        },
    }
    warnings.append(f"d3 {d3_ver} from {d3_src}")
    return finish(errors, warnings, applied, manifest, written)


def finish(errors, warnings, applied, manifest, written):
    emit({"build_status": "error" if errors else "ok",
          "build_report": {"errors": errors, "warnings": warnings, "defaults_applied": applied, "written": written},
          "page_manifest": manifest or {}})


if __name__ == "__main__":
    main()
