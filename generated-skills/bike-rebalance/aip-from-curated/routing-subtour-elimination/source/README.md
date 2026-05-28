# routing-subtour-elimination — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `routing-subtour-elimination`
from the `bike-rebalance` SkillsBench task (`aip-from-curated` track).
The canonical original is preserved verbatim at
`source/ORIGINAL_SKILL.md`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2)
  the body validates against. Bundled locally so the skill is
  self-contained.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill teaches a
short workflow — declare base notation, add base route constraints,
pick a subtour-elimination method, add it, validate the extracted
routes — plus a catalog of four methods. That maps cleanly to a
procedure of script-backed steps with one `one_of` branch on method
choice. No new schema fields were needed.

## Layout decisions

The curated `SKILL.md` mixes three kinds of content:

1. A **fixed setup workflow** — canonical base notation, degree /
   continuity constraints, route extraction. These are the same on
   every problem instance and become script-backed steps.
2. **Four parallel method blocks** (MTZ, single-commodity flow, static
   DFJ, lazy/iterative DFJ separation). Each is a self-contained
   constraint family with a fixed mathematical shape. They become
   callable scripts AND a reference catalog for the agent to read on
   demand if its variable shape deviates from the base notation.
3. **A method-choice table** with soft thresholds (~15-18 stations
   for static DFJ). AIP best-practice puts thresholds in scripts;
   `scripts/select_method.py` encodes the recommendation logic and
   returns a structured `(method, rationale)` pair.

## Why these scripts exist

- `scripts/route_setup.py` — declares `DEPOT_START` / `DEPOT_END`
  constants, the canonical arc-set builder, the binary `x[v, i, j]`
  variable family, and the degree+continuity base constraints. Every
  method downstream relies on this exact shape. Keeping it in a script
  prevents subtle naming drift between the model and the helpers.
- `scripts/subtour_constraints.py` — three drop-in functions for the
  static methods: `add_mtz_constraints`, `add_single_commodity_flow`,
  `add_static_dfj_cuts`. Each is the exact code from the curated
  source, parameterized over the (vehicles, stations, x) tuple. The
  static DFJ helper carries a hard `max_n` guard at 18 (curated cap)
  with an explicit override path — silently emitting exponential
  constraints is the failure mode this guard prevents.
- `scripts/lazy_separation.py` — `selected_arcs`,
  `station_cycles_without_start`, `add_subtour_cut`, and the
  `iterative_subtour_cuts` driver. The driver carries a
  `max_iterations` guard because endless re-solving on a cycle-detection
  bug is otherwise indistinguishable from a hard instance.
- `scripts/route_extraction.py` — the post-solve guardrail. Walking
  the successor map detects disconnection, repeated stations, and
  missing endpoints — the curated source's "fail fast" rule.
- `scripts/select_method.py` — encodes the method-choice table. Inputs
  are structured (`n_stations`, `n_vehicles`, `optional_visits`,
  `memory_tight`, `debug_baseline`, `weak_incumbents`); output is
  `MethodRecommendation(method, rationale)`. Thresholds
  (`STATIC_DFJ_HARD_CAP = 15`, `SMALL_INSTANCE_MAX_STATIONS = 30`,
  `MEDIUM_INSTANCE_MAX_STATIONS = 60`) sit at module top so they are
  one edit away from being tuned.

The four method bodies are deliberately mirrored in
`references/methods.md`. The scripts cover the canonical-shape case;
the reference covers the adapt-to-my-model case. This is the
"convert-back-to-prose-when-a-script-would-over-restrict-reasoning"
guidance from AIP best practices applied selectively — scripted by
default, prose on demand.

## Notable expansions beyond the literal source

- **Method-choice as a callable recommender.** The original prints the
  choice table; the AIP version turns it into a function so the agent
  passes its structured problem features in and gets a typed
  recommendation back instead of re-reading the table.
- **Hard cap on static-DFJ enumeration.** The curated text says
  "roughly 15-18 stations". The AIP `add_static_dfj_cuts` script
  raises by default when `n > 18`. Override is explicit.
- **Iterations guard on the lazy separation loop.** Endless re-solve is
  the silent-bug failure mode; the AIP driver fails loudly after
  `max_iterations` (default 100).
- **`freeTransform` callout.** The original includes the call inside
  the code block; the AIP body and `methods.md` both highlight that
  without it, the second iteration silently fails to add the cut. This
  is the trap that bit the curated source enough to make it into the
  reference docstring.

## Source-content classification (completeness check)

Every distinct piece of the curated `SKILL.md`:

- Intro paragraph (degree + continuity not enough; binary arc vars
  trigger subtour cuts) -> **Mapped** to `purpose`, `trigger_when`,
  and the rationale text in `references/notation.md`.
- Base notation code block (`START`, `END`, `vehicles`, `stations`,
  `arcs`, `x`) -> **Mapped** to `scripts/route_setup.py` (constants
  + `build_arc_set` + `add_arc_variables`) and to
  `references/notation.md` § Nodes and arcs / Decision variables.
- Required base route constraints code block -> **Mapped** to
  `scripts/route_setup.py::add_base_route_constraints` and to
  `references/notation.md` § Required base route constraints.
- Method 1 MTZ (code + pros + cons + when-to-use) -> **Mapped** to
  `scripts/subtour_constraints.py::add_mtz_constraints` and
  `references/methods.md` § 1.
- Method 2 single-commodity flow (code + pros + cons + when-to-use)
  -> **Mapped** to
  `scripts/subtour_constraints.py::add_single_commodity_flow` and
  `references/methods.md` § 2.
- Method 3 static DFJ (code + pros + cons + when-to-use) -> **Mapped**
  to `scripts/subtour_constraints.py::add_static_dfj_cuts` (with the
  added hard cap guard) and `references/methods.md` § 3.
- Method 4 lazy/iterative DFJ separation (helper functions + main
  loop) -> **Mapped** to `scripts/lazy_separation.py` and
  `references/methods.md` § 4. The `freeTransform` requirement is
  preserved.
- Method-choice table -> **Mapped** to
  `scripts/select_method.py::recommend_method` and to
  `references/methods.md` § Method Choice Table.
- Pickup/dropoff rebalancing guidance (do not use physical load as
  connectivity flow) -> **Mapped** to `anti_patterns` and to inline
  docstring warnings in `add_single_commodity_flow` and
  `references/methods.md`.
- Validation route-extraction code -> **Mapped** to
  `scripts/route_extraction.py::extract_route` and to the
  `extract-and-validate-routes` step.
- "Fail fast on disconnected cycle, repeated station, missing depot"
  rule -> **Mapped** to docstring + `RuntimeError` paths in
  `extract_route`.

No source content was dropped. Promotions: the implicit
"freeTransform before re-adding cuts" rule and the implicit
"physical load is not connectivity flow" rule both became explicit
`anti_patterns` entries in the body.

## Tested

`scripts/validate.py` from the bundled AIP skill was run against this
folder and passes. Functional testing was not conducted with fresh
sub-agents in this session — the task runtime here does not spawn
fresh sub-agents against arbitrary skill folders.
