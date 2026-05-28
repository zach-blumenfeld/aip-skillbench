# Source for dialogue-script-parser

## Origin

Authored from `vendor/skillsbench/tasks/dialogue-parser/instruction.md`
alone (no existing skill was consulted). The instruction specifies:

- Input at `/app/script.txt`, outputs `/app/dialogue.json` +
  `/app/dialogue.dot`.
- A `parse_script(text: str)` function in `solution.py`.
- Node shape `{id, text, speaker, type}` with `type ∈ {"line","choice"}`.
- Edge shape `{from, to, text}`.
- Constraints: (1) all nodes reachable from the first, (2) all edge
  targets exist, (3) multiple paths may lead to `End`.

## Schema choice

`procedure.schema.json` (bundled here). The skill is a step-by-step
parsing pipeline — schema's `steps`, `decisions`, `scenarios`, and
`anti_patterns` map cleanly onto the work. No new schema needed.

## Design notes

- **Reference implementation lives in `scripts/parse_dialogue.py`.** The
  solver can either copy it to `/app/solution.py` or re-author against
  the spec — both paths satisfy the harness, which imports
  `parse_script` by name.
- **Validator is separate** (`scripts/validate_graph.py`) so the solver
  has a single command for constraints (1) and (2) without re-loading
  the parser.
- **Format spec is in `references/format.md`** — load on demand when the
  agent needs grammar detail beyond what the body covers.

## Completeness check against the instruction

| Instruction item | Captured in |
|---|---|
| Parse `/app/script.txt` → `/app/dialogue.json` + `/app/dialogue.dot` | `steps.read-input`, `steps.write-json`, `steps.write-dot` |
| `parse_script(text)` in `solution.py` | `steps.write-solution`, `scripts/parse_dialogue.py` |
| Node keys `id/text/speaker/type` (line\|choice) | `steps.parse-lines`, `steps.parse-choices`, `references/format.md` |
| Edge keys `from/to/text` | same |
| Example block parses (Guard/NameChoice) | `scenarios` |
| Bracketed tags `[Lie]`, `[Attack]` preserved | `anti_patterns`, `references/format.md` |
| Constraint 1 — all reachable from first | `steps.validate-graph`, `scripts/validate_graph.py` |
| Constraint 2 — all targets exist | `steps.synthesize-implicit-nodes`, `scripts/validate_graph.py` |
| Constraint 3 — multiple paths to `End` | `decisions` (terminal handling), `references/format.md` |

No deliberate drops.
