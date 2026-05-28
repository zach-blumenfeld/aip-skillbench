---
name: dialogue-graph
description: A library for building, validating, visualizing, and serializing dialogue graphs. Use this when parsing scripts or creating branching narrative structures.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Build, validate, visualize, and serialize dialogue graphs using the
  bundled `dialogue_graph` Python module. The module exposes `Graph`,
  `Node`, and `Edge` classes that represent branching dialogue as
  line/choice nodes connected by edges, with JSON round-tripping and
  Graphviz-based visualization.

trigger_when:
  - Parsing scripts or text into structured dialogue data.
  - Building tools that edit conversation flow.
  - Traversing dialogue trees for game logic.
  - Generating visual diagrams of dialogue flows.
  - Creating branching narrative structures.

steps:
  - name: import-module
    description: |
      Import the classes from the bundled module:
      `from dialogue_graph import Graph, Node, Edge`.
  - name: create-graph
    description: |
      Instantiate the container: `graph = Graph()`. A Graph holds a
      dict of nodes keyed by id and a list of edges.
  - name: add-nodes
    description: |
      Add `Node(id, speaker="", text="", type="line")` instances via
      `graph.add_node(...)`. Use `type="line"` for spoken beats (with
      `speaker` and `text`) and `type="choice"` for choice hubs (id
      only). Node ids must be unique — duplicates raise ValueError.
      Examples:
      `graph.add_node(Node(id="Start", speaker="Guard", text="Halt!", type="line"))`
      `graph.add_node(Node(id="Choices", type="choice"))`
  - name: add-edges
    description: |
      Connect nodes with `Edge(source, target, text="")` via
      `graph.add_edge(...)`. Leave `text` empty for plain transitions;
      set it to the choice label (e.g. `"1. Run away"`) or skill-check
      tag (e.g. `"[Lie]"`) for choice transitions. The literal target
      `"End"` is treated as an implicit terminal node by `validate()`.
  - name: validate-graph
    description: |
      Call `errors = graph.validate()` to check integrity. Returns a
      list of strings — empty means valid. Catches edges whose source
      or target is missing (other than `"End"`).
  - name: export
    description: |
      Serialize with `graph.to_dict()` to get
      `{"nodes": [...], "edges": [...]}` (edges use `from`/`to`/`text`),
      or `graph.to_json()` for an indented JSON string.
  - name: visualize
    description: |
      Render a diagram with `graph.visualize('output_file')` (PNG by
      default) or `graph.visualize('output_file', format='svg')`.
      Requires the `graphviz` Python package and the Graphviz system
      binary. Choice nodes render as light-blue diamonds; line nodes
      as rounded boxes colored by speaker; an implicit `End` double
      circle is added. Edges whose text contains `[...]` (skill
      checks) render bold dark-blue; other labeled edges render gray;
      unlabeled edges render black.
  - name: load
    description: |
      Reload from serialized form via `Graph.from_file('dialogue.json')`,
      `Graph.from_dict({'nodes': [...], 'edges': [...]})`, or
      `Graph.from_json(json_string)`. Edge dicts use `from`/`to` keys,
      not `source`/`target`.

decisions:
  - signal: Need a branching dialogue beat with multiple player options.
    action: Add a `type="choice"` hub node, then one labeled edge per option.
  - signal: A choice represents a skill check (Lie, Attack, Persuade, etc.).
    action: Use square-bracket syntax in edge text (e.g. `"[Lie]"`) so visualization highlights it.
  - signal: An edge should terminate the dialogue.
    action: Point its target at the literal id `"End"` — `validate()` accepts it implicitly and `visualize()` renders a terminal node.
  - signal: "`visualize()` raises ImportError."
    action: "Install both the Python package (`pip install graphviz`) and the Graphviz system binary from https://graphviz.org/download/."

scenarios:
  - need: Convert a parsed script into a dialogue graph for a game engine.
    action: |
      Build a Graph; add a line Node per spoken beat and a choice Node
      per branching point; add Edges (with text on choice transitions);
      run `validate()` to catch dangling references; call `to_json()`
      to hand off to the engine.
    outcome: A round-trippable JSON document the engine can load with `Graph.from_json`.
  - need: Inspect an existing dialogue structure visually.
    context: A `dialogue.json` file exists from a prior export.
    action: |
      `graph = Graph.from_file('dialogue.json')`, then
      `graph.visualize('dialogue_graph')` to produce `dialogue_graph.png`.
    outcome: PNG with diamond choice hubs, speaker-colored line boxes, and styled edges.

anti_patterns:
  - Adding two nodes with the same id — `add_node` raises ValueError; pick unique ids per beat.
  - Putting dialogue text on a `type="choice"` node — choice nodes are hubs; put text on the inbound/outbound edges or on adjacent line nodes.
  - Using `source`/`target` keys when loading from a dict — the wire format uses `from`/`to`.
  - Calling `visualize()` without the Graphviz system binary installed — the Python package alone is insufficient.
```
