---
name: transit-period-finder
description: Finds the orbital period of a transiting exoplanet hidden under strong stellar variability (rotational starspot modulation, pulsation) in a TESS/Kepler-style light curve text file. It quality-filters on flags, clips outliers, removes the variability (iterative sine fitting plus a Savitzky-Golay flatten), searches with Transit Least Squares and cross-checks with Box Least Squares, vets aliases (P/2, 2P, the rotation period, single events), refines the period with a transit-model fit, and writes it rounded to N decimals. Use when asked to detect a transit, find or measure a planet's period, or detrend a light curve before a TLS/BLS/Lomb-Scargle period search.
compatibility: Python 3 with numpy, scipy, astropy, lightkurve 2.4, transitleastsquares 1.32 and batman-package (all present in the python:3.12-slim task image). No network needed.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Turn a raw light curve (time, normalized flux, quality flag, flux error) whose transits are
  buried under percent-level stellar variability into one vetted, model-refined orbital period.
  The skill encodes what an unaided agent gets wrong: clipping outliers against the raw flux
  (which removes variability troughs and the transits in them), flattening with a window that
  either eats the transits or lets a fast rotator through, trusting TLS's coarse grid period
  to 5 decimals, mistaking the rotation period, a harmonic, an alias or a single event for the
  planet, and using `compute_stats` keys that do not exist in astropy 6. All the numerical work
  is in one script, `scripts/transit_period.py`, with three subcommands (inspect, search,
  refine), each printing a JSON report. Commands below are run from the skill folder. Use a
  scratch work dir such as /tmp/tp, never the skill folder. API details, thresholds and
  troubleshooting are in references/methods.md; read it only when a step below says to.

trigger_when:
  - A task gives a light curve file and asks for the period of a transiting exoplanet.
  - Stellar activity, rotation, starspots or pulsation is hiding a transit signal that must be removed first.
  - Asked to filter quality flags and outliers, detrend or flatten, then run TLS, BLS or a periodogram on TESS, Kepler or K2 photometry.
  - Validating a transit candidate (SDE, SNR, odd/even, aliasing) or refining its period precision.
  - Searching for an additional planet after masking a known one.

do_not_use_when:
  - The goal is the stellar rotation or pulsation period itself. Use a Lomb-Scargle periodogram (inspect reports it) and skip the transit steps.
  - The data are radial velocities or eclipsing-binary light curves where full eclipse modelling is wanted.
  - Only a target name is given with no light curve file. Fetching data from MAST is out of scope.

scope_and_approval: >
  Read-only on the input light curve. Writes JSON reports to the work dir and the single
  answer file named by the task. Runs offline. Expect TLS to take about 10 to 60 s per
  search, depending on cores.

