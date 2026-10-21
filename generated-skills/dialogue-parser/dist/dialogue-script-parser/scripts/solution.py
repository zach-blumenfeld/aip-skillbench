#!/usr/bin/env python3
"""Dialogue script parser: script text -> validated JSON graph + Graphviz .dot.

Requires: Python >= 3.8, standard library only.
Optional: `graphviz` pip package + Graphviz `dot` binary, only for --render (PNG/SVG).

Import use (what graders call):
    from solution import parse_script
    graph = parse_script(open("script.txt").read())   # {"nodes": [...], "edges": [...]}

CLI use:
    python solution.py <script.txt> [--json dialogue.json] [--dot dialogue.dot]
                       [--render png|svg] [--add-end-node]
    Defaults: script /app/script.txt, outputs next to it as dialogue.json / dialogue.dot.
    Exit 0 = graph written and valid; 1 = validation errors (files still written); 2 = bad input.

Script format:
    [NodeId]                         starts a block; the block's first node gets this id
    Speaker: text -> Target          'line' node (speaker, text) + edge to Target (edge text "")
    text -> Target                   'line' node with no speaker
    1. choice text -> Target         block becomes a 'choice' node (text "", speaker "");
                                     one edge per option, edge text = the whole option
                                     including its number and any [Skill] tag ("1. [Lie] ...")
    # comment / // comment           ignored, as are blank lines
"""
import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

END_ID = "End"  # terminal target; allowed to be referenced without being defined

# ---------------------------------------------------------------- graph model
# Adapted from source/dialogue_graph/scripts/dialogue_graph.py (same API, same JSON).


class Node:
    def __init__(self, id: str, text: str = "", speaker: str = "", type: str = "line"):
        self.id = id
        self.text = text
        self.speaker = speaker
        self.type = type  # 'line' or 'choice'

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "text": self.text, "speaker": self.speaker, "type": self.type}


class Edge:
    def __init__(self, source: str, target: str, text: str = ""):
        self.source = source
        self.target = target
        self.text = text

    def to_dict(self) -> Dict[str, Any]:
        d = {"from": self.source, "to": self.target}
        if self.text is not None:
            d["text"] = self.text
        return d


