"""aip-skillbench CLI — multi-mode evaluation harness over SkillsBench tasks."""

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
    AIP_SERVER_URL,
    BAKE_ENV,
    GENERATED_SKILLS,
    NUDGE_ENV,
    PUBLISH_ENV,
    REFS_FILE,
    ROOT,
    SERVER_ENV,
    SERVER_EXTRA_ENV,
    VARIANTS,
    WHEEL_ENV,
    Variant,
    aip_spec_wheel,
    aip_wheel,
    format_version,
    read_refs,
    skill_dirs,
    validate_packs,
)
from aip_skillbench._variants import AIP_REMOTE, AIP_SPEC_REMOTE

VENDOR_SKILLSBENCH = ROOT / "vendor" / "skillsbench"
VENDOR_SKILL_CREATOR = VENDOR_SKILLSBENCH / ".agents" / "skills" / "skill-creator"
JOBS_DIR = ROOT / "jobs"

app = typer.Typer(add_completion=False, no_args_is_help=True)


class Mode(str, Enum):
    """What the solver's container gets (kept in sync with run_matrix.Mode)."""
    noskill = "noskill"                          # instruction and fixtures only
    human_curated = "human-curated"              # the task's curated skills, as shipped
    selfgen_skill_creator = "selfgen-skill-creator"  # a skill the solver writes at trial time
    skill = "skill"                              # a variant's pack mounted as a skill (--variant; --nudge off by default)
    aip_runtime = "aip-runtime"                  # a variant's pack published to an in-container aip server (--variant)


VARIANT_MODES = (Mode.skill, Mode.aip_runtime)


def _task_dir(task: str) -> Path:
    path = VENDOR_SKILLSBENCH / "tasks" / task
    if not path.exists():
        raise typer.BadParameter(f"task not found: {path}")
    return path


def _curated_skills_dir(task: str) -> Path:
    return _task_dir(task) / "environment" / "skills"


def _variant(name: str) -> Variant:
    if name not in VARIANTS:
        raise typer.BadParameter(f"unknown variant {name!r}; one of {', '.join(VARIANTS)}", param_hint="'--variant'")
    return VARIANTS[name]


def _checked_pack(task: str, v: Variant) -> Path:
    """The task's pack dir for a variant, refused unless every skill in it passes the variant's gate."""
    root = v.pack_root(task)
    if not skill_dirs(root):
        raise typer.BadParameter(
            f"No {v.name} pack at {root}. Run `aip-skillbench convert --task {task} --variant {v.name}` first."
        )
    failures = validate_packs(v, root)
    if failures:
        raise typer.BadParameter(
            f"{v.name} pack fails its gate (regenerate with "
            f"`aip-skillbench convert --task {task} --variant {v.name} --force`):\n  - "
            + "\n  - ".join(failures)
        )
    return root


def _require_aip(v: Variant) -> Path:
    skill = v.authoring_skill
    if not (skill / "SKILL.md").exists():
        raise typer.BadParameter(
            f"authoring skill for variant {v.name} not found at {skill}. Run "
            f"`aip-skillbench bootstrap --variant {v.name}` first."
        )
    return skill


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

def _run(cmd: list[str], cwd: Path | None = None) -> None:
    typer.echo("$ " + " ".join(cmd))
    rc = subprocess.call(cmd, cwd=cwd)
    if rc != 0:
        raise typer.Exit(rc)


def _clone(remote: str, ref: str, dest: Path, sha: str | None) -> str:
    """Clone `remote` at `ref` into `dest` (optionally detach at `sha`); return HEAD."""
    if sha:
        # A SHA cannot be cloned shallowly by name; take the ref, then fetch the commit.
        _run(["git", "clone", "--branch", ref, remote, str(dest)])
        _run(["git", "fetch", "origin", sha], cwd=dest)
        _run(["git", "checkout", "--detach", sha], cwd=dest)
    else:
        _run(["git", "clone", "--depth", "1", "--branch", ref, remote, str(dest)])
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=dest, text=True).strip()


