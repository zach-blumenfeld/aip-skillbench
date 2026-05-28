---
name: power-flow-data
description: "Parse and navigate MATPOWER-format power-system network data (PGLib-OPF JSON): load bus / gen / branch / gencost / reserve arrays, map non-contiguous bus numbers, identify slack and PV buses, look up generators on a bus, extract branch parameters, compute total load, convert MW <-> per-unit. Use when reading a network.json for power flow, OPF, unit-commitment, or reserves analysis."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+ with numpy. Network files follow the MATPOWER / PGLib-OPF JSON convention.
---

```yaml
purpose: >
  Plumbing for MATPOWER-format power system network data (PGLib-OPF JSON):
  load arrays, handle non-contiguous bus numbering, find the slack bus,
  list generators on a bus, extract per-branch parameters, sum total load,
  and convert MW <-> per-unit. The skill keeps the format conventions and
  helper functions in one place so an OPF / unit-commitment task does not
  re-derive them from the raw JSON.

trigger_when:
  - Loading a MATPOWER / PGLib-OPF network JSON.
  - Examining `bus`, `gen`, `branch`, `gencost`, `reserve_capacity`, or `reserve_requirement` arrays.
  - Identifying bus types (slack=3 / PV=2 / PQ=1) or finding the slack bus.
  - Mapping bus numbers to 0-indexed array positions (bus numbers are NOT contiguous in real grids).
  - Listing which generators are attached to a bus, or which branches connect two buses.
  - Computing total system load, or converting between MW and per-unit.
  - Reading reserve fields (`reserve_capacity` per-gen, `reserve_requirement` system-wide).

do_not_use_when:
  - Solving the OPF / DC-OPF / unit-commitment optimization itself — this skill is data plumbing only.
  - The data is not MATPOWER format (e.g. PSS/E RAW, CIM, GridLAB-D, OpenDSS).

scope_and_approval: >
  Read-only against the network JSON. Functions return values; nothing is written
  to disk and no external services are called. Safe to invoke without confirmation.

steps:
  - name: load-network
    description: Parse the network JSON with `json.load` (fast even for multi-MB files) into numpy arrays plus optional reserve fields.
    script: scripts/power_flow_data.py
    inputs:
      - name: filepath
        type: string
        description: Path to the MATPOWER-format JSON.
    outputs:
      - name: network
        type: object
        description: dict with baseMVA, bus, gen, branch, gencost, and (when present) reserve_capacity, reserve_requirement.

  - name: summarize-network
    description: Print baseMVA, bus/gen/branch counts, and total load — sanity check immediately after load before touching the data further.
    script: scripts/power_flow_data.py
    depends_on: [load-network]
    inputs:
      - name: network
        type: object
    outputs:
      - name: summary
        type: object

  - name: build-bus-mapping
    description: Build `bus_num_to_idx` (bus_number -> 0-indexed row). Required before any per-bus lookup because bus numbers are not contiguous and are not 0-indexed.
    script: scripts/power_flow_data.py
    depends_on: [load-network]
    inputs:
      - name: network
        type: object
    outputs:
      - name: bus_num_to_idx
        type: object
        description: dict[int, int] keyed by raw bus number.

  - name: find-slack-bus
    description: Return the 0-indexed slack bus (where `bus[i, 1] == 3`).
    script: scripts/power_flow_data.py
    depends_on: [load-network]
    inputs:
      - name: network
        type: object
    outputs:
      - name: slack_idx
        type: integer
        nullable: true

  - name: get-generators-at-bus
    description: List generator indices attached to a given 0-indexed bus (uses the bus mapping to compare gen[k, 0] correctly).
    script: scripts/power_flow_data.py
    depends_on: [build-bus-mapping]
    inputs:
      - name: network
        type: object
      - name: bus_num_to_idx
        type: object
      - name: bus_idx
        type: integer
    outputs:
      - name: gen_indices
        type: list[integer]

  - name: get-branch-info
    description: Extract one branch's parameters — from_bus, to_bus (both 0-indexed), R, X, B in pu, MVA rating, and the `status == 1` in-service flag.
    script: scripts/power_flow_data.py
    depends_on: [build-bus-mapping]
    inputs:
      - name: network
        type: object
      - name: bus_num_to_idx
        type: object
      - name: branch_idx
        type: integer
    outputs:
      - name: branch_info
        type: object

  - name: total-load
    description: Sum the bus Pd column (column 2) to get total system load in MW.
    script: scripts/power_flow_data.py
    depends_on: [load-network]
    inputs:
      - name: network
        type: object
    outputs:
      - name: total_mw
        type: float

  - name: pu-conversion
    description: Convert MW <-> per-unit on the system MVA base via `mw_to_pu(value, baseMVA)` / `pu_to_mw(value, baseMVA)`. Use whenever mixing dispatch (MW / MVAr) with line parameters (pu).
    script: scripts/power_flow_data.py
    depends_on: [load-network]

  - name: consult-format-reference
    description: Read `references/matpower-format.md` when a question requires the meaning of a specific column or field — full bus / gen / branch / gencost column tables, bus-type codes, per-unit definitions, and reserve fields live there.

anti_patterns:
  - Reading large network JSON line-by-line with `sed`, `head`, `tail`, or `cat` — JSON parsers are fast even on multi-MB files. Use `json.load` directly.
  - Assuming bus numbers are contiguous or 0-indexed. They are not. Always route lookups through `bus_num_to_idx`.
  - Comparing `gen[k, 0]` against a 0-indexed bus position. The first gen column is the raw bus number — map it first.
  - Mixing MW with per-unit values in the same expression. Convert with `baseMVA` first.
  - Iterating branches without checking `branch[10] == 1` (status) — out-of-service branches will silently corrupt totals.
  - Treating `reserve_capacity` / `reserve_requirement` as always present. They are optional fields; check before using.

scenarios:
  - need: First look at an unfamiliar PGLib network.
    action: Call `load_network(path)` then `summarize_network(net)` to print baseMVA, counts, and total load before any deeper analysis.
    outcome: Sanity check confirms the file parsed and gives scale before any per-bus work.

  - need: Find which generators sit on bus number 8945 in a 2000-bus case.
    context: Bus numbers are sparse — index 8945 does not exist in a 2000-entry array.
    action: Build `bus_num_to_idx`, then `bus_idx = bus_num_to_idx[8945]`, then `get_generators_at_bus(gens, bus_idx, bus_num_to_idx)`.
    outcome: Correct generator indices despite the non-contiguous numbering.

  - need: Compute line flow limits in per-unit for an LP formulation.
    action: Read `rateA` from `get_branch_info(...)` (MVA), divide by `network['baseMVA']` (or call `mw_to_pu`) to get the per-unit limit.
    outcome: Branch rating in pu, ready to use alongside `r`, `x`, `b` which are already in pu.
```
