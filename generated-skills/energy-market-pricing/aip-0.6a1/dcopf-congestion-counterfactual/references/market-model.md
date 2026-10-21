# Market model and data reference (DC-OPF + spinning reserve)

Load this when diagnosing a failed run, when the network file looks unusual, or when
you must explain or re-derive a result by hand. `scripts/clear_markets.py` implements
everything below; it is the source of truth.

## Network file (MATPOWER JSON, from the PGLib-OPF benchmark library, github.com/power-grid-lib/pglib-opf)

Files can be multi-MB (100K+ lines). Never page through them with `sed`/`head`; load
with `json.load` and print a summary (bus/gen/branch counts, total load).

Keys: `baseMVA`, `bus`, `gen`, `branch`, `gencost`, optional `reserve_capacity`
(MW per generator, r_bar) and `reserve_requirement` (MW system total, R), optional
`column_info`. Columns are 0-indexed:

| Array  | Col | Field |
|--------|-----|-------|
| bus    | 0 BUS_I (bus number) · 1 BUS_TYPE (1 PQ load, 2 PV generator, 3 slack: V and θ=0 specified) · 2 PD (MW) · 3 QD |
| gen    | 0 GEN_BUS · 7 GEN_STATUS · 8 PMAX (MW) · 9 PMIN (MW) |
| branch | 0 F_BUS · 1 T_BUS · 2 R · 3 X (pu) · 4 B (charging) · 5 RATE_A (MW limit) · 8 TAP · 9 SHIFT · 10 BR_STATUS |
| gencost| 0 MODEL (2 polynomial, 1 piecewise linear) · 1 STARTUP · 2 SHUTDOWN · 3 NCOST · 4+ coefficients |

- Bus numbers are not contiguous (e.g. case300). Always map `bus_number -> row index`;
  never use `bus - 1`.
- Per unit: P_pu = P_MW / baseMVA (typically 100).
- Generators at a bus: rows of `gen` whose GEN_BUS maps to that bus index.
- gencost model 2, NCOST=3: `[c2, c1, c0]` at cols 4-6, cost = c2·P² + c1·P + c0 ($/h,
  P in MW); NCOST=2: `[c1, c0]`; NCOST=1: constant. Model 1: breakpoints
  `(P1,C1)...(Pn,Cn)`. Marginal cost of a polynomial unit = 2·c2·P + c1. See
  `references/cost-functions.md` for examples and typical values.

## DC approximation

Lossless lines (R ≈ 0), flat voltage (|V| = 1 pu), small angles (sin θ ≈ θ). Flow on a
branch f→t: `flow_MW = baseMVA · (θ_f − θ_t) / X`. Susceptance b = 1/X; B-bus has
B[f,f] += b, B[t,t] += b, B[f,t] −= b, B[t,f] −= b (source `build_b_matrix.py`).
TAP and SHIFT are ignored (b = 1/X as in the source skills). Loading % =
|flow_MW| / RATE_A · 100.

## Optimization (one market clearing)

Variables: Pg (pu), Rg (MW), θ (rad).

- minimize Σ cost_i(Pg_i · baseMVA)  (includes c0 no-load terms)
- nodal balance, per bus: Σ_{g at bus} Pg_MW − PD = baseMVA · (B θ)_bus
- PMIN ≤ Pg_MW ≤ PMAX
- 0 ≤ Rg ≤ reserve_capacity; capacity coupling Pg_MW + Rg ≤ PMAX
- Σ Rg ≥ reserve_requirement
- −RATE_A ≤ flow_MW ≤ RATE_A for branches with RATE_A > 0
- θ_slack = 0 (bus type 3)

Solver: cvxpy + CLARABEL (robust interior point; OSQP can fail on this
ill-conditioned problem). HIGHS/SCS are fallbacks.

Related quantities (not in the report): operating margin = Σ (PMAX − Pg − Rg), the
uncommitted headroom; totals = generation MW, load MW, reserve MW, cost.

## Prices

- LMP = marginal cost of serving +1 MW at the bus = the balance constraint's dual.
  **cvxpy returns the negative of d(cost)/d(load)** for `gen − load == B θ`, and if the
  balance is written in per-unit the dual is per pu (×100 too big). The source skill's
  `dual * baseMVA` is wrong on both counts (off by −10⁴ on the task data). Write the
  balance in MW and take `LMP = −dual`; confirm with a +1 MW re-solve.
- Negative LMPs are valid: cheap generation trapped behind a congested line, where
  extra load relieves the constraint. Magnitudes can reach hundreds or thousands of
  $/MWh in heavily congested networks.
- Reserve MCP = dual of Σ Rg ≥ R ($/MW·h, non-negative). It is 0 when reserve is not
  scarce, i.e. the requirement is met by headroom without displacing energy.

## Counterfactual analysis

1. Solve base; record cost, LMPs, binding lines (loading ≥ 99% of RATE_A).
2. Multiply RATE_A of the target line (match either orientation; every parallel
   circuit) by (1 + pct/100).
3. Solve the counterfactual.
4. cost_reduction = base − cf (≥ 0: relaxing a constraint cannot raise the optimum;
   it quantifies the value of the constraint). delta = cf_lmp − base_lmp; negative is a
   price drop; take the 3 most negative. congestion_relieved = the target line is
   NOT binding (< 99%) in the counterfactual (the task's definition). Converging LMPs
   after relief indicate less price separation.

A newly binding line in the counterfactual is normal: flow re-routes onto a
different bottleneck.

## Failure causes

- Target line not found: check the bus numbers against `branch` cols 0-1 (either
  orientation) and BR_STATUS; the line may be a transformer or have a different
  number in the file.
- Infeasible: total load > online PMAX, reserve requirement > Σ min(reserve_capacity,
  PMAX − PMIN-dispatch), a bus with load but no path to generation (island), or a
  RATE_A too small to deliver load at a radial bus.
- Solver error: rerun; if CLARABEL fails, HIGHS handles LPs; quadratic costs need
  CLARABEL or OSQP.
