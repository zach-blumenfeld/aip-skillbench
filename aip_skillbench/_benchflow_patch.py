"""Monkey-patches for benchflow, loaded by `aip_skillbench/__init__.py` so every
CLI entry point (and the `bench` subprocess via `_bench_launcher`) gets them.

1. Pre-create /app and /solution in the sandbox.
   `benchflow.rollout._start_env_and_upload` unconditionally uploads task
   assets to `/app/skills` and `/solution` after `env.start()`, but many
   SkillsBench task Dockerfiles use `WORKDIR /root` and never create `/app`,
   which makes the upload fail (Docker compose cp: "Could not find the file
   /app in container"). We `mkdir -p` the expected mount points first.

2. AIP container setup for the `aip-runtime` mode, driven by env vars `eval` sets
   (all run as root, before the sandbox user exists and the agent is installed):
   - `AIP_SKILLBENCH_WHEELS` (colon-separated host paths to the aip-spec and aip
     wheels): uploaded and installed with `--no-deps` into a venv at /opt/aip
     created with --system-site-packages, then their runtime dependencies by name
     from PyPI. The aip wheel pins `aip-spec @ git+…`, and many task images have
     no git, hence wheels plus named deps. The venv keeps aip's dependencies out
     of system Python (benchflow's verifier scans system Python for pytest
     plugins) while execution-step scripts still see the task's preinstalled
     packages. `--ignore-requires-python` covers the aip wheel's `>=3.14` floor
     (it imports fine on 3.12). `aip` and `aip-spec` are symlinked into
     /usr/local/bin. Timing key `aip_install`.
   - `AIP_SKILLBENCH_SERVER=1`: starts `aip server` (filesystem backend, catalog
     at /opt/aip/catalog, 127.0.0.1:8000, no token needed on localhost) detached
     with `setsid nohup`, so it outlives the `docker compose exec` that started
     it, and waits up to 60 s for /catalog. Timing key `aip_server`. Scripts run
     by the server run as root (the solver is the sandbox user).
   - `AIP_SKILLBENCH_PUBLISH` (host path of one skill folder): uploaded to
     /opt/aip/packs/<name> and published with `aip publish`; the printed
     `name@revision` goes to the log. Timing key `aip_publish`.
   Any failure raises: an AIP-mode trial without its client, server, or
   procedure is a different experimental condition and must not pass silently.

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

from aip_skillbench._aip import NUDGE_ENV, PUBLISH_ENV, SERVER_ENV, WHEEL_ENV

logger = logging.getLogger(__name__)

AIP_VENV = "/opt/aip"
AIP_SERVER_PORT = 8000
AIP_SERVER_URL = f"http://127.0.0.1:{AIP_SERVER_PORT}"
AIP_PACKS_DIR = f"{AIP_VENV}/packs"
# Runtime dependencies of the two wheels plus aip's `server` extra (neo4j omitted:
# the server runs the filesystem backend).
AIP_DEPS = "httpx jsonschema pydantic pyyaml typesafe-sdk fastapi uvicorn"


# Runs as root, before the sandbox user is created and before the agent installs.
_INSTALL_AIP_SCRIPT = r"""
set -e
VENV={venv}
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
PIP="$VENV/bin/python -m pip"
# --no-deps: the aip wheel pins aip-spec to a git URL and many images have no git.
$PIP install --quiet --ignore-requires-python --no-deps {spec_wheel} {aip_wheel} >/dev/null 2>&1 \
  || $PIP install --ignore-requires-python --no-deps {spec_wheel} {aip_wheel}
$PIP install --quiet {deps} >/dev/null 2>&1 || $PIP install {deps}
ln -sf "$VENV/bin/aip" /usr/local/bin/aip
ln -sf "$VENV/bin/aip-spec" /usr/local/bin/aip-spec
# World-readable for the sandbox user; skip packs/, which may be a read-only mount.
find "$VENV" -path "$VENV/packs" -prune -o -exec chmod a+rX {{}} +
aip --help >/dev/null
aip-spec --version >/dev/null
echo "aip installed at /usr/local/bin/aip -> $VENV ($("$VENV/bin/python" --version 2>&1), system site-packages visible)"
"""

# Started from / so the server does not pick up a task's ./.env or ./aip-server.toml.
# setsid + nohup + stdin from /dev/null detaches it from the exec session.
_SERVER_SCRIPT = r"""
set -e
mkdir -p {venv}/catalog
cd /
{env}setsid nohup {venv}/bin/aip server --backend filesystem --root {venv}/catalog \
  --host 127.0.0.1 --port {port} --log-level warning > /var/log/aip-server.log 2>&1 < /dev/null &
for i in $(seq 1 60); do
  if python3 -c "import urllib.request; urllib.request.urlopen('{url}/catalog', timeout=2)" >/dev/null 2>&1; then
    echo "aip server ready at {url} after ${{i}}s"
    exit 0
  fi
  sleep 1
