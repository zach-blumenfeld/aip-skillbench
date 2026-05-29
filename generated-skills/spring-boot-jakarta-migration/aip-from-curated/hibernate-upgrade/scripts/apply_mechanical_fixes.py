#!/usr/bin/env python3
"""Apply mechanical Hibernate 5 -> 6 rewrites that are safe across the codebase.

Safe = the transformation is unambiguous and reversible. Anything requiring
judgment (Criteria API rewrites, custom type mappings, query semantic review)
stays in prose steps for the agent.

Rewrites applied:
  1. `import javax.persistence.*` -> `import jakarta.persistence.*`
     (only the persistence sub-package; leaves other javax.* alone)
  2. `update from <Entity>` -> `update <Entity>` inside JPQL/HQL strings
     (matches `update<ws>from<ws>` case-insensitively; Hibernate 6 rejects the
     legacy `from` keyword in bulk updates)

Idempotent. Re-running on already-migrated code is a no-op.

Usage:
  python scripts/apply_mechanical_fixes.py <project_root> [--dry-run]

Outputs JSON to stdout describing every file changed and the count per rule.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".idea", ".gradle", "target", "build", "out", "node_modules", ".mvn"}

# Rule 1: javax.persistence import migration. Anchored to import lines only
# to avoid touching string literals or comments that mention the old package.
JAVAX_IMPORT_RE = re.compile(r"^(\s*import\s+(?:static\s+)?)javax\.persistence\.", re.MULTILINE)

# Rule 2: `update from` -> `update`. Hibernate stripped the optional `from`
# keyword from bulk update HQL in v6.
UPDATE_FROM_RE = re.compile(r"\bupdate\s+from\s+", re.IGNORECASE)


def iter_java(root: Path):
    for path in root.rglob("*.java"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def rewrite_file(path: Path, dry_run: bool) -> dict:
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"file": str(path), "error": str(exc)}

    new_text, n_imports = JAVAX_IMPORT_RE.subn(r"\1jakarta.persistence.", original)
    new_text, n_update_from = UPDATE_FROM_RE.subn("update ", new_text)

    changed = new_text != original
    if changed and not dry_run:
        path.write_text(new_text, encoding="utf-8")

    return {
        "file": str(path),
        "changed": changed,
        "javax_to_jakarta_imports": n_imports,
        "update_from_rewrites": n_update_from,
    }


def main(argv: list[str]) -> int:
    args = argv[1:]
    dry_run = False
    if "--dry-run" in args:
        dry_run = True
        args.remove("--dry-run")
    if len(args) != 1:
        print("usage: apply_mechanical_fixes.py <project_root> [--dry-run]", file=sys.stderr)
        return 2

    root = Path(args[0]).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    results = []
    totals = {"javax_to_jakarta_imports": 0, "update_from_rewrites": 0, "files_changed": 0}
    for path in iter_java(root):
        rel = path.relative_to(root)
        result = rewrite_file(path, dry_run)
        result["file"] = str(rel)
        if result.get("changed"):
            totals["files_changed"] += 1
            results.append(result)
        totals["javax_to_jakarta_imports"] += result.get("javax_to_jakarta_imports", 0)
        totals["update_from_rewrites"] += result.get("update_from_rewrites", 0)

    json.dump({"project_root": str(root), "dry_run": dry_run, "totals": totals, "files": results}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
