---
name: dialogue-graph
description: |
  Build, validate, visualize, and serialize dialogue graphs (branching narrative trees) and parse bracketed dialogue scripts into the JSON ({"nodes":[...],"edges":[...]}) plus Graphviz DOT artifacts the dialogue-parser task expects. Use when converting scripts with [NodeID] headers, "Speaker: Text -> Target" lines, and "N. Choice -> Target" options into structured graphs, when constructing branching narratives programmatically, or when generating PNG/SVG/DOT visualizations of dialogue flow.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: |
  Requires Python 3.10+. The `graphviz` Python package and Graphviz system binary are optional — needed only for PNG/SVG rendering. The bundled parser script falls back to a hand-written DOT when they are absent.
---

```yaml
purpose: >
  Convert bracketed dialogue scripts into validated dialogue graphs and emit
  the JSON + Graphviz DOT artifacts downstream tooling expects. The bundled
  `dialogue_graph` Python module (Node, Edge, Graph) is also exposed for
  ad-hoc construction, traversal, validation, and visualization of any
  branching narrative structure.

trigger_when:
  - 'Converting a bracketed dialogue script (`[NodeID]` headers, `Speaker: Text -> Target`, `N. Choice -> Target`) into a structured graph.'
  - 'Producing `dialogue.json` (`{"nodes":[...],"edges":[...]}`) and/or `dialogue.dot` from such a script.'
  - Building or editing branching narrative or conversation structures programmatically.
  - Validating an existing dialogue graph's edge/node integrity.
  - Generating a PNG/SVG/DOT visualization of a dialogue flow.

do_not_use_when:
  - Input is free-form prose with no `[NodeID]` headers — there is no graph structure to extract.
  - Target output is an LLM transcript or chat-bot prompt, not a typed node/edge graph.

steps:
  - name: locate-inputs
    description: >
      Resolve the input script path and decide output paths. The
      dialogue-parser task's expected I/O is `/app/script.txt` →
      `/app/dialogue.json` + `/app/dialogue.dot`. Outside Docker, fall back to
      `./script.txt` and write outputs next to it.
    outputs:
      - name: input-path
        type: string
        description: Resolved path to the dialogue script.
      - name: json-output-path
        type: string
        description: Destination for the dialogue JSON (default `/app/dialogue.json`).
      - name: dot-output-path
        type: string
        description: Destination for the DOT visualization (default `/app/dialogue.dot`).

  - name: inspect-format
    description: >
      Read the first ~30 lines of the script and confirm the bracketed format
      — `[NodeID]` headers, `Speaker: Text -> Target` transitions, and
      numbered `N. ...` choice lines (optionally tagged `[Skill]`). If the
      script does not match this format, stop and report — this skill is the
      wrong fit. Lines starting with `//` and blank lines are skipped by the
      parser.
    inputs:
      - name: input-path
        type: string

  - name: parse-and-export
    description: >
      Run the deterministic parser. It builds a `Graph` from the bracketed
      script via the bundled library, calls `graph.validate()`, writes the
      JSON output through `Graph.to_json()`, and emits the DOT source through
      `Graph.visualize(..., format='dot')` (with a hand-written DOT fallback
      when the `graphviz` package is unavailable).
    script: scripts/parse_script.py
    inputs:
      - name: input-path
        type: string
      - name: json-output-path
        type: string
      - name: dot-output-path
        type: string
    outputs:
      - name: dialogue-json-path
        type: string
        description: Path to the written `dialogue.json`.
      - name: dialogue-dot-path
        type: string
        description: Path to the written `dialogue.dot`.
      - name: validation-warnings
        type: list[string]
        description: Missing edge source/target warnings printed on stderr.

  - name: verify-outputs
    description: >
      Confirm both files exist and are non-empty. Spot-check the JSON: it must
      have top-level `nodes` and `edges` lists; every node must carry `id`,
      `text`, `speaker`, and `type` (one of `line` / `choice`); every edge
      must carry `from`, `to`, and `text`. Spot-check the DOT: it must contain
      `digraph`, balanced `{` `}`, `->`, and `shape=diamond` for choice nodes.
      If anything is off, do NOT re-run the parser blindly — read the
      warnings surfaced in the previous step first.
    inputs:
      - name: dialogue-json-path
        type: string
      - name: dialogue-dot-path
        type: string

  - name: address-warnings
    description: >
      Interpret `validation-warnings` case by case. Warnings about edges
      whose target is `End` are intentional — `End` is a sentinel and does
      not need a node definition. Any other missing-target warning signals a
      typo in the script or a header the parser skipped. Read the offending
      line(s) in the script before deciding whether to amend the input or
      accept the warning.
    inputs:
      - name: validation-warnings
        type: list[string]

