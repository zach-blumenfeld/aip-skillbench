# Extraction And Independent Validation

SCIP reporting `optimal` or `feasible` means the **model** is satisfied — it
does not mean the reported file is correct. Always reconstruct the answer from
variable values and recompute every objective component and hard rule before
declaring success.

## Reading variable values

```python
def is_selected(var):
    return model.getVal(var) > 0.5
```

Compare binaries with a 0.5 cutoff; never trust exact equality against `1.0`.
For integer variables, round explicitly when you serialise them.

## Recompute the objective from selected decisions

```python
selected_arcs = [(i, j) for i, j in arcs if is_selected(x[vehicle, i, j])]
reported_cost = sum(distance[i, j] for i, j in selected_arcs)

if abs(reported_cost - expected_cost) > 1e-6:
    raise AssertionError("reported objective component does not match reconstruction")
```

Apply the same pattern to every named objective component (travel cost,
penalty, fixed cost, …). Discrepancies signal either a modeling bug, a
linking-constraint gap, or an extraction bug — investigate before reporting.

## Independent checks the reported file must pass

Run these *outside* SCIP, against the reconstructed solution:

1. **Schema** — every required field present, types correct, IDs match the
   input.
2. **Route reconstruction** — start at the depot, follow selected arcs, end at
   the depot. No disconnected segments, no repeated visits unless the model
   explicitly allows them.
3. **Capacity** — vehicle loads and station inventories stay within bounds at
   every step, not just at the start/end.
4. **Inventory / flow conservation** — `load_after_stop = previous_load +
   pickup - dropoff` (or the problem's equivalent) holds at every node.
5. **Penalty arithmetic** — unmet quantities computed from the
   reconstructed solution match the reported penalty term.
6. **Objective arithmetic** — the sum of reconstructed components equals the
   reported objective to within `1e-6`.

If any check fails, fix the model or the extraction before submitting — do not
patch the report to make the numbers reconcile.
