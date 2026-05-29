#!/usr/bin/env python3
"""pom_migrate.py — Spring Boot 2.x → 3.x + Jakarta migration helper for Maven pom.xml.

Subcommands:
  scan POM      Inspect pom.xml and print findings JSON on stdout.
  migrate POM   Apply deterministic edits in place: bump spring-boot-starter-parent
                version, set <java.version>, strip deprecated javax/JAXB/activation
                deps, and replace the monolithic jjwt 0.9.x dependency with the
                modular jjwt-api/jjwt-impl/jjwt-jackson trio. Print change report JSON.
  verify POM    Re-scan and emit any residual issues. Exit 1 (with JSON) on issues.

Design notes:
  * Scanning uses xml.etree (handles the Maven default namespace).
  * Edits use regex on raw text so comments and existing indentation survive.
  * No external dependencies — stdlib only, runs anywhere with Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

POM_NS = "http://maven.apache.org/POM/4.0.0"
NS = {"m": POM_NS}

# Hardcoded list — these ship classes that collide with Jakarta EE in Spring Boot 3.
DEPRECATED_DEPS: list[tuple[str, str]] = [
    ("javax.xml.bind", "jaxb-api"),
    ("com.sun.xml.bind", "jaxb-impl"),
    ("com.sun.xml.bind", "jaxb-core"),
    ("javax.activation", "activation"),
    ("javax.activation", "javax.activation-api"),
]

JJWT_OLD_GID = "io.jsonwebtoken"
JJWT_OLD_AID = "jjwt"
# (groupId, artifactId, scope-or-None)
JJWT_MODULAR: list[tuple[str, str, str | None]] = [
    ("io.jsonwebtoken", "jjwt-api", None),
    ("io.jsonwebtoken", "jjwt-impl", "runtime"),
    ("io.jsonwebtoken", "jjwt-jackson", "runtime"),
]

DEFAULT_TARGET_SPRING_BOOT = "3.2.0"
DEFAULT_TARGET_JAVA = "21"
DEFAULT_JJWT_VERSION = "0.12.3"


# ---------------------------------------------------------------------------
# Scan: parse pom.xml structurally
# ---------------------------------------------------------------------------

def _first_text(elem: ET.Element, xpath: str) -> str | None:
    found = elem.find(xpath, NS)
    if found is None or found.text is None:
        return None
    txt = found.text.strip()
    return txt or None


def _parse_pom(path: Path) -> ET.ElementTree:
    try:
        return ET.parse(path)
    except FileNotFoundError:
        sys.stderr.write(f"error: pom.xml not found at {path}\n")
        sys.exit(2)
    except ET.ParseError as e:
        sys.stderr.write(f"error: failed to parse {path}: {e}\n")
        sys.exit(2)


def scan(pom_path: Path) -> dict:
    tree = _parse_pom(pom_path)
    root = tree.getroot()

    out: dict = {
        "pom_path": str(pom_path),
        "spring_boot_parent_version": None,
        "java_version": None,
        "java_version_source": None,
        "deprecated_dependencies": [],
        "jjwt_old_present": False,
        "jjwt_modular_present": False,
        "jakarta_xml_bind_present": False,
        "openrewrite_plugin_present": False,
    }

    parent = root.find("m:parent", NS)
    if parent is not None and _first_text(parent, "m:artifactId") == "spring-boot-starter-parent":
        out["spring_boot_parent_version"] = _first_text(parent, "m:version")

    props = root.find("m:properties", NS)
    if props is not None:
        for tag in ("java.version", "maven.compiler.release",
                    "maven.compiler.source", "maven.compiler.target"):
            v = _first_text(props, f"m:{tag}")
            if v:
                out["java_version"] = v
                out["java_version_source"] = tag
                break

    for dep in root.findall(".//m:dependencies/m:dependency", NS):
        gid = _first_text(dep, "m:groupId")
        aid = _first_text(dep, "m:artifactId")
        if not gid or not aid:
            continue
        if (gid, aid) in DEPRECATED_DEPS:
            out["deprecated_dependencies"].append({"groupId": gid, "artifactId": aid})
        if (gid, aid) == (JJWT_OLD_GID, JJWT_OLD_AID):
            out["jjwt_old_present"] = True
        if gid == "io.jsonwebtoken" and aid == "jjwt-api":
            out["jjwt_modular_present"] = True
        if gid == "jakarta.xml.bind" and aid == "jakarta.xml.bind-api":
            out["jakarta_xml_bind_present"] = True

    for plugin in root.findall(".//m:build//m:plugin", NS):
        if _first_text(plugin, "m:artifactId") == "rewrite-maven-plugin":
            out["openrewrite_plugin_present"] = True
            break

    return out


# ---------------------------------------------------------------------------
# Migrate: regex-based surgical edits
# ---------------------------------------------------------------------------

# Matches a <dependency>...</dependency> block including the preceding
# newline + indent. Non-greedy body capture so adjacent blocks don't merge.
_DEP_BLOCK_RE = re.compile(
    r"(?P<lead>\n[ \t]*)?<dependency\b[^>]*>(?P<body>.*?)</dependency>",
    re.DOTALL,
)


def _block_matches(body: str, gid: str, aid: str) -> bool:
    g = re.search(r"<groupId>\s*" + re.escape(gid) + r"\s*</groupId>", body)
    a = re.search(r"<artifactId>\s*" + re.escape(aid) + r"\s*</artifactId>", body)
    return bool(g and a)


def _remove_dependency(text: str, gid: str, aid: str) -> tuple[str, int]:
    """Strip every <dependency> block whose groupId+artifactId match. The block's
    leading newline+indent is dropped with it so we don't leave blank rows behind."""
    out_parts: list[str] = []
    last = 0
    removed = 0
    for m in _DEP_BLOCK_RE.finditer(text):
        if _block_matches(m.group("body"), gid, aid):
            out_parts.append(text[last:m.start()])
            last = m.end()
            removed += 1
    if removed == 0:
        return text, 0
    out_parts.append(text[last:])
    return "".join(out_parts), removed


