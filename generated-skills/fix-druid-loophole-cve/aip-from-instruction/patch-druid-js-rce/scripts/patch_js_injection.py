#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Patch the Apache Druid JavaScript RCE (CVE-2021-25646 class).

Root cause: classes that gate JavaScript execution take the server's
`JavaScriptConfig` via a Jackson `@JacksonInject` constructor parameter that
carries NO explicit property name. With Jackson's default `useInput`
(`OptBoolean.DEFAULT` == "input wins"), an attacker can supply that parameter
through the request body under the empty key `""` — e.g.
`{"type":"javascript","function":"...","":{"enabled":true}}` — which overrides
the Guice-injected, server-controlled config and flips `enabled` to true,
bypassing `druid.javascript.enabled=false`.

Fix: pin every such injection point to the injected value by adding
`useInput = OptBoolean.FALSE` so request input can never override it, and add
the `OptBoolean` import. Behavior is preserved for legitimate configs: when the
server enables JavaScript the injected config still says enabled=true.

Modes
-----
apply (default): rewrite every vulnerable site in-place and add the import.
                 Prints each modified file. Idempotent.
--check        : report any remaining un-pinned site. Exit 1 if any found,
                 0 if the tree is clean. Use as a post-edit / post-build gate.

Usage
-----
  uv run patch_js_injection.py /root/druid
  uv run patch_js_injection.py --check /root/druid
"""

import argparse
import re
import sys
from pathlib import Path

# A vulnerable injection site: a *bare* `@JacksonInject` (no parentheses, so no
# useInput pin) whose annotated parameter is of type JavaScriptConfig. Allows
# intervening annotations (e.g. @Nullable) and a `final` modifier between the
# annotation and the type. `\s+` after `@JacksonInject` guarantees we never
# match an already-parameterized `@JacksonInject(...)` form — that is the
# patched/idempotent case.
BARE_SITE = re.compile(
    r"@JacksonInject"
    r"(?P<between>\s+(?:@\w+(?:\([^)]*\))?\s+)*(?:final\s+)?JavaScriptConfig\b)"
)

OPTBOOLEAN_IMPORT = "import com.fasterxml.jackson.annotation.OptBoolean;"
JACKSONINJECT_IMPORT = "import com.fasterxml.jackson.annotation.JacksonInject;"


def find_sites(text: str) -> int:
    """Count bare (un-pinned) JavaScriptConfig injection sites in source text."""
    return len(BARE_SITE.findall(text))


def add_optboolean_import(text: str) -> str:
    """Ensure the OptBoolean import is present; insert in a sensible spot."""
    if OPTBOOLEAN_IMPORT in text:
        return text
    lines = text.splitlines(keepends=True)

    # Preferred anchor: right after the JacksonInject import (keeps the two
    # Jackson-annotation imports together and alphabetically ordered).
    for i, line in enumerate(lines):
        if line.strip() == JACKSONINJECT_IMPORT:
            indent = line[: len(line) - len(line.lstrip())]
            lines.insert(i + 1, f"{indent}{OPTBOOLEAN_IMPORT}\n")
            return "".join(lines)

    # Fallback: after the last com.fasterxml.jackson.annotation import.
    last = None
    for i, line in enumerate(lines):
        if line.strip().startswith("import com.fasterxml.jackson.annotation."):
            last = i
    if last is not None:
        lines.insert(last + 1, f"{OPTBOOLEAN_IMPORT}\n")
        return "".join(lines)

    # Last resort: after the package declaration.
    for i, line in enumerate(lines):
        if line.strip().startswith("package "):
            lines.insert(i + 1, f"\n{OPTBOOLEAN_IMPORT}\n")
            return "".join(lines)

    return OPTBOOLEAN_IMPORT + "\n" + text


def patch_text(text: str) -> tuple[str, int]:
    """Pin every bare site and add the import. Returns (new_text, n_sites)."""
    n = find_sites(text)
    if n == 0:
        return text, 0
    new_text = BARE_SITE.sub(
        r"@JacksonInject(useInput = OptBoolean.FALSE)\g<between>", text
    )
    new_text = add_optboolean_import(new_text)
    return new_text, n


def iter_java_files(root: Path):
    for p in root.rglob("*.java"):
        # Skip generated/build output; patch source only.
        parts = set(p.parts)
        if "target" in parts or "generated-sources" in parts:
            continue
        yield p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "druid_dir",
        nargs="?",
        default="/root/druid",
        help="root of the Druid source tree (default: /root/druid)",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="report remaining un-pinned sites without editing; exit 1 if any",
    )
    args = ap.parse_args()

    root = Path(args.druid_dir)
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2

    if args.check:
        offenders = []
        for f in iter_java_files(root):
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            n = find_sites(text)
            if n:
                offenders.append((f, n))
        if offenders:
            for f, n in offenders:
                print(f"UNPATCHED: {f} ({n} site(s))", file=sys.stderr)
            print(f"FAIL: {len(offenders)} file(s) still have un-pinned "
                  f"JavaScriptConfig injection", file=sys.stderr)
            return 1
        print("OK: no un-pinned JavaScriptConfig injection sites remain")
        return 0

    modified = []
    total_sites = 0
    for f in iter_java_files(root):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new_text, n = patch_text(text)
        if n and new_text != text:
            f.write_text(new_text, encoding="utf-8")
            modified.append((f, n))
            total_sites += n

    if not modified:
        print("No bare JavaScriptConfig injection sites found "
              "(already patched, or pattern not present).")
        return 0
    for f, n in modified:
        print(f"PATCHED: {f} ({n} site(s))")
    print(f"Done: {len(modified)} file(s), {total_sites} site(s) pinned to "
          f"useInput = OptBoolean.FALSE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
