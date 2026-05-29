#!/usr/bin/env python3
"""Classify a Maven build failure log into a known error class.

Reads a Maven build log (path argv[1] or stdin) and emits JSON to stdout:

    {
      "error_class": "<primary class>",
      "candidates": [
        {"error_class": ..., "match": "...", ...class-specific keys}
      ]
    }

Classes (priority order, first hit wins for `error_class`):
  missing-artifact   — Maven could not download/resolve a coordinate
  package-not-found  — javac "package X does not exist" (often a scope bug)
  class-not-found    — runtime ClassNotFoundException / NoClassDefFoundError
  method-not-found   — runtime NoSuchMethodError (version skew)
  version-conflict   — dependency convergence / upper-bound failures
  compile-symbol     — javac "cannot find symbol"
  other              — no pattern matched

Stdlib only — must run in the BugSwarm container without extra installs.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Order matters: earlier patterns claim the "primary" class.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "missing-artifact",
        re.compile(
            r"Could not find artifact\s+([\w.\-]+):([\w.\-]+):(?:jar|pom|war)"
            r"(?::[\w.\-]+)?:([\w.\-]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "missing-artifact",
        re.compile(
            r"Failure to find\s+([\w.\-]+):([\w.\-]+):(?:jar|pom|war)"
            r"(?::[\w.\-]+)?:([\w.\-]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "missing-artifact",
        re.compile(
            r"Could not resolve dependencies for project[^\n]*?:\s*"
            r"([\w.\-]+):([\w.\-]+):(?:jar|pom|war):([\w.\-]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "package-not-found",
        re.compile(r"package\s+([\w.]+)\s+does not exist"),
    ),
    (
        "class-not-found",
        re.compile(
            r"java\.lang\.(?:ClassNotFoundException|NoClassDefFoundError):\s*([\w.$/]+)"
        ),
    ),
    (
        "method-not-found",
        re.compile(r"java\.lang\.NoSuchMethodError:\s*([^\s\n]+)"),
    ),
    (
        "version-conflict",
        re.compile(
            r"(dependency convergence|requireUpperBoundDeps|conflicts with|"
            r"Failed while enforcing releasability)",
            re.IGNORECASE,
        ),
    ),
    (
        "compile-symbol",
        re.compile(
            r"cannot find symbol[\s\S]{0,200}?symbol:\s+(\w+)\s+([^\s\n]+)",
            re.IGNORECASE,
        ),
    ),
]


def classify(log: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for label, rx in PATTERNS:
        for m in rx.finditer(log):
            match_text = m.group(0).strip()
            key = (label, match_text)
            if key in seen:
                continue
            seen.add(key)
            finding: dict[str, Any] = {
                "error_class": label,
                "match": match_text[:240],
            }
            groups = m.groups()
            if label == "missing-artifact" and len(groups) >= 3:
                finding["groupId"] = groups[0]
                finding["artifactId"] = groups[1]
                finding["version"] = groups[2]
            elif label == "package-not-found" and groups:
                finding["package"] = groups[0]
            elif label == "class-not-found" and groups:
                finding["fqcn"] = groups[0]
            elif label == "method-not-found" and groups:
                finding["method"] = groups[0]
            elif label == "compile-symbol" and len(groups) >= 2:
                finding["symbol_kind"] = groups[0]
                finding["symbol"] = groups[1]
            candidates.append(finding)

    primary = candidates[0]["error_class"] if candidates else "other"
    return {"error_class": primary, "candidates": candidates}


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] not in ("-", ""):
        log = Path(argv[1]).read_text(errors="replace")
    else:
        log = sys.stdin.read()
    result = classify(log)
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
