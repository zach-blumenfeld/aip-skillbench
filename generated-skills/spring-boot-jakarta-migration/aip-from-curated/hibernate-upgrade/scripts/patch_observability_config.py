#!/usr/bin/env python3
"""Add Hibernate 6 observability properties to the project's Spring config.

Idempotent: skips properties already declared. Targets the first
`application.properties` (or .yml — appends a properties block in a YAML comment
fallback is intentionally NOT supported; pass the .properties file path
explicitly if YAML is preferred).

Properties added (when missing):
  spring.jpa.properties.hibernate.generate_statistics=true
  logging.level.org.hibernate.stat=debug
  logging.level.org.hibernate.SQL=debug
  spring.jpa.properties.hibernate.timezone.default_storage=NORMALIZE
  spring.jpa.properties.hibernate.session.events.log.LOG_QUERIES_SLOWER_THAN_MS=100

Usage:
  python scripts/patch_observability_config.py <project_root> [--target <relative_path>]

Outputs JSON summarising additions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".idea", ".gradle", "target", "build", "out", "node_modules", ".mvn"}

PROPS_TO_ADD = [
    ("spring.jpa.properties.hibernate.generate_statistics", "true"),
    ("logging.level.org.hibernate.stat", "debug"),
    ("logging.level.org.hibernate.SQL", "debug"),
    ("spring.jpa.properties.hibernate.timezone.default_storage", "NORMALIZE"),
    ("spring.jpa.properties.hibernate.session.events.log.LOG_QUERIES_SLOWER_THAN_MS", "100"),
]


def find_default_target(root: Path) -> Path | None:
    candidates = []
    for path in root.rglob("application.properties"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda p: (len(p.parts), str(p)))
    return candidates[0]


def patch(target: Path) -> dict:
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    existing_keys = set()
    for line in existing.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" in s:
            existing_keys.add(s.split("=", 1)[0].strip())

    additions = []
    for key, value in PROPS_TO_ADD:
        if key not in existing_keys:
            additions.append(f"{key}={value}")

    if not additions:
        return {"file": str(target), "added": [], "note": "all observability properties already present"}

    if existing and not existing.endswith("\n"):
        existing += "\n"
    block = "\n# Hibernate 6 observability (added by hibernate-upgrade skill)\n" + "\n".join(additions) + "\n"
    target.write_text(existing + block, encoding="utf-8")
    return {"file": str(target), "added": additions}


def main(argv: list[str]) -> int:
    args = argv[1:]
    target_override: str | None = None
    if "--target" in args:
        idx = args.index("--target")
        if idx + 1 >= len(args):
            print("--target requires a value", file=sys.stderr)
            return 2
        target_override = args[idx + 1]
        args = args[:idx] + args[idx + 2:]
    if len(args) != 1:
        print("usage: patch_observability_config.py <project_root> [--target <relative_path>]", file=sys.stderr)
        return 2

    root = Path(args[0]).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    if target_override:
        target = (root / target_override).resolve()
    else:
        found = find_default_target(root)
        if found is None:
            print(json.dumps({"project_root": str(root), "error": "no application.properties found; pass --target"}, indent=2))
            return 1
        target = found

    if target.suffix not in {".properties"}:
        print(f"target must be a .properties file (got {target.suffix}); pass --target with a .properties path", file=sys.stderr)
        return 2

    result = patch(target)
    result["project_root"] = str(root)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
