#!/usr/bin/env python3
"""Ingest and standardize hierarchical product-category CSVs from multiple sources.

Reads every CSV in a data directory, locates the hierarchical `category_path`
column even when files differ in format, detects the path delimiter per file,
splits each path into level segments, standardizes the text, and emits a single
normalized JSON. Also emits a *profile* that aggregates the native top-level
categories and proposes seed groupings — the deterministic scaffolding the agent
uses to design the unified taxonomy.

Stdlib only (csv, json, re, ...). No third-party dependencies, so it runs in any
python3 environment.

Usage:
    python3 ingest.py --data-dir /root/data --out /root/output/normalized_categories.json

Output JSON shape:
{
  "sources":      {"amazon": 1234, ...},          # row count per source
  "delimiters":   {"amazon": " > ", ...},         # detected path delimiter per file
  "depth_distribution": {"amazon": {1: 10, 2: 200, ...}, ...},
  "level1_terms": {"amazon": [["electronics", 320], ...], ...},
  "suggested_l1_groups": [                         # seed clusters for unified level 1
      {"terms": ["electronics", "consumer electronics"],
       "sources": ["amazon", "google"], "total": 540}, ...],
  "rows": [ {"source", "category_path", "segments": [...], "depth": n}, ... ]
}
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict

# Candidate path delimiters, in preference order (spaced variants first so we
# keep the cleaner split when two candidates tie on segment count).
DELIMITER_CANDIDATES = [" > ", " | ", " / ", " :: ", " \\ ", ">", "|", "/", "::", ">>", "\\"]

# Filename substrings -> canonical source label required by the output spec.
SOURCE_PATTERNS = [
    ("amazon", "amazon"),
    ("facebook", "facebook"),
    ("fb", "facebook"),
    ("google", "google"),
]

# Tokens that carry no categorical meaning; dropped before similarity grouping.
STOPWORDS = {
    "and", "or", "the", "a", "an", "of", "for", "to", "in", "with", "other",
    "others", "misc", "miscellaneous", "general", "all", "more", "etc", "&",
}

CATEGORY_COLUMN_HINTS = ["category_path", "categorypath", "category path",
                          "path", "categories", "category", "taxonomy", "breadcrumb"]


def canonical_source(filename):
    low = filename.lower()
    for needle, label in SOURCE_PATTERNS:
        if needle in low:
            return label
    # Fall back to the filename stem so unknown sources still ingest.
    return re.sub(r"[^a-z0-9]+", "_", os.path.splitext(low)[0]).strip("_")


def standardize_segment(text):
    """Standardize one category segment into a clean, comparable display string.

    Lowercase-fold for normalization, replace separator punctuation with spaces,
    drop stray symbols, collapse whitespace, then Title-Case for readability.
    Returns "" for empty/whitespace input.
    """
    if text is None:
        return ""
    s = str(text).strip().strip('"').strip("'")
    s = s.replace("_", " ").replace("-", " ").replace("/", " ")
    s = s.replace("&", " and ")
    s = re.sub(r"[^0-9a-zA-Z ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    # Title-case but keep short tokens lower only when they are stopwords.
    words = []
    for w in s.split(" "):
        words.append(w.capitalize())
    return " ".join(words)


def norm_tokens(segment_display):
    """Lowercase content tokens of a standardized segment, stopwords removed."""
    toks = [t for t in segment_display.lower().split(" ") if t and t not in STOPWORDS]
    return toks


def detect_category_column(fieldnames, sample_rows):
    """Pick the column holding hierarchical paths.

    Strategy: (1) exact/normalized name hint match; (2) the column whose values
    most often contain a path delimiter.
    """
    if not fieldnames:
        return None
    norm = {fn: re.sub(r"[^a-z0-9]+", "", (fn or "").lower()) for fn in fieldnames}
    # 1. name hints, most specific first
    for hint in CATEGORY_COLUMN_HINTS:
        hkey = re.sub(r"[^a-z0-9]+", "", hint)
        for fn in fieldnames:
            if norm[fn] == hkey:
                return fn
    for hint in CATEGORY_COLUMN_HINTS:
        hkey = re.sub(r"[^a-z0-9]+", "", hint)
        for fn in fieldnames:
            if hkey and hkey in norm[fn]:
                return fn
    # 2. delimiter density
    best, best_score = None, -1
    for fn in fieldnames:
        score = 0
        for row in sample_rows:
            val = (row.get(fn) or "")
            if any(d in val for d in DELIMITER_CANDIDATES[:5]) or ">" in val or "/" in val:
                score += 1
        if score > best_score:
            best, best_score = fn, score
    return best if best_score > 0 else (fieldnames[0] if fieldnames else None)


def detect_delimiter(values):
    """Pick the delimiter that splits the most rows into >=2 segments."""
    best, best_score = " > ", -1
    for delim in DELIMITER_CANDIDATES:
        total = 0
        for v in values:
            parts = [p for p in v.split(delim) if p.strip()]
            if len(parts) >= 2:
                total += len(parts)
        if total > best_score:
            best, best_score = delim, total
    return best if best_score > 0 else " > "


def read_csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        rows = list(reader)
        return reader.fieldnames, rows


def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def group_level1_terms(level1_by_source, threshold=0.5):
    """Greedily merge native top-level terms across sources by token overlap.

    Produces seed groups for unified level 1. Each group records the member
    terms, the sources they came from, and total frequency.
    """
    items = []  # (term, source, count)
    for source, terms in level1_by_source.items():
        for term, count in terms:
            items.append((term, source, count))
    # Sort by frequency so heavy categories anchor groups.
    items.sort(key=lambda x: -x[2])
    groups = []  # each: {"tokens": set, "terms": Counter, "sources": set, "total": int}
    for term, source, count in items:
        toks = norm_tokens(term)
        placed = False
        for g in groups:
            if jaccard(toks, g["tokens"]) >= threshold or (toks and set(toks) <= g["tokens"]):
                g["tokens"] |= set(toks)
                g["terms"][term] += count
                g["sources"].add(source)
                g["total"] += count
                placed = True
                break
        if not placed:
            groups.append({
                "tokens": set(toks),
                "terms": Counter({term: count}),
                "sources": {source},
                "total": count,
            })
    out = []
    for g in sorted(groups, key=lambda g: -g["total"]):
        out.append({
            "terms": [t for t, _ in g["terms"].most_common()],
            "sources": sorted(g["sources"]),
            "total": g["total"],
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Ingest + standardize multi-source category CSVs.")
    ap.add_argument("--data-dir", default="/root/data", help="directory of input CSVs")
    ap.add_argument("--out", default="/root/output/normalized_categories.json",
                    help="path to write normalized JSON")
    args = ap.parse_args()

    if not os.path.isdir(args.data_dir):
        print(f"ERROR: data dir not found: {args.data_dir}", file=sys.stderr)
        return 1
    csv_files = sorted(f for f in os.listdir(args.data_dir) if f.lower().endswith(".csv"))
    if not csv_files:
        print(f"ERROR: no CSV files in {args.data_dir}", file=sys.stderr)
        return 1

    sources = {}
    delimiters = {}
    depth_dist = {}
    level1_terms = {}
    rows_out = []
    seen = set()  # (source, original_path) dedupe

    for fname in csv_files:
        fpath = os.path.join(args.data_dir, fname)
        source = canonical_source(fname)
        try:
            fieldnames, raw_rows = read_csv_rows(fpath)
        except Exception as exc:  # noqa: BLE001 - report and skip unreadable files
            print(f"WARNING: could not read {fname}: {exc}", file=sys.stderr)
            continue
        cat_col = detect_category_column(fieldnames, raw_rows[:200])
        if cat_col is None:
            print(f"WARNING: no category column found in {fname}", file=sys.stderr)
            continue
        raw_values = [(r.get(cat_col) or "").strip() for r in raw_rows]
        raw_values = [v for v in raw_values if v]
        delim = detect_delimiter(raw_values[:500] or raw_values)
        delimiters[source] = delim

        count = 0
        l1_counter = Counter()
        dhist = Counter()
        for v in raw_values:
            segs = [standardize_segment(p) for p in v.split(delim)]
            segs = [s for s in segs if s]
            if not segs:
                continue
            key = (source, v)
            if key in seen:
                continue
            seen.add(key)
            rows_out.append({
                "source": source,
                "category_path": v,
                "segments": segs,
                "depth": len(segs),
            })
            l1_counter[segs[0].lower()] += 1
            dhist[len(segs)] += 1
            count += 1
        sources[source] = sources.get(source, 0) + count
        depth_dist[source] = {str(k): v for k, v in sorted(dhist.items())}
        # merge l1 counters if same source spans multiple files
        prev = dict(level1_terms.get(source, []))
        merged = Counter(prev)
        merged.update(l1_counter)
        level1_terms[source] = merged.most_common()

    suggested = group_level1_terms(level1_terms)

    out = {
        "sources": sources,
        "delimiters": delimiters,
        "depth_distribution": depth_dist,
        "level1_terms": level1_terms,
        "suggested_l1_groups": suggested,
        "rows": rows_out,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    total = sum(sources.values())
    print(f"OK: {total} unique category paths from {len(sources)} source(s) "
          f"-> {args.out}; suggested {len(suggested)} level-1 seed groups; "
          f"delimiters={delimiters}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
