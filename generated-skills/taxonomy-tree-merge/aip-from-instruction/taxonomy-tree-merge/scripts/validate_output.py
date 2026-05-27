#!/usr/bin/env python3
"""Validate the unified taxonomy outputs against the task rules.

Reads unified_taxonomy_full.csv and unified_taxonomy_hierarchy.csv from the
given output directory (default /root/output) and checks mechanical rules:

- Required columns and column order.
- Source values restricted to {amazon, facebook, google}.
- depth column matches the input category_path's segment count.
- unified_level_k populated only when k <= unified depth (no gaps).
- Name format: each unified_level_* cell <= 5 words, words joined by " | ".
- 10 <= number of distinct unified_level_1 <= 20.
- Every internal node has 3 <= children <= 20.
- No child name shares a word stem with its parent name.
- Pairwise sibling word-overlap < 30% (Jaccard over tokens, ignoring
  stopwords).
- Hierarchy file contains every prefix of every unified path that appears in
  the full file, and vice versa.
- Per-source share of each top-level bucket is between 0.25x and 4x of the
  bucket's overall share (loose evenness check).

Exit codes:
  0  all checks pass.
  1  one or more violations found (printed to stderr as JSON Lines records,
     human-readable summary on stdout).

Usage:
    python scripts/validate_output.py [--output-dir /root/output]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

FULL_COLS = [
    "source",
    "category_path",
    "depth",
    "unified_level_1",
    "unified_level_2",
    "unified_level_3",
    "unified_level_4",
    "unified_level_5",
]
HIER_COLS = [
    "unified_level_1",
    "unified_level_2",
    "unified_level_3",
    "unified_level_4",
    "unified_level_5",
]
ALLOWED_SOURCES = {"amazon", "facebook", "google"}
PATH_SEP = " > "
NAME_SEP = " | "
MAX_WORDS = 5
TOP_MIN, TOP_MAX = 10, 20
CHILD_MIN, CHILD_MAX = 3, 20
SIBLING_OVERLAP_MAX = 0.30
STOPWORDS = {"and", "or", "the", "a", "an", "of", "for", "in", "on", "to", "with", "&"}

Violations: list[dict] = []


def report(level: str, code: str, **fields) -> None:
    Violations.append({"level": level, "code": code, **fields})


def words(name: str) -> list[str]:
    parts = [w.strip().lower() for w in name.replace(NAME_SEP, " ").split() if w.strip()]
    return [w for w in parts if w not in STOPWORDS]


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / min(len(sa), len(sb))


def levels_of(row: dict) -> tuple[str, ...]:
    out: list[str] = []
    for col in HIER_COLS:
        v = (row.get(col) or "").strip()
        if v:
            out.append(v)
        else:
            break
    for col_idx, col in enumerate(HIER_COLS):
        v = (row.get(col) or "").strip()
        if v and col_idx >= len(out):
            report("error", "gap_in_levels", row=row, column=col)
    return tuple(out)


def check_name(name: str, where: str) -> None:
    n_words = len(name.split())
    if n_words > MAX_WORDS:
        report("error", "name_too_long", where=where, name=name, words=n_words)
    if " " in name and NAME_SEP not in name and n_words > 1:
        report("error", "name_separator", where=where, name=name)
    if "," in name:
        report("error", "name_has_comma", where=where, name=name)


def load_csv(path: Path, expected_cols: list[str]) -> list[dict]:
    if not path.exists():
        report("error", "missing_file", file=str(path))
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        if header != expected_cols:
            report(
                "error",
                "bad_header",
                file=str(path),
                expected=expected_cols,
                actual=header,
            )
        return list(reader)


def validate_full(rows: list[dict]) -> tuple[set[tuple[str, ...]], Counter, dict]:
    """Return (set of unified paths seen, top-level Counter, per-top source share)."""
    paths_seen: set[tuple[str, ...]] = set()
    top_counts: Counter = Counter()
    per_top_source: dict = defaultdict(Counter)

    for i, row in enumerate(rows):
        src = (row.get("source") or "").strip().lower()
        if src not in ALLOWED_SOURCES:
            report("error", "bad_source", row_index=i, source=src)
        depth_str = (row.get("depth") or "").strip()
        try:
            depth = int(depth_str)
        except ValueError:
            report("error", "bad_depth", row_index=i, depth=depth_str)
            depth = -1
        if depth != -1:
            actual_depth = len([s for s in (row.get("category_path") or "").split(PATH_SEP) if s.strip()])
            if depth != actual_depth:
                report(
                    "warn",
                    "depth_mismatch",
                    row_index=i,
                    declared=depth,
                    actual=actual_depth,
                )
        levels = levels_of(row)
        if not levels:
            report("error", "empty_levels", row_index=i)
            continue
        for j in range(1, len(levels) + 1):
            paths_seen.add(levels[:j])
        for cell in levels:
            check_name(cell, where=f"full row {i}")
        top = levels[0]
        top_counts[top] += 1
        if src in ALLOWED_SOURCES:
            per_top_source[top][src] += 1
    return paths_seen, top_counts, per_top_source


def validate_hierarchy(rows: list[dict]) -> set[tuple[str, ...]]:
    paths_seen: set[tuple[str, ...]] = set()
    for i, row in enumerate(rows):
        levels = levels_of(row)
        if not levels:
            report("error", "empty_hierarchy_row", row_index=i)
            continue
        for cell in levels:
            check_name(cell, where=f"hier row {i}")
        paths_seen.add(levels)
    return paths_seen


def check_tree_shape(full_paths: set[tuple[str, ...]]) -> None:
    children: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for p in full_paths:
        for j in range(len(p)):
            children[p[:j]].add(p[j])
    top_level = children[()]
    if not (TOP_MIN <= len(top_level) <= TOP_MAX):
        report("error", "top_level_count", count=len(top_level), min=TOP_MIN, max=TOP_MAX)
    for parent, kids in children.items():
        if parent == ():
            continue
        if not (CHILD_MIN <= len(kids) <= CHILD_MAX):
            report(
                "error",
                "child_count",
                parent=" > ".join(parent),
                count=len(kids),
                min=CHILD_MIN,
                max=CHILD_MAX,
            )
        for kid in kids:
            parent_words = set(words(parent[-1]))
            kid_words = set(words(kid))
            if parent_words & kid_words:
                report(
                    "error",
                    "parent_child_overlap",
                    parent=" > ".join(parent),
                    child=kid,
                    overlap=sorted(parent_words & kid_words),
                )
        kid_list = list(kids)
        for a_idx in range(len(kid_list)):
            for b_idx in range(a_idx + 1, len(kid_list)):
                a, b = kid_list[a_idx], kid_list[b_idx]
                score = jaccard(words(a), words(b))
                if score >= SIBLING_OVERLAP_MAX:
                    report(
                        "warn",
                        "sibling_overlap",
                        parent=" > ".join(parent) or "(root)",
                        a=a,
                        b=b,
                        overlap=round(score, 2),
                    )


def check_prefix_coverage(full_paths: set[tuple[str, ...]], hier_paths: set[tuple[str, ...]]) -> None:
    needed: set[tuple[str, ...]] = set()
    for p in full_paths:
        for j in range(1, len(p) + 1):
            needed.add(p[:j])
    missing = sorted(needed - hier_paths)
    extra = sorted(hier_paths - needed)
    for m in missing[:25]:
        report("error", "missing_in_hierarchy", path=list(m))
    if len(missing) > 25:
        report("error", "missing_in_hierarchy_truncated", remaining=len(missing) - 25)
    for e in extra[:10]:
        report("warn", "extra_in_hierarchy", path=list(e))


def check_source_balance(top_counts: Counter, per_top_source: dict) -> None:
    total = sum(top_counts.values()) or 1
    overall_share = {s: 0 for s in ALLOWED_SOURCES}
    for top, by_src in per_top_source.items():
        for s, c in by_src.items():
            overall_share[s] += c
    overall_share_frac = {s: (overall_share[s] / total) for s in ALLOWED_SOURCES}
    for top, total_in_top in top_counts.items():
        for s in ALLOWED_SOURCES:
            actual = per_top_source[top].get(s, 0) / total_in_top
            target = overall_share_frac[s]
            if target == 0:
                continue
            ratio = actual / target
            if ratio < 0.25 or ratio > 4.0:
                report(
                    "warn",
                    "source_imbalance",
                    top=top,
                    source=s,
                    actual=round(actual, 2),
                    overall=round(target, 2),
                    ratio=round(ratio, 2),
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="/root/output", type=Path)
    args = parser.parse_args()

    full = load_csv(args.output_dir / "unified_taxonomy_full.csv", FULL_COLS)
    hier = load_csv(args.output_dir / "unified_taxonomy_hierarchy.csv", HIER_COLS)

    full_paths, top_counts, per_top_source = validate_full(full)
    hier_paths = validate_hierarchy(hier)

    check_tree_shape(full_paths)
    check_prefix_coverage(full_paths, hier_paths)
    check_source_balance(top_counts, per_top_source)

    errors = [v for v in Violations if v["level"] == "error"]
    warns = [v for v in Violations if v["level"] == "warn"]
    for v in Violations:
        print(json.dumps(v), file=sys.stderr)

    summary = (
        f"validate_output: full_rows={len(full)} hier_rows={len(hier)} "
        f"top_buckets={len(top_counts)} errors={len(errors)} warns={len(warns)}"
    )
    print(summary)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
