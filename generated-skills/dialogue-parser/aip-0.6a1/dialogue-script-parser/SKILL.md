---
name: dialogue-script-parser
description: >-
  Parse a branching dialogue script ([NodeId] headers, "Speaker: text -> Target" lines, "1. option -> Target" choices, End terminal) into a validated JSON graph of line/choice nodes and from/to/text edges plus a Graphviz .dot visualization, delivered as solution.py with parse_script(text). Use for dialogue/narrative script parsers, game dialogue trees, script.txt -> dialogue.json / dialogue.dot tasks.
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Turn a branching dialogue script (e.g. /app/script.txt) into the three deliverables a dialogue-parser
  task checks: /app/solution.py defining parse_script(text) -> {"nodes", "edges"}, /app/dialogue.json
  holding that graph, and /app/dialogue.dot visualizing it. A bundled, tested parser (built on the
  dialogue_graph Graph/Node/Edge library) is installed and run by script, which also validates the
  task constraints: every node reachable from the first node, every edge target defined except the
  virtual End, End reachable from several paths. Only when validation fails does the agent adapt the
  parser to the script's variant of the format.

trigger_when:
  - A task asks to parse a dialogue or narrative script text file into a JSON graph of nodes and edges.
  - A task names script.txt, dialogue.json, dialogue.dot, solution.py, or a parse_script(text) function.
  - Building, validating, visualizing, or serializing branching dialogue trees (script parsers, dialogue editors, game logic).

do_not_use_when:
  - The dialogue is already structured data (JSON/YAML/Ink/Yarn) that only needs loading, not parsing from this bracketed text format.
  - The task wants a runtime dialogue engine or UI rather than a parsed graph.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - graphviz

steps:
  - name: build-graph
    kind: execution
    description: >
      Install scripts/solution.py at solution_path, parse script_path, write json_path and dot_path,
      and validate (missing targets, unreachable nodes, unparsed lines, JSON == parse_script output,
      and `dot -Tsvg` acceptance when the Graphviz binary is on PATH).
    inputs:
      - name: script_path
        type: string
        description: The dialogue script to parse; in the task container /app/script.txt.
      - name: solution_path
        type: string
        description: Where the parser module must live; /app/solution.py (tests import parse_script from it).
      - name: json_path
        type: string
        description: Output graph JSON; /app/dialogue.json.
      - name: dot_path
        type: string
        description: Output Graphviz visualization; /app/dialogue.dot.
    script: scripts/build_graph.py
    outputs:
      - name: graph_status
        type: string
        description: "valid when no validation error was found, invalid otherwise."
      - name: first_node
        type: string
        description: Id of the first [Header], the start node all others must be reachable from.
      - name: node_count
        type: integer
        description: Nodes written (one per [Header]; End is virtual and not counted).
      - name: edge_count
        type: integer
        description: Edges written (one per "-> Target").
      - name: choice_node_count
        type: integer
        description: Nodes of type choice.
      - name: end_edge_count
        type: integer
        description: Edges whose target is End.
      - name: graph_errors
        type: list[*]
        description: Validation errors (parse issues, missing targets, unreachable nodes, dot rejection).
      - name: graph_warnings
        type: list[*]
        description: Non-fatal oddities (dead-end nodes, no edge to End).
      - name: sample_nodes
        type: list[*]
        description: The first two nodes and the first choice node, to eyeball the node format.
      - name: sample_edges
        type: list[*]
        description: Edges leaving the sample nodes, to eyeball the edge format.
    inputs_to: by-status

  - name: by-status
    kind: router
    description: A valid graph is done; an invalid one sends the agent to adapt the parser.
    branch_on: graph_status
    branches:
      valid: end
      invalid: repair-parser

  - name: repair-parser
    kind: client_task
    description: Classify each validation error as parser gap or script defect, fix parser gaps in solution.py, and re-run it until valid.
    inputs:
      - name: script_path
        type: string
      - name: solution_path
        type: string
      - name: json_path
        type: string
      - name: dot_path
        type: string
      - name: first_node
        type: string
      - name: node_count
        type: integer
      - name: edge_count
        type: integer
      - name: end_edge_count
        type: integer
      - name: graph_errors
        type: list[*]
      - name: graph_warnings
        type: list[*]
    template: assets/repair.md
    references:
      - path: references/script-format.md
        description: >
          Script grammar, the format variants the parser already tolerates, and the exact JSON/DOT output
          contract and styling. Load before editing solution.py or when an error cites a line you cannot classify.
    outputs:
      - name: final_status
        type: string
        description: "valid, or script_defect when only defects in the script itself remain."
      - name: repair_summary
        type: string
        description: What was changed in the parser and why, or which script defects remain.
    inputs_to: end

  - name: end
    kind: end
    description: The parser module and both output files are in place; graph_status says whether the first build validated.
    inputs:
      - name: solution_path
        type: string
      - name: json_path
        type: string
      - name: dot_path
        type: string
      - name: graph_status
        type: string
      - name: node_count
        type: integer
      - name: edge_count
        type: integer

anti_patterns:
  - Hardcoding node ids, counts, or the expected graph into solution.py; parse_script must compute the graph from whatever text it is given.
  - Adding End to nodes or treating `-> End` as a missing target; End is a virtual terminal that several nodes may lead to.
  - Dropping keys or writing null; every node carries id, text, speaker, type and every edge from, to, text (empty string when there is none).
  - Stripping the number or the [Skill] tag from choice edge text; keep the option text as written ("4. [Attack] Draw your sword!").
  - Splitting on the first "->" or the first ":" inside the text; split the target on the last "->" and the speaker on the first ":" of non-numbered lines only.
  - Leaving parse_script only in a helper module; tests import it from /app/solution.py, so that file must be self-contained.
  - Writing a .png instead of the .dot source, or hand-editing dialogue.json so it no longer equals parse_script(script text).
  - Inventing nodes or editing script.txt to silence a missing-target error that is a genuine defect in the script.
```
