#!/usr/bin/env python3
"""Migrate javax.servlet.* imports and fully qualified references to jakarta.servlet.*.

Spring Security 6 (Spring Boot 3) depends on Jakarta EE 9+, which renamed
the javax.* namespace to jakarta.*. Security configs commonly touch
HttpServletRequest/Response in entry points, filters, and exception
handlers — those imports must be rewritten.

This script rewrites:

    import javax.servlet.            → import jakarta.servlet.
    javax.servlet.                   → jakarta.servlet.
    (only when they appear on import lines or as fully qualified types)

It does NOT rewrite other javax.* namespaces (javax.persistence,
javax.validation, etc.) — those are out of scope for the Spring Security
migration. Handle them in the broader Jakarta migration.

Usage:
    python scripts/migrate_servlet_imports.py <project-root> [--dry-run]
"""

import argparse
import json
import re
import sys
from pathlib import Path

IMPORT_PATTERN = re.compile(r"^(\s*import\s+(?:static\s+)?)javax\.servlet\.",
                            re.MULTILINE)
QUALIFIED_PATTERN = re.compile(r"\bjavax\.servlet\.")


def rewrite(text: str) -> tuple[str, int]:
    new_text, n1 = IMPORT_PATTERN.subn(r"\1jakarta.servlet.", text)
    new_text, n2 = QUALIFIED_PATTERN.subn("jakarta.servlet.", new_text)
    return new_text, n1 + n2


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
        new_text, count = rewrite(original)
        if count == 0:
            continue
        files_changed += 1
        edits.append({"file": str(path), "replacements": count})
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
