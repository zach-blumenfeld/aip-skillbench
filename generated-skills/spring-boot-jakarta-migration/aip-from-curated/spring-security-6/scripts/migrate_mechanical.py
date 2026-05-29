#!/usr/bin/env python3
"""Apply mechanical (text-substitution) Spring Security 5 → 6 migrations.

This script ONLY covers substitutions that are safe to apply blindly across
every .java file under the project root. Structural refactors
(WebSecurityConfigurerAdapter removal, chained-DSL → lambda-DSL conversion)
are NOT handled here — they require code rewriting and are documented in
references/lambda-dsl-conversion.md.

Substitutions applied:

    @EnableGlobalMethodSecurity           → @EnableMethodSecurity
    EnableGlobalMethodSecurity (imports)  → EnableMethodSecurity
    .antMatchers(                         → .requestMatchers(
    .mvcMatchers(                         → .requestMatchers(
    .regexMatchers(                       → .requestMatchers(
    .authorizeRequests(                   → .authorizeHttpRequests(

Usage:
    python scripts/migrate_mechanical.py <project-root> [--dry-run]

Prints a JSON summary to stdout: { "files_changed": N, "edits": [...] }.
With --dry-run, no files are written.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SUBSTITUTIONS = [
    (re.compile(r"@EnableGlobalMethodSecurity\b"), "@EnableMethodSecurity"),
    (re.compile(r"\bEnableGlobalMethodSecurity\b"), "EnableMethodSecurity"),
    (re.compile(r"\.antMatchers\s*\("), ".requestMatchers("),
    (re.compile(r"\.mvcMatchers\s*\("), ".requestMatchers("),
    (re.compile(r"\.regexMatchers\s*\("), ".requestMatchers("),
    (re.compile(r"\.authorizeRequests\s*\("), ".authorizeHttpRequests("),
]


def apply_substitutions(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for pattern, repl in SUBSTITUTIONS:
        new_text, n = pattern.subn(repl, text)
        if n:
            counts[pattern.pattern] = counts.get(pattern.pattern, 0) + n
        text = new_text
    return text, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="project root to scan recursively")
    parser.add_argument("--dry-run", action="store_true",
                        help="report changes without writing files")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    edits = []
    files_changed = 0
    for path in root.rglob("*.java"):
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new_text, counts = apply_substitutions(original)
        if not counts:
            continue
        files_changed += 1
        edits.append({"file": str(path), "substitutions": counts})
        if not args.dry_run:
            path.write_text(new_text, encoding="utf-8")

    print(json.dumps({
        "dry_run": args.dry_run,
        "files_changed": files_changed,
        "edits": edits,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
