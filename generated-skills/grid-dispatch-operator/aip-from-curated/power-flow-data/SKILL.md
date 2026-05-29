---
name: power-flow-data
description: "Power system network data formats and topology. Use when parsing bus, generator, and branch data for power flow analysis — MATPOWER-format JSON snapshots from the PGLib-OPF benchmark library, including loading the file, building the bus-number-to-index map, identifying the slack bus, locating generators on a bus, decoding branch rows, looking up reserve capacity and the system reserve requirement, and computing total system load."
compatibility: "Requires Python 3 and numpy."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Parse, load, and interrogate MATPOWER-format power-system network JSON
  snapshots (PGLib-OPF benchmark, github.com/power-grid-lib/pglib-opf).
  Encapsulates the field conventions of the bus / gen / branch / gencost
  matrices, the per-unit base-MVA system, the discontiguous bus-number
  problem, and reserve fields. Downstream DC-power-flow and economic
  dispatch code relies on these helpers — especially the
  bus-number-to-index map — to join generators and branches back to bus
  rows correctly.

trigger_when:
  - A `network.json` MATPOWER snapshot must be parsed.
  - Bus types must be identified (slack / PV / PQ) or the slack row located.
  - Generators must be matched to their host bus, or branch endpoints decoded.
  - Reserve capacity (`reserve_capacity`) or the system reserve floor
    (`reserve_requirement`) is being looked up.
  - Total system load must be computed.
  - A multi-MB network file is about to be inspected with line-oriented
    tools (`sed`, `head`, `cat`) — stop and use the JSON parser instead.

do_not_use_when:
  - The task does not involve MATPOWER / power-system data.
  - You only need a quick byte- or line-count of the file (use `wc -l`
    or `du -h` and stop).

steps:
  - name: summarize-network
    description: >
      One-shot read of the file producing counts (buses, generators,
      branches), total load, reserve totals, and the slack bus row.
      Run this first on any new network — never line-step a multi-MB
      JSON file with `sed`/`head`. The script also doubles as the
      library module imported by later steps.
    script: scripts/network_utils.py
    inputs:
      - name: network-json-path
        type: string
        description: Path to the MATPOWER-format network JSON file.
    outputs:
      - name: summary
        type: object
        description: >
          Dict with baseMVA, n_bus, n_gen, n_branch, total_load_MW,
          reserve_requirement_MW, reserve_capacity_total_MW, slack_bus_row.

  - name: load-network
    description: >
      Call `network_utils.load_network(path)` to obtain a dict with
      `baseMVA` (float, typically 100.0) plus numpy arrays for `bus`,
      `gen`, `branch`, `gencost`, `reserve_capacity` (MW per generator;
      empty array if absent), and the scalar `reserve_requirement` (MW
      system floor; 0.0 if absent). Per-unit conversions: divide MW /
      MVAr / MVA by `baseMVA` for pu; multiply pu by `baseMVA` to
      recover engineering units — `to_per_unit` / `from_per_unit` in
      the same module do this.
    script: scripts/network_utils.py
    inputs:
      - name: network-json-path
        type: string
    outputs:
      - name: network
        type: object
        description: >
          Dict with baseMVA, bus, gen, branch, gencost,
          reserve_capacity, reserve_requirement.

  - name: build-bus-index
    description: >
      Build the bus-number-to-row-index map with
      `network_utils.build_bus_num_to_idx(network['bus'])`. MATPOWER
      bus numbers (column 0 of the bus matrix) are NOT contiguous —
      e.g. case300 has gaps. Every join from a generator (`gen[:,0]`)
      or branch endpoint (`branch[:,0]`, `branch[:,1]`) back to a bus
      row must go through this map. Never use `bus_number - 1` as an
      array index.
    depends_on: [load-network]
    inputs:
      - name: network
        type: object
    outputs:
      - name: bus-num-to-idx
        type: object
        description: dict[int, int] — bus number → 0-indexed bus row.
    script: scripts/network_utils.py

  - name: query-topology
    description: >
      Use the structural helpers in `network_utils`:
      `find_slack_bus(bus)` → 0-indexed slack row (the row whose
      column-1 type code equals 3; codes are 3=slack, 2=PV, 1=PQ);
      `get_generators_at_bus(gen, bus_idx, bus_num_to_idx)` → indices
      into `gen` of generators connected to a given bus row;
      `get_branch_info(branch_row, bus_num_to_idx)` → dict with
      from/to bus indices, resistance R (pu), reactance X (pu),
      susceptance B (pu), MVA rating (rateA), and in-service flag
      (status column 10 == 1).
    depends_on: [build-bus-index]
    inputs:
      - name: network
        type: object
      - name: bus-num-to-idx
        type: object
    outputs:
      - name: topology
        type: object
        description: >
          Whatever subset the caller needs — slack row index, generator
          lists per bus, decoded branch records.
    script: scripts/network_utils.py

  - name: aggregate-loads
    description: >
      Compute total system load with `network_utils.total_load(bus)`
      — the sum of Pd (column 2) across all bus rows, in MW. Use this
      as the right-hand side of the system power balance and as a
      sanity check before solving dispatch.
    depends_on: [load-network]
    inputs:
      - name: network
        type: object
    outputs:
      - name: total-load-mw
        type: float
    script: scripts/network_utils.py

scenarios:
  - need: >
      Quickly understand a brand-new `network.json` before writing
      any dispatch code.
    action: >
      `python scripts/network_utils.py network.json` — prints counts,
      total load, reserves, and slack row in one shot.
    outcome: >
      Sizing, slack identification, and reserve floor known without
      touching the file with line-oriented tools.
  - need: >
      Map every generator to the bus it sits on.
    context: >
      `gen[:,0]` holds bus *numbers*, not row indices. Bus numbers can
      have gaps.
    action: >
      Load with `load_network`, then build the map with
      `build_bus_num_to_idx`, then index each generator's bus number
      through that map.
    outcome: >
      Generator-to-bus joins are correct even on cases with
      non-contiguous bus IDs (e.g. case300, large PGLib snapshots).
  - need: >
      Decide branch flow direction and limits for a DC-OPF
      formulation.
    action: >
      For each branch row call
      `get_branch_info(row, bus_num_to_idx)`. Use `from_bus`/`to_bus`
      (already 0-indexed) as the angle-difference endpoints, `1/X` as
      the susceptance, and `rating` (MVA) as the thermal limit.
    outcome: >
      Branch constraints ready to plug into DC power flow with the
      correct sign convention and per-branch susceptance.

anti_patterns:
  - >
      Reading `network.json` line-by-line with `sed`, `head`, `tail`,
      or `cat`. Files can be 100K+ lines; line-stepping wastes context
      and time. Always `json.load` the whole file — the parse cost
      scales linearly even on multi-MB inputs.
  - >
      Using `bus_number - 1` (or any arithmetic on the bus number) as
      a row index. MATPOWER bus numbers are not contiguous. Always go
      through the `bus_num_to_idx` map.
  - >
      Treating `reserve_capacity` and `reserve_requirement` as the
      same thing. `reserve_capacity` is the per-generator MW cap
      (array, one entry per generator); `reserve_requirement` is the
      system-wide MW floor (scalar).
  - >
      Reading raw bus / gen / branch columns from memory without
      checking units. Powers in the file are in MW / MVAr / MVA;
      impedances (R, X, B) are already per-unit on `baseMVA`. Mix
      these up and the susceptance matrix is off by a factor of
      `baseMVA`.
  - >
      Hard-coding bus type 3 as "row 0 is always the slack." It often
      isn't — use `find_slack_bus`.
```
