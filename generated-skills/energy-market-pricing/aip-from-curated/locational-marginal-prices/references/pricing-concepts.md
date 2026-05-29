# Pricing Concepts — LMPs, Reserve MCP, and Counterfactual Economics

Reference for the *interpretation* of values the `lmp_utils` scripts return.
Load on demand when an LMP looks "wrong", a counterfactual cost goes the
unexpected direction, or you need to explain a result to a stakeholder.

## 1. What an LMP actually is

An LMP at bus `i` is the marginal cost of serving one additional MW of load
at that bus *given the binding constraints of the current dispatch*. In
optimization terms it is the **dual value (shadow price)** of the bus-`i`
power-balance equality constraint.

For the canonical DC-OPF balance written in per-unit:

```
  generation_i - load_i  ==  sum over branches of net export
```

the dual `λ_i` has units of `$ / pu-MW`. Because per-unit power is
`P_MW / baseMVA`, the dollar-per-MWh value is:

```
  LMP_i  =  λ_i * baseMVA
```

Forgetting the `* baseMVA` factor is the single most common LMP bug — prices
come out ~100× too small (or whatever baseMVA the file uses).

## 2. The LMP sign convention

Using the balance form `generation - load == net_export`:

- **Positive LMP** — adding 1 MW of load at the bus *raises* total system
  cost. This is the typical case.
- **Negative LMP** — adding 1 MW of load at the bus *lowers* total system
  cost. The bus is downstream of a congested line trapping cheap generation;
  adding local load consumes that excess instead of forcing redispatch
  elsewhere.

Negative LMPs are not bugs. In heavily congested systems they can reach
thousands of dollars per MWh and should be reported verbatim. Do not take
absolute values or clip to zero.

## 3. Reserve MCP

The reserve market-clearing price (MCP) is the dual of the system-wide
spinning-reserve requirement:

```
  sum_g R_g  >=  reserve_requirement
```

Because `R_g` and `reserve_requirement` are stored in MW (not per-unit) in
the PGLib reserve extension, the dual is already in `$/MWh`. **Do not scale
it by baseMVA.** Doing so silently inflates the reported MCP by ~100×.

## 4. Binding lines

A line is "binding" when its absolute flow is at or near its thermal rating
`rateA`. The conventional threshold is 99% loading; the task spec adopts
this exact cutoff. Below 99% the line has spare capacity and is irrelevant
to congestion analysis.

DC line flow from solved angles:

```
  flow_MW = (1 / x) * (theta[f] - theta[t]) * baseMVA
  loading_pct = |flow_MW| / rateA * 100
```

Always read `theta.value`, not `theta`, after `prob.solve()`. Skip branches
where `x == 0`, `rateA == 0`, or `status == 0` (out of service).

## 5. Counterfactual economics

Relaxing a binding constraint (e.g., raising a line's `rateA`) is equivalent
to giving the solver more feasibility. Therefore:

- **Cost cannot increase.** `cost_reduction = base_cost - cf_cost >= 0`.
  A negative cost reduction indicates a modeling bug — usually a stale
  branch array, a missing constraint-reference store, or a solver tolerance
  issue.
- **The cost reduction equals the constraint's shadow price** times the
  amount of relaxation, in the limit of small changes. For larger changes
  (20% rating bump), the reduction reflects the full re-dispatch.
- **LMP convergence** — relieving congestion narrows the LMP spread across
  buses. If LMPs were highly separated before and converge after, the
  counterfactual confirms the line was the cause of price separation.
- **`congestion_relieved`** is true only when the target line was binding
  in the base case AND is no longer binding in the counterfactual. A line
  that was never binding cannot be "relieved" by raising its limit.

## 6. Ranking LMP drops

When the spec asks for "buses with the largest LMP drop", "largest" means
the **most-negative `delta = cf_lmp - base_lmp`** — the prices that fell
furthest. Do NOT rank by absolute magnitude (which would mix LMP rises and
falls) and do NOT sort by `base_lmp` alone.

Tie-break by bus number ascending so the output is reproducible across
re-runs and across solvers that may permute equal-valued variables.
