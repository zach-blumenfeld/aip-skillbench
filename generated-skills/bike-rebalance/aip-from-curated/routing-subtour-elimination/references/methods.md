# Subtour-Elimination Method Catalog

Load this file when the canonical helper scripts do not fit your model
(different variable shape, custom indexing, mixed depots) and you need
to re-derive a method by hand. Each section gives the structural shape
and the gotcha that bites if you skip it.

All snippets assume the base notation in `references/notation.md` —
`x[v, i, j]`, `vehicles`, `stations`, `START`, `END`, and `n =
len(stations)`.

## 1. MTZ Order Constraints

Compact: O(K n^2) constraints, O(K n) extra variables. LP relaxation is
weak compared with cutset / flow formulations.

```python
order = {(v, i): model.addVar(vtype="C", lb=1, ub=max(1, n),
                              name=f"order_{v}_{i}")
         for v in vehicles for i in stations}

for v in vehicles:
    for i in stations:
        for j in stations:
            if i != j:
                model.addCons(order[v, i] - order[v, j] + n * x[v, i, j] <= n - 1)
```

Pros: small, easy, good default for small / medium instances.
Cons: weak relaxation; can be slow for larger VRPs; order variables are
artificial — do NOT interpret as service times.

## 2. Single-Commodity Flow Connectivity

Artificial flow originates at the depot and distributes one unit to
each visited station. The flow is not physical vehicle load.

```python
visit = {(v, i): quicksum(x[v, i, j] for j in [*stations, END] if j != i)
         for v in vehicles for i in stations}

flow_arcs = [(i, j) for i in [START, *stations] for j in stations if i != j]
f = {(v, i, j): model.addVar(vtype="C", lb=0, ub=n,
                             name=f"conn_flow_{v}_{i}_{j}")
     for v in vehicles for (i, j) in flow_arcs}

for v in vehicles:
    total_visits = quicksum(visit[v, i] for i in stations)
    model.addCons(quicksum(f[v, START, j] for j in stations) == total_visits)

    for (i, j) in flow_arcs:
        model.addCons(f[v, i, j] <= n * x[v, i, j])

    for i in stations:
        incoming_flow = quicksum(f[v, h, i] for h in [START, *stations] if h != i)
        outgoing_flow = quicksum(f[v, i, j] for j in stations if j != i)
        model.addCons(incoming_flow - outgoing_flow == visit[v, i])
```

Pros: stronger connectivity than MTZ in many models; static, no
callback; works with optional visits.
Cons: O(K n^2) extra continuous variables; more memory than MTZ.

NEVER reuse physical truck load as the connectivity flow when the
vehicle can both pick up and drop off — physical load can both increase
and decrease, so it cannot prove connectivity.

## 3. DFJ Subset Cuts (Static Enumeration)

For every nonempty proper subset S of stations:

```text
sum_{i in S, j in S, i != j} x[v, i, j] <= |S| - 1
```

Full enumeration:

```python
from itertools import combinations

for v in vehicles:
    for r in range(2, n):
        for S_tuple in combinations(stations, r):
            S = set(S_tuple)
            model.addCons(
                quicksum(x[v, i, j] for i in S for j in S if i != j)
                <= len(S) - 1
            )
```

Pros: strong, direct subtour elimination, no auxiliary variables.
Cons: exponential constraint count.

Only acceptable for tiny instances (curated: roughly 15-18 stations
maximum) or as a debugging baseline.

## 4. Lazy / Iterative DFJ Cut Separation

Solve with base route constraints, detect subtours in the incumbent,
add only the violated DFJ cuts, re-solve. Convergence is theoretical;
worth a max-iteration guard against bugs in cycle detection.

```python
def selected_arcs(model, x, v, arcs):
    return [(i, j) for (i, j) in arcs if model.getVal(x[v, i, j]) > 0.5]

def station_cycles_without_start(selected, stations):
    succ = {i: j for (i, j) in selected}
    cycles = []
    seen = set()
    for s in stations:
        if s in seen or s not in succ:
            continue
        path = []
        pos = {}
        cur = s
        while cur in succ and cur not in pos and cur not in seen:
            pos[cur] = len(path)
            path.append(cur)
            cur = succ[cur]
        seen.update(path)
        if cur in pos:
            cycle = path[pos[cur]:]
            if START not in cycle and END not in cycle:
                cycles.append(cycle)
    return cycles

while True:
    model.optimize()
    if model.getNSols() == 0:
        raise RuntimeError(f"no feasible solution; status={model.getStatus()}")

    cuts_added = 0
    for v in vehicles:
        selected = selected_arcs(model, x, v, arcs)
        for cycle in station_cycles_without_start(selected, stations):
            if len(cycle) >= 2:
                S = set(cycle)
                model.freeTransform()
                model.addCons(
                    quicksum(x[v, i, j] for i in S for j in S if i != j)
                    <= len(S) - 1
                )
                cuts_added += 1

    if cuts_added == 0:
        break
```

Pros: only cuts that are needed; often stronger than MTZ; avoids
exponential static SEC generation.
Cons: iterative resolve can be slower than a true lazy callback;
requires reliable subtour detection.

`model.freeTransform()` is required before `addCons` after a SCIP
solve. Without it the second iteration silently fails to add the cut.

## Method Choice Table

| Method                  | Best For                                              | Avoid When                                                       |
| ----------------------- | ----------------------------------------------------- | ---------------------------------------------------------------- |
| MTZ                     | Quick, compact, small/medium MIPs                     | Large hard VRPs where relaxation strength matters                |
| Single-commodity flow   | Stronger static connectivity, optional visits         | Memory is tight, or `n` is large                                 |
| Multi-commodity flow    | Very strong small routing models                      | Most practical benchmark tasks; too many variables               |
| Static DFJ              | Tiny instances, debugging                             | More than roughly 15-18 stations without careful filtering       |
| Lazy / iterative DFJ    | Strong routing models with many possible SECs         | Solver API / callback complexity is too risky                    |

For pickup/dropoff rebalancing, start with MTZ or artificial
connectivity flow. Do NOT use physical truck load as the only
subtour-elimination mechanism — pickup/dropoff load can increase and
decrease and may not prove route connectivity.
