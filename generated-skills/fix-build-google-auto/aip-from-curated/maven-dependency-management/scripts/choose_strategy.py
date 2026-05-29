#!/usr/bin/env python3
"""Map a diagnosed issue to a resolution strategy.

Reads the JSON emitted by `diagnose_conflict.py` (stdin or path arg) and
attaches a `strategy` to each issue using a deterministic decision table.
Conditional logic lives here, not in the SKILL.md body.

Strategies:
  - add-missing-dependency        : declare the artifact in <dependencies>
  - bom-import                    : add a BOM under <dependencyManagement> with scope=import
  - dependency-management-pin     : pin a version in <dependencyManagement>
  - transitive-exclusion          : exclude a problematic transitive
  - scope-fix                     : change scope (e.g., test→compile, compile→provided)
  - declare-used-undeclared       : add an explicit <dependency> for a used transitive
  - remove-unused-declared        : delete an unused <dependency>
  - swap-snapshot-for-release     : replace SNAPSHOT with a released version

The chosen strategy is a starting point, not the final word — the agent
should still inspect surrounding pom.xml context (parent POM, scope of the
project, presence of an existing BOM) before applying.
"""
from __future__ import annotations

import json
import sys
from typing import Any


KNOWN_BOM_GROUPS = {
    "org.springframework.boot": ("org.springframework.boot", "spring-boot-dependencies"),
    "org.springframework.cloud": ("org.springframework.cloud", "spring-cloud-dependencies"),
    "com.fasterxml.jackson.core": ("com.fasterxml.jackson", "jackson-bom"),
    "com.fasterxml.jackson.dataformat": ("com.fasterxml.jackson", "jackson-bom"),
    "com.fasterxml.jackson.module": ("com.fasterxml.jackson", "jackson-bom"),
    "io.netty": ("io.netty", "netty-bom"),
    "io.grpc": ("io.grpc", "grpc-bom"),
    "software.amazon.awssdk": ("software.amazon.awssdk", "bom"),
    "com.google.cloud": ("com.google.cloud", "libraries-bom"),
    "org.junit.jupiter": ("org.junit", "junit-bom"),
    "org.junit.vintage": ("org.junit", "junit-bom"),
    "org.junit.platform": ("org.junit", "junit-bom"),
}

# Logging artifacts that frequently need to be excluded when a project chose
# a different logging backend.
LOGGING_FACADES = {
    ("commons-logging", "commons-logging"),
    ("log4j", "log4j"),
    ("org.slf4j", "slf4j-log4j12"),
    ("org.springframework.boot", "spring-boot-starter-logging"),
}


def pick(issue: dict[str, Any]) -> dict[str, Any]:
    t = issue.get("issue_type")
    out = dict(issue)
    rationale = []

    if t == "missing-artifact":
        out["strategy"] = "add-missing-dependency"
        rationale.append("artifact could not be resolved; declare it explicitly")
    elif t == "version-conflict":
        gid = issue.get("group_id", "")
        if gid in KNOWN_BOM_GROUPS:
            bom = KNOWN_BOM_GROUPS[gid]
            out["strategy"] = "bom-import"
            out["bom_group_id"] = bom[0]
            out["bom_artifact_id"] = bom[1]
            rationale.append(f"{gid} is best managed via {bom[0]}:{bom[1]} BOM")
        else:
            out["strategy"] = "dependency-management-pin"
            rationale.append("pin a single version across modules via <dependencyManagement>")
    elif t == "convergence-error":
        out["strategy"] = "dependency-management-pin"
        rationale.append("enforcer requires a single convergent version; pin in <dependencyManagement>")
    elif t == "used-undeclared":
        out["strategy"] = "declare-used-undeclared"
        rationale.append("code uses this artifact but only inherits it transitively — make it explicit")
    elif t == "unused-declared":
        out["strategy"] = "remove-unused-declared"
        rationale.append("declared but never used at compile; safe to remove unless reflectively loaded")
    elif t == "duplicate-class":
        out["strategy"] = "transitive-exclusion"
        rationale.append("two artifacts ship the same class; exclude the duplicate from the loser")
    elif t == "snapshot-in-release":
        out["strategy"] = "swap-snapshot-for-release"
        rationale.append("SNAPSHOT versions are non-reproducible; replace with the matching released version")
    else:
        out["strategy"] = "manual-investigation"
        rationale.append(f"no strategy mapping for issue_type={t!r}")

    out["rationale"] = " ".join(rationale)
    return out


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] != "-":
        data = json.loads(open(argv[1]).read())
    else:
        data = json.loads(sys.stdin.read())

    issues = data.get("issues", []) if isinstance(data, dict) else data
    enriched = [pick(issue) for issue in issues]
    out = data if isinstance(data, dict) else {}
    out["issues"] = enriched
    print(json.dumps(out, indent=2))
    print(f"choose_strategy: tagged {len(enriched)} issue(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
