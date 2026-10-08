---
name: dialogue-graph
description: >-
  Parse a bracketed branching-dialogue script ([NodeId] blocks, "Speaker: text -> Target" lines, numbered "1. [Skill] option -> Target" choices, End terminal) into a validated dialogue graph JSON (nodes id/text/speaker/type, edges from/to/text), with optional Graphviz DOT/PNG/SVG visualization and a reusable parser. Use for script parsers, dialogue editors, game dialogue trees, and branching-narrative visualization.
metadata:
  aip-version: "0.5a1"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Convert a text dialogue script into a dialogue graph: one node per [NodeId] block
  (type "line" with speaker and text, or type "choice" for numbered-option hubs), one edge
  per transition ("->"), choice edges labelled with the option text, End as the terminal
  target. A decision fixes the output conventions from the task's wording; one script
  parses, validates (dangling targets, duplicates, unreachable nodes, dead ends), writes the
  JSON and optional DOT/image using the bundled dialogue_graph library; failures go to a
  repair task; a delivery task checks every output against the task's spec.

trigger_when:
  - A task asks to parse, convert, or load a dialogue/conversation script (e.g. script.txt) into JSON, a graph, or a tree.
  - 'The text has [NodeId] headers, "Speaker: line -> Target" transitions, and numbered "1. option -> Target" choices.'
  - A task asks to validate, visualize (Graphviz PNG/SVG/DOT), or serialize a branching dialogue or narrative graph.
  - Building a dialogue editor, game dialogue traversal, or script parser that needs the Graph/Node/Edge model.

do_not_use_when:
  - The dialogue is in an established engine format with its own tooling (Ink, Yarn Spinner, Twine/Twee, Ren'Py) and the task wants that format kept.
  - The task is writing new narrative content rather than structuring an existing script.

steps:
  - name: conventions
    kind: decision
    description: Read the task's wording to fix End handling and choice-edge text before parsing.
    inputs:
      - name: task_instructions
        type: string
        description: The task's own instructions/spec for the output, verbatim ("" if none were given).
    questions:
      end_node:
        type: choice
        instructions: >
          How must the terminal target "End" appear in the output graph? Judge only from what
          the task says or shows (an example JSON, a test description, "every edge target must
          be a node"). With no such signal, answer virtual — that is the library's convention
          (Graph.validate accepts "End" as a target without a node).
        criteria:
          virtual: Edges point to "End" but no End node is listed — the default.
          explicit: The task requires End to be present in nodes, or requires every edge target to exist as a node.
      choice_text:
        type: choice
        instructions: >
          What text should an edge leaving a choice hub carry? Default verbatim, numbering and
          [Skill] tags included (the library's own example is text="1. Run away"). Answer
          strip_number only if the task explicitly shows or demands option text without the
          leading "1." numbering.
        criteria:
          verbatim: The full option line before "->", e.g. "4. [Observe] Study the room from the shadows."
          strip_number: Option text without the leading number, e.g. "[Observe] Study the room from the shadows."
    thresholds:
      end_node: 0.7
      choice_text: 0.7
    inputs_to: build

  - name: build
    kind: execution
    description: Parse the script, validate the graph, write graph JSON plus optional DOT source and rendered image.
    inputs:
      - name: script_path
        type: string
        description: Absolute path to the dialogue script (e.g. /app/script.txt). Read as UTF-8; BOM and CRLF tolerated.
      - name: output_json
        type: string
        description: Where to write the graph JSON (the task's required path, e.g. /app/dialogue.json); "" writes dialogue.json beside the script.
      - name: dot_path
        type: string
        description: Where to write Graphviz DOT source, or "" for none.
      - name: image_path
        type: string
        description: Rendered diagram path; the extension (.png/.svg/.pdf) picks the format; "" for none. Needs the Graphviz dot binary.
      - name: end_node
        type: string
        description: virtual | explicit, from the conventions decision.
      - name: choice_text
        type: string
        description: verbatim | strip_number, from the conventions decision.
    script: scripts/dialogue_tool.py
    timeout: 180
    inputs_to: by-status

  - name: by-status
    kind: router
    description: Clean parse goes to delivery; any parse or integrity error goes to repair first.
    branch_on: status
    branches:
      ok: deliver
      broken: repair

  - name: repair
    kind: client_task
    description: Diagnose parse/integrity errors against the raw script and fix parser mismatches without inventing content.
    inputs:
      - name: script_path
        type: string
      - name: graph_path
        type: string
      - name: errors
        type: list[*]
      - name: warnings
        type: list[*]
    template: assets/repair.md
    references:
      - path: references/format-and-api.md
        description: Script syntax, the parse rules for irregular blocks, the exact output JSON shape, and the Graph/Node/Edge API for patching a graph by hand. Load before changing anything.
    inputs_to: deliver

  - name: deliver
    kind: client_task
    description: Check every required output against the task's spec, adapt shape or paths if the task demands, and deliver parser code if asked.
    inputs:
      - name: task_instructions
        type: string
      - name: script_path
        type: string
      - name: graph_path
        type: string
      - name: files_written
        type: list[*]
      - name: status
        type: string
      - name: start_node
        type: string
      - name: node_count
        type: integer
      - name: line_node_count
        type: integer
      - name: choice_node_count
        type: integer
      - name: edge_count
        type: integer
      - name: end_edge_count
        type: integer
      - name: reaches_end
        type: boolean
      - name: speakers
        type: list[*]
      - name: unreachable_nodes
        type: list[*]
      - name: options_used
        type: object
    template: assets/deliver.md
    references:
      - path: references/format-and-api.md
        description: Output JSON shape, End/choice-text conventions, visualization legend and Graphviz caveats (visualize() deletes the .dot), and how to ship dialogue_tool.py as a parser program. Load when the task asks for code, a different JSON shape, or a visualization.
    inputs_to: end

  - name: end
    kind: end
    description: The graph JSON (and any DOT/image/parser) at the task's paths, with a summary of counts, conventions, and reported defects.
    inputs:
      - name: graph_path
        type: string
      - name: status
        type: string
        description: ok, or broken when genuine script defects remain (listed in summary).
      - name: deliverables
        type: list[*]
      - name: summary
        type: string

anti_patterns:
  - Hand-transcribing nodes or hardcoding counts instead of running the parser on the actual file; the graph must come from whatever script is given.
  - Splitting a line on the first "->" or the first ":" of the text — split the target on the last "->" and the speaker on the first ":" only.
  - Dropping the [Skill] tag or the "1." numbering from choice edge text unless the task asks for it.
  - Adding an End node, or synthesizing nodes for dangling targets, when the task has not asked for it.
  - Using Graph.visualize() when a .dot file is required — it renders with cleanup=True and deletes the DOT source.
  - Reading the script with the platform default encoding; it contains UTF-8 punctuation such as em dashes.
```
