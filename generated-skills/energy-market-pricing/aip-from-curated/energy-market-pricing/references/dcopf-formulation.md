# DC-OPF formulation with reserves and LMPs

The procedure's scripts implement the formulation in this reference.
Read it only when debugging an unexpected result (negative LMPs, no
binding lines where you expected some, counterfactual cost that went up).

## DC approximations
1. **Lossless lines** — resistance R ≈ 0.
2. **Flat voltage** — all bus voltage magnitudes = 1.0 pu.
3. **Small angles** — sin(θ) ≈ θ, cos(θ) ≈ 1.

Result: real-power flow depends only on bus angles θ and line reactances X.
Reactive power and voltage magnitude drop out of the problem.

## Susceptance matrix (B)
```
for br in branches:
    f = bus_num_to_idx[int(br[0])]
    t = bus_num_to_idx[int(br[1])]
    x = br[3]
    if x != 0:
        b = 1.0 / x
        B[f, f] += b;  B[t, t] += b
        B[f, t] -= b;  B[t, f] -= b
```
`B` is symmetric. Nodal balance: `Pg - Pd = B[i, :] @ θ` (per-unit).

## Decision variables
- `Pg[i]` — generator output (pu). Enforce `pmin/baseMVA ≤ Pg[i] ≤ pmax/baseMVA`.
- `θ[i]` — bus voltage angle (rad). `θ[slack] = 0`.
- `Rg[i]` — generator reserve (MW), only when `reserve_requirement > 0`.

## Objective
Minimize `Σ C_i(Pg[i] * baseMVA)` where `C_i` is the quadratic / linear /
constant polynomial from `gencost[i]`. Costs are evaluated in MW, not pu.

## Nodal balance (one per bus)
```
balance_cons[i]:  B[i, :] @ θ  ==  Σ_{g on i} Pg[g] - Pd[i]/baseMVA
```
Store references to these constraints — their dual values are the LMPs.
**LHS matters.** With `B@θ == pg - pd` CVXPY's equality dual carries the
sign convention where `dual / baseMVA` is the economically correct LMP
(positive at expensive buses, lowest at cheap-and-congested buses). The
mirror form `pg - pd == B@θ` returns duals of the opposite sign.

## Reserve co-optimization (when configured)
```
Rg[i] >= 0
Rg[i] <= reserve_capacity[i]
Pg[i]*baseMVA + Rg[i] <= pmax[i]        # capacity coupling
Σ Rg[i] >= reserve_requirement           # dual == reserve MCP
```

## Line-flow limits
```
flow_MW = (1/x) * (θ[f] - θ[t]) * baseMVA
-rate <= flow_MW <= rate
```
Lines with `rate <= 0` or `x == 0` are left unconstrained.

## Solver
Use `cp.CLARABEL` — robust interior-point, handles the quadratic objective and
reserves. `OSQP` is prone to failing on ill-conditioned DC-OPF-with-reserves.

## LMPs from duals
`lmp_i_$/MWh = balance_cons[i].dual_value / baseMVA`.
The balance constraint is per-unit; dual units are $/hr-per-pu, i.e.
$/hr per 100 MW. Divide by baseMVA to land in $/MWh.
Negative LMPs are physically valid in congested systems
(cheap generation trapped behind a congested line; local load relieves the
congestion by consuming excess output). Magnitudes of thousands of $/MWh
are possible under heavy congestion.

## Reserve MCP
`reserve_mcp_$/MWh = reserve_con.dual_value`. Not scaled by baseMVA because
the reserve constraint is written in MW.

## Binding-line definition
`loading_pct = |flow_MW| / rate_MW * 100`. A line is "binding" when
`loading_pct ≥ 99`. These are the candidates whose relaxation can lower cost.

## Counterfactual rules
- Pick the binding line with the highest loading% (ties broken by |flow|).
- Multiply its `RATE_A` by `counterfactual_scale` (default 1.20).
- Re-solve. The new cost must satisfy `cf_cost ≤ base_cost` to within solver
  tolerance; if not, treat as a solver/model bug.
- `congestion_relieved` is true when the target line is no longer binding.
- Per-bus `lmp_delta = cf_lmp - base_lmp`. Negative deltas mean the bus got
  cheaper.
