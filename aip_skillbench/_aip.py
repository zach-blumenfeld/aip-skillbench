"""AIP toolchain helpers shared by cli.py, run_matrix.py, and _authoring.py.

Everything is per variant (aip_skillbench._variants): the clones, host CLIs, wheels,
authoring skill, runtime skill, and the validation gate all live under build/<variant>/,
populated by `aip-skillbench bootstrap`.

- `spec_cli(v)`          how to invoke that variant's `aip-spec` CLI (kind "aip")
- `aip_wheel(v)` / `aip_spec_wheel(v)`   the wheels bootstrap built, uploaded into trial containers
- `format_version(v)`    the format version the variant's validator reports
- `validate_pack(v, d)`  the variant's gate on one skill folder
- `validate_packs(v, root)`  every skill folder under a pack root
- `skill_dirs(root)`     the skill folders under a pack root
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

from aip_skillbench._variants import (  # noqa: F401  (re-exported for callers)
    GENERATED_SKILLS,
    REFS_FILE,
    ROOT,
    RUNTIME_VARIANTS,
    VARIANTS,
    Variant,
    dist_gate,
    read_refs,
    variant,
)

# Where the in-container `aip server` listens (aip-runtime mode); the agent gets
# AIP_SERVER set to this.
AIP_SERVER_PORT = 8000
AIP_SERVER_URL = f"http://127.0.0.1:{AIP_SERVER_PORT}"

# Env vars read by aip_skillbench._benchflow_patch inside the `bench` subprocess.
# Colon-separated host paths of the aip-spec and aip wheels to install in the container.
WHEEL_ENV = "AIP_SKILLBENCH_WHEELS"
# "1" to start `aip server` in the container (needs WHEEL_ENV).
SERVER_ENV = "AIP_SKILLBENCH_SERVER"
# JSON object of extra environment for the server process only (AIP_STEP_TIMEOUT). The
# server holds no model key: `--decision-model` gives TYPESAFE_API_KEY to the solver's
# environment, where the `aip` client resolves decisions.
SERVER_EXTRA_ENV = "AIP_SKILLBENCH_SERVER_ENV"
# Host path of one skill folder to publish to that server (needs SERVER_ENV).
PUBLISH_ENV = "AIP_SKILLBENCH_PUBLISH"
# Memory text to write (`skill` or `aip-runtime`) as CLAUDE.md in the sandbox user's home.
# Unset = no memory.
NUDGE_ENV = "AIP_SKILLBENCH_NUDGE"
# Agent name whose benchflow install command is baked into the task image as an extra
# layer before the build, so trials skip the per-container `npm install` (which stalls
# when many containers fetch the package at once). Unset = benchflow's runtime install.
BAKE_ENV = "AIP_SKILLBENCH_BAKE_AGENT"


def spec_cli(v: Variant) -> list[str]:
    """Command prefix for the variant's `aip-spec` CLI, run from its own clone so the gate
    does not depend on which version `uv tool install` last put on PATH."""
    if v.kind != "aip":
        raise ValueError(f"variant {v.name} has no aip-spec CLI")
    return ["uv", "run", "--quiet", "--project", str(v.src_dir("aip-spec")), "aip-spec"]


def _latest_wheel(v: Variant, pattern: str) -> Path:
    wheels = sorted(v.wheels_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not wheels:
        raise FileNotFoundError(
            f"no {pattern} under {v.wheels_dir}; run `aip-skillbench bootstrap --variant {v.name} --force`"
        )
    return wheels[-1]


def aip_wheel(v: Variant) -> Path:
    return _latest_wheel(v, "aip-*.whl")


def aip_spec_wheel(v: Variant) -> Path:
    return _latest_wheel(v, "aip_spec-*.whl")


def format_version(v: Variant) -> str | None:
    """The format version the variant's tooling reports.

    kind "aip": `aip-spec --version`. kind "aip-legacy": `metadata.aip.version` in the
    skill's frontmatter. kind "dist": none.
    """
    if v.kind == "aip":
        try:
            out = subprocess.run([*spec_cli(v), "--version"], capture_output=True, text=True, cwd=ROOT)
        except FileNotFoundError:
            return None
        m = re.search(r"\d+\.\d+\w*", out.stdout)
        return m.group(0) if out.returncode == 0 and m else None
    if v.kind == "aip-legacy":
        skill_md = v.authoring_skill / "SKILL.md"
        if not skill_md.exists():
            return None
        m = re.match(r"^---\s*\n(.*?)\n---", skill_md.read_text(), re.DOTALL)
        if not m:
            return None
        fm = yaml.safe_load(m.group(1)) or {}
        ver = ((fm.get("metadata") or {}).get("aip") or {}).get("version")
        return str(ver) if ver else None
    return None


# Validator warnings that fail the gate anyway: a campaign must not mix block versions.
STRICT_WARNINGS = ("runtime_block_outdated",)


def _validate_aip(v: Variant, skill_dir: Path) -> tuple[bool, str]:
    """`aip-spec validate` (kind "aip"). Warnings come as JSON lines on stderr with exit 0;
    any kind in STRICT_WARNINGS is a failure, reported by its validator message."""
    proc = subprocess.run([*spec_cli(v), "validate", str(skill_dir)], capture_output=True, text=True, cwd=ROOT)
    out = (proc.stdout + proc.stderr).strip()
    strict: list[str] = []
    for line in proc.stderr.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("kind") in STRICT_WARNINGS:
            strict.append(f"{item['kind']}: {item.get('message', '')}")
    if strict:
        return False, "\n".join(strict)
    return proc.returncode == 0, out


def _validate_legacy(v: Variant, skill_dir: Path) -> tuple[bool, str]:
    """The 0.3-era skill's own `scripts/validate.py` (a PEP 723 script: `uv run` resolves
    its jsonschema and pyyaml). Exit 0 = valid; errors are JSON lines on stderr."""
    script = v.authoring_skill / "scripts" / "validate.py"
    if not script.exists():
        return False, f"no validator at {script}; run `aip-skillbench bootstrap --variant {v.name} --force`"
    proc = subprocess.run(["uv", "run", "--quiet", str(script), str(skill_dir)], capture_output=True, text=True, cwd=ROOT)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def validate_pack(v: Variant, skill_dir: Path) -> tuple[bool, str]:
    """Run the variant's gate on one skill folder. Returns (ok, combined output)."""
    if v.kind == "aip":
        return _validate_aip(v, skill_dir)
    if v.kind == "aip-legacy":
        return _validate_legacy(v, skill_dir)
    problems = dist_gate(skill_dir)
    return not problems, "\n".join(problems) if problems else "ok"


def skill_dirs(pack_root: Path) -> list[Path]:
    if not pack_root.is_dir():
        return []
    return sorted(p for p in pack_root.iterdir() if p.is_dir() and (p / "SKILL.md").exists())


def validate_packs(v: Variant, pack_root: Path) -> list[str]:
    """Validate every skill folder under a pack root with the variant's gate; return failure lines."""
    failures: list[str] = []
    dirs = skill_dirs(pack_root)
    if not dirs:
        return [f"{pack_root}: no skill folders with SKILL.md"]
    for d in dirs:
        ok, out = validate_pack(v, d)
        if not ok:
            failures.append(f"{d}:\n    " + out.replace("\n", "\n    "))
    return failures
