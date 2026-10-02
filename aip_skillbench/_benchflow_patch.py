"""Monkey-patches for benchflow, loaded by `aip_skillbench/__init__.py` so every
CLI entry point (and the `bench` subprocess via `_bench_launcher`) gets them.

1. Pre-create /app and /solution in the sandbox.
   `benchflow.rollout._start_env_and_upload` unconditionally uploads task
   assets to `/app/skills` and `/solution` after `env.start()`, but many
   SkillsBench task Dockerfiles use `WORKDIR /root` and never create `/app`,
   which makes the upload fail (Docker compose cp: "Could not find the file
   /app in container"). We `mkdir -p` the expected mount points first.

2. Install the `aip` CLI into the trial container (AIP modes only).
   AIP 0.4a0 skills carry a runtime block that tells the agent to drive the
   procedure with `aip run` when the CLI is present and to execute the graph
   itself otherwise. To measure the protocol-client path, the CLI has to exist
   before the agent starts. When `AIP_SKILLBENCH_WHEEL` names a wheel, it is
   uploaded and pip-installed into a venv at /opt/aip created with
   --system-site-packages, so execution-step scripts (run with that venv's
   interpreter) see the task's preinstalled packages while aip's own
   dependencies stay out of system Python (benchflow's verifier scans system
   Python for pytest plugins). `--ignore-requires-python` covers the wheel's
   `>=3.14` floor (the package imports fine on 3.12).
   A failed install raises: an AIP-mode trial without the client is a
   different experimental condition and must not pass silently.

Track these here — if they end up upstream in benchflow, delete and remove
the import.
"""

from __future__ import annotations

import logging
import os
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any

from benchflow import rollout as _rollout
from benchflow import sdk as _sdk

from aip_skillbench._aip import NUDGE_ENV, WHEEL_ENV

logger = logging.getLogger(__name__)


# Runs as root, before the sandbox user is created and before the agent installs.
_INSTALL_AIP_SCRIPT = r"""
set -e
W={wheel}
VENV=/opt/aip
# A venv that sees the image's site-packages: `aip` and its own dependencies stay
# out of system Python (benchflow's verifier scans system Python for pytest
# plugins and would otherwise pass e.g. `-p anyio` to an isolated pytest), while
# execution-step scripts, run with the venv's interpreter, still see the task's
# preinstalled packages.
if ! python3 -m venv --system-site-packages "$VENV" >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq python3-venv >/dev/null 2>&1
    python3 -m venv --system-site-packages "$VENV"
  else
    echo "aip install: python3 -m venv unavailable and no apt-get" >&2
    exit 2
  fi
fi
"$VENV/bin/python" -m pip install --quiet --ignore-requires-python "$W" >/dev/null 2>&1 \
  || "$VENV/bin/python" -m pip install --ignore-requires-python "$W"
ln -sf "$VENV/bin/aip" /usr/local/bin/aip
chmod -R a+rX "$VENV"
aip --help >/dev/null
echo "aip installed at /usr/local/bin/aip -> $VENV ($("$VENV/bin/python" --version 2>&1), system site-packages visible)"
"""


# Copied into /home/<sandbox_user>/.claude/ by benchflow's setup_sandbox_user (the
# .claude dir is one of the home dirs it materialises from /root), where Claude Code
# loads it as user memory.
_NUDGE_MEMORY = """\
# AIP skills

The `aip` CLI is installed on this machine. When a skill's SKILL.md contains an
AIP runtime block, run the procedure through it exactly as the block says:
`aip run <skill folder> --input <start.json>`, then `aip resume` at each pause,
until the output has "done": true. Do not execute the steps by hand when `aip`
is available.
"""

_NUDGE_SCRIPT = r"""
set -e
mkdir -p /root/.claude
cat > /root/.claude/CLAUDE.md <<'EOF'
{memory}EOF
chmod 644 /root/.claude/CLAUDE.md
echo "aip nudge written to /root/.claude/CLAUDE.md"
"""


async def _install_aip(env: Any, wheel: Path) -> None:
    target = f"/tmp/{wheel.name}"  # pip needs the real wheel filename
    await env.upload_file(wheel, target)
    script = _INSTALL_AIP_SCRIPT.format(wheel=shlex.quote(target))
    result = await env.exec(script, timeout_sec=600)
    rc = getattr(result, "return_code", 0)
    out = (getattr(result, "stdout", "") or "").strip()
    err = (getattr(result, "stderr", "") or "").strip()
    if rc != 0:
        raise RuntimeError(f"aip CLI install failed in container (rc={rc}):\n{out}\n{err}")
    logger.info("aip-skillbench: %s", out.splitlines()[-1] if out else "aip installed")


async def _patched_start_env_and_upload(
    env: Any, task_path: Path, timing: dict
) -> None:
    """Drop-in replacement that ensures /app and /solution exist first, then
    installs the aip CLI when an AIP mode asked for it."""
    t0 = datetime.now()
    await env.start(force_build=False)
    timing["environment_setup"] = (datetime.now() - t0).total_seconds()
    # The fix: create the dirs benchflow is about to upload into, regardless
    # of what the task's Dockerfile set as WORKDIR.
    result = await env.exec("mkdir -p /app /solution", timeout_sec=10)
    if getattr(result, "return_code", 0) != 0:
        logger.warning(
            "Pre-upload mkdir failed: %s",
            getattr(result, "stderr", None) or getattr(result, "stdout", ""),
        )
    if (task_path / "instruction.md").exists():
        await env.upload_file(task_path / "instruction.md", "/instruction.md")
    task_skills = task_path / "environment" / "skills"
    if task_skills.is_dir():
        await env.upload_dir(task_skills, "/app/skills")
    if (task_path / "solution").is_dir():
        await env.upload_dir(task_path / "solution", "/solution")

    wheel = os.environ.get(WHEEL_ENV)
    if wheel:
        t1 = datetime.now()
        await _install_aip(env, Path(wheel))
        timing["aip_install"] = (datetime.now() - t1).total_seconds()
        if os.environ.get(NUDGE_ENV) == "1":
            result = await env.exec(_NUDGE_SCRIPT.format(memory=_NUDGE_MEMORY), timeout_sec=30)
            if getattr(result, "return_code", 0) != 0:
                raise RuntimeError(f"aip nudge write failed: {getattr(result, 'stderr', '')}")
            timing["aip_nudge"] = True


_rollout._start_env_and_upload = _patched_start_env_and_upload
# sdk.py captured the original by value via `from benchflow.rollout import …`,
# so we have to patch the binding in that module too.
_sdk._start_env_and_upload = _patched_start_env_and_upload
logger.info("Patched benchflow._start_env_and_upload (pre-create /app /solution; aip CLI install)")
