# Source: power-flow-data → AIP

## Origin

Translated from the curated `power-flow-data` skill bundled with the
SkillsBench `grid-dispatch-operator` task at
`vendor/skillsbench/tasks/grid-dispatch-operator/environment/skills/power-flow-data/SKILL.md`.

## Schema choice

Validates against [`procedure.schema.json`](procedure.schema.json) — the
universal procedure schema. The source is a small data-loading + topology
procedure (load JSON → build bus-number index → query slack / generators /
branches → aggregate load). A graph of script-backed nodes with typed
inputs/outputs is the natural shape.

## What moved into scripts/

The source SKILL.md inlines five helper functions (`load_network`,
`bus_num_to_idx` construction, `find_slack_bus`, `get_generators_at_bus`,
`get_branch_info`, `total_load`) plus the per-unit conversion formulas.
All of this is deterministic, structured-input logic — the AIP best
practices guide says to put deterministic mechanics in `scripts/`. They
are consolidated into one library module `scripts/network_utils.py` that
also runs as a CLI for the file-summary node.

One file (rather than one-per-step) was chosen because the helpers share
the bus-number-to-index map and are too small to warrant separate
files. The procedure body references the same script path from every
step that uses a function in the library.

## What stayed prose

Nothing in the source SKILL.md is judgment-laden — it is pure reference
+ pure mechanical helpers. The body keeps short prose descriptions of
each step pointing at the relevant helper plus the per-unit /
column-convention reference text that the agent needs to *interpret*
results (bus type codes, column meanings).

## Mapping vs. source

| Source content                       | Disposition                       |
|-------------------------------------|-----------------------------------|
| MATPOWER + PGLib-OPF provenance     | `purpose`                         |
| File-size handling warning          | step `summarize-network` + anti-pattern |
| Bus-type table (3=slack, 2=PV, 1=PQ)| step `query-topology` description |
| Per-unit conversions                | `network_utils.to_per_unit / from_per_unit`; description in `load-network` step |
| `load_network` helper               | `network_utils.load_network`      |
| Reserve data fields                 | `network_utils.load_network` description |
| Bus number mapping                  | `network_utils.build_bus_num_to_idx`; step `build-bus-index` |
| `find_slack_bus`, `get_generators_at_bus`, `get_branch_info` | `network_utils.*`; step `query-topology` |
| `total_load`                        | `network_utils.total_load`; step `aggregate-loads` |
| Branch column conventions           | docstring on `network_utils.get_branch_info` and step description |

No source content was dropped.
