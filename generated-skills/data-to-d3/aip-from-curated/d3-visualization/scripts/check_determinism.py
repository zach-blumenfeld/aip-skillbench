#!/usr/bin/env python3
"""Validate a D3 visualization output for the non-negotiable determinism rules.

Checks the rendered HTML (and optionally a sibling SVG) against the rule set
codified in SKILL.md § Determinism rules. Each rule maps to one line of regex
or string lookup so violations can be reported individually.

Usage:
    python3 check_determinism.py path/to/chart.html [path/to/chart.svg]

Exit codes:
    0 — all checks pass
    1 — one or more violations
    2 — bad input (file missing, can't read)

Output:
    stdout: human summary
    stderr: one line per violation, prefixed with the rule key
"""

import re
import sys
from pathlib import Path


# Each rule: (key, severity, pattern_or_check, message)
# pattern_or_check may be:
#   - a compiled regex: matching means a VIOLATION
#   - a callable(text) -> bool: True means a VIOLATION
RULES = [
    (
        "no-math-random",
        "error",
        re.compile(r"\bMath\.random\s*\("),
        "Math.random() introduces nondeterminism; remove or replace with a seeded source.",
    ),
    (
        "no-d3-random",
        "error",
        re.compile(r"d3\.random[A-Z][a-zA-Z]*\s*\("),
        "d3-random helpers introduce nondeterminism; remove or seed explicitly.",
    ),
    (
        "no-cdn-d3",
        "error",
        re.compile(
            r"""<script[^>]+src\s*=\s*['"]https?://[^'"]*d3[^'"]*['"]""",
            re.IGNORECASE,
        ),
        "D3 is loaded from a remote URL; vendor a pinned local copy instead.",
    ),
    (
        "no-default-transitions",
        "warning",
        re.compile(r"\.transition\s*\("),
        ".transition() can introduce timing variance; remove unless seeded and bounded.",
    ),
    (
        "fixed-viewbox-or-dims",
        "error",
        lambda t: not (
            re.search(r"viewBox\s*=\s*['\"]", t) is not None
            or (
                re.search(r"\bwidth\s*=\s*['\"]?\d+", t)
                and re.search(r"\bheight\s*=\s*['\"]?\d+", t)
            )
        ),
        "SVG is missing a fixed viewBox or explicit width/height — output size will drift.",
    ),
    (
        "no-now-or-date",
        "error",
        re.compile(r"\bDate\.now\s*\(|\bnew\s+Date\s*\(\s*\)"),
        "Date.now() / new Date() embed wall-clock time; use a fixed date or pass via data.",
    ),
    (
        "no-window-location-host-leak",
        "warning",
        re.compile(r"window\.(location|navigator)\."),
        "Page-context lookups vary per environment; avoid using them in deterministic output.",
    ),
]


def check_file(path: Path) -> list[tuple[str, str, str]]:
    """Return list of (rule_key, severity, message) violations."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"could not read {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    violations: list[tuple[str, str, str]] = []
    for key, severity, check, msg in RULES:
        if isinstance(check, re.Pattern):
            if check.search(text):
                violations.append((key, severity, msg))
        else:
            if check(text):
                violations.append((key, severity, msg))
    return violations


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_determinism.py <chart.html> [chart.svg]", file=sys.stderr)
        return 2

    targets = [Path(p) for p in sys.argv[1:]]
    missing = [p for p in targets if not p.exists()]
    if missing:
        for p in missing:
            print(f"file not found: {p}", file=sys.stderr)
        return 2

    all_errors = 0
    all_warnings = 0
    for p in targets:
        violations = check_file(p)
        for key, severity, msg in violations:
            print(f"[{severity}] {p}:{key}: {msg}", file=sys.stderr)
            if severity == "error":
                all_errors += 1
            else:
                all_warnings += 1

    if all_errors == 0:
        suffix = f" ({all_warnings} warning(s))" if all_warnings else ""
        print(f"OK: determinism checks passed{suffix}")
        return 0
    print(f"FAIL: {all_errors} determinism error(s), {all_warnings} warning(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
