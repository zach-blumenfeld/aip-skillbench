# Route Validation

After solving, reconstruct each route by following selected arcs and fail fast on any disconnect, repeated station, or missing depot endpoint.

```python
def extract_route(selected):
    outgoing = dict(selected)
    route = [START]
    cur = START
    seen = {START}
    while cur != END:
        if cur not in outgoing:
            raise RuntimeError(f"route disconnected at {cur!r}")
        cur = outgoing[cur]
        if cur in seen and cur != END:
            raise RuntimeError(f"cycle detected at {cur!r}")
        route.append(cur)
        seen.add(cur)
    return route
```

Apply per vehicle using its selected arcs:

```python
for v in vehicles:
    selected = [(i, j) for i, j in arcs if model.getVal(x[v, i, j]) > 0.5]
    route = extract_route(selected)
```

## What it catches
- **Disconnected route** — a station has no outgoing arc, signaling the model picked an inconsistent set.
- **Cycle in the depot path** — a station repeats before `END`, meaning subtour elimination failed for this incumbent.
- **Missing `END`** — the path stops before reaching the depot.

If any of these fire, the subtour-elimination method is insufficient (e.g., MTZ relaxation accepted a fractional incumbent that integer-rounded to a cycle) or a base degree constraint is missing. Tighten the method or re-check base constraints.