@app.command()
def bootstrap(
    variants: list[str] = typer.Option(
        [], "--variant", help="Repeatable; default every variant: " + ", ".join(VARIANTS),
    ),
    aip_sha: Optional[str] = typer.Option(
        None, "--aip-sha", help="aip commit to check out after cloning (exact reproduction); applies to every named variant.",
    ),
    force: bool = typer.Option(False, help="Rebuild a variant whose build dir already exists."),
) -> None:
    """Set up the compile variants under build/<variant>/ (gitignored) and record their pins.

    Per variant (aip_skillbench/_variants.py): clone its repos, build what its kind needs
    (host CLIs, wheels, authoring skill, runtime skill, or just a copy of the skill), write
    build/<variant>/REF.json, and merge it into generated-skills/REFS.json (committed with
    the packs). Variant `aip-0.6a1` also installs `aip-spec` and `aip` on the host PATH,
    which its authoring sessions need; the validation gates never depend on PATH.
    """
    names = list(variants) or list(VARIANTS)
    bad = [n for n in names if n not in VARIANTS]
    if bad:
        raise typer.BadParameter(f"unknown variant(s) {bad}; one of {', '.join(VARIANTS)}")
    for name in names:
        v = VARIANTS[name]
        if v.build_dir.exists():
            if not force:
                typer.echo(f"{v.name}: {v.build_dir.relative_to(ROOT)} exists (pass --force to rebuild)")
                continue
            shutil.rmtree(v.build_dir)
        v.build_dir.mkdir(parents=True)
        typer.echo(f"\n== {v.name} ({v.kind})")
        ref = _bootstrap_variant(v, aip_sha)
        v.ref_file.write_text(json.dumps(ref, indent=2) + "\n")
        typer.echo(f"{v.name}: format={ref.get('format_version')}  recorded {v.ref_file.relative_to(ROOT)}")
    # Merge every built variant's REF.json into the committed REFS.json.
    GENERATED_SKILLS.mkdir(exist_ok=True)
    refs = read_refs()
    for v in VARIANTS.values():
        if v.ref_file.exists():
            refs[v.name] = v.read_ref()
    REFS_FILE.write_text(json.dumps(refs, indent=2) + "\n")
    typer.echo(f"\nRecorded {REFS_FILE.relative_to(ROOT)} for {', '.join(sorted(refs))} (commit it with the packs)")


_SKILL_COPY_IGNORE = shutil.ignore_patterns(".git", ".gitignore", "tests", "img", "__pycache__", "*.pyc", ".DS_Store")


