# MATPOWER JSON layout — fields the solver reads

Load with `json.load`. If the top level is `{"mpc": {...}}`, unwrap once.

| Key        | Shape                          | Notes |
|------------|--------------------------------|-------|
| `baseMVA`  | scalar                         | Apparent-power base (default 100). Multiplies p.u. flows back to MW. |
| `bus`      | list of rows                   | One per bus. Columns: `[bus_i, type, Pd, Qd, Gs, Bs, area, Vm, Va, baseKV, zone, Vmax, Vmin]`. |
| `gen`      | list of rows                   | One per generator unit. Columns: `[bus, Pg, Qg, Qmax, Qmin, Vg, mBase, status, Pmax, Pmin, …]`. |
| `branch`   | list of rows                   | One per branch. Columns: `[fbus, tbus, r, x, b, rateA, rateB, rateC, ratio, angle, status, angmin, angmax]`. |
| `gencost`  | list of rows (length = n_gen)  | One per generator. Columns: `[model, startup, shutdown, n, c_{n-1}, …, c_0]`. |
| `reserves` | optional dict                  | PYPOWER-style block: `{ "req": MW (scalar or list), "cost": [$/MWh per gen], "qty": [MW per gen], "zones": [...] }`. |

## Field interpretation rules used by the solver

- **Bus `type`.** `1 = PQ`, `2 = PV`, `3 = Slack/reference`, `4 = Isolated`. The solver picks the first bus with `type==3` as the angle reference; if none exists, it falls back to bus index 0.
- **Generator/branch `status`.** Rows with `status != 1` are ignored. Apply this filter *before* indexing gencost — the solver iterates aligned rows.
- **`rateA == 0`** means "unlimited" in MATPOWER. The solver substitutes `1e9` MW and emits a warning if a counterfactual override tries to scale an unlimited line.
- **Reactance `x` of zero** would make the susceptance infinite. The solver guards against this by clamping `|x| < 1e-9` to `1e-9`.
- **`gencost` model.** `model=2` is polynomial with coefficients listed **highest order first**: `c_{n-1}, c_{n-2}, …, c_0`. `model=1` is piecewise linear with `(x0, y0, x1, y1, …)` breakpoints.
- **Quadratic generator cost** is linearized at the midpoint of `[Pmin, Pmax]` to keep the LP clean. For LMPs to be accurate when generators dispatch far from midpoint, re-linearize at the solution and re-solve — but for most test networks the midpoint approximation is within rounding.

## Reserve defaults when `reserves` is absent

The instruction prescribes "Spinning Reserve Requirements with Standard Capacity Coupling" but the bare MATPOWER format does not carry reserve data. The solver applies these defaults:

- **Requirement (`R_req`)** = largest in-service generator's `Pmax` (N-1 contingency convention).
- **Per-generator reserve cap** = `Pmax − Pmin` (full ramp range).
- **Per-generator reserve offer cost** = `0.0`.

If the agent has reason to use different defaults, pass `--reserve-req <MW>` on the CLI. Document the choice in the report's preamble or in your message to the user.

## Common gotchas

- Bus IDs are **not** dense — they may be `1, 2, 3, …` or sparse like `1, 4, 64, 1501`. The solver builds a `bus_idx` map and never assumes contiguity. When you read or write LMPs, use the bus *number*, not the array index.
- Generator rows and gencost rows must align after filtering by `status`. Some networks carry reactive-power costs as a second block (`gencost` length = `2 * n_gen`). The solver reads only the first `n_gen` rows; this matches DC-OPF (no reactive dispatch).
- `branch` direction is `from → to`. Power can flow in either direction; the sign of computed flow reflects this. When the task names a line by `from, to`, treat either orientation as a match (the solver does).
- A network may contain parallel branches between the same pair of buses (different impedances, different ratings). A counterfactual override that names only `(from, to)` applies to **all** of them; use `--branch-index N` to target one row specifically.
