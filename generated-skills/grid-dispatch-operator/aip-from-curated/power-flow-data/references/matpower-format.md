# MATPOWER Network Data — Column Reference

Network data follows the MATPOWER format, a standard for power-system test cases. Files in this task derive from the PGLib-OPF benchmark library (`github.com/power-grid-lib/pglib-opf`).

Top-level JSON keys: `baseMVA`, `bus`, `gen`, `branch`, `gencost`, and optionally `reserve_capacity` / `reserve_requirement`. Each of `bus`, `gen`, `branch`, `gencost` is a 2-D array (list of rows).

## Bus types

Power-system buses are classified by which quantities are specified versus solved:

| Type  | Code | Specified  | Solved | Description                          |
|-------|------|------------|--------|--------------------------------------|
| Slack | 3    | V, θ=0     | P, Q   | Reference bus, balances power        |
| PV    | 2    | P, V       | Q, θ   | Generator bus with voltage control   |
| PQ    | 1    | P, Q       | V, θ   | Load bus                             |

The bus-type code lives in column 1 of each `bus` row. See `find_slack_bus` in `scripts/network_utils.py`.

## Per-unit system

All electrical quantities are normalized to base values. `baseMVA` is typically 100.

```
P_pu = P_MW / baseMVA
Q_pu = Q_MVAr / baseMVA
S_pu = S_MVA / baseMVA
```

Helpers: `to_pu(value, baseMVA)` and `from_pu(value, baseMVA)` in `scripts/network_utils.py`.

## Bus row columns (relevant subset)

| Col | Name | Description                                |
|-----|------|--------------------------------------------|
| 0   | bus_i | Bus number (may be non-contiguous — map it) |
| 1   | type  | 1=PQ, 2=PV, 3=slack                        |
| 2   | Pd    | Real power demand (MW)                     |
| 3   | Qd    | Reactive power demand (MVAr)               |

Bus numbers are NOT guaranteed contiguous. Always build a mapping `bus_number -> 0-indexed position` before joining gens/branches to buses. See `bus_num_to_idx`.

## Branch row columns (relevant subset)

| Col | Name        | Description                       |
|-----|-------------|-----------------------------------|
| 0   | fbus        | "From" bus number                 |
| 1   | tbus        | "To" bus number                   |
| 2   | r           | Resistance (pu)                   |
| 3   | x           | Reactance (pu)                    |
| 4   | b           | Total line charging susceptance (pu) |
| 5   | rateA       | MVA rating (long-term limit)      |
| 10  | status      | 1 = in service, 0 = out of service |

See `get_branch_info` in `scripts/network_utils.py`.

## Reserve data (optional)

Network files may include operating-reserve parameters:

| Field                 | Type   | Description                                          |
|-----------------------|--------|------------------------------------------------------|
| `reserve_capacity`    | array  | Max reserve each generator can provide (MW), one per gen |
| `reserve_requirement` | float  | Minimum total system reserves required (MW)          |

`load_network` returns these only when present in the input JSON.
