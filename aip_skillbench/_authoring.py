"""Sandboxed AIP authoring for `aip-skillbench convert`.

The authoring session (`claude -p`) runs inside a throwaway workspace that holds
only what the prompt is allowed to see:

    build/authoring/<task>-<from>-<stamp>/
    ├── .claude/skills/aip/      copy of the aip-spec authoring skill (build/skills/aip/)
    ├── inputs/
    │   ├── skills/<name>/…      curated skills            (--from curated)
    │   ├── environment/Dockerfile                          (--from curated)
    │   └── instruction.md                                  (--from instruction)
    ├── out/<skill-name>/…       what the author writes
    └── scratch/                 functional-test inputs (not kept)

No `--add-dir` is granted, the prompt only names workspace-relative paths, and the
repo (with the task's tests/ and solution/) is nowhere in the session's view. Claude
Code still runs with permissions skipped so the checklist can execute `aip` and the
scripts it writes, so this is not a kernel sandbox: the enforcement is the audit.
Every tool call is captured as a stream-json transcript and scanned for paths that
leave the workspace; a hit fails the conversion. Prompt, transcript, audit, and
metadata are kept next to the pack under generated-skills/<task>/_authoring/<from>/
(a sibling of the mounted pack dir, so trials never see them).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from aip_skillbench._aip import HOST_SKILLS_DIR, ROOT, read_aip_ref

AUTHORING_BUILD = ROOT / "build" / "authoring"

_AIP_SKILL_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
_INPUT_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")

# Paths a session may legitimately touch outside its workspace: interpreters, caches,
# temp dirs, and the aip CLI it runs.
# The AIP tool's own source: the host `aip`/`aip-spec` CLIs are editable installs of these
# clones, so an author reading how the runtime invokes scripts lands here. Not task data.
_TOOL_SRC_PREFIXES = tuple(
    str(p) + "/" for p in (ROOT / ".claude" / "skills-src", ROOT / ".claude" / "skills")
)
_ALLOWED_PREFIXES = (
    *_TOOL_SRC_PREFIXES,

    "/tmp/", "/private/tmp/", "/private/var/folders/", "/var/folders/",
    "/usr/", "/bin/", "/opt/", "/etc/", "/dev/", "/proc/", "/Library/", "/System/",
    str(Path.home() / ".cache") + "/", str(Path.home() / ".local") + "/",
    str(Path.home() / ".claude") + "/",
)
# Anything mentioning these is a violation regardless of prefix.
_FORBIDDEN_FRAGMENTS = ("vendor/skillsbench", "/tests/", "/solution/", "test_outputs", "solve.sh")
# A path right after `$(pwd)` or `${VAR}` is relative to that expansion, not absolute.
_PATH_RE = re.compile(r"(?<![\w.)}-])(/[^\s\"'`<>|;&()\[\]{}]+)")


class AuditViolation(Exception):
    pass


def make_workspace(task: str, from_: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    ws = AUTHORING_BUILD / f"{task}-{from_}-{stamp}"
    ws.mkdir(parents=True)
    shutil.copytree(HOST_SKILLS_DIR / "aip", ws / ".claude" / "skills" / "aip", ignore=_AIP_SKILL_IGNORE, symlinks=True)
    (ws / "inputs").mkdir()
    (ws / "out").mkdir()
    (ws / "scratch").mkdir()
    return ws


SAMPLE_BYTES = 2048
_ENV_SKIP = {"skills", "_deps", "Dockerfile", "__pycache__", ".DS_Store"}


def _sample_file(src: Path, dst: Path) -> None:
    """First SAMPLE_BYTES of a file, whole lines when it is text, raw bytes otherwise."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes()[: SAMPLE_BYTES + 512]
    try:
        text = data.decode("utf-8")
        cut = text[:SAMPLE_BYTES]
        if len(text) > SAMPLE_BYTES and "\n" in cut:
            cut = cut[: cut.rfind("\n") + 1]
        dst.write_text(cut)
    except UnicodeDecodeError:
        dst.write_bytes(data[:SAMPLE_BYTES])


def stage_environment(ws: Path, env_dir: Path, mode: str) -> list[str]:
    """The task's environment/ (inputs the skill will run on), never tests/ or solution/.

    mode "full" (default, decided 2026-10-06): the files as they are, so the author can
    functional-test the distilled procedure against the real inputs the way a human
    skill author would; the author never sees tests/ or solution/, but it can tune to
    the instance, and that is accepted as part of the condition (recorded in
    meta.json). mode "sample": every file truncated to its first SAMPLE_BYTES under
    its real relative name plus MANIFEST.md with true sizes: format only, the stricter
    condition. mode "none": only the Dockerfile.
    """
    out = ws / "inputs" / "environment"
    out.mkdir(parents=True, exist_ok=True)
    dockerfile = env_dir / "Dockerfile"
    if dockerfile.exists():
        shutil.copy2(dockerfile, out / "Dockerfile")
    staged: list[str] = []
    if mode == "none":
        return staged
    files = sorted(
        p for p in env_dir.rglob("*")
        if p.is_file() and not any(part in _ENV_SKIP for part in p.relative_to(env_dir).parts)
    )
    lines = ["# Input files the skill will run on", "",
             "Relative to the task's environment folder; in the container they live where the",
             "task's instructions say (usually under /root/). Sizes are the real files'.", ""]
    if mode == "sample":
        lines += [f"These copies are TRUNCATED to their first {SAMPLE_BYTES} bytes: enough to see the",
                  "format (header lines, delimiters, column order, cadence, encoding), not the content.",
                  "Test loaders and defaults against them; do not expect the real signal in them.", ""]
    for f in files:
        rel = f.relative_to(env_dir)
        size = f.stat().st_size
        lines.append(f"- `{rel}`  {size:,} bytes")
        if mode == "full":
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, out / rel)
        else:
            _sample_file(f, out / rel)
        staged.append(str(rel))
    (out / "MANIFEST.md").write_text("\n".join(lines) + "\n")
    return staged


