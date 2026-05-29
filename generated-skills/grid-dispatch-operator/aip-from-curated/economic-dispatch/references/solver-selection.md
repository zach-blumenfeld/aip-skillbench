# Solver Selection

## Default: CLARABEL

Use CLARABEL for economic dispatch with quadratic costs and DC-OPF network
constraints. It is a robust interior-point solver and handles ill-conditioned
problems well.

```python
prob = cp.Problem(cp.Minimize(cost), constraints)
prob.solve(solver=cp.CLARABEL)
```

## Why not OSQP?

OSQP is the CVXPY default for QPs but may fail or return inaccurate solutions
on DC-OPF problems with reserves — the constraint matrix is typically poorly
scaled (mix of branch limits, power balance, capacity coupling), and OSQP's
ADMM iterates can stall.

## Fallback ladder

1. `cp.CLARABEL` — first choice
2. `cp.ECOS` — alternative interior-point, smaller problems
3. `cp.SCS` — last resort, looser tolerances

If `prob.status` is not `optimal`/`optimal_inaccurate` after CLARABEL,
re-solve with ECOS before reporting failure.
