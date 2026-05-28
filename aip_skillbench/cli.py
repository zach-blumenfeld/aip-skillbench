"""aip-skillbench CLI — five-mode evaluation harness over SkillsBench tasks."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import typer

ROOT = Path(__file__).resolve().parents[1]
VENDOR_SKILLSBENCH = ROOT / "vendor" / "skillsbench"
VENDOR_SKILL_CREATOR = VENDOR_SKILLSBENCH / ".agents" / "skills" / "skill-creator"
AIP_DIR = ROOT / ".claude" / "skills" / "aip"
AIP_REMOTE = "git@github.com:zach-blumenfeld/aip.git"
GENERATED_SKILLS = ROOT / "generated-skills"
JOBS_DIR = ROOT / "jobs"

app = typer.Typer(add_completion=False, no_args_is_help=True)


class Mode(str, Enum):
    noskill = "noskill"
    human_curated = "human-curated"
    selfgen_skill_creator = "selfgen-skill-creator"
    aip_from_instruction = "aip-from-instruction"
    aip_from_curated = "aip-from-curated"


class ConvertFrom(str, Enum):
    instruction = "instruction"
    curated = "curated"


def _task_dir(task: str) -> Path:
    path = VENDOR_SKILLSBENCH / "tasks" / task
    if not path.exists():
        raise typer.BadParameter(f"task not found: {path}")
    return path


def _curated_skills_dir(task: str) -> Path:
    return _task_dir(task) / "environment" / "skills"


def _generated_skills_dir(task: str, from_: ConvertFrom) -> Path:
    return GENERATED_SKILLS / task / f"aip-from-{from_.value}"


def _require_aip() -> Path:
    if not (AIP_DIR / "SKILL.md").exists():
        raise typer.BadParameter(
            f"AIP not installed at {AIP_DIR}. Run `aip-skillbench bootstrap` first."
        )
    return AIP_DIR


def _require_skill_creator() -> Path:
    if not (VENDOR_SKILL_CREATOR / "SKILL.md").exists():
        raise typer.BadParameter(
            f"skill-creator not found at {VENDOR_SKILL_CREATOR}. "
            "Run `git submodule update --init` to populate vendor/skillsbench."
        )
    return VENDOR_SKILL_CREATOR


def _bench(*args: str) -> int:
    """Invoke benchflow's `bench` CLI via our patched launcher.

    We can't `uv run bench` directly: that spawns a Python process that never
    imports aip_skillbench, so the benchflow monkey-patches in
    aip_skillbench._benchflow_patch wouldn't apply. Going through
    aip_skillbench._bench_launcher ensures the patches load first.
    """
    cmd = ["uv", "run", "python", "-m", "aip_skillbench._bench_launcher", *args]
    typer.echo("$ uv run bench " + " ".join(args))  # log the user-friendly form
    return subprocess.call(cmd)


def _read_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env parser — KEY=VALUE lines, ignores comments/blanks."""
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


def _run_claude(prompt: str, model: str, add_dirs: list[Path]) -> None:
    """Shell out to `claude -p` with AIP discoverable from cwd.

    Authoring bills against the `.env` ANTHROPIC_API_KEY when present, so it
    uses the same API account as eval (not whatever account `claude` is logged
    into). The .env value takes precedence over any inherited env var.
    """
    cmd = ["claude", "-p", prompt, "--model", model]
    for d in add_dirs:
        cmd += ["--add-dir", str(d)]
    cmd += ["--dangerously-skip-permissions"]

    env = os.environ.copy()
    key = _read_dotenv(ROOT / ".env").get("ANTHROPIC_API_KEY")
    key_src = "inherited env" if not key else ".env"
    if key:
        env["ANTHROPIC_API_KEY"] = key

    typer.echo(
        "$ claude -p <…prompt elided…> --model " + model
        + "".join(f" --add-dir {d}" for d in add_dirs)
        + f" --dangerously-skip-permissions   [ANTHROPIC_API_KEY: {key_src}]"
    )
    rc = subprocess.call(cmd, cwd=ROOT, env=env)
    if rc != 0:
        raise typer.Exit(rc)


