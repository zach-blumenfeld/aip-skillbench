The dialogue script `{script_path}` parsed with errors. The graph was still written to `{graph_path}`.

Errors:
{errors}

Warnings:
{warnings}

Fix the root cause, not the symptom:

1. Open the script at the reported line numbers and look at the raw text.
2. Classify each error:
   - **Parser mismatch**: the line is valid dialogue in a variant syntax the parser did not expect
     (a different option numbering, an arrow written as `→` or `=>`, a speaker with brackets, etc.).
     Re-run `scripts/dialogue_tool.py` (CLI form in the reference) after normalising, or patch the graph
     with `Graph.from_file` / `add_node` / `add_edge` / `to_json`, keeping the format in the reference.
   - **Genuine script defect** (a target with no block, a duplicate id, an empty block): keep the graph
     faithful to the script. Do not invent nodes, dialogue, or targets; leave the edge as written and
     report it — unless the task instructions say how to handle it.
   - **Conflict with the task**: if the task's constraints cannot hold without changing content (e.g.
     "every edge target must be a node" but a target has no block), say so explicitly in your notes and
     in the final summary, naming the line, the edge, and the options (stub node, drop the edge, fix the
     script). Apply one only if the task authorizes it.
3. Re-run the parser (or `Graph.validate()` on the patched file) and confirm the remaining errors are
   only genuine script defects.

Return JSON: `{{"status": "ok" or "broken", "repair_notes": "<what you changed and what remains, with line numbers>"}}`.
Set `status` to `ok` only if no parse errors remain.
