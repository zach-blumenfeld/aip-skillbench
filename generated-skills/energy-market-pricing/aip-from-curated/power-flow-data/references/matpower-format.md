# MATPOWER-Format Reference

Network data follows the MATPOWER format used by the PGLib-OPF benchmark library
(github.com/power-grid-lib/pglib-opf). The JSON encodes each MATPOWER matrix as
a 2-D array; columns are positional, indexed below.

## Bus Types

Power system buses are classified by what is specified vs. what the solver
returns:

| Type  | Code | Specified | Solved | Description                          |
|-------|------|-----------|--------|--------------------------------------|
| Slack | 3    | V, θ=0    | P, Q   | Reference bus; balances power        |
| PV    | 2    | P, V      | Q, θ   | Generator bus with voltage control   |
| PQ    | 1    | P, Q      | V, θ   | Load bus                             |

The slack bus is column 1 (0-indexed: `bus[i, 1]`). Exactly one slack bus is
expected per network.

## Per-Unit System

All electrical quantities are normalized to base values:

```
baseMVA = 100  # typical system base power, taken from data['baseMVA']

P_pu = P_MW   / baseMVA
Q_pu = Q_MVAr / baseMVA
S_pu = S_MVA  / baseMVA
```

Mixing MW with per-unit values is a common bug — always convert first.

## Bus Columns (data['bus'])

| Col | Field | Description                       |
|-----|-------|-----------------------------------|
| 0   | num   | Bus number (not necessarily contiguous, not 0-indexed) |
| 1   | type  | 1=PQ, 2=PV, 3=slack               |
| 2   | Pd    | Active load (MW)                  |
| 3   | Qd    | Reactive load (MVAr)              |
| 4   | Gs    | Shunt conductance                 |
| 5   | Bs    | Shunt susceptance                 |
| 6   | area  | Area number                       |
| 7   | Vm    | Voltage magnitude (pu)            |
| 8   | Va    | Voltage angle (deg)               |
| 9   | baseKV| Base voltage (kV)                 |
| 10  | zone  | Loss zone                         |
| 11  | Vmax  | Max voltage (pu)                  |
| 12  | Vmin  | Min voltage (pu)                  |

## Generator Columns (data['gen'])

| Col | Field | Description                |
|-----|-------|----------------------------|
| 0   | bus   | Bus number (map via bus_num_to_idx) |
| 1   | Pg    | Active dispatch (MW)       |
| 2   | Qg    | Reactive dispatch (MVAr)   |
| 3   | Qmax  | Max reactive (MVAr)        |
| 4   | Qmin  | Min reactive (MVAr)        |
| 5   | Vg    | Voltage setpoint (pu)      |
| 6   | mBase | Generator MVA base         |
| 7   | status| 1=in-service, 0=out        |
| 8   | Pmax  | Max active (MW)            |
| 9   | Pmin  | Min active (MW)            |

## Branch Columns (data['branch'])

| Col | Field      | Description                          |
|-----|------------|--------------------------------------|
| 0   | from_bus   | From-end bus number (map it)         |
| 1   | to_bus     | To-end bus number (map it)           |
| 2   | r          | Resistance (pu)                      |
| 3   | x          | Reactance (pu)                       |
| 4   | b          | Total line charging susceptance (pu) |
| 5   | rateA      | Long-term MVA limit                  |
| 6   | rateB      | Short-term MVA limit                 |
| 7   | rateC      | Emergency MVA limit                  |
| 8   | tap        | Off-nominal turns ratio (0 = line)   |
| 9   | shift      | Phase-shift angle (deg)              |
| 10  | status     | 1=in-service, 0=out                  |
| 11  | angmin     | Minimum angle difference (deg)       |
| 12  | angmax     | Maximum angle difference (deg)       |

## Gencost Columns (data['gencost'])

Polynomial cost model (model code 2):

| Col | Field    | Description                          |
|-----|----------|--------------------------------------|
| 0   | model    | 1=piecewise-linear, 2=polynomial     |
| 1   | startup  | Startup cost ($)                     |
| 2   | shutdown | Shutdown cost ($)                    |
| 3   | n        | Number of polynomial coefficients    |
| 4+  | coefs    | Highest-order first (e.g. quadratic: c2, c1, c0) |

## Reserve Fields (optional)

Network files may include operating-reserve parameters:

| Field                | Type  | Description                                     |
|----------------------|-------|-------------------------------------------------|
| reserve_capacity     | array | Maximum reserve each generator can provide (MW) — `r_bar` per gen |
| reserve_requirement  | float | Minimum total system reserves required (MW) — `R` system-wide      |