steps:
  - name: read-task
    description: >
      From the task statement, extract: the light-curve path, the column order (default
      time, flux, flag, flux_err), what flag value means good data, the output file path, the
      required rounding (decimals) and units. If a column is missing, plan `--cols` with -1 for
      it (for example `--cols 0,1,2,-1` when there is no error column; errors are then estimated
      from the scatter). Paths in the task are container paths. Use them exactly.
    outputs:
      - {name: lc-path, type: string}
      - {name: cols, type: string, description: "time,flux,flag,err indices, default 0,1,2,3"}
      - {name: flag-good, type: string, description: "zero (TESS default) or nonzero"}
      - {name: answer-path, type: string}
      - {name: decimals, type: integer}

  - name: inspect
    description: >
      `mkdir -p /tmp/tp && python3 scripts/transit_period.py inspect --lc <lc-path> --cols <cols> --out /tmp/tp/inspect.json`.
      Reports row count, flag value counts with the point-to-point scatter of the flag==0 and
      flag!=0 subsets, NaNs and bad errors, cadence, gaps, baseline, the Lomb-Scargle
      variability period and amplitude, the recommended flatten window (P_rot/4 clamped to
      [0.25, 0.75] d) and the maximum searchable period (baseline/2).
    script: scripts/transit_period.py
    inputs:
      - {name: lc-path, type: string}
      - {name: cols, type: string}
    outputs:
      - {name: inspect-report, type: object}

  - name: choose-preprocessing
    description: >
      Decide the search settings. Flag convention: follow the task statement. If it is silent,
      the good subset is the one with the far smaller point-to-point scatter (conventions vary
      by source, and junk data shows tens of times more scatter). If every flag is 0 there is
      nothing to filter, which is normal. Period range: the default 0.5 d to baseline/2
      guarantees at least 2 transits. Narrow it only if the task gives a range. Window: keep the
      default unless the task or the inspect report argues otherwise. It must be several transit
      durations long and well under the variability period. Pre-whitening (`--prewhiten 10`,
      the default) removes up to 10 coherent sinusoids before flattening; keep it on.
    inputs:
      - {name: inspect-report, type: object}
    outputs:
      - {name: search-args, type: string, description: "extra flags: --flag-good, --period-min/max, --window-days"}

  - name: search
    description: >
      `python3 scripts/transit_period.py search --lc <lc-path> --cols <cols> --flag-good <flag-good> [search-args] --out /tmp/tp/search.json`.
      Pipeline: quality filter, drop NaNs, normalise, iterative sine fitting, then outlier clipping
      against the local trend (3σ high; low points only if >10σ and isolated, so transits
      survive), Savitzky-Golay flatten, TLS over the period range, and BLS at 0.6×, 1× and 1.6×
      the window. Reports the TLS candidate (period, T0, duration, depth, SDE, SNR, odd/even,
      transit counts), the top 5 independent TLS peaks, the BLS periods, the BLS depth/odd-even
      stats at P, 2P and P/2, per-transit depths, P/P_rot, and a `flags` list of warnings.
    script: scripts/transit_period.py
    inputs:
      - {name: lc-path, type: string}
      - {name: search-args, type: string}
    outputs:
      - {name: search-report, type: object}

  - name: vet-candidate
    description: >
      Judge the candidate from search-report.validation. Accept it when SDE ≥ 9 (≥ 6 is a
      candidate), SNR ≥ 7, it has ≥ 2 transits with data, odd/even < 3σ, the BLS windows
      agree, each per-transit depth is positive and similar, and P is not within 2% of a
      multiple or fraction of the variability period. A `flags` entry about predicted
      transits falling in gaps is informational when at_2P has fewer transits and a lower depth
      SNR than at_P. For other flags, pick the action below and repeat search. Read
      references/methods.md (troubleshooting table) when the right action is unclear.
    inputs:
      - {name: search-report, type: object}
    outputs:
      - {name: candidate, type: object, description: "period, t0, duration (from search.json or edited)"}
    one_of:
      - "Accept: the TLS candidate passes and refine uses /tmp/tp/search.json."
      - "Alias: odd/even > 3σ (true period 2P), or the P/2 flag with consistent odd/even (true period P/2). Refine with --period/--t0/--duration set to the alias."
      - "Stellar residual: P is near the variability period or a harmonic of it, or the BLS windows disagree. Rerun search with --prewhiten 20 and/or --window-days set to about 0.6× the current window."
      - "Single event or artifact: < 2 transits with data, or one epoch carries all the depth. Rerun search with --mask P,T0,3*DUR to remove it and take the next peak."
      - "Too weak: SDE < 6 after the above. Retry with a longer window (≤ P_rot/3), compare against a --prewhiten 0 run, take whichever gives the higher SDE with consistent per-transit depths, and state the caveat."

  - name: refine
    description: >
      `python3 scripts/transit_period.py refine --lc <lc-path> --cols <cols> --flag-good <flag-good> [same --window-days/--prewhiten as search] --search /tmp/tp/search.json --decimals <decimals> --write <answer-path> --out /tmp/tp/refine.json`.
      To refine an edited candidate, pass `--period P --t0 T0 --duration D` instead of
      `--search`. Steps: re-flatten with the transits masked (3× duration) so the filter cannot
      shallow or shift them; least-squares fit of a quadratic limb-darkened batman model
      (P, T0, Rp/R*, a/R*, b) over the transit windows; dense BLS around P as a cross-check
      (and the fallback if the fit fails); then a reliability gate. Writes the period rounded to
      `decimals` as a single line.
    script: scripts/transit_period.py
    inputs:
      - {name: candidate, type: object}
      - {name: answer-path, type: string}
      - {name: decimals, type: integer}
    outputs:
      - {name: refine-report, type: object}
      - {name: answer-file, type: string}

  - name: check-answer
    description: >
      Require `reliable: true` in refine-report. If it is false, read `unreliable_reasons`,
      return to vet-candidate, and do not ship the number. A fit/BLS disagreement or depth SNR
      < 7 means a wrong candidate; reduced χ² > 5 means a wrong flag convention or bad
      detrending. Confirm the model fit's period_err is far smaller than 10^-decimals × 5 or
      note the precision limit. Then `cat <answer-path>`: it must be one number in days with
      exactly `decimals` decimals and no units or extra text. Report the period, its error,
      SDE/SNR and the transit count.
    inputs:
      - {name: refine-report, type: object}
      - {name: answer-file, type: string}
    outputs:
      - {name: final-period, type: float}

