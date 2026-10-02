"""aip-skillbench CLI — five-mode evaluation harness over SkillsBench tasks."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import typer

from aip_skillbench._aip import (
    AIP_BUILD_DIR,
    AIP_DEFAULT_REF,
    AIP_DIR,
    AIP_REF_FILE,
    AIP_REMOTE,
    GENERATED_SKILLS,
    NUDGE_ENV,
    ROOT,
    WHEEL_ENV,
    aip_wheel,
    format_version,
    validate_packs,
)

VENDOR_SKILLSBENCH = ROOT / "vendor" / "skillsbench"
VENDOR_SKILL_CREATOR = VENDOR_SKILLSBENCH / ".agents" / "skills" / "skill-creator"
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


def _bench(*args: str, env: dict[str, str] | None = None) -> int:
    """Invoke benchflow's `bench` CLI via our patched launcher.

    We can't `uv run bench` directly: that spawns a Python process that never
    imports aip_skillbench, so the benchflow monkey-patches in
    aip_skillbench._benchflow_patch wouldn't apply. Going through
    aip_skillbench._bench_launcher ensures the patches load first.
    """
    cmd = ["uv", "run", "python", "-m", "aip_skillbench._bench_launcher", *args]
    shown = [a if not a.startswith("TYPESAFE_API_KEY=") else "TYPESAFE_API_KEY=…" for a in args]
    typer.echo("$ uv run bench " + " ".join(shown))  # log the user-friendly form
    return subprocess.call(cmd, env={**os.environ, **(env or {})})


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


def _author_api_key() -> tuple[str | None, str]:
    """Authoring bills against the `.env` ANTHROPIC_API_KEY when present, so it uses
    the same API account as eval (not whatever account `claude` is logged into)."""
    key = _read_dotenv(ROOT / ".env").get("ANTHROPIC_API_KEY")
    return key, (".env" if key else "inherited env")

@app.command()
def bootstrap(
    aip_ref: str = typer.Option(
        AIP_DEFAULT_REF, help="AIP branch or tag to clone (the 0.4a0 format lives on `aip-s1`)."
    ),
    aip_sha: Optional[str] = typer.Option(
        None, "--aip-sha", help="Commit to check out after cloning, for an exact reproduction."
    ),
    force: bool = typer.Option(False, help="Re-clone if AIP already present."),
    install_cli: bool = typer.Option(
        True, "--install-cli/--no-install-cli",
        help="Install the `aip` CLI on the host (uv tool) and build the wheel trial containers get.",
    ),
) -> None:
    """One-time setup: clone AIP into ./.claude/skills/aip (gitignored), install the
    host `aip` CLI, build the wheel for trial containers, and record the exact ref.

    The 0.4a0 authoring checklist runs `aip validate` and functional-tests skills
    with `aip run`, so the CLI has to be on the host PATH for `convert`. Trial
    containers get the wheel from build/aip/ (see _benchflow_patch).
    """
    if AIP_DIR.exists():
        if not force:
            typer.echo(f"AIP already at {AIP_DIR} (pass --force to re-clone).")
            raise typer.Exit(0)
        shutil.rmtree(AIP_DIR)

    AIP_DIR.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--depth", "1", "--branch", aip_ref, AIP_REMOTE, str(AIP_DIR)]
    if aip_sha:
        # A SHA cannot be cloned shallowly by name; take the branch, then fetch the commit.
        cmd = ["git", "clone", "--branch", aip_ref, AIP_REMOTE, str(AIP_DIR)]
    typer.echo("$ " + " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        raise typer.Exit(rc)
    if aip_sha:
        for step in (["git", "fetch", "origin", aip_sha], ["git", "checkout", "--detach", aip_sha]):
            typer.echo("$ " + " ".join(step))
            rc = subprocess.call(step, cwd=AIP_DIR)
            if rc != 0:
                raise typer.Exit(rc)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=AIP_DIR, text=True).strip()
    version = format_version()
    typer.echo(f"Installed AIP at {AIP_DIR}  ref={aip_ref}  sha={sha[:12]}  format={version}")

    if install_cli:
        # Host CLI: `aip validate` / `aip run` for authoring and pack validation.
        cmd = ["uv", "tool", "install", "--force", "--editable", str(AIP_DIR)]
        typer.echo("$ " + " ".join(cmd))
        rc = subprocess.call(cmd)
        if rc != 0:
            raise typer.Exit(rc)
        # Wheel for trial containers.
        if AIP_BUILD_DIR.exists():
            shutil.rmtree(AIP_BUILD_DIR)
        AIP_BUILD_DIR.mkdir(parents=True)
        cmd = ["uv", "build", "--wheel", "--out-dir", str(AIP_BUILD_DIR), str(AIP_DIR)]
        typer.echo("$ " + " ".join(cmd))
        rc = subprocess.call(cmd)
        if rc != 0:
            raise typer.Exit(rc)
        typer.echo(f"Built {aip_wheel().name} in {AIP_BUILD_DIR}")

    GENERATED_SKILLS.mkdir(exist_ok=True)
    AIP_REF_FILE.write_text(
        json.dumps(
            {
                "remote": AIP_REMOTE,
                "ref": aip_ref,
                "sha": sha,
                "aip_version": version,
                "recorded_at": datetime.now().isoformat(timespec="seconds"),
            },
            indent=2,
        )
        + "\n"
    )
    typer.echo(f"Recorded {AIP_REF_FILE.relative_to(ROOT)} (commit it with the regenerated cohort)")


@app.command()
def eval(
    task: str = typer.Option(..., help="Task name under vendor/skillsbench/tasks/."),
    model: str = typer.Option(..., help="Model string, e.g. claude-haiku-4-5."),
    mode: Mode = typer.Option(Mode.noskill, case_sensitive=False),
    agent: str = typer.Option("claude-agent-acp", help="Agent name."),
    sandbox: str = typer.Option("docker", help="docker | daytona | modal."),
    concurrency: int = typer.Option(4),
    jobs_dir: Path = typer.Option(None, help="Override jobs/ output dir."),
    install_aip: bool = typer.Option(
        True, "--install-aip/--no-install-aip",
        help="AIP modes: install the `aip` CLI in the trial container so the agent runs the "
             "procedure through the protocol client (`aip run`). Off = agent executes the graph itself.",
    ),
    decision_model: bool = typer.Option(
        False, "--decision-model/--no-decision-model",
        help="AIP modes: forward TYPESAFE_API_KEY from .env so decision steps are answered by the "
             "System One model. Off = the agent answers decision questions itself at each pause.",
    ),
    aip_nudge: bool = typer.Option(
        False, "--aip-nudge/--no-aip-nudge",
        help="AIP modes: also write a ~/.claude/CLAUDE.md memory in the sandbox telling the agent "
             "to drive AIP skills through `aip run`. Off = only the skill's runtime block says so.",
    ),
) -> None:
    """Run one evaluation in one of the five modes."""
    task_dir = _task_dir(task)
    out = jobs_dir or (JOBS_DIR / f"{task}-{mode.value}-{model}")
    env: dict[str, str] = {}

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
        failures = validate_packs(conv)
        if failures:
            raise typer.BadParameter(
                "AIP pack does not validate against the bootstrapped AIP format "
                f"(regenerate with `aip-skillbench convert --task {task} --from {from_.value} --force`):\n  - "
                + "\n  - ".join(failures)
            )
        extra = ["--skills-dir", str(conv)]
        if install_aip:
            try:
                env[WHEEL_ENV] = str(aip_wheel())
            except FileNotFoundError as err:
                raise typer.BadParameter(str(err)) from err
            if aip_nudge:
                env[NUDGE_ENV] = "1"
        elif aip_nudge:
            raise typer.BadParameter("--aip-nudge needs --install-aip")
        if decision_model:
            key = _read_dotenv(ROOT / ".env").get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFE_API_KEY")
            if not key:
                raise typer.BadParameter("--decision-model needs TYPESAFE_API_KEY in .env or the environment")
            extra += ["--agent-env", f"TYPESAFE_API_KEY={key}"]
    else:
        raise typer.BadParameter(f"unknown mode: {mode}")

    raise typer.Exit(_bench(*base, *extra, env=env))


_CHECKLIST_NOTE = """\
Follow the aip skill's "Authoring an Agent Skill" checklist end to end: source/
materials, SKILL.md with the verbatim runtime block and one fenced YAML procedure,
`aip validate` after every edit (the `aip` CLI is on PATH), the line-by-line
completeness check against the sources, and the functional test with `aip run`
using realistic start inputs. Nobody is watching this session: do not ask
questions, and skip the checklist's install step (write straight to the
destination below). Everything you may read is under ./inputs/ and everything you
write goes under ./out/; do not look anywhere else on this machine. Scripts run
inside the task's container, so they must work with the packages that container
provides (see ./inputs/environment/Dockerfile when present) or bootstrap their own
environment; do not assume extra packages.\
"""

_PROMPT_FROM_CURATED = """\
Use the `aip` skill in ./.claude/skills/aip/ to convert the curated Agent
Skill at:

    ./inputs/skills/{name}

