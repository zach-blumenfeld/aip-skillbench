#!/usr/bin/env python3
"""Parse Maven diagnostic output and classify dependency issues.

Reads the files written by `inspect_dependencies.sh` (or the equivalent raw
mvn output piped on stdin) and emits a JSON report of issues found, each
classified by `issue_type` so downstream steps can pick a resolution
strategy without re-parsing the logs.

Issue types emitted:
  - missing-artifact        : Maven could not resolve a coordinate
  - version-conflict        : multiple versions of the same g:a in the tree
  - convergence-error       : enforcer dependencyConvergence violation
  - unused-declared         : dependency:analyze flagged as unused
  - used-undeclared         : dependency:analyze flagged as undeclared
  - duplicate-class         : duplicate classes between artifacts
  - snapshot-in-release     : SNAPSHOT pulled into a non-SNAPSHOT build

Usage:
  diagnose_conflict.py [diagnostic_dir]      # reads files written by inspect_dependencies.sh
  diagnose_conflict.py -                     # reads raw mvn output from stdin

Output: JSON on stdout, human-readable summary on stderr.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable


COORD = r"([\w.\-]+):([\w.\-]+):([\w.\-]+):([\w.\-${}]+)(?::([\w.\-]+))?"
CONFLICT_LINE = re.compile(r"\(version managed from ([\w.\-${}]+)\)")
OMITTED_LINE = re.compile(r"omitted for conflict with ([\w.\-${}]+)")
COULD_NOT_RESOLVE = re.compile(
    r"Could not (?:resolve|find)(?:[^\n]*?:\s+)?([\w.\-]+):([\w.\-]+):[\w.]+:([\w.\-${}]+)"
)
UNRESOLVABLE = re.compile(
    r"(?:The following artifacts could not be resolved|Failure to find): ([\w.\-]+):([\w.\-]+):[\w.]+:([\w.\-${}]+)"
)
CONVERGE = re.compile(r"Failed while enforcing releasability\.|dependencyConvergence failed")
USED_UNDECLARED = re.compile(r"Used undeclared dependencies found:\s*(.*?)(?:\Z|\n\[(?:WARNING|INFO|ERROR)\])", re.S)
UNUSED_DECLARED = re.compile(r"Unused declared dependencies found:\s*(.*?)(?:\Z|\n\[(?:WARNING|INFO|ERROR)\])", re.S)
ARTIFACT_LINE = re.compile(r"\[WARNING\]\s+" + COORD)
DUPLICATE_CLASS = re.compile(r"duplicate (?:class|entry|module): ([\w.$/\\]+)", re.I)
SNAPSHOT_USAGE = re.compile(r"([\w.\-]+):([\w.\-]+):([\w.\-]+):([\w.\-]+-SNAPSHOT)")


def read_files(diag_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in ("dep-tree", "dep-tree-verbose", "dep-analyze", "compile", "effective-pom"):
        for ext in (".txt", ".xml"):
            p = diag_dir / f"{name}{ext}"
            if p.exists():
                out[name] = p.read_text(errors="replace")
                break
    return out


def find_missing(text: str) -> list[dict]:
    seen = set()
    found = []
    for m in COULD_NOT_RESOLVE.finditer(text):
        key = (m.group(1), m.group(2), m.group(3))
        if key in seen:
            continue
        seen.add(key)
        found.append({
            "issue_type": "missing-artifact",
            "group_id": m.group(1),
            "artifact_id": m.group(2),
            "version": m.group(3),
            "evidence": m.group(0)[:240],
        })
    for m in UNRESOLVABLE.finditer(text):
        key = (m.group(1), m.group(2), m.group(3))
        if key in seen:
            continue
        seen.add(key)
        found.append({
            "issue_type": "missing-artifact",
            "group_id": m.group(1),
            "artifact_id": m.group(2),
            "version": m.group(3),
            "evidence": m.group(0)[:240],
        })
    return found


def find_version_conflicts(verbose_tree: str) -> list[dict]:
    """A verbose tree marks resolved-away versions inline; collect them."""
    issues: list[dict] = []
    seen: set[tuple[str, str]] = set()
    coord_with_marker = re.compile(
        r"([\w.\-]+):([\w.\-]+):(?:jar|pom|war|ear|test-jar):([\w.\-]+)(?::(?:compile|provided|runtime|test|system))?\s+\((omitted for conflict with [\w.\-]+|version managed from [\w.\-]+)\)"
    )
    for m in coord_with_marker.finditer(verbose_tree):
        gid, aid, ver, note = m.group(1), m.group(2), m.group(3), m.group(4)
        key = (f"{gid}:{aid}", ver)
        if key in seen:
            continue
        seen.add(key)
        winner = note.split()[-1]
        issues.append({
            "issue_type": "version-conflict",
            "group_id": gid,
            "artifact_id": aid,
            "losing_version": ver,
            "winning_version": winner,
            "evidence": m.group(0)[:240],
        })
    return issues


def find_convergence(text: str) -> list[dict]:
    if CONVERGE.search(text):
        return [{
            "issue_type": "convergence-error",
            "evidence": "enforcer dependencyConvergence rule failed",
        }]
    return []


def find_analyze_issues(text: str) -> list[dict]:
    issues: list[dict] = []
    for kind, rx in (("used-undeclared", USED_UNDECLARED), ("unused-declared", UNUSED_DECLARED)):
        m = rx.search(text)
        if not m:
            continue
        block = m.group(1)
        for am in ARTIFACT_LINE.finditer(block):
            issues.append({
                "issue_type": kind,
                "group_id": am.group(1),
                "artifact_id": am.group(2),
                "version": am.group(4),
                "evidence": am.group(0).strip()[:240],
            })
    return issues


def find_duplicate_classes(text: str) -> list[dict]:
    issues = []
    for m in DUPLICATE_CLASS.finditer(text):
        issues.append({
            "issue_type": "duplicate-class",
            "class_name": m.group(1),
            "evidence": m.group(0)[:240],
        })
    return issues


def find_snapshots_in_release(text: str, effective_pom: str) -> list[dict]:
    if "SNAPSHOT" in effective_pom and re.search(r"<version>[\w.\-]+-SNAPSHOT</version>", effective_pom):
        return []  # project itself is a snapshot; not a problem
    issues = []
    seen: set[tuple[str, str, str]] = set()
    for m in SNAPSHOT_USAGE.finditer(text):
        key = (m.group(1), m.group(2), m.group(4))
        if key in seen:
            continue
        seen.add(key)
        issues.append({
            "issue_type": "snapshot-in-release",
            "group_id": m.group(1),
            "artifact_id": m.group(2),
            "version": m.group(4),
            "evidence": m.group(0)[:240],
        })
    return issues


def diagnose(files: dict[str, str]) -> list[dict]:
    compile_log = files.get("compile", "")
    dep_tree = files.get("dep-tree", "")
    dep_tree_verbose = files.get("dep-tree-verbose", "")
    dep_analyze = files.get("dep-analyze", "")
    effective_pom = files.get("effective-pom", "")

    issues: list[dict] = []
    issues += find_missing(compile_log + "\n" + dep_tree + "\n" + dep_tree_verbose)
    issues += find_version_conflicts(dep_tree_verbose)
    issues += find_convergence(compile_log + "\n" + dep_tree_verbose)
    issues += find_analyze_issues(dep_analyze)
    issues += find_duplicate_classes(compile_log)
    issues += find_snapshots_in_release(dep_tree, effective_pom)
    return issues


def main(argv: list[str]) -> int:
    if len(argv) == 1:
        diag_dir = Path("./.mvn-diagnostic")
    elif argv[1] == "-":
        text = sys.stdin.read()
        issues = (
            find_missing(text)
            + find_version_conflicts(text)
            + find_convergence(text)
            + find_analyze_issues(text)
            + find_duplicate_classes(text)
        )
        print(json.dumps({"issues": issues}, indent=2))
        print(f"diagnose_conflict: {len(issues)} issue(s)", file=sys.stderr)
        return 0
    else:
        diag_dir = Path(argv[1])

    if not diag_dir.is_dir():
        print(f"ERROR: diagnostic dir {diag_dir} not found — run inspect_dependencies.sh first", file=sys.stderr)
        return 2

    files = read_files(diag_dir)
    issues = diagnose(files)
    print(json.dumps({"diagnostic_dir": str(diag_dir), "issues": issues}, indent=2))
    print(f"diagnose_conflict: {len(issues)} issue(s) found in {diag_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
