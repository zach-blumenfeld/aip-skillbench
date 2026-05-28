# Source notes — dc-opf-market-clearing

Authored from the task instruction at
`vendor/skillsbench/tasks/energy-market-pricing/instruction.md` (read-only).
No human-written skill or prior implementation was inspected during
authoring; the procedure was derived from the instruction alone.

## Coverage map

Every distinct piece of guidance in the instruction is captured in one of
the following:

| Source content                                              | Where it landed                                       |
|-------------------------------------------------------------|-------------------------------------------------------|
| "Run market clearing twice (base + counterfactual)"         | `steps.run-base-and-counterfactual`                   |
| "Increase line 64→1501 thermal capacity by 20%"             | Solver CLI flag `--override-line FROM,TO,FACTOR`; demonstrated in `scenarios[0]` |
| "DC-OPF with reserve co-optimization"                       | `references/dcopf-formulation.md` + solver script LP build |
| Constraint 1 — power balance at each bus                    | Solver `A_eq` rows + `references/dcopf-formulation.md` §(1) |
| Constraint 2 — thermal limits of generators and lines       | Solver `A_ub` rows + `references/dcopf-formulation.md` §(3), §(4) |
| Constraint 3 — spinning reserve with capacity coupling      | Solver capacity-coupling rows + reserve-req row; `references/dcopf-formulation.md` §(4), §(5) |
| MATPOWER format input                                       | `references/matpower-format.md` + solver `load_network`/`parse_network` |
| Required `report.json` structure                            | `references/report-template.md` + solver `run()` writer |
| `total_cost_dollars_per_hour`, `lmp_by_bus`, `reserve_mcp`  | Solver output formatting (rounded to 4 dp)            |
| `binding_lines` defined as `loading ≥ 99%`                  | Solver `binding_threshold` arg (default 0.99) + `decisions` row on threshold; report template |
| `cost_reduction = base - counterfactual`                    | Solver `run()` impact-analysis block + report template |
| `buses_with_largest_lmp_drop` — top 3 by reduction          | Solver sort on full-precision `cf_lmp − base_lmp`, truncate to 3 |
| `congestion_relieved` = targeted line NOT binding in CF     | Solver `is_line_binding` + `anti_patterns` line warning against assuming it's always true |

## Deliberate drops

None. Every distinct field and constraint named in the instruction is
either implemented in the solver or documented in a reference loaded on
demand.

## Schema choice

Bundled `procedure.schema.json` (the universal AIP procedure schema, v0.1).
This skill is a step-by-step procedure with decisions and worked
scenarios — the schema fits without modification.

## Authoring environment

- Python 3.10+
- `numpy`, `scipy` (both via standard pip)
- The solver embeds a `# /// script` PEP 723 block so `uv run scripts/solve_dcopf.py …` resolves dependencies automatically.
