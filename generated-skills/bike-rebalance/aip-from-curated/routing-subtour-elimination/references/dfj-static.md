# DFJ Subset Cuts (Static Enumeration)

For every nonempty proper subset `S` of stations, selected station-to-station arcs inside `S` cannot form a closed cycle:

```text
sum_{i in S, j in S, i != j} x[v,i,j] <= |S| - 1
```

For very small `n`, static enumeration is possible:

```python
from itertools import combinations

for v in vehicles:
    for r in range(2, n):
        for S_tuple in combinations(stations, r):
            S = set(S_tuple)
            model.addCons(
                quicksum(x[v, i, j] for i in S for j in S if i != j) <= len(S) - 1
            )
```

## Pros
- Strong, direct subtour elimination.
- No artificial order or flow variables.

## Cons
- Exponential number of constraints.
- Static enumeration is only acceptable for small station counts.

## When to use
Use static DFJ only for tiny instances (n less than ~15-18 stations without careful filtering) or as a debugging baseline.
