# DC-OPF market clearing: method, prices, counterfactuals

`scripts/solve_market.py` implements all of this. Read this file when you must re-run, extend, or
explain the model by hand (e.g. a request needs a quantity the script does not output).

## DC approximation
Lossless lines (R ~ 0), flat voltage (|V| = 1 pu), small angles (sin t ~ t, cos t ~ 1). Flows depend
only on bus angles theta (rad) and reactances X. Suitable for dispatch, pricing, contingency screens.

## Susceptance matrix
For each branch with x != 0: b = 1/x; B[f,f] += b; B[t,t] += b; B[f,t] -= b; B[t,f] -= b
(f, t via the bus-number map). Use sparse matrices for large grids (`scripts/build_b_matrix.py` in
`source/dc-power-flow/` is the dense reference version). Store each branch's b for flow constraints
(b = 0 when x = 0).

## Constraints
- Nodal balance at every bus: Pg_bus - Pd = B[i,:] @ theta (pu), equivalently in MW times baseMVA.
- Slack: theta[slack] = 0 for the type-3 bus.
- Flow on branch k: flow_MW = b (theta_f - theta_t) baseMVA; limit -RATE_A <= flow <= RATE_A.
- Loading % = |flow_MW| / RATE_A * 100.
- Generator limits: PMIN <= Pg <= PMAX (convert MW / baseMVA if Pg is per-unit).
- Without a network: sum(Pg) = total load. With a network use nodal balance instead.

## Objective
sum_i c2 P_i^2 + c1 P_i + c0 ($/hr), P in MW (Pg_pu * baseMVA). Linear costs (c2 = 0) give an LP.

## Reserve co-optimization (when reserve data exists)
Rg (MW) per generator: Rg >= 0; Rg <= reserve_capacity; Pg_MW + Rg <= PMAX; sum(Rg) >= R.

## Outputs
- Dispatch rows: `{id: i+1, bus, output_MW, reserve_MW, pmax_MW}` rounded to 2 dp.
- Totals: `cost_dollars_per_hour` (objective), `load_MW`, `generation_MW`, `reserve_MW`.
- Operating margin = sum(PMAX - Pg_MW - Rg_MW): uncommitted headroom beyond energy and reserves.

## Solver
cvxpy with CLARABEL (robust interior point); OSQP may fail on ill-conditioned DC-OPF with reserves.

## LMPs (dual of nodal balance)
LMP = marginal cost of serving one more MW of load at the bus. Keep references to the balance
constraints, solve, read `dual_value`.

**Sign and scale (verified by finite difference, cvxpy 1.x):** cvxpy's Lagrangian is
f + y'(lhs - rhs). For `gen - load == B theta` written in **MW**, LMP = **-dual** ($/MWh). Written
in **per-unit**, LMP = **-dual / baseMVA**. The often-quoted `dual * baseMVA` is wrong in both sign
and scale (it gives values ~10^4 times too large with flipped sign). Always confirm one bus by
finite difference: add 1 MW to its load, re-solve, cost delta must equal its LMP.

Sign meaning: positive LMP = more load raises cost (typical). Negative LMP = more load lowers cost:
cheap generation trapped behind a congested line, local load relieves the congestion. Magnitudes can
reach thousands of $/MWh in congested grids. Valid, not an error.

## Reserve clearing price
Reserve MCP = dual of `sum(Rg) >= R` ($/MW-h), >= 0; zero when the requirement is slack-priced
(ample reserve headroom at zero reserve cost).

## Binding lines
Loading >= 99% of RATE_A (only branches with x != 0 and RATE_A > 0). Report from, to, flow_MW,
limit_MW. Binding lines cause congestion and LMP separation.

## Counterfactual analysis
1. Solve base case; record costs, LMPs, binding lines.
2. Modify the constraint, e.g. raise one line's RATE_A by 20%: find the branch matching
   (from,to) or (to,from), multiply RATE_A by 1.20, stop at the first match.
3. Solve the counterfactual.
4. Impact: cost_reduction = base_cost - cf_cost (>= 0 when relaxing); per-bus delta =
   cf_lmp - base_lmp (negative = price fell, congestion relieved); congestion_relieved =
   line binding in base AND not binding in counterfactual.

Intuition: relaxing a binding constraint cannot raise cost; the cost reduction measures the
constraint's shadow value; LMPs converging afterwards indicates reduced price separation.
