# Modeling notes: ordered-window sequencing MIPs and PySCIPOpt

Load this file only when you must change the model in `scripts/blockseq.py` (an objective
definition the script's flags cannot express, a new constraint family, a different solver call),
or when you need to explain a modeling choice the report does not already cover.

## Choosing the sequence representation

- **Assignment variables** `x[i,t]` (item i at position t) plus auxiliary window variables. This is
  what `blockseq.py` uses: `x` binary, adjacent-pair flow `y[a,b,t]`, big-M triplet costs `u`, `v`.
- **Arc variables** for predecessor/successor relations (route-style models).
- **Direct ordered-window model**: `W[t,a1..ar] = 1` if ordered tuple (a1..ar) starts at t. Constraint
  families: exactly one window per eligible start; each item appears the required number of times in
  each position role; windows with repeated items are prohibited for permutations; neighbouring
  windows agree on shared items (prefix/suffix continuity below). Tighter LP, but at 24 blocks a
  length-3 window model has ~270k columns: SCIP presolve alone took ~226 s and the root LP did not
  finish in 300 s. Do not use it for full-size instances unless the time budget is generous.

## Linearizations

Assignment-linked length-3 window (standard AND linearization; create only for eligible starts):

```text
window[i,j,k,t] <= assign[i,t]
window[i,j,k,t] <= assign[j,next_t]
window[i,j,k,t] <= assign[k,next_next_t]
window[i,j,k,t] >= assign[i,t] + assign[j,next_t] + assign[k,next_next_t] - 2
```

Same pattern for pairs or longer windows. Every auxiliary needs its lower-bound linking constraint,
or a minimizing solver sets it to 0.

Prefix/suffix continuity for length-r windows (one consistent global sequence):

```text
sum over a0 of W[t, a0, q1..q_{r-1}] = sum over ar of W[next(t), q1..q_{r-1}, ar]
```

for each shared ordered (q1..q_{r-1}). Use cyclic wraparound only when the source formulation makes
the sequence cyclic; otherwise handle first/last positions with explicit boundary logic. Even in a
cyclic model, reported metrics use only the declared eligible starts.

Overlap of two active patterns A and B:

```text
overlap <= A;  overlap <= B;  overlap >= A + B - 1
```

Attach the instance-defined ordered cost to `overlap` and keep it inside the optimized model:
optimizing a reduced model and adding the high-order penalty afterwards optimizes a different problem.

Big-M cost aggregation (what `blockseq.py` does, compact and exact at integral points because the
cost variable is minimized):

```text
u[a,b,s] >= sum_c W_s[a,b,c] * x[c,s+k] - max_c W_s[a,b,c] * (1 - y[a,b,s])     # offsets (0,1,k)
v[a,s]   >= sum_(c,d) W_s[a,c,d] * y[c,d,s+k] - max W_s[a,.,.] * (1 - x[a,s])      # offsets (0,k,k+1)
```

The LP bound is weak (the real instance shows ~130% gap after 120 s) but the model builds in seconds
and accepts the warm start. Offsets of the form (0,i,j) with i>1 and j>i+1 are not supported; add a
non-adjacent pair variable family if you need them.

## Overlap definitions are not interchangeable

When prose mentions pressure, overlap, or "three in four", distinguish:

- all unordered triples contained in a four-position span;
- ordered triples whose positions have span at most four;
- pairs of adjacent active three-position windows sharing positions;
- explicit auxiliary variables from a source formulation.

Before implementing one, write down: primitive pattern, active-start set, overlap membership rule,
overlap cost formula. Generic active-pattern evaluator:

```python
active = {tuple(item_at(start, o) for o in primitive_offsets) for start in eligible_starts}
overlap = 0
for ext in candidate_extended_tuples:
    if primitive_left(ext) in active and primitive_right(ext) in active:
        overlap += overlap_cost(ext)
```

Wrong unless explicitly defined that way:

```python
for window in all_length_4_windows:
    for triple in combinations(window, 3):
        overlap += triplet_count[triple]
```

## PySCIPOpt API notes

```python
from pyscipopt import Model, quicksum
m = Model("mip"); m.setParam("limits/time", 600.0)
m.setObjective(expr, "minimize"); m.optimize()
status = str(m.getStatus()).lower()           # "optimal", "timelimit", ...
if m.getNSols() == 0: raise RuntimeError(status)
sol = m.getBestSol(); inc = m.getSolObjVal(sol)
bound = m.getDualbound(); gap = m.getGap()
val = m.getSolVal(sol, var)                   # or m.getVal(var); never var.getVal()
# warm start
s = m.createSol(); m.setSolVal(s, var, 1.0); accepted = m.addSol(s, free=True)
```

Manual gap check for minimization: `(incumbent - bound) / max(1, abs(incumbent))`; prefer the
solver's own gap (SCIP uses |primal-dual| / |dual|, which can exceed 100% with a weak bound).
Statuses such as time, node, solution, or gap limit mean an incumbent, not a proof of optimality.
Never round non-integral binaries to "fix" an extraction; investigate the model instead.
