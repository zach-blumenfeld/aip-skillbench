# DC-OPF with reserve co-optimization — formulation reference

This is the math the solver implements. Read it when you need to debug LMPs, modify constraints, or explain results.

## Decision variables

| Symbol     | Shape    | Meaning                                              |
|------------|----------|------------------------------------------------------|
| `p_g`      | n_gen    | Energy dispatch of generator `g` (MW).               |
| `r_g`      | n_gen    | Spinning reserve provision of generator `g` (MW).    |
| `θ_b`      | n_bus    | Voltage angle at bus `b` (radians).                  |

## Objective

```
minimize  Σ_g  c_g · p_g  +  Σ_g  rc_g · r_g
```

`c_g` is the linear marginal energy cost from `gencost`. `rc_g` is the reserve offer cost (defaults to 0 when the network has no `reserves` block).

## Constraints

### (1) Bus power balance (DC approximation)

For every bus `b`:

```
Σ_{g at b} p_g  −  pd_b  =  baseMVA · Σ_b'  B_bus[b,b'] · θ_b'
```

Vectorized: `G · p  −  pd  =  baseMVA · B_bus · θ`, where `G` is the (bus × gen) incidence and `B_bus` is the susceptance Laplacian:

```
B_bus[b,b]  =  Σ_{branches k incident to b}  1/x_k
B_bus[b,b'] = −1/x_k  for each branch k between b and b'
```

The **LMP at bus `b` is the Lagrange multiplier of this equality**, with positive sign convention (raising `pd_b` by 1 MW raises the optimal cost by `LMP_b`).

### (2) Slack-bus angle pin

`θ_slack = 0`. Required because the DC power flow has a one-dimensional null space (a uniform angle shift produces the same flows).

### (3) Line thermal limits

For every branch `k = (i, j)`:

```
−rateA_k  ≤  baseMVA · (1/x_k) · (θ_i − θ_j)  ≤  rateA_k
```

A line is **binding** when `|flow_k| ≥ binding_threshold · rateA_k` (default `binding_threshold = 0.99`).

### (4) Generator capacity with reserve coupling

```
Pmin_g  ≤  p_g
p_g + r_g  ≤  Pmax_g          ← standard capacity coupling
0  ≤  r_g  ≤  rmax_g
```

Capacity coupling is the key reason energy and reserve markets clear jointly. Drop the `+ r_g` term and the markets decouple — LMPs and the reserve MCP both end up wrong.

### (5) System reserve requirement

```
Σ_g  r_g  ≥  R_req
```

`R_req` defaults to the largest in-service `Pmax` (N-1 contingency). The **reserve MCP is the dual of this constraint**, again with positive sign.

## Why LMPs are the equality duals

Recall the Lagrangian for `min c·x  s.t.  A·x = b`:

```
L(x, λ) = c·x − λ · (A·x − b)
```

Envelope theorem: `∂(optimal cost) / ∂b_i  =  λ_i`. The bus power balance row puts `pd_b` on the RHS, so `λ_b = ∂cost / ∂pd_b`, which is the textbook LMP.

In LP solvers:

- HiGHS (`scipy.optimize.linprog(method="highs")`) returns `res.eqlin.marginals` with this same sign convention.
- CVXPY's `constraint.dual_value` follows a similar convention but the sign can flip depending on how you wrote the constraint. If your LMPs come back with median < 0, multiply by −1 (the solver script does this automatically).

## Why the reserve MCP is the inequality dual

For `min c·x  s.t.  A·x ≤ b`:

```
∂(optimal cost) / ∂b  ≤  0
```

Loosening the constraint (larger `b`) cannot raise cost. We wrote the reserve requirement as `−Σ r_g ≤ −R_req`, so raising `R_req` *tightens* the constraint (lowers the RHS) and increases cost. The MCP is therefore `−(marginal of that row)`.

## What the LP does not capture

- AC voltage magnitudes and reactive power.
- Line losses (DC-OPF assumes lossless lines).
- Unit commitment (binary on/off, startup/shutdown). All units with `status=1` are assumed already committed.
- Multi-period chronological dispatch (ramp limits between hours, storage).
- Stochastic or robust formulations (uncertainty is collapsed to a deterministic reserve requirement).

If the task requires any of these, the agent must build a different model — this solver will silently produce the wrong answer.