into an AIP skill at:

    ./out/{name}

{checklist}

Requirements:
1. Read ./inputs/skills/{name}/SKILL.md and every other file under it (scripts/,
   references/, assets/, etc.). Copy the originals verbatim into ./out/{name}/source/
   and write ./out/{name}/source/README.md with the provenance, the step-kind
   choices, and the deliberate-drop log. Mirror, copy, or adapt supporting files into
   scripts/, references/, or assets/ as the procedure needs.
2. Do not change the skill's `name:` frontmatter field ({name}) — the mounted skill
   directory name must match.
3. The skill must carry all the specialized knowledge and procedures an agent needs
   to solve this task type autonomously.

Write nothing outside ./out/{name}/."""


_PROMPT_FROM_CURATED_SINGLE = """\
Use the `aip` skill in ./.claude/skills/aip/ to compile the curated Agent
Skills under:

    ./inputs/skills/

({skill_names}) into ONE AIP skill at:

    ./out/<skill-name>/

{checklist}

Requirements:
1. Read every SKILL.md and every other file under ./inputs/skills/ (scripts/,
   references/, assets/, etc.). The curated skills describe one workflow; compile
   them into a single procedure graph. Copy all the originals verbatim into
   ./out/<skill-name>/source/ and write ./out/<skill-name>/source/README.md with
   the provenance, the step-kind choices, and the deliberate-drop log. Mirror, copy,
   or adapt supporting files into scripts/, references/, or assets/ as the
   procedure needs.
