---
name: dialogue-script-parser
description: 'Parse a branching dialogue script ("[NodeId]" blocks, "Speaker: text -> Target" lines, numbered "1. option -> Target" choices) into a validated JSON graph of line/choice nodes and from/to/text edges plus a Graphviz .dot visualization, and expose it as parse_script(text) in solution.py. Use for dialogue/script parsers, branching-narrative or game-dialogue trees, and dialogue graph validation or visualization.'
compatibility: Python >= 3.8, standard library only. Optional for --render (PNG/SVG) only — pip package graphviz and the Graphviz `dot` binary.
---

# Dialogue Script Parser

## Trigger When

1. A task asks for a parser that turns a dialogue/script text file into a JSON graph (`nodes` + `edges`) and/or a `.dot` visualization.
2. A task asks for `def parse_script(text: str)` in a `solution.py` (graders import it).
3. Input looks like `[NodeId]` headers followed by `Speaker: text -> Target` lines or numbered `1. text -> Target` options.
4. Building, validating, visualizing, or traversing branching dialogue / narrative trees (script parsers, dialogue editors, game logic).

## Purpose

Ships a tested, dependency-free `solution.py` that parses the dialogue script format, builds the graph with the `dialogue_graph` Node/Edge/Graph model, validates the task's constraints (every node reachable from the first node; every edge target defined except `End`; several paths may end in `End`), and writes the JSON and DOT files. It carries the format conventions an agent would otherwise guess at: what becomes a `choice` vs `line` node, what goes in edge `text`, and why `End` is not a node.

## Output contract

```json
{"nodes": [{"id": "Start", "text": "The tavern door creaks open.", "speaker": "Narrator", "type": "line"},
           {"id": "TavernChoice", "text": "", "speaker": "", "type": "choice"}],
 "edges": [{"from": "Start", "to": "TavernEntry", "text": ""},
           {"from": "TavernChoice", "to": "ObserveRoom", "text": "4. [Observe] Study the room from the shadows."}]}
```

Parsing rules (implemented in the script; listed so you can check its output):
- `[Id]` starts a block. Nodes keep file order, so the first block is the start node.
- `Speaker: text -> Target` → `line` node `{id, speaker, text}` + edge `{from: id, to: Target, text: ""}`. Text keeps inline tags like `[Narrows eyes]`. No `Speaker:` → speaker `""`.
- A block of numbered options (`1.` or `1)`) → one `choice` node with `text: ""`, `speaker: ""`, and one edge per option whose `text` is the whole option as written, number and `[Skill]` tag included (`"3. [Lie] I'm a merchant with important goods."`).
- `End` is a terminal target, **not** a node: edges may point to it without a `[End]` block. The DOT file still draws an `END` doublecircle.
- Less common shapes, handled so another script instance still parses: several speaker lines in one block become `Id`, `Id_2`, `Id_3`… chained with empty-text edges. A speaker line followed by options hangs the option edges off that line node. Blank lines and `#` / `//` comments are skipped. An empty block becomes an edgeless `line` node.

## Procedure

Progress:
- [ ] 1. Check the environment
- [ ] 2. Install and run the parser (script)
- [ ] 3. Triage any warnings/errors (decision), fix if needed (client task)
- [ ] 4. Confirm the deliverables

### 1. Check the environment (execution)

Run `python3 --version` and confirm it is 3.8 or newer. The parser needs nothing else. `--render` needs the `graphviz` pip package and the `dot` binary, and it is optional: if either is missing, say which one and skip `--render`. The task's own deliverable is the `.dot` text, which the script writes without them.

### 2. Install and run the parser (execution)

Copy the script to where the task wants `solution.py`, then run it on the task's script file. Paths below are the usual task layout; use the ones your task names.

```bash
cp scripts/solution.py /app/solution.py
cd /app && python3 solution.py /app/script.txt --json /app/dialogue.json --dot /app/dialogue.dot
```

Inputs: script path (string; default `/app/script.txt`). Flags: `--json PATH`, `--dot PATH` (string; default `dialogue.json` / `dialogue.dot` next to the script). `--render png|svg|pdf` also writes an image. `--add-end-node` adds an explicit `End` node to the JSON; use it only if the task says `End` must be a node.

