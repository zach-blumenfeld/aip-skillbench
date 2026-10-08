# Dialogue script format, graph JSON, and the `dialogue_graph` library

Load this when a script line will not parse, when the task asks for a parser
program/module (not just the JSON), or when you must patch a graph by hand.

## Script format (input)

```
[NodeId]
Speaker: Line of dialogue. -> NextNodeId

[ChoiceHub]
1. Plain option text. -> TargetA
2. [Persuade] Skill-check option text. -> TargetB
```

- A block starts at a line that is exactly `[NodeId]`; blank lines separate blocks.
  The **first block is the start node** (`Start` in the reference script).
- `Speaker: text -> Target` — a dialogue line. Split on the **last** `->` (text may
  contain `:`, `?!`, em dashes, etc.); speaker is everything before the first `:`.
- `N. text -> Target` (or `N) text`) — a numbered choice option.
  Bracketed tags like `[Observe]`, `[Sleight of Hand]`, `[Intimidate]` are skill checks;
  they stay in the option text.
- `End` is a terminal target; no `[End]` block exists.
- File is UTF-8 (contains non-ASCII such as `—`); read with `encoding="utf-8"`
  (`utf-8-sig` tolerates a BOM). Strip `\r` for CRLF files.

`scripts/dialogue_tool.py` parse rules for irregular blocks:
- Pure option block → one `choice` node (empty speaker/text), one edge per option.
- One dialogue line → one `line` node, one edge with empty text.
- Several dialogue lines → nodes `Id`, `Id_2`, `Id_3`… chained with empty-text edges.
- Dialogue line(s) followed by options → the last line's node becomes the `choice`
  node (keeps its speaker/text) and owns the option edges.
- Line without `Speaker:` → speakerless `line` node (warning). Content before the
  first header, an option without `->`, an empty block, or a duplicate id → error.

## Graph JSON (output) — `Graph.to_dict()` / `to_json()` (indent=2)

```json
{
  "nodes": [
    {"id": "Start", "text": "The tavern door creaks open. ...", "speaker": "Narrator", "type": "line"},
    {"id": "TavernChoice", "text": "", "speaker": "", "type": "choice"}
  ],
  "edges": [
    {"from": "Start", "to": "TavernEntry", "text": ""},
    {"from": "TavernChoice", "to": "StrangerApproach", "text": "1. Approach the hooded stranger."},
    {"from": "TavernChoice", "to": "ObserveRoom", "text": "4. [Observe] Study the room from the shadows."}
  ]
}
```

- Node keys: `id`, `text`, `speaker`, `type` (`line` | `choice`). Edge keys: `from`, `to`, `text`.
- Simple transitions carry `"text": ""`; choice edges carry the option text
  (verbatim, numbering included, by default — as in the library's own example
  `Edge(source="Choices", target="End", text="1. Run away")`).
- Order: nodes and edges in script order.
- `End` handling: by default `End` is a virtual target (not in `nodes`), which is
  what `Graph.validate()` accepts. With `end_node: explicit` an
  `{"id": "End", "text": "", "speaker": "", "type": "line"}` node is appended.

## Library API (`scripts/dialogue_graph.py`, copied verbatim from the source skill)

```python
from dialogue_graph import Graph, Node, Edge

graph = Graph()
graph.add_node(Node(id="Start", speaker="Guard", text="Halt!", type="line"))  # regular line
graph.add_node(Node(id="Choices", type="choice"))                              # choice hub
graph.add_edge(Edge(source="Start", target="Choices"))                         # simple transition
graph.add_edge(Edge(source="Choices", target="End", text="1. Run away"))       # choice transition

data = graph.to_dict()        # {"nodes": [...], "edges": [...]}
json_str = graph.to_json()
errors = graph.validate()     # e.g. ["Edge target 'Unk' not found"]; 'End' target is allowed

graph = Graph.from_file('dialogue.json')   # also Graph.from_dict(d), Graph.from_json(s)
graph.visualize('dialogue_graph')          # dialogue_graph.png
graph.visualize('output', format='svg')    # output.svg  (png | svg | pdf)
```

- `add_node` raises `ValueError` on a duplicate id.
- `visualize` needs the `graphviz` Python package **and** the Graphviz `dot` binary
  (both are in the task container: `graphviz==0.20.3` + apt `graphviz`). It renders with
  `cleanup=True`, i.e. it **deletes the .dot source** — if the task wants a `.dot`
  file, use `dialogue_tool.py --dot` (or `Digraph.save`) instead.
- Visual legend (reproduced by `dialogue_tool.to_dot`): choice nodes = light-blue
  diamonds labelled with their id; dialogue nodes = rounded boxes `id\nSpeaker: text`
  (text cut to 37 chars + `...` when over 40), filled by speaker (Narrator lightyellow,
  Guard lightcoral, Stranger plum, Merchant lightgreen, Barkeep peachpuff, Kira
  lightcyan, others white); `End` = gray double circle `END`; edges with `[...]` text =
  bold dark-blue (skill checks); other labelled edges = gray40 (regular choices);
  unlabelled = black (simple transitions); edge labels cut to 27 chars + `...` over 30.
  Graph attrs: `rankdir=TB splines=ortho nodesep=0.5 ranksep=0.8`, Arial 10/8.

## Using the parser as a deliverable

`dialogue_tool.py` is stdlib-only and importable:

```bash
python dialogue_tool.py /app/script.txt -o /app/dialogue.json --dot /app/dialogue.dot --image /app/dialogue.png
```
```python
from dialogue_tool import parse_file, parse_script, check_graph, to_dot
data = parse_file(path)                     # path -> {"nodes": [...], "edges": [...]}
graph, issues = parse_script(open(path, encoding="utf-8").read())   # text -> (Graph, issues)
check_graph(graph, issues, start_id=next(iter(graph.nodes)))        # fills issues["errors"/"warnings"]
dot_src = to_dot(graph)
```

When the task names its own signature (e.g. `parse_script(path) -> dict` in `parser.py`), write a thin
wrapper module that imports `dialogue_tool` and returns `parse_file(path)`; don't rename the
tool's own functions. A shipped parser should return the graph faithful to the script and report
defects (warnings or a returned list), not raise — unless the task says invalid input must fail.

Serialization: `Graph.to_json()` uses `json.dumps(indent=2)` with the default `ensure_ascii=True`,
so `—` is written as `\u2014`. That is the same JSON value as a literal `—`; if a wrapper writes
the file itself, use `graph.to_json()` (or `json.dumps(data, indent=2)`) to stay byte-identical.

Copy both `dialogue_tool.py` and `dialogue_graph.py` together (the tool imports the
library from its own folder).