def _bootstrap_variant(v: Variant, aip_sha: Optional[str]) -> dict:
    ref: dict[str, Any] = {"variant": v.name, "kind": v.kind, "skill_name": v.skill_name}
    if v.kind == "aip":
        aip_src, spec_src = v.src_dir("aip"), v.src_dir("aip-spec")
        aip_head = _clone(AIP_REMOTE, v.aip_ref, aip_src, aip_sha)
        spec_head = _clone(AIP_SPEC_REMOTE, v.aip_spec_ref, spec_src, None)
        # Host CLIs on PATH: the authoring checklist runs `aip-spec validate` and `aip run`.
        _run(["uv", "tool", "install", "--force", "--editable", str(spec_src)])
        _run(["uv", "tool", "install", "--force", "--editable", f"{aip_src}[server]"])
        # Wheels for trial containers.
        v.wheels_dir.mkdir()
        for src in (spec_src, aip_src):
            _run(["uv", "build", "--wheel", "--out-dir", str(v.wheels_dir), str(src)])
        typer.echo(f"Built {aip_spec_wheel(v).name} and {aip_wheel(v).name} in {v.wheels_dir.relative_to(ROOT)}")
        # Skills: aip/ (authoring, copied into workspaces) and a dir holding only aip-runtime/ for trials.
        _run(["uv", "run", "--quiet", "--project", str(aip_src), "aip", "skill", "install", "--path", str(v.skill_dir)])
        _run(["uv", "run", "--quiet", "--project", str(aip_src), "aip", "runtime", "--skill", "--out", str(v.runtime_skill_dir)])
        ref["aip"] = {"remote": AIP_REMOTE, "ref": v.aip_ref, "sha": aip_head}
        ref["aip_spec"] = {"remote": AIP_SPEC_REMOTE, "ref": v.aip_spec_ref, "sha": spec_head}
    elif v.kind == "aip-legacy":
        aip_src = v.src_dir("aip")
        aip_head = _clone(AIP_REMOTE, v.aip_ref, aip_src, aip_sha)
        # The repo is the skill: copy it minus tests/ and images.
        shutil.copytree(aip_src, v.authoring_skill, ignore=_SKILL_COPY_IGNORE)
        _run(["uv", "run", "--quiet", str(v.authoring_skill / "scripts" / "validate.py"), "--help"])
        ref["aip"] = {"remote": AIP_REMOTE, "ref": v.aip_ref, "sha": aip_head}
    elif v.kind == "dist":
        assert v.skill_source is not None
        if not (v.skill_source / "SKILL.md").exists():
            raise typer.BadParameter(f"no SKILL.md under {v.skill_source}")
        shutil.copytree(v.skill_source, v.authoring_skill, ignore=_SKILL_COPY_IGNORE)
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", str(v.skill_source)],
                               capture_output=True, text=True, cwd=ROOT).stdout.strip()
        ref["skill_source"] = {"path": str(v.skill_source.relative_to(ROOT)), "repo_sha": head, "dirty": bool(dirty)}
    else:
        raise typer.BadParameter(f"variant {v.name}: unknown kind {v.kind}")
    if not (v.authoring_skill / "SKILL.md").exists():
        raise typer.BadParameter(f"{v.name}: no authoring skill at {v.authoring_skill}")
    ref["format_version"] = format_version(v)
    ref["recorded_at"] = datetime.now().isoformat(timespec="seconds")
    return ref