@app.command()
def bootstrap(
    aip_ref: str = typer.Option("main", help="AIP branch/tag/SHA to clone."),
    force: bool = typer.Option(False, help="Re-clone if AIP already present."),
) -> None:
    """One-time setup: clone AIP into ./.claude/skills/aip (gitignored)."""
    if AIP_DIR.exists():
        if not force:
            typer.echo(f"AIP already at {AIP_DIR} (pass --force to re-clone).")
            raise typer.Exit(0)
        shutil.rmtree(AIP_DIR)

    AIP_DIR.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--depth", "1", "--branch", aip_ref, AIP_REMOTE, str(AIP_DIR)]
    typer.echo("$ " + " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        raise typer.Exit(rc)
    typer.echo(f"Installed AIP at {AIP_DIR}")


@app.command()
def eval(
    task: str = typer.Option(..., help="Task name under vendor/skillsbench/tasks/."),
    model: str = typer.Option(..., help="Model string, e.g. claude-haiku-4-5."),
    mode: Mode = typer.Option(Mode.noskill, case_sensitive=False),
    agent: str = typer.Option("claude-agent-acp", help="Agent name."),
    sandbox: str = typer.Option("docker", help="docker | daytona | modal."),
    concurrency: int = typer.Option(4),
    jobs_dir: Path = typer.Option(None, help="Override jobs/ output dir."),
) -> None:
    """Run one evaluation in one of the five modes."""
    task_dir = _task_dir(task)
    out = jobs_dir or (JOBS_DIR / f"{task}-{mode.value}-{model}")

    base = [
        "eval", "create",
        "--tasks-dir", str(task_dir),
        "--agent", agent,
        "--model", model,
        "--sandbox", sandbox,
        "--concurrency", str(concurrency),
        "--jobs-dir", str(out),
    ]

    if mode is Mode.noskill:
        extra: list[str] = []
    elif mode is Mode.human_curated:
        extra = ["--skills-dir", str(_curated_skills_dir(task))]
    elif mode is Mode.selfgen_skill_creator:
        # Pin skill-creator to the SkillsBench-vendored copy for reproducibility,
        # regardless of what's in the user's ~/.claude/skills/.
        extra = ["--skill-mode", "self-gen", "--skill-creator-dir", str(_require_skill_creator())]
    elif mode in (Mode.aip_from_instruction, Mode.aip_from_curated):
        from_ = (
            ConvertFrom.instruction if mode is Mode.aip_from_instruction
            else ConvertFrom.curated
        )
        conv = _generated_skills_dir(task, from_)
        if not conv.exists() or not any(conv.iterdir()):
            raise typer.BadParameter(
                f"No converted skills at {conv}. Run "
                f"`aip-skillbench convert --task {task} --from {from_.value}` first."
            )
        extra = ["--skills-dir", str(conv)]
    else:
        raise typer.BadParameter(f"unknown mode: {mode}")

    raise typer.Exit(_bench(*base, *extra))


_PROMPT_FROM_CURATED = """\
Use the `aip` skill in ./.claude/skills/aip/ to convert the curated Agent
Skill at:

    {src}

into an AIP skill at:

    {dst}

Requirements:
1. Read {src}/SKILL.md. Produce {dst}/SKILL.md in AIP format.
2. Read every other file under {src}/ (scripts/, references/, assets/, etc.) for context.
    Create scripts to mirror, copy verbatim into {dst}/, or alter as needed.
3. Do not change the skill's `name:` frontmatter field — the task's mounted
   skill name must match.
4. The skills you author should have all the specialized knowledge and procedures an agent needs to solve this
   task type autonomously.

Write nothing outside {dst}/. Do not modify {src}/."""


_PROMPT_FROM_INSTRUCTION = """\
Use the `aip` skill in ./.claude/skills/aip/ to author one or more
AIP Agent Skills so a downstream agent can solve the
task described in:

    {instruction_path}

Write the skill pack(s) into:

    {dst_root}/<skill-name>/SKILL.md (plus scripts/, references/, assets/ as needed)

Requirements:
1. Read ONLY {instruction_path}. DO NOT inspect or copy from any existing
   skills directory under the task — you must author from the
   instruction alone. 
2. The skills you author should have all the specialized knowledge and procedures an agent needs to solve this
   task type autonomously. Pick concise `<skill-name>` value(s); the directory name
   under {dst_root}/ must match the skill's `name:` frontmatter.

Write nothing outside {dst_root}/. Do not modify the task source."""


@app.command()
def convert(
    task: str = typer.Option(..., help="Task name under vendor/skillsbench/tasks/."),
    from_: ConvertFrom = typer.Option(
        ConvertFrom.curated,
        "--from",
        case_sensitive=False,
        help="Authoring input: 'curated' (existing skill) or 'instruction' (instruction.md only).",
    ),
    force: bool = typer.Option(False, help="Overwrite existing converted output."),
    author_model: str = typer.Option(
        "claude-opus-4-7",
        "--author-model",
        help="Model used to author. Per AIP spec, use the largest available frontier model.",
    ),
) -> None:
    """Produce an AIP skill pack for `task`, by Opus authoring offline.

    `--from curated` — convert each skill under
    `vendor/skillsbench/tasks/<task>/environment/skills/` to AIP, preserving
    names; supporting files (scripts/references) are reproduced, mirrored, or
    adapted as the authoring model sees fit. Output: `generated-skills/<task>/aip-from-curated/<skill>/`.

    `--from instruction` — author one or more AIP skills from
    `vendor/skillsbench/tasks/<task>/instruction.md` alone. Output:
    `generated-skills/<task>/aip-from-instruction/<skill>/`.
    """
    _require_aip()
    _task_dir(task)  # validate before we touch the filesystem
    dst_root = _generated_skills_dir(task, from_)
    if dst_root.exists() and not force:
        raise typer.BadParameter(f"already exists: {dst_root} (pass --force to overwrite)")
    if dst_root.exists():
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True)

    if from_ is ConvertFrom.curated:
        _convert_from_curated(task, dst_root, author_model)
    else:
        _convert_from_instruction(task, dst_root, author_model)


