"""Strip status="error" rows from a campaign's summary.jsonl + summary.csv
so a re-run of `aip-skillbench run-matrix` retries them.

Usage:
    uv run python scripts/retry_errors.py runs/eval-1-haiku

Then re-run the original launch command — resume will pick up exactly the
errored cells (passes/fails stay in the summary and get skipped as normal).

WARNING: don't run this while a campaign is actively writing to the same
output dir. Either wait for the run to finish or stop it with Ctrl-C first.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def filter_jsonl(path: Path) -> tuple[int, int]:
    rows = [l for l in path.read_text().splitlines() if l.strip()]
    keep = [l for l in rows if json.loads(l).get("status") != "error"]
    path.write_text("\n".join(keep) + ("\n" if keep else ""))
    return len(rows), len(keep)


def filter_csv(path: Path) -> tuple[int, int]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    keep = [r for r in rows if r["status"] != "error"]
    if not rows:
        return 0, 0
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(keep)
    return len(rows), len(keep)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <campaign-dir>", file=sys.stderr)
        return 2

    campaign = Path(sys.argv[1])
    jsonl = campaign / "summary.jsonl"
    csv_path = campaign / "summary.csv"

    if not jsonl.exists():
        print(f"error: {jsonl} does not exist", file=sys.stderr)
        return 1

    status_file = campaign / "status.json"
    if status_file.exists():
        try:
            s = json.loads(status_file.read_text())
            if s.get("running", 0) > 0:
                print(
                    f"WARNING: status.json shows {s['running']} cells currently running. "
                    "Stop the campaign (Ctrl-C in its tmux window) or wait for it to finish "
                    "before running this script. Re-run with --force-anyway to bypass.",
                    file=sys.stderr,
                )
                if "--force-anyway" not in sys.argv:
                    return 1
        except (json.JSONDecodeError, OSError):
            pass

    jsonl_bak = jsonl.with_suffix(jsonl.suffix + ".bak")
    csv_bak = csv_path.with_suffix(csv_path.suffix + ".bak")
    jsonl_bak.write_bytes(jsonl.read_bytes())
    if csv_path.exists():
        csv_bak.write_bytes(csv_path.read_bytes())
    print(f"backed up: {jsonl_bak.name}" + (f", {csv_bak.name}" if csv_path.exists() else ""))

    before, after = filter_jsonl(jsonl)
    removed = before - after
    print(f"summary.jsonl: kept {after}/{before} rows ({removed} errors removed)")

    if csv_path.exists():
        before_c, after_c = filter_csv(csv_path)
        print(f"summary.csv:   kept {after_c}/{before_c} rows ({before_c - after_c} errors removed)")

    if removed == 0:
        print("\nNo error rows to remove — nothing to retry.")
        return 0

    print(
        f"\nDone. Re-run the original launch command and resume will retry the "
        f"{removed} errored cell(s):"
    )
    print(
        f"\n    caffeinate -dimsu uv run aip-skillbench run-matrix "
        f"--config configs/<your-config>.yaml --out {campaign} --yes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
