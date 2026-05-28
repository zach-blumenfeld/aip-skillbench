#!/usr/bin/env python3
"""Emit the XML snippet for a chosen strategy.

Output is a fragment intended for insertion into pom.xml at the right
section (<dependencies>, <dependencyManagement>, etc.) — not a full pom.
The agent decides *where* to insert based on the existing pom layout; this
script is responsible for the *what*.

Reads JSON from stdin or first positional arg (the output of
`choose_strategy.py`) and writes a single fragment for each issue.
"""
from __future__ import annotations

import json
import sys
import textwrap
from typing import Any


def fragment(issue: dict[str, Any]) -> str:
    strategy = issue.get("strategy")
    gid = issue.get("group_id", "GROUP_ID")
    aid = issue.get("artifact_id", "ARTIFACT_ID")
    version = issue.get("version") or issue.get("winning_version") or "VERSION"

    if strategy == "add-missing-dependency":
        return textwrap.dedent(f"""\
            <!-- Insert under <dependencies> -->
            <dependency>
                <groupId>{gid}</groupId>
                <artifactId>{aid}</artifactId>
                <version>{version}</version>
            </dependency>""")

    if strategy == "bom-import":
        bom_gid = issue.get("bom_group_id", "BOM_GROUP")
        bom_aid = issue.get("bom_artifact_id", "BOM_ARTIFACT")
        return textwrap.dedent(f"""\
            <!-- Insert under <dependencyManagement><dependencies>.
                 After this, the matching <dependency> entries can omit <version>. -->
            <dependency>
                <groupId>{bom_gid}</groupId>
                <artifactId>{bom_aid}</artifactId>
                <version>BOM_VERSION</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>""")

    if strategy == "dependency-management-pin":
        return textwrap.dedent(f"""\
            <!-- Insert under <dependencyManagement><dependencies>.
                 Pins the version everywhere this g:a appears in the tree. -->
            <dependency>
                <groupId>{gid}</groupId>
                <artifactId>{aid}</artifactId>
                <version>{version}</version>
            </dependency>""")

    if strategy == "transitive-exclusion":
        parent_gid = issue.get("parent_group_id", "PARENT_GROUP")
        parent_aid = issue.get("parent_artifact_id", "PARENT_ARTIFACT")
        return textwrap.dedent(f"""\
            <!-- Add <exclusions> to the parent dependency that pulls in {gid}:{aid}.
                 Verify with `mvn dependency:tree` which dep is the real parent. -->
            <dependency>
                <groupId>{parent_gid}</groupId>
                <artifactId>{parent_aid}</artifactId>
                <exclusions>
                    <exclusion>
                        <groupId>{gid}</groupId>
                        <artifactId>{aid}</artifactId>
                    </exclusion>
                </exclusions>
            </dependency>""")

    if strategy == "scope-fix":
        new_scope = issue.get("recommended_scope", "compile")
        return textwrap.dedent(f"""\
            <!-- Change the scope on the existing <dependency> for {gid}:{aid}. -->
            <dependency>
                <groupId>{gid}</groupId>
                <artifactId>{aid}</artifactId>
                <version>{version}</version>
                <scope>{new_scope}</scope>
            </dependency>""")

    if strategy == "declare-used-undeclared":
        return textwrap.dedent(f"""\
            <!-- Code references {gid}:{aid} but only inherits it transitively.
                 Declare it explicitly so a future transitive bump can't drop it. -->
            <dependency>
                <groupId>{gid}</groupId>
                <artifactId>{aid}</artifactId>
                <version>{version}</version>
            </dependency>""")

    if strategy == "remove-unused-declared":
        return textwrap.dedent(f"""\
            <!-- Delete this <dependency> from pom.xml unless it is loaded reflectively
                 (e.g., JDBC drivers, SPI providers, Hibernate dialects). -->
            <dependency>
                <groupId>{gid}</groupId>
                <artifactId>{aid}</artifactId>
            </dependency>""")

    if strategy == "swap-snapshot-for-release":
        return textwrap.dedent(f"""\
            <!-- Replace the SNAPSHOT version with the matching released version.
                 Find the latest release on Maven Central before committing. -->
            <dependency>
                <groupId>{gid}</groupId>
                <artifactId>{aid}</artifactId>
                <version>RELEASED_VERSION  <!-- was {version} --></version>
            </dependency>""")

    return f"<!-- No snippet template for strategy={strategy!r} -->"


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] != "-":
        data = json.loads(open(argv[1]).read())
    else:
        data = json.loads(sys.stdin.read())

    issues = data.get("issues", []) if isinstance(data, dict) else data
    out_parts = []
    for i, issue in enumerate(issues, 1):
        header = f"=== issue {i}: {issue.get('issue_type')} → {issue.get('strategy')} ==="
        out_parts.append(header)
        out_parts.append(fragment(issue))
        out_parts.append("")
    print("\n".join(out_parts))
    print(f"generate_patch_snippet: wrote {len(issues)} fragment(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