modes:
  - name: single-planet
    body: >
      Default. Report the strongest vetted transit signal.
  - name: additional-planets
    body: >
      After the first planet is refined, rerun search with `--mask P,T0,3*DUR` (repeatable,
      using the refined P and T0) and vet again. Stop when SDE < 6 or < 2 transits remain.
      Report each planet separately; the task's "the planet" means the strongest.

scenarios:
  - need: Active star with ~1.4 d spot modulation (1.3% peak to peak) hiding a shallow (~0.2%) transit, all flags 0, one mid-sector gap.
    action: >
      inspect recommends a ~0.35 d window. search gives one TLS peak with SDE > 15, 4 transits
      with similar depths, and one predicted transit in the gap (flagged; at_2P is worse, so
      kept). A secondary TLS peak at a longer period is a single event (1 transit with data) and
      is ignored. refine moves the period by ~0.0015 d from the TLS grid value, with a fit error
      of ~0.0003 d, and is reliable.
    outcome: The TLS grid value alone would be wrong in the third decimal place; the refined value is written.
  - need: Fast rotator (0.9 d) with a strong first harmonic.
    context: Without pre-whitening, the flatten window cannot follow a 0.45 d harmonic, and TLS locks onto the rotation period (flags show P ≈ 1× P_rot and the BLS windows disagree).
    action: Pre-whitening removes 4 sinusoids, after which TLS finds the planet with SDE ~20 and every BLS window agrees.
  - need: Quality flag convention inverted (non-zero means good).
    context: inspect shows the flag==0 subset has ~25× the scatter of the flag!=0 subset.
    action: Run with --flag-good nonzero. With the wrong convention, refine reports unreliable (reduced χ² of hundreds, negative depth SNR).

anti_patterns:
  - Do not sigma-clip the raw flux symmetrically. Variability troughs (and the transits in them) get clipped. Clip residuals from the trend, and only isolated low points.
  - Do not run a lower 3σ clip after flattening. Transit points sit 1 to 3σ low and would be deleted. The script clips high at 3σ and low only for isolated spikes above 10σ.
  - Do not reuse a flatten window from another dataset. Long windows (500+ cadences at 2-min on a ~1.4 d rotator) let the rotation through and BLS locks onto it; very short ones (< 3 transit durations) shallow the transit.
  - Do not report TLS's `period` to 5 decimals. It is a grid value with uncertainty ~0.01 d. Refine with the model fit.
  - Do not use `compute_stats()['depth_snr']`, `['depth_err']` or `['transit_count']`. They do not exist in astropy 6. Use depth[0]/depth[1] and per_transit_count.
  - Do not omit flux_err from TLS/BLS. If the file has no error column, estimate it (the script does).
  - Do not run iterative sine fitting on the flattened series you search, or with dozens of terms blindly. The script stops once the amplitude falls below the flux error.
  - Do not run TLS from an unguarded script (no `if __name__ == "__main__":`). Its multiprocessing re-executes the file under spawn.
  - Do not hardcode a period, epoch or window from a previous run. Every number must come from the file in hand.
  - Do not write extra text, units or a different rounding to the answer file.
```
