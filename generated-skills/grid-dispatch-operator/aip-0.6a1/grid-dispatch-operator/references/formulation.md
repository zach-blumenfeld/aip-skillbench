# DC-OPF with spinning reserves: data, model, report

Everything `scripts/dispatch.py` implements, for diagnosing an infeasible/failed solve or
explaining a result. Network data is MATPOWER format (PGLib-OPF benchmark cases).

## Reading the file

Network JSON can be multi-MB (100K+ lines). Never page it with `sed`/`head`/`cat`; load it
with `json.load` and print a summary (bus/gen/branch counts, total load).

## MATPOWER columns (0-indexed)

**bus**: 0 BUS_I (bus number, may be non-contiguous), 1 BUS_TYPE (1 PQ load bus, 2 PV
generator bus with voltage control, 3 slack/reference: θ = 0, balances power), 2 PD (MW),
3 QD, 4 GS, 5 BS, 6 AREA, 7 VM, 8 VA, 9 BASE_KV, 10 ZONE, 11 VMAX, 12 VMIN.

**gen**: 0 GEN_BUS (bus number), 1 PG, 2 QG, 3 QMAX, 4 QMIN, 5 VG, 6 MBASE,
7 GEN_STATUS (1 in service), 8 PMAX (MW), 9 PMIN (MW; may be negative).

**branch**: 0 F_BUS, 1 T_BUS, 2 BR_R, 3 BR_X (pu), 4 BR_B (line charging), 5 RATE_A (MVA,
long-term; 0 = unlimited), 6 RATE_B, 7 RATE_C, 8 TAP, 9 SHIFT, 10 BR_STATUS (1 in
service), 11 ANGMIN, 12 ANGMAX.

**gencost** (one row per generator, same order as gen):
- MODEL 2 polynomial: `[2, STARTUP, SHUTDOWN, NCOST, c(n-1) … c1, c0]`, highest order
  first. NCOST 3 → `[c2, c1, c0]` at indices 4–6; NCOST 2 → `[c1, c0]` at 4–5.
  Cost = c2·P² + c1·P + c0 ($/hr), P in **MW** (not per-unit). c0 is the no-load cost
  and is part of the total. Example `[2,0,0,3,0.01,20,100]` at 50 MW → $1125/hr.
  Marginal cost = 2·c2·P + c1 ($/MWh).
- MODEL 1 piecewise linear: `[1, STARTUP, SHUTDOWN, N, P1, C1, …, PN, CN]` breakpoints;
  modelled as the convex epigraph of its segments.
- Typical magnitudes (sanity check): nuclear c2≈0.001, c1 5–10, c0 500–1000; coal
  c2 0.005–0.01, c1 15–25, c0 200–400; gas CCGT c2 0.01–0.02, c1 25–40, c0 100–200;
  gas peaker c2 0.02–0.05, c1 50–80, c0 50–100.

**Reserve fields** (top-level): `reserve_capacity` (list, MW per generator, r̄ᵢ),
`reserve_requirement` (float, MW, R).

**Per-unit**: P_pu = P_MW / baseMVA (typically 100). Reserves stay in MW.

## Model

Bus number → row index map `{int(bus[i,0]): i}`; use it for every branch endpoint and
generator bus (never `bus_number - 1`).

DC approximations: lossless (R ignored), |V| = 1 pu, small angles (sin θ ≈ θ, cos θ ≈ 1);
flow depends only on angles and reactance. Branch susceptance b = 1/x (x = 0 → b = 0).
B matrix: `B[f,f] += b; B[t,t] += b; B[f,t] -= b; B[t,f] -= b`.

Variables: Pgᵢ (MW), Rgᵢ (MW), θ (rad). Minimize Σ costᵢ(Pgᵢ) subject to
- nodal balance at every bus: Σ_{g at bus} Pg − PD = baseMVA · (B θ)
- θ_slack = 0 (first bus with type 3)
- Pminᵢ ≤ Pgᵢ ≤ Pmaxᵢ
- 0 ≤ Rgᵢ ≤ r̄ᵢ; Pgᵢ + Rgᵢ ≤ Pmaxᵢ (standard capacity coupling); Σ Rgᵢ ≥ R
- −RATE_A ≤ baseMVA · b·(θ_f − θ_t) ≤ RATE_A for branches with RATE_A > 0

Solver: CLARABEL (robust interior point for QP with network + reserves); OSQP can fail on
these ill-conditioned problems. Fallbacks: HIGHS, OSQP, SCS.

Copper-plate (no network) dispatch replaces nodal balance with Σ Pg = Σ PD; never use it
when the task asks for DC power balance at each bus.

## Report fields

- `generator_dispatch[i]`: `id` = i+1 (gen row order), `bus` = GEN_BUS, `output_MW` = Pg,
  `reserve_MW` = Rg, `pmax_MW` = PMAX; values rounded to 2 dp.
- `totals`: `cost_dollars_per_hour` (Σ cost incl. c0), `load_MW` (Σ PD),
  `generation_MW` (Σ Pg), `reserve_MW` (Σ Rg).
- `most_loaded_lines`: top 3 branches by `loading_pct = |flow_MW| / RATE_A · 100`
  (RATE_A = 0 → 0 %), `from`/`to` are bus numbers.
- `operating_margin_MW` = Σ (Pmax − Pg − Rg): uncommitted headroom beyond energy and
  reserves.

Reserves carry no cost, so the split of reserve above R among generators (and therefore
`reserve_MW` and `operating_margin_MW` in the last few MW) is not unique; any split that
satisfies the constraints is optimal.

## Infeasibility causes (for diagnosis)

- Σ Pmin > load (over-committed minimum generation) or load > Σ Pmax.
- Σ min(r̄ᵢ, Pmaxᵢ − Pminᵢ) < R (reserve capability short), or Σ Pmax < load + R.
- Network: thermal limits trap cheap/needed generation (island, radial overloaded line,
  load bus fed only by low-rated branches). Find it by relaxing RATE_A (e.g. ×1.5, or
  dropping limits) and re-solving; if that solves, congestion is the cause.
- Data: missing/negative reserve fields, gencost rows not matching gen rows, no slack bus,
  non-convex cost (c2 < 0).
