#!/usr/bin/env python3
"""Verify a Spring Security 5 → 6 migration is complete.

Two checks:
    1. NO legacy patterns remain (WebSecurityConfigurerAdapter, antMatchers,
       authorizeRequests, @EnableGlobalMethodSecurity, javax.servlet imports,
       chained-DSL signatures).
    2. WHERE expected, new patterns ARE present (SecurityFilterChain bean
       and @EnableMethodSecurity when method-level security is in use).

Usage:
    python scripts/verify_migration.py <project-root>

Exits 0 if no legacy patterns are found AND required new patterns are
present (or method-level security is not used at all). Exits 1 otherwise.
Prints a JSON report to stdout listing every check, its status, and any
offending locations.
"""

import json
import re
import sys
from pathlib import Path

LEGACY_CHECKS = [
    ("websecurityconfigureradapter",
     re.compile(r"\bWebSecurityConfigurerAdapter\b")),
    ("enable-global-method-security",
     re.compile(r"@EnableGlobalMethodSecurity\b")),
    ("ant-matchers",
     re.compile(r"\.antMatchers\s*\(")),
    ("mvc-matchers",
     re.compile(r"\.mvcMatchers\s*\(")),
    ("regex-matchers",
     re.compile(r"\.regexMatchers\s*\(")),
    ("authorize-requests",
     re.compile(r"\.authorizeRequests\s*\(")),
    ("authentication-manager-bean-override",
     re.compile(r"authenticationManagerBean\s*\(")),
    ("javax-servlet-import",
     re.compile(r"^\s*import\s+javax\.servlet\.", re.MULTILINE)),
    ("chained-csrf-disable",
     re.compile(r"\.csrf\s*\(\s*\)\s*\.disable\s*\(\s*\)")),
]

NEW_CHECK_SECURITY_FILTER_CHAIN = re.compile(r"\bSecurityFilterChain\b")
NEW_CHECK_ENABLE_METHOD_SECURITY = re.compile(r"@EnableMethodSecurity\b")
USES_METHOD_LEVEL_SECURITY = re.compile(
    r"@(PreAuthorize|PostAuthorize|Secured|RolesAllowed|PreFilter|PostFilter)\b"
)


def find_matches(root: Path, pattern: re.Pattern) -> list[dict]:
    occ = []
    for path in root.rglob("*.java"):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for m in pattern.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            occ.append({"file": str(path), "line": line_no})
    return occ


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_migration.py <project-root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    report: dict = {"legacy_checks": [], "presence_checks": []}
    failed = False

    for key, pattern in LEGACY_CHECKS:
        hits = find_matches(root, pattern)
        ok = not hits
        report["legacy_checks"].append({
            "name": key, "ok": ok, "occurrences": hits,
        })
        if not ok:
            failed = True

    sfc = find_matches(root, NEW_CHECK_SECURITY_FILTER_CHAIN)
    report["presence_checks"].append({
        "name": "security-filter-chain-present",
        "ok": bool(sfc),
        "advice": "Expect at least one SecurityFilterChain @Bean. "
                  "If a SecurityConfig exists in the project, this bean "
                  "should be defined there.",
        "occurrences": sfc,
    })
    if not sfc:
        failed = True

    method_use = find_matches(root, USES_METHOD_LEVEL_SECURITY)
    enable_ms = find_matches(root, NEW_CHECK_ENABLE_METHOD_SECURITY)
    if method_use:
        ok = bool(enable_ms)
        report["presence_checks"].append({
            "name": "enable-method-security-when-method-level-used",
            "ok": ok,
            "advice": "Project uses @PreAuthorize / @PostAuthorize / etc.; "
                      "@EnableMethodSecurity must be present on a "
                      "@Configuration class.",
            "method_level_uses": method_use[:5],
            "occurrences": enable_ms,
        })
        if not ok:
            failed = True
    else:
        report["presence_checks"].append({
            "name": "enable-method-security-when-method-level-used",
            "ok": True,
            "advice": "Method-level security annotations not in use; "
                      "@EnableMethodSecurity not required.",
        })

    report["summary"] = {
        "all_passed": not failed,
    }
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
