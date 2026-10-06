# MATPOWER network.json format reference

Network data uses the MATPOWER case format (via PGLib-OPF benchmark cases,
`github.com/power-grid-lib/pglib-opf`). Load with `json.load`; the files
can run into tens of MB, so never `cat`/`head`/`sed` them.

```python
import json
with open('network.json') as f:
    data = json.load(f)
```

## Top-level keys
| Key | Type | Description |
|-----|------|-------------|
| `baseMVA` | float | Per-unit base power (typically 100). |
| `bus` | list[list] | Bus rows (see below). |
| `gen` | list[list] | Generator rows. |
| `branch` | list[list] | Transmission line / transformer rows. |
| `gencost` | list[list] | Generator cost polynomials (MODEL=2). |
| `reserve_capacity` | list[float] | Max reserve MW each generator can hold. |
| `reserve_requirement` | float | System-wide minimum reserve MW. |

## Per-unit conversions
```
P_pu = P_MW / baseMVA
Q_pu = Q_MVAr / baseMVA
```

## Bus row (columns used)
| Idx | Field | Notes |
|-----|-------|-------|
| 0 | BUS_I | Bus number (may be non-contiguous — build a mapping). |
| 1 | BUS_TYPE | 1=PQ load, 2=PV gen, 3=slack reference. |
| 2 | Pd | Real power demand in MW. |

## Generator row (columns used)
| Idx | Field | Notes |
|-----|-------|-------|
| 0 | GEN_BUS | Bus number this generator sits on. |
| 8 | PMAX | Max real power output (MW). |
| 9 | PMIN | Min real power output (MW). |

## Branch row (columns used)
| Idx | Field | Notes |
|-----|-------|-------|
| 0 | F_BUS | From-bus number. |
| 1 | T_BUS | To-bus number. |
| 2 | BR_R | Resistance (pu) — ignored in DC approx. |
| 3 | BR_X | Reactance (pu). Susceptance = 1/X. |
| 4 | BR_B | Line charging susceptance (pu). |
| 5 | RATE_A | MVA thermal limit — the long-term rating. |
| 10 | BR_STATUS | 1=in service, 0=out. |

## Gencost row (MODEL=2 polynomial)
| Idx | Field | Notes |
|-----|-------|-------|
| 0 | MODEL | 2 = polynomial. |
| 1 | STARTUP | $. |
| 2 | SHUTDOWN | $. |
| 3 | NCOST | Number of coefficients. |
| 4+ | coeffs | Highest order first: `[c2, c1, c0]` for quadratic. |

`Cost(P_MW) = c2 * P^2 + c1 * P + c0` ($/hr).

## Bus-number mapping
Bus IDs are not guaranteed to be 1..n. Always build:
```python
bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}
f = bus_num_to_idx[int(branch_row[0])]
```
Never do `branch_row[0] - 1`.

## Slack bus
Exactly one bus has `BUS_TYPE == 3`. Its angle is fixed to 0 in the DC-OPF
constraint set — the reference for every other θ.

## Typical generator cost ranges
| Type | c2 ($/MW²·hr) | c1 ($/MWh) | c0 ($/hr) |
|------|---------------|------------|-----------|
| Nuclear | 0.001 | 5–10 | 500–1000 |
| Coal | 0.005–0.01 | 15–25 | 200–400 |
| Gas CCGT | 0.01–0.02 | 25–40 | 100–200 |
| Gas Peaker | 0.02–0.05 | 50–80 | 50–100 |

Marginal cost at output `P`: `2*c2*P + c1`.
