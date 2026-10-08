"""Parse a bracketed dialogue script into a dialogue graph, validate it, and export it.

Built on the bundled `dialogue_graph` library (Graph / Node / Edge), stdlib only.

Script format (one block per node):

    [NodeId]
    Speaker: Line of dialogue. -> NextNodeId

    [ChoiceHub]
    1. Option text. -> TargetA
    2. [Skill Check] Option text. -> TargetB

`End` is a terminal target that needs no block of its own.

Two ways to run:
  * AIP execution step: one JSON object on stdin {"currentState", "assets", "expects"};
    one JSON object on stdout.
  * CLI / importable parser (for tasks that want a parser program as the deliverable):
        python dialogue_tool.py script.txt -o dialogue.json [--dot g.dot] [--image g.png]
            [--end-node virtual|explicit] [--choice-text verbatim|strip_number]
        from dialogue_tool import parse_file     # path -> {"nodes", "edges"}
        from dialogue_tool import parse_script   # text -> (Graph, issues)
"""
import json
import os
import re
import shutil
import subprocess
import sys
from collections import deque

sys.dont_write_bytecode = True  # never leave __pycache__ inside the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dialogue_graph import Edge, Graph, Node  # noqa: E402

END_ID = "End"
HEADER_RE = re.compile(r"^\[([^\[\]]+)\]$")
CHOICE_RE = re.compile(r"^(\d+)\s*[.)]\s*(.*)$")
SPEAKER_RE = re.compile(r"^([^:\[\]]{1,60}?)\s*:\s*(.*)$")

# Same speaker palette as dialogue_graph.Graph.visualize
SPEAKER_COLORS = {
    "Narrator": "lightyellow",
    "Guard": "lightcoral",
    "Stranger": "plum",
    "Merchant": "lightgreen",
    "Barkeep": "peachpuff",
    "Kira": "lightcyan",
}


# --------------------------------------------------------------------------- parse
def _read_blocks(text, issues):
    """Split the script into blocks: {id, lineno, lines: [...], options: [...]}."""
    blocks = []
    cur = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        m = HEADER_RE.match(line)
        if m:
            cur = {"id": m.group(1).strip(), "lineno": lineno, "lines": [], "options": []}
            blocks.append(cur)
            continue
        if cur is None:
            issues["errors"].append(f"line {lineno}: content before the first [NodeId] header: {line!r}")
            continue

        body, target = line, None
        if "->" in line:
            body, _, target = line.rpartition("->")
            body, target = body.strip(), target.strip()
            if not target:
                issues["errors"].append(f"line {lineno}: '->' with no target: {line!r}")
                target = None

        cm = CHOICE_RE.match(body)
        if cm:
            if target is None:
                issues["errors"].append(f"line {lineno}: choice option has no '-> Target': {line!r}")
                continue
            cur["options"].append({"num": cm.group(1), "label": cm.group(2).strip(),
                                   "raw": body, "target": target, "lineno": lineno})
            continue

        sm = SPEAKER_RE.match(body)
        if sm and not body.startswith("["):
            speaker, said = sm.group(1).strip(), sm.group(2).strip()
        else:
            speaker, said = "", body
            issues["warnings"].append(f"line {lineno}: no 'Speaker:' prefix; stored as speakerless line: {line!r}")
        if cur["options"]:
            issues["warnings"].append(f"line {lineno}: dialogue line after choice options in [{cur['id']}]")
        cur["lines"].append({"speaker": speaker, "text": said, "target": target, "lineno": lineno})
    return blocks


def parse_script(text, end_node="virtual", choice_text="verbatim"):
    """Return (Graph, issues). Nodes and edges keep the script's order."""
    issues = {"errors": [], "warnings": [], "edge_lines": []}
    if text.startswith("﻿"):
        text = text[1:]
    blocks = _read_blocks(text, issues)
    graph = Graph()

    seen = {}
    for b in blocks:
        bid = b["id"]
        if bid in seen:
            issues["errors"].append(f"line {b['lineno']}: duplicate node id [{bid}] (first at line {seen[bid]}); later block ignored")
            continue
        seen[bid] = b["lineno"]

        lines, options = b["lines"], b["options"]
        if not lines and not options:
            issues["errors"].append(f"line {b['lineno']}: block [{bid}] is empty")
            graph.add_node(Node(id=bid, type="line"))
            continue
        if not lines:
            # Pure choice hub, as in the library: Node(id=..., type="choice")
            graph.add_node(Node(id=bid, type="choice"))
            owner = bid
        else:
            # One node per dialogue line; extra lines become <id>_2, <id>_3 ... chained in order.
            ids = [bid] + [f"{bid}_{k}" for k in range(2, len(lines) + 1)]
            if len(lines) > 1:
                issues["warnings"].append(f"[{bid}] has {len(lines)} dialogue lines; split into {ids}")
            for i, (nid, ln) in enumerate(zip(ids, lines)):
                is_last = i == len(lines) - 1
                ntype = "choice" if (is_last and options) else "line"
                graph.add_node(Node(id=nid, speaker=ln["speaker"], text=ln["text"], type=ntype))
                if ln["target"]:
                    if is_last and options:
                        issues["warnings"].append(f"line {ln['lineno']}: [{bid}] has both '-> {ln['target']}' and choices; kept both")
                    graph.add_edge(Edge(source=nid, target=ln["target"]))
                    issues["edge_lines"].append(ln["lineno"])
                elif not is_last:
                    graph.add_edge(Edge(source=nid, target=ids[i + 1]))
                    issues["edge_lines"].append(ln["lineno"])
            owner = ids[-1]
        for opt in options:
            label = opt["raw"] if choice_text == "verbatim" else opt["label"]
            graph.add_edge(Edge(source=owner, target=opt["target"], text=label))
            issues["edge_lines"].append(opt["lineno"])

    if end_node == "explicit" and END_ID not in graph.nodes:
        graph.add_node(Node(id=END_ID, text="", speaker="", type="line"))
    return graph, issues