done
echo "aip server not ready after 60s; log tail:" >&2
tail -n 40 /var/log/aip-server.log >&2 || true
exit 1
"""

_PUBLISH_SCRIPT = r"""
set -e
AIP_SERVER={url} {venv}/bin/aip publish {pack}
"""


def install_script(spec_wheel: str, aip_wheel: str) -> str:
    """Shell script that installs the two wheels (container paths) into /opt/aip."""
    return _INSTALL_AIP_SCRIPT.format(
        venv=AIP_VENV,
        spec_wheel=shlex.quote(spec_wheel),
        aip_wheel=shlex.quote(aip_wheel),
        deps=AIP_DEPS,
    )


def server_script(env: dict[str, str] | None = None) -> str:
    """Shell script that starts `aip server` detached and waits until it answers."""
    prefix = "".join(f"{k}={shlex.quote(v)} " for k, v in (env or {}).items())
    return _SERVER_SCRIPT.format(
        venv=AIP_VENV, port=AIP_SERVER_PORT, url=AIP_SERVER_URL, env=prefix
    )


def publish_script(pack: str) -> str:
    """Shell script that publishes one skill folder (container path) to the server."""
    return _PUBLISH_SCRIPT.format(url=AIP_SERVER_URL, venv=AIP_VENV, pack=shlex.quote(pack))


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


async def _exec_or_raise(env: Any, what: str, script: str, timeout_sec: int) -> str:
    result = await env.exec(script, timeout_sec=timeout_sec)
    rc = getattr(result, "return_code", 0)
    out = (getattr(result, "stdout", "") or "").strip()
    err = (getattr(result, "stderr", "") or "").strip()
    if rc != 0:
        raise RuntimeError(f"{what} failed in container (rc={rc}):\n{out}\n{err}")
    return out


async def _install_aip(env: Any, wheels: list[Path]) -> None:
    spec = [w for w in wheels if w.name.startswith("aip_spec-")]
    aip = [w for w in wheels if w.name.startswith("aip-")]
    if len(spec) != 1 or len(aip) != 1:
        raise RuntimeError(f"{WHEEL_ENV} needs one aip_spec-*.whl and one aip-*.whl, got {wheels}")
    for w in (spec[0], aip[0]):
        await env.upload_file(w, f"/tmp/{w.name}")  # pip needs the real wheel filename
    script = install_script(f"/tmp/{spec[0].name}", f"/tmp/{aip[0].name}")
    out = await _exec_or_raise(env, "aip install", script, timeout_sec=600)
    logger.info("aip-skillbench: %s", out.splitlines()[-1] if out else "aip installed")


async def _start_aip_server(env: Any) -> None:
    out = await _exec_or_raise(env, "aip server start", server_script(), timeout_sec=120)
    logger.info("aip-skillbench: %s", out.splitlines()[-1] if out else "aip server ready")


async def _publish_pack(env: Any, pack: Path) -> str:
    target = f"{AIP_PACKS_DIR}/{pack.name}"
    await env.exec(f"mkdir -p {AIP_PACKS_DIR}", timeout_sec=10)
    await env.upload_dir(pack, target)
    out = await _exec_or_raise(env, "aip publish", publish_script(target), timeout_sec=120)
    ref = out.splitlines()[-1].strip() if out else ""
    if "@" not in ref:
        raise RuntimeError(f"aip publish printed no name@revision for {pack}:\n{out}")
    logger.info("aip-skillbench: published %s", ref)
    return ref


async def _patched_start_env_and_upload(
    env: Any, task_path: Path, timing: dict
) -> None:
    """Drop-in replacement that ensures /app and /solution exist first, then
    runs the AIP container setup (install, server, publish) the env asks for."""
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

    wheels = [Path(w) for w in os.environ.get(WHEEL_ENV, "").split(":") if w]
    if wheels:
        t1 = datetime.now()
        await _install_aip(env, wheels)
        timing["aip_install"] = (datetime.now() - t1).total_seconds()
    if os.environ.get(SERVER_ENV) == "1":
        if not wheels:
            raise RuntimeError(f"{SERVER_ENV}=1 needs {WHEEL_ENV}")
        t1 = datetime.now()
        await _start_aip_server(env)
        timing["aip_server"] = (datetime.now() - t1).total_seconds()
    pack = os.environ.get(PUBLISH_ENV)
    if pack:
        if os.environ.get(SERVER_ENV) != "1":
            raise RuntimeError(f"{PUBLISH_ENV} needs {SERVER_ENV}=1")
        t1 = datetime.now()
        await _publish_pack(env, Path(pack))
        timing["aip_publish"] = (datetime.now() - t1).total_seconds()
    if wheels and os.environ.get(NUDGE_ENV) == "1":
        result = await env.exec(_NUDGE_SCRIPT.format(memory=_NUDGE_MEMORY), timeout_sec=30)
        if getattr(result, "return_code", 0) != 0:
            raise RuntimeError(f"aip nudge write failed: {getattr(result, 'stderr', '')}")
        timing["aip_nudge"] = True


_rollout._start_env_and_upload = _patched_start_env_and_upload
# sdk.py captured the original by value via `from benchflow.rollout import …`,
# so we have to patch the binding in that module too.
_sdk._start_env_and_upload = _patched_start_env_and_upload
logger.info("Patched benchflow._start_env_and_upload (pre-create /app /solution; aip container setup)")