def _convert_from_curated(task: str, dst_root: Path, author_model: str) -> None:
    src_root = _curated_skills_dir(task)
    if not src_root.exists():
        raise typer.BadParameter(f"no curated skills at {src_root}")
    skills = [p for p in src_root.iterdir() if p.is_dir() and (p / "SKILL.md").exists()]
    if not skills:
        raise typer.BadParameter(f"no skill dirs (with SKILL.md) under {src_root}")
    typer.echo(f"Converting {len(skills)} curated skill(s) under task '{task}':")

    for src in skills:
        dst = dst_root / src.name
        typer.echo(f"\n→ {src.name}")
        _run_claude(
            _PROMPT_FROM_CURATED.format(src=src, dst=dst),
            model=author_model,
            add_dirs=[src, dst_root],
        )
        if not (dst / "SKILL.md").exists():
            typer.echo(f"  WARNING: {dst}/SKILL.md not produced by Claude.")
    typer.echo(f"\nWrote {len(skills)} skill(s) to {dst_root}")


def _convert_from_instruction(task: str, dst_root: Path, author_model: str) -> None:
    instruction_path = _task_dir(task) / "instruction.md"
    if not instruction_path.exists():
        raise typer.BadParameter(f"no instruction.md at {instruction_path}")
    typer.echo(f"Authoring AIP skill(s) for task '{task}' from instruction.md alone…")
    _run_claude(
        _PROMPT_FROM_INSTRUCTION.format(instruction_path=instruction_path, dst_root=dst_root),
        model=author_model,
        add_dirs=[instruction_path.parent, dst_root],
    )
    produced = [p for p in dst_root.iterdir() if p.is_dir() and (p / "SKILL.md").exists()]
    if not produced:
        typer.echo(f"WARNING: no SKILL.md files produced under {dst_root}")
    else:
        typer.echo(f"\nWrote {len(produced)} skill(s) to {dst_root}: {[p.name for p in produced]}")