def parse_file(path, end_node="virtual", choice_text="verbatim"):
    """Convenience for parser deliverables: script path -> graph dict ({"nodes", "edges"}).
    Script defects are not raised; call parse_script + check_graph to inspect them."""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        graph, _ = parse_script(f.read(), end_node=end_node, choice_text=choice_text)
    return graph.to_dict()


# ------------------------------------------------------------------------ validate
def check_graph(graph, issues, start_id):
    errors, warnings = issues["errors"], issues["warnings"]
    # Library integrity rules: every edge source/target exists ('End' is allowed as a virtual target).
    # Same check as graph.validate(), but each message carries the script line of the edge.
    lines = issues.get("edge_lines", [])
    lib_errors = graph.validate()
    if lib_errors:
        for i, e in enumerate(graph.edges):
            at = f"line {lines[i]}: " if i < len(lines) else ""
            if e.source not in graph.nodes:
                errors.append(f"{at}Edge source '{e.source}' not found")
            if e.target not in graph.nodes and e.target != END_ID:
                errors.append(f"{at}Edge target '{e.target}' not found (in [{e.source}] -> {e.target})")

    out_edges = {}
    for e in graph.edges:
        out_edges.setdefault(e.source, []).append(e)
    for nid, node in graph.nodes.items():
        if nid == END_ID:
            continue
        if nid not in out_edges:
            warnings.append(f"node [{nid}] has no outgoing edge (dead end that is not End)")
        if node.type == "choice" and not any(e.text for e in out_edges.get(nid, [])):
            errors.append(f"choice node [{nid}] has no choice options")

    reachable = set()
    if start_id in graph.nodes:
        q = deque([start_id])
        while q:
            n = q.popleft()
            if n in reachable:
                continue
            reachable.add(n)
            for e in out_edges.get(n, []):
                if e.target in graph.nodes and e.target not in reachable:
                    q.append(e.target)
    unreachable = [n for n in graph.nodes if n not in reachable and n != END_ID]
    if unreachable:
        warnings.append(f"{len(unreachable)} node(s) unreachable from [{start_id}]: {unreachable}")
    reaches_end = any(e.target == END_ID and e.source in reachable for e in graph.edges)
    if not reaches_end:
        warnings.append(f"no path from [{start_id}] reaches End")
    return unreachable, reaches_end


# ----------------------------------------------------------------------- visualize
def _q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_dot(graph):
    """DOT source with the same styling as dialogue_graph.Graph.visualize."""
    out = ["// Dialogue Graph", "digraph {",
           '\trankdir=TB splines=ortho nodesep=0.5 ranksep=0.8',
           '\tnode [fontname=Arial fontsize=10]',
           '\tedge [fontname=Arial fontsize=8]']
    for nid, node in graph.nodes.items():
        if nid == END_ID:
            continue
        text = node.text[:37] + "..." if len(node.text) > 40 else node.text
        if node.type == "choice":
            out.append(f"\t{_q(nid)} [label={_q(nid)} fillcolor=lightblue shape=diamond style=filled width=1.5]")
        else:
            if node.speaker and text:
                label = f"{nid}\\n{node.speaker}: {text}"
            elif node.speaker:
                label = f"{nid}\\n{node.speaker}"
            else:
                label = nid
            color = SPEAKER_COLORS.get(node.speaker, "white")
            lab = '"' + label.replace('"', '\\"') + '"'  # keep the \n escape for DOT
            out.append(f'\t{_q(nid)} [label={lab} fillcolor={color} shape=box style="filled,rounded" width=2]')
    out.append(f'\t{_q(END_ID)} [label=END fillcolor=lightgray shape=doublecircle style=filled width=0.8]')
    for e in graph.edges:
        et = e.text[:27] + "..." if len(e.text) > 30 else e.text
        if et:
            if "[" in et and "]" in et:  # skill-check choice
                out.append(f"\t{_q(e.source)} -> {_q(e.target)} [label={_q(et)} color=darkblue fontcolor=darkblue style=bold]")
            else:
                out.append(f"\t{_q(e.source)} -> {_q(e.target)} [label={_q(et)} color=gray40 fontcolor=gray40]")
        else:
            out.append(f"\t{_q(e.source)} -> {_q(e.target)} [color=black]")
    out.append("}")
    return "\n".join(out) + "\n"


