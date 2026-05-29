"""Render ONE combined run-matrix visual across several run dirs.

Like render_run.py, but merges multiple campaigns into a single matrix +
aggregates, with a section break separating protocol versions (the v0.3a3
cohort tasks vs the hand-picked v0.3a2 eval-3med tasks). The visual is a pure
function of each campaign.json + summary.jsonl.

Usage:
    uv run python scripts/render_runs_combined.py \
        runs/eval-cohort-a-sonnet-aipv0_3a3 \
        runs/eval-cohort-b-sonnet-aipv0_3a3 \
        runs/eval-cohort-c-sonnet-aipv0_3a3 \
        runs/eval-3med-sonnet-v0_3a2 \
        --svg figures/combined-matrix.svg

Optional --modes to pick mode columns (default: the primary human-curated vs
aip-from-curated comparison shared by all 27 tasks).
"""
import argparse
import json
import time
from pathlib import Path

from rich.console import Console, Group
from rich.table import Table
from rich.text import Text

from aip_skillbench.run_matrix import (
    MODE_LABEL,
    SYM_ERROR,
    SYM_FAIL,
    SYM_PASS,
    SYM_PENDING,
    SYM_RUNNING,
    Cell,
    MatrixState,
    Mode,
)

DEFAULT_MODES = ["human-curated", "aip-from-curated"]

GLYPH = {
    "pending": SYM_PENDING,
    "running": f"[yellow]{SYM_RUNNING}[/]",
    "pass": f"[green]{SYM_PASS}[/]",
    "fail": f"[red]{SYM_FAIL}[/]",
    "error": f"[magenta]{SYM_ERROR}[/]",
}


def version_of(run_dir: Path) -> str:
    """Protocol version a run was produced under, from its dir name."""
    return "v0.3a2" if "v0_3a2" in run_dir.name else "v0.3a3"


def render_combined(state: MatrixState, task_version: dict[str, str]) -> Group:
    n_total = len(state.cells)
    n_done = sum(1 for s in state.status.values() if s in {"pass", "fail", "error"})
    n_pass = sum(1 for s in state.status.values() if s == "pass")
    rate = (n_pass / n_done * 100) if n_done else 0.0
    header = Text.from_markup(
        f"[bold]aip-skillbench combined run-matrix[/]  "
        f"cells {n_done}/{n_total} done  pass {n_pass} ({rate:.1f}%)  "
        f"{len(state.tasks)} tasks × {len(state.modes)} modes × {state.trials} trials"
    )

    matrix = Table(title="Trials", show_header=True, header_style="bold")
    matrix.add_column("task")
    matrix.add_column("model")
    for mode in state.modes:
        matrix.add_column(MODE_LABEL[mode], justify="center")

    prev_version: str | None = None
    for task in state.tasks:
        version = task_version.get(task, "v0.3a3")
        if prev_version is not None and version != prev_version:
            # Section break + a labelled divider row marking the version switch.
            matrix.add_section()
            matrix.add_row(
                Text.from_markup(f"[dim italic]— {version} (eval-3med, hand-picked) —[/]"),
                "", *["" for _ in state.modes],
            )
        prev_version = version
        for model in state.models:
            row = [task, model]
            for mode in state.modes:
                glyphs = [
                    GLYPH[state.status.get(Cell(task, model, mode.value, tr).key, "pending")]
                    for tr in range(state.trials)
                ]
                row.append(" ".join(glyphs))
            matrix.add_row(*row)

    summary = Table(title="Per-mode aggregates", show_header=True, header_style="bold")
    summary.add_column("mode")
    summary.add_column("n", justify="right")
    summary.add_column("pass", justify="right")
    summary.add_column("pass%", justify="right")
    summary.add_column("mean reward", justify="right")
    summary.add_column("mean tool calls", justify="right")
    summary.add_column("mean wall (s)", justify="right")
    for mode in state.modes:
        rs = [r for r in state.results.values() if r.mode == mode.value]
        n = len(rs)
        passes = sum(1 for r in rs if r.status == "pass")
        rewards = [r.reward for r in rs if r.reward is not None]
        tcs = [r.n_tool_calls for r in rs if r.n_tool_calls is not None]
        wcs = [r.wall_clock for r in rs if r.wall_clock is not None]
        summary.add_row(
            MODE_LABEL[mode],
            str(n),
            str(passes),
            f"{passes / n * 100:.1f}%" if n else "—",
            f"{sum(rewards) / len(rewards):.2f}" if rewards else "—",
            f"{sum(tcs) / len(tcs):.1f}" if tcs else "—",
            f"{sum(wcs) / len(wcs):.1f}" if wcs else "—",
        )

    return Group(header, matrix, summary)


parser = argparse.ArgumentParser()
parser.add_argument("run_dirs", nargs="+", type=Path)
parser.add_argument("--modes", default=",".join(DEFAULT_MODES),
                    help="comma-separated mode values to render as columns")
parser.add_argument("--title", default=None,
                    help="optional title printed above the matrix")
parser.add_argument("--svg", type=Path, default=None,
                    help="also write the visual to this SVG path")
args = parser.parse_args()

modes = [Mode(m) for m in args.modes.split(",")]

# Merge campaigns in the order given. Tasks keep that order.
tasks: list[str] = []
models: list[str] = []
trials = 0
task_version: dict[str, str] = {}
for run in args.run_dirs:
    camp = json.loads((run / "campaign.json").read_text())
    for t in camp["tasks"]:
        if t not in tasks:
            tasks.append(t)
            task_version[t] = version_of(run)
    for m in camp["models"]:
        if m not in models:
            models.append(m)
    trials = max(trials, camp["trials"])

cells = [
    Cell(task=t, model=m, mode=md.value, trial=tr)
    for t in tasks for m in models for md in modes for tr in range(trials)
]

combined = MatrixState(
    cells, modes, models, tasks, trials,
    summary_path=Path("/dev/null"), csv_path=Path("/dev/null"),
    status_path=Path("/dev/null"),
)
combined.started_at = time.time()
valid_keys = {c.key for c in cells}
for run in args.run_dirs:
    per = MatrixState(
        cells, modes, models, tasks, trials,
        summary_path=run / "summary.jsonl",
        csv_path=run / "summary.csv",
        status_path=run / "status.json",
    )
    per.preload()
    # Keep only cells in this matrix: eval-3med also has aip-from-instruction
    # results that aren't columns here, and per.status defaults untouched cells
    # to "pending" (which would clobber earlier runs). valid_keys fixes both.
    for k, r in per.results.items():
        if k in valid_keys:
            combined.results[k] = r
            combined.status[k] = r.status

console = Console(record=args.svg is not None)
if args.title:
    console.print(f"[bold]{args.title}[/]")
console.print(render_combined(combined, task_version))

if args.svg:
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    console.save_svg(str(args.svg), title=args.title or "aip-skillbench combined run-matrix")
    print(f"\nwrote {args.svg}")
