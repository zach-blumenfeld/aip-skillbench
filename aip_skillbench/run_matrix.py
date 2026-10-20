"""run-matrix: run a (task × model × scenario × trial) eval matrix concurrently with live progress.

A scenario is a campaign row: a solver mode plus, for the `skill` and `aip-runtime`
modes, the compile variant whose pack the container gets, and whether the memory nudge
is written. Cells are keyed by scenario name (docs/aip-version-ablation-benchmark.md).
"""

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

from aip_skillbench._aip import VARIANTS, read_refs, skill_dirs, validate_packs

ROOT = Path(__file__).resolve().parents[1]
VENDOR_SKILLSBENCH = ROOT / "vendor" / "skillsbench"
GENERATED_SKILLS = ROOT / "generated-skills"


class Mode(str, Enum):
    """Kept in sync with cli.Mode."""
    noskill = "noskill"
    human_curated = "human-curated"
    selfgen_skill_creator = "selfgen-skill-creator"
    skill = "skill"
    aip_runtime = "aip-runtime"


VARIANT_MODES = (Mode.skill, Mode.aip_runtime)

AGENT_KEY_ENV = {
    "claude-agent-acp": "ANTHROPIC_API_KEY",
    "codex-acp": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

SYM_PENDING = "▢"
SYM_RUNNING = "⟳"
SYM_PASS = "✓"
SYM_FAIL = "✗"
SYM_ERROR = "·"


@dataclass(frozen=True)
class Scenario:
    name: str
    mode: str
    variant: Optional[str] = None
    nudge: Optional[bool] = None  # None = the mode's default (skill: off, aip-runtime: on)

    @property
    def nudge_effective(self) -> bool:
        if self.nudge is not None:
            return self.nudge
        return self.mode == Mode.aip_runtime.value

    def as_dict(self) -> dict:
        return {"name": self.name, "mode": self.mode, "variant": self.variant, "nudge": self.nudge_effective}

    @classmethod
    def parse(cls, item: object) -> Scenario:
        """A config entry: a mode name (shorthand for a scenario without a variant) or a
        mapping {name, mode, variant?, nudge?}."""
        if isinstance(item, str):
            mode = Mode(item)
            if mode in VARIANT_MODES:
                raise typer.BadParameter(f"mode {mode.value} needs a variant: write it as a scenario mapping")
            return cls(name=mode.value, mode=mode.value)
        if not isinstance(item, dict) or "mode" not in item:
            raise typer.BadParameter(f"scenario must be a mode name or a mapping with `mode`: {item!r}")
        mode = Mode(item["mode"])
        variant = item.get("variant")
        if mode in VARIANT_MODES and not variant:
            raise typer.BadParameter(f"scenario {item.get('name', mode.value)!r}: mode {mode.value} needs `variant`")
        if mode not in VARIANT_MODES and variant:
            raise typer.BadParameter(f"scenario {item.get('name', mode.value)!r}: mode {mode.value} takes no variant")
        if variant and variant not in VARIANTS:
            raise typer.BadParameter(f"scenario {item.get('name')!r}: unknown variant {variant!r}; one of {', '.join(VARIANTS)}")
        if mode is Mode.aip_runtime and not VARIANTS[variant].has_runtime:
            raise typer.BadParameter(f"scenario {item.get('name')!r}: variant {variant} has no runtime; aip-runtime needs one of "
                                     + ", ".join(n for n, v in VARIANTS.items() if v.has_runtime))
        nudge = item.get("nudge")
        if nudge is not None and not isinstance(nudge, bool):
            raise typer.BadParameter(f"scenario {item.get('name')!r}: `nudge` must be true or false")
        if nudge and mode not in VARIANT_MODES:
            raise typer.BadParameter(f"scenario {item.get('name')!r}: `nudge` applies to skill and aip-runtime only")
        name = item.get("name") or (f"{mode.value}:{variant}" if variant else mode.value)
        return cls(name=str(name), mode=mode.value, variant=variant, nudge=nudge)


def parse_scenarios(items: list[object]) -> list[Scenario]:
    scenarios = [Scenario.parse(i) for i in items]
    names = [s.name for s in scenarios]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise typer.BadParameter(f"duplicate scenario name(s): {dupes}")
    return scenarios


@dataclass
class Cell:
    task: str
    model: str
    scenario: str
    trial: int

    @property
    def key(self) -> str:
        return f"{self.task}|{self.model}|{self.scenario}|t{self.trial}"

    @property
    def safe_name(self) -> str:
        return f"{self.task}__{self.model}__{self.scenario}__t{self.trial}"


@dataclass
class CellResult:
    task: str
    model: str
    scenario: str
    mode: str
    variant: Optional[str]
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
        scenarios: list[Scenario],
        models: list[str],
        tasks: list[str],
        trials: int,
        summary_path: Path,
        csv_path: Path,
        status_path: Path,
    ) -> None:
        self.cells = cells
        self.scenarios = scenarios
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
                key = Cell(cr.task, cr.model, cr.scenario, cr.trial).key
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


