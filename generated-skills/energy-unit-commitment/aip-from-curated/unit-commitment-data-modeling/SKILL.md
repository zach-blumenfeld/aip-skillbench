---
name: unit-commitment-data-modeling
description: Use for parsing structured unit commitment input data from JSON, CSV, benchmark cases, spreadsheets, databases, or nested tables; finding fields for time periods, resources, load, reserve, generator limits, initial conditions, startup data, renewable availability, and production costs without assuming one source-specific schema.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Map structured unit commitment input data onto UC concepts without
  hard-coding any one benchmark or package schema. Inspect the source,
  identify the time axis and resource sets, map fields by meaning, and
  normalize into an in-memory case representation with explicit shapes,
  preserved ordering, verified units, and parser-level checks before
  modeling.

trigger_when:
  - The task supplies structured UC input data (JSON, CSV, spreadsheet, database, nested dict).
  - The prompt or schema mentions periods, generators, load, reserve, startup tiers, ramp limits, initial conditions, or renewable availability and you need to extract them.
  - You are about to write modeling/solver code and need a normalized case dict to drive it.
  - You're unsure whether a field maps to commitment, output limits, ramping, cost, or reserve.

do_not_use_when:
  - The input data is unstructured prose with no fields to parse.
  - Parsing has already been done upstream and the normalized case dict is provided directly.
  - The task is purely about formulating constraints or solving, with no source-data ambiguity.

scope_and_approval: >
  Read-only against the source data. Produce an in-memory normalized
  representation and, optionally, a validation report. Do not mutate or
  rescale the source. If the prompt forbids data changes, never apply
  unit conversions inside the case dict — record the source units and
  convert at the modeling boundary instead.