def render(dot_src, image_path, issues):
    fmt = os.path.splitext(image_path)[1].lstrip(".").lower() or "png"
    exe = shutil.which("dot")
    if not exe:
        issues["warnings"].append("Graphviz 'dot' binary not found; image not rendered (DOT source still written if requested)")
        return None
    r = subprocess.run([exe, f"-T{fmt}", "-o", image_path], input=dot_src.encode("utf-8"),
                       capture_output=True, timeout=120)
    if r.returncode != 0:
        issues["errors"].append(f"dot render failed: {r.stderr.decode('utf-8', 'replace')[:500]}")
        return None
    return image_path


# ----------------------------------------------------------------------------- run
def run(script_path, output_json="", dot_path="", image_path="",
        end_node="virtual", choice_text="verbatim"):
    script_path = os.path.abspath(os.path.expanduser(script_path))
    if not os.path.isfile(script_path):
        return {"status": "broken", "errors": [f"script not found: {script_path}"], "warnings": []}
    with open(script_path, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    if end_node not in ("virtual", "explicit"):
        end_node = "virtual"
    if choice_text not in ("verbatim", "strip_number"):
        choice_text = "verbatim"

    graph, issues = parse_script(text, end_node=end_node, choice_text=choice_text)
    start_id = next(iter(graph.nodes), "")
    unreachable, reaches_end = check_graph(graph, issues, start_id)

    written = []
    data = graph.to_dict()
    if not output_json:
        output_json = os.path.join(os.path.dirname(script_path), "dialogue.json")
    output_json = os.path.abspath(os.path.expanduser(output_json))
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        f.write(graph.to_json())
    written.append(output_json)

    dot_src = to_dot(graph) if (dot_path or image_path) else None
    if dot_path:
        dot_path = os.path.abspath(os.path.expanduser(dot_path))
        os.makedirs(os.path.dirname(dot_path), exist_ok=True)
        with open(dot_path, "w", encoding="utf-8") as f:
            f.write(dot_src)
        written.append(dot_path)
    if image_path:
        image_path = os.path.abspath(os.path.expanduser(image_path))
        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        if render(dot_src, image_path, issues):
            written.append(image_path)

    nodes = data["nodes"]
    return {
        "status": "broken" if issues["errors"] else "ok",
        "graph_path": output_json,
        "files_written": written,
        "start_node": start_id,
        "node_count": len(nodes),
        "edge_count": len(data["edges"]),
        "line_node_count": sum(n["type"] == "line" for n in nodes),
        "choice_node_count": sum(n["type"] == "choice" for n in nodes),
        "end_edge_count": sum(e["to"] == END_ID for e in data["edges"]),
        "speakers": sorted({n["speaker"] for n in nodes if n["speaker"]}),
        "unreachable_nodes": unreachable,
        "reaches_end": reaches_end,
        "errors": issues["errors"],
        "warnings": issues["warnings"],
        "preview": {"nodes": nodes[:3], "edges": data["edges"][:4]},
        "options_used": {"end_node": end_node, "choice_text": choice_text},
    }


def _main_stdin():
    payload = json.loads(sys.stdin.read() or "{}")
    st = payload.get("currentState", payload)
    res = run(st.get("script_path", ""), st.get("output_json", ""), st.get("dot_path", ""),
              st.get("image_path", ""), st.get("end_node", "virtual"), st.get("choice_text", "verbatim"))
    print(json.dumps(res, ensure_ascii=False))


def _main_cli(argv):
    import argparse
    p = argparse.ArgumentParser(description="Parse a dialogue script into dialogue-graph JSON.")
    p.add_argument("script")
    p.add_argument("-o", "--output", default="")
    p.add_argument("--dot", default="")
    p.add_argument("--image", default="")
    p.add_argument("--end-node", default="virtual", choices=["virtual", "explicit"])
    p.add_argument("--choice-text", default="verbatim", choices=["verbatim", "strip_number"])
    a = p.parse_args(argv)
    res = run(a.script, a.output, a.dot, a.image, a.end_node, a.choice_text)
    res.pop("preview", None)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res["status"] == "ok" else 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(_main_cli(sys.argv[1:]))
    try:
        _main_stdin()
    except Exception as exc:  # report as JSON so the runtime can surface it
        print(json.dumps({"status": "broken", "errors": [f"{type(exc).__name__}: {exc}"], "warnings": []}))
