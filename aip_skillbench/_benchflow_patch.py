"""Monkey-patch benchflow to pre-create /app and /solution in the sandbox.

`benchflow.rollout._start_env_and_upload` unconditionally uploads task
assets to `/app/skills` and `/solution` after `env.start()`, but many
SkillsBench task Dockerfiles use `WORKDIR /root` and never create `/app`,
which makes the upload fail (Docker compose cp: "Could not find the file
/app in container"). We `mkdir -p` the expected mount points before
either upload runs.

Loaded by `aip_skillbench/__init__.py` so every CLI entry point gets it.
Track this patch here — if it ends up upstream in benchflow, delete this
file and remove the import.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from benchflow import rollout as _rollout
from benchflow import sdk as _sdk

logger = logging.getLogger(__name__)


async def _patched_start_env_and_upload(
    env: Any, task_path: Path, timing: dict
) -> None:
    """Drop-in replacement that ensures /app and /solution exist first."""
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


_rollout._start_env_and_upload = _patched_start_env_and_upload
# sdk.py captured the original by value via `from benchflow.rollout import …`,
# so we have to patch the binding in that module too.
_sdk._start_env_and_upload = _patched_start_env_and_upload
logger.info("Patched benchflow._start_env_and_upload to pre-create /app /solution")
