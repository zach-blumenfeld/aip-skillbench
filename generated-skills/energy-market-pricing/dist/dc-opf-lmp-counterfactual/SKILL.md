---
name: dc-opf-lmp-counterfactual
description: "Clear a day-ahead electricity market as DC-OPF with spinning-reserve co-optimization on a MATPOWER/PGLib network JSON. Extracts nodal LMPs and the reserve clearing price, flags binding lines, and runs a 'what if we relax this transmission line by X%' counterfactual that reports cost reduction, the largest LMP drops, and whether congestion is relieved. Use for congestion analysis, nodal price impact studies, line-rating counterfactuals, and economic dispatch with network and reserve constraints."
compatibility: "Python >= 3.9 with pip packages numpy, scipy, cvxpy (uses its bundled CLARABEL and HIGHS solvers). If they are missing, the script creates a venv (~/.cache/dcopf-venv) with python3 -m venv and pip-installs them, which needs network access. The ubuntu python3 + python3-venv image is enough."
---

# DC-OPF market clearing + line-relaxation counterfactual

## Trigger When

- A task asks to run market clearing, DC-OPF, or economic dispatch with network constraints on a MATPOWER-format `network.json` (keys `bus`, `gen`, `branch`, `gencost`, `baseMVA`, optionally `reserve_capacity` and `reserve_requirement`).
- You need nodal LMPs, a reserve market clearing price (MCP), or the list of binding or congested lines.
- A "what if" study changes one transmission line's thermal limit (for example "increase the line from bus A to bus B by 20%") and compares base and counterfactual costs, LMPs, and congestion.
- More broadly: explaining price spikes or price separation at buses, or quantifying the value of transmission capacity.

## Purpose

This skill solves the whole base-plus-counterfactual study with one script. It covers MATPOWER parsing with non-contiguous bus numbers, a sparse DC-OPF with reserve co-optimization (0 ≤ R ≤ r̄, P + R ≤ Pmax, ΣR ≥ requirement), LMPs and the reserve MCP taken from the duals, binding lines at ≥ 99% loading, and the comparison report. It also encodes the conventions and pitfalls an agent would otherwise get wrong. The most important is the sign and scale of cvxpy duals. The model and data columns are in [references/formulation.md](references/formulation.md); read it when you need the math or must explain a result.

## Procedure

### 1. Check the runtime and inspect the network (execution)

The script needs Python ≥ 3.9 and numpy, scipy, and cvxpy. You don't need to check them first: on the first run the script finds what is missing, names it on stderr, and installs it into a venv. The first container run takes about 10 s. If the bootstrap fails (for example with no network), report the missing packages it names and install them by another route.

```bash
python3 scripts/market_counterfactual.py inspect --network /root/network.json --from-bus A --to-bus B
```

Run this from the skill folder, giving data paths as absolute paths. A and B are the target line's buses from the task. The command prints the bus, generator, and branch counts, the slack bus, total load, generator capacity, out-of-service elements, the cost-model mix, the reserve data, and **every branch joining A and B** with its 0-based index, x, RATE_A, and status. Never read `network.json` with `cat`, `sed`, or `head`: it can be MBs.

### 2. Settle the study parameters (decision)

Take these values straight from the task statement:
- `--from-bus`/`--to-bus`: the target line. Order doesn't matter, and either direction matches.
- `--scale`: 1 + the % increase (+20% → 1.20, −10% → 0.90).
- `--out`: the report path. If the task names only a filename, write it in the task's working directory next to the input (for example `/root/report.json`).
- `--binding-threshold`: default 99; change it only if the task defines binding differently.
- `--top-n`: default 3.

Then answer these questions about the task statement and the inspect output:

```yaml
circuit_scope:
  type: choice
  instructions: >
    Which branches does the counterfactual relax? Answer "single" whenever inspect lists exactly
    one branch joining A and B. If it lists several, wrongly relaxing every circuit overstates the
    relief, so reconsider any close call that leans toward all_parallel.
  criteria:
    single: Exactly one branch joins A and B.
    all_parallel: Several branches join A and B, and the task speaks of the corridor or interface as a whole, or says "all circuits" or "the lines".
    one_circuit: Several branches join A and B, and the task identifies one of them by circuit id, order, or rating. Pass its 0-based index with --branch-index.
dc_model:
  type: choice
  instructions: >
    Which DC network model should be used? The default "source" (b = 1/x, taps, shifts and shunts
    ignored) is the convention of the curated skills this was built from. Switching without an explicit instruction changes every
    number, so pick matpower only on explicit wording.
  criteria:
    source: The task just says DC power flow or DC-OPF, or says nothing about transformers.
    matpower: The task explicitly requires transformer tap ratios, phase-shift angles, or MATPOWER makeBdc/rundcopf equivalence.
relieved_rule:
  type: choice
  instructions: How does the task define congestion_relieved?
  criteria:
    not_binding_cf: Relieved means the adjusted line is not binding in the counterfactual ("true indicates not binding"). Use this as the default.
    binding_base_and_not_cf: The task explicitly requires that the line was binding in the base case and is not binding in the counterfactual.
```

