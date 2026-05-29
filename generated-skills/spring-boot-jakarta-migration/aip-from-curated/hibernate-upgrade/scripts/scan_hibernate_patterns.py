#!/usr/bin/env python3
"""Scan a Java/Spring Boot project for Hibernate 5 patterns that need migration.

Walks the project tree once and reports findings as JSON to stdout. The findings
catalog drives every downstream step: mechanical rewrites, Criteria API
migration, type-mapping migration, configuration updates.

Usage:
  python scripts/scan_hibernate_patterns.py <project_root>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Directories we never want to scan (build outputs, IDE, VCS, deps).
SKIP_DIRS = {".git", ".idea", ".gradle", "target", "build", "out", "node_modules", ".mvn"}

# Files we treat as Java source.
JAVA_GLOB = "*.java"

# Properties / YAML files we inspect for dialect & hibernate config.
CONFIG_PATTERNS = ("application.properties", "application*.properties", "application.yml", "application*.yml", "application*.yaml")

# Regex catalog. Each entry: name -> (compiled_pattern, file_kind).
PATTERNS = {
    # Legacy Criteria API (org.hibernate.Criteria) - removed in H6.
    "legacy_criteria_api": re.compile(r"(session\.createCriteria|org\.hibernate\.Criteria|Restrictions\.)"),
    # Old custom-type annotations.
    "type_annotation": re.compile(r"@Type\s*\(\s*type\s*="),
    "typedef_annotation": re.compile(r"@TypeDef\s*\("),
    # Non-standard HQL "update from" (optional `from` was stripped in H6).
    "update_from_hql": re.compile(r"update\s+from\s+", re.IGNORECASE),
    # javax.persistence -> jakarta.persistence imports.
    "javax_persistence_import": re.compile(r"^\s*import\s+javax\.persistence\."),
    # javax.persistence.* package references (non-import) in code body.
    "javax_persistence_reference": re.compile(r"\bjavax\.persistence\."),
    # `select distinct ... join fetch` — `distinct` is unnecessary in H6.
    "distinct_join_fetch": re.compile(r"select\s+distinct\b[^\"]*\bjoin\s+fetch\b", re.IGNORECASE),
}

# Properties-file regexes (look for dialect overrides + observability gaps).
PROP_PATTERNS = {
    "explicit_dialect": re.compile(r"^\s*spring\.jpa\.database-platform\s*[:=]"),
    "hibernate_dialect_alt": re.compile(r"^\s*spring\.jpa\.properties\.hibernate\.dialect\s*[:=]"),
    "generate_statistics": re.compile(r"^\s*spring\.jpa\.properties\.hibernate\.generate_statistics\s*[:=]"),
    "timezone_storage": re.compile(r"^\s*spring\.jpa\.properties\.hibernate\.timezone\.default_storage\s*[:=]"),
}


def iter_files(root: Path, suffixes: tuple[str, ...] | None = None, names: tuple[str, ...] | None = None):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if suffixes and path.suffix in suffixes:
            yield path
            continue
        if names and any(path.match(n) for n in names):
            yield path


def scan_java(root: Path) -> dict[str, list[dict]]:
    findings: dict[str, list[dict]] = {key: [] for key in PATTERNS}
    for path in iter_files(root, suffixes=(".java",)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(root))
        for lineno, line in enumerate(text.splitlines(), start=1):
            for key, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings[key].append({
                        "file": rel,
                        "line": lineno,
                        "text": line.strip(),
                    })
    return findings


def scan_config(root: Path) -> dict[str, list[dict]]:
    findings: dict[str, list[dict]] = {key: [] for key in PROP_PATTERNS}
    seen_props_files: list[str] = []
    for path in iter_files(root, names=CONFIG_PATTERNS):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(root))
        seen_props_files.append(rel)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for key, pattern in PROP_PATTERNS.items():
                if pattern.search(line):
                    findings[key].append({
                        "file": rel,
                        "line": lineno,
                        "text": line.strip(),
                    })
    findings["_config_files_seen"] = [{"file": f} for f in seen_props_files]
    return findings


def summarize(java: dict, config: dict) -> dict:
    counts = {k: len(v) for k, v in java.items()}
    counts.update({f"config.{k}": len(v) for k, v in config.items() if not k.startswith("_")})
    return counts


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: scan_hibernate_patterns.py <project_root>", file=sys.stderr)
        return 2
    root = Path(argv[1]).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    java = scan_java(root)
    config = scan_config(root)
    output = {
        "project_root": str(root),
        "java": java,
        "config": config,
        "summary": summarize(java, config),
    }
    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
