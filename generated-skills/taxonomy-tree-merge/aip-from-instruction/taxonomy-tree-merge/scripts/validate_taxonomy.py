#!/usr/bin/env python3
"""Validate the unified taxonomy output against every rule in the task.

Reads the two deliverable CSVs and checks them against the constraints. Hard
checks fail the build (exit 1); soft checks emit warnings + scores for the agent
to weigh with its own judgment (they never fail the build on their own).

HARD (rule -> check):
  schema      - both CSVs carry the required columns
  source      - source in {amazon, facebook, google}
  depth       - depth is an integer 1..5
  contiguous  - unified levels form a gapless prefix (a tree path)
  rule 1      - 10..20 level-1 categories; 3..20 children per non-leaf parent
  rule 2      - each category name is <=5 words joined by " | "
  rule 4      - a child name shares no word with its parent name
  rule 5      - sibling names overlap < 30% (Jaccard on " | " words)
  coverage    - every source path appears exactly once (needs --normalized)
  hierarchy   - hierarchy.csv == the set of distinct node paths from full.csv

SOFT (advisory warnings + scores in the report):
  rule 2 (representativeness) - >=70% of a node's members share a theme token
  rule 6 (pyramid balance)    - children-per-parent spread per level
  rule 7 (source evenness)    - each source spread across the tree

Run after every rebuild; fix assignments and rebuild until 0 errors.
Stdlib only.

Usage:
    python3 validate_taxonomy.py \
        --full /root/output/unified_taxonomy_full.csv \
        --hierarchy /root/output/unified_taxonomy_hierarchy.csv \
        --normalized /root/output/normalized_categories.json \
        --report /root/output/validation_report.json
"""

import argparse
import csv
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from itertools import combinations

LEVEL_COLS = [f"unified_level_{i}" for i in range(1, 6)]
VALID_SOURCES = {"amazon", "facebook", "google"}

# Structural thresholds (rule 1).
L1_MIN, L1_MAX = 10, 20
CHILD_MIN, CHILD_MAX = 3, 20
# Naming / overlap thresholds.
MAX_NAME_WORDS = 5            # rule 2
SIBLING_MAX_OVERLAP = 0.30    # rule 5
# Soft thresholds.
REPRESENTATIVE_MIN = 0.70     # rule 2 (representativeness proxy)
MIN_MEMBERS_FOR_REP = 3       # skip representativeness on tiny nodes
BALANCE_CV_WARN = 1.0         # rule 6
MAX_OFFENDERS = 50            # cap lists in the report

STOPWORDS = {
    "and", "or", "the", "a", "an", "of", "for", "to", "in", "with", "other",
    "others", "misc", "miscellaneous", "general", "all", "more", "etc",
}
PATH_DELIMS = [" > ", " | ", " / ", " :: ", ">", "|", "/", "::", "\\"]


def words_of(name):
    """All words of a category name, lowercased — split on ' | ' and whitespace.

    Robust to names that used spaces instead of the required ' | ' separator, so
    word-count and overlap checks reflect real word content either way.
    """
    return [w for w in re.split(r"\s*\|\s*|\s+", str(name).strip().lower()) if w]


def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def content_tokens(path_str):
    s = str(path_str).lower()
    for d in PATH_DELIMS:
        s = s.replace(d, " ")
    toks = re.split(r"[^0-9a-z]+", s)
    return [t for t in toks if t and t not in STOPWORDS]


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames or [], list(reader)


def row_path(row):
    """Contiguous list of non-empty unified levels; (path, gap_flag)."""
    cells = [(row.get(c) or "").strip() for c in LEVEL_COLS]
    path, ended, gap = [], False, False
    for c in cells:
        if c:
            if ended:
                gap = True
            path.append(c)
        else:
            ended = True
    return path, gap


