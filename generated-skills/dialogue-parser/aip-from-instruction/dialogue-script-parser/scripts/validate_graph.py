#!/usr/bin/env python3
"""Static checks for a parsed dialogue graph.

Usage: python validate_graph.py /app/dialogue.json

Enforces the task constraints:
  1. Every node is reachable from the first node (forward edges).
  2. Every edge target resolves to a defined node.
  3. "End" (or any sink) may be reached by multiple paths — no uniqueness check.

Exits 0 on success, 1 on the first failure. Errors print to stderr.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict, deque
from pathlib import Path


def validate(graph: dict) -> list[str]:
    errors: list[str] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not nodes:
        return ["graph has no nodes"]

    ids = [n["id"] for n in nodes]
    id_set = set(ids)
    if len(ids) != len(id_set):
        dupes = {i for i in ids if ids.count(i) > 1}
        errors.append(f"duplicate node ids: {sorted(dupes)}")

    for e in edges:
        if not e.get("to"):
            errors.append(f"edge from {e.get('from')!r} has empty target")
        elif e["to"] not in id_set:
            errors.append(f"edge {e['from']!r} -> {e['to']!r} targets undefined node")

    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.get("from") and e.get("to"):
            adj[e["from"]].append(e["to"])

    start = ids[0]
    seen = {start}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for nxt in adj.get(cur, []):
            if nxt in id_set and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    unreachable = id_set - seen
    if unreachable:
        errors.append(f"unreachable from start node {start!r}: {sorted(unreachable)}")

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_graph.py <dialogue.json>", file=sys.stderr)
        return 1
    path = Path(sys.argv[1])
    graph = json.loads(path.read_text())
    errors = validate(graph)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1
    print(f"ok: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges reachable from {graph['nodes'][0]['id']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
