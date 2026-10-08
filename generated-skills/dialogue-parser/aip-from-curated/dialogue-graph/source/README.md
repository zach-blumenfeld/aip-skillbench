# dialogue-graph — provenance and compile notes

## Provenance

Compiled from one curated Agent Skill, copied verbatim under `source/dialogue_graph/`:

| File | Role |
|---|---|
| `dialogue_graph/SKILL.md` | Usage guide for the `dialogue_graph` module: Graph/Node/Edge, export, validation, visualization, loading. |
| `dialogue_graph/scripts/dialogue_graph.py` | The library itself (stdlib + optional `graphviz`). |

Environment context used (not copied, since it describes the task container rather than the skill):
the task's `Dockerfile` (`python:3.12.8-slim`, `pip install graphviz==0.20.3`, apt `graphviz`,
input copied to `/app/script.txt`, `WORKDIR /app`) and the input `script.txt` (22,785 bytes, UTF-8,
LF, 204 `[NodeId]` blocks, `Speaker: text -> Target` lines, numbered `N. [Skill] text -> Target`
options, two transitions into `End`, which has no block). The manifest gives the real size, and the
file in `inputs/` is that full file.

The source skill is a library manual: it says *how to build* a graph, not how to turn a script into one.
The compiled procedure adds the missing workflow (parse the script format → validate → export →
check against the task), and keeps the library as the data model and serializer.

## Pack layout

- `scripts/dialogue_graph.py`: the source library, verbatim. `dialogue_tool.py` imports it.
- `scripts/dialogue_tool.py`: parser + extended validation + DOT emitter/renderer. Runs as an AIP
  execution step (JSON on stdin), as a CLI, or as an importable module (`parse_script`), so it can be
  shipped as the task's parser program. Stdlib only. Rendering shells out to the Graphviz `dot` binary,
  which the container has.
- `assets/repair.md`, `assets/deliver.md`: client-task templates.
- `references/format-and-api.md`: script syntax, parse rules for irregular blocks, the output JSON
  shape, the full library API from the source SKILL.md, and the visualization legend.

## Step-kind choices

| Step | Kind | Why |
|---|---|---|
| `conventions` | decision | Two output conventions the source leaves open (End as a virtual target vs a node; choice-edge text with or without numbering) depend on reading the task's wording, and the answer space is fixed. Choice questions with library-backed defaults (`virtual`, `verbatim`) and thresholds 0.7 so an unclear spec gets a second look. |
| `build` | execution | Parsing a line grammar, building Graph/Node/Edge, integrity checks, JSON serialization, and DOT generation are all deterministic. Hand-transcribing 200+ nodes is the main failure mode, so this is a script. |
| `by-status` | router | Branches on the script's `status` (`ok` / `broken`). |
| `repair` | client_task | Telling a parser mismatch from a genuine script defect, and choosing how to fix it, needs judgment over the raw text. Open-ended, so it is a client task. |
| `deliver` | client_task | Output paths, any task-specific JSON shape, and parser-code deliverables (function signature, filename) vary by task. The agent has to adapt and verify them. |
| `end` | end | Graph path, deliverables, summary. |

## Design decisions (beyond the source)

- **Choice-edge text verbatim by default** (`"1. Approach the hooded stranger."`, `[Skill]` tags kept),
  following the source's own example `Edge(source="Choices", target="End", text="1. Run away")`.
- **End is virtual by default**, following `Graph.validate()`, which accepts `End` without a node, and
  `visualize()`, which draws its own END node. `explicit` appends `{"id":"End","text":"","speaker":"","type":"line"}`
  (`type` stays within the library's `line`/`choice` vocabulary).
- **Choice hubs** are `Node(id, type="choice")` with empty speaker/text, as in the source example.
- **Split on the last `->`, speaker on the first `:`**, because the real text contains `:`, `?!`, and `—`.
- **Irregular blocks**, which are absent from the real file but handled so other scripts don't break:
  several dialogue lines in one block are chained as `Id`, `Id_2`, …; dialogue followed by options makes
  the last line's node the choice hub; a speakerless line is kept with a warning.
- **Extended validation**: the library's `validate()` plus duplicate ids (where the library would raise
  `ValueError`), empty blocks, unparseable lines, choice hubs without options (errors), and dead ends,
  nodes unreachable from the first block, and no path to End (warnings).
- **DOT emitted directly**, with the same styling as `Graph.visualize()`, because `visualize()` renders
  with `cleanup=True` and deletes the `.dot` source. A task asking for a `.dot` file would otherwise get
  nothing. Rendering uses `dot -T<ext>`.