def stage_curated(ws: Path, curated_root: Path, env_dir: Path | None, data_mode: str = "full") -> list[str]:
    names: list[str] = []
    for src in sorted(p for p in curated_root.iterdir() if p.is_dir() and (p / "SKILL.md").exists()):
        shutil.copytree(src, ws / "inputs" / "skills" / src.name, ignore=_INPUT_IGNORE)
        names.append(src.name)
    if env_dir and env_dir.is_dir():
        stage_environment(ws, env_dir, data_mode)
    return names


def stage_instruction(ws: Path, instruction: Path) -> None:
    shutil.copy2(instruction, ws / "inputs" / "instruction.md")


def run_author(ws: Path, prompt: str, model: str, api_key: str | None) -> tuple[int, Path]:
    """Run `claude -p` inside the workspace, capturing the stream-json transcript."""
    transcript = ws / "transcript.jsonl"
    (ws / "prompt.md").write_text(prompt)
    cmd = [
        "claude", "-p", prompt, "--model", model,
        "--output-format", "stream-json", "--verbose",
        "--dangerously-skip-permissions",
    ]
    env = os.environ.copy()
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    with open(transcript, "w") as fh:
        proc = subprocess.run(cmd, cwd=ws, env=env, stdout=fh, stderr=subprocess.PIPE, text=True)
    if proc.stderr.strip():
        (ws / "stderr.txt").write_text(proc.stderr)
    return proc.returncode, transcript


def _tool_calls(transcript: Path):
    for line in transcript.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("type") != "assistant":
            continue
        for c in e.get("message", {}).get("content", []) or []:
            if c.get("type") == "tool_use":
                yield c.get("name", ""), c.get("input", {})


# Which input fields carry paths the session actually acts on. File *contents*
# (Write/Edit) are not scanned: a doc may legitimately mention /path/to/x.
_PATH_FIELDS = {
    "Read": ("file_path",), "Write": ("file_path",), "Edit": ("file_path",),
    "MultiEdit": ("file_path",), "NotebookEdit": ("notebook_path",),
    "Bash": ("command",), "Glob": ("path",), "Grep": ("path",),
    "Agent": ("prompt",), "Task": ("prompt",), "Skill": ("args",),
}
_PLACEHOLDER_PREFIXES = ("/path/to", "/your/", "/example")


def _scan_text(text: str, ws_prefixes: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for frag in _FORBIDDEN_FRAGMENTS:
        if frag in text:
            hits.append(f"forbidden fragment {frag!r}")
    for m in _PATH_RE.finditer(text):
        p = m.group(1).rstrip("/.,:")
        if any(p == w.rstrip("/") or p.startswith(w) for w in ws_prefixes):
            continue
        if any(p.startswith(pre) for pre in _ALLOWED_PREFIXES + _PLACEHOLDER_PREFIXES):
            continue
        if "<" in p or ">" in p or "{" in p:
            continue
        if "/" not in p[1:]:
            continue  # a lone "/name" is a JSON pointer, a division, or a top-level dir, never a file we care about
        hits.append(p)
    return hits


def audit_transcript(transcript: Path, ws: Path) -> dict:
    """Every path-bearing tool-call field is checked for paths outside the workspace."""
    ws_prefixes = (str(ws.resolve()) + "/", str(ws) + "/")
    calls = 0
    outside: list[dict] = []
    for name, inp in _tool_calls(transcript):
        calls += 1
        fields = _PATH_FIELDS.get(name)
        if fields is None:
            texts = [json.dumps(inp)]  # unknown tool: scan everything
        else:
            texts = [str(inp.get(f, "")) for f in fields]
        hits: list[str] = []
        for t in texts:
            hits.extend(_scan_text(t, ws_prefixes))
        if hits:
            outside.append({"tool": name, "hits": sorted(set(hits)), "input": json.dumps(inp)[:400]})
    result_cost = None
    for line in transcript.read_text().splitlines():
        if '"type": "result"' in line or '"type":"result"' in line:
            try:
                result_cost = json.loads(line).get("total_cost_usd")
            except json.JSONDecodeError:
                pass
    return {"tool_calls": calls, "violations": outside, "ok": not outside, "total_cost_usd": result_cost}


def finalize(ws: Path, dst_root: Path, record_dir: Path, audit: dict, meta: dict, keep_workspace: bool) -> list[str]:
    """Move out/* into dst_root, keep the authoring record beside it, drop the workspace."""
    produced: list[str] = []
    dst_root.mkdir(parents=True, exist_ok=True)
    for child in sorted((ws / "out").iterdir()):
        target = dst_root / child.name
        if target.exists():
            shutil.rmtree(target) if target.is_dir() else target.unlink()
        shutil.move(str(child), str(target))
        produced.append(child.name)
    if record_dir.exists():
        shutil.rmtree(record_dir)
    record_dir.mkdir(parents=True)
    for name in ("prompt.md", "transcript.jsonl", "stderr.txt"):
        if (ws / name).exists():
            shutil.copy2(ws / name, record_dir / name)
    (record_dir / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    meta = {**meta, "produced": produced, "aip": read_aip_ref(), "workspace": str(ws)}
    (record_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    if not keep_workspace:
        shutil.rmtree(ws, ignore_errors=True)
    return produced