def _validate_generated_skills(tasks: list[str], scenarios: list[Scenario]) -> None:
    """Every (task, variant) a scenario needs has a pack that passes the variant's gate,
    before a campaign spends money on it; aip-runtime needs exactly one skill folder."""
    needs: dict[str, bool] = {}  # variant -> needs a single folder (runtime)
    for s in scenarios:
        if s.variant:
            needs[s.variant] = needs.get(s.variant, False) or s.mode == Mode.aip_runtime.value
    missing: list[str] = []
    failures: list[str] = []
    for vname, single in needs.items():
        v = VARIANTS[vname]
        for task in tasks:
            root = v.pack_root(task)
            dirs = skill_dirs(root)
            if not dirs:
                missing.append(f"{root}  (aip-skillbench convert --task {task} --variant {vname})")
                continue
            if single and len(dirs) != 1:
                failures.append(f"{root}: aip-runtime publishes one procedure per task, found {len(dirs)} skill folders")
            failures.extend(validate_packs(v, root))
    if missing:
        raise typer.BadParameter("Missing packs:\n  - " + "\n  - ".join(missing))
    if failures:
        raise typer.BadParameter(
            "Packs that fail their variant's gate (regenerate with `aip-skillbench convert --force`):\n  - "
            + "\n  - ".join(failures)
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
    tasks: list[str], models: list[str], scenarios: list[Scenario], trials: int
) -> list[Cell]:
    cells: list[Cell] = []
    for t in tasks:
        for m in models:
            for s in scenarios:
                for trial in range(trials):
                    cells.append(Cell(task=t, model=m, scenario=s.name, trial=trial))
    return cells


def _load_done(summary_path: Path) -> set[str]:
    done: set[str] = set()
    if not summary_path.exists():
        return done
    for line in summary_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            done.add(Cell(r["task"], r["model"], r["scenario"], r["trial"]).key)
        except (json.JSONDecodeError, KeyError):
            continue
    return done


