---
name: dialogue-script-parser
description: "Parse [SceneName]-style branching dialogue scripts into a {nodes, edges} JSON graph plus a Graphviz .dot visualization, and emit a solution.py exposing parse_script(text). Use when the task input is /app/script.txt with 'Speaker: text -> Target' lines and 'N. choice -> Target' options, and the expected outputs are /app/dialogue.json, /app/dialogue.dot, and a parse_script function. Covers grammar parsing, choice vs line node typing, implicit 'End' handling, and reachability/target validation."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.9+ on the solver environment. No external packages; only stdlib (re, json, pathlib).
---

```yaml
purpose: >
  Convert dialogue scripts written in the [SceneName] + line/choice DSL into a
  validated JSON node-edge graph plus a Graphviz .dot visualization, and ship
  a solution.py module exposing parse_script(text) -> {"nodes": [...],
  "edges": [...]}. The grading harness imports parse_script by name, so the
  function signature and return shape are load-bearing.

trigger_when:
  - "Task names /app/script.txt as input and /app/dialogue.json plus /app/dialogue.dot as outputs."
  - "Task requires solution.py with a parse_script(text: str) function whose return value is graded directly."
  - "Source uses [SceneName] headers, 'Speaker: text -> Target' lines, and numbered 'N. text -> Target' choice options."
  - "Task references nodes with keys id/text/speaker/type and edges with keys from/to/text."

do_not_use_when:
  - Parsing a different dialogue DSL (Ink, YarnSpinner, Twine, Ren'Py).
  - Building a runtime dialogue engine rather than a static parser.
  - Editing or generating new dialogue content — this skill only reads existing scripts.

scope_and_approval: >
  Read-only on /app/script.txt; writes /app/dialogue.json, /app/dialogue.dot,
  and /app/solution.py. Pure stdlib, no network. Validation (steps.validate-graph)
  is part of the procedure, not an optional polish step — do not skip it.

steps:
  - name: read-input
    description: Read /app/script.txt as UTF-8 text. Refuse to continue if empty.
  - name: tokenize-blocks
    description: >
      Split into scene blocks. A block boundary is one or more blank lines. The
      first non-blank line of each block must match ^\[([^\]]+)\]$ — capture the
      group as the scene id. Remaining non-blank lines form the block body, in
      order. Preserve the original block order; the first block is the start node.
  - name: classify-blocks
    description: >
      A block is a choice node when every body line matches ^\d+\.\s+. Otherwise
      it is a line node. Choice scenes typically have 2-4 options; line scenes
      typically have a single body line.
  - name: parse-lines
    description: >
      For a line block, match ^(?P<speaker>[^:]+):\s*(?P<text>.+?)(?:\s*->\s*(?P<target>\S+))?\s*$
      on the first body line. Emit {id, text, speaker, type:"line"}. Preserve
      trailing punctuation in text. If a target was captured, emit one edge
      {from:id, to:target, text:""}. A line scene with no target is a terminal.
  - name: parse-choices
    description: >
      For a choice block, emit {id, text:"", speaker:"", type:"choice"}. For each
      option, match ^\d+\.\s*(?P<text>.+?)(?:\s*->\s*(?P<target>\S+))?\s*$ and
      emit one edge {from:id, to:target, text:option_text}. Keep bracketed tags
      like [Lie], [Attack], [Persuade] inside the edge text verbatim — tests
      check for them.
  - name: synthesize-implicit-nodes
    description: >
      Collect every edge.to. Any target id that is not the id of a defined scene
      must be appended as a terminal node {id:target, text:"", speaker:"",
      type:"line"}. The canonical case is "End" referenced repeatedly but never
      declared as [End]. Do this once, after all blocks are parsed.
  - name: validate-graph
    description: >
      Run scripts/validate_graph.py on the in-memory or serialized graph. It
      enforces (a) every edge.to resolves to a node id, and (b) every node is
      reachable from the first node via forward edges. Fix violations before
      writing outputs — re-parse, fix typos, or add missing edges.
  - name: write-json
    description: >
      Serialize the graph with json.dumps(graph, indent=2) and write to
      /app/dialogue.json. Top-level shape is exactly {"nodes":[...], "edges":[...]}.
      No extra wrapper keys.
  - name: write-dot
    description: >
      Write a Graphviz directed graph to /app/dialogue.dot. Emit `digraph
      dialogue { ... }`. Use shape=box for line nodes, shape=diamond for choice
      nodes. Edge labels carry the edge text — emit `[label="..."]` only when
      non-empty. Quote node ids and labels; escape embedded backslashes and
      double quotes.
  - name: write-solution
    description: >
      Place a Python module at /app/solution.py that defines parse_script(text:
      str) and returns the same dict shape as the in-memory graph. The fastest
      route is to copy scripts/parse_dialogue.py verbatim — it already exposes
      parse_script and, when run as __main__, also writes dialogue.json and
      dialogue.dot.

decisions:
  - signal: A line block has no `->` on its body line.
    action: Emit the node with no outgoing edge — this is a terminal scene. Reachability still holds as long as something routes to it.
  - signal: A line block spans multiple non-empty body lines.
    action: Match the first line with LINE_RE for speaker/text/target; concatenate trailing lines into the node text with spaces. Speaker stays from the first line.
  - signal: An edge target id is never declared as a scene header.
    action: Synthesize a terminal node {id:target, text:"", speaker:"", type:"line"}. Do not drop the edge. The common case is `-> End`.
  - signal: validate_graph.py reports an unreachable node.
    action: Most likely a typo in a `->` target. Compare unreachable ids to defined ids and look for off-by-one letter mismatches. Fix the source-level typo or, if intentional, drop the orphan node.
  - signal: A choice option lacks `->` after the text.
    action: Treat as malformed input. The DSL assumes every choice routes somewhere; flag it rather than silently emitting an edge with empty `to`.
  - signal: The script ends without a [End] block but references `-> End`.
    action: This is expected — the synthesize-implicit-nodes step adds it. Do not invent text or speaker for it; both are empty strings.

scenarios:
  - need: Single-line scene routing to the next scene.
    context: "Input block:\n[GateScene]\nGuard: Halt! State your name and business. -> NameChoice"
    action: >
      Emit node {id:"GateScene", text:"Halt! State your name and business.",
      speaker:"Guard", type:"line"} and edge {from:"GateScene", to:"NameChoice",
      text:""}. Trailing period stays in the node text.
    outcome: One node, one edge.
  - need: Choice scene with bracketed action tags.
    context: "Input block:\n[NameChoice]\n1. I am Sir Aldric, Knight of the Realm. -> KnightPath\n3. [Lie] I'm a merchant with important goods. -> MerchantPath"
    action: >
      Emit node {id:"NameChoice", text:"", speaker:"", type:"choice"} plus one
      edge per option. The Lie/Attack tags stay inside the edge text — e.g.,
      {from:"NameChoice", to:"MerchantPath", text:"[Lie] I'm a merchant with important goods."}.
    outcome: One choice node, N edges, tags preserved.
  - need: Reference to "End" with no [End] block.
    context: Multiple branches all funnel into `-> End`, but the source file never declares [End].
    action: After parsing, the synthesize-implicit-nodes step appends {id:"End", text:"", speaker:"", type:"line"} so every edge resolves.
    outcome: validate_graph.py reports ok; "End" is reachable from the start node by multiple paths, satisfying constraint (3).

anti_patterns:
  - Stripping trailing punctuation (`.` `!` `?`) from line text. Preserve it — the spec uses the source verbatim.
  - Dropping bracketed tags like [Lie], [Attack], [Persuade] from choice option text. They are part of the displayed choice and tests check for them.
  - Putting choice option text into the choice node's `text` field. Choice nodes have empty `text`; the option text lives on the edge.
  - Allowing whitespace inside the target id when matching `->`. The target is a single \S+ token; greedy matching past it corrupts ids.
  - Hardcoding `GateScene`, `NameChoice`, or `End` as the start node. The start is whatever scene appears first in the file.
  - Skipping the reachability check. Constraint (1) is graded — silently emitting an unreachable orphan fails the task.
  - Adding outgoing edges to synthesized terminal nodes (e.g., "End"). Terminals have no outgoing edges; only inbound.
  - "Wrapping the output in an extra key (e.g., `{\"graph\": {\"nodes\": ..., \"edges\": ...}}`). Top-level must be exactly `{\"nodes\": [...], \"edges\": [...]}`."
  - Loading references/format.md when the body already covers the grammar. Load it on demand only when an unusual block shape forces a re-read of the spec.
```
