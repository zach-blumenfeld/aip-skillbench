# Business rule → variable choice → constraint pattern

Use this table to find the modeling pattern for a business rule. Each row is a
rule the agent will encounter in operations problems, the variable family that
encodes it, and the constraint shape that enforces it. The "constraint pattern"
column uses informal solver-agnostic syntax (`x`, `q`, `sum_j`); see
`constraint-snippets.md` and `variable-snippets.md` for runnable PySCIPOpt code.

| Business rule | Variable choice | Constraint pattern |
| --- | --- | --- |
| Choose exactly one option | `x[i,j]` binary | `sum_j x[i,j] == 1` |
| Choose at most one option | `x[i,j]` binary | `sum_j x[i,j] <= 1` |
| Open facility before assigning to it | `open[j]`, `assign[i,j]` binary | `assign[i,j] <= open[j]` |
| Resource capacity | quantity variable | `sum_i q[i,j] <= capacity[j]` |
| Quantity only if selected | `q[i]`, `use[i]` | `q[i] <= M * use[i]` |
| Fixed cost if used | `use[i]` binary | add `fixed_cost[i] * use[i]` to objective |
| Mutually exclusive modes | mode binaries | `sum_m mode[i,m] <= 1` |
| Incompatible pair | two binaries | `x[a] + x[b] <= 1` |
| Demand must be met | flow / quantity | `supply_to[i] >= demand[i]` |
| Demand may be unmet | nonneg slack | `served[i] + unmet[i] >= demand[i]` |
| Absolute deviation penalty | nonneg slack | `actual - target <= dev`, `target - actual <= dev` |
| Inventory balance | inventory variables | `inv[t+1] = inv[t] + inbound - outbound` |
| Station / storage upper bound | inventory variable | `inv[i,t] <= capacity[i]` |
| Cannot remove unavailable stock | move variable | `outbound[i,t] <= inv[i,t]` |
| Vehicle starts at depot | arc variables | `sum_j x[v, START, j] == use_vehicle[v]` |
| Vehicle ends at depot | arc variables | `sum_i x[v, i, END] == use_vehicle[v]` |
| Route continuity | arc variables | `incoming[v,i] == outgoing[v,i]` |
| Visit at most once (per vehicle) | arc variables | `outgoing[v,i] <= 1` |
| Split service allowed | arc / quantity variables | omit global single-visit; aggregate quantities over resources |
| Time window | arrival variable | `earliest[i] <= arrival[v,i] <= latest[i]` when visited |
| Travel time propagation | arc + arrival | `arrival[j] >= arrival[i] + service_time[i] + travel[i,j] - M(1 - x[i,j])` |
| Precedence | start / arrival variables | `start[b] >= finish[a]` |
| Route duration limit | arc variables | `sum travel[i,j] * x[v,i,j] <= max_duration[v]` |

## How to pick a row

1. Read the business rule from the problem statement verbatim.
2. Classify it into one of: **conservation**, **capacity**, **linking**,
   **assignment**, **sequence**, **compatibility**, **soft penalty**.
3. Match the row whose intent matches that classification — names in the
   table are reminders, not exhaustive labels.
4. If two rows could fit (e.g., demand-must-be-met vs demand-may-be-unmet),
   pick the *softer* form when the problem mentions a penalty for missing the
   target, and the *harder* form when the rule is described as a requirement.
5. Use the variable family in column 2 if you have not introduced an
   equivalent one already. Do not duplicate variables under a new name.
