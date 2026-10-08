# DC-OPF with reserves — formulation and data reference

Load this when you need to adapt or audit `scripts/solve_dispatch.py`, hand-check a number,
or the task asks for a quantity the script does not report.

## Network file (MATPOWER / PGLib-OPF JSON)

Top-level keys: `baseMVA`, `bus`, `gen`, `branch`, `gencost`, optional `reserve_capacity`
(list, MW per generator, same order as `gen`), `reserve_requirement` (float, MW system
total), `column_info`. Files are multi-MB (100K+ lines): parse with `json.load`, never page
through with `sed`/`head`. Quick summary first: counts of bus/gen/branch and total load
`sum(b[2] for b in bus)`. (`wc -l` / `du -h` if you only need size.)

Columns (0-indexed):

| array | idx | field |
|---|---|---|
| bus | 0 | BUS_I bus number (may be non-contiguous) |
| bus | 1 | BUS_TYPE 1=PQ load (P,Q given; V,θ solved), 2=PV generator (P,V given; Q,θ solved), 3=slack (V, θ=0 given; P,Q solved) |
| bus | 2 | PD real demand MW (3 QD MVAr, 4 GS, 5 BS shunt) |
| gen | 0 | GEN_BUS bus number |
| gen | 7 | GEN_STATUS 1 in service |
| gen | 8 / 9 | PMAX / PMIN MW (PMIN may be negative) |
| branch | 0 / 1 | F_BUS / T_BUS bus numbers |
| branch | 2 / 3 / 4 | R, X, line-charging B (pu) |
| branch | 5 | RATE_A long-term MVA rating (used as MW limit; 0 = unlimited) |
| branch | 10 | BR_STATUS 1 in service |
| gencost | 0..3 | MODEL (2 polynomial, 1 piecewise linear), STARTUP, SHUTDOWN, NCOST |
| gencost | 4+ | coefficients, highest order first: NCOST=3 → c2,c1,c0 at 4,5,6; NCOST=2 → c1,c0 at 4,5 |

Per-unit: `P_pu = P_MW / baseMVA` (likewise Q, S). Cost uses P in MW:
`C = c2·P² + c1·P + c0` $/hr. Startup/shutdown costs are not part of hourly dispatch cost.

**Always map bus numbers to positions**: `bus_num_to_idx = {int(bus[i][0]): i ...}`; use it
for branch endpoints and generator buses (never `bus_number - 1`). Generators at a bus:
those whose mapped GEN_BUS equals the bus index. Slack: first bus with type 3.

## DC approximation

Lossless (R≈0), flat voltage (|V|=1 pu), small angles (sinθ≈θ, cosθ≈1). Flows depend only
on angles θ (radians) and reactances X.

- Branch susceptance `b = 1/X` (0 if X=0). Store per branch.
- B matrix: `B[f,f]+=b; B[t,t]+=b; B[f,t]-=b; B[t,f]-=b` (see `source/dc-power-flow/scripts/build_b_matrix.py`).
- Nodal balance at every bus (pu): `Pg_bus − Pd_bus = B[i,:] @ θ`; θ_slack = 0.
- Flow f→t: `flow_MW = b·(θf − θt)·baseMVA`.
- Loading: `loading_pct = |flow_MW| / RATE_A · 100` (0 when RATE_A is 0).
- Thermal limit (OPF): `−RATE_A ≤ flow_MW ≤ RATE_A`.

## Economic dispatch / DC-OPF

Variables Pg (gen outputs), optional Rg (reserves, MW), θ.

- Objective: Σ cost_i(Pg_i) handling NCOST per row (≥3 quadratic, 2 linear, 1 constant).
- Limits: PMIN ≤ Pg ≤ PMAX.
- Balance: copper-plate ED uses `Σ Pg = Σ PD`; network DC-OPF uses nodal balance + line limits instead.
- Reserves (when required): `Rg ≥ 0`, `Rg_i ≤ reserve_capacity_i`, `Pg_i + Rg_i ≤ PMAX_i`
  (capacity coupling), `Σ Rg ≥ reserve_requirement`.
- Solver: CLARABEL (robust interior point). OSQP can fail on ill-conditioned DC-OPF with
  reserves. All-linear costs make this an LP (HiGHS also works).

## Reported quantities

- generator_dispatch per gen: `id` (1-based position), `bus` (bus number), `output_MW`,
  `reserve_MW`, `pmax_MW`, rounded to 2 dp.
- totals: `cost_dollars_per_hour` (objective value), `load_MW` (Σ PD), `generation_MW`
  (Σ Pg), `reserve_MW` (Σ Rg).
- operating margin: `Σ (PMAX − Pg − Rg)` — uncommitted headroom beyond energy and reserves.
- most loaded lines: branches sorted by loading_pct, descending.
- marginal cost of a unit: `2·c2·P + c1` $/MWh. This is the unit's own incremental cost. A unit
  at PMAX or PMIN does not set the price; the system lambda (copper-plate) is the marginal cost
  of the unit(s) strictly between their limits, and under network constraints prices differ by
  bus (LMPs). If a task asks for "the marginal cost" of a unit at a limit, report its own
  incremental cost and say it is at a limit (give the system lambda too).
- parallel circuits share from/to bus numbers; identify branches by 1-based row
  (`branch_index` in the script's output).

## Modelling conventions the script fixes (and why)

- Out-of-service generators/branches (status 0) are forced to 0 / dropped. PGLib files
  normally have all in service.
- Transformer TAP/SHIFT and bus GS are ignored by default, matching the curated sources'
  `b = 1/X` model. If a task explicitly demands MATPOWER's exact DC model, re-run with
  `--matpower-taps` (or state key `matpower_taps: true`): b = 1/(X·TAP) with TAP 0 → 1, and
  flow = b·(θf − θt − SHIFT_rad). On the PGLib 2869-bus file this lowers cost by about 0.01 %.
- Reserves carry no cost in the sources' model, so the script adds a 1e-6 $/MW tie-breaker
  (excluded from the reported cost). Σ Rg then equals the requirement, which makes the
  operating margin Σ PMAX − load − R unique. The per-unit reserve split can still vary.
- Solver: HiGHS first when every cost is linear (an LP; exact vertex), otherwise CLARABEL.
- Many lines can tie at 100 % loading; ties are ordered by branch row, and the script reports
  `n_lines_tied_at_top_loading`.