@app.command()
def eval(
    task: str = typer.Option(..., help="Task name under vendor/skillsbench/tasks/."),
    model: str = typer.Option(..., help="Model string, e.g. claude-haiku-5-5."),
    mode: Mode = typer.Option(Mode.noskill, case_sensitive=False),
    variant_name: Optional[str] = typer.Option(
        None, "--variant",
        help="skill / aip-runtime: the compile variant whose pack the container gets: " + ", ".join(VARIANTS),
    ),
    agent: str = typer.Option("claude-agent-acp", help="Agent name."),
    sandbox: str = typer.Option("docker", help="docker | daytona | modal."),
    concurrency: int = typer.Option(4),
    jobs_dir: Path = typer.Option(None, help="Override jobs/ output dir."),
    nudge: bool = typer.Option(
        False, "--nudge/--no-nudge",
        help="skill only: write the mounted-skill memory file (~/.claude/CLAUDE.md) naming the skill "
             "as the mandatory first action. Off by default: the skill's own description does the "
             "activation. The ablation knob.",
    ),
    aip_nudge: bool = typer.Option(
        True, "--aip-nudge/--no-aip-nudge",
        help="aip-runtime only: write the aip-runtime memory file (`aip search` first). On by default; "
             "--no-aip-nudge is the ablation.",
    ),
    decision_model: bool = typer.Option(
        False, "--decision-model/--no-decision-model",
        help="aip-runtime only: put TYPESAFE_API_KEY from .env in the solver's environment, where "
             "the aip client answers decision steps with the decision model (the server holds no key). "
             "Off = the solver answers each pause.",
    ),
    step_timeout: int = typer.Option(
        1800, "--step-timeout",
        help="aip-runtime: seconds an execution step may run before the aip client kills it "
             "(the in-container server's AIP_STEP_TIMEOUT, sent with each step; 0 = no limit). "
             "Default 1800, the agent's own budget.",
    ),
    agent_env: list[str] = typer.Option(
        [], "--agent-env",
        help="Repeatable KEY=VALUE for the solver process in the container (e.g. "
             "MAX_THINKING_TOKENS=0 for models the bundled harness cannot send thinking params to).",
    ),
    bake_agent: bool = typer.Option(
        True, "--bake-agent/--no-bake-agent",
        help="Bake the agent (Node + its npm package) into the task image once instead of "
             "npm-installing it in every container; avoids the stall when many trials start at once.",
    ),
) -> None:
    """Run one evaluation in one mode."""
    task_dir = _task_dir(task)
    if mode in VARIANT_MODES and not variant_name:
        raise typer.BadParameter(f"--mode {mode.value} needs --variant (one of {', '.join(VARIANTS)})", param_hint="'--variant'")
    if mode not in VARIANT_MODES and variant_name:
        raise typer.BadParameter(f"--variant applies only to --mode skill / aip-runtime (got {mode.value})", param_hint="'--variant'")
    if nudge and mode is not Mode.skill:
        raise typer.BadParameter(f"--nudge applies only to --mode skill (got {mode.value})", param_hint="'--nudge'")
    if decision_model and mode is not Mode.aip_runtime:
        raise typer.BadParameter(
            f"--decision-model applies only to --mode aip-runtime (got {mode.value})",
            param_hint="'--decision-model'",
        )
    v = _variant(variant_name) if variant_name else None
    if mode is Mode.aip_runtime and v is not None and not v.has_runtime:
        raise typer.BadParameter(
            f"variant {v.name} has no runtime; --mode aip-runtime takes one of "
            + ", ".join(n for n, x in VARIANTS.items() if x.has_runtime), param_hint="'--variant'",
        )
    label = f"{mode.value}-{v.name}" if v else mode.value
    out = jobs_dir or (JOBS_DIR / f"{task}-{label}-{model}")
    env: dict[str, str] = {}
    if bake_agent:
        env[BAKE_ENV] = agent

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
    elif mode is Mode.skill:
        # The variant's pack mounted as a skill; nothing else is installed. An AIP pack's
        # runtime block has the solver execute the graph itself; a dist pack is a plain skill.
        assert v is not None
        extra = ["--skills-dir", str(_checked_pack(task, v))]
        if nudge:
            env[NUDGE_ENV] = mode.value
    elif mode is Mode.aip_runtime:
        # Nothing task-specific mounted: only the aip-runtime skill. The pack is
        # published to an aip server inside the container (see _benchflow_patch).
        assert v is not None
        pack_root = _checked_pack(task, v)
        packs = skill_dirs(pack_root)
        if len(packs) != 1:
            raise typer.BadParameter(
                f"aip-runtime publishes one procedure per task, but {pack_root} holds "
                f"{len(packs)} skill folders ({', '.join(p.name for p in packs)}). Re-author with "
                f"`aip-skillbench convert --task {task} --variant {v.name} --force`."
            )
        runtime_skills = v.runtime_skill_dir
        if not (runtime_skills / "aip-runtime" / "SKILL.md").exists():
            raise typer.BadParameter(
                f"no aip-runtime skill at {runtime_skills}; run `aip-skillbench bootstrap --variant {v.name} --force`"
            )
        try:
            env[WHEEL_ENV] = f"{aip_spec_wheel(v)}:{aip_wheel(v)}"
        except FileNotFoundError as err:
            raise typer.BadParameter(str(err)) from err
        env[SERVER_ENV] = "1"
        env[PUBLISH_ENV] = str(packs[0])
        if aip_nudge:
            env[NUDGE_ENV] = mode.value
        # The server's default per-step timeout, which it sends with each execution step
        # the client runs. aip's built-in default is 60 s, which a correct but slow script
        # exceeds on a 1-CPU task container (TLS took 73 s), while the same step has no
        # limit when the solver runs it by hand in skill mode. Give the protocol the same
        # budget as the agent.
        env[SERVER_EXTRA_ENV] = json.dumps({"AIP_STEP_TIMEOUT": str(step_timeout)})
        extra = [
            "--skills-dir", str(runtime_skills),
            "--agent-env", f"AIP_SERVER={AIP_SERVER_URL}",
        ]
        if decision_model:
            # The aip client resolves decisions, so the key goes where it runs:
            # the solver's environment. benchflow keeps *KEY* names out of config.json.
            key = _read_dotenv(ROOT / ".env").get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFE_API_KEY")
            if not key:
                raise typer.BadParameter("--decision-model needs TYPESAFE_API_KEY in .env or the environment")
            extra += ["--agent-env", f"TYPESAFE_API_KEY={key}"]
    else:
        raise typer.BadParameter(f"unknown mode: {mode}")

    for kv in agent_env:
        if "=" not in kv:
            raise typer.BadParameter(f"--agent-env expects KEY=VALUE, got {kv!r}")
        extra += ["--agent-env", kv]
    raise typer.Exit(_bench(*base, *extra, env=env))