def main():
    ap = argparse.ArgumentParser(description="Validate the unified taxonomy outputs.")
    ap.add_argument("--full", default="/root/output/unified_taxonomy_full.csv")
    ap.add_argument("--hierarchy", default="/root/output/unified_taxonomy_hierarchy.csv")
    ap.add_argument("--normalized", default=None,
                    help="optional normalized_categories.json for coverage checks")
    ap.add_argument("--report", default="/root/output/validation_report.json")
    args = ap.parse_args()

    errors, warnings = [], []
    report = {"checks": {}}

    def err(check, msg, offenders=None):
        errors.append(f"[{check}] {msg}")
        c = report["checks"].setdefault(check, {"status": "fail", "messages": []})
        c["status"] = "fail"
        c["messages"].append(msg)
        if offenders is not None:
            c.setdefault("offenders", [])
            c["offenders"].extend(offenders[:MAX_OFFENDERS])

    def warn(check, msg, data=None):
        warnings.append(f"[{check}] {msg}")
        c = report["checks"].setdefault(check, {"status": "warn", "messages": []})
        if c["status"] != "fail":
            c["status"] = "warn"
        c["messages"].append(msg)
        if data is not None:
            c["data"] = data

    def ok(check, data=None):
        c = report["checks"].setdefault(check, {"status": "pass", "messages": []})
        if data is not None:
            c["data"] = data

    if not os.path.exists(args.full):
        print(f"ERROR: full CSV not found: {args.full}", file=sys.stderr)
        return 1
    full_cols, full_rows = read_csv(args.full)

    # --- schema ---------------------------------------------------------
    required_full = ["source", "category_path", "depth"] + LEVEL_COLS
    missing = [c for c in required_full if c not in full_cols]
    if missing:
        err("schema", f"full CSV missing columns: {missing}")
    else:
        ok("schema")

    hier_cols, hier_rows = ([], [])
    if os.path.exists(args.hierarchy):
        hier_cols, hier_rows = read_csv(args.hierarchy)
        missing_h = [c for c in LEVEL_COLS if c not in hier_cols]
        if missing_h:
            err("schema", f"hierarchy CSV missing columns: {missing_h}")
    else:
        err("schema", f"hierarchy CSV not found: {args.hierarchy}")

    # If full schema is broken we cannot proceed meaningfully.
    if missing:
        _finalize(report, errors, warnings, args.report)
        return 1

    # --- per-row: source, depth, contiguity -----------------------------
    bad_source, bad_depth, gaps = [], [], []
    paths = []           # list of (source, category_path, upath)
    seen_pairs = Counter()
    for i, row in enumerate(full_rows):
        src = (row.get("source") or "").strip()
        if src not in VALID_SOURCES:
            bad_source.append(f"row {i}: source={src!r}")
        d_raw = (row.get("depth") or "").strip()
        try:
            d = int(float(d_raw))
            if not (1 <= d <= 5):
                bad_depth.append(f"row {i}: depth={d_raw!r}")
        except ValueError:
            bad_depth.append(f"row {i}: depth={d_raw!r}")
        upath, gap = row_path(row)
        if gap:
            gaps.append(f"row {i}: {[row.get(c) for c in LEVEL_COLS]}")
        if not upath:
            gaps.append(f"row {i}: no unified levels")
        paths.append((src, (row.get("category_path") or "").strip(), upath))
        seen_pairs[(src, (row.get("category_path") or "").strip())] += 1

    if bad_source:
        err("source", f"{len(bad_source)} row(s) with source not in {sorted(VALID_SOURCES)}", bad_source)
    else:
        ok("source")
    if bad_depth:
        err("depth", f"{len(bad_depth)} row(s) with depth not an integer in 1..5", bad_depth)
    else:
        ok("depth")
    if gaps:
        err("contiguous", f"{len(gaps)} row(s) with a gap in unified levels", gaps)
    else:
        ok("contiguous")

    dupes = [f"{p} x{n}" for p, n in seen_pairs.items() if n > 1]
    if dupes:
        err("coverage", f"{len(dupes)} duplicate (source, category_path) row(s)", dupes)

    # --- build tree ------------------------------------------------------
    children = defaultdict(set)     # parent tuple -> set(child tuple)
    node_members = defaultdict(list)  # node tuple -> list of member row indices
    all_nodes = set()
    for idx, (src, cat, upath) in enumerate(paths):
        for k in range(1, len(upath) + 1):
            node = tuple(upath[:k])
            parent = tuple(upath[:k - 1])
            children[parent].add(node)
            all_nodes.add(node)
            node_members[node].append(idx)

    l1_nodes = sorted(children[()])
    report["summary_tree"] = {
        "level1_count": len(l1_nodes),
        "total_nodes": len(all_nodes),
        "rows": len(full_rows),
    }

    # --- rule 1: level-1 count + children per parent --------------------
    if not (L1_MIN <= len(l1_nodes) <= L1_MAX):
        err("rule1_level1_count",
            f"level-1 categories = {len(l1_nodes)}; must be {L1_MIN}..{L1_MAX}",
            [n[0] for n in l1_nodes])
    else:
        ok("rule1_level1_count", {"count": len(l1_nodes)})

    child_violations = []
    for parent, kids in children.items():
        if parent == ():
            continue  # level-1 handled above
        n = len(kids)
        if n and not (CHILD_MIN <= n <= CHILD_MAX):
            child_violations.append(f"{' | '.join(parent)} -> {n} children")
    if child_violations:
        err("rule1_children_per_parent",
            f"{len(child_violations)} parent(s) with child count outside {CHILD_MIN}..{CHILD_MAX}",
            child_violations)
    else:
        ok("rule1_children_per_parent")

    # --- rule 2: name format (<=5 words, ' | ' separator) ---------------
    name_violations = []
    for node in all_nodes:
        name = node[-1]
        w = words_of(name)
        if len(w) == 0:
            name_violations.append(f"{name!r}: empty")
        elif len(w) > MAX_NAME_WORDS:
            name_violations.append(f"{name!r}: {len(w)} words (max {MAX_NAME_WORDS})")
        # Standardized, ' | '-joined words only: no raw path separators, and
        # multi-word names must actually use ' | ' (not spaces).
        elif re.search(r"[>/]|::", name):
            name_violations.append(f"{name!r}: contains raw path separator (>, /, ::) — standardize")
        elif len(w) >= 2 and " | " not in name:
            name_violations.append(f"{name!r}: multi-word name must join words with ' | '")
    if name_violations:
        err("rule2_name_format",
            f"{len(name_violations)} name(s) violate the format (<= {MAX_NAME_WORDS} "
            "standardized words joined by ' | ')", name_violations)
    else:
        ok("rule2_name_format")

    # --- rule 4: parent/child name overlap ------------------------------
    pc_overlap = []
    for parent, kids in children.items():
        if parent == ():
            continue
        pw = set(words_of(parent[-1]))
        for kid in kids:
            shared = pw & set(words_of(kid[-1]))
            if shared:
                pc_overlap.append(f"{parent[-1]!r} -> {kid[-1]!r} share {sorted(shared)}")
    if pc_overlap:
        err("rule4_parent_child_overlap",
            f"{len(pc_overlap)} parent/child pair(s) share a word", pc_overlap)
    else:
        ok("rule4_parent_child_overlap")

    # --- rule 5: sibling distinctness -----------------------------------
    sib_overlap = []
    for parent, kids in children.items():
        kid_list = sorted(kids)
        for a, b in combinations(kid_list, 2):
            j = jaccard(words_of(a[-1]), words_of(b[-1]))
            if j >= SIBLING_MAX_OVERLAP:
                sib_overlap.append(f"{a[-1]!r} ~ {b[-1]!r} overlap={j:.2f}")
    if sib_overlap:
        err("rule5_sibling_overlap",
            f"{len(sib_overlap)} sibling pair(s) with >= {SIBLING_MAX_OVERLAP:.0%} word overlap",
            sib_overlap)
    else:
        ok("rule5_sibling_overlap")

    # --- coverage (needs normalized) ------------------------------------
    if args.normalized and os.path.exists(args.normalized):
        with open(args.normalized, encoding="utf-8") as fh:
            norm = json.load(fh)
        expected = {(r["source"], r["category_path"]) for r in norm.get("rows", [])}
        actual = set(seen_pairs)
        missing_paths = sorted(expected - actual)
        extra_paths = sorted(actual - expected)
        if missing_paths or extra_paths:
            msg = f"{len(missing_paths)} source path(s) unmapped, {len(extra_paths)} unexpected"
            err("coverage", msg,
                [f"MISSING {p}" for p in missing_paths[:MAX_OFFENDERS]] +
                [f"EXTRA {p}" for p in extra_paths[:MAX_OFFENDERS]])
        elif not dupes:
            ok("coverage", {"mapped": len(actual)})
    elif not dupes:
        warn("coverage", "skipped exact coverage check (no --normalized provided)")

    # --- hierarchy consistency ------------------------------------------
    if hier_cols:
        hier_paths = []
        for r in hier_rows:
            p = tuple((r.get(c) or "").strip() for c in LEVEL_COLS)
            p = tuple(x for x in p if x)  # leading non-empty (assumes contiguous)
            hier_paths.append(p)
        hier_set = set(hier_paths)
        hdupes = [p for p, n in Counter(hier_paths).items() if n > 1]
        miss = sorted(all_nodes - hier_set)
        extra = sorted(hier_set - all_nodes)
        if miss or extra or hdupes:
            err("hierarchy",
                f"{len(miss)} node(s) missing, {len(extra)} extra, {len(hdupes)} duplicate row(s)",
                [f"MISSING {' | '.join(p)}" for p in miss[:MAX_OFFENDERS]] +
                [f"EXTRA {' | '.join(p)}" for p in extra[:MAX_OFFENDERS]] +
                [f"DUP {' | '.join(p)}" for p in hdupes[:MAX_OFFENDERS]])
        else:
            ok("hierarchy", {"nodes": len(hier_set)})

    # --- rule 2 soft: representativeness --------------------------------
    rep_low = []
    rep_scores = {}
    for node in all_nodes:
        if node not in children or not children[node]:
            continue  # leaves trivially represent themselves
        member_idx = node_members[node]
        if len(member_idx) < MIN_MEMBERS_FOR_REP:
            continue
        tok_counter = Counter()
        for idx in member_idx:
            tok_counter.update(set(content_tokens(paths[idx][1])))
        if not tok_counter:
            continue
        top, top_n = tok_counter.most_common(1)[0]
        score = top_n / len(member_idx)
        rep_scores[" | ".join(node)] = round(score, 2)
        if score < REPRESENTATIVE_MIN:
            rep_low.append(f"{' | '.join(node)} (top theme '{top}' covers {score:.0%})")
    if rep_low:
        warn("rule2_representativeness",
             f"{len(rep_low)} node(s) below {REPRESENTATIVE_MIN:.0%} theme coverage "
             "(heuristic — confirm with semantic judgment)",
             rep_low[:MAX_OFFENDERS])
    else:
        ok("rule2_representativeness")
    report["checks"].setdefault("rule2_representativeness", {})["scores"] = rep_scores

    # --- rule 6 soft: pyramid balance -----------------------------------
    balance = {}
    for depth in range(1, 5):
        parents = [p for p in children if len(p) == depth and children[p]]
        counts = [len(children[p]) for p in parents]
        if not counts:
            continue
        mean = statistics.mean(counts)
        cv = (statistics.pstdev(counts) / mean) if mean else 0.0
        balance[f"level{depth}_to_{depth + 1}"] = {
            "parents": len(parents), "min": min(counts), "max": max(counts),
            "mean": round(mean, 2), "cv": round(cv, 2),
        }
        if cv > BALANCE_CV_WARN:
            warn("rule6_pyramid_balance",
                 f"level {depth}->{depth + 1} children-per-parent is uneven (cv={cv:.2f})")
    report["checks"].setdefault("rule6_pyramid_balance", {"status": "pass", "messages": []})
    report["checks"]["rule6_pyramid_balance"]["data"] = balance

    # --- rule 7 soft: source evenness -----------------------------------
    global_src = Counter(src for src, _, _ in paths)
    per_l1 = {}
    src_branch_coverage = Counter()
    for l1 in l1_nodes:
        members = node_members[l1]
        mix = Counter(paths[i][0] for i in members)
        per_l1[l1[0]] = dict(mix)
        for s in mix:
            src_branch_coverage[s] += 1
    n_l1 = max(len(l1_nodes), 1)
    coverage_frac = {s: round(src_branch_coverage[s] / n_l1, 2) for s in global_src}
    for s, c in global_src.items():
        if src_branch_coverage[s] == 0:
            warn("rule7_source_even", f"source {s!r} absent from the taxonomy")
        elif coverage_frac[s] < 0.5 and c >= 0.1 * sum(global_src.values()):
            warn("rule7_source_even",
                 f"source {s!r} appears in only {coverage_frac[s]:.0%} of level-1 branches")
    report["checks"].setdefault("rule7_source_even", {"status": "pass", "messages": []})
    report["checks"]["rule7_source_even"]["data"] = {
        "global": dict(global_src), "level1_coverage_fraction": coverage_frac,
        "per_level1_source_mix": per_l1,
    }

    return _finalize(report, errors, warnings, args.report)


def _finalize(report, errors, warnings, report_path):
    report["summary"] = {"errors": len(errors), "warnings": len(warnings)}
    try:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"WARNING: could not write report: {exc}", file=sys.stderr)
    for line in errors:
        print(line, file=sys.stderr)
    for line in warnings:
        print(line, file=sys.stderr)
    if errors:
        print(f"INVALID: {len(errors)} error(s), {len(warnings)} warning(s) "
              f"— see {report_path}")
        return 1
    print(f"VALID: 0 errors, {len(warnings)} warning(s) — see {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