class BatchFrom(str, Enum):
    instruction = "instruction"
    curated = "curated"
    both = "both"


def _discover_tasks(pattern: str) -> list[str]:
    tasks_dir = VENDOR_SKILLSBENCH / "tasks"
    return sorted(
        p.name for p in tasks_dir.glob(pattern)
        if p.is_dir() and (p / "instruction.md").exists()
    )


def _already_done(task: str, from_: ConvertFrom) -> bool:
    d = _generated_skills_dir(task, from_)
    if not d.exists():
        return False
    return any(child.is_dir() and (child / "SKILL.md").exists() for child in d.iterdir())


def _convert_one(task: str, from_value: str, author_model: str, force: bool) -> tuple[str, str, int, float, str]:
    """Run one `aip-skillbench convert` invocation as a subprocess. Returns (task, from, rc, secs, tail)."""
    import time
    cmd = [
        "uv", "run", "aip-skillbench", "convert",
        "--task", task, "--from", from_value,
        "--author-model", author_model,
    ]
    if force:
        cmd.append("--force")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    secs = time.time() - t0
    tail = (proc.stderr or proc.stdout).splitlines()[-1] if (proc.stderr or proc.stdout) else ""
    return task, from_value, proc.returncode, secs, tail[:140]


@app.command("batch-convert")
def batch_convert(
    from_: BatchFrom = typer.Option(
        BatchFrom.both, "--from", case_sensitive=False, help="Which mode(s) to author."
    ),
    concurrency: int = typer.Option(4, "--concurrency", "-j", help="Parallel claude calls."),
    force: bool = typer.Option(False, help="Re-author even if output exists."),
    pattern: str = typer.Option("*", help="Glob filter on task names. Ignored if --task is given."),
    tasks_explicit: list[str] = typer.Option(
        [], "--task", help="Explicit task name; repeatable. If any --task is given, --pattern is ignored."
    ),
    limit: int = typer.Option(0, help="Cap number of conversions (0 = all)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the 5s confirm pause."),
    author_model: str = typer.Option("claude-opus-4-7", "--author-model"),
) -> None:
    """Author AIP skills for many tasks at once. Skips already-converted output unless --force."""
    import concurrent.futures
    import time

    _require_aip()

    froms: list[ConvertFrom] = (
        [ConvertFrom.instruction, ConvertFrom.curated]
        if from_ is BatchFrom.both
        else [ConvertFrom(from_.value)]
    )

    if tasks_explicit:
        missing = [t for t in tasks_explicit if not (VENDOR_SKILLSBENCH / "tasks" / t / "instruction.md").exists()]
        if missing:
            raise typer.BadParameter(f"task(s) not found: {missing}")
        tasks = sorted(set(tasks_explicit))
    else:
        tasks = _discover_tasks(pattern)
    work: list[tuple[str, ConvertFrom]] = []
    skipped = 0
    for task in tasks:
        for f in froms:
            if not force and _already_done(task, f):
                skipped += 1
                continue
            work.append((task, f))
    if limit > 0:
        work = work[:limit]

    typer.echo(f"Batch convert: {len(tasks)} tasks × {len(froms)} mode(s) = {len(tasks) * len(froms)} cells")
    typer.echo(f"  to author: {len(work)}   skipped (already done): {skipped}")
    typer.echo(f"  concurrency: {concurrency}   author model: {author_model}")
    typer.echo(f"  est. cost (very rough): ~${0.5 * len(work):.0f}   est. wall clock: ~{2 * len(work) / max(concurrency,1):.0f} min")
    if not work:
        typer.echo("Nothing to do.")
        raise typer.Exit(0)

    if not yes:
        typer.echo("\nStarting in 5s — Ctrl-C to abort.")
        for i in range(5, 0, -1):
            typer.echo(f"  {i}…", nl=False)
            time.sleep(1)
        typer.echo()

    t_start = time.time()
    done = failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {
            ex.submit(_convert_one, task, f.value, author_model, force): (task, f.value)
            for task, f in work
        }
        total = len(futures)
        for fut in concurrent.futures.as_completed(futures):
            task, fv, rc, secs, tail = fut.result()
            done += 1
            status = "OK" if rc == 0 else f"FAIL(rc={rc})"
            if rc != 0:
                failed += 1
            typer.echo(
                f"[{done:>3}/{total}] {status:9s} {task:40s} --from {fv:11s} "
                f"({secs:5.1f}s) {tail}"
            )
    elapsed = time.time() - t_start
    typer.echo()
    typer.echo(f"Done in {elapsed/60:.1f} min. {done - failed} succeeded, {failed} failed.")
    if failed:
        raise typer.Exit(1)