@app.command()
def convert(
    task: str = typer.Option(..., help="Task name under vendor/skillsbench/tasks/."),
    variant_name: str = typer.Option(..., "--variant", help="Compile variant: " + ", ".join(VARIANTS)),
    force: bool = typer.Option(False, help="Overwrite an existing pack for this task and variant."),
    author_model: str = typer.Option(
        "claude-opus-5-5", "--author-model",
        help="Model used to author. Per AIP guidance, the largest available frontier model.",
    ),
    keep_workspace: bool = typer.Option(
        False, "--keep-workspace", help="Keep build/authoring/<workspace> after the run (debugging)."
    ),
    stage_data: str = typer.Option(
        "full", "--stage-data",
        help="What the author sees of the task's environment/ inputs: 'full' (default: the real "
             "files, so the skill can be tested against them; recorded in meta.json), 'sample' "
             "(first 2 KB of each file + manifest; format only, the stricter condition), or 'none'.",
    ),
) -> None:
    """Compile one task's curated skills into one pack under a variant, by Opus authoring
    offline in a sandboxed workspace.

    The authoring session sees only ./inputs/ (the curated skills, instruction.md, the
    Dockerfile, and the environment inputs per --stage-data) and writes to ./out/; its
    transcript is audited for any path outside the workspace and the conversion fails
    on a hit. Output: generated-skills/<task>/<variant>/<skill-name>/. Prompt,
    transcript, audit, and metadata: generated-skills/<task>/_authoring/<variant>/single/.
    The pack must pass the variant's gate (aip_skillbench/_variants.py).
    """
    from aip_skillbench import _authoring as A
    from aip_skillbench._prompts import prompt_for

    if stage_data not in ("sample", "full", "none"):
        raise typer.BadParameter("--stage-data must be sample, full, or none")
    v = _variant(variant_name)
    _require_aip(v)
    task_dir = _task_dir(task)
    dst_root = v.pack_root(task)
    if dst_root.exists() and not force:
        raise typer.BadParameter(f"already exists: {dst_root} (pass --force to overwrite)")
    if dst_root.exists():
        shutil.rmtree(dst_root)
    record_dir = v.record_dir(task) / "single"
    key, key_src = _author_api_key()

    src_root = _curated_skills_dir(task)
    skills = sorted(p.name for p in src_root.iterdir() if p.is_dir() and (p / "SKILL.md").exists()) if src_root.exists() else []
    if not skills:
        raise typer.BadParameter(f"no skill dirs (with SKILL.md) under {src_root}")
    instruction = task_dir / "instruction.md"
    if not instruction.exists():
        raise typer.BadParameter(f"no instruction.md at {instruction}")
    prompt = prompt_for(v, skills, stage_data)

    typer.echo(f"Authoring the {v.name} pack for task '{task}' with {author_model} [ANTHROPIC_API_KEY: {key_src}]")
    ws = A.make_workspace(task, v)
    A.stage_curated(ws, src_root, task_dir / "environment", instruction, stage_data)
    typer.echo(f"→ workspace {ws.relative_to(ROOT)}")
    rc, transcript = A.run_author(ws, prompt, author_model, key)
    audit = A.audit_transcript(transcript, ws)
    meta = {
        "task": task, "variant": v.name, "label": "single", "single": True,
        "author_model": author_model, "claude_exit": rc,
        "stage_data": stage_data, "stage_instruction": True,
        "started_workspace": ws.name, "recorded_at": datetime.now().isoformat(timespec="seconds"),
    }
    produced = A.finalize(ws, v, dst_root, record_dir, audit, meta, keep_workspace)
    cost = audit.get("total_cost_usd")
    typer.echo(f"  claude exit={rc}  tool calls={audit['tool_calls']}  cost=${cost:.2f}  produced={produced}"
               if isinstance(cost, (int, float)) else
               f"  claude exit={rc}  tool calls={audit['tool_calls']}  produced={produced}")
    failed = rc != 0
    if not audit["ok"]:
        failed = True
        typer.echo("  AUDIT FAILED: tool calls reached outside the workspace:")
        for viol in audit["violations"][:10]:
            typer.echo(f"    {viol['tool']}: {viol['hits']}")
        typer.echo(f"  full record: {(record_dir / 'audit.json').relative_to(ROOT)}")
    if not produced:
        failed = True
        typer.echo("  WARNING: nothing written under out/")
    if failed:
        typer.echo("\nCONVERSION FAILED (output kept for inspection)")
        raise typer.Exit(1)
    _gate(v, dst_root)


