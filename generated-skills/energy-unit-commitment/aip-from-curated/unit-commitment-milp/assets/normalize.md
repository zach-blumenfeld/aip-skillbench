The case file at `{data_path}` is not usable as-is.

Errors: {data_errors}
Warnings: {data_warnings}
Schema seen: {schema_summary}

Map the source into the canonical case schema the scripts read, then write it as JSON to a new file
outside the skill folder (e.g. next to the solution file) and return its path as `data_path`.
The prompt and the source schema are the source of truth; map by meaning, units, shape, and context,
not by names.

1. Load with structured parsers (JSON as objects, CSV/sheets as tables, databases as query results).
   Inspect top-level keys, tables/sheets, resource groups, time series, cost curves, startup tiers,
   initial-condition fields.
2. Identify the time axis (period count, labels, duration). The input horizon is authoritative; keep
   source period order; every time series must have length T. Keep 0-based internal indexes separate
   from 1-based/timestamped report labels.
3. Identify resource sets (thermal, renewable, storage, imports, zones, reserve products). Keep thermal
   and renewable separate. Treat IDs as opaque strings, preserve source order, never duplicate a
   resource when joining tables (join on the right key).
4. Fill the canonical fields:

| Canonical field | Look for |
| --- | --- |
| time_periods | periods, hours, timestamps, interval count |
| demand [T] | load, system demand, net load (sum zones only if the task is single-zone) |
| reserves [T] | spinning / operating / contingency reserve requirement |
| must_run | forced online, fixed status |
| power_output_minimum / maximum | minimum stable output, maximum output / capacity (MW) |
| ramp_up_limit / ramp_down_limit | MW per period (convert MW/min x period minutes if needed) |
| ramp_startup_limit / ramp_shutdown_limit | max total output in the startup period / the period before shutdown; use pmax if absent |
| time_up_minimum / time_down_minimum | required periods on after start / off after stop |
| unit_on_t0, power_output_t0 | initial status and initial output (0 when off) |
| time_up_t0 / time_down_t0 | periods already on / off before period 1 |
| startup (list of lag, cost) | fixed startup cost, or tiers keyed by prior offline duration (lag in periods) |
| piecewise_production (list of mw, cost) | total cost ($/period) at output breakpoints, first point at pmin, last at pmax |
| renewable_generators (name -> power_output_minimum [T], power_output_maximum [T]) | hourly min/max or forecast bounds |

   Typical shapes: scalars by resource (min up/down, ramp rates, startup ramp, must-run); time series by
   system/zone (demand, reserve); time series by resource (renewable availability, outage status);
   curve/tier tables (startup costs, production-cost breakpoints); nested resource objects.
   Do not confuse reserve, capacity, availability, and dispatch. Thermal outages or time-varying
   availability have no canonical field: extend the model (per-period pmax / forced u = 0) rather than
   dropping them.
5. Cost curves: decide whether points are total cost at breakpoints, marginal/incremental segment cost,
   or heat rate x fuel price, and convert to total cost at breakpoints. A first point at minimum output
   is the online minimum-output cost; do not invent no-load or shutdown costs. Renewables cost zero unless
   the data/task gives a cost (then extend the objective). A single linear
   coefficient c with no-load n becomes two points: (mw=pmin, cost=n + c*pmin) and (mw=pmax, cost=n + c*pmax).
6. Startup tiers: parse thresholds and costs without assuming order; one fixed cost = one tier with lag 1.
7. Production convention: if the source gives output above minimum, convert initial output to actual MW
   (actual = pmin*u + above_min).
8. Check units (MW vs p.u., period duration, ramp units, cost units) before converting anything.

Data the canonical schema cannot express (zones/network, storage, imports, other reserve products,
cost components) must not be dropped silently: either extend scripts/solve_uc.py and validate_uc.py per
references/uc-model.md, or report the limitation. If the data is genuinely inconsistent, fix only what the
prompt justifies and note it.

Return a JSON object with key `data_path` = absolute path of the normalized JSON.
