# MATPOWER-format Network Data (as used by this skill)

Network files follow the MATPOWER case convention (via the PGLib-OPF
benchmark). The JSON file at `network_path` has this shape:

```json
{
  "name": "...",
  "baseMVA": 100.0,
  "bus":     [[ ... ], ...],
  "gen":     [[ ... ], ...],
  "branch":  [[ ... ], ...],
  "gencost": [[ ... ], ...],
  "reserve_capacity":   [MW_per_gen, ...],
  "reserve_requirement": total_MW
}
```

All electrical quantities are in SI units in the arrays; the solver
converts to per-unit using `baseMVA` where needed.

Files can be large (100 K+ lines for realistic grids). Always parse
with `json.load`; never scan line-by-line with `sed`/`head`.

## bus row — columns

| Index | Field  | Description                             |
|-------|--------|-----------------------------------------|
| 0     | BUS_I  | Bus number (may be non-contiguous)      |
| 1     | TYPE   | 1=PQ load, 2=PV generator, 3=slack      |
| 2     | PD     | Real load (MW)                          |
| 3     | QD     | Reactive load (MVAr) — unused by DC-OPF |
| 9     | BASEKV | Nominal voltage                         |

Always build a `bus_num_to_idx` mapping; row position ≠ bus number.

## gen row — columns

| Index | Field    | Description                 |
|-------|----------|-----------------------------|
| 0     | GEN_BUS  | Bus number (1-indexed)      |
| 8     | PMAX     | Maximum real power (MW)     |
| 9     | PMIN     | Minimum real power (MW)     |

## branch row — columns

| Index | Field  | Description                 |
|-------|--------|-----------------------------|
| 0     | F_BUS  | From-bus number             |
| 1     | T_BUS  | To-bus number               |
| 2     | BR_R   | Resistance (pu) — unused    |
| 3     | BR_X   | Reactance (pu)              |
| 4     | BR_B   | Line charging (pu) — unused |
| 5     | RATE_A | Thermal limit (MVA)         |
| 10    | STATUS | 1=in service                |

## gencost row — polynomial type

| Index | Field    | Description                              |
|-------|----------|------------------------------------------|
| 0     | MODEL    | 2 = polynomial                           |
| 1     | STARTUP  | Startup cost ($)                         |
| 2     | SHUTDOWN | Shutdown cost ($)                        |
| 3     | NCOST    | Number of coefficients                   |
| 4+    | coeffs   | Highest-order first                      |

- NCOST=3 (quadratic): coeffs = [c2, c1, c0] → `c2*P² + c1*P + c0` ($/hr, P in MW)
- NCOST=2 (linear):    coeffs = [c1, c0]    → `c1*P + c0`
- NCOST=1 (constant):  coeffs = [c0]        → `c0`

Marginal cost at output P (quadratic): `2*c2*P + c1` ($/MWh).

## Reserve fields

- `reserve_capacity[i]` — upper bound on reserve each generator i can
  supply (MW).
- `reserve_requirement` — minimum total system reserves required (MW).