def _replace_jjwt(text: str, jjwt_version: str) -> bool:
    """Replace the monolithic io.jsonwebtoken:jjwt block with the modular trio.
    Mutates `text` indirectly via the returned tuple. Returns (new_text, replaced?)."""
    # Anchor on the start of a line so we capture the block's indent.
    pat = re.compile(
        r"^(?P<indent>[ \t]*)<dependency\b[^>]*>(?P<body>.*?)</dependency>",
        re.DOTALL | re.MULTILINE,
    )
    for m in pat.finditer(text):
        if not _block_matches(m.group("body"), JJWT_OLD_GID, JJWT_OLD_AID):
            continue
        indent = m.group("indent")
        blocks: list[str] = []
        for gid, aid, scope in JJWT_MODULAR:
            lines = [
                "<dependency>",
                f"    <groupId>{gid}</groupId>",
                f"    <artifactId>{aid}</artifactId>",
                f"    <version>{jjwt_version}</version>",
            ]
            if scope:
                lines.append(f"    <scope>{scope}</scope>")
            lines.append("</dependency>")
            blocks.append("\n".join(indent + ln for ln in lines))
        replacement = "\n".join(blocks)
        return text[: m.start()] + replacement + text[m.end():], True
    return text, False


def _set_spring_boot_parent_version(text: str, target: str) -> tuple[str, str | None]:
    """Inside <parent>...</parent> for spring-boot-starter-parent, replace <version>."""
    parent_re = re.compile(r"<parent\b[^>]*>(?P<inner>.*?)</parent>", re.DOTALL)
    m = parent_re.search(text)
    if not m:
        return text, None
    inner = m.group("inner")
    if not re.search(r"<artifactId>\s*spring-boot-starter-parent\s*</artifactId>", inner):
        return text, None
    ver_re = re.compile(r"<version>(?P<v>[^<]+)</version>")
    vm = ver_re.search(inner)
    if not vm:
        return text, None
    old = vm.group("v").strip()
    if old == target:
        return text, old  # no change, but report the old==new value
    new_inner = inner[: vm.start()] + f"<version>{target}</version>" + inner[vm.end():]
    new_text = text[: m.start()] + m.group(0).replace(inner, new_inner) + text[m.end():]
    return new_text, old


def _set_java_version(text: str, target: str) -> tuple[str, str | None]:
    """Replace <java.version>X</java.version>. If absent, leaves text unchanged."""
    re_java = re.compile(r"<java\.version>(?P<v>[^<]+)</java\.version>")
    m = re_java.search(text)
    if not m:
        return text, None
    old = m.group("v").strip()
    if old == target:
        return text, old
    new_text = text[: m.start()] + f"<java.version>{target}</java.version>" + text[m.end():]
    return new_text, old