- **Nodes and edges keep script order.** The first block is the start.

## Completeness check (source line by line)

| Source item | Where it lives in the pack |
|---|---|
| Frontmatter: build/validate/visualize/serialize dialogue graphs; parsing scripts, branching narratives | `description`, `purpose`, `trigger_when` |
| When to use: script parsers, dialogue editors, game logic traversal, visualization | `trigger_when` (all four) |
| `from dialogue_graph import Graph, Node, Edge` | reference §Library API. `dialogue_tool.py` imports it. |
| `Graph()` container | reference. Used by `dialogue_tool.parse_script`. |
| Adding nodes: line node with speaker/text/type, choice hub `type="choice"` | reference. Parse rules in `dialogue_tool.py`. |
| Adding edges: simple transition, choice transition with text | reference. `dialogue_tool.py`. `choice_text` decision. |
| Export `to_dict()` → `{"nodes","edges"}`, `to_json()` | `build` writes `graph.to_json()`. JSON shape in reference and `deliver` template. |
| Validation `validate()` returning error strings | `check_graph` runs it and adds further checks. Errors route to `repair`. |
| Visualization: PNG/SVG, `pip install graphviz` + Graphviz binary | `build` `image_path` (extension picks format). Reference Graphviz caveats. Dockerfile confirms both present. |
| Legend: diamonds light blue for choices; rounded boxes coloured by speaker; bold blue skill-check edges `[Lie]`/`[Attack]`; gray regular choices; black simple transitions | `to_dot` reproduces each. Legend is in the reference. |
| Loading: `from_file`, `from_dict`, `from_json` | reference §Library API. Named in the `repair` template for patching. |
| Library: `add_node` raises on duplicate id | duplicate-id error in `dialogue_tool.py`. Noted in the reference. |
| Library: `validate` allows target `End` | `end_node: virtual` default and decision instructions |
| Library: `Edge.to_dict` emits `from`/`to`/`text` | JSON shape in the reference. Produced by the library itself. |
| Library: `visualize` details (rankdir TB, ortho splines, nodesep/ranksep, Arial sizes, speaker palette, 40/37 and 30/27 truncation, END doublecircle, `cleanup=True`) | `to_dot` and `SPEAKER_COLORS`. Reference legend. Anti-pattern on `.dot` deletion. |
| Library: `from_dict` defaults (`text`/`speaker` "", `type` "line") | Library copied verbatim. Parser writes every key explicitly. |
| Library: `from_file` reads UTF-8 | anti-pattern on encoding. Parser reads `utf-8-sig`. |

### Deliberate drops

- **"Requires: pip install graphviz" install instructions.** The container already has `graphviz==0.20.3`
  and the binary, and the pack renders through the `dot` binary without the Python package. The
  requirement still appears in the reference as a caveat for `Graph.visualize()`.
- **Link to graphviz.org/download.** Not actionable inside the container.
- **The source's prose headings and code-block layout.** The same content is restructured into the
  reference and the procedure. Nothing is lost.

## Functional test record

Run with `aip run`/`aip resume` from `scratch/` on a copy of the real `script.txt`:

- **ok branch**: conventions → `virtual`/`verbatim`; build → 204 nodes (146 line, 58 choice), 321 edges,
  start `Start`, 2 edges into End, none unreachable; deliver → parser copied and re-run gave byte-identical
  JSON/DOT; DOT parsed by pydot (321 edges). End reached.
- **broken branch**: the real script plus a dangling `-> Vault` and a duplicate `[TavernExit]`;
  conventions → `explicit`/`strip_number`; build → `status: broken` with both errors, the unreachable
  `Cellar` warning, an explicit End node, and stripped option text; repair classified both as genuine
  defects; deliver; End reached.
- PNG rendering was not exercised locally (no `dot` binary on the authoring machine). The container
  installs it.
- **Fresh-agent sessions (2)**: one ran the ok path and wrote a `parser.py` wrapper; the other ran the
  broken path, used explicit End, and reported the defects. Neither hit a script error. Changes made
  from their feedback:
  - added `parse_file(path) -> dict` for parser deliverables
  - documented that `to_json` escapes non-ASCII (`—`)
  - declared every deliver-template key as an input
  - dangling-target errors now carry line numbers
  - `status` carried into `end`
  - repair guidance for task-vs-script conflicts
  - `sys.dont_write_bytecode` so no `__pycache__` lands in the pack

  After the changes the ok path was re-run to the end: 204 nodes, byte-identical JSON.
- `to_dot` was checked against the library's own `visualize()` source (graphviz 0.20.3, render stubbed).
  Every node and edge has identical attributes.
