# power-flow-data — AIP Author Notes

## Source

Converted from the curated Agent Skill at
`vendor/skillsbench/tasks/energy-market-pricing/environment/skills/power-flow-data/SKILL.md`
(see `SKILL.original.md`). Skill is consumed by the `energy-market-pricing`
SkillsBench task, where the agent must parse a MATPOWER-format `network.json`
and run a DC-OPF + reserve co-optimization base vs counterfactual analysis.

## Schema choice

Picked `procedure.schema.json` (bundled at `procedure.schema.json`).
The source is a knowledge guide more than a procedure, but the procedure
schema fits because each utility (load, summarize, build index, locate slack,
lookup generators-at-bus, decode branch row, total load) is a discrete
script-backed step with typed inputs and outputs. The conceptual knowledge
that doesn't map to a step (column layouts, per-unit semantics, reserve
fields) is moved to `references/matpower-format.md` and loaded on demand.

No new schema drafted — schema reuse over invention per AIP best practices.

## Script vs prose decisions

Scripted (deterministic, mechanical — `scripts/network_utils.py`):
- Loading JSON into numpy arrays — fixed key set, fixed conversions.
- `bus_num_to_idx` mapping — pure dict construction.
- `find_slack_bus` — fixed lookup (column 1 == 3).
- `get_generators_at_bus` — index filter.
- `get_branch_info` — column-index → named-dict mapping.
- `total_load` — column sum.

Scripted (CLI orientation — `scripts/summarize_network.py`):
- Quick stdout summary an agent runs to orient before reading details. Keeps
  the agent off `head`/`sed` for multi-MB files.

Prose (judgment / context):
- *When* to convert per-unit (depends on downstream calculation) — prose.
- *Why* never to use `head`/`sed` — prose anti-pattern.
- Reserve data semantics (`reserve_capacity`, `reserve_requirement`) — prose
  + reference. These are interpreted by downstream optimization code, not by
  this skill, so a parser script would be premature.

## Mapping the source content

| Source section                       | Destination                                         |
|--------------------------------------|-----------------------------------------------------|
| Large-file warning                   | `anti_patterns` + `summarize-network` step          |
| Bus type table (PQ/PV/slack)         | `references/matpower-format.md`                     |
| Per-unit system block                | `references/matpower-format.md` + body purpose      |
| `load_network` Python snippet        | `scripts/network_utils.py::load_network`            |
| Reserve data table                   | `references/matpower-format.md`                     |
| `bus_num_to_idx` snippet             | `scripts/network_utils.py::bus_num_to_idx`          |
| `get_generators_at_bus`              | `scripts/network_utils.py`                          |
| `find_slack_bus`                     | `scripts/network_utils.py`                          |
| `get_branch_info`                    | `scripts/network_utils.py`                          |
| `total_load`                         | `scripts/network_utils.py`                          |
| MATPOWER + PGLib provenance line     | `purpose`                                           |

### Deliberate drops

- `wc -l network.json` / `du -h network.json` shell snippet. Redundant with
  `scripts/summarize_network.py` (which reports counts and presence of
  reserve fields in one shot) and on a multi-MB file `wc -l` is not
  meaningfully faster than `json.load`. Keeping it would partially undo the
  "don't use shell tools on network.json" anti-pattern.

## Notes for future iteration

- If downstream skills (`dc-power-flow`, `economic-dispatch`,
  `locational-marginal-prices`) need a shared loader, `network_utils.py` is
  the natural place to extend — keep its function signatures stable.
- The reserve fields (`reserve_capacity`, `reserve_requirement`) are not
  always present in MATPOWER files outside this benchmark. The loader treats
  them as optional and surfaces `None` when absent so this skill works on
  off-benchmark networks.