def _find_result_json(cell_jobs_dir: Path) -> Optional[Path]:
    """Return the newest result.json under the cell's jobs dir, or None."""
    candidates = list(cell_jobs_dir.glob("**/result.json"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def eval_command(cell: Cell, scenario: Scenario, agent: str, sandbox: str, jobs_dir: Path,
                 decision_model: bool, agent_env: list[str] | None) -> list[str]:
    """The `aip-skillbench eval` invocation for one cell."""
    cmd = [
        "uv", "run", "aip-skillbench", "eval",
        "--task", cell.task,
        "--model", cell.model,
        "--mode", scenario.mode,
        "--agent", agent,
        "--sandbox", sandbox,
        "--concurrency", "1",
        "--jobs-dir", str(jobs_dir),
    ]
    if scenario.variant:
        cmd += ["--variant", scenario.variant]
    if scenario.mode == Mode.skill.value:
        cmd.append("--nudge" if scenario.nudge_effective else "--no-nudge")
    elif scenario.mode == Mode.aip_runtime.value:
        cmd.append("--aip-nudge" if scenario.nudge_effective else "--no-aip-nudge")
        if decision_model:
            cmd.append("--decision-model")
    for kv in agent_env or []:
        cmd += ["--agent-env", kv]
    return cmd


def _run_cell(
    cell: Cell, scenario: Scenario, out: Path, agent: str, sandbox: str, state: MatrixState,
    decision_model: bool = False,
    agent_env: list[str] | None = None,
) -> CellResult:
    state.mark_running(cell)
    cell_jobs_dir = out / "cells" / cell.safe_name
    cell_jobs_dir.mkdir(parents=True, exist_ok=True)
    log_path = out / "logs" / f"{cell.safe_name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = eval_command(cell, scenario, agent, sandbox, cell_jobs_dir, decision_model, agent_env)
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
        scenario=scenario.name,
        mode=scenario.mode,
        variant=scenario.variant,
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
    for s in state.scenarios:
        matrix.add_column(s.name, justify="center")

    for task in state.tasks:
        for model in state.models:
            row = [task, model]
            for s in state.scenarios:
                glyphs: list[str] = []
                for trial in range(state.trials):
                    st = state.status.get(Cell(task, model, s.name, trial).key, "pending")
                    glyphs.append(
                        {
                            "pending": SYM_PENDING,
                            "running": f"[yellow]{SYM_RUNNING}[/]",
                            "pass": f"[green]{SYM_PASS}[/]",
                            "fail": f"[red]{SYM_FAIL}[/]",
                            "error": f"[magenta]{SYM_ERROR}[/]",
                        }[st]
                    )
                row.append(" ".join(glyphs))
            matrix.add_row(*row)

    summary = Table(title="Per-scenario aggregates", show_header=True, header_style="bold")
    summary.add_column("scenario")
    summary.add_column("mode")
    summary.add_column("variant")
    summary.add_column("n", justify="right")
    summary.add_column("pass", justify="right")
    summary.add_column("pass%", justify="right")
    summary.add_column("mean reward", justify="right")
    summary.add_column("mean tool calls", justify="right")
    summary.add_column("mean wall (s)", justify="right")
    for s in state.scenarios:
        rs = [r for r in state.results.values() if r.scenario == s.name]
        n = len(rs)
        passes = sum(1 for r in rs if r.status == "pass")
        rewards = [r.reward for r in rs if r.reward is not None]
        tcs = [r.n_tool_calls for r in rs if r.n_tool_calls is not None]
        wcs = [r.wall_clock for r in rs if r.wall_clock is not None]
        summary.add_row(
            s.name,
            s.mode,
            s.variant or "—",
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
    scenarios: list[Scenario],
    trials: int,
    concurrency: int,
    out: Path,
    agent: str,
    sandbox: str,
    yes: bool,
    force: bool,
    shuffle: bool,
    decision_model: bool = False,
    agent_env: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    if not tasks:
        raise typer.BadParameter("no tasks specified (use --task ... or --config)")
    if not models:
        raise typer.BadParameter("no models specified (use --model ... or --config)")
    if not scenarios:
        raise typer.BadParameter("no scenarios specified (config `scenarios:`/`modes:` or --mode ...)")
    if trials < 1:
        raise typer.BadParameter(f"--trials must be >= 1 (got {trials})")
    if concurrency < 1:
        raise typer.BadParameter(f"--concurrency must be >= 1 (got {concurrency})")

    _validate_tasks(tasks)
    cells = _build_cells(tasks, models, scenarios, trials)
    if shuffle:
        random.shuffle(cells)
    summary_path = out / "summary.jsonl"
    csv_path = out / "summary.csv"
    status_path = out / "status.json"
    done = set() if force else _load_done(summary_path)
    pending = [c for c in cells if c.key not in done]

    typer.echo(f"Campaign: {out}")
    typer.echo(f"  tasks       ({len(tasks)}): {', '.join(tasks)}")
    typer.echo(f"  models      ({len(models)}): {', '.join(models)}")
    typer.echo(f"  scenarios   ({len(scenarios)}):")
    for s in scenarios:
        typer.echo(f"    {s.name:<14} mode={s.mode:<22} variant={s.variant or '-':<10} nudge={'on' if s.nudge_effective else 'off'}")
    typer.echo(f"  trials:      {trials}")
    typer.echo(
        f"  total cells: {len(cells)}   already done: {len(done)}   to run: {len(pending)}"
    )
    typer.echo(f"  concurrency: {concurrency}   agent: {agent}   sandbox: {sandbox}   decision_model: {decision_model}")
    if dry_run:
        typer.echo("\nDry run: packs are not checked and nothing is spent. First cell's command:")
        if pending:
            c = pending[0]
            sc = next(s for s in scenarios if s.name == c.scenario)
            typer.echo("  " + " ".join(eval_command(c, sc, agent, sandbox, out / "cells" / c.safe_name, decision_model, agent_env)))
        return 0

    _validate_generated_skills(tasks, scenarios)
    _validate_api_key(agent)
    out.mkdir(parents=True, exist_ok=True)
    if not pending:
        typer.echo("Nothing to do.")
        return 0
    if not yes:
        typer.echo("\nStarting in 5s — Ctrl-C to abort.")
        for i in range(5, 0, -1):
            typer.echo(f"  {i}…", nl=False)
            time.sleep(1)
        typer.echo()

    refs = read_refs()
    (out / "campaign.json").write_text(
        json.dumps(
            {
                "started_at": datetime.now().isoformat(),
                "tasks": tasks,
                "models": models,
                "scenarios": [s.as_dict() for s in scenarios],
                "trials": trials,
                "concurrency": concurrency,
                "agent": agent,
                "sandbox": sandbox,
                "decision_model": decision_model,
                "agent_env": agent_env or [],
                "refs": {name: refs.get(name) for name in sorted({s.variant for s in scenarios if s.variant})},
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
        scenarios=scenarios,
        models=models,
        tasks=tasks,
        trials=trials,
        summary_path=summary_path,
        csv_path=csv_path,
        status_path=status_path,
    )
    state.preload()
    by_name = {s.name: s for s in scenarios}

    console = Console()
    with Live(_render(state), refresh_per_second=2, console=console) as live:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = {
                ex.submit(_run_cell, c, by_name[c.scenario], out, agent, sandbox, state, decision_model, agent_env): c
                for c in pending
            }
            try:
                for fut in concurrent.futures.as_completed(futures):
                    cell = futures[fut]
                    try:
                        result = fut.result()
                    except Exception as e:
                        sc = by_name[cell.scenario]
                        result = CellResult(
                            task=cell.task, model=cell.model, scenario=cell.scenario,
                            mode=sc.mode, variant=sc.variant, trial=cell.trial,
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


def _load_campaign_state(out: Path) -> MatrixState:
    """Rebuild a MatrixState for an existing campaign dir from campaign.json + summary.jsonl.

    A cell whose `cells/<name>/` dir exists but has no summary row is shown as running:
    `_run_cell` creates that dir first thing and the row is written only when it ends.
    """
    campaign = json.loads((out / "campaign.json").read_text())
    tasks = list(campaign["tasks"])
    models = list(campaign["models"])
    scenarios = parse_scenarios(campaign["scenarios"])
    trials = int(campaign["trials"])
    cells = _build_cells(tasks, models, scenarios, trials)
    state = MatrixState(
        cells=cells, scenarios=scenarios, models=models, tasks=tasks, trials=trials,
        summary_path=out / "summary.jsonl", csv_path=out / "summary.csv",
        status_path=out / "status.json",
    )
    try:
        state.started_at = datetime.fromisoformat(campaign["started_at"]).timestamp()
    except (KeyError, ValueError):
        pass
    state.preload()
    for c in cells:
        if state.status[c.key] == "pending" and (out / "cells" / c.safe_name).is_dir():
            state.status[c.key] = "running"
    return state


def matrix_view(out: Path, watch: bool, interval: float) -> int:
    """Print (or keep refreshing) the run-matrix view for a campaign dir, from its files."""
    if not (out / "campaign.json").exists():
        typer.echo(f"not a campaign dir (no campaign.json): {out}", err=True)
        return 2
    from rich.console import Console
    from rich.live import Live

    console = Console()
    if not watch:
        console.print(_render(_load_campaign_state(out)))
        return 0
    with Live(_render(_load_campaign_state(out)), refresh_per_second=2, console=console) as live:
        try:
            while True:
                time.sleep(interval)
                live.update(_render(_load_campaign_state(out)))
        except KeyboardInterrupt:
            pass
    return 0
