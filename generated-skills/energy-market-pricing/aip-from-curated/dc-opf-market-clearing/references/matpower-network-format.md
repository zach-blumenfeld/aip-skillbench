# MATPOWER network.json format (PGLib-OPF derived)

Load with `json.load` (fast even for multi-MB files). Never page through the file with sed/head/cat:
realistic grids are 100K+ lines. Quick summary first:

```python
import json
data = json.load(open('network.json'))
print(len(data['bus']), len(data['gen']), len(data['branch']), sum(b[2] for b in data['bus']))
```
(`wc -l` / `du -h` if you only need the size.)

Top-level keys: `baseMVA` (typically 100), `bus`, `gen`, `branch`, `gencost`, optional
`reserve_capacity` (list, MW per generator, r_bar) and `reserve_requirement` (float, MW, system R),
optional `column_info` (column descriptions).

## bus (0-based columns)
| idx | field | notes |
|---|---|---|
| 0 | BUS_I | bus number (may be non-contiguous: always map number -> row index) |
| 1 | BUS_TYPE | 1 = PQ (load: P,Q given; V,theta solved), 2 = PV (generator: P,V given; Q,theta solved), 3 = slack (V, theta=0 given; P,Q solved; reference) |
| 2 | PD | real demand, MW (negative = net injection) |
| 3 | QD | reactive demand, MVAr |
| 4, 5 | GS, BS | shunt conductance / susceptance |
| 6 | BUS_AREA | |
| 7, 8 | VM, VA | voltage magnitude (pu) / angle (deg) |
| 9 | BASE_KV | |
| 10 | ZONE | |
| 11, 12 | VMAX, VMIN | pu |

## gen
| idx | field |
|---|---|
| 0 | GEN_BUS (bus number) |
| 1, 2 | PG, QG (initial point, not the dispatch) |
| 3, 4 | QMAX, QMIN |
| 5 | VG |
| 6 | MBASE |
| 7 | GEN_STATUS (1 in service, 0 out) |
| 8 | PMAX (MW) |
| 9 | PMIN (MW) |

## branch
| idx | field |
|---|---|
| 0, 1 | F_BUS, T_BUS (bus numbers) |
| 2 | BR_R resistance pu (ignored in DC) |
| 3 | BR_X reactance pu (susceptance b = 1/x) |
| 4 | BR_B line charging pu |
| 5 | RATE_A long-term rating, MVA, used as the MW flow limit (0 = unlimited) |
| 6, 7 | RATE_B, RATE_C |
| 8 | TAP ratio (0 = line) |
| 9 | SHIFT phase shift, deg |
| 10 | BR_STATUS |
| 11, 12 | ANGMIN, ANGMAX deg |

Parallel circuits between the same bus pair are common; they are separate rows.

## gencost
`[MODEL, STARTUP, SHUTDOWN, NCOST, coeffs...]`. MODEL 2 = polynomial, coefficients highest order
first: NCOST=3 -> [c2, c1, c0] at idx 4,5,6; NCOST=2 -> [c1, c0] at idx 4,5; NCOST=1 -> constant.
MODEL 1 = piecewise linear with NCOST breakpoints `P1, C1, ..., Pn, Cn`. See `cost-functions.md`.

## Per-unit
`P_pu = P_MW / baseMVA`, `Q_pu = Q_MVAr / baseMVA`, `S_pu = S_MVA / baseMVA`.

## Helpers
```python
bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}
gen_bus = [bus_num_to_idx[int(g[0])] for g in gens]         # NOT g[0] - 1
f = bus_num_to_idx[int(br[0])]; t = bus_num_to_idx[int(br[1])]

def get_generators_at_bus(gens, bus_idx, bus_num_to_idx):
    return [i for i, g in enumerate(gens) if bus_num_to_idx[int(g[0])] == bus_idx]

def find_slack_bus(buses):
    return next((i for i, b in enumerate(buses) if b[1] == 3), None)

def get_branch_info(branch, bus_num_to_idx):
    return {'from_bus': bus_num_to_idx[int(branch[0])], 'to_bus': bus_num_to_idx[int(branch[1])],
            'resistance': branch[2], 'reactance': branch[3], 'susceptance': branch[4],
            'rating': branch[5], 'in_service': branch[10] == 1}

total_load_MW = sum(bus[2] for bus in buses)
```
