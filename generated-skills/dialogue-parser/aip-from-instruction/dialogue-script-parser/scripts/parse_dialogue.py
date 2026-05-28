#!/usr/bin/env python3
"""Reference parser for the [SceneName] dialogue DSL.

Drop this file at /app/solution.py — the grading harness imports
parse_script directly. When run as a script, it also writes
/app/dialogue.json and /app/dialogue.dot from /app/script.txt.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

SCENE_HEADER_RE = re.compile(r"^\[([^\]]+)\]\s*$")
LINE_RE = re.compile(r"^(?P<speaker>[^:]+):\s*(?P<text>.+?)(?:\s*->\s*(?P<target>\S+))?\s*$")
CHOICE_RE = re.compile(r"^\d+\.\s*(?P<text>.+?)(?:\s*->\s*(?P<target>\S+))?\s*$")


def _split_blocks(text: str) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    current_id: str | None = None
    current_body: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = SCENE_HEADER_RE.match(line)
        if m:
            if current_id is not None:
                blocks.append((current_id, current_body))
            current_id = m.group(1).strip()
            current_body = []
        else:
            current_body.append(line)
    if current_id is not None:
        blocks.append((current_id, current_body))
    return blocks


def _is_choice_block(body: list[str]) -> bool:
    return bool(body) and all(re.match(r"^\d+\.\s+", line) for line in body)


def parse_script(text: str) -> dict[str, list[dict[str, Any]]]:
    """Convert dialogue script source into a node-edge graph.

    Returns {"nodes": [...], "edges": [...]} where:
      - nodes have keys id, text, speaker, type ("line" or "choice")
      - edges have keys from, to, text
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    defined: set[str] = set()
    blocks = _split_blocks(text)

    for scene_id, body in blocks:
        defined.add(scene_id)
        if _is_choice_block(body):
            nodes.append({"id": scene_id, "text": "", "speaker": "", "type": "choice"})
            for option in body:
                m = CHOICE_RE.match(option)
                if not m:
                    continue
                edges.append({
                    "from": scene_id,
                    "to": m.group("target") or "",
                    "text": m.group("text").strip(),
                })
        else:
            speaker = ""
            text_parts: list[str] = []
            target = ""
            for idx, line in enumerate(body):
                m = LINE_RE.match(line) if idx == 0 else None
                if m:
                    speaker = m.group("speaker").strip()
                    text_parts.append(m.group("text").strip())
                    if m.group("target"):
                        target = m.group("target")
                else:
                    text_parts.append(line)
            nodes.append({
                "id": scene_id,
                "text": " ".join(text_parts).strip(),
                "speaker": speaker,
                "type": "line",
            })
            if target:
                edges.append({"from": scene_id, "to": target, "text": ""})

    referenced = {e["to"] for e in edges if e["to"]}
    for target in referenced - defined:
        nodes.append({"id": target, "text": "", "speaker": "", "type": "line"})

    return {"nodes": nodes, "edges": edges}


def _escape_dot(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def to_dot(graph: dict[str, list[dict[str, Any]]]) -> str:
    out = ["digraph dialogue {", "  rankdir=LR;"]
    for node in graph["nodes"]:
        shape = "diamond" if node["type"] == "choice" else "box"
        label_bits = [node["id"]]
        if node["speaker"] and node["text"]:
            label_bits.append(f'{node["speaker"]}: {node["text"]}')
        elif node["text"]:
            label_bits.append(node["text"])
        label = "\\n".join(_escape_dot(b) for b in label_bits)
        out.append(f'  "{_escape_dot(node["id"])}" [label="{label}", shape={shape}];')
    for edge in graph["edges"]:
        if not edge["to"]:
            continue
        src = _escape_dot(edge["from"])
        dst = _escape_dot(edge["to"])
        if edge["text"]:
            out.append(f'  "{src}" -> "{dst}" [label="{_escape_dot(edge["text"])}"];')
        else:
            out.append(f'  "{src}" -> "{dst}";')
    out.append("}")
    return "\n".join(out) + "\n"


def main() -> int:
    src = Path("/app/script.txt")
    if not src.exists():
        print(f"missing input: {src}", file=sys.stderr)
        return 1
    graph = parse_script(src.read_text())
    Path("/app/dialogue.json").write_text(json.dumps(graph, indent=2) + "\n")
    Path("/app/dialogue.dot").write_text(to_dot(graph))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
