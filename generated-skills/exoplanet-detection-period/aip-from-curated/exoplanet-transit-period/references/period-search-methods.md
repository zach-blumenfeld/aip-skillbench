# Period search: TLS, BLS, Lomb-Scargle

Load this when choosing a period range, re-running a search by hand, or interpreting
TLS/BLS/LS output beyond what the pack's scripts report.

## Which algorithm

| Method | Use when | Strengths | Weaknesses |
|---|---|---|---|
| TLS (`transitleastsquares`) | Searching for transiting planets; transit-shaped dips; you have flux_err | Most sensitive for transits; handles grazing transits; returns transit parameters; robust automatic period grid | Slower than LS/BLS (very long series); only detects transits; less control over transit shape |
| BLS (`astropy.timeseries.BoxLeastSquares`) | Fast alternative/cross-check; need `compute_stats` validation; want fine grid control | Built into astropy; fast for targeted searches; good statistics | Box model; needs a careful period grid; less sensitive to grazing transits |
| Lomb-Scargle (lightkurve `to_periodogram`) | Any periodic signal: rotation, pulsation, eclipsing binaries; quick exploration | Fast; works for any periodic signal | Less sensitive to shallow transits; confuses harmonics with the true period |

TLS generally beats BLS for planets; try both and compare. Use LS before TLS for
initial exploration and for diagnosing stellar variability.

## Period range

- Hot Jupiters 0.5-10 d; warm planets 10-100 d; habitable zone: Sun-like 200-400 d, M dwarf 10-50 d.
- LS ranges: rotation 0.1-100 d, transits 0.5-50 d (most common), EBs 0.1-100 d, pulsation 0.001-1 d.
- Wider range = more complete but slower. Cap at baseline/2 so at least two transits
  fall in the data; adjust to the mission duration and expected planet types.
- Pack: `period_min` / `period_max` = 0 means auto (TLS default minimum, max = baseline/2).

## TLS

```python
from transitleastsquares import transitleastsquares, transit_mask
model = transitleastsquares(t, flux, flux_err)        # flux_err is REQUIRED in practice
res = model.power(period_min=2.0, period_max=7.0, show_progress_bar=False, verbose=False)
res.period, res.period_uncertainty, res.T0, res.depth  # depth = mean in-transit flux (1 - depth = fractional depth)
res.duration, res.snr, res.SDE, res.odd_even_mismatch, res.transit_count, res.distinct_transit_count
res.empty_transit_count, res.per_transit_count, res.transit_times
res.periods, res.power                                 # SDE periodogram
res.folded_phase, res.folded_y, res.model_folded_phase, res.model_folded_model
res.model_lightcurve_time, res.model_lightcurve_model
```
- TLS prints warnings to stdout ("X of Y transits without data. The true period may be
  twice the given period."). Capture stdout when a script must emit JSON.
- Refinement: broad search first, then narrow (+/-2-10% of the candidate, +/-5%
  typical). Narrow range = finer grid = better precision.
- Advanced: `oversampling_factor` (finer period grid, slower; TLS default is 3,
  the pack uses 3 broad / 10 refine), `duration_grid_step` (1.1 default; 1.01 = 1%
  steps, slow), `T0_fit_margin` (default 5; 0 = no margin, faster).
- SDE is normalised over the searched range: a narrow refine window gives a low SDE
  that is NOT comparable to the 6/9 thresholds. Judge strength on the broad search.
- Multi-planet: `mask = transit_mask(t, period, 2*duration, T0)`; search `t[~mask]`
  again; repeat until no significant signal (pack: `search_additional_planets: true`).
  A "second planet" at an integer multiple/fraction of the first is a residual, not a planet.

## BLS

```python
import astropy.units as u
from astropy.timeseries import BoxLeastSquares
bls = BoxLeastSquares(t * u.day, flux, dy=flux_err)
pg = bls.autopower([0.05, 0.1, 0.2] * u.day, objective="likelihood")   # or objective="snr"
periods = bls.autoperiod(durations, minimum_period=1*u.day, maximum_period=10*u.day)
pg = bls.power(periods, durations)                     # custom grid
i = np.argmax(pg.power); P, D, T0 = pg.period[i], pg.duration[i], pg.transit_time[i]
st = bls.compute_stats(P, D, T0)
st["depth"], st["depth_odd"], st["depth_even"], st["depth_phased"], st["per_transit_count"]
```
- `objective="snr"` can be more reliable with correlated noise.
- Grid quality matters more for BLS than for LS: too coarse misses the period. Use
  `autopower` for initial searches, finer grids around candidates.
- Durations must be shorter than the minimum period.
- `compute_stats` has no `depth_snr` key: SNR = `st["depth"][0] / st["depth"][1]`.
  Odd-even check: `abs(depth_odd - depth_even) > 3 * depth_err` means likely not planetary.
- Top peaks: sort `pg.power` descending, take distinct periods, run `compute_stats` on each.

## Lomb-Scargle (lightkurve)

```python
pg = lc.to_periodogram(minimum_period=2.0, maximum_period=15)
pg.period_at_max_power, pg.max_power, pg.frequency_at_max_power
model = pg.model(time=lc.time, frequency=pg.frequency_at_max_power)
pg.plot(view="period")       # default view is frequency (1/period)
```
- Single strong peak: likely the true period. Peaks at P/2 and 2P: harmonics; very short
  periods may be aliases of longer ones.

## Phase folding by hand

```python
phase = ((t - T0) % P) / P
```
