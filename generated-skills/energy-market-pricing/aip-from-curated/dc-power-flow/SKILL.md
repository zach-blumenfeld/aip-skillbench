---
name: dc-power-flow
description: "DC power flow analysis for power systems. Use when computing power flows using DC approximation, building susceptance matrices, calculating line flows and loading percentages, or performing sensitivity analysis on transmission networks."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  DC power flow analysis for power systems — a linearized approximation of
  AC power flow suitable for economic dispatch and contingency analysis.
  Encodes the standard DC assumptions, susceptance-matrix construction with
  non-contiguous bus IDs, the power-balance equation, slack-bus pinning,
  line-flow and loading calculations, and the thermal-limit constraints
  used in DC optimal power flow (DC-OPF).

trigger_when:
  - Computing power flows using the DC approximation.
  - Building a susceptance (B) matrix from branch reactances.
  - Calculating line flows and loading percentages on a transmission network.
  - Performing sensitivity analysis on transmission networks.
  - Setting up DC-OPF thermal-limit constraints.

steps:
  - name: apply-dc-approximations
    description: |
      Apply the three DC simplifications so power flow depends only on bus
      angles (theta) and line reactances (X):
        1. Lossless lines — ignore resistance (R ~= 0).
        2. Flat voltage — all bus voltages = 1.0 pu.
        3. Small angles — sin(theta) ~= theta, cos(theta) ~= 1.

  - name: build-bus-number-mapping
    description: |
      Power system bus numbers may not be contiguous (e.g., case300 has
      non-sequential bus IDs). Always create a mapping from bus numbers to
      0-indexed array positions; never index branches as `br[0] - 1`.

      Code:
          bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}
          f = bus_num_to_idx[int(br[0])]  # NOT br[0] - 1
          t = bus_num_to_idx[int(br[1])]

  - name: build-susceptance-matrix
    description: |
      Build the B matrix from branch reactances using the bus number
      mapping. For each branch with reactance X != 0, set b = 1/X and
      accumulate +b on the diagonals B[f,f] and B[t,t] and -b on the
      off-diagonals B[f,t] and B[t,f]. Run `scripts/build_b_matrix.py` or
      inline:

          bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}
          B = np.zeros((n_bus, n_bus))

          for br in branches:
              f = bus_num_to_idx[int(br[0])]  # Map bus number to index
              t = bus_num_to_idx[int(br[1])]
              x = br[3]  # Reactance
              if x != 0:
                  b = 1.0 / x
                  B[f, f] += b
                  B[t, t] += b
                  B[f, t] -= b
                  B[t, f] -= b

  - name: write-power-balance
    description: |
      At each bus the power-balance equation is:

          Pg - Pd = B[i, :] @ theta

      Where:
        - Pg = generation at bus (pu)
        - Pd = load at bus (pu)
        - theta = vector of bus angles (radians)

  - name: pin-slack-bus
    description: |
      One bus must have theta = 0 as the angular reference. Find the slack
      bus (type column = 3) and pin its angle:

          slack_idx = None
          for i in range(n_bus):
              if buses[i, 1] == 3:
                  slack_idx = i
                  break
          constraints.append(theta[slack_idx] == 0)

  - name: store-branch-susceptances
    description: |
      Store branch susceptances when building constraints so line flows
      and thermal limits can reuse them:

          branch_susceptances = []
          for br in branches:
              x = br[3]
              b = 1.0 / x if x != 0 else 0
              branch_susceptances.append(b)

  - name: calculate-line-flows
    description: |
      Compute the flow on each branch from bus f to bus t using the bus
      number mapping. Susceptance = 1/X:

          f = bus_num_to_idx[int(br[0])]
          t = bus_num_to_idx[int(br[1])]
          b = 1.0 / br[3]
          flow_pu = b * (theta[f] - theta[t])
          flow_MW = flow_pu * baseMVA

  - name: calculate-loading-percentage
    description: |
      Convert line flow to a loading percentage of the thermal rating.
      `rating_MW` is branch column 5 (RATE_A):

          loading_pct = abs(flow_MW) / rating_MW * 100

  - name: enforce-line-flow-limits
    description: |
      For DC-OPF, enforce thermal limits as linear constraints
      (|flow| <= rating  ->  -rating <= flow <= rating):

          flow = b * (theta[f] - theta[t]) * baseMVA
          constraints.append(flow <= rate)
          constraints.append(flow >= -rate)

anti_patterns:
  - Indexing branch endpoints as `br[0] - 1`; bus numbers may not be contiguous (e.g., case300). Always resolve endpoints through `bus_num_to_idx`.
  - Forgetting to pin the slack bus angle to 0 — leaves the angular reference unconstrained and the system underdetermined.
  - Dividing by reactance without guarding X != 0 when building B or branch susceptances.
  - Including AC resistance terms in DC formulations — DC assumes lossless lines (R ~= 0).
```
