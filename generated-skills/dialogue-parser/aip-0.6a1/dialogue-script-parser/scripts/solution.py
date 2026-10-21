"""Dialogue script parser: script text -> {"nodes": [...], "edges": [...]} graph + Graphviz .dot.

Self-contained (stdlib only; the `graphviz` package is used for the .dot when present).
Adapted from the dialogue_graph library (Graph / Node / Edge, validate, visualize, from_*).

Script format:
    [NodeId]                                  section header = one node
    Speaker: Spoken text. -> TargetId         dialogue line  -> node type "line"
    1. Choice text. -> TargetId               numbered option -> node type "choice"
    - Choice text. -> TargetId                bulleted option (also "*") -> node type "choice"
    2. [Skill] Skill-check choice. -> Other

Usage:
    python3 solution.py [script.txt] [dialogue.json] [dialogue.dot]
    (defaults: /app/script.txt /app/dialogue.json /app/dialogue.dot, or the files next to
    this file when /app/script.txt does not exist)
"""
import json
import os
import re
import shutil
import subprocess
import sys
from collections import deque
from typing import Any, Dict, List, Optional

END_ID = "End"  # virtual terminal node: may be targeted without being defined

HEADER_RE = re.compile(r"^\[([^\[\]]+)\]$")
CHOICE_RE = re.compile(r"^(?:\d+\s*[.)]\s*|[-*\u2022]\s+)(.*)$")  # "1." / "1)" / "-" / "*" / bullet
SPEAKER_RE = re.compile(r"^([^\s:\[\]\d][^:\[\]]*?)\s*:\s*(.*)$")
COMMENT_PREFIXES = ("#", "//")


class Node:
    def __init__(self, id: str, text: str = "", speaker: str = "", type: str = "line"):
        self.id = id
        self.text = text
        self.speaker = speaker
        self.type = type  # 'line', 'choice'

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "text": self.text, "speaker": self.speaker, "type": self.type}


class Edge:
    def __init__(self, source: str, target: str, text: str = ""):
        self.source = source
        self.target = target
        self.text = text

    def to_dict(self) -> Dict[str, Any]:
        return {"from": self.source, "to": self.target, "text": self.text if self.text is not None else ""}


