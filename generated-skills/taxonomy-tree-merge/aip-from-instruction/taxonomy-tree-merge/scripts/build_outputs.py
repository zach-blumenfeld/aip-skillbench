#!/usr/bin/env python3
"""Build the two required output CSVs from the agent's taxonomy assignment.

Input: assignments.json — a list of objects, one per source category path:
    {
      "source": "amazon",                       # amazon | facebook | google
      "category_path": "Electronics > Computers > Laptops",   # original source path
      "unified_level_1": "Electronics",
      "unified_level_2": "Computers",
      "unified_level_3": "Laptops",
      "unified_level_4": "",
      "unified_level_5": ""
    }

Outputs (deterministic formatting — do not hand-write these CSVs):
  * unified_taxonomy_full.csv
        source, category_path, depth, unified_level_1..5
  * unified_taxonomy_hierarchy.csv
        unified_level_1..5   (every distinct node path, low granularity -> high)

`depth` semantics are controlled by --depth-mode:
  * source  (default) -> number of levels in the ORIGINAL category_path, capped at 5
  * unified            -> number of populated unified_level_* cells

Fails (exit 1) if a unified path has a gap (e.g. level_3 set while level_2 is
blank) — a tree path must be contiguous. Fix the assignment and rebuild.

Stdlib only.
"""

import argparse
import csv
import json
import os
import sys

LEVEL_COLS = [f"unified_level_{i}" for i in range(1, 6)]


def load_assignments(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "assignments" in data:
        data = data["assignments"]
    if not isinstance(data, list):
        raise ValueError("assignments.json must be a JSON list (or {\"assignments\": [...]})")
    return data


def unified_path(row):
    """Return the contiguous list of non-empty unified level names, or raise on a gap."""
    cells = [(row.get(c) or "").strip() for c in LEVEL_COLS]
    path = []
    ended = False
    for i, c in enumerate(cells):
        if c:
            if ended:
                raise ValueError(
                    f"gap in unified path for source={row.get('source')!r} "
                    f"category_path={row.get('category_path')!r}: "
                    f"{cells} (a level is blank before a later level is filled)"
                )
            path.append(c)
        else:
            ended = True
    return path


def source_depth(category_path):
    # Count segments using the most common delimiters; cap at 5.
    for delim in [" > ", " | ", " / ", ">", "|", "/"]:
        parts = [p for p in str(category_path).split(delim) if p.strip()]
        if len(parts) >= 2:
            return min(len(parts), 5)
    return 1


def main():
    ap = argparse.ArgumentParser(description="Build unified taxonomy output CSVs.")
    ap.add_argument("--assignments", default="/root/output/assignments.json")
    ap.add_argument("--out-dir", default="/root/output")
    ap.add_argument("--depth-mode", choices=["source", "unified"], default="source",
                    help="how to compute the `depth` column (default: source path depth)")
    args = ap.parse_args()

    try:
        rows = load_assignments(args.assignments)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    os.makedirs(args.out_dir, exist_ok=True)
    full_path = os.path.join(args.out_dir, "unified_taxonomy_full.csv")
    hier_path = os.path.join(args.out_dir, "unified_taxonomy_hierarchy.csv")

    node_paths = set()  # every distinct prefix path -> hierarchy rows
    errors = []
    full_rows = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row {idx} is not an object")
            continue
        src = (row.get("source") or "").strip()
        cat = (row.get("category_path") or "").strip()
        try:
            upath = unified_path(row)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not upath:
            errors.append(f"row {idx} (source={src!r}, path={cat!r}) has no unified levels")
            continue
        depth = len(upath) if args.depth_mode == "unified" else source_depth(cat)
        levels = upath + [""] * (5 - len(upath))
        full_rows.append([src, cat, depth] + levels)
        for k in range(1, len(upath) + 1):
            prefix = tuple(upath[:k])
            node_paths.add(prefix)

    if errors:
        for e in errors[:50]:
            print(f"ERROR: {e}", file=sys.stderr)
        print(f"ERROR: {len(errors)} assignment problem(s); no output written.", file=sys.stderr)
        return 1

    with open(full_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "category_path", "depth"] + LEVEL_COLS)
        w.writerows(full_rows)

    # Hierarchy: low granularity (depth 1) first, then lexicographic.
    ordered = sorted(node_paths, key=lambda p: (len(p), [s.lower() for s in p]))
    with open(hier_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(LEVEL_COLS)
        for p in ordered:
            w.writerow(list(p) + [""] * (5 - len(p)))

    print(f"OK: wrote {len(full_rows)} rows -> {full_path}; "
          f"{len(ordered)} distinct nodes -> {hier_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
