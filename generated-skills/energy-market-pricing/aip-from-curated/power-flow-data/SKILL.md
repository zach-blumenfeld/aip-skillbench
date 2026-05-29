---
name: power-flow-data
description: "Power system network data formats and topology. Use when parsing bus, generator, and branch data for power flow analysis."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Reference for MATPOWER-format network data (as produced by PGLib-OPF) and a
  small set of utilities every downstream power-flow / OPF skill consumes:
  loading JSON into numpy arrays, building a bus-number → row-index map,
  finding the slack bus, locating generators at a bus, decoding branch rows,
  and computing total system load. Encodes the column layouts, bus-type
  codes, per-unit conventions, and PGLib reserve-field extensions so the
  agent never has to guess MATPOWER indices.

trigger_when:
  - Parsing MATPOWER-format network JSON (bus, gen, branch, gencost, reserves).
  - Looking up MATPOWER column indices, bus-type codes, or per-unit conversions.
  - Building a bus-number → 0-indexed row map for gen/branch lookups.
  - Finding the slack bus or generators at a specific bus.
  - Locating a branch by its endpoint bus numbers (e.g. "line 64–1501").
  - Reading network files that may exceed 100k lines — don't open with head/sed.
  - Computing total system load before sanity-checking an OPF solution.

do_not_use_when:
  - Solving DC power flow itself — use the `dc-power-flow` skill.
  - Running economic dispatch or computing LMPs — use `economic-dispatch` or
    `locational-marginal-prices`.

scope_and_approval: >
  Read-only. Every utility here parses or reports on network data; none
  mutate the source file. Counterfactual perturbations (e.g. raising a line
  rating by 20%) are performed by the caller on the in-memory numpy arrays,
  not by this skill.

steps:
  - name: orient
    description: >
      Run `python scripts/summarize_network.py <network.json>` first to get
      bus/gen/branch counts, total load, baseMVA, slack bus number, bus-number
      range, contiguity, and presence of reserve fields. Use this instead of
      `head`, `sed`, or `cat` — network JSON files in this benchmark can
      exceed 100k lines and shell tools waste time and context.
    script: scripts/summarize_network.py
    inputs:
      - name: filepath
        type: string
        description: Path to the MATPOWER-format network.json file.

  - name: load-network
    description: >
      Load the file into a dict of numpy arrays via
      `network_utils.load_network`. Keys: baseMVA, bus, gen, branch, gencost,
      reserve_capacity, reserve_requirement. Reserve fields are PGLib
      extensions and are None when absent.
    script: scripts/network_utils.py
    inputs:
      - name: filepath
        type: string
    outputs:
      - name: network
        type: object
        description: Dict with baseMVA, bus, gen, branch, gencost, reserve_capacity, reserve_requirement.

  - name: build-bus-index
    description: >
      Build `bus_num_to_idx`, a dict mapping raw bus number (column 0) to
      its 0-indexed row position. Bus numbers in MATPOWER files are NOT
      guaranteed contiguous or 1-indexed — always go through this map before
      relating gen/branch rows to bus rows.
    script: scripts/network_utils.py
    inputs:
      - name: bus
        type: object
        description: numpy array from network['bus'].
    outputs:
      - name: bus_num_to_idx
        type: object
        description: dict[int, int] keyed by bus number, valued by row index.

  - name: locate-slack
    description: >
      Return the 0-indexed row of the slack bus (bus type code 3). Every
      DC-OPF needs exactly one. Returns None if missing — treat as malformed
      input and stop.
    script: scripts/network_utils.py
    inputs:
      - name: bus
        type: object
    outputs:
      - name: slack_idx
        type: integer
        nullable: true

  - name: generators-at-bus
    description: >
      Return generator row indices whose `gen[:,0]` (bus number) maps to the
      given 0-indexed bus position. Always pass `bus_num_to_idx` explicitly
      — comparing raw bus numbers to row indices is the single most common
      bug in MATPOWER code.
    script: scripts/network_utils.py
    inputs:
      - name: gen
        type: object
      - name: bus_idx
        type: integer
      - name: bus_num_to_idx
        type: object
    outputs:
      - name: gen_indices
        type: list[integer]

  - name: find-branch
    description: >
      Locate a branch by its endpoint bus numbers (matches either
      direction). Returns the 0-indexed row. Use this when a task names a
      line by its endpoints (e.g. "the line from bus 64 to bus 1501") and
      you need the row to read or perturb its rating (column 5, rateA).
    script: scripts/network_utils.py
    inputs:
      - name: branch
        type: object
      - name: from_bus_number
        type: integer
      - name: to_bus_number
        type: integer
    outputs:
      - name: row_idx
        type: integer
        nullable: true

  - name: decode-branch
    description: >
      Decode a single branch row into named fields (from_bus, to_bus, R, X,
      B, MVA rating, in_service). from_bus and to_bus are 0-indexed
      positions, not raw bus numbers.
    script: scripts/network_utils.py
    inputs:
      - name: branch_row
        type: object
      - name: bus_num_to_idx
        type: object
    outputs:
      - name: info
        type: object

  - name: total-load
    description: >
      Sum bus column 2 (Pd) — total active-power system load in MW. Use as a
      quick sanity check that an OPF solution's dispatch covers demand.
    script: scripts/network_utils.py
    inputs:
      - name: bus
        type: object
    outputs:
      - name: load_mw
        type: float

  - name: convert-per-unit
    description: >
      MATPOWER mixes physical units (MW, MVAr, kV) in raw data with per-unit
      values in branch impedances. When wiring data into a DC-OPF
      formulation, divide power quantities by `baseMVA` before any
      calculation that uses pu reactances. Direction:
      `P_pu = P_MW / baseMVA`. Read
      `references/matpower-format.md` § baseMVA when unsure.

  - name: load-reference-when-stuck
    description: >
      If a column index, bus-type code, gencost layout, or reserve field
      semantics is unclear, read `references/matpower-format.md` — full
      column-by-column tables for bus, gen, branch, and gencost, plus the
      PGLib reserve extensions. Don't guess MATPOWER indices.