steps:
  - name: load-data
    description: >
      Parse the source with the appropriate structured parser — JSON as
      Python objects, CSV/sheets as tables (pandas, csv.DictReader),
      databases as query results. Do not regex-scrape values out of
      free text. Keep the parsed object available for inspection in the
      next step.
    outputs:
      - name: raw-data
        type: object
        description: The parsed source — dict for JSON, DataFrames for tabular, etc.

  - name: inspect-schema
    description: >
      Survey the parsed object before assuming anything. List top-level
      keys, table/sheet names, resource groups, time-series fields,
      cost-curve fields, startup-tier fields, and initial-condition
      fields. Note the *shape* of each: scalar, list, nested object,
      table. The prompt and the source schema are the source of truth —
      not your prior memory of any benchmark.
    inputs:
      - name: raw-data
        type: object
    outputs:
      - name: schema-survey
        type: object
        description: Inventory of keys/tables/shapes, used to drive the mapping steps.

  - name: identify-time-axis
    description: >
      Determine the horizon T. Look for an explicit period count, a list
      of timestamps, a `periods` array, or the length of a representative
      time-series field. Capture period labels, period duration (1h vs
      sub-hourly), and the reporting convention (zero-based vs one-based,
      label vs timestamp). Use the input horizon as authoritative.
    inputs:
      - name: schema-survey
        type: object
    outputs:
      - name: time-axis
        type: object
        description: "{T, period_labels, duration, report_label_base}"

  - name: identify-resource-sets
    description: >
      Categorize resources by role: thermal generators, renewable
      generators, storage, imports/exports, zones, reserve products,
      network objects. Keep sets separate where their constraints
      differ. Preserve source ordering within each set. Treat resource
      IDs as opaque strings; do not parse meaning out of names.
    inputs:
      - name: schema-survey
        type: object
    outputs:
      - name: resource-sets
        type: object
        description: "{thermal_names, renewable_names, storage_names, ...} in source order"

  - name: map-fields-to-concepts
    description: |
      Map source fields onto UC concepts by *meaning*, *units*, *shape*,
      and *context* — not by exact-string name match. Use this table:

      | UC concept            | Look for                                                                  |
      | --------------------- | ------------------------------------------------------------------------- |
      | Horizon               | periods, hours, timestamps, interval count                                |
      | Demand                | load, system demand, net load, zone load                                  |
      | Reserve requirement   | spinning, operating, contingency, regulation reserve                      |
      | Resource sets         | thermal, renewable, storage, import/export                                |
      | Commitment status     | on/off, online, active, unit status                                       |
      | Output limits         | minimum stable output, maximum output, availability                       |
      | Ramping               | ramp up/down, startup capability, shutdown capability                     |
      | Minimum up/down       | required duration after start/stop                                        |
      | Initial conditions    | initial status, initial output, time already on/off                       |
      | Must-run              | forced online, fixed status                                               |
      | Startup data          | fixed costs or tiers by prior offline duration                            |
      | Production cost       | linear coefficients, heat rate, piecewise or total-cost curves            |
      | Renewable availability| hourly min/max output or forecast bounds                                  |

      Recognize the data shapes you will encounter:
        - Scalar by resource: min up/down, ramp rates, startup ramp, must-run.
        - Time series by system/zone: demand and reserve requirement.
        - Time series by resource: renewable availability or outage status.
        - Curve/tier tables: startup costs and production-cost breakpoints.
        - Nested resource objects: generator-specific limits, status, costs.

      If a field's meaning is ambiguous, prefer the prompt's wording and
      the units over a guess based on the field name.
    inputs:
      - name: schema-survey
        type: object
      - name: resource-sets
        type: object
    outputs:
      - name: field-mapping
        type: object
        description: source-name → UC-concept mapping for each resource set and system-level series.

  - name: check-units-and-conventions
    description: >
      Before normalizing, verify power units (MW vs kW), period duration
      (1h vs sub-hourly affects ramp and energy), ramp-rate units
      (MW/min vs MW/h vs MW/period), and cost units (currency, per-MWh
      vs per-period). Choose one internal output convention — actual MW
      *or* output-above-minimum — and record it. Reporting and ramping
      logic depend on the choice; see anti_patterns.
    inputs:
      - name: field-mapping
        type: object
    outputs:
      - name: conventions
        type: object
        description: "{power_unit, period_duration, ramp_unit, cost_unit, output_convention}"

  - name: normalize-into-case-dict
    description: |
      Build a small, explicit in-memory representation. Preserve source
      order in the name lists; keep zero-based internal indexes separate
      from one-based report labels; verify every time-series length
      equals T. Suggested skeleton:

          case = {
              "T": T,
              "periods": periods,                 # length T
              "thermal_names": thermal_names,     # length G, source order
              "renewable_names": renewable_names, # length R, source order
              "demand": demand,                   # shape (T,)
              "reserve_requirement": reserve,     # shape (T,)
              "thermal": thermal_params,          # name -> params dict
              "renewable_min": renewable_min,     # name -> length-T list
              "renewable_max": renewable_max,     # name -> length-T list
              "conventions": conventions,
          }

      Keep thermal and renewable parameter sets separate when their
      constraints differ. Treat IDs as opaque strings.
    inputs:
      - name: time-axis
        type: object
      - name: resource-sets
        type: object
      - name: field-mapping
        type: object
      - name: conventions
        type: object
    outputs:
      - name: case
        type: object

  - name: parse-startup-tiers
    description: >
      For each thermal resource, normalize startup data into a list of
      tiers, each `{lag, cost}`. Do not assume the source lists them in
      lag order. To select the right tier at a given prior-offline
      duration, call `choose_startup_tier(tiers, prior_offline_duration)`
      from `scripts/uc_data_helpers.py` — it sorts by lag and returns
      the latest tier whose lag ≤ duration. Keep prior offline duration
      consistent with initial status and transition timing.
    script: scripts/uc_data_helpers.py
    inputs:
      - name: case
        type: object
    outputs:
      - name: startup-tier-fn
        type: object
        description: Reference to choose_startup_tier; attach normalized tier lists into case["thermal"][name]["startup_tiers"].

  - name: parse-cost-curves
    description: >
      Identify whether the source gives total cost, marginal cost,
      incremental-segment cost, or heat-rate data. For total-cost
      breakpoints, call `interpolate_total_cost(points, output_mw)` from
      `scripts/uc_data_helpers.py` — piecewise linear, clamps at
      endpoints, no extrapolation. If the first point is at minimum
      output, treat it as the online minimum-output cost; do not invent
      no-load or shutdown costs unless the source provides them. For
      marginal or incremental data, convert to total before interpolating.
    script: scripts/uc_data_helpers.py
    inputs:
      - name: case
        type: object
    outputs:
      - name: cost-curve-fn
        type: object
        description: Reference to interpolate_total_cost; attach normalized curves into case["thermal"][name]["production_curve"].

  - name: handle-renewables
    description: >
      Parse hourly minimum and maximum output for each renewable
      resource. If min equals max in a period, output is fixed; if min
      < max, curtailment is allowed in that period. Do not count
      renewable headroom toward spinning reserve unless the task or
      data explicitly allows it. Renewable cost is zero unless the data
      says otherwise.
    inputs:
      - name: case
        type: object
    outputs:
      - name: renewable-attached
        type: object

  - name: validate-parsed-case
    description: >
      Run `scripts/validate_parsed_case.py` (or call `validate_case(case)`
      from it) on the normalized dict. Checks: finite demand and reserve,
      pmin ≤ pmax, renewable_min ≤ renewable_max per period, length of
      every time-series equals T, ≥2 points per production curve, ≥1
      tier per generator, no duplicate resource IDs, no duplicate
      startup-tier lags, and initial-status/initial-output consistency.
      Returned errors must be resolved before downstream modeling.
    script: scripts/validate_parsed_case.py
    inputs:
      - name: case
        type: object
    outputs:
      - name: validation-errors
        type: list[string]
        description: Empty list when the parsed case is clean.

anti_patterns:
  - Hard-coding a familiar benchmark's schema instead of inspecting the actual data.
  - Mapping by exact field-name match instead of by meaning, units, and shape.
  - Losing source ordering when converting dictionaries or tables into arrays.
  - Joining tables on the wrong key or duplicating resources.
  - Confusing total output with output-above-minimum in constraints, ramping, reserve deliverability, or reports.
  - Treating every cost curve as marginal cost when the source gives total cost.
  - Ignoring startup-tier lags or initial offline duration when picking a startup cost.
  - Assuming renewable maximum output must always be used (curtailment may be allowed).
  - Inventing no-load or shutdown costs that the source did not provide.
  - Counting renewable headroom as spinning reserve when the task does not allow it.
  - Rescaling or unit-converting the source data when the prompt forbids it; convert at the modeling boundary instead.
```
