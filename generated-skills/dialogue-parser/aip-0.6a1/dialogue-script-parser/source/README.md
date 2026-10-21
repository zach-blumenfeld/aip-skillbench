# Source material for `dialogue-script-parser`

## Provenance

| File | Origin | Status |
|---|---|---|
| `dialogue_graph/SKILL.md` | curated skill `inputs/skills/dialogue_graph/SKILL.md` | verbatim copy |
| `dialogue_graph/scripts/dialogue_graph.py` | curated skill `inputs/skills/dialogue_graph/scripts/dialogue_graph.py` | verbatim copy |
| `task-instruction.md` | the task statement the downstream agent receives (`inputs/instruction.md`) | verbatim copy, used for the output contract and the three graph constraints |

The task's real input (`script.txt`, 22,785 bytes, 204 `[Header]` sections, 321 `->` transitions,
58 choice sections, speakers Narrator/Stranger/Merchant/Barkeep/Kira, two edges into `End`) and its
Dockerfile (`python:3.12.8-slim`, `pip graphviz==0.20.3`, apt `graphviz`) were used to test, not copied.

## Intent

The task wants `/app/solution.py` with `parse_script(text)`, `/app/dialogue.json`, and
`/app/dialogue.dot`. The curated skill supplies a `Graph`/`Node`/`Edge` library with validation,
JSON serialization, and Graphviz styling, but no parser. The compiled skill bundles a tested parser
built on that library, installs and runs it by script, validates the task constraints, and only hands
work to the agent when the script uses a format variant the parser misses.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| `build-graph` | execution | Parsing a fixed line grammar, serializing, and checking reachability / missing targets / JSON == `parse_script` are deterministic. One script (`scripts/build_graph.py`) installs `scripts/solution.py` at `solution_path`, imports the installed copy, and calls its `run()`. |
| `by-status` | router | Branches on the script's own `graph_status` (`valid` / `invalid`); no judgment needed, so no decision step. |
| `repair-parser` | client_task | Adapting a parser to an unseen format variant is code generation, and telling a parser gap from a genuine script defect needs reading the script. Template `assets/repair.md`; lazy reference `references/script-format.md`. |
| `end` | end | Returns the three paths, the first-build status, and the counts. |

`solution.py` is self-contained (classes embedded rather than importing `dialogue_graph`) because the
task's tests import `/app/solution.py` alone. It needs only the stdlib; it uses the `graphviz`
package for the .dot when importable and falls back to a plain DOT writer otherwise. The `dot`
binary is used only for an optional render check (skipped when absent), so it is not in `requires.tools`.

### Format decisions (not dictated by the sources, chosen and documented)

- `End` is virtual: never added to `nodes`, allowed as an edge target (source `validate()` and the
  task's "all edge targets must exist except the last node"), drawn in the .dot as a doublecircle
  (source `visualize()`).
- Choice edge text keeps the option text as written, number and `[Skill]` tag included, following
  the source example `Edge(source="Choices", target="End", text="1. Run away")`.
- Choice nodes have `text: ""`, `speaker: ""` (source example `Node(id="Choices", type="choice")`);
  if a section has a dialogue line *and* options, the choice node carries that line's speaker/text.
- Line transitions carry `text: ""`; every edge always has `from`, `to`, `text` (task format).

## Completeness check (source → compiled skill)

| Source item | Where it lives now |
|---|---|
| frontmatter description ("building, validating, visualizing, serializing dialogue graphs; parsing scripts, branching narrative") | SKILL.md `description`, `trigger_when[2]` |
| When to use: Script Parsers / Dialogue Editors / Game Logic / Visualization | `trigger_when[0]`, `trigger_when[2]` |
| `from dialogue_graph import Graph, Node, Edge` | classes embedded in `scripts/solution.py`; anti-pattern "Leaving parse_script only in a helper module" |
| `Graph()` container; `add_node` raises on duplicate id | `solution.py` `Graph.add_node`; the parser merges duplicate headers and reports them as an error |
| Regular line node `Node(id, speaker, text, type="line")`; choice hub `Node(id, type="choice")` | `solution.py` `Node`, `build_graph`; contract in `assets/repair.md` and `references/script-format.md` |
| `add_edge`; simple transition without text; choice transition with `"1. Run away"` text | `solution.py` `build_graph`; anti-pattern on stripping numbers/tags |
| `to_dict()` → `{"nodes","edges"}`, `to_json()` | `solution.py` `to_dict`, `to_json`; `parse_script` returns `to_dict()` |
| `validate()` → list of strings, e.g. `"Edge 'Start'->'Unk' points to missing node 'Unk'"`; End exempt | `solution.py` `validate` (same message format, End exempt), extended with reachability from the first node and parse issues; surfaced as `graph_errors` |
| `visualize()` PNG/SVG; requires `pip install graphviz` + Graphviz binary | `solution.py` `visualize` (renders via `graphviz.Source`); `to_dot` writes the .dot the task needs; `requires.packages: graphviz` |
| Diamond lightblue choice nodes; rounded boxes coloured by speaker; speaker colour map (Narrator, Guard, Stranger, Merchant, Barkeep, Kira); white default | `solution.py` `SPEAKER_COLORS`, `_dot_items`; `references/script-format.md` |
| Bold dark-blue edges for skill checks (`[` and `]` in text); gray40 regular choices; black plain transitions | `solution.py` `_dot_items`; reference |
| End node `END` doublecircle lightgray | `solution.py` `_dot_items`; anti-pattern on End |
| Label truncation (node text 40→37+`...`, edge text 30→27+`...`); `id\nSpeaker: text` labels | `solution.py` `_dot_items`; reference |
| Graph attrs `rankdir=TB`, `nodesep=0.5`, `ranksep=0.8`; Arial 10 nodes / 8 edges; comment "Dialogue Graph" | `solution.py` `to_dot` / `_to_dot_plain` |
| `from_file`, `from_dict`, `from_json` (with defaults text/speaker `""`, type `line`) | `solution.py` static methods |
| `Node.type` is `'line'` or `'choice'` | `solution.py` `Node`; contract |
| Task: parse_script in solution.py, dialogue.json, dialogue.dot, node/edge key sets, three constraints | `build-graph` inputs/outputs, `solution.py` `run`, `assets/repair.md`, anti-patterns |

## Deliberate-drop log

| Dropped / changed | Rationale |
|---|---|
| `splines='ortho'` graph attribute | Graphviz warns "Orthogonal edges do not currently handle edge labels" for every labelled choice edge; dropping it keeps `dot` output clean. Layout only, no information lost. |
| `Edge.to_dict` omitting `text` when it is `None` | The task's edge format always has `text`; it is now always emitted (`""` when absent). |
| `visualize()` writing PNG with `cleanup=True` as the main output | The task needs the `.dot` source, so `to_dot()` is the primary path; `visualize()` kept for images. |
| Install instructions (`pip install graphviz`, graphviz.org download link) | The container already provides both; captured as `requires.packages` instead of prose. |
| Fixed colour map only | Kept, plus a rotating palette for speakers outside the map (other task instances have other casts). Additive. |
