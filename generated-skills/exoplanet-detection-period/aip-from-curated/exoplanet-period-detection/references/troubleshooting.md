# Troubleshooting weak or suspicious detections

Load this when the `classify` decision returns `weak` or `moderate`, or
whenever the reported period looks implausible.

## Low SDE (< 6)

Likely causes, in order of frequency:

1. **Over-aggressive preprocessing is eating the transit.** Two sub-cases:
   - Flattening with a window shorter than the transit duration absorbs the
     dip. The `preprocess` script picks ~16 hours of coverage; raise it to
     24–36 hours by editing `preprocess.py` if the transits are long.
   - A symmetric sigma clip removes in-transit points before the search.
     This script already uses asymmetric clipping (`sigma_lower=np.inf` on
     both passes) to avoid it — if you have modified the script to add
     symmetric low-side clipping and your period came back at 2x the true
     value with low depth, revert that change.
2. **Transit depth is near the noise floor.** For Earth-sized planets in
   TESS data, SDE ~5–6 can still be a real detection; validate with
   phase-folding and multi-sector stacking before dismissing.
3. **Period is outside the search window.** Default is
   `max(0.5 d, 3 x cadence)` to `min(50 d, baseline/2)`. For long-period
   candidates the baseline/2 cap may be the problem — supply a wider
   `period_max` only if there are at least two full transits in the data.
4. **Data gaps during transits** cause TLS to under-count transits. Expect
   a warning like "X of Y transits without data"; the true period may be
   twice the reported one.

## Period is 2x or 0.5x expected

Classic aliasing. Rule-of-thumb checks:

- **Odd/even depth mismatch** at the reported period but matched at `period*2`
  → the true period is `period*2` and the "transits" are the two eclipses
  of an eclipsing binary. BLS's `compute_stats()` returns `depth_odd` and
  `depth_even`; `|depth_odd - depth_even| > 3 * depth_err` is the gate.
- **Phase-folded gaps** at the reported period that vanish at `period*2`
  → the alternate transits fell in data gaps; prefer `period*2`.

Both cases: re-run `tls-search` with `period_min` / `period_max` bracketed
tightly around `period*2` and compare SDE.

## Flux_err required error from TLS

Non-negotiable per source `transit-least-squares`: TLS crashes without
flux uncertainties. The `load_qc` script drops any cadence with
non-positive `flux_err`; if your input file has an all-zero flux-error
column you must synthesise one (e.g. the standard deviation of the
flattened residuals) before this skill will run.

## Expected transit depths for sanity-checking

| Planet class     | Depth (relative flux) |
|------------------|-----------------------|
| Hot Jupiter      | 0.01 – 0.03           |
| Super-Earth      | 0.001 – 0.003         |
| Earth-sized      | 0.0001 – 0.001        |

A reported depth outside this range for the stated SDE is a red flag.
