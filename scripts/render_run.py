"""Re-render the run-matrix visual for a finished or in-progress run dir.

Usage: uv run python scripts/render_run.py runs/<campaign>
The visual is a pure function of campaign.json + summary.jsonl, so this works
on partial (still-running) campaigns too — it shows the cells done so far.
"""
import json
import sys
from pathlib import Path

from rich.console import Console

from aip_skillbench.run_matrix import Cell, MatrixState, Mode, _render

run = Path(sys.argv[1])
camp = json.loads((run / "campaign.json").read_text())
modes = [Mode(m) for m in camp["modes"]]
cells = [
    Cell(task=t, model=m, mode=md.value, trial=tr)
    for t in camp["tasks"]
    for m in camp["models"]
    for md in modes
    for tr in range(camp["trials"])
]
state = MatrixState(
    cells,
    modes,
    camp["models"],
    camp["tasks"],
    camp["trials"],
    run / "summary.jsonl",
    run / "summary.csv",
    run / "status.json",
)
state.preload()
Console().print(_render(state))