2. Pick a concise `<skill-name>`; the directory name under ./out/ must equal the
   skill's `name:` frontmatter.
3. The skill must carry all the specialized knowledge and procedures an agent needs
   to solve this task type autonomously.

Write nothing outside ./out/."""


_PROMPT_FROM_INSTRUCTION = """\
Use the `aip` skill in ./.claude/skills/aip/ to author one or more
AIP Agent Skills so a downstream agent can solve the
task described in:

    ./inputs/instruction.md

Write the skill pack(s) into:

    ./out/<skill-name>/SKILL.md (plus scripts/, references/, assets/ as needed)

{checklist}

Requirements:
1. ./inputs/instruction.md is the only input; author from it alone. Copy it into
   each skill's source/ folder next to its source/README.md.
2. The skills you author should have all the specialized knowledge and procedures
   an agent needs to solve this task type autonomously. Pick concise
   `<skill-name>` value(s); the directory name under ./out/ must match the
   skill's `name:` frontmatter.

Write nothing outside ./out/."""

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
    single: bool = typer.Option(
        False, "--single/--per-skill",
        help="--from curated only: compile all curated skills into one AIP procedure "
             "(default: one AIP skill per curated skill, names preserved).",
    ),
    keep_workspace: bool = typer.Option(
        False, "--keep-workspace", help="Keep build/authoring/<workspace> after the run (debugging)."
    ),
) -> None:
    """Produce an AIP skill pack for `task`, by Opus authoring offline in a sandboxed workspace.

    The authoring session sees only ./inputs/ (the curated skills and Dockerfile, or
    instruction.md) and writes to ./out/; its transcript is audited for any path
    outside the workspace and the conversion fails on a hit. Prompt, transcript,
    audit, and metadata land in generated-skills/<task>/_authoring/<from>/.

    `--from curated` — convert each skill under
    `vendor/skillsbench/tasks/<task>/environment/skills/` to AIP, preserving
    names (or `--single`: one procedure for the whole task).
    Output: `generated-skills/<task>/aip-from-curated/<skill>/`.

    `--from instruction` — author from `instruction.md` alone.
    Output: `generated-skills/<task>/aip-from-instruction/<skill>/`.
    """
    from aip_skillbench import _authoring as A

    _require_aip()
    task_dir = _task_dir(task)
    dst_root = _generated_skills_dir(task, from_)
    if dst_root.exists() and not force:
        raise typer.BadParameter(f"already exists: {dst_root} (pass --force to overwrite)")
    if dst_root.exists():
        shutil.rmtree(dst_root)
    record_dir = GENERATED_SKILLS / task / "_authoring" / from_.value
    key, key_src = _author_api_key()

    jobs: list[tuple[str, str, Any]] = []  # (label, prompt, stager)
    if from_ is ConvertFrom.curated:
        src_root = _curated_skills_dir(task)
        skills = sorted(p.name for p in src_root.iterdir() if p.is_dir() and (p / "SKILL.md").exists()) if src_root.exists() else []
        if not skills:
            raise typer.BadParameter(f"no skill dirs (with SKILL.md) under {src_root}")
        dockerfile = task_dir / "environment" / "Dockerfile"
        if single:
            jobs.append((
                "single",
                _PROMPT_FROM_CURATED_SINGLE.format(skill_names=", ".join(skills), checklist=_CHECKLIST_NOTE),
                lambda ws: A.stage_curated(ws, src_root, dockerfile),
            ))
        else:
            for name in skills:
                jobs.append((
                    name,
                    _PROMPT_FROM_CURATED.format(name=name, checklist=_CHECKLIST_NOTE),
                    lambda ws: A.stage_curated(ws, src_root, dockerfile),
                ))
    else:
        instruction = task_dir / "instruction.md"
        if not instruction.exists():
            raise typer.BadParameter(f"no instruction.md at {instruction}")
        jobs.append(("instruction", _PROMPT_FROM_INSTRUCTION.format(checklist=_CHECKLIST_NOTE),
                     lambda ws: A.stage_instruction(ws, instruction)))

    typer.echo(f"Authoring {len(jobs)} AIP pack(s) for task '{task}' from {from_.value} with {author_model} "
               f"[ANTHROPIC_API_KEY: {key_src}]")
    failed = False
    for label, prompt, stage in jobs:
        ws = A.make_workspace(task, f"{from_.value}-{label}")
        stage(ws)
        typer.echo(f"\n→ {label}: workspace {ws.relative_to(ROOT)}")
        rc, transcript = A.run_author(ws, prompt, author_model, key)
        audit = A.audit_transcript(transcript, ws)
        meta = {
            "task": task, "from": from_.value, "label": label, "single": single,
            "author_model": author_model, "claude_exit": rc,
            "started_workspace": ws.name, "recorded_at": datetime.now().isoformat(timespec="seconds"),
        }
        produced = A.finalize(ws, dst_root, record_dir / label, audit, meta, keep_workspace)
        cost = audit.get("total_cost_usd")
        typer.echo(f"  claude exit={rc}  tool calls={audit['tool_calls']}  cost=${cost:.2f}  produced={produced}"
                   if isinstance(cost, (int, float)) else
                   f"  claude exit={rc}  tool calls={audit['tool_calls']}  produced={produced}")
        if rc != 0:
            failed = True
        if not audit["ok"]:
            failed = True
            typer.echo("  AUDIT FAILED: tool calls reached outside the workspace:")
            for v in audit["violations"][:10]:
                typer.echo(f"    {v['tool']}: {v['hits']}")
            typer.echo(f"  full record: {(record_dir / label / 'audit.json').relative_to(ROOT)}")
        if not produced:
            failed = True
            typer.echo("  WARNING: nothing written under out/")
    if failed:
        typer.echo("\nCONVERSION FAILED (output kept for inspection)")
        raise typer.Exit(1)
    _gate(dst_root)


def _gate(dst_root: Path) -> None:
    """Every produced pack must validate against the bootstrapped AIP format."""
    failures = validate_packs(dst_root)
    if failures:
        typer.echo("\nVALIDATION FAILED (output kept for inspection):\n  - " + "\n  - ".join(failures))
        raise typer.Exit(1)
    typer.echo(f"Validated {len(list(dst_root.iterdir()))} pack(s) under {dst_root}")

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


def _convert_one(
    task: str, from_value: str, author_model: str, force: bool, single: bool = False
) -> tuple[str, str, int, float, str]:
    """Run one `aip-skillbench convert` invocation as a subprocess. Returns (task, from, rc, secs, tail)."""
    import time
    cmd = [
        "uv", "run", "aip-skillbench", "convert",
        "--task", task, "--from", from_value,
        "--author-model", author_model,
    ]
    if force:
        cmd.append("--force")
    if single and from_value == "curated":
        cmd.append("--single")
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
    single: bool = typer.Option(
        False, "--single/--per-skill",
        help="Curated side: compile all curated skills into one AIP procedure per task.",
    ),
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
            ex.submit(_convert_one, task, f.value, author_model, force, single): (task, f.value)
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
    decision_model: Optional[bool] = typer.Option(
        None, "--decision-model/--no-decision-model",
        help="AIP modes: answer decision steps with the System One model (TYPESAFE_API_KEY). "
             "Config key `decision_model`. Default off.",
    ),
    aip_nudge: Optional[bool] = typer.Option(
        None, "--aip-nudge/--no-aip-nudge",
        help="AIP modes: seed a ~/.claude/CLAUDE.md memory telling the solver to run AIP skills "
             "through `aip run`. Config key `aip_nudge`. Default off.",
    ),
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
    decision_resolved = (
        decision_model if decision_model is not None else bool(cfg.get("decision_model", False))
    )
    nudge_resolved = aip_nudge if aip_nudge is not None else bool(cfg.get("aip_nudge", False))

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
        decision_model=decision_resolved,
        aip_nudge=nudge_resolved,
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
