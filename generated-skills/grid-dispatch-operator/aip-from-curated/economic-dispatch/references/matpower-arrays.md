# MATPOWER Array Reference

MATPOWER stores network data as numpy arrays. Columns referenced by this skill
are listed here. All indices are **0-indexed** into the numpy column, while
bus numbers (the values stored in those columns) are typically **1-indexed**
and may be non-contiguous.

## Generator array (`gen`)

| Index | Field | Description |
|-------|-------|-------------|
| 0 | GEN_BUS | Bus number this generator is connected to (1-indexed bus id) |
| 1 | PG | Real power output (MW) — usually overwritten by dispatch |
| 8 | PMAX | Maximum real power output (MW) |
| 9 | PMIN | Minimum real power output (MW) |

## Gencost array (`gencost`) — polynomial type 2

| Index | Field | Description |
|-------|-------|-------------|
| 0 | MODEL | 2 = polynomial cost |
| 1 | STARTUP | Startup cost ($) |
| 2 | SHUTDOWN | Shutdown cost ($) |
| 3 | NCOST | Number of polynomial coefficients |
| 4… | coeffs | Coefficients highest order first |

Layouts by NCOST:
- `NCOST == 3` (quadratic): `[c2, c1, c0]` at indices `4, 5, 6`
- `NCOST == 2` (linear):    `[c1, c0]`    at indices `4, 5`
- `NCOST == 1` (constant):  `[c0]`        at index `4`

Cost units: `C(P) = c2·P² + c1·P + c0` in `$/hr` where `P` is in MW.

## Bus array (`bus`)

| Index | Field | Description |
|-------|-------|-------------|
| 0 | BUS_I | Bus number (1-indexed, may be non-contiguous) |
| 2 | PD | Real power load demand at this bus (MW) |

## Bus indexing rule

Because MATPOWER bus numbers may be non-contiguous (e.g. 1, 2, 4, 7, …),
always build a mapping before indexing:

```python
bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}
gen_row_to_bus_row = [bus_num_to_idx[int(g[0])] for g in gens]
```

## Units convention

- Power values in arrays (PMAX, PMIN, PD, gencost) are in **MW** and **$/MW{·,²}·hr**.
- CVXPY variables are typically in **per-unit** (`Pg / baseMVA`).
- Convert before mixing into cost coefficients sized in `$/MW`:
  `Pg_MW = Pg * baseMVA`.

Mixing MW and per-unit silently is the most common bug in dispatch code.
