# Input format and field mapping

Load this when `inspect` exits 2 (schema mismatch) or when you need to know what a field means.

## Canonical schema (what `scripts/uc_milp.py` reads)

pglib-uc style JSON. Units: MW, hours (1 period = 1 hour), $.

```json
{
  "time_periods": 48,
  "demand":   [T floats],              // system load, MW
  "reserves": [T floats],              // spinning reserve requirement, MW
  "thermal_generators": {
    "<name>": {
      "must_run": 0,                    // 1 = online every period
      "power_output_minimum": 30.0,     // pmin, MW (actual output when on)
      "power_output_maximum": 76.0,     // pmax
      "ramp_up_limit": 40.0,            // MW/period, applied to output above minimum (+ reserve)
      "ramp_down_limit": 40.0,
      "ramp_startup_limit": 30.0,       // max TOTAL output (+ reserve) in the startup period
      "ramp_shutdown_limit": 30.0,      // max TOTAL output (+ reserve) in the period before shutdown
      "time_up_minimum": 8,             // periods
      "time_down_minimum": 4,
      "power_output_t0": 30.0,          // actual MW in the period before the horizon
      "unit_on_t0": 1,
      "time_up_t0": 168,                // periods already on at t0 (0 if off)
      "time_down_t0": 0,                // periods already off at t0 (0 if on)
      "startup": [{"lag": 4, "cost": 7144.02}, {"lag": 10, "cost": 10276.95}],
      "piecewise_production": [{"mw": 30.0, "cost": 751.27}, {"mw": 76.0, "cost": 1819.67}]
    }
  },
  "renewable_generators": {
    "<name>": {"power_output_minimum": [T], "power_output_maximum": [T]}
  }
}
```

Extra keys (e.g. a `name` field duplicating the dict key) are ignored. The dict key is the
reporting name; source order of the dicts is the report order.

Field semantics the script relies on:
- `piecewise_production` is **total cost** ($/h) at output breakpoints. The first point sits at
  pmin and is the online minimum-output cost; the last at pmax. No extra no-load cost exists.
- `startup` tiers are keyed by **prior offline duration**: the tier used is the one with the
  largest `lag` not exceeding the number of periods offline before the startup period (first
  tier if none). Initially-off units have been off `time_down_t0` periods at t0.
- Renewables: output anywhere in `[min, max]` per hour (curtailment allowed); min == max means
  fixed. Zero cost. Renewable headroom is never spinning reserve.
- Initial obligations: an on unit must stay on for `max(0, time_up_minimum - time_up_t0)`
  periods; an off unit must stay off `max(0, time_down_minimum - time_down_t0)` periods.

## Concept map for other schemas

Map by meaning, units, and shape, not by name. The prompt and the data are the source of truth.

| UC concept | Look for | Canonical field |
| --- | --- | --- |
| Horizon | periods, hours, timestamps, interval count | `time_periods` |
| Demand | load, system demand, net load, zone load (sum zones for single-zone) | `demand` |
| Reserve requirement | spinning, operating, contingency reserve | `reserves` |
| Commitment status at t0 | on/off, online, active, unit status | `unit_on_t0` |
| Output limits | minimum stable output, maximum output, availability | `power_output_minimum/maximum` |
| Ramping | ramp up/down, startup/shutdown capability | `ramp_*_limit` |
| Minimum up/down | required duration after start/stop | `time_up/down_minimum` |
| Initial conditions | initial output, time already on/off (often one signed `initial_status`: +h on, -h off) | `power_output_t0`, `time_up_t0`, `time_down_t0` |
| Must-run | forced online, fixed status | `must_run` |
| Startup data | fixed cost or tiers by prior offline duration | `startup` (a fixed cost = one tier, lag 1) |
| Production cost | linear coefficients, heat rate, piecewise or total-cost curves | `piecewise_production` (total cost) |
| Renewable availability | hourly min/max output or forecast | renewable min/max series |

Converting other conventions to `piecewise_production` (total cost at breakpoints):
- marginal/incremental segment costs: cumulate `cost(pmin) + Σ slope_k * width_k`;
- linear `a + b*P`: two points `(pmin, a+b*pmin)`, `(pmax, a+b*pmax)`;
- heat-rate curve: multiply heat rate × output × fuel price per breakpoint;
- a missing ramp limit means unlimited: use pmax; missing startup/shutdown limit: use pmax.

Keep these separate when converting:
- total output vs output above minimum (`actual = pmin*u + above_min`);
- reserve vs capacity vs availability vs dispatch;
- thermal vs renewable sets; never merge or duplicate resources when joining tables (join on
  the resource ID; treat IDs as opaque strings, and keep 0-based internal indexes separate from
  1-based or timestamped report labels);
- do not rescale or drop data; check power, period-duration, ramp-rate (per minute vs per
  period), and cost units before converting anything.

After writing the converted JSON, rerun `inspect` on it; it must exit 0 before `solve`.
