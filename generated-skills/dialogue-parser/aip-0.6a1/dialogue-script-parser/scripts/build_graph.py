"""AIP execution step: install solution.py, parse the script, write dialogue.json + dialogue.dot, validate.

stdin:  {"state": {"script_path", "solution_path", "json_path", "dot_path"}, "assets": {...}, "expects": [...]}
stdout: {"graph_status", "first_node", "node_count", "edge_count", "choice_node_count",
         "end_edge_count", "graph_errors", "graph_warnings", "sample_nodes", "sample_edges"}
"""
import importlib.util
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def fail(msg: str):
    print(msg, file=sys.stderr)
    sys.exit(1)


def main():
    payload = json.load(sys.stdin)
    state = payload.get("state", payload)
    try:
        script_path = state["script_path"]
        solution_path = state["solution_path"]
        json_path = state["json_path"]
        dot_path = state["dot_path"]
    except KeyError as e:
        fail(f"missing state key {e}")
    if not os.path.isfile(script_path):
        fail(f"script not found: {script_path}")

    template = os.path.join(HERE, "solution.py")
    os.makedirs(os.path.dirname(os.path.abspath(solution_path)), exist_ok=True)
    if os.path.abspath(template) != os.path.abspath(solution_path):
        shutil.copyfile(template, solution_path)

    # import the INSTALLED copy: that file is what the task's tests import
    spec = importlib.util.spec_from_file_location("solution", solution_path)
    solution = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(solution)
    if not callable(getattr(solution, "parse_script", None)):
        fail(f"{solution_path} does not define parse_script(text)")

    report = solution.run(script_path, json_path, dot_path)
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    choice_ids = [n["id"] for n in data["nodes"] if n["type"] == "choice"][:1]
    sample_nodes = data["nodes"][:2] + [n for n in data["nodes"] if n["id"] in choice_ids]
    sample_edges = [e for e in data["edges"] if e["from"] in {n["id"] for n in sample_nodes}][:8]
    print(json.dumps({
        "graph_status": "invalid" if report["errors"] else "valid",
        "first_node": report["first_node"],
        "node_count": report["node_count"],
        "edge_count": report["edge_count"],
        "choice_node_count": report["choice_node_count"],
        "end_edge_count": report["end_edge_count"],
        "graph_errors": report["errors"][:50],
        "graph_warnings": report["warnings"][:50],
        "sample_nodes": sample_nodes,
        "sample_edges": sample_edges,
    }))


if __name__ == "__main__":
    main()