def _gate(v: Variant, dst_root: Path) -> None:
    """Every produced pack must pass the variant's gate."""
    failures = validate_packs(v, dst_root)
    if failures:
        typer.echo("\nVALIDATION FAILED (output kept for inspection):\n  - " + "\n  - ".join(failures))
        raise typer.Exit(1)
    typer.echo(f"Validated {len(skill_dirs(dst_root))} pack(s) under {dst_root} with the {v.name} gate")


def _discover_tasks(pattern: str) -> list[str]:
    tasks_dir = VENDOR_SKILLSBENCH / "tasks"
    return sorted(
        p.name for p in tasks_dir.glob(pattern)
        if p.is_dir() and (p / "instruction.md").exists()
    )


def _already_done(task: str, v: Variant) -> bool:
    """A pack exists and passes the variant's gate."""
    root = v.pack_root(task)
    return bool(skill_dirs(root)) and not validate_packs(v, root)


def _convert_one(
    task: str, v: Variant, author_model: str, force: bool, stage_data: str = "full"
) -> tuple[str, str, int, float, str]:
    """Run one `aip-skillbench convert` invocation as a subprocess. Returns (task, variant, rc, secs, tail)."""
    import time
    cmd = [
        "uv", "run", "aip-skillbench", "convert",
        "--task", task, "--variant", v.name,
        "--author-model", author_model,
    ]
    # A pack dir that exists here is either forced or failed its gate (valid ones were
    # skipped by the caller); convert refuses to overwrite without --force either way.
    if force or v.pack_root(task).exists():
        cmd.append("--force")
    if stage_data != "full":
        cmd += ["--stage-data", stage_data]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    secs = time.time() - t0
    tail = (proc.stderr or proc.stdout).splitlines()[-1] if (proc.stderr or proc.stdout) else ""
    return task, v.name, proc.returncode, secs, tail[:140]


