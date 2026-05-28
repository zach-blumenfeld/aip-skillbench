"""End-to-end orchestrator for one command file.

Usage:
    uv run scripts/run_command.py <command_path> <results_dir> [system_params.yaml]

Example:
    uv run scripts/run_command.py /root/commands/001.txt /root/results/001 /root/system_params.yaml

Writes:
    <results_dir>/planned_trajectory.npy
    <results_dir>/actual_trajectory.npy
    <results_dir>/metrics_3d.json
    <results_dir>/tuning_results.json
    <results_dir>/plots/desired_vs_actual.png
    <results_dir>/plots/errors.png
    <results_dir>/plots/cumulative_errors.png

Prints a JSON summary to stdout. Exits non-zero if verify-specs fails.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_metrics import compute_metrics  # noqa: E402
from generate_plots import generate  # noqa: E402
from load_system_params import load as load_params  # noqa: E402
from parse_command import parse as parse_cmd  # noqa: E402
from plan_trajectory import plan  # noqa: E402
from tune_pid import tune  # noqa: E402
from verify_specs import verify  # noqa: E402
from write_outputs import write  # noqa: E402


def run(command_path: str, results_dir: str,
        system_params_path: str = "system_params.yaml") -> dict:
    params = load_params(system_params_path)
    with open(command_path) as f:
        command = parse_cmd(f.read())
    planned = plan(command, params)
    tuned = tune(planned, params, command)
    metrics = compute_metrics(planned, tuned["actual"], command)
    generate(planned, tuned["actual"], results_dir)
    write(planned, tuned["actual"], metrics, tuned["gains"], results_dir)
    verdict = verify(planned, tuned["actual"], metrics, params)
    return {
        "command": command["raw"],
        "results_dir": os.path.abspath(results_dir),
        "metrics": metrics,
        "tuning_iterations": tuned["iterations"],
        "passed": verdict["passed"],
        "failures": verdict["failures"],
    }


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    command_path = argv[1]
    results_dir = argv[2]
    sp = argv[3] if len(argv) > 3 else "system_params.yaml"
    summary = run(command_path, results_dir, sp)
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
