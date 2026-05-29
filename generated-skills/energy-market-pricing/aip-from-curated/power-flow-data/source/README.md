# Source Notes — power-flow-data (AIP conversion)

## Intent

Convert the curated `power-flow-data` skill (MATPOWER-format reference + helper
snippets) into an AIP-validated procedure skill. The skill is data-plumbing for
PGLib-OPF JSONs: load, summarize, navigate non-contiguous bus numbering, look up
topology, and extract branch parameters. It is consumed by OPF / unit-commitment
solving tasks that need a clean handle on the network before doing math.

## Schema choice

`procedure.schema.json` — even though this skill is partly a reference, the
helper functions form a small execution graph (load → map → topology lookups,
branch parsing, total load). The procedure schema lets us back each step with a
script and keep the bus/branch/per-unit lookup tables in `references/`.

## Source → AIP mapping

| Source content                                  | Destination                              |
|-------------------------------------------------|------------------------------------------|
| "Important: Handling Large Network Files" warning | `anti_patterns` + `scenarios`          |
| `load_network()` snippet                        | `scripts/power_flow_data.py:load_network` |
| Quick summary print (bus/gen/branch counts)     | `scripts/power_flow_data.py:summarize_network` |
| Bus types table (1/2/3)                         | `references/matpower-format.md`          |
| Per-unit conversions                            | `references/matpower-format.md` + helper funcs |
| Reserve data fields                             | `references/matpower-format.md`; honored in `load_network` |
| Bus number mapping snippet                      | `scripts/power_flow_data.py:build_bus_mapping` |
| `get_generators_at_bus()`                       | `scripts/power_flow_data.py:get_generators_at_bus` |
| `find_slack_bus()`                              | `scripts/power_flow_data.py:find_slack_bus` |
| `get_branch_info()`                             | `scripts/power_flow_data.py:get_branch_info` |
| `total_load()`                                  | `scripts/power_flow_data.py:total_load`  |
| Branch column meanings                          | `references/matpower-format.md` (full column table) |

No deliberate drops — all source content is either mapped to a step+script or
captured in the reference doc.

## Bundled artifacts

- `procedure.schema.json` — local copy of the AIP procedure schema this skill
  validates against.
- `ORIGINAL-SKILL.md` — verbatim copy of the curated source SKILL.md for
  traceability.