def migrate(
    pom_path: Path,
    target_spring_boot: str,
    target_java: str,
    jjwt_version: str,
) -> dict:
    text = pom_path.read_text(encoding="utf-8")
    report: dict = {
        "pom_path": str(pom_path),
        "spring_boot_parent_updated_from": None,
        "spring_boot_parent_updated_to": None,
        "java_version_updated_from": None,
        "java_version_updated_to": None,
        "dependencies_removed": [],
        "jjwt_upgraded": False,
        "jjwt_target_version": jjwt_version,
        "warnings": [],
    }

    new_text, old_ver = _set_spring_boot_parent_version(text, target_spring_boot)
    if old_ver is not None:
        report["spring_boot_parent_updated_from"] = old_ver
        report["spring_boot_parent_updated_to"] = target_spring_boot
        text = new_text
    else:
        report["warnings"].append(
            "Could not locate spring-boot-starter-parent <parent> block; set the parent version manually."
        )

    new_text, old_java = _set_java_version(text, target_java)
    if old_java is not None:
        report["java_version_updated_from"] = old_java
        report["java_version_updated_to"] = target_java
        text = new_text
    else:
        report["warnings"].append(
            "Could not locate <java.version> property; add or update it manually under <properties>."
        )

    # Swap jjwt first; old block is structurally similar to JAXB blocks and we want
    # to act on it before the indiscriminate dependency-removal loop sees it.
    text, upgraded = _replace_jjwt(text, jjwt_version)
    report["jjwt_upgraded"] = upgraded

    for gid, aid in DEPRECATED_DEPS:
        text, n = _remove_dependency(text, gid, aid)
        for _ in range(n):
            report["dependencies_removed"].append({"groupId": gid, "artifactId": aid})

    pom_path.write_text(text, encoding="utf-8")
    return report


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def _java_major(version: str) -> int | None:
    s = version.strip()
    if s.startswith("1."):
        s = s.split(".", 1)[1]
    s = s.split(".")[0]
    try:
        return int(s)
    except ValueError:
        return None


def verify(
    pom_path: Path,
    expected_spring_boot_major: int = 3,
    expected_java_min: int = 17,
) -> dict:
    findings = scan(pom_path)
    issues: list[str] = []

    sb_ver = findings["spring_boot_parent_version"]
    if sb_ver:
        major = sb_ver.split(".", 1)[0]
        if not major.isdigit() or int(major) < expected_spring_boot_major:
            issues.append(
                f"spring-boot-starter-parent is {sb_ver}; expected >= {expected_spring_boot_major}.x"
            )
    else:
        issues.append("spring-boot-starter-parent <version> not found")

    jv = findings["java_version"]
    if jv:
        major = _java_major(jv)
        if major is None or major < expected_java_min:
            issues.append(f"java.version is {jv}; expected >= {expected_java_min}")
    else:
        issues.append("<java.version> property not found")

    for d in findings["deprecated_dependencies"]:
        issues.append(f"deprecated dependency still present: {d['groupId']}:{d['artifactId']}")

    if findings["jjwt_old_present"]:
        issues.append(
            "monolithic io.jsonwebtoken:jjwt still present; replace with the modular jjwt-api/jjwt-impl/jjwt-jackson trio"
        )

    return {
        "pom_path": str(pom_path),
        "scan": findings,
        "issues": issues,
        "clean": not issues,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_scan = sub.add_parser("scan", help="Report pom.xml state as JSON")
    sp_scan.add_argument("pom", type=Path, help="Path to pom.xml")

    sp_mig = sub.add_parser("migrate", help="Apply migrations to pom.xml in place")
    sp_mig.add_argument("pom", type=Path, help="Path to pom.xml")
    sp_mig.add_argument("--target-spring-boot", default=DEFAULT_TARGET_SPRING_BOOT,
                        help=f"spring-boot-starter-parent target (default {DEFAULT_TARGET_SPRING_BOOT})")
    sp_mig.add_argument("--target-java", default=DEFAULT_TARGET_JAVA,
                        help=f"java.version target (default {DEFAULT_TARGET_JAVA})")
    sp_mig.add_argument("--jjwt-version", default=DEFAULT_JJWT_VERSION,
                        help=f"modular jjwt target version (default {DEFAULT_JJWT_VERSION})")

    sp_ver = sub.add_parser("verify", help="Verify pom.xml meets Spring Boot 3.x / Java 17+ state")
    sp_ver.add_argument("pom", type=Path, help="Path to pom.xml")
    sp_ver.add_argument("--expected-spring-boot-major", type=int, default=3)
    sp_ver.add_argument("--expected-java-min", type=int, default=17)

    args = p.parse_args(argv)

    if args.cmd == "scan":
        print(json.dumps(scan(args.pom), indent=2))
        return 0
    if args.cmd == "migrate":
        print(json.dumps(
            migrate(args.pom, args.target_spring_boot, args.target_java, args.jjwt_version),
            indent=2,
        ))
        return 0
    if args.cmd == "verify":
        result = verify(args.pom, args.expected_spring_boot_major, args.expected_java_min)
        print(json.dumps(result, indent=2))
        return 0 if result["clean"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