@app.command("batch-convert")
def batch_convert(
    variant_names: list[str] = typer.Option(
        [], "--variant", help="Repeatable compile variant; default every variant: " + ", ".join(VARIANTS),
    ),
    concurrency: int = typer.Option(4, "--concurrency", "-j", help="Parallel claude calls."),
    force: bool = typer.Option(False, help="Re-author even if a valid pack exists."),
    pattern: str = typer.Option("*", help="Glob filter on task names. Ignored if --task is given."),
    tasks_explicit: list[str] = typer.Option(
        [], "--task", help="Explicit task name; repeatable. If any --task is given, --pattern is ignored."
    ),
    limit: int = typer.Option(0, help="Cap number of conversions (0 = all)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the 5s confirm pause."),
    author_model: str = typer.Option("claude-opus-5-5", "--author-model"),
    stage_data: str = typer.Option("full", "--stage-data", help="full | sample | none (see convert)."),
) -> None:
    """Compile many (task, variant) packs at once. Skips packs that exist and pass their gate unless --force."""
    import concurrent.futures
    import time

    variants = [_variant(n) for n in (variant_names or list(VARIANTS))]
    for v in variants:
        _require_aip(v)

    if tasks_explicit:
        missing = [t for t in tasks_explicit if not (VENDOR_SKILLSBENCH / "tasks" / t / "instruction.md").exists()]
        if missing:
            raise typer.BadParameter(f"task(s) not found: {missing}")
        tasks = sorted(set(tasks_explicit))
    else:
        tasks = _discover_tasks(pattern)
    work: list[tuple[str, Variant]] = []
    skipped = 0
    for task in tasks:
        for v in variants:
            if not force and _already_done(task, v):
                skipped += 1
                continue
            work.append((task, v))
    if limit > 0:
        work = work[:limit]

    typer.echo(f"Batch convert: {len(tasks)} tasks × {len(variants)} variant(s) = {len(tasks) * len(variants)} packs")
    typer.echo(f"  to author: {len(work)}   skipped (valid pack exists): {skipped}")
    typer.echo(f"  concurrency: {concurrency}   author model: {author_model}")
    typer.echo(f"  est. cost: ~${4 * len(work):.0f} (measured mean $4.19/pack with Opus 5.5)   "
               f"est. wall clock: ~{12 * len(work) / max(concurrency, 1):.0f} min")
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
            ex.submit(_convert_one, task, v, author_model, force, stage_data): (task, v.name)
            for task, v in work
        }
        total = len(futures)
        for fut in concurrent.futures.as_completed(futures):
            task, vn, rc, secs, tail = fut.result()
            done += 1
            status = "OK" if rc == 0 else f"FAIL(rc={rc})"
            if rc != 0:
                failed += 1
            typer.echo(
                f"[{done:>3}/{total}] {status:9s} {task:40s} --variant {vn:10s} "
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
        [], "--task", help="Repeatable. Task name under vendor/skillsbench/tasks/. Overrides the config's list."
    ),
    models_explicit: list[str] = typer.Option(
        [], "--model", help="Repeatable. Model string (agent-specific). Overrides the config's list."
    ),
    modes_explicit: list[Mode] = typer.Option(
        [], "--mode", case_sensitive=False,
        help="Repeatable. Scenarios without a variant (noskill, human-curated, selfgen-skill-creator); "
             "skill and aip-runtime scenarios need a config `scenarios:` entry.",
    ),
    scenarios_explicit: list[str] = typer.Option(
        [], "--scenario", help="Repeatable. Run only these of the config's scenarios, by name."
    ),
    trials: Optional[int] = typer.Option(
        None, "--trials", help="Trials per (task, model, scenario). Default 1."
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
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the campaign (cells, scenarios, first command) and exit; spends nothing."),
    decision_model: Optional[bool] = typer.Option(
        None, "--decision-model/--no-decision-model",
        help="aip-runtime scenarios: put TYPESAFE_API_KEY in the solver's environment so the aip client "
             "answers decision steps with the decision model. Config key `decision_model`. Default off.",
    ),
    agent_env: list[str] = typer.Option(
        [], "--agent-env", help="Repeatable KEY=VALUE for the solver process. Config key `agent_env` (list)."
    ),
) -> None:
    """Run a (task × model × scenario × trial) eval matrix concurrently with live progress.

    A config lists `scenarios:` as `{name, mode, variant?, nudge?}` mappings (a bare mode
    name is a scenario without a variant); `modes:` is accepted as the same shorthand.
    """
    from aip_skillbench.run_matrix import parse_scenarios, run_matrix

    cfg: dict = {}
    if config:
        import yaml
        if not config.exists():
            raise typer.BadParameter(f"config not found: {config}")
        cfg = yaml.safe_load(config.read_text()) or {}

    tasks_resolved = list(tasks_explicit) or list(cfg.get("tasks", []))
    models_resolved = list(models_explicit) or list(cfg.get("models", []))
    if modes_explicit:
        scenarios = parse_scenarios([m.value for m in modes_explicit])
    elif "scenarios" in cfg:
        scenarios = parse_scenarios(list(cfg["scenarios"]))
    elif "modes" in cfg:
        scenarios = parse_scenarios(list(cfg["modes"]))
    else:
        scenarios = parse_scenarios([Mode.noskill.value, Mode.human_curated.value, Mode.selfgen_skill_creator.value])
    if scenarios_explicit:
        known = {s.name for s in scenarios}
        unknown = [n for n in scenarios_explicit if n not in known]
        if unknown:
            raise typer.BadParameter(f"unknown scenario(s) {unknown}; the config has {sorted(known)}", param_hint="'--scenario'")
        scenarios = [s for s in scenarios if s.name in scenarios_explicit]
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
    agent_env_resolved = list(agent_env) or [str(x) for x in cfg.get("agent_env", [])]

    rc = run_matrix(
        tasks=tasks_resolved,
        models=models_resolved,
        scenarios=scenarios,
        trials=trials_resolved,
        concurrency=concurrency_resolved,
        out=out_resolved,
        agent=agent_resolved,
        sandbox=sandbox_resolved,
        yes=yes,
        force=force,
        shuffle=shuffle,
        decision_model=decision_resolved,
        agent_env=agent_env_resolved,
        dry_run=dry_run,
    )
    raise typer.Exit(rc)


