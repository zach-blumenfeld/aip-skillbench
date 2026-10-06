# DC-OPF with Reserve Co-optimization — Formulation Reference

The `scripts/solve_dcopf.py` script encodes exactly the formulation
below. Read this when you need to understand its outputs, verify a
hand-worked example, or extend it (e.g. for counterfactual analysis).

## DC approximations

1. Lossless lines: ignore `R`.
2. Flat voltages: `|V| = 1.0` pu everywhere.
3. Small angles: `sin(θ) ≈ θ`, `cos(θ) ≈ 1`.

Flow depends only on bus angles `θ` and line reactances `X`.

## Decision variables

| Symbol    | Units | Description                       |
|-----------|-------|-----------------------------------|
| `Pg[i]`   | pu    | Real-power dispatch of generator i |
| `Rg[i]`   | MW    | Operating reserve from generator i |
| `theta[i]`| rad   | Voltage angle at bus i             |

## Objective — minimize total cost ($/hr)

Per-generator polynomial (quadratic/linear/constant) via gencost
NCOST column. For NCOST=3: `c2*P_MW² + c1*P_MW + c0`.

## Constraints

- Slack: `theta[slack] == 0` (bus with TYPE=3; fall back to index 0).
- Per generator: `pmin/baseMVA ≤ Pg[i] ≤ pmax/baseMVA`.
- Reserves non-negative: `Rg ≥ 0`.
- Per-generator reserve capacity: `Rg[i] ≤ reserve_capacity[i]`.
- Capacity coupling: `Pg[i]*baseMVA + Rg[i] ≤ pmax_MW[i]`.
- System reserves: `sum(Rg) ≥ reserve_requirement`.
- Nodal balance (per bus i, per-unit):
  `sum(Pg[g] for g at bus i) - Pd[i]/baseMVA == B[i, :] @ theta`.
  Keep a reference to each of these constraints — their dual values are
  the LMPs.
- Line thermal limits (per branch, MW):
  `|b_k * (theta[f] - theta[t]) * baseMVA| ≤ RATE_A`.

Where `B` is the susceptance matrix built from `1/X` entries:

```
B[f,f] += 1/x;  B[t,t] += 1/x;  B[f,t] -= 1/x;  B[t,f] -= 1/x
```

Bus numbering may be non-contiguous — use a `bus_num_to_idx` mapping
whenever indexing into arrays.

## Solver

Use CLARABEL. OSQP is unreliable on ill-conditioned DC-OPF problems
with reserves.

## Extracting outputs

- **Dispatch**: `Pg.value * baseMVA` for energy (MW); `Rg.value` is
  already MW.
- **LMP** at bus i (`$/MWh`):
  `balance_constraints[i].dual_value / baseMVA`.
  The balance constraint is in per-unit (`Pg_pu - Pd_pu = B@theta`)
  while the objective is written over `Pg_MW = Pg_pu * baseMVA`, so by
  KKT the dual carries units of `$/(pu·hr) = baseMVA × $/MWh`. Divide
  (do not multiply) by `baseMVA` to recover LMP in `$/MWh`.
  Negative LMPs are physically valid in a congested network — do not
  treat them as errors.
- **Reserve MCP** (`$/MWh`): `reserve_con.dual_value` directly (the
  reserve constraint is already in MW).
- **Line flow** (MW): `b_k * (theta[f] - theta[t]) * baseMVA`.
- **Binding line**: `|flow_MW| / RATE_A ≥ 99 %`.

## Counterfactual analysis (optional extension)

To study relieving a congested line, re-solve with that line's
`branches[k, 5]` (RATE_A) increased (e.g. by 20 %), then compare costs
and LMPs. Relaxing a binding constraint can only lower cost; LMPs tend
to converge when congestion is removed.
