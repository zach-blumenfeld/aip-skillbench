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


@app.command()
def convert(
    task: str = typer.Option(..., help="Task name; converts every skill under it."),
    force: bool = typer.Option(False, help="Overwrite existing converted output."),
) -> None:
    """Mode-5 step 1: convert curated skills under a task to AIP format.

    NOT IMPLEMENTED — stub. The real conversion should invoke an LLM with AIP
    mounted as a skill (see ./.claude/skills/aip) and feed it the curated SKILL.md
    as input, writing the AIP version to generated-skills/<task>/aip-from-curated/.
    """
    _require_aip()
    src = _curated_skills_dir(task)
    if not src.exists():
        raise typer.BadParameter(f"no curated skills at {src}")
    dst = _converted_skills_dir(task)
    if dst.exists() and not force:
        raise typer.BadParameter(f"already exists: {dst} (pass --force to overwrite)")

    dst.mkdir(parents=True, exist_ok=True)
    skills = [p for p in src.iterdir() if p.is_dir() and (p / "SKILL.md").exists()]
    typer.echo(f"Found {len(skills)} curated skill(s) in {src}:")
    for s in skills:
        typer.echo(f"  - {s.name}")
        # TODO: invoke AIP-conversion (LLM call) here and write to dst / s.name.
        # For now, copy verbatim so the rest of the pipeline is exercisable.
        target = dst / s.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(s, target)
    typer.echo(f"\nWrote {len(skills)} skill(s) to {dst}")
    typer.echo("WARNING: conversion is a stub (copy). Implement real AIP authoring in cli.convert.")


@app.command()
def reward(jobs_subdir: Path) -> None:
    """Print the reward(s) under a jobs/ output directory."""
    if not jobs_subdir.exists():
        raise typer.BadParameter(f"not found: {jobs_subdir}")
    for r in sorted(jobs_subdir.glob("*/verifier/reward.txt")):
        typer.echo(f"{r.parent.parent.name}: {r.read_text().strip()}")


if __name__ == "__main__":
    app()
