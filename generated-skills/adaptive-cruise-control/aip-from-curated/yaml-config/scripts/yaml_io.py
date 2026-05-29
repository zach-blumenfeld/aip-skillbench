"""YAML configuration I/O helpers for the ACC project.

Importable functions:
    safe_load_yaml(path) -> object | None
    load_config(path, defaults=None) -> dict
    safe_dump_yaml(data, path, allow_unicode=True) -> None

CLI:
    python scripts/yaml_io.py read <path> [--defaults-json '<json>']
    python scripts/yaml_io.py write <path> --data-json '<json>'

All reads use yaml.safe_load (no arbitrary-object construction).
All writes preserve key order and use block style for human readability.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

import yaml


def safe_load_yaml(path: str) -> Any:
    """Read a YAML file using safe_load. Caller handles FileNotFoundError / YAMLError."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_config(path: str, defaults: Optional[dict] = None) -> dict:
    """Load a YAML config file with a defaults fallback.

    Missing file → return a copy of defaults.
    Parse error  → log to stderr and return a copy of defaults.
    Successful load → shallow-merge loaded over defaults so explicit YAML wins.
    """
    base: dict = {} if defaults is None else dict(defaults)

    if not os.path.exists(path):
        return base

    try:
        with open(path, "r") as f:
            loaded = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"YAML parse error in {path}: {e}", file=sys.stderr)
        return base

    if not isinstance(loaded, dict):
        print(
            f"YAML at {path} is not a mapping (got {type(loaded).__name__}); using defaults",
            file=sys.stderr,
        )
        return base

    base.update(loaded)
    return base


def safe_dump_yaml(data: Any, path: str, allow_unicode: bool = True) -> None:
    """Write data as YAML in block style, preserving the dict's key order."""
    with open(path, "w") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=allow_unicode,
        )


def _main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="YAML config I/O helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_read = sub.add_parser("read", help="Read a YAML file; print JSON to stdout")
    p_read.add_argument("path")
    p_read.add_argument(
        "--defaults-json",
        default=None,
        help="Optional JSON object of defaults to merge under the loaded config.",
    )

    p_write = sub.add_parser("write", help="Write JSON data as YAML to a path")
    p_write.add_argument("path")
    p_write.add_argument(
        "--data-json",
        required=True,
        help="JSON-encoded mapping to serialize as YAML.",
    )

    args = parser.parse_args(argv)

    if args.cmd == "read":
        defaults = json.loads(args.defaults_json) if args.defaults_json else None
        config = load_config(args.path, defaults)
        json.dump(config, sys.stdout)
        sys.stdout.write("\n")
        return 0

    if args.cmd == "write":
        data = json.loads(args.data_json)
        safe_dump_yaml(data, args.path)
        print(args.path)
        return 0

    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
