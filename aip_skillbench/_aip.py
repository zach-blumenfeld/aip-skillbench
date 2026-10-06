"""AIP toolchain helpers shared by cli.py and run_matrix.py.

Owns the paths and small subprocess wrappers around the two AIP clones under
`.claude/skills-src/` (populated by `aip-skillbench bootstrap`): `aip` (runtime,
client, server) and `aip-spec` (the format, its validator, the authoring skill).

- `aip_cli()`           how to invoke the validator (`aip-spec`) on the host
- `aip_wheel()`         the aip wheel `bootstrap` built, uploaded into trial containers
- `aip_spec_wheel()`    the aip-spec wheel, likewise
- `runtime_skill_dir()` a skills dir holding only `aip-runtime/SKILL.md`
- `validate_pack()`     `aip-spec validate` on one skill folder (outdated block = failure)
- `validate_packs()`    every skill folder under a generated-skills subdir
- `read_aip_ref()`      the pins recorded by `bootstrap`
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AIP_SRC_DIR = ROOT / ".claude" / "skills-src" / "aip"
AIP_REMOTE = "git@github.com:zach-blumenfeld/aip.git"
AIP_DEFAULT_REF = "aip-0.5a0"
AIP_SPEC_DIR = ROOT / ".claude" / "skills-src" / "aip-spec"
AIP_SPEC_REMOTE = "git@github.com:zach-blumenfeld/aip-spec.git"
AIP_SPEC_DEFAULT_REF = "v0.5a1"
AIP_BUILD_DIR = ROOT / "build" / "aip"
# `aip skill install --path` writes aip/ (authoring skill) and aip-runtime/ here.
HOST_SKILLS_DIR = ROOT / "build" / "skills"
GENERATED_SKILLS = ROOT / "generated-skills"
AIP_REF_FILE = GENERATED_SKILLS / "AIP_REF.json"

# Where the in-container `aip server` listens (aip-runtime mode); the agent gets
# AIP_SERVER set to this.
AIP_SERVER_PORT = 8000
AIP_SERVER_URL = f"http://127.0.0.1:{AIP_SERVER_PORT}"

# Env vars read by aip_skillbench._benchflow_patch inside the `bench` subprocess.
# Colon-separated host paths of the aip-spec and aip wheels to install in the container.
WHEEL_ENV = "AIP_SKILLBENCH_WHEELS"
# "1" to start `aip server` in the container (needs WHEEL_ENV).
SERVER_ENV = "AIP_SKILLBENCH_SERVER"
# JSON object of extra environment for the server process only (e.g. TYPESAFE_API_KEY
# under `--decision-model`); never given to the agent.
SERVER_EXTRA_ENV = "AIP_SKILLBENCH_SERVER_ENV"
# Host path of one skill folder to publish to that server (needs SERVER_ENV).
PUBLISH_ENV = "AIP_SKILLBENCH_PUBLISH"
# Mode name (`aip-spec` or `aip-runtime`): write that mode's CLAUDE.md memory in the
# sandbox user's home. Unset = no memory (`--no-aip-nudge`, and every other mode).
NUDGE_ENV = "AIP_SKILLBENCH_NUDGE"


def aip_cli() -> list[str]:
    """Command prefix for the host validator: the uv-tool `aip-spec`, else the clone."""
    if shutil.which("aip-spec"):
        return ["aip-spec"]
    return ["uv", "run", "--project", str(AIP_SPEC_DIR), "aip-spec"]


def _latest_wheel(pattern: str) -> Path:
    wheels = sorted(AIP_BUILD_DIR.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not wheels:
        raise FileNotFoundError(
            f"no {pattern} under {AIP_BUILD_DIR}; run `aip-skillbench bootstrap --force`"
        )
    return wheels[-1]


def aip_wheel() -> Path:
    return _latest_wheel("aip-*.whl")


def aip_spec_wheel() -> Path:
    return _latest_wheel("aip_spec-*.whl")


def runtime_skill_dir() -> Path:
    """Skills dir with only `aip-runtime/SKILL.md`, mounted in `aip-runtime` trials."""
    return ROOT / "build" / "aip-runtime-skill"


def format_version() -> str | None:
    """The format version the validator reports (`aip-spec --version`)."""
    try:
        out = subprocess.run([*aip_cli(), "--version"], capture_output=True, text=True, cwd=ROOT)
    except FileNotFoundError:
        return None
    m = re.search(r"\d+\.\d+\w*", out.stdout)
    return m.group(0) if out.returncode == 0 and m else None


def read_aip_ref() -> dict:
    if not AIP_REF_FILE.exists():
        return {}
    return json.loads(AIP_REF_FILE.read_text())


# Validator warnings that fail the gate anyway: a campaign must not mix block versions.
STRICT_WARNINGS = ("runtime_block_outdated",)


def validate_pack(skill_dir: Path) -> tuple[bool, str]:
    """Run `aip-spec validate` on one skill folder. Returns (ok, combined output).

    Warnings come as JSON lines on stderr with exit 0; any kind in STRICT_WARNINGS
    is a failure, reported by its validator message.
    """
    proc = subprocess.run(
        [*aip_cli(), "validate", str(skill_dir)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
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


def skill_dirs(pack_root: Path) -> list[Path]:
    if not pack_root.is_dir():
        return []
    return sorted(p for p in pack_root.iterdir() if p.is_dir() and (p / "SKILL.md").exists())


def validate_packs(pack_root: Path) -> list[str]:
    """Validate every skill folder under a generated-skills subdir; return failure lines."""
    failures: list[str] = []
    dirs = skill_dirs(pack_root)
    if not dirs:
        return [f"{pack_root}: no skill folders with SKILL.md"]
    for d in dirs:
        ok, out = validate_pack(d)
        if not ok:
            failures.append(f"{d}:\n    " + out.replace("\n", "\n    "))
    return failures
