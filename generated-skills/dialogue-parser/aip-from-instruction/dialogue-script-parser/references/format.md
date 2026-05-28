# Dialogue script DSL — format reference

## Block structure

The source is divided into **scene blocks** separated by one or more blank
lines. Each block begins with a header line of the form `[SceneId]` where
`SceneId` is the node id used elsewhere (`-> SceneId`).

The first block in the file is the **start node**. Do not hardcode an id —
read whichever scene appears first.

## Line scene

A line scene has exactly one body line:

```
[GateScene]
Guard: Halt! State your name and business. -> NameChoice
```

Grammar for the body line:

```
<speaker> ":" <text> ( "->" <target_id> )?
```

- `speaker` — everything before the first `:`.
- `text` — everything between `:` and the optional ` -> `. Keep trailing
  punctuation (period, exclamation, question mark) verbatim.
- `target_id` — single whitespace-free token. Omitted on terminal scenes.

Emit one node and (when a target exists) one edge:

```json
{"id":"GateScene","text":"Halt! State your name and business.","speaker":"Guard","type":"line"}
{"from":"GateScene","to":"NameChoice","text":""}
```

The edge `text` is empty for line scenes — the speech belongs in the node.

## Choice scene

A choice scene has multiple body lines, each starting with `N.`:

```
[NameChoice]
1. I am Sir Aldric, Knight of the Realm. -> KnightPath
2. Just a humble traveler seeking shelter. -> TravelerPath
3. [Lie] I'm a merchant with important goods. -> MerchantPath
4. [Attack] Draw your sword! -> CombatStart
```

Grammar per option:

```
<digit>+ "." <text> ( "->" <target_id> )?
```

Emit one node with empty `text`/`speaker` and one edge per option:

```json
{"id":"NameChoice","text":"","speaker":"","type":"choice"}
{"from":"NameChoice","to":"KnightPath","text":"I am Sir Aldric, Knight of the Realm."}
{"from":"NameChoice","to":"MerchantPath","text":"[Lie] I'm a merchant with important goods."}
```

**Keep bracketed tags** (`[Lie]`, `[Attack]`, `[Persuade]`, …) inside the
edge `text`. They are part of the displayed choice and tests check for them.

## Implicit "End" node

The script may reference `-> End` without ever declaring `[End]`. After
parsing all blocks, walk every edge `to` value — for any id not in the
defined set, synthesize a terminal node:

```json
{"id":"End","text":"","speaker":"","type":"line"}
```

This satisfies constraint (2) "all edge targets must exist" without
requiring the author to spell out an empty scene.

## Output shape

`/app/dialogue.json`:

```json
{
  "nodes": [
    {"id":"...", "text":"...", "speaker":"...", "type":"line"|"choice"}
  ],
  "edges": [
    {"from":"...", "to":"...", "text":"..."}
  ]
}
```

`/app/dialogue.dot`:

```
digraph dialogue {
  rankdir=LR;
  "GateScene" [label="GateScene\nGuard: Halt! ...", shape=box];
  "NameChoice" [label="NameChoice", shape=diamond];
  "GateScene" -> "NameChoice";
  "NameChoice" -> "KnightPath" [label="I am Sir Aldric, ..."];
}
```

Use `box` for line nodes, `diamond` for choice nodes. Quote ids and labels;
escape embedded double quotes with `\"`.

## Validation

- Every edge `to` must appear as some node `id`.
- Every node must be reachable from the first node via forward edges.
- A node with no outgoing edge is a valid terminal (e.g., `End`).
- Multiple edges may point to the same target (especially `End`).

Run `scripts/validate_graph.py /app/dialogue.json` after writing the file
and fix any violations before claiming completion.