modes:
  - name: parse-script-end-to-end
    body: >
      Default mode for the dialogue-parser task. Invoke
      `python scripts/parse_script.py --input <script> --output-json <json>
      --output-dot <dot>`. The script reads the bracketed format, builds the
      graph, validates, writes both artifacts, and prints node/edge counts.

  - name: programmatic-build
    body: |
      For agents constructing a dialogue tree from scratch (not parsing text),
      import the library directly:

          from dialogue_graph import Graph, Node, Edge
          g = Graph()
          g.add_node(Node(id="Start", speaker="Guard", text="Halt!", type="line"))
          g.add_node(Node(id="Choices", type="choice"))
          g.add_edge(Edge(source="Start",   target="Choices"))
          g.add_edge(Edge(source="Choices", target="End", text="1. Run away"))
          errors = g.validate()
          open("dialogue.json", "w").write(g.to_json())
          g.visualize("dialogue", format="png")

      `add_node` raises `ValueError` on duplicate IDs. `add_edge` does NOT —
      duplicate or missing-target edges surface only through `validate()`.

  - name: load-existing-graph
    body: |
      For agents reading an existing graph, the library exposes three entry
      points; all return a populated `Graph`:

          Graph.from_file("dialogue.json")
          Graph.from_dict({"nodes": [...], "edges": [...]})
          Graph.from_json(json_string)

      Wire-format edges use `from` / `to` / `text`; the in-memory `Edge`
      attributes are `source` / `target` / `text`. Always serialize through
      `to_dict` / `to_json` (and deserialize through `from_dict` /
      `from_json`) to keep these in sync.

scenarios:
  - need: >
      Parse `/app/script.txt` (quest-style branching dialogue, ~150 nodes)
      into `/app/dialogue.json` and `/app/dialogue.dot` for the
      dialogue-parser task.
    action: >
      Run `python scripts/parse_script.py --input /app/script.txt
      --output-json /app/dialogue.json --output-dot /app/dialogue.dot`. Verify
      JSON has both `nodes` and `edges` lists and DOT contains `digraph` and
      `shape=diamond`.
    outcome: >
      Two files written. Validation warnings about `End` targets are benign;
      other missing-target warnings indicate a script issue.

  - need: Visualize a dialogue graph as PNG for human review.
    context: The agent already has an in-memory `Graph` object.
    action: >
      Call `graph.visualize("dialogue_graph", format="png")`. Requires the
      `graphviz` Python package AND the Graphviz `dot` system binary.
    outcome: A `dialogue_graph.png` file is written; the path is returned.

  - need: Add a skill-check choice (e.g. `[Lie]`, `[Attack]`) to a graph.
    action: >
      Add an edge whose `text` includes the bracketed skill tag inside the
      numbered option, e.g. `Edge(source="Hub", target="LiePath",
      text="3. [Lie] I'm a merchant.")`. The library's `visualize` draws
      such edges bold dark-blue.
    outcome: The DOT output uses `color=darkblue, style=bold` on that edge.

anti_patterns:
  - Hand-writing a regex parser when `scripts/parse_script.py` already handles the bracketed format (headers, numbered choices, `[Skill]` tags, `//` comments, `End` sentinel).
  - Editing the bundled `dialogue_graph.py` library — its method signatures are referenced by callers and downstream tests.
  - Treating warnings about edges to `End` as errors. `End` is a sentinel target by design.
  - Calling `graph.visualize(..., format='png'|'svg')` without installing both the `graphviz` Python package AND the Graphviz `dot` system binary. For DOT-only output, prefer the parser script — it falls back to a hand-written DOT when Graphviz is unavailable.
  - Confusing edge field names — wire JSON uses `from` / `to`; the `Edge` object exposes `source` / `target`. Always go through `to_dict` / `from_dict`.
  - Re-running the parser in a loop hoping warnings disappear. Warnings come from missing target nodes — fix the script or accept them.
  - Stripping `[Skill]` tags out of choice edge text. The styling (bold-blue) and downstream test fixtures depend on the tags being preserved verbatim inside the numbered option string.
```
