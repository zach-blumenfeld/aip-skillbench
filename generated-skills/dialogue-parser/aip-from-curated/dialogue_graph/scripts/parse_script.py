#!/usr/bin/env python3
"""Parse a bracketed-dialogue script into a validated Graph, then emit JSON + DOT.

Input format (one node per `[NodeID]` block):

    [NodeID]
    Speaker: Text body -> TargetNodeID          # dialogue line
    Narrator: Scene text. -> NextNode           # narrator line

    [ChoiceHubID]
    1. Plain option. -> TargetA                 # choice option
    2. [SkillTag] Option with skill check. -> TargetB
    3. Another option. -> TargetC

Rules:
- `[X]` header opens (or reopens) node `X`. The node type is inferred from the
  body: any `N. ...` numbered choice promotes the node to type `choice`;
  otherwise it stays `line`.
- A `Speaker: Text -> Target` line records `speaker`/`text` on the current node
  and adds a transition edge with empty `text`.
- A `N. Choice -> Target` line adds an edge whose `text` is the full numbered
  option string (preserving any `[Skill]` tag). The current node becomes a
  choice hub with empty `speaker`/`text`.
- Lines starting with `//` and blank lines are skipped.
- `End` is a sentinel target; it does not need a node definition.

Outputs:
- `<output-json>` — JSON in the form `{"nodes": [...], "edges": [...]}`.
- `<output-dot>`  — Graphviz DOT source (header `digraph`, choice nodes drawn
  as diamonds). Generated via the bundled `dialogue_graph` library so colors
  and shapes match the documented visualization style.

Usage:
    python parse_script.py --input /app/script.txt \\
        --output-json /app/dialogue.json --output-dot /app/dialogue.dot
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Allow running from any CWD by ensuring the script directory is importable.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from dialogue_graph import Edge, Graph, Node  # noqa: E402


HEADER_RE = re.compile(r"^\[(.+?)\]$")
CHOICE_RE = re.compile(r"^(\d+)\.\s*(.+)$")


def parse_script(text: str) -> Graph:
    """Parse the bracketed dialogue script text into a Graph.

    Returns the populated Graph. Run `graph.validate()` afterwards to surface
    structural problems (missing edge targets, etc.).
    """
    graph = Graph()
    current_id: str | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue

        header = HEADER_RE.match(line)
        if header:
            current_id = header.group(1)
            if current_id not in graph.nodes:
                graph.add_node(Node(id=current_id, text="", speaker="", type="line"))
            continue

        if current_id is None:
            continue

        node = graph.nodes[current_id]

        if "->" in line:
            text_part, target = line.rsplit("->", 1)
            text_part = text_part.strip()
            target = target.strip()
        else:
            text_part, target = line, None

        choice = CHOICE_RE.match(text_part)
        if choice:
            # Numbered choice option. Promote the current node to a choice hub
            # and add an edge whose label is the full option text (including
            # the leading number and any [SkillTag]).
            node.type = "choice"
            node.text = ""
            node.speaker = ""
            if target:
                graph.add_edge(Edge(source=current_id, target=target, text=text_part))
            continue

        if ":" in text_part:
            # Dialogue line: "Speaker: body".
            speaker, body = text_part.split(":", 1)
            node.speaker = speaker.strip()
            node.text = body.strip()
            node.type = "line"
            if target:
                graph.add_edge(Edge(source=current_id, target=target, text=""))
            continue

        # No colon, no number — treat as a bare transition.
        if target:
            graph.add_edge(Edge(source=current_id, target=target, text=""))

    return graph


def write_dot(graph: Graph, dot_path: Path) -> None:
    """Write DOT source for the graph to `dot_path`.

    Prefers the `dialogue_graph` library's `visualize` method (matches the
    documented styling: diamond choice nodes, speaker-colored boxes, bold-blue
    skill-check edges). Falls back to a minimal hand-written DOT if either the
    `graphviz` Python package OR the Graphviz `dot` system binary is missing,
    so the parser still produces a schema-valid DOT file in environments
    without a full Graphviz install.
    """
    dot_path = Path(dot_path)
    dot_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from graphviz import Digraph  # noqa: F401  (probe — used inside library)
    except ImportError:
        _write_dot_fallback(graph, dot_path)
        return

    # graphviz.Digraph.render(format='dot') writes "<stem>.dot" beside the
    # requested stem. We render to dot_path's stem then move into place.
    stem = dot_path.with_suffix("")
    try:
        rendered = graph.visualize(str(stem), format="dot")
    except Exception as exc:  # ExecutableNotFound, FileNotFoundError, etc.
        print(
            f"Warning: graphviz `dot` binary unavailable ({exc.__class__.__name__}); "
            f"writing DOT source directly.",
            file=sys.stderr,
        )
        _write_dot_fallback(graph, dot_path)
        return

    rendered_path = Path(rendered)
    if rendered_path != dot_path and rendered_path.exists():
        os.replace(rendered_path, dot_path)


def _write_dot_fallback(graph: Graph, dot_path: Path) -> None:
    lines = ["digraph DialogueGraph {", '  rankdir="TB";']
    for node_id, node in graph.nodes.items():
        if node.type == "choice":
            lines.append(f'  "{node_id}" [shape=diamond, style=filled, fillcolor=lightblue];')
        else:
            label = node_id
            if node.speaker and node.text:
                snippet = node.text if len(node.text) <= 40 else node.text[:37] + "..."
                label = f"{node_id}\\n{node.speaker}: {snippet}"
            elif node.speaker:
                label = f"{node_id}\\n{node.speaker}"
            label = label.replace('"', '\\"')
            lines.append(f'  "{node_id}" [shape=box, style="filled,rounded", label="{label}"];')
    lines.append('  "End" [shape=doublecircle, style=filled, fillcolor=lightgray];')
    for edge in graph.edges:
        label = edge.text.replace('"', '\\"')
        if label:
            lines.append(f'  "{edge.source}" -> "{edge.target}" [label="{label}"];')
        else:
            lines.append(f'  "{edge.source}" -> "{edge.target}";')
    lines.append("}")
    dot_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", default="/app/script.txt",
                        help="Path to the dialogue script (default: /app/script.txt).")
    parser.add_argument("--output-json", default="/app/dialogue.json",
                        help="Path for the dialogue JSON output (default: /app/dialogue.json).")
    parser.add_argument("--output-dot", default="/app/dialogue.dot",
                        help="Path for the DOT visualization output (default: /app/dialogue.dot).")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        # Fall back to CWD/script.txt for local runs outside Docker.
        local = Path("script.txt")
        if local.exists():
            input_path = local
        else:
            print(f"ERROR: input script not found at {args.input} or ./script.txt", file=sys.stderr)
            return 2

    text = input_path.read_text(encoding="utf-8")
    graph = parse_script(text)

    errors = graph.validate()
    if errors:
        print("Validation warnings:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)

    json_path = Path(args.output_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(graph.to_json(), encoding="utf-8")

    write_dot(graph, Path(args.output_dot))

    print(
        f"Parsed {len(graph.nodes)} nodes and {len(graph.edges)} edges "
        f"from {input_path} -> {json_path}, {args.output_dot}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
