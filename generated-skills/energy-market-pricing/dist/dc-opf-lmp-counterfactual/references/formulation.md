# DC-OPF market model: formulation and data reference

Read this to check the model, extend the script, or explain a result.
`scripts/market_counterfactual.py` implements everything here.

## MATPOWER JSON layout (PGLib-OPF style)

Load the file with `json.load`. Network files can run to 100K+ lines, so never page
through them with `sed` or `head`. Keys are `baseMVA`, `bus`, `gen`, `branch`, `gencost`,
and optionally `reserve_capacity` (MW per generator, the r̄ values) and
`reserve_requirement` (system R, in MW).

| array | col | field |
|---|---|---|
| bus | 0 | BUS_I bus number (may be non-contiguous; always map number → row index) |
| bus | 1 | BUS_TYPE 1=PQ load, 2=PV generator, 3=slack/reference (θ=0) |
| bus | 2 | PD real load MW (total load = sum of col 2) |
| bus | 4 | GS shunt conductance (used only by `--dc-model matpower`) |
| gen | 0 | GEN_BUS bus number |
| gen | 7 | GEN_STATUS (≤0 = out of service → forced to 0 MW, 0 reserve) |
| gen | 8 / 9 | PMAX / PMIN MW |
| branch | 0 / 1 | F_BUS / T_BUS bus numbers |
| branch | 2 / 3 / 4 | R, X, line-charging B (pu); DC uses X only |
| branch | 5 | RATE_A MW limit (0 = unlimited, no flow constraint) |
| branch | 8 / 9 | TAP ratio (0 means 1), SHIFT degrees (used only by `--dc-model matpower`) |
| branch | 10 | BR_STATUS (≤0 = out of service, dropped) |
| gencost | 0..3 | MODEL (2 = polynomial, 1 = piecewise linear), STARTUP, SHUTDOWN, NCOST |
| gencost | 4+ | polynomial: NCOST coefficients, highest order first. NCOST=3 → c2,c1,c0; NCOST=2 → c1,c0; NCOST=1 → c0. PWL: NCOST (P MW, cost $/h) breakpoints |

Polynomial cost is C(P) = c2·P² + c1·P + c0 in $/h with P in MW. Marginal cost is 2·c2·P + c1.
Example: [2,0,0,3, 0.01, 20, 100] at 50 MW costs 0.01·2500 + 1000 + 100 = $1125/h.
PWL [1,0,0,3, 0,0, 50,1000, 100,2500] means breakpoints (0,0),(50,1000),(100,2500); the
script models it as an epigraph, which is exact only for convex curves.
Startup and shutdown costs play no part in a single-period dispatch.
Typical c1 values in $/MWh: nuclear 5–10, coal 15–25, CCGT 25–40, peaker 50–80.

Per-unit: P_pu = P_MW / baseMVA (baseMVA is usually 100).

## Model (one snapshot, minimize total $/h)

Variables: Pg (MW), Rg (MW), θ (rad).

- Objective: Σ C_i(Pg_i), including the c0 constants. `total_cost_dollars_per_hour` is this optimum.
- Nodal balance at every bus (DC: lossless, |V| = 1, sin θ ≈ θ):
  Σ_{g at bus} Pg − Pd = baseMVA · (B θ)_bus. B is the bus susceptance matrix,
  built from b = 1/x per in-service branch: diagonal +b, off-diagonal −b.
  The dual of this constraint is the LMP.
- Reference: θ_slack = 0 (the first bus with type 3; row 0 if none).
- Generator limits: Pmin ≤ Pg ≤ Pmax.
- Line thermal limits: |b·(θ_f − θ_t)·baseMVA| ≤ RATE_A, both directions, for RATE_A > 0.
- Reserves, only when the file has reserve data:
  0 ≤ Rg ≤ r̄ (reserve_capacity), Pg + Rg ≤ Pmax (standard capacity coupling),
  and Σ Rg ≥ R (reserve_requirement). The dual of Σ Rg ≥ R is the reserve MCP in $/MW·h.
  Reserves carry no offer cost, so the MCP is positive only when holding reserve forces
  costlier energy dispatch (coupling binds).

Line flow is b·(θ_f − θ_t)·baseMVA in MW: positive means from→to.
Loading % is |flow| / RATE_A · 100. A line counts as **binding** when loading ≥ 99%.

Operating margin is the uncommitted headroom Σ(Pmax − Pg − Rg). The script's `run --dispatch-out FILE`
writes it, along with the per-generator dispatch and totals.

## LMP sign and magnitude

- Positive LMP: serving one more MW at the bus raises total cost (the normal case).
- Negative LMP: serving one more MW lowers cost. This happens when cheap power is trapped
  behind a congested line and extra local load relieves the congestion. It is valid, not
  an error, and in heavily congested grids the magnitude can reach hundreds or thousands
  of $/MWh.
- Without congestion every LMP equals the system marginal cost. Congestion causes the
  price separation between buses.
- At a generator strictly inside its limits, with no reserve coupling binding, LMP = its
  marginal cost. The script checks this (`lmp_check`) to validate the sign and scale of
  the duals.

## Counterfactual economics

- Relaxing a binding limit cannot raise the optimal cost, so cost_reduction ≥ 0 up to
  solver tolerance. It stays 0 if the line was not binding.
- The cost reduction measures the value of the extra capacity, roughly the line's shadow
  price × added MW.
- After relief, LMPs converge: the price spread shrinks around the relieved interface.
  Other lines may start binding as flows redistribute.
