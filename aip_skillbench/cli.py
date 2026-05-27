"""aip-skillbench CLI — five-mode evaluation harness over SkillsBench tasks."""

from __future__ import annotations

import shutil
import subprocess
from enum import Enum
from pathlib import Path

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


def _run_claude(prompt: str, model: str, add_dirs: list[Path]) -> None:
    """Shell out to `claude -p` with AIP discoverable from cwd."""
    cmd = ["claude", "-p", prompt, "--model", model]
    for d in add_dirs:
        cmd += ["--add-dir", str(d)]
    cmd += ["--dangerously-skip-permissions"]
    typer.echo(
        "$ claude -p <…prompt elided…> --model " + model
        + "".join(f" --add-dir {d}" for d in add_dirs)
        + " --dangerously-skip-permissions"
    )
    rc = subprocess.call(cmd, cwd=ROOT)
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

into an AIP-compliant skill at:

    {dst}

Requirements:
1. Read {src}/SKILL.md. Produce {dst}/SKILL.md in AIP format per the aip
   skill's specification (schema-validated YAML body, AIP frontmatter).
2. Copy every other file under {src}/ (scripts/, references/, assets/, etc.)
   verbatim into {dst}/, preserving the directory structure.
3. Do not change the skill's `name:` frontmatter field — the task's mounted
   skill name must match.
4. Validate the result against the AIP schema before writing.

Write nothing outside {dst}/. Do not modify {src}/."""


_PROMPT_FROM_INSTRUCTION = """\
Use the `aip` skill in ./.claude/skills/aip/ to author one or more
AIP-compliant Agent Skills that would help a downstream agent solve the
task described in:

    {instruction_path}

Write the skill pack(s) into:

    {dst_root}/<skill-name>/SKILL.md (plus scripts/, references/, assets/ as needed)

Requirements:
1. Read ONLY {instruction_path}. Do not inspect or copy from any existing
   skills directory under the task — this mode authors from the
   instruction alone, not from a human-written skill.
2. Author the reusable procedural knowledge an agent needs to solve this
   task type. Pick concise `<skill-name>` value(s); the directory name
   under {dst_root}/ must match the skill's `name:` frontmatter.
3. Include any scripts or assets that would help the solver — this skill
   is the only thing the solver will have, besides the task environment.
4. Every produced SKILL.md must validate against the AIP schema. Run
   `uv run .claude/skills/aip/scripts/validate.py <skill-dir>` before
   considering the work complete.

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
    names and copying scripts verbatim. Output: `generated-skills/<task>/aip-from-curated/<skill>/`.

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
    pattern: str = typer.Option("*", help="Glob filter on task names."),
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


@app.command()
def reward(jobs_subdir: Path) -> None:
    """Print the reward(s) under a jobs/ output directory."""
    if not jobs_subdir.exists():
        raise typer.BadParameter(f"not found: {jobs_subdir}")
    for r in sorted(jobs_subdir.glob("*/verifier/reward.txt")):
        typer.echo(f"{r.parent.parent.name}: {r.read_text().strip()}")


if __name__ == "__main__":
    app()