### 3. Run base and counterfactual (execution)

```bash
python3 scripts/market_counterfactual.py run --network /root/network.json \
  --from-bus A --to-bus B --scale 1.20 --out /root/report.json \
  [--all-parallel | --branch-index K] [--dc-model matpower] [--relieved-rule binding_base_and_not_cf]
```

Add the bracketed flags only when the step 2 answers call for them: `all_parallel` → `--all-parallel`, `one_circuit` → `--branch-index K`. If several circuits match and you pass neither flag, the script stops and lists their indices. The run takes about 1 s on a ~3000-bus case. It writes the report in exactly this schema:

- `base_case` and `counterfactual`, each with:
  - `total_cost_dollars_per_hour`
  - `lmp_by_bus`: `[{bus, lmp_dollars_per_MWh}]`, every bus, in file order
  - `reserve_mcp_dollars_per_MWh`
  - `binding_lines`: `[{from, to, flow_MW, limit_MW}]`. A line is binding when |flow|/RATE_A ≥ 99%. `flow_MW` is signed from→to, and `limit_MW` is the limit in force in that case, so the relaxed line shows the scaled limit.
- `impact_analysis`, with:
  - `cost_reduction_dollars_per_hour` = base − counterfactual
  - `buses_with_largest_lmp_drop`: the top-N most negative `delta = cf_lmp − base_lmp`, each as `{bus, base_lmp, cf_lmp, delta}`
  - `congestion_relieved`

Values are rounded to 2 decimals. If the task also asks for generator dispatch, totals, or operating margin, add `--dispatch-out /path/dispatch.json`. It writes `generator_dispatch` (`{id, bus, output_MW, reserve_MW, pmax_MW}`), `totals`, and `operating_margin_MW` (Σ Pmax − P − R) for each case. Stdout carries diagnostics that are not part of the report: the target line's flow and loading in both cases, the binding counts, LMP ranges, reserve totals, and `checks`.

### 4. Verify (execution output → decision)

The last stdout line is `{"checks": {...}, "all_checks_pass": ...}`. The checks are: solver optimal, LMP equals marginal cost at unconstrained generators within $0.05, counterfactual cost ≤ base cost, generation equals load, and the reserve requirement is met.
- If all of them pass, go to step 5.
- `solver_optimal` false, or `ERROR: ... infeasible`: the data can't be satisfied, for example load above total Pmax, reserve requirement above Σr̄, or an islanded load. Use the inspect totals to find out which, and report it. Do not loosen constraints to force a solution.
- Any other check false: rerun once. If it still fails, report the failing check next to the numbers instead of hiding it.

### 5. Report back (client task)

Tell the user where the report is. Then summarize: base and counterfactual cost and the reduction; whether the target line was binding in the base case (from the `target_base` loading) and its loading after relief; the reserve MCP; the three largest LMP drops; and any lines that start binding in the counterfactual. Explain negative or very large LMPs as congestion effects (see Gotchas), not errors.

## Gotchas

- **LMP sign and scale.** cvxpy's dual of `gen − load == B·θ` is −∂cost/∂load. The script poses balance in MW and uses LMP = −dual. The common recipe `dual * baseMVA` on a per-unit balance row gives LMPs of −10⁴× the true value (millions of $/MWh). `lmp_check` catches this.
- **Negative LMPs are valid.** Cheap generation trapped behind a congested line makes extra local load reduce cost. Magnitudes of hundreds of $/MWh happen in congested grids.
- **Bus numbers are labels**, not row indices: they may be non-contiguous. Always map number → row; never use `bus_number − 1`.
- **RATE_A = 0 means unlimited.** Such a branch gets no flow constraint and is never "binding". The script refuses to scale one.
- **Formulation conditioning.** The script poses the model in MW, not per unit. The per-unit form makes CLARABEL and HIGHS fail on big grids with tiny reactances (x ≈ 2e-4). If CLARABEL fails, the script falls back to HIGHS automatically.
- **Reserve MCP is often 0.** Reserves have no offer cost, so the price is positive only when the coupling P + R ≤ Pmax forces costlier redispatch. A 0 from a slack requirement is correct.
- **Relaxing a line can create new binding lines.** Flows reroute, and this is expected. The cost still cannot rise.
- **Ties in LMP drop** are broken by bus number. Many buses often share the same delta when congestion is fully relieved.
