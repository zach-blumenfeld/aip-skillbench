# Authoring notes — power-flow-data (AIP)

## Source
- `source/SKILL.md` — the curated Agent Skill from `vendor/skillsbench/tasks/grid-dispatch-operator/environment/skills/power-flow-data/`.

## Schema choice
- `source/procedure.schema.json` — the AIP `procedure` schema. The source SKILL is a structured guide for parsing MATPOWER-format network JSON: load → topology → connectivity → branch interpretation → load aggregation. That maps cleanly onto an execution graph of script-backed steps.

## Authoring decisions
- **Code lifted into `scripts/network_utils.py`.** Every Python helper in the source (`load_network`, `bus_num_to_idx`, `get_generators_at_bus`, `find_slack_bus`, `get_branch_info`, `total_load`, per-unit conversions) is consolidated into one importable module. Per AIP best practices, fewer script files is better when the logic is tightly coupled around one domain object (the network dict).
- **MATPOWER column semantics and bus-type table lifted into `references/matpower-format.md`.** Bus type codes, per-unit base-MVA convention, branch column layout, and reserve fields are lookup tables — pure reference material the agent loads only when interpreting raw rows. Keeping them out of `SKILL.md` keeps the body lean.
- **The "never read line-by-line" warning stays in the body.** It is an anti-pattern correction the agent needs *before* it picks a parsing strategy, so it belongs in steps + anti-patterns, not in an on-demand reference.

## Completeness check against `source/SKILL.md`
- L8 MATPOWER + PGLib-OPF provenance → captured in `purpose` and `references/matpower-format.md`.
- L10–34 Large-file warning + `wc -l` / `du -h` size check → `inspect-and-load` step + anti-patterns.
- L36–57 Bus types + per-unit system → `references/matpower-format.md`.
- L59–79 `load_network` → `scripts/network_utils.py::load_network`.
- L81–93 Reserve data → `references/matpower-format.md` + `load_network` output.
- L95–105 Bus number mapping → `scripts/network_utils.py::bus_num_to_idx` and `gen_bus_indices`.
- L107–125 Bus connections / slack bus → `scripts/network_utils.py::get_generators_at_bus`, `find_slack_bus`.
- L127–143 Branch data interpretation → `scripts/network_utils.py::get_branch_info` + branch column table in references.
- L145–151 Total load → `scripts/network_utils.py::total_load`.

No content deliberately dropped.
