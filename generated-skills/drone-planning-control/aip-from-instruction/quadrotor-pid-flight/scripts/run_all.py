"""Batch driver: iterate every command file in a directory.

Usage:
    uv run scripts/run_all.py <commands_dir> <results_root> [system_params.yaml]

Example:
    uv run scripts/run_all.py /root/commands /root/results /root/system_params.yaml

For each `<commands_dir>/<id>.txt`, runs run_command with results in
`<results_root>/<id>/`. Prints a summary line per command and a final
pass/fail count.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_command import run  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    cmd_dir = Path(argv[1])
    out_root = Path(argv[2])
    sp = argv[3] if len(argv) > 3 else "system_params.yaml"
    cmd_files = sorted(p for p in cmd_dir.iterdir() if p.suffix == ".txt")
    if not cmd_files:
        print(f"no .txt commands found in {cmd_dir}", file=sys.stderr)
        return 2
    out_root.mkdir(parents=True, exist_ok=True)
    passed = 0
    failed = 0
    for cf in cmd_files:
        cmd_id = cf.stem
        results_dir = str(out_root / cmd_id)
        try:
            summary = run(str(cf), results_dir, sp)
        except Exception as e:
            print(json.dumps({"command_file": str(cf), "error": str(e)}))
            failed += 1
            continue
        print(json.dumps({
            "command_file": str(cf),
            "passed": summary["passed"],
            "failures": summary["failures"],
        }))
        if summary["passed"]:
            passed += 1
        else:
            failed += 1
    print(f"DONE: {passed} passed, {failed} failed", file=sys.stderr)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
