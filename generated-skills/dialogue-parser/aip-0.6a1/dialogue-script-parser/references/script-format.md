# Dialogue script format and graph contract

Load when a parse error cites a line you cannot classify, or before editing `solution.py`.

## Input grammar (as observed in the task script)

```
[NodeId]                                   section header; one header = one node, id = text in brackets
Speaker: Spoken text. -> TargetId          dialogue line  -> node type "line", one edge (text "")
1. Option text. -> TargetId                numbered option -> node type "choice", one edge per option
2. [Skill] Skill-check option. -> Other    [Skill] tags (Lie, Attack, Observe, Persuade...) stay in the edge text
```

- Blank lines separate sections. The first header is the start node; every node must be reachable from it.
- `-> End` ends the conversation. `End` is never declared with a header; several nodes may lead to it.
- Options can loop back to earlier nodes (e.g. `Pretend you saw nothing. -> TavernChoice`): cycles are fine.
- Split the target on the LAST `->` so text containing arrows survives; strip the target.
- Speaker is everything before the first `:` on a non-numbered line; dialogue text may itself contain `:`.
- Choice lines are detected before speaker lines so `1. Ask: why?` stays a choice.

## Variants the parser also tolerates (other instances of the task)

| Variant | Handling |
|---|---|
| CRLF line endings, BOM, trailing spaces | normalised |
| `# comment`, `// comment` lines | skipped |
| `1)` numbering, `-` / `*` bullet options | same as `1.`; the edge text keeps the marker |
| line with no speaker (`The door opens. -> X`) | line node, speaker `""` |
| several dialogue lines in one section | first keeps the id, later ones become `Id_2`, `Id_3`, chained |
| dialogue line plus options in one section | one `choice` node carrying the line's speaker/text |
| line with no `->` | node with no outgoing edge (reported as a warning) |
| `-> [Target]` | brackets stripped |
| duplicate header | lines merged into the first node, reported as an error |

## Output contract

- `/app/dialogue.json`: `{"nodes":[{"id","text","speaker","type"}], "edges":[{"from","to","text"}]}`,
  every key always present (empty string, never null/missing). Nodes in script order.
- `parse_script(text)` in `/app/solution.py` returns that same dict; tests import it.
- `/app/dialogue.dot`: Graphviz digraph. Styling from the dialogue_graph library: choice nodes
  diamond/lightblue, line nodes rounded box coloured by speaker (Narrator lightyellow, Guard
  lightcoral, Stranger plum, Merchant lightgreen, Barkeep peachpuff, Kira lightcyan, others white or
  a rotating palette), End doublecircle lightgray; skill-check edges (text with `[...]`) bold
  darkblue, other choice edges gray40, plain transitions black. Labels truncated to 40 (node text)
  and 30 (edge text) characters with `...`.
- Validation: every edge target exists in nodes or is `End`; every node reachable from `nodes[0]`.