class Graph:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []

    def add_node(self, node: Node):
        if node.id in self.nodes:
            raise ValueError(f"Node {node.id} already exists")
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge):
        self.edges.append(edge)

    def validate(self) -> List[str]:
        """Edge sources/targets exist (target 'End' exempt) and every node is
        reachable from the first node."""
        errors = []
        for edge in self.edges:
            if edge.source not in self.nodes:
                errors.append(f"Edge source '{edge.source}' not found")
            if edge.target not in self.nodes and edge.target != END_ID:
                errors.append(f"Edge '{edge.source}'->'{edge.target}' points to missing node '{edge.target}'")
        if self.nodes:
            start = next(iter(self.nodes))
            adj: Dict[str, List[str]] = {}
            for e in self.edges:
                adj.setdefault(e.source, []).append(e.target)
            seen, stack = {start}, [start]
            while stack:
                for t in adj.get(stack.pop(), []):
                    if t not in seen:
                        seen.add(t)
                        stack.append(t)
            for nid in self.nodes:
                if nid not in seen:
                    errors.append(f"Node '{nid}' is not reachable from first node '{start}'")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {"nodes": [n.to_dict() for n in self.nodes.values()],
                "edges": [e.to_dict() for e in self.edges]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_dot(self) -> str:
        """Graphviz DOT source, no dependencies. Styling matches the source library's
        visualize(): diamonds for choices, rounded boxes colored by speaker, a gray
        doublecircle END node, bold dark-blue edges for [Skill] options, gray for other
        options, black for plain transitions."""
        def q(s: str) -> str:
            return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

        out = ["digraph DialogueGraph {",
               "  // Dialogue Graph",
               '  rankdir=TB; splines=ortho; nodesep=0.5; ranksep=0.8;',
               '  node [fontname="Arial", fontsize=10];',
               '  edge [fontname="Arial", fontsize=8];']
        for nid, n in self.nodes.items():
            if nid == END_ID:
                continue
            if n.type == "choice":
                out.append(f'  {q(nid)} [label={q(nid)}, shape=diamond, style=filled, '
                           f'fillcolor=lightblue, width=1.5];')
                continue
            text = n.text[:37] + "..." if len(n.text) > 40 else n.text
            if n.speaker and text:
                label = f"{nid}\n{n.speaker}: {text}"
            elif n.speaker:
                label = f"{nid}\n{n.speaker}"
            elif text:
                label = f"{nid}\n{text}"
            else:
                label = nid
            color = SPEAKER_COLORS.get(n.speaker, "white")
            out.append(f'  {q(nid)} [label={q(label)}, shape=box, style="filled,rounded", '
                       f'fillcolor={color}, width=2];')
        out.append(f'  {q(END_ID)} [label="END", shape=doublecircle, style=filled, '
                   f'fillcolor=lightgray, width=0.8];')
        for e in self.edges:
            et = e.text[:27] + "..." if len(e.text) > 30 else e.text
            if not et:
                out.append(f"  {q(e.source)} -> {q(e.target)} [color=black];")
            elif SKILL_TAG.search(e.text):
                out.append(f"  {q(e.source)} -> {q(e.target)} [label={q(et)}, color=darkblue, "
                           f"fontcolor=darkblue, style=bold];")
            else:
                out.append(f"  {q(e.source)} -> {q(e.target)} [label={q(et)}, color=gray40, "
                           f"fontcolor=gray40];")
        out.append("}")
        return "\n".join(out) + "\n"

    def visualize(self, output_file: str = "dialogue_graph", format: str = "png") -> str:
        """Render PNG/SVG/PDF. Needs `pip install graphviz` and the Graphviz binary."""
        try:
            from graphviz import Source
        except ImportError:
            raise ImportError("graphviz package required. Install with: pip install graphviz")
        return Source(self.to_dot(), format=format).render(output_file, cleanup=True)

    @staticmethod
    def from_json(json_str: str) -> "Graph":
        return Graph.from_dict(json.loads(json_str))

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
    def from_file(filepath: str) -> "Graph":
        with open(filepath, "r", encoding="utf-8") as f:
            return Graph.from_json(f.read())


SPEAKER_COLORS = {"Narrator": "lightyellow", "Guard": "lightcoral", "Stranger": "plum",
                  "Merchant": "lightgreen", "Barkeep": "peachpuff", "Kira": "lightcyan"}
SKILL_TAG = re.compile(r"\[[^\]]+\]")

# ---------------------------------------------------------------- parser

HEADER = re.compile(r"^\[([^\[\]]+)\]\s*$")
CHOICE = re.compile(r"^\d+\s*[.)]\s*\S")
SPEAKER = re.compile(r"^([^:\[\]]{1,40}?)\s*:\s+(.*)$")


def _split_arrow(s: str) -> Tuple[str, Optional[str]]:
    """'text -> Target' -> ('text', 'Target'); no arrow -> (s, None). Uses the last '->'."""
    if "->" not in s:
        return s.strip(), None
    left, right = s.rsplit("->", 1)
    return left.strip(), (right.strip() or None)


def _parse(text: str) -> Tuple[Graph, List[str]]:
    graph, warnings = Graph(), []
    blocks: List[Tuple[str, int, List[Tuple[int, str]]]] = []
    for ln, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        m = HEADER.match(line)
        if m:
            blocks.append((m.group(1).strip(), ln, []))
        elif blocks:
            blocks[-1][2].append((ln, line))
        else:
            warnings.append(f"line {ln}: content before the first [Node] header ignored: {line!r}")

    for bid, bln, body in blocks:
        if bid in graph.nodes:
            raise ValueError(f"line {bln}: duplicate node id [{bid}]")
        choices = [(ln, l) for ln, l in body if CHOICE.match(l)]
        lines = [(ln, l) for ln, l in body if not CHOICE.match(l)]
        if not body:
            warnings.append(f"line {bln}: block [{bid}] is empty; kept as a line node with no edges")
            graph.add_node(Node(id=bid, text="", speaker="", type="line"))
        # Lines first: the first gets the block id, later ones get bid_2, bid_3... chained.
        prev: Optional[str] = None
        for i, (ln, l) in enumerate(lines):
            nid = bid if i == 0 else f"{bid}_{i + 1}"
            content, target = _split_arrow(l)
            m = SPEAKER.match(content)
            speaker, said = (m.group(1).strip(), m.group(2).strip()) if m else ("", content)
            graph.add_node(Node(id=nid, text=said, speaker=speaker, type="line"))
            if prev is not None:
                graph.add_edge(Edge(prev, nid, ""))
            if target:
                if i < len(lines) - 1 or choices:
                    warnings.append(f"line {ln}: '-> {target}' on a non-final line of [{bid}]")
                graph.add_edge(Edge(nid, target, ""))
            prev = nid
        if choices:
            if prev is None:
                graph.add_node(Node(id=bid, text="", speaker="", type="choice"))
                hub = bid
            else:
                hub = prev  # speaker line followed by options: options hang off that line
            for ln, l in choices:
                content, target = _split_arrow(l)
                if not target:
                    warnings.append(f"line {ln}: choice without '-> Target' skipped: {l!r}")
                    continue
                graph.add_edge(Edge(hub, target, content))
    return graph, warnings


def parse_script(text: str) -> Dict[str, Any]:
    """Parse dialogue script text into {"nodes": [...], "edges": [...]}."""
    return _parse(text)[0].to_dict()


# ---------------------------------------------------------------- CLI


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("script", nargs="?", default="/app/script.txt")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--dot", dest="dot_out")
    ap.add_argument("--render", choices=["png", "svg", "pdf"],
                    help="also render an image (needs graphviz package + binary)")
    ap.add_argument("--add-end-node", action="store_true",
                    help="emit an explicit 'End' node in the JSON (off by default)")
    a = ap.parse_args(argv)

    if not os.path.isfile(a.script):
        print(f"ERROR: script not found: {a.script}", file=sys.stderr)
        return 2
    with open(a.script, encoding="utf-8") as f:
        text = f.read()
    try:
        graph, warnings = _parse(text)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if not graph.nodes:
        print("ERROR: no [Node] blocks found", file=sys.stderr)
        return 2
    if a.add_end_node and END_ID not in graph.nodes and any(e.target == END_ID for e in graph.edges):
        graph.add_node(Node(id=END_ID, text="", speaker="", type="line"))

    base = os.path.dirname(os.path.abspath(a.script))
    json_out = a.json_out or os.path.join(base, "dialogue.json")
    dot_out = a.dot_out or os.path.join(base, "dialogue.dot")
    with open(json_out, "w", encoding="utf-8") as f:
        f.write(graph.to_json() + "\n")
    with open(dot_out, "w", encoding="utf-8") as f:
        f.write(graph.to_dot())

    errors = graph.validate()
    n_choice = sum(n.type == "choice" for n in graph.nodes.values())
    to_end = [e.source for e in graph.edges if e.target == END_ID]
    speakers = sorted({n.speaker for n in graph.nodes.values() if n.speaker})
    print(f"nodes: {len(graph.nodes)} ({len(graph.nodes) - n_choice} line, {n_choice} choice)")
    print(f"edges: {len(graph.edges)}  (with text: {sum(bool(e.text) for e in graph.edges)})")
    print(f"first node: {next(iter(graph.nodes))}")
    print(f"paths into {END_ID}: {len(to_end)} from {to_end}")
    print(f"speakers: {', '.join(speakers)}")
    print(f"wrote {json_out}\nwrote {dot_out}")
    if a.render:
        try:
            print(f"rendered {graph.visualize(os.path.splitext(dot_out)[0], a.render)}")
        except Exception as e:  # rendering is optional; never fail the parse on it
            print(f"WARNING: render skipped: {e}", file=sys.stderr)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    for e in errors:
        print(f"INVALID: {e}", file=sys.stderr)
    print("VALID" if not errors else f"INVALID ({len(errors)} errors)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
