---
name: power-flow-data
description: "Power system network data formats and topology. Use when parsing bus, generator, and branch data for power flow analysis."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Parse and interpret MATPOWER-format power-system network JSON (as
  published by the PGLib-OPF benchmark library) into structured data an
  agent can reason about: bus topology, generator placement, branch
  parameters, aggregate load, and reserve requirements. Encodes column
  semantics, the bus-type taxonomy, the per-unit convention, and the
  bus-number-to-index mapping that downstream power-flow / dispatch
  steps depend on.

trigger_when:
  - A task hands the agent a `network.json` (or similarly named MATPOWER
    JSON) and asks it to inspect, summarize, or solve against it.
  - User asks about buses, generators, branches, slack bus, per-unit
    quantities, or reserve capacity in a power-flow context.
  - Building inputs for an OPF / economic-dispatch / power-flow solve
    and needing structured access to topology.

do_not_use_when:
  - Working with PSS/E, CIM, or other non-MATPOWER grid formats.
  - The task is purely about solving the OPF math (use the relevant
    optimization skill); this skill stops at structured data extraction.

steps:
  - name: inspect-and-load
    description: >
      Load the network JSON with Python's `json` module — never `sed`,
      `head`, or line-by-line reads, which waste time and context on
      multi-MB files. Use `wc -l` / `du -h` only for a size sanity check.
      Then call `load_network` to materialize numpy arrays.
    script: scripts/network_utils.py
    inputs:
      - name: network_path
        type: string
        description: Filesystem path to the MATPOWER-format network JSON.
    outputs:
      - name: net
        type: object
        description: >
          Dict with keys `baseMVA`, `bus`, `gen`, `branch`, `gencost`,
          and (when present in the source) `reserve_capacity`,
          `reserve_requirement`.

  - name: summarize
    description: >
      Emit scalar counts (n_bus, n_gen, n_branch), baseMVA, total load,
      and reserve requirement. Run this first on any new file to confirm
      shape before deeper analysis.
    script: scripts/network_utils.py
    depends_on: [inspect-and-load]
    inputs:
      - name: net
        type: object
    outputs:
      - name: summary
        type: object

  - name: build-bus-mapping
    description: >
      Bus numbers in MATPOWER are not guaranteed contiguous. Build the
      `bus_number -> 0-indexed position` mapping with `bus_num_to_idx`
      and use it for every subsequent gen/branch join. Joining on raw
      bus numbers is the most common silent bug in this format.
    script: scripts/network_utils.py
    depends_on: [inspect-and-load]
    inputs:
      - name: net
        type: object
    outputs:
      - name: mapping
        type: object
        description: dict[int, int] from raw bus number to row index.

  - name: locate-topology
    description: >
      Find the slack bus (type code 3) with `find_slack_bus`; resolve
      generators-at-bus with `get_generators_at_bus`; resolve
      generator-to-bus-index with `gen_bus_indices`. Bus-type codes
      (1=PQ, 2=PV, 3=slack) are tabulated in
      `references/matpower-format.md`.
    script: scripts/network_utils.py
    depends_on: [build-bus-mapping]
    inputs:
      - name: net
        type: object
      - name: mapping
        type: object
    outputs:
      - name: topology
        type: object
        description: >
          Dict with slack_bus_idx (int|None) and gen_bus_idx (list[int]).

  - name: interpret-branches
    description: >
      Decode branch rows with `get_branch_info`: from/to bus indices,
      R/X/B in pu, MVA rating, in-service flag. Column layout is in
      `references/matpower-format.md`.
    script: scripts/network_utils.py
    depends_on: [build-bus-mapping]
    inputs:
      - name: net
        type: object
      - name: mapping
        type: object
    outputs:
      - name: branches
        type: list[object]

  - name: aggregate-load
    description: >
      Sum bus Pd (column 2) to get total system load in MW via
      `total_load`. For per-unit conversion against baseMVA, use
      `to_pu` / `from_pu`.
    script: scripts/network_utils.py
    depends_on: [inspect-and-load]
    inputs:
      - name: net
        type: object
    outputs:
      - name: load_mw
        type: float

scenarios:
  - need: >
      Task hands the agent a 100K+ line `network.json` for a realistic
      grid and asks for a topology summary.
    context: >
      First instinct might be `head network.json` or `sed -n '1,200p'`
      to peek at structure — that path burns context and produces
      nothing useful because the file is a single long JSON array.
    action: >
      Use `wc -l` / `du -h` to check size, then call
      `load_network('network.json')` followed by `summarize(net)` for
      counts and total load.
    outcome: >
      Scalar summary in seconds, full network materialized as numpy
      arrays for downstream steps.

  - need: >
      Need to know which generators sit at the slack bus before
      seeding a power-flow solve.
    context: >
      Bus numbers in the file are 1-indexed and non-contiguous (typical
      of PGLib cases); naive row-index joins would mis-assign gens.
    action: >
      `mapping = bus_num_to_idx(net['bus'])`, then
      `slack = find_slack_bus(net['bus'])`, then
      `get_generators_at_bus(net['gen'], slack, mapping)`.
    outcome: >
      Correct generator row indices keyed to the slack bus, robust to
      non-contiguous bus numbering.

anti_patterns:
  - Reading large network JSON files line-by-line with `sed`, `head`,
    `tail`, or `cat`. Use `json.load` — it is fast even on multi-MB
    files and gives you a structured object in one shot.
  - Joining `gen` or `branch` rows to `bus` rows on raw bus numbers
    instead of going through the `bus_number -> index` mapping. Bus
    numbers are not contiguous and not zero-indexed.
  - Treating MW and per-unit quantities interchangeably. baseMVA (often
    100) is the divisor — see `references/matpower-format.md` § Per-unit.
  - Hard-coding column indices in prose. The branch and bus column
    layouts live in `references/matpower-format.md`; load that file
    when interpreting raw rows.
  - Assuming every network file has `reserve_capacity` /
    `reserve_requirement`. `load_network` returns them only when
    present; check before referencing.
```
