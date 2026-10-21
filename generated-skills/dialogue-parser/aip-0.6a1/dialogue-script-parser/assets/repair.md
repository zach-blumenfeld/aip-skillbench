# Repair the dialogue parser ({meta.name})

The installed parser `{solution_path}` parsed `{script_path}` but the graph failed validation.

- First node: `{first_node}` — nodes: {node_count}, edges: {edge_count}, edges into `End`: {end_edge_count}
- Errors: {graph_errors}
- Warnings: {graph_warnings}

Decide which kind each error is, by opening `{script_path}` at the cited line or node:

1. **Parser gap** — the script uses a variant the parser does not recognise (different header
   brackets, `1)` vs `1.`, a speaker-less line, a section with several dialogue lines, comments,
   odd whitespace or encoding). Edit `{solution_path}` (functions `build_graph` / the regexes at the
   top) so the variant parses, keeping the output contract below. Never special-case node ids or
   hardcode the expected graph: the parser must work on any script of this format.
2. **Script defect** — the script itself names a target that has no `[Header]` (other than `End`)
   or contains a section nothing links to. Do not edit the script and do not invent nodes; keep the
   parser faithful and report the defect in `repair_summary`.

After each edit re-run `python3 {solution_path} {script_path} {json_path} {dot_path}`: it rewrites
both outputs and prints a report (exit 0 = valid). Repeat until it is valid or only script
defects remain.

Output contract that must survive any edit:
- `parse_script(text: str)` in `{solution_path}` returns a dict with lists `nodes` and `edges`, and
  `{json_path}` holds exactly that for the task script.
- each node has keys `id`, `text`, `speaker`, `type`, with `type` `"line"` (dialogue: speaker + text) or
  `"choice"` (option hub: text `""`, speaker `""`); the first `[Header]` is `nodes[0]`.
- each edge has keys `from`, `to`, `text`: line transitions have text `""`; choice edges carry the full
  option text as written (`"3. [Lie] I'm a merchant..."`).
- `End` is a virtual terminal: edges may target it, it is not added to `nodes`, it is drawn in the
  .dot as a doublecircle.
- `{dot_path}` is a Graphviz `digraph` (choice = diamond, line = rounded box, End = doublecircle).

Answer with `final_status` (`valid`, or `script_defect` when only script defects remain) and
`repair_summary` (what you changed in the parser and why, or which script defects remain).
