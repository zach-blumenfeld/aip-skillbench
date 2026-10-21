# dialogue_graph API (as embedded in `scripts/solution.py`)

```python
from solution import Graph, Node, Edge   # same classes as the original dialogue_graph module
```

## Build

```python
graph = Graph()                                                        # main container
graph.add_node(Node(id="Start", speaker="Guard", text="Halt!", type="line"))   # regular line
graph.add_node(Node(id="Choices", type="choice"))                      # choice hub (text/speaker "")
graph.add_edge(Edge(source="Start", target="Choices"))                 # simple transition, text ""
graph.add_edge(Edge(source="Choices", target="End", text="1. Run away"))  # choice transition
```

`add_node` raises `ValueError("Node X already exists")` on a duplicate id. `Node` defaults: `text=""`, `speaker=""`, `type="line"`.

## Export

```python
data = graph.to_dict()      # {"nodes": [{id,text,speaker,type}...], "edges": [{from,to,text}...]}
json_str = graph.to_json()  # indent=2, UTF-8 kept (ensure_ascii=False)
dot_src = graph.to_dot()    # Graphviz DOT text, no dependencies
```

## Validate

```python
errors = graph.validate()
# [] when valid, else strings such as
#   "Edge 'Start'->'Unk' points to missing node 'Unk'"
#   "Edge source 'X' not found"
#   "Node 'Orphan' is not reachable from first node 'Start'"
```

A target of `End` is always allowed. Reachability is checked from the first node added.

## Visualize

```python
graph.visualize('dialogue_graph')          # dialogue_graph.png
graph.visualize('output', format='svg')    # output.svg ('png', 'svg', 'pdf')
```

This needs `pip install graphviz` and the Graphviz system binary (https://graphviz.org/download/). It raises `ImportError` with an install hint if the package is missing. The styling matches the original library:
- choice nodes: lightblue diamonds labelled with the id
- line nodes: rounded boxes labelled `id\nSpeaker: text`, with the text cut to 37 chars + `...` when it is over 40. Fill colour by speaker: Narrator lightyellow, Guard lightcoral, Stranger plum, Merchant lightgreen, Barkeep peachpuff, Kira lightcyan, any other speaker white.
- an `End` node: gray doublecircle labelled `END`
- edge labels are cut to 27 chars + `...` when over 30. Skill-check options (`[Lie]`, `[Attack]`) are bold dark blue, other options gray40, and plain transitions black.
- graph attributes: `rankdir=TB, splines=ortho, nodesep=0.5, ranksep=0.8`, Arial 10pt for nodes and 8pt for edges

## Load

```python
graph = Graph.from_file('dialogue.json')
graph = Graph.from_dict({'nodes': [...], 'edges': [...]})
graph = Graph.from_json(json_string)
```

Missing node fields default to `text=""`, `speaker=""`, `type="line"`. A missing edge `text` defaults to `""`.

## Traverse (game logic)

```python
out = {}
for e in graph.edges:
    out.setdefault(e.source, []).append(e)
node = graph.nodes["Start"]
options = out.get(node.id, [])   # choice node: show each e.text; line node: one edge, follow e.target
```
