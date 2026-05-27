#!/usr/bin/env python3
"""Summarize the three source taxonomy CSVs.

Reads amazon_product_categories.csv, fb_product_categories.csv, and
google_shopping_product_categories.csv from the given directory (default
/root/data) and reports:

- Column names of each file (formats can differ).
- Row counts and unique-path counts per source.
- Depth distribution (segments per category_path, split on " > ").
- Per-source top-of-path frequency table (so the agent can eyeball the
  natural top-level categories before clustering).
- A sample of paths at each depth.

Run this once at the start of the procedure. Use the output to decide:
- Which input columns to read (`category_path` is the canonical name but
  some files may need a rename).
- How to seed the unified level-1 buckets.
- Where rare/long-tail paths sit so they can be merged into siblings.

Usage:
    python scripts/inspect_inputs.py [--data-dir /root/data]
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

SOURCES = {
    "amazon": "amazon_product_categories.csv",
    "facebook": "fb_product_categories.csv",
    "google": "google_shopping_product_categories.csv",
}

PATH_SEP = " > "


def find_path_column(header: list[str]) -> str | None:
    for col in header:
        if col.strip().lower() == "category_path":
            return col
    for col in header:
        if "path" in col.lower() or "category" in col.lower():
            return col
    return None


def load_paths(csv_path: Path) -> tuple[list[str], str | None]:
    if not csv_path.exists():
        return [], None
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        col = find_path_column(header)
        paths: list[str] = []
        if col is None:
            return [], None
        for row in reader:
            value = (row.get(col) or "").strip()
            if value:
                paths.append(value)
    return paths, col


def depth_of(path: str) -> int:
    return len([seg for seg in path.split(PATH_SEP) if seg.strip()])


def summarize(source: str, csv_path: Path) -> None:
    paths, col = load_paths(csv_path)
    print(f"\n=== {source} ({csv_path.name}) ===")
    if col is None:
        print(f"  MISSING or unreadable; expected file at {csv_path}")
        return
    print(f"  path column: {col!r}")
    print(f"  rows with non-empty path: {len(paths)}")
    print(f"  unique paths: {len(set(paths))}")

    depths = Counter(depth_of(p) for p in paths)
    print("  depth distribution:")
    for d in sorted(depths):
        print(f"    depth {d}: {depths[d]} rows")

    top = Counter(p.split(PATH_SEP)[0].strip() for p in paths)
    print(f"  top-of-path frequency (first 15 of {len(top)}):")
    for label, count in top.most_common(15):
        print(f"    {count:6d}  {label}")

    print("  sample path at each depth:")
    seen: set[int] = set()
    for p in paths:
        d = depth_of(p)
        if d not in seen:
            seen.add(d)
            print(f"    d={d}: {p}")
        if len(seen) >= 5:
            break


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="/root/data", type=Path)
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    if not data_dir.exists():
        print(f"data dir not found: {data_dir}", file=sys.stderr)
        return 1

    for source, filename in SOURCES.items():
        summarize(source, data_dir / filename)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