@app.command("run-matrix")
def run_matrix_cmd(
    tasks_explicit: list[str] = typer.Option(
        [], "--task", help="Repeatable. Task name under vendor/skillsbench/tasks/."
    ),
    models_explicit: list[str] = typer.Option(
        [], "--model", help="Repeatable. Model string (agent-specific)."
    ),
    modes_explicit: list[Mode] = typer.Option(
        [], "--mode", case_sensitive=False, help="Repeatable. Default: all 5 modes."
    ),
    trials: Optional[int] = typer.Option(
        None, "--trials", help="Trials per (task, model, mode). Default 1."
    ),
    concurrency: Optional[int] = typer.Option(
        None, "--concurrency", "-j", help="Max concurrent cells. Default 4."
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", help="YAML config (CLI flags override matching keys)."
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Campaign output dir. Default: runs/<timestamp>/."
    ),
    agent: Optional[str] = typer.Option(None, "--agent", help="Solver agent name."),
    sandbox: Optional[str] = typer.Option(None, "--sandbox", help="docker | daytona | modal."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the 5s confirm pause."),
    force: bool = typer.Option(False, "--force", help="Re-run cells already in summary.jsonl."),
    shuffle: bool = typer.Option(False, "--shuffle", help="Randomize cell execution order."),
) -> None:
    """Run a (task × model × mode × trial) eval matrix concurrently with live progress."""
    from aip_skillbench.run_matrix import ALL_MODES, run_matrix

    cfg: dict = {}
    if config:
        import yaml
        if not config.exists():
            raise typer.BadParameter(f"config not found: {config}")
        cfg = yaml.safe_load(config.read_text()) or {}

    tasks_resolved = list(tasks_explicit) or list(cfg.get("tasks", []))
    models_resolved = list(models_explicit) or list(cfg.get("models", []))
    if modes_explicit:
        modes_resolved = list(modes_explicit)
    elif "modes" in cfg:
        modes_resolved = [Mode(m) for m in cfg["modes"]]
    else:
        modes_resolved = list(ALL_MODES)
    trials_resolved = trials if trials is not None else int(cfg.get("trials", 1))
    concurrency_resolved = (
        concurrency if concurrency is not None else int(cfg.get("concurrency", 4))
    )
    agent_resolved = agent if agent is not None else cfg.get("agent", "claude-agent-acp")
    sandbox_resolved = sandbox if sandbox is not None else cfg.get("sandbox", "docker")
    out_resolved = out or (ROOT / "runs" / datetime.now().strftime("%Y-%m-%d__%H-%M-%S"))

    rc = run_matrix(
        tasks=tasks_resolved,
        models=models_resolved,
        modes=modes_resolved,
        trials=trials_resolved,
        concurrency=concurrency_resolved,
        out=out_resolved,
        agent=agent_resolved,
        sandbox=sandbox_resolved,
        yes=yes,
        force=force,
        shuffle=shuffle,
    )
    raise typer.Exit(rc)


@app.command()
def reward(jobs_subdir: Path) -> None:
    """Print the reward(s) under a jobs/ output directory."""
    if not jobs_subdir.exists():
        raise typer.BadParameter(f"not found: {jobs_subdir}")
    for r in sorted(jobs_subdir.glob("*/verifier/reward.txt")):
        typer.echo(f"{r.parent.parent.name}: {r.read_text().strip()}")


if __name__ == "__main__":
    app()
