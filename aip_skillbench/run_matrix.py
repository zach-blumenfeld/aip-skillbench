"""run-matrix: run a (task × model × mode × trial) eval matrix concurrently with live progress."""

from __future__ import annotations

import concurrent.futures
import csv as csv_module
import json
import os
import random
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

ROOT = Path(__file__).resolve().parents[1]
VENDOR_SKILLSBENCH = ROOT / "vendor" / "skillsbench"
GENERATED_SKILLS = ROOT / "generated-skills"


class Mode(str, Enum):
    noskill = "noskill"
    human_curated = "human-curated"
    selfgen_skill_creator = "selfgen-skill-creator"
    aip_from_instruction = "aip-from-instruction"
    aip_from_curated = "aip-from-curated"


ALL_MODES: list[Mode] = list(Mode)


AGENT_KEY_ENV = {
    "claude-agent-acp": "ANTHROPIC_API_KEY",
    "codex-acp": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

MODE_LABEL = {
    Mode.noskill: "noskill",
    Mode.human_curated: "human",
    Mode.selfgen_skill_creator: "selfgen",
    Mode.aip_from_instruction: "aip-inst",
    Mode.aip_from_curated: "aip-cur",
}

SYM_PENDING = "▢"
SYM_RUNNING = "⟳"
SYM_PASS = "✓"
SYM_FAIL = "✗"
SYM_ERROR = "·"


@dataclass
class Cell:
    task: str
    model: str
    mode: str
    trial: int

    @property
    def key(self) -> str:
        return f"{self.task}|{self.model}|{self.mode}|t{self.trial}"

    @property
    def safe_name(self) -> str:
        return f"{self.task}__{self.model}__{self.mode}__t{self.trial}"


@dataclass
class CellResult:
    task: str
    model: str
    mode: str
    trial: int
    status: str  # "pass" | "fail" | "error"
    reward: Optional[float]
    n_tool_calls: Optional[int]
    wall_clock: Optional[float]
    error: Optional[str]
    jobs_dir: str
    trial_dir: Optional[str]
    started_at: str
    finished_at: str
    subprocess_rc: int


class MatrixState:
    """Shared, thread-safe state used by the UI and the persistence writers."""

    def __init__(
        self,
        cells: list[Cell],
        modes: list[Mode],
        models: list[str],
        tasks: list[str],
        trials: int,
        summary_path: Path,
        csv_path: Path,
        status_path: Path,
    ) -> None:
        self.cells = cells
        self.modes = modes
        self.models = models
        self.tasks = tasks
        self.trials = trials
        self.summary_path = summary_path
        self.csv_path = csv_path
        self.status_path = status_path
        self.started_at = time.time()
        self._lock = threading.Lock()
        self.status: dict[str, str] = {c.key: "pending" for c in cells}
        self.results: dict[str, CellResult] = {}

    def mark_running(self, cell: Cell) -> None:
        with self._lock:
            self.status[cell.key] = "running"

    def mark_done(self, cell: Cell, result: CellResult) -> None:
        with self._lock:
            self.status[cell.key] = result.status
            self.results[cell.key] = result
            with open(self.summary_path, "a") as f:
                f.write(json.dumps(asdict(result)) + "\n")
            csv_exists = self.csv_path.exists()
            with open(self.csv_path, "a", newline="") as f:
                writer = csv_module.DictWriter(f, fieldnames=list(asdict(result).keys()))
                if not csv_exists:
                    writer.writeheader()
                writer.writerow(asdict(result))
            snapshot = {
                "elapsed_sec": time.time() - self.started_at,
                "total": len(self.cells),
                "done": sum(1 for s in self.status.values() if s in {"pass", "fail", "error"}),
                "pass": sum(1 for s in self.status.values() if s == "pass"),
                "fail": sum(1 for s in self.status.values() if s == "fail"),
                "error": sum(1 for s in self.status.values() if s == "error"),
                "running": sum(1 for s in self.status.values() if s == "running"),
            }
            self.status_path.write_text(json.dumps(snapshot, indent=2))

    def preload(self) -> None:
        """Populate status/results from existing summary.jsonl (for resume)."""
        if not self.summary_path.exists():
            return
        for line in self.summary_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                cr = CellResult(**r)
                key = Cell(cr.task, cr.model, cr.mode, cr.trial).key
                self.results[key] = cr
                self.status[key] = cr.status
            except (json.JSONDecodeError, TypeError):
                continue


def _validate_tasks(tasks: list[str]) -> None:
    missing = [
        t for t in tasks
        if not (VENDOR_SKILLSBENCH / "tasks" / t / "instruction.md").exists()
    ]
    if missing:
        raise typer.BadParameter(
            f"task(s) not found under vendor/skillsbench/tasks/: {missing}"
        )


def _validate_generated_skills(tasks: list[str], modes: list[Mode]) -> None:
    needs: list[tuple[str, str]] = []
    if Mode.aip_from_instruction in modes:
        needs.extend((t, "aip-from-instruction") for t in tasks)
    if Mode.aip_from_curated in modes:
        needs.extend((t, "aip-from-curated") for t in tasks)
    missing: list[str] = []
    for task, sub in needs:
        d = GENERATED_SKILLS / task / sub
        if not d.exists() or not any(
            p.is_dir() and (p / "SKILL.md").exists() for p in d.iterdir()
        ):
            missing.append(str(d))
    if missing:
        bullets = "\n  - ".join(missing)
        raise typer.BadParameter(
            "Missing AIP-converted skill packs. Run `aip-skillbench convert` "
            "or `aip-skillbench batch-convert` first.\n  - " + bullets
        )


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _validate_api_key(agent: str) -> None:
    env_var = AGENT_KEY_ENV.get(agent)
    if env_var is None:
        return  # unknown agent — skip
    if os.environ.get(env_var):
        return
    if _read_dotenv(ROOT / ".env").get(env_var):
        return
    raise typer.BadParameter(
        f"agent '{agent}' needs {env_var}, but it is not set in env or .env"
    )


def _build_cells(
    tasks: list[str], models: list[str], modes: list[Mode], trials: int
) -> list[Cell]:
    cells: list[Cell] = []
    for t in tasks:
        for m in models:
            for mode in modes:
                for trial in range(trials):
                    cells.append(Cell(task=t, model=m, mode=mode.value, trial=trial))
    return cells


def _load_done(summary_path: Path) -> set[str]:
    if not summary_path.exists():
        return set()
    done: set[str] = set()
    for line in summary_path.read_text().splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            r = json.loads(s)
            done.add(Cell(r["task"], r["model"], r["mode"], r["trial"]).key)
        except (json.JSONDecodeError, KeyError):
            continue
    return done


def _find_result_json(cell_jobs_dir: Path) -> Optional[Path]:
    candidates = list(cell_jobs_dir.glob("*/*/result.json"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _run_cell(
    cell: Cell, out: Path, agent: str, sandbox: str, state: MatrixState
) -> CellResult:
    state.mark_running(cell)
    cell_jobs_dir = out / "cells" / cell.safe_name
    cell_jobs_dir.mkdir(parents=True, exist_ok=True)
    log_path = out / "logs" / f"{cell.safe_name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "uv", "run", "aip-skillbench", "eval",
        "--task", cell.task,
        "--model", cell.model,
        "--mode", cell.mode,
        "--agent", agent,
        "--sandbox", sandbox,
        "--concurrency", "1",
        "--jobs-dir", str(cell_jobs_dir),
    ]
    started_at = datetime.now().isoformat()
    with open(log_path, "w") as logf:
        logf.write("$ " + " ".join(cmd) + "\n\n")
        logf.flush()
        proc = subprocess.run(cmd, cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT)
    finished_at = datetime.now().isoformat()

    rj_path = _find_result_json(cell_jobs_dir)
    reward: Optional[float] = None
    n_tool_calls: Optional[int] = None
    wall_clock: Optional[float] = None
    error: Optional[str] = None
    trial_dir: Optional[str] = None

    if rj_path is not None:
        trial_dir = str(rj_path.parent)
        try:
            rj = json.loads(rj_path.read_text())
            r = rj.get("rewards")
            if isinstance(r, dict):
                reward = r.get("reward")
            n_tool_calls = rj.get("n_tool_calls")
            wall_clock = (rj.get("timing") or {}).get("total")
            error = rj.get("error")
        except (json.JSONDecodeError, OSError) as e:
            error = f"could not parse result.json: {e}"
    else:
        error = f"no result.json found under {cell_jobs_dir} (rc={proc.returncode})"

    if error:
        status = "error"
    elif reward is not None and reward >= 1.0:
        status = "pass"
    else:
        status = "fail"

    return CellResult(
        task=cell.task,
        model=cell.model,
        mode=cell.mode,
        trial=cell.trial,
        status=status,
        reward=reward,
        n_tool_calls=n_tool_calls,
        wall_clock=wall_clock,
        error=error,
        jobs_dir=str(cell_jobs_dir),
        trial_dir=trial_dir,
        started_at=started_at,
        finished_at=finished_at,
        subprocess_rc=proc.returncode,
    )


def _render(state: MatrixState) -> Group:
    n_total = len(state.cells)
    n_done = sum(1 for s in state.status.values() if s in {"pass", "fail", "error"})
    n_pass = sum(1 for s in state.status.values() if s == "pass")
    n_run = sum(1 for s in state.status.values() if s == "running")
    elapsed = time.time() - state.started_at
    rate = (n_pass / n_done * 100) if n_done else 0.0
    header = Text.from_markup(
        f"[bold]aip-skillbench run-matrix[/]  "
        f"cells {n_done}/{n_total} done ({n_run} running)  "
        f"pass {n_pass} ({rate:.1f}%)  elapsed {elapsed / 60:.1f}m"
    )

    matrix = Table(title="Trials", show_header=True, header_style="bold")
    matrix.add_column("task")
    matrix.add_column("model")
    for mode in state.modes:
        matrix.add_column(MODE_LABEL[mode], justify="center")

    for task in state.tasks:
        for model in state.models:
            row = [task, model]
            for mode in state.modes:
                glyphs: list[str] = []
                for trial in range(state.trials):
                    s = state.status.get(Cell(task, model, mode.value, trial).key, "pending")
                    glyphs.append(
                        {
                            "pending": SYM_PENDING,
                            "running": f"[yellow]{SYM_RUNNING}[/]",
                            "pass": f"[green]{SYM_PASS}[/]",
                            "fail": f"[red]{SYM_FAIL}[/]",
                            "error": f"[magenta]{SYM_ERROR}[/]",
                        }[s]
                    )
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


def run_matrix(
    tasks: list[str],
    models: list[str],
    modes: list[Mode],
    trials: int,
    concurrency: int,
    out: Path,
    agent: str,
    sandbox: str,
    yes: bool,
    force: bool,
    shuffle: bool,
) -> int:
    if not tasks:
        raise typer.BadParameter("no tasks specified (use --task ... or --config)")
    if not models:
        raise typer.BadParameter("no models specified (use --model ... or --config)")
    if not modes:
        modes = list(ALL_MODES)
    if trials < 1:
        raise typer.BadParameter(f"--trials must be >= 1 (got {trials})")
    if concurrency < 1:
        raise typer.BadParameter(f"--concurrency must be >= 1 (got {concurrency})")

    _validate_tasks(tasks)
    _validate_generated_skills(tasks, modes)
    _validate_api_key(agent)

    cells = _build_cells(tasks, models, modes, trials)
    if shuffle:
        random.shuffle(cells)

    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "summary.jsonl"
    csv_path = out / "summary.csv"
    status_path = out / "status.json"
    done = set() if force else _load_done(summary_path)
    pending = [c for c in cells if c.key not in done]

    typer.echo(f"Campaign: {out}")
    typer.echo(f"  tasks       ({len(tasks)}): {', '.join(tasks)}")
    typer.echo(f"  models      ({len(models)}): {', '.join(models)}")
    typer.echo(f"  modes       ({len(modes)}): {', '.join(m.value for m in modes)}")
    typer.echo(f"  trials:      {trials}")
    typer.echo(
        f"  total cells: {len(cells)}   already done: {len(done)}   to run: {len(pending)}"
    )
    typer.echo(f"  concurrency: {concurrency}   agent: {agent}   sandbox: {sandbox}")
    if not pending:
        typer.echo("Nothing to do.")
        return 0
    if not yes:
        typer.echo("\nStarting in 5s — Ctrl-C to abort.")
        for i in range(5, 0, -1):
            typer.echo(f"  {i}…", nl=False)
            time.sleep(1)
        typer.echo()

    (out / "campaign.json").write_text(
        json.dumps(
            {
                "started_at": datetime.now().isoformat(),
                "tasks": tasks,
                "models": models,
                "modes": [m.value for m in modes],
                "trials": trials,
                "concurrency": concurrency,
                "agent": agent,
                "sandbox": sandbox,
                "total_cells": len(cells),
                "already_done_at_start": len(done),
                "to_run": len(pending),
                "shuffle": shuffle,
            },
            indent=2,
        )
    )

    state = MatrixState(
        cells=cells,
        modes=modes,
        models=models,
        tasks=tasks,
        trials=trials,
        summary_path=summary_path,
        csv_path=csv_path,
        status_path=status_path,
    )
    state.preload()

    console = Console()
    with Live(_render(state), refresh_per_second=2, console=console) as live:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = {ex.submit(_run_cell, c, out, agent, sandbox, state): c for c in pending}
            try:
                for fut in concurrent.futures.as_completed(futures):
                    cell = futures[fut]
                    try:
                        result = fut.result()
                    except Exception as e:
                        result = CellResult(
                            task=cell.task, model=cell.model, mode=cell.mode, trial=cell.trial,
                            status="error", reward=None, n_tool_calls=None, wall_clock=None,
                            error=f"worker exception: {e!r}",
                            jobs_dir=str(out / "cells" / cell.safe_name),
                            trial_dir=None,
                            started_at="", finished_at=datetime.now().isoformat(),
                            subprocess_rc=-1,
                        )
                    state.mark_done(cell, result)
                    live.update(_render(state))
            except KeyboardInterrupt:
                console.print("[red]Interrupted — cancelling pending cells…[/]")
                for f in futures:
                    f.cancel()
                raise

    n_pass = sum(1 for r in state.results.values() if r.status == "pass")
    n_fail = sum(1 for r in state.results.values() if r.status == "fail")
    n_err = sum(1 for r in state.results.values() if r.status == "error")
    typer.echo(
        f"\nDone. pass={n_pass} fail={n_fail} error={n_err}  |  summary: {summary_path}"
    )
    return 1 if n_err else 0