class Graph:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self.parse_issues: List[str] = []  # lines the parser could not classify, duplicates

    def add_node(self, node: Node):
        if node.id in self.nodes:
            raise ValueError(f"Node {node.id} already exists")
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge):
        self.edges.append(edge)

    def first_node(self) -> Optional[str]:
        return next(iter(self.nodes), None)

    def reachable(self) -> set:
        start = self.first_node()
        if start is None:
            return set()
        adj: Dict[str, List[str]] = {}
        for e in self.edges:
            adj.setdefault(e.source, []).append(e.target)
        seen, queue = {start}, deque([start])
        while queue:
            for nxt in adj.get(queue.popleft(), []):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def validate(self) -> List[str]:
        """Errors that break the task constraints: missing edge endpoints (End excepted),
        nodes unreachable from the first node, and parse issues."""
        errors = list(self.parse_issues)
        if not self.nodes:
            errors.append("Graph has no nodes")
            return errors
        for edge in self.edges:
            if edge.source not in self.nodes:
                errors.append(f"Edge source '{edge.source}' not found")
            if edge.target not in self.nodes and edge.target != END_ID:
                errors.append(f"Edge '{edge.source}'->'{edge.target}' points to missing node '{edge.target}'")
        seen = self.reachable()
        for node_id in self.nodes:
            if node_id not in seen:
                errors.append(f"Node '{node_id}' is not reachable from first node '{self.first_node()}'")
        return errors

    def warnings(self) -> List[str]:
        """Non-fatal oddities worth a look (dead ends, End never reached)."""
        out = []
        sources = {e.source for e in self.edges}
        for node_id in self.nodes:
            if node_id not in sources:
                out.append(f"Node '{node_id}' has no outgoing edge (dead end that is not End)")
        if self.nodes and not any(e.target == END_ID for e in self.edges):
            out.append("No edge leads to 'End'")
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {"nodes": [n.to_dict() for n in self.nodes.values()],
                "edges": [e.to_dict() for e in self.edges]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    # ---- visualization (styling from dialogue_graph.Graph.visualize) ----
    SPEAKER_COLORS = {
        "Narrator": "lightyellow", "Guard": "lightcoral", "Stranger": "plum",
        "Merchant": "lightgreen", "Barkeep": "peachpuff", "Kira": "lightcyan",
    }
    EXTRA_COLORS = ["khaki", "lightpink", "palegreen", "lightsteelblue", "wheat", "thistle"]

    def _color(self, speaker: str, assigned: Dict[str, str]) -> str:
        if not speaker:
            return "white"
        if speaker in self.SPEAKER_COLORS:
            return self.SPEAKER_COLORS[speaker]
        if speaker not in assigned:
            assigned[speaker] = self.EXTRA_COLORS[len(assigned) % len(self.EXTRA_COLORS)]
        return assigned[speaker]

    def _dot_items(self):
        """Yield ('node'|'edge', args, attrs) in render order."""
        assigned: Dict[str, str] = {}
        for node_id, node in self.nodes.items():
            text = node.text[:37] + "..." if len(node.text) > 40 else node.text
            if node.type == "choice":
                yield "node", (node_id, node_id), dict(shape="diamond", style="filled",
                                                      fillcolor="lightblue", width="1.5")
            else:
                if node.speaker and text:
                    label = f"{node_id}\n{node.speaker}: {text}"
                elif node.speaker:
                    label = f"{node_id}\n{node.speaker}"
                elif text:
                    label = f"{node_id}\n{text}"
                else:
                    label = node_id
                yield "node", (node_id, label), dict(shape="box", style="filled,rounded",
                                                    fillcolor=self._color(node.speaker, assigned), width="2")
        if END_ID not in self.nodes:
            yield "node", (END_ID, "END"), dict(shape="doublecircle", style="filled",
                                               fillcolor="lightgray", width="0.8")
        for edge in self.edges:
            t = edge.text or ""
            t = t[:27] + "..." if len(t) > 30 else t
            if t and "[" in t and "]" in t:  # skill check edge, e.g. [Lie], [Attack]
                yield "edge", (edge.source, edge.target), dict(label=t, color="darkblue",
                                                             fontcolor="darkblue", style="bold")
            elif t:
                yield "edge", (edge.source, edge.target), dict(label=t, color="gray40", fontcolor="gray40")
            else:
                yield "edge", (edge.source, edge.target), dict(color="black")

    def to_dot(self) -> str:
        try:
            from graphviz import Digraph
        except ImportError:
            return self._to_dot_plain()
        dot = Digraph("dialogue", comment="Dialogue Graph")
        dot.attr(rankdir="TB", nodesep="0.5", ranksep="0.8")
        dot.attr("node", fontname="Arial", fontsize="10")
        dot.attr("edge", fontname="Arial", fontsize="8")
        for kind, args, attrs in self._dot_items():
            if kind == "node":
                # graphviz escapes quotes/backslashes; a literal "\n" in the label is a line break
                dot.node(args[0], args[1].replace("\\", "\\\\").replace("\n", "\\n"), **attrs)
            else:
                dot.edge(args[0], args[1], **attrs)
        return dot.source

    def _to_dot_plain(self) -> str:
        def q(s: str) -> str:
            return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
        lines = ["// Dialogue Graph", "digraph dialogue {",
                 '\trankdir=TB nodesep=0.5 ranksep=0.8',
                 '\tnode [fontname=Arial fontsize=10]', '\tedge [fontname=Arial fontsize=8]']
        for kind, args, attrs in self._dot_items():
            a = " ".join(f"{k}={q(v)}" for k, v in attrs.items())
            if kind == "node":
                lines.append(f"\t{q(args[0])} [label={q(args[1])} {a}]")
            else:
                lines.append(f"\t{q(args[0])} -> {q(args[1])} [{a}]")
        lines.append("}")
        return "\n".join(lines) + "\n"

    def visualize(self, output_file: str = "dialogue_graph", format: str = "png") -> str:
        """Render an image with the Graphviz binary (needs `pip install graphviz` + `dot`)."""
        from graphviz import Source
        return Source(self.to_dot()).render(output_file, format=format, cleanup=True)

    @staticmethod
    def from_dict(data: Dict) -> "Graph":
        graph = Graph()
        for n in data.get("nodes", []):
            graph.nodes[n["id"]] = Node(id=n["id"], text=n.get("text", ""),
                                        speaker=n.get("speaker", ""), type=n.get("type", "line"))
        for e in data.get("edges", []):
            graph.edges.append(Edge(source=e["from"], target=e["to"], text=e.get("text", "")))
        return graph

    @staticmethod
    def from_json(json_str: str) -> "Graph":
        return Graph.from_dict(json.loads(json_str))

    @staticmethod
    def from_file(filepath: str) -> "Graph":
        with open(filepath, "r", encoding="utf-8") as f:
            return Graph.from_json(f.read())


def _split_target(body: str):
    """'text -> Target' -> ('text', 'Target'); no arrow -> (body, None). Uses the LAST arrow."""
    if "->" not in body:
        return body.strip(), None
    text, _, target = body.rpartition("->")
    target = target.strip()
    if target.startswith("[") and target.endswith("]"):
        target = target[1:-1].strip()
    return text.strip(), (target or None)


def build_graph(text: str) -> Graph:
    """Parse script text into a Graph. Never raises on odd input; records parse_issues instead."""
    graph = Graph()
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    sections: List[List] = []  # [node_id, [(lineno, line), ...]]
    for lineno, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith(COMMENT_PREFIXES):
            continue
        m = HEADER_RE.match(line)
        if m:
            sections.append([m.group(1).strip(), []])
        elif sections:
            sections[-1][1].append((lineno, line))
        else:
            graph.parse_issues.append(f"Line {lineno} appears before any [Node] header: {line!r}")

    for node_id, body in sections:
        if node_id in graph.nodes:
            graph.parse_issues.append(f"Duplicate node header [{node_id}]; its lines were merged into the first")
            node = graph.nodes[node_id]
        else:
            node = Node(id=node_id)
            graph.add_node(node)
        current = node  # node that receives the next dialogue line's text
        pending_line_edge = None  # dialogue line seen but its target not yet emitted
        for lineno, line in body:
            cm = CHOICE_RE.match(line)
            if cm:
                choice_text, target = _split_target(line)
                node.type = "choice"
                if target is None:
                    graph.parse_issues.append(f"Line {lineno} in [{node_id}]: choice without '-> Target': {line!r}")
                    continue
                graph.add_edge(Edge(node_id, target, choice_text))
                continue
            content, target = _split_target(line)
            sm = SPEAKER_RE.match(content)
            speaker, spoken = (sm.group(1).strip(), sm.group(2).strip()) if sm else ("", content)
            if not spoken and not speaker and target is None:
                graph.parse_issues.append(f"Line {lineno} in [{node_id}]: unrecognized line: {line!r}")
                continue
            if current.text or current.speaker:
                # a second dialogue line in one section: chain it as its own line node
                k = 2
                while f"{node_id}_{k}" in graph.nodes:
                    k += 1
                nxt = Node(id=f"{node_id}_{k}")
                graph.add_node(nxt)
                if pending_line_edge is None:
                    graph.add_edge(Edge(current.id, nxt.id, ""))
                current = nxt
            current.speaker, current.text = speaker, spoken
            pending_line_edge = None
            if target is not None:
                graph.add_edge(Edge(current.id, target, ""))
                pending_line_edge = target
    return graph


def parse_script(text: str) -> Dict[str, Any]:
    """Required entry point: script text -> {"nodes": [...], "edges": [...]}."""
    return build_graph(text).to_dict()


def check_dot_renders(dot_path: str) -> Optional[str]:
    """Return an error string if the Graphviz `dot` binary rejects the file; None if ok or absent."""
    exe = shutil.which("dot")
    if not exe:
        return None
    proc = subprocess.run([exe, "-Tsvg", "-o", os.devnull, dot_path], capture_output=True, text=True)
    return None if proc.returncode == 0 else f"dot rejected {dot_path}: {proc.stderr.strip()[:500]}"


def run(script_path: str, json_path: str, dot_path: str) -> Dict[str, Any]:
    """Parse the script, write JSON + DOT, and return a validation report."""
    with open(script_path, "r", encoding="utf-8") as f:
        graph = build_graph(f.read())
    data = graph.to_dict()
    for path in (json_path, dot_path):
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    with open(dot_path, "w", encoding="utf-8") as f:
        f.write(graph.to_dot())
    errors = graph.validate()
    render_err = check_dot_renders(dot_path)
    if render_err:
        errors.append(render_err)
    with open(json_path, "r", encoding="utf-8") as f:  # round-trip: what tests will read
        reread = json.load(f)
    if reread != parse_script(open(script_path, encoding="utf-8").read()):
        errors.append("dialogue.json does not match parse_script(text) output")
    return {
        "first_node": graph.first_node() or "",
        "node_count": len(data["nodes"]),
        "edge_count": len(data["edges"]),
        "choice_node_count": sum(1 for n in data["nodes"] if n["type"] == "choice"),
        "end_edge_count": sum(1 for e in data["edges"] if e["to"] == END_ID),
        "errors": errors,
        "warnings": graph.warnings(),
    }


def _default_paths(argv: List[str]):
    here = os.path.dirname(os.path.abspath(__file__))
    base = "/app" if os.path.exists("/app/script.txt") else here
    script = argv[0] if len(argv) > 0 else os.path.join(base, "script.txt")
    out_dir = os.path.dirname(os.path.abspath(script))
    json_path = argv[1] if len(argv) > 1 else os.path.join(out_dir, "dialogue.json")
    dot_path = argv[2] if len(argv) > 2 else os.path.join(out_dir, "dialogue.dot")
    return script, json_path, dot_path


if __name__ == "__main__":
    report = run(*_default_paths(sys.argv[1:]))
    print(json.dumps(report, indent=2))
    sys.exit(1 if report["errors"] else 0)
