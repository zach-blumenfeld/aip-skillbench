# Source and provenance: dialogue-script-parser

## Originals (verbatim copies)

- `dialogue_graph/SKILL.md`: the curated `dialogue-graph` skill, a library guide for building, validating, visualizing, and serializing dialogue graphs.
- `dialogue_graph/scripts/dialogue_graph.py`: its `Node` / `Edge` / `Graph` module.
- `task-instruction.md`: the downstream task statement, which specifies the parse_script contract, the output shape, and the three graph constraints.

## Intent

The downstream agent must write `/app/solution.py` with `parse_script(text)` and produce `/app/dialogue.json` and `/app/dialogue.dot` from `/app/script.txt`. The source skill provides the graph model and visual style but no parser. This skill adds a tested parser and keeps the library API, so the agent copies one file and runs it.

## Component-kind choices

| Component | Kind | Why |
|---|---|---|
| Environment check (step 1) | execution | A deterministic version/package check. The script is stdlib-only, so nothing can block the core deliverable. |
| Parse + build + validate + write JSON/DOT (step 2, `scripts/solution.py`) | execution | Line classification (header / speaker line / numbered option), the End exemption, reachability, and DOT styling are all fixed rules over structured text. One file holds both the library and the parser, because the task requires a single `solution.py`. |
| DOT writer (`Graph.to_dot`) | execution, inside the same script | The task needs `.dot` text. The source's `visualize()` needs the graphviz package plus the binary and only writes rendered images. `to_dot()` writes the same styling with no dependencies, and `visualize()` is kept on top of it for PNG/SVG. |
| Warning/error triage (step 3, `cause`) | decision (choice) | Whether an unparsed line is new syntax or a real defect in the script depends on reading the input. The answer set is fixed: parser_gap / input_defect / benign. |
| Extending the parser for new syntax | client_task | New code has to be written for syntax no one could predict. This only runs on `parser_gap`. |
| Deliverable confirmation (step 4) | execution | A deterministic import check plus an equality check. |

## Design decisions (from source conventions + task statement)

- **Edge text for options keeps the number and tag** (`"1. Run away"`). The source example uses `Edge(..., text="1. Run away")`, and the source visualizer detects skill checks by `[` `]` in the edge text.
- **`End` is not emitted as a node by default.** The source `validate()` exempts the target `End`, the source `visualize()` adds `End` only in the drawing, and the task says "all edge targets must exist except the last node". `--add-end-node` is the escape hatch.
- **Choice nodes have empty text/speaker.** This matches the source example `Node(id="Choices", type="choice")`.
- **validate() adds a reachability check.** Task constraint (1) is not in the source library. The message format follows the source SKILL.md example ("Edge 'Start'->'Unk' points to missing node 'Unk'"), not the source code's terser "Edge target 'X' not found".
- **Tested against the real `/app/script.txt`** in the task's Docker image (python:3.12.8-slim + graphviz). Result: 204 nodes (146 line, 58 choice) and 321 edges (175 with option text). These counts match the raw file's headers, arrows, and numbered lines. The run reported VALID with two edges into End, `dot -Tsvg` parsed the output, and `--render png` worked.

## Deliberate-drop log

| Source item | Disposition | Rationale |
|---|---|---|
| "When to use" bullets (script parsers, dialogue editors, game logic, visualization) | Kept, in Trigger When #4 | n/a |
| `from dialogue_graph import Graph, Node, Edge` | Adapted to `from solution import ...` | The classes are embedded in solution.py so the deliverable is one file. |
| Sections 1-7 (Graph, add nodes, add edges, export, validate, visualize, load) | Kept, in references/dialogue_graph_api.md + script | n/a |
| Visualization style list (diamond/lightblue, rounded boxes colored by speaker, bold blue skill edges, gray option edges, black transitions) | Kept, in `to_dot()` + reference | Speaker color table and truncation lengths are kept exactly. |
| `pip install graphviz` / Graphviz binary requirement | Kept, in compatibility + step 1 + reference | It is optional now, because `.dot` text needs neither. |
| `visualize()` builds via `Digraph` then `render` | Adapted: renders `Source(to_dot())` | Same output, and there is one styling implementation to maintain. |
| `dot.attr(comment='Dialogue Graph')` | Kept as a `// Dialogue Graph` line in DOT | n/a |
| `to_json()` `indent=2` | Kept; added `ensure_ascii=False` | Keeps em-dashes and other characters readable. JSON semantics are unchanged. |
| `Edge.to_dict` omitting `text` when `None` | Kept | n/a |
| Source `validate()` message wording "Edge target 'X' not found" | Replaced by the SKILL.md-documented wording | The two source files disagree. The documented example wins. |

## Functional-test log (this session, task Docker image)

- Real `/app/script.txt`: steps 1, 2, and 4 ran exactly as written, exit 0, VALID, and the counts matched the grep checks (204/321/175). `dot -Tsvg` parsed the DOT file.
- Branches covered with synthetic scripts under `scratch/`:
  - the task-statement example: exit 1, missing targets, `input_defect`
  - multiple speaker lines, `1)` options, a choice without a target, an empty block, `--add-end-node`
  - a duplicate id, a file with no headers, a missing file: all exit 2
  - `--render` without graphviz: warning, still exit 0
  - stray text and comments before the first header: `benign`
  - `- option` bullets: `parser_gap`. The run said VALID but had a warning and 0 choice nodes. The client task extended `CHOICE` to `^(\d+\s*[.)]|[-*])\s*\S`, and the re-run gave 1 choice node with 2 text edges.
- Bug found and fixed during testing: an empty block was warned about but never added as a node.
