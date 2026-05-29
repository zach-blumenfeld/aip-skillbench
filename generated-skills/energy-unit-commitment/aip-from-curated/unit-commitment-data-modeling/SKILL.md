---
name: unit-commitment-data-modeling
description: Use for parsing structured unit commitment input data from JSON, CSV, benchmark cases, spreadsheets, databases, or nested tables; finding fields for time periods, resources, load, reserve, generator limits, initial conditions, startup data, renewable availability, and production costs without assuming one source-specific schema.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3. The bundled helpers use only the standard library — no numpy, pandas, or solver required.
---

```yaml
purpose: >
  Parse structured unit commitment input data — JSON, CSV, benchmark
  cases, spreadsheets, database tables, or nested dictionaries — into a
  normalized per-resource, per-period representation that downstream
  modeling code can consume without knowing the source format. Maps
  fields to UC concepts by meaning and shape (not by hard-coded names),
  locks the time axis and resource sets, preserves source ordering and
  IDs for reports, and runs parser-level validation before any solver
  is invoked. Bundled scripts encode the startup-tier lookup, the
  piecewise-linear cost-curve interpolation, and the parser checks so
  the agent runs the same checks the data steward would. This is a
  parsing and ingestion guide — not a complete optimization model.

trigger_when:
  - A unit commitment task supplies structured input data and the agent must extract horizon, demand, reserve, resource limits, costs, and initial conditions.
  - The source format is unfamiliar (a new benchmark case, a vendor export, a database snapshot) and the schema is not obvious from the field names.
  - Production cost data needs to be classified (total-cost breakpoints, marginal cost, heat-rate, linear coefficients) before being fed into a model.
  - Startup cost data is supplied as tiers keyed by prior offline duration.
  - Initial conditions (`initial_on`, `initial_output`, `initial_on_duration`, `initial_off_duration`) need to be reconciled before the first period can be modeled.
  - A normalized case object needs to be validated before solving so infeasibility cannot be blamed on a parsing bug.

do_not_use_when:
  - The data has already been parsed into a known, validated normalized form — invoking parsing again is redundant.
  - The task is purely about *constructing* the optimization model or *validating* a returned schedule. Use the operating-rules skill for that, after this skill has produced the normalized case.
  - The task is single-period economic dispatch with no commitment, ramping, reserves, or initial state — the parsing graph here is overkill.

scope_and_approval: >
  Read-only with respect to source data. The parser checker returns a
  structured report and does not mutate the input. The agent may
  proceed to model construction only when `parser_checks.py` returns
  `ok=True`. No network access required.

steps:
  - name: load-raw-data
    description: >
      Load the source with a structured parser: JSON as objects, CSV
      and spreadsheets as tables, databases as query results, nested
      dicts as-is. Do not flatten or rename fields yet. Capture the
      source paths, sheet/table names, and ordering so reports can
      reproduce them.
    outputs:
      - name: raw_data
        type: object
        description: Source-format payload, untouched except for parser-native loading.

  - name: inspect-schema
    description: >
      Walk the top-level keys, tables, sheets, and resource groups.
      Note time-series fields vs scalar fields, nested resource
      objects, cost curves, startup tier tables, and initial-condition
      fields. List candidate field names per UC concept using the
      alias table in `references/parsing-patterns.md`. Defer any naming
      decisions until shapes and units have been inspected — the
      prompt and schema are authoritative when names are ambiguous.
    depends_on: [load-raw-data]
    inputs:
      - name: raw_data
        type: object
    outputs:
      - name: schema_map
        type: object
        description: Candidate source-field -> UC-concept mappings, with shape and unit notes.

  - name: identify-time-axis
    description: >
      Determine the horizon length `T`, the period labels (timestamps,
      one-based hour indexes, etc.), the period duration, and the
      report convention. Keep zero-based internal indexes separate
      from the report labels. The horizon length is authoritative for
      every subsequent time-series length check.
    depends_on: [inspect-schema]
    inputs:
      - name: schema_map
        type: object
    outputs:
      - name: time_axis
        type: object
        description: '{T, periods, period_duration, report_label_convention}.'

  - name: identify-resource-sets
    description: >
      Partition resources by physical class — thermal, renewable,
      storage, imports, network nodes, reserve products. Preserve
      source ordering. Treat resource IDs as opaque strings. Keep
      thermal and renewable sets separate when their constraints
      differ. Capture per-class membership lists used as keys in the
      normalized case.
    depends_on: [inspect-schema]
    inputs:
      - name: schema_map
        type: object
    outputs:
      - name: resource_sets
        type: object
        description: 'Per-class name lists in source order, e.g. {thermal_names, renewable_names}.'

  - name: pick-production-convention
    description: >
      Choose exactly one production-variable convention for the model
      that will consume this case — actual MW or output above minimum
      — and record it next to the normalized case. Ramping, reserve
      deliverability, the cost-curve evaluator, and report extraction
      must all use the same convention. Reports usually require actual
      MW; convert at extraction time when the internal model uses
      above-minimum. See `references/parsing-patterns.md` § Production
      convention.
    depends_on: [identify-resource-sets]
    one_of:
      - actual-MW production
      - above-minimum production
    outputs:
      - name: production_convention
        type: string
        description: Either "actual" or "above_min".

  - name: classify-cost-curves
    description: >
      For each thermal unit, classify the cost data shape before
      storing it: total cost at breakpoints, marginal/incremental
      segment cost, heat-rate table, or linear coefficient pair
      (a + b * P). Convert every shape to total-cost breakpoints so
      `scripts/cost_curve.py` can be applied uniformly. Do not feed
      marginal-cost data to the interpolator. If the smallest
      breakpoint sits at `pmin`, do not invent an additional no-load
      cost unless the source explicitly provides one.
    depends_on: [identify-resource-sets]
    inputs:
      - name: schema_map
        type: object
    outputs:
      - name: production_curves
        type: object
        description: Per-unit list of {mw, cost} breakpoints in total-cost form.

  - name: reconcile-initial-state
    description: >
      For each thermal unit, reconcile `initial_on`,
      `initial_on_duration`, `initial_off_duration`, and any
      `initial_output`. If `initial_on == 1`, the off-duration must be
      zero; if `initial_on == 0`, the on-duration must be zero. The
      offline-duration counter used by the startup-tier rule starts
      at `initial_off_duration` when the unit was offline pre-horizon.
      Surface inconsistencies for `parser_checks.py` to flag.
    depends_on: [identify-resource-sets]
    inputs:
      - name: schema_map
        type: object
    outputs:
      - name: initial_state
        type: object
        description: Per-unit initial-condition record consistent with the chosen convention.

  - name: normalize-into-case
    description: >
      Project the source fields into the normalized `case`
      representation defined in `references/parsing-patterns.md`.
      Every resource appears exactly once. Every time series has
      length `T`. Per-unit parameters are scalar; demand and reserve
      requirement are length-`T` system arrays; renewable min/max are
      length-`T` per-resource arrays. Preserve source names in the
      `*_names` lists so the report can render them unchanged.
    depends_on:
      - identify-time-axis
      - pick-production-convention
      - classify-cost-curves
      - reconcile-initial-state
    inputs:
      - name: time_axis
        type: object
      - name: resource_sets
        type: object
      - name: production_curves
        type: object
      - name: initial_state
        type: object
    outputs:
      - name: case
        type: object
        description: Normalized per-resource, per-period case object ready for validation.

  - name: validate-parsed-case
    description: >
      Run the bundled parser-level checker. It enforces required
      fields, time-series lengths against `T`, finite numeric values,
      `pmin <= pmax`, `renewable_min <= renewable_max`, minimum sizes
      on production curves (>=2 points) and startup tier tables
      (>=1 tier), duplicate-ID detection, and initial-state
      consistency; it warns on repeated cost-curve points and
      non-monotone tier lags. Do not proceed to model construction if
      `ok == False`. Surface every error and warning in the report.
    script: scripts/parser_checks.py
    depends_on: [normalize-into-case]
    inputs:
      - name: case
        type: object
    outputs:
      - name: parser_report
        type: object
        description: '{"ok": bool, "errors": [str, ...], "warnings": [str, ...]}.'

  - name: choose-startup-tier
    description: >
      When a downstream consumer needs the tier-specific startup cost
      for a unit at a given prior offline duration, call the bundled
      helper. The rule is "largest `lag` not exceeding the prior
      offline duration wins"; the helper sorts the tier list
      defensively and falls back to the smallest-`lag` tier when the
      duration is below every threshold. The full tier dict is
      returned so auxiliary fields (e.g. fuel, emissions) survive.
    script: scripts/startup_tier.py
    depends_on: [validate-parsed-case]
    inputs:
      - name: tiers
        type: list[object]
      - name: prior_offline_duration
        type: integer
    outputs:
      - name: chosen_tier
        type: object

  - name: evaluate-cost-curve
    description: >
      When a downstream consumer needs the total production cost for
      a unit at a given actual-MW output, call the bundled helper.
      It sorts breakpoints by `mw`, clamps at the endpoints, and
      linearly interpolates between adjacent breakpoints. Inputs MUST
      already be in total-cost form — do not pass marginal or
      incremental segment costs.
    script: scripts/cost_curve.py
    depends_on: [validate-parsed-case]
    inputs:
      - name: points
        type: list[object]
      - name: output_mw
        type: float
    outputs:
      - name: total_cost
        type: float

scenarios:
  - need: A JSON benchmark case with 24 hourly periods, three thermal units (each with a five-point total-cost curve and three startup tiers), two wind farms with hourly min/max, and zone-level demand and reserve.
    context: >
      The schema names are unfamiliar — `units` instead of `thermal`,
      `forecast_low`/`forecast_high` for renewable bounds, `tier_lag`
      and `tier_cost` inside a nested `startups` array.
    action: >
      Walk the source, build a schema map against the alias table,
      then normalize into `case` with `thermal_names = list(units.keys())`,
      `renewable_min = [[wf["forecast_low"][t] for t in range(T)] for wf in wind]`,
      and similarly for `max`. Lock the production convention as
      "actual" because the report wants MW. Convert startup tiers to
      `{"lag": int, "cost": float}` per unit. Run
      `scripts/parser_checks.py`; with `ok=True`, hand the case to the
      operating-rules skill.
    outcome: >
      A normalized case object reaches the model builder without any
      source-name leakage, and the report renders `units.keys()` in
      source order.
  - need: A vendor export gives production cost as a heat rate plus a fuel price column, not as a total-cost curve.
    context: >
      The interpolator expects total cost at each breakpoint; passing
      marginal heat-rate values would silently produce wrong totals
      everywhere except at one point.
    action: >
      Multiply heat rate by fuel price across each breakpoint, add any
      no-load cost the export provides, and store the result as
      `{"mw", "cost"}` breakpoints in `case["thermal"][g]["production_curve"]`.
      Note in the parser report which units were converted and from
      which source form.
    outcome: >
      `scripts/cost_curve.py` evaluates correctly because the input is
      now genuine total cost; reviewers can trace any reported cost
      back to the conversion step.
  - need: A unit's source record has `initial_on = 1` but `initial_off_duration = 4`.
    context: >
      Mutually inconsistent initial state. If the field is silently
      ignored, the model picks whichever value the first constraint
      reads — usually leading to a wrong startup-cost computation in
      period 0.
    action: >
      `scripts/parser_checks.py` reports
      "thermal[g]: initial_on=1 but initial_off_duration>0" as an
      error. The agent stops, returns the report, and asks the data
      steward to reconcile rather than guessing.
    outcome: >
      The error surfaces at the parsing boundary rather than as an
      unexplained infeasibility downstream.

anti_patterns:
  - Hard-coding a familiar benchmark schema instead of inspecting the data. Source field names vary; map by meaning, units, and shape.
  - Losing source ordering when converting dictionaries or tables into arrays. Reports often expect rows and resources in source order.
  - Joining tables on the wrong key or duplicating resources. Run the duplicate-ID check before downstream code assumes uniqueness.
  - Confusing total output with output above minimum. Pick one convention in `pick-production-convention` and convert only at extraction.
  - Confusing reserve, capacity, availability, and dispatch — they share units but mean different things and live in different fields.
  - Treating every cost curve as marginal cost. Classify the source shape first; convert to total-cost breakpoints before calling `scripts/cost_curve.py`.
  - Ignoring startup-tier lags or initial offline duration. The tier rule is "largest lag not exceeding offline duration"; sorting the tier list defensively is mandatory.
  - Assuming renewable maximum output must always be used. Curtailment is allowed unless the prompt says otherwise; do not turn `max` into a hard equality.
  - Counting renewable headroom as spinning reserve. Reserve is satisfied by thermal units unless the prompt explicitly opens that door.
  - Inventing a no-load or shutdown cost when the source only provides a curve at `pmin`. The smallest breakpoint's cost may already include the online minimum-output cost.
  - Skipping `scripts/parser_checks.py` because the data "looks fine". Parser bugs hide as infeasibility deep in the solver — catch them at the boundary.
```
