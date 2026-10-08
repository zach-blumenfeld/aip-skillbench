"""Profile the local data files a visualization will be built from.

State in:  data_paths (list of files and/or directories)
State out: data_profile — per table: row count, columns with kind/missing/distinct values,
           which numeric columns are entirely missing for a category (e.g. ETFs have no
           marketCap), and for directories of per-entity files: header variants, stems,
           date ranges, and which table column their stems match (case-insensitively).
"""
import os

from d3common import emit, find_file_for_key, is_missing, read_stdin, read_table, to_number

TABLE_EXT = {".csv", ".tsv", ".json", ".txt"}
MAX_DISTINCT = 30


def profile_table(path):
    cols, rows = read_table(path)
    out_cols = []
    for c in cols:
        vals = [r.get(c) for r in rows]
        present = [v for v in vals if not is_missing(v)]
        nums = [to_number(v) for v in present]
        numeric = present and all(n is not None for n in nums)
        info = {"name": c, "missing": len(vals) - len(present)}
        if c == "":
            info["kind"] = "index (unnamed first column; ignore)"
        elif not present:
            info["kind"] = "empty"
        elif numeric:
            ns = [n for n in nums if n is not None]
            info.update(kind="numeric", min=min(ns), max=max(ns))
        else:
            avg_len = sum(len(str(v)) for v in present) / len(present)
            distinct = sorted({str(v) for v in present})
            if avg_len > 120:
                info["kind"] = "long_text"
            elif len(distinct) <= MAX_DISTINCT and len(distinct) < len(present):
                info.update(kind="categorical", values={d: sum(1 for v in present if str(v) == d) for d in distinct})
            else:
                info["kind"] = "text"
                info["unique"] = len(distinct) == len(present)
            info["example"] = str(present[0])[:60]
        out_cols.append(info)

    # categories whose numeric columns are all missing (drives uniform sizing / tooltip exclusion)
    gaps = []
    cat_cols = [c for c in out_cols if c.get("kind") == "categorical"]
    num_cols = [c["name"] for c in out_cols if c.get("kind") == "numeric"]
    for cc in cat_cols:
        for val in cc["values"]:
            sub = [r for r in rows if str(r.get(cc["name"])) == val]
            missing_all = [n for n in num_cols if all(is_missing(r.get(n)) for r in sub)]
            text_missing = [c["name"] for c in out_cols if c.get("kind") in ("text", "long_text", "categorical")
                            and c["name"] != cc["name"] and all(is_missing(r.get(c["name"])) for r in sub)]
            if missing_all or text_missing:
                gaps.append({"column": cc["name"], "value": val, "rows": len(sub),
                             "numeric_all_missing": missing_all, "text_all_missing": text_missing})
    return {"path": path, "rows": len(rows), "columns": out_cols, "category_gaps": gaps,
            "unique_text_columns": [c["name"] for c in out_cols if c.get("unique")]}


def profile_dir(path):
    files = sorted(f for f in os.listdir(path) if os.path.splitext(f)[1].lower() in TABLE_EXT)
    headers = {}
    stems = []
    dates = []
    for f in files:
        full = os.path.join(path, f)
        cols, rows = read_table(full)
        headers.setdefault(",".join(cols), []).append(f)
        stems.append(os.path.splitext(f)[0])
        dc = next((c for c in cols if c.lower() == "date"), None)
        if dc and rows:
            dates.append((rows[0].get(dc), rows[-1].get(dc), len(rows)))
    variants = [{"header": h, "files": len(fs), "example_files": fs[:5]} for h, fs in headers.items()]
    info = {"path": path, "files": len(files), "stems": stems, "header_variants": variants}
    if dates:
        info["date_range"] = [min(d[0] for d in dates), max(d[1] for d in dates)]
        info["rows_per_file"] = [min(d[2] for d in dates), max(d[2] for d in dates)]
    return info


def main():
    state, _ = read_stdin()
    paths = state.get("data_paths") or []
    tables, dirs, problems = [], [], []
    for p in paths:
        if not os.path.isabs(p):
            problems.append(f"{p}: relative path (resolved against the skill's scripts/ folder); pass absolute paths")
        if os.path.isdir(p):
            dirs.append(profile_dir(p))
        elif os.path.isfile(p):
            try:
                tables.append(profile_table(p))
            except Exception as e:  # noqa: BLE001
                problems.append(f"{p}: {e}")
        else:
            problems.append(f"{p}: not found")
    # link directories of per-entity files to a table key column
    for d in dirs:
        for t in tables:
            for c in t["columns"]:
                if c.get("kind") not in ("text", "categorical") or c["name"] == "":
                    continue
                cols, rows = read_table(t["path"])
                keys = [str(r.get(c["name"])) for r in rows if not is_missing(r.get(c["name"]))]
                hits = [k for k in keys if find_file_for_key(d["path"], k)]
                if keys and len(hits) >= 0.8 * len(keys):
                    case_diff = sorted(k for k in hits if os.path.splitext(os.path.basename(find_file_for_key(d["path"], k)))[0] != k)
                    d["matches_table"] = {"table": t["path"], "key_column": c["name"],
                                          "matched": len(hits), "of": len(keys),
                                          "stem_case_differs_for": case_diff}
                    break
    # build_report starts empty so the spec step can take it on the first pass
    emit({"data_profile": {"tables": tables, "directories": dirs, "problems": problems},
          "build_report": {"errors": [], "note": "no build yet"}})


if __name__ == "__main__":
    main()
