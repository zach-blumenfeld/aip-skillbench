The dialogue graph for `{script_path}` is built.

- Graph JSON: `{graph_path}` — {node_count} nodes ({line_node_count} line, {choice_node_count} choice), {edge_count} edges, start `{start_node}`, {end_edge_count} edge(s) into End, reaches End: {reaches_end}
- Files written: {files_written}
- Speakers: {speakers}
- Unreachable nodes: {unreachable_nodes}
- Conventions used: {options_used}
- Status: {status}

Task instructions:
{task_instructions}

Check the result against the task instructions, then finish the job:

1. Every output the task names exists at the exact path and filename it names (JSON, `.dot`, image,
   parser program). Re-run the tool with corrected paths if not.
2. The JSON shape matches what the task asks for. If the task spells out keys, types, ordering, or End
   handling that differ from the defaults (`nodes[{{id,text,speaker,type}}]`, `edges[{{from,to,text}}]`,
   choice text verbatim, End virtual), transform the file to the task's shape — the task's spec wins.
3. If the task wants parser code (a script, module, or function), deliver it by copying
   `scripts/dialogue_tool.py` together with `scripts/dialogue_graph.py`; when the task names a signature
   (e.g. `parse_script(path) -> dict`), add a thin wrapper that returns `dialogue_tool.parse_file(path)`.
   Report script defects rather than raising unless the task says invalid input must fail. Run it once
   on the real input and confirm it reproduces the graph JSON.
4. If the task wants a visualization, confirm the image rendered (needs the Graphviz `dot` binary);
   if only DOT text is wanted, the `.dot` file suffices.
5. Spot-check three things against the script: the start node, one choice hub with a `[Skill]` option,
   and one edge into End.

Return JSON: `{{"deliverables": ["<absolute path>", ...], "summary": "<counts, conventions, any defects reported>"}}`.
