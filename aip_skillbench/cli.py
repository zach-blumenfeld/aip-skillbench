"""aip-skillbench CLI — five-mode evaluation harness over SkillsBench tasks."""

from __future__ import annotations

import shutil
import subprocess
from enum import Enum
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parents[1]
VENDOR_SKILLSBENCH = ROOT / "vendor" / "skillsbench"
AIP_DIR = ROOT / ".claude" / "skills" / "aip"
AIP_REMOTE = "git@github.com:zach-blumenfeld/aip.git"
GENERATED_SKILLS = ROOT / "generated-skills"
JOBS_DIR = ROOT / "jobs"

app = typer.Typer(add_completion=False, no_args_is_help=True)


class Mode(str, Enum):
    noskill = "noskill"
    human_curated = "human-curated"
    selfgen_skill_creator = "selfgen-skill-creator"
    selfgen_aip = "selfgen-aip"
    aip_from_curated = "aip-from-curated"


def _task_dir(task: str) -> Path:
    path = VENDOR_SKILLSBENCH / "tasks" / task
    if not path.exists():
        raise typer.BadParameter(f"task not found: {path}")
    return path


def _curated_skills_dir(task: str) -> Path:
    return _task_dir(task) / "environment" / "skills"


def _converted_skills_dir(task: str) -> Path:
    return GENERATED_SKILLS / task / "aip-from-curated"


def _require_aip() -> Path:
    if not (AIP_DIR / "SKILL.md").exists():
        raise typer.BadParameter(
            f"AIP not installed at {AIP_DIR}. Run `aip-skillbench bootstrap` first."
        )
    return AIP_DIR


def _bench(*args: str) -> int:
    """Invoke benchflow's `bench` CLI in the current uv env."""
    cmd = ["uv", "run", "bench", *args]
    typer.echo("$ " + " ".join(cmd))
    return subprocess.call(cmd)


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
        extra = ["--skill-mode", "self-gen"]
        # skill-creator auto-discovered from ~/.claude/skills/skill-creator etc.
    elif mode is Mode.selfgen_aip:
        extra = ["--skill-mode", "self-gen", "--skill-creator-dir", str(_require_aip())]
    elif mode is Mode.aip_from_curated:
        conv = _converted_skills_dir(task)
        if not conv.exists() or not any(conv.iterdir()):
            raise typer.BadParameter(
                f"No converted skills at {conv}. Run `aip-skillbench convert --task {task}` first."
            )
        extra = ["--skills-dir", str(conv)]
    else:
        raise typer.BadParameter(f"unknown mode: {mode}")

    raise typer.Exit(_bench(*base, *extra))


_CONVERT_PROMPT = """\
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


@app.command()
def convert(
    task: str = typer.Option(..., help="Task name; converts every skill under it."),
    force: bool = typer.Option(False, help="Overwrite existing converted output."),
    claude_model: str = typer.Option(
        "claude-opus-4-7", help="Model for the conversion call."
    ),
) -> None:
    """Mode-5 step 1: convert curated skills under a task to AIP format.

    Shells out to `claude -p` with the AIP skill mounted at ./.claude/skills/aip/
    and writes the AIP version to generated-skills/<task>/aip-from-curated/<skill>/.
    """
    _require_aip()
    src_root = _curated_skills_dir(task)
    if not src_root.exists():
        raise typer.BadParameter(f"no curated skills at {src_root}")
    dst_root = _converted_skills_dir(task)
    if dst_root.exists() and not force:
        raise typer.BadParameter(f"already exists: {dst_root} (pass --force to overwrite)")
    dst_root.mkdir(parents=True, exist_ok=True)

    skills = [p for p in src_root.iterdir() if p.is_dir() and (p / "SKILL.md").exists()]
    if not skills:
        raise typer.BadParameter(f"no skill dirs (with SKILL.md) under {src_root}")
    typer.echo(f"Converting {len(skills)} skill(s) under task '{task}':")

    for src in skills:
        dst = dst_root / src.name
        if dst.exists():
            shutil.rmtree(dst)
        typer.echo(f"\n→ {src.name}")
        prompt = _CONVERT_PROMPT.format(src=src, dst=dst)
        cmd = [
            "claude", "-p", prompt,
            "--model", claude_model,
            "--add-dir", str(src),
            "--add-dir", str(dst_root),
            "--dangerously-skip-permissions",
        ]
        typer.echo("$ " + " ".join(cmd[:4]) + f" … --add-dir {src} --add-dir {dst_root} …")
        rc = subprocess.call(cmd, cwd=ROOT)
        if rc != 0:
            raise typer.Exit(rc)
        if not (dst / "SKILL.md").exists():
            typer.echo(f"  WARNING: {dst}/SKILL.md not produced by Claude.")

    typer.echo(f"\nWrote {len(skills)} skill(s) to {dst_root}")


@app.command()
def reward(jobs_subdir: Path) -> None:
    """Print the reward(s) under a jobs/ output directory."""
    if not jobs_subdir.exists():
        raise typer.BadParameter(f"not found: {jobs_subdir}")
    for r in sorted(jobs_subdir.glob("*/verifier/reward.txt")):
        typer.echo(f"{r.parent.parent.name}: {r.read_text().strip()}")


if __name__ == "__main__":
    app()
