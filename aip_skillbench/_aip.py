"""AIP toolchain helpers shared by cli.py and run_matrix.py.

Owns the paths and small subprocess wrappers around the AIP clone at
`.claude/skills/aip` (populated by `aip-skillbench bootstrap`):

- `aip_cli()`        how to invoke the `aip` CLI on the host
- `aip_wheel()`      the wheel `bootstrap` built, uploaded into trial containers
- `validate_pack()`  `aip validate` on one skill folder
- `validate_packs()` every skill folder under a generated-skills subdir
- `read_aip_ref()`   the ref/sha/format recorded by `bootstrap`
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AIP_DIR = ROOT / ".claude" / "skills" / "aip"
AIP_REMOTE = "git@github.com:zach-blumenfeld/aip.git"
AIP_DEFAULT_REF = "main"
AIP_BUILD_DIR = ROOT / "build" / "aip"
GENERATED_SKILLS = ROOT / "generated-skills"
AIP_REF_FILE = GENERATED_SKILLS / "AIP_REF.json"

# Env var read by aip_skillbench._benchflow_patch inside the `bench` subprocess:
# path to the aip wheel to install into every trial container.
WHEEL_ENV = "AIP_SKILLBENCH_WHEEL"
# Set to "1" to also write a CLAUDE.md memory in the sandbox user's home telling the
# agent to drive AIP skills through `aip run` (an explicit experimental condition).
NUDGE_ENV = "AIP_SKILLBENCH_NUDGE"


def aip_cli() -> list[str]:
    """Command prefix for the host `aip` CLI: the uv-tool install, else the clone."""
    if shutil.which("aip"):
        return ["aip"]
    return ["uv", "run", "--project", str(AIP_DIR), "aip"]


def aip_wheel() -> Path:
    wheels = sorted(AIP_BUILD_DIR.glob("aip-*.whl"), key=lambda p: p.stat().st_mtime)
    if not wheels:
        raise FileNotFoundError(
            f"no aip wheel under {AIP_BUILD_DIR}; run `aip-skillbench bootstrap --force`"
        )
    return wheels[-1]


def format_version() -> str | None:
    models = AIP_DIR / "src" / "aip" / "spec" / "models.py"
    if not models.exists():
        return None
    m = re.search(r'FORMAT_VERSION\s*=\s*"([^"]+)"', models.read_text())
    return m.group(1) if m else None


def read_aip_ref() -> dict:
    if not AIP_REF_FILE.exists():
        return {}
    return json.loads(AIP_REF_FILE.read_text())


def validate_pack(skill_dir: Path) -> tuple[bool, str]:
    """Run `aip validate` on one skill folder. Returns (ok, combined output)."""
    proc = subprocess.run(
        [*aip_cli(), "validate", str(skill_dir)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    out = (proc.stdout + proc.stderr).strip()
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
