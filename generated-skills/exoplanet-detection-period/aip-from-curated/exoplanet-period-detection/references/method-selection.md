# Period-search method selection

This skill defaults to **Transit Least Squares (TLS)** because the input is
assumed to be a photometric light curve where we care about a *transit-shaped*
signal. If the input is actually non-transit (stellar rotation, pulsation,
eclipsing-binary) you likely want Lomb-Scargle; if TLS is unavailable or
you need a built-in solution, BLS is the alternative.

## Decision matrix

| Signal type / goal                                   | Method              | Why                                          |
|------------------------------------------------------|---------------------|----------------------------------------------|
| Transiting exoplanet, flux_err available (default)   | TLS                 | Fits transit shape; most sensitive           |
| Transit search, cannot install TLS                   | BLS (astropy)       | Built in; box model is good enough           |
| Rotation / pulsation / general periodicity           | Lomb-Scargle        | Fast; agnostic to signal shape               |
| Quick first look to spot *any* periodicity           | Lomb-Scargle        | ~10x faster than TLS                         |
| Grazing / shallow transits                           | TLS                 | Transit-shape fit beats box fit              |

## Why TLS as the default here

- Source `transit-least-squares/SKILL.md`: "most sensitive for transits, handles grazing transits, provides transit parameters."
- Source `exoplanet-workflows/SKILL.md`: "TLS generally performs better than BLS for exoplanet detection."
- Source `box-least-squares/SKILL.md`: "Try both! TLS is often more sensitive, but BLS is faster and built-in."

## When to deviate

The scripts in this skill all run TLS. To switch, either:
1. Replace `scripts/tls_search.py` and `scripts/refine.py` with BLS equivalents
   (`astropy.timeseries.BoxLeastSquares.autopower(...)` with a duration grid), or
2. Run Lomb-Scargle first via `lightkurve.LightCurve.to_periodogram(...)` to find
   the dominant period, then feed that back in as `period_min` / `period_max`
   bounds in the state before `tls-search`.

Both are deliberately out of scope for the default pipeline — the agent
executing this skill may make either call before activating it.
