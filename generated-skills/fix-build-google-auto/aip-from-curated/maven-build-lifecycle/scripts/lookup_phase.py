#!/usr/bin/env python3
"""Look up a Maven phase's position in its lifecycle.

Usage:
    python lookup_phase.py <phase-name>
    python lookup_phase.py --before <phase-name>
    python lookup_phase.py --list [default|clean|site]

Returns the phase's 1-indexed position, the lifecycle it belongs to,
and (with --before) every phase that runs before it.
"""
from __future__ import annotations

import argparse
import json
import sys

DEFAULT = [
    "validate", "initialize",
    "generate-sources", "process-sources",
    "generate-resources", "process-resources",
    "compile", "process-classes",
    "generate-test-sources", "process-test-sources",
    "generate-test-resources", "process-test-resources",
    "test-compile", "process-test-classes",
    "test",
    "prepare-package", "package",
    "pre-integration-test", "integration-test", "post-integration-test",
    "verify",
    "install", "deploy",
]
CLEAN = ["pre-clean", "clean", "post-clean"]
SITE = ["pre-site", "site", "post-site", "site-deploy"]

LIFECYCLES = {"default": DEFAULT, "clean": CLEAN, "site": SITE}


def locate(phase: str) -> tuple[str, int] | None:
    for name, phases in LIFECYCLES.items():
        if phase in phases:
            return name, phases.index(phase) + 1
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("phase", nargs="?", help="phase to locate")
    p.add_argument("--before", action="store_true", help="also list every phase that runs before it")
    p.add_argument("--list", dest="list_lifecycle", choices=list(LIFECYCLES), help="dump a lifecycle")
    args = p.parse_args()

    if args.list_lifecycle:
        print(json.dumps({args.list_lifecycle: LIFECYCLES[args.list_lifecycle]}, indent=2))
        return 0

    if not args.phase:
        p.error("phase is required unless --list is given")

    hit = locate(args.phase)
    if hit is None:
        print(f"unknown phase: {args.phase}", file=sys.stderr)
        print("valid lifecycles: " + ", ".join(LIFECYCLES), file=sys.stderr)
        return 1

    lifecycle, pos = hit
    result: dict = {"phase": args.phase, "lifecycle": lifecycle, "position": pos}
    if args.before:
        result["runs_before_it"] = LIFECYCLES[lifecycle][: pos - 1]
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