@app.command("matrix-view")
def matrix_view_cmd(
    out: Optional[Path] = typer.Argument(
        None, help="Campaign dir (the run-matrix --out). Default: newest dir under runs/."
    ),
    watch: bool = typer.Option(False, "--watch", "-w", help="Keep refreshing until Ctrl-C."),
    interval: float = typer.Option(10.0, "--interval", help="Seconds between refreshes with --watch."),
) -> None:
    """Show the run-matrix progress view for a campaign, from its files (any terminal, any time)."""
    from aip_skillbench.run_matrix import matrix_view

    if out is None:
        candidates = sorted(
            (d for d in (ROOT / "runs").glob("*/campaign.json")), key=lambda p: p.stat().st_mtime
        )
        if not candidates:
            raise typer.BadParameter("no campaign dirs under runs/")
        out = candidates[-1].parent
    raise typer.Exit(matrix_view(out, watch, interval))


@app.command()
def reward(jobs_subdir: Path) -> None:
    """Print the reward(s) under a jobs/ output directory."""
    if not jobs_subdir.exists():
        raise typer.BadParameter(f"not found: {jobs_subdir}")
    for r in sorted(jobs_subdir.glob("*/verifier/reward.txt")):
        typer.echo(f"{r.parent.parent.name}: {r.read_text().strip()}")


if __name__ == "__main__":
    app()