scenarios:
  - need: >
      "What is the thermal capacity of the transmission line connecting
      bus 64 to bus 1501?"
    action: >
      `load-network` → `find-branch(branch, 64, 1501)` → read column 5
      (rateA) of that row.
    outcome: >
      MVA limit in hand. To perturb (e.g. +20% in a counterfactual), copy
      the branch array and multiply `branch[row, 5] *= 1.20` before
      re-running OPF.

  - need: >
      "Compute total system load to sanity-check the dispatch."
    action: >
      `load-network` → `total_load(network['bus'])`.
    outcome: >
      Scalar MW value. Dispatch `sum(gen[:,1])` should approximately equal
      this (small slack absorbs balance) when the OPF converges.

  - need: >
      "Which generators are at the slack bus?"
    action: >
      `load-network` → `bus_num_to_idx` → `find_slack_bus` → pass the
      0-indexed slack position to `get_generators_at_bus`.
    outcome: >
      List of generator row indices. Pmax/Pmin/cost can then be read from
      `gen[idx, :]` and `gencost[idx, :]`.

anti_patterns:
  - Reading network.json with `head`, `sed`, `cat`, or other line-oriented
    shell tools. Always parse via `json.load` (or run
    `scripts/summarize_network.py` for a first look).
  - Assuming bus numbers are 0-indexed, 1-indexed, or contiguous. They are
    none of those guaranteed — always build `bus_num_to_idx` first.
  - Comparing `gen[:,0]` directly to a 0-indexed bus position. Map through
    `bus_num_to_idx` first; otherwise generator-to-bus joins silently produce
    empty or wrong results.
  - Mixing MW and per-unit values in the same expression. Divide by
    `baseMVA` before any pu computation.
  - Hardcoding `baseMVA = 100`. Read it from the file — PGLib mostly uses
    100, but other MATPOWER cases do not.
  - Treating bus type as a string ("PQ"/"PV"/"slack"). Codes are integers
    1, 2, 3.
  - Forgetting to filter on branch column 10 (`status`) when computing
    flows or scanning binding lines — out-of-service branches must be skipped.
  - Assuming `reserve_capacity` / `reserve_requirement` always exist. They
    are PGLib extensions; `load_network` returns None when absent.
```