Output (stdout): node counts (line/choice), edge counts, the first node, edges into `End`, speakers, the files written, then `VALID` or `INVALID (n errors)`. Problems go to stderr as `WARNING:` (input skipped or reshaped) or `INVALID:` (constraint broken). Exit 0 means valid and written. Exit 1 means files were written but validation failed. Exit 2 means bad input (missing file, no `[Id]` blocks, duplicate id) and nothing was written.

Check the counts against the raw file, because a run can print `VALID` and still have misread lines:

```bash
grep -c '^\[' /app/script.txt            # = nodes
grep -c -- '->' /app/script.txt          # = edges
grep -cE '^[0-9]+[.)]' /app/script.txt   # = edges with text
```

Treat any mismatch as a problem line for step 3. Two exceptions don't count: blocks with several speaker lines add `Id_2`… nodes, and comment lines may contain `->`.

### 3. Triage (decision, then client task if needed)

Skip this step when the exit code is 0, stderr shows no `WARNING:` lines, and the counts match. Otherwise, answer one question for each warning/error line or count mismatch:

```yaml
cause:
  type: choice
  instructions: >-
    Given one WARNING/INVALID line and the script lines it cites, what caused it?
    A false `input_defect` is the costly mistake, because it ships a wrong graph.
    If the line could be read either way, re-read the cited script lines before
    answering, and lean towards parser_gap.
  criteria:
    parser_gap: The script uses a syntax the rules above do not cover (e.g. `- option -> X` bullets, `Speaker -> X` with no colon, multi-line text, a different arrow), so content was skipped or misread.
    input_defect: An INVALID line, an exit-2 error, or a "choice without target" WARNING, where the script itself is inconsistent (a target with no [block] other than End, a block nothing links to, a choice with no target, a duplicate id) and the parser reported it faithfully.
    benign: A WARNING (never an INVALID line) about an empty block, or about a comment or stray text before the first header, that the task does not need.
```

- `parser_gap` → **client task**: edit `/app/solution.py` (the `HEADER` / `CHOICE` / `SPEAKER` regexes or `_parse`) to handle the new syntax. Keep the output contract, keep `parse_script(text) -> dict`, and re-run step 2 until the run has no `parser_gap` lines.
- `input_defect` → keep the graph faithful to the script. Do not invent nodes or delete edges to force `VALID`. Report the specific defect in your final answer. If the task explicitly requires `End` to exist as a node, re-run with `--add-end-node`.
- `benign` → no action.

### 4. Confirm the deliverables (execution)

```bash
cd /app && python3 -c "import json, solution; g = solution.parse_script(open('script.txt').read()); assert g == json.load(open('dialogue.json')); print(len(g['nodes']), len(g['edges']))"
head -3 /app/dialogue.dot
```

The first command checks that `parse_script` is importable from `solution.py`, returns a dict, and matches the JSON file. The second checks that the `.dot` file starts with `digraph`. To check that the DOT parses, run `dot -Tsvg /app/dialogue.dot -o /dev/null` if the binary exists.

## Gotchas

- Graders call `parse_script(text)` with the file's **contents**, not a path. It must return a plain dict with `nodes` and `edges`. Importing `solution` must not run the CLI (it is behind `if __name__ == "__main__"`).
- Edge keys are `from`/`to`, not `source`/`target`. The Python `Edge` class uses `source`/`target` internally, and `to_dict()` maps them.
- Do not strip the `1.` number or the `[Skill]` tag from option text. The source library's convention is `text="1. Run away"`, and the DOT styling detects skill checks by the `[...]` in the edge text.
- `Graphviz: Orthogonal edges do not currently handle edge labels` on stderr when rendering is harmless (`splines=ortho` is the source library's style).
- Choice nodes have empty `text` and `speaker`. Do not copy the option text into the node.

## Library API

Read [references/dialogue_graph_api.md](references/dialogue_graph_api.md) when you need to build, load, edit, or traverse a graph in code instead of parsing a script. Examples: `Graph.from_file('dialogue.json')`, adding nodes/edges by hand, `validate()`, `to_dot()`, `visualize()`. The classes live in `scripts/solution.py` (`from solution import Graph, Node, Edge`).
