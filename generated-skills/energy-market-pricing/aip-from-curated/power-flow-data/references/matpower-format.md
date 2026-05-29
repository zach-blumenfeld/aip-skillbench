# MATPOWER format reference

Load via `scripts/network_utils.py::load_network`. All column indices below
are 0-based and refer to the numpy arrays that loader returns.

## baseMVA

System base power (MVA), typically 100. Per-unit conversions divide MW or
MVAr quantities by `baseMVA`. Always use the value from the file — do not
hardcode 100.

```
P_pu = P_MW   / baseMVA
Q_pu = Q_MVAr / baseMVA
S_pu = S_MVA  / baseMVA
```

## bus

Each row describes one bus.

| Col | Field    | Meaning                                              |
|-----|----------|------------------------------------------------------|
| 0   | bus_i    | Bus number (NOT a row index, NOT guaranteed contig.) |
| 1   | bus_type | 1=PQ load, 2=PV generator, 3=slack/ref, 4=isolated   |
| 2   | Pd       | Active load (MW)                                     |
| 3   | Qd       | Reactive load (MVAr)                                 |
| 4   | Gs       | Shunt conductance (MW @ V=1pu)                       |
| 5   | Bs       | Shunt susceptance (MVAr @ V=1pu)                     |
| 6   | area     | Area number                                          |
| 7   | Vm       | Voltage magnitude (pu)                               |
| 8   | Va       | Voltage angle (deg)                                  |
| 9   | baseKV   | Base voltage (kV)                                    |
| 10  | zone     | Loss zone                                            |
| 11  | Vmax     | Max voltage (pu)                                     |
| 12  | Vmin     | Min voltage (pu)                                     |

### Bus type semantics

| Code | Type  | Specified | Solved | Notes                              |
|------|-------|-----------|--------|------------------------------------|
| 1    | PQ    | P, Q      | V, θ   | Pure load bus                      |
| 2    | PV    | P, V      | Q, θ   | Generator bus, voltage controlled  |
| 3    | slack | V, θ=0    | P, Q   | Reference bus, balances power      |
| 4    | iso   | —         | —      | Isolated, ignore in flow equations |

Every DC-OPF needs exactly one bus with type code 3. Use
`network_utils.find_slack_bus`.

## gen

Each row describes one generator.

| Col | Field   | Meaning                                  |
|-----|---------|------------------------------------------|
| 0   | bus     | Bus number this generator connects to    |
| 1   | Pg      | Active dispatch (MW)                     |
| 2   | Qg      | Reactive dispatch (MVAr)                 |
| 3   | Qmax    | Reactive upper limit (MVAr)              |
| 4   | Qmin    | Reactive lower limit (MVAr)              |
| 5   | Vg      | Voltage setpoint (pu)                    |
| 6   | mBase   | Machine MVA base                         |
| 7   | status  | 1 in-service, 0 out                      |
| 8   | Pmax    | Active upper limit (MW)                  |
| 9   | Pmin    | Active lower limit (MW)                  |

Always map `gen[:,0]` through `bus_num_to_idx` before relating a generator
to its bus row.

## branch

Each row describes one transmission line or transformer.

| Col | Field    | Meaning                                          |
|-----|----------|--------------------------------------------------|
| 0   | fbus     | From bus number                                  |
| 1   | tbus     | To bus number                                    |
| 2   | r        | Resistance (pu on baseMVA)                       |
| 3   | x        | Reactance (pu on baseMVA)                        |
| 4   | b        | Total line charging susceptance (pu)             |
| 5   | rateA    | Long-term MVA rating (thermal limit)             |
| 6   | rateB    | Short-term MVA rating                            |
| 7   | rateC    | Emergency MVA rating                             |
| 8   | ratio    | Transformer off-nominal ratio (0 = line)         |
| 9   | angle    | Transformer phase shift (deg)                    |
| 10  | status   | 1 in-service, 0 out                              |
| 11  | angmin   | Minimum angle difference (deg)                   |
| 12  | angmax   | Maximum angle difference (deg)                   |

DC-OPF line flow constraints use `rateA` as the thermal capacity. Skip
rows where column 10 is 0.

## gencost

Polynomial or piecewise-linear cost curve per generator. One row per gen,
same order as `gen`.

| Col | Field    | Meaning                                          |
|-----|----------|--------------------------------------------------|
| 0   | model    | 1 = piecewise linear, 2 = polynomial             |
| 1   | startup  | Start-up cost ($)                                |
| 2   | shutdown | Shutdown cost ($)                                |
| 3   | n        | Number of cost-curve coefficients (or breakpoints) |
| 4+  | coeffs   | Polynomial: c_{n-1}, …, c_1, c_0 (highest first) |

For DC-OPF in this benchmark, expect `model == 2` with a quadratic or
linear cost curve. A linear curve has `n == 2` and columns `[4, 5]` =
`[c_1, c_0]`, so marginal cost is just `c_1` ($/MWh).

## reserve_capacity (PGLib extension)

Array of length `len(gen)`. Element `i` is the maximum reserve (MW) that
generator `i` can provide. Couples to dispatch via `Pg + r_i <= Pmax_i` in
standard capacity-coupling formulations.

## reserve_requirement (PGLib extension)

Scalar (MW). Minimum total system reserves required across all generators:
`sum_i r_i >= reserve_requirement`. Dual of this constraint is the
system-wide reserve clearing price.

Both reserve fields are extensions used by the PGLib benchmark; a generic
MATPOWER file may not have them. The loader returns `None` when absent.
