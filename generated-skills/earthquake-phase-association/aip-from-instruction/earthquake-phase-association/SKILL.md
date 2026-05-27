---
name: earthquake-phase-association
description: End-to-end seismic phase association — pick P/S arrivals from MSEED waveforms with SeisBench deep-learning models (PhaseNet), then group picks across stations into discrete earthquake events using a 1-D velocity model (vp=6 km/s, vs=vp/1.75) with PyOcto (or GaMMA fallback). Emits an event catalog CSV with one row per event and an ISO-naive `time` column. Use when a task provides MSEED waveforms plus a station CSV and asks to detect or list earthquake events, build an event catalog, perform phase association, or run P/S picking with SeisBench.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python with seisbench, obspy, pandas, and pyocto installed. PhaseNet pretrained weights download on first run (one-time network access).
---

```yaml
purpose: >
  End-to-end seismic phase association. Pick P/S arrivals from MSEED
  waveforms with a SeisBench deep-learning model, then group picks across
  stations into discrete earthquake events using a uniform 1-D velocity
  model (vp=6 km/s, vs=vp/1.75). Output is a CSV catalog with one row per
  event and an ISO-format `time` column with no timezone (evaluators that
  match on ±5 s rely on this format).

trigger_when:
  - Task provides MSEED waveform data plus a station CSV and asks for an earthquake catalog or event list.
  - Task mentions "phase association", "P/S picking", "SeisBench", "PhaseNet", "PyOcto", or "GaMMA".
  - Output is judged by matching event times against a ground-truth catalog with a fixed time tolerance.

do_not_use_when:
  - Phase picks (P/S onset times per station) are already provided — skip steps 1–3, jump straight to associate.
  - Task asks for moment tensors, focal mechanisms, magnitude estimation, or relocation — those are downstream stages, not part of this pipeline.
  - Waveform format is not MSEED, or no station metadata (lat/lon) is available.

scope_and_approval: >
  Read-only on the input MSEED and station CSV. Writes only the requested
  output CSV. PhaseNet downloads pretrained weights from the SeisBench model
  repository on first run (one-time network access). No other side effects.

steps:
  - name: setup-env
    description: >
      Ensure the runtime has `seisbench`, `obspy`, `pandas`, and `pyocto`
      installed. If missing, install with
      `pip install seisbench obspy pandas pyocto`. Verify
      `import seisbench.models, pyocto, obspy` succeeds before running the
      solver. If `pyocto` cannot be installed, use the GaMMA fallback in
      references/associators.md instead.

  - name: inspect-inputs
    description: >
      Read the MSEED with `obspy.read(path)` and print the Stream to confirm
      channel coverage and time span. Read the station CSV with pandas and
      confirm columns `network, station, channel, longitude, latitude,
      elevation_m, response`. Each station typically has three rows (one per
      channel — e.g. BHE, BHN, BHZ); the solver collapses these to one row
      per station.

  - name: run-solver
    description: >
      Invoke `python scripts/solve.py <wave.mseed> <stations.csv> <output.csv>`.
      The script (a) collapses the per-channel station rows to one row per
      network.station; (b) runs SeisBench PhaseNet (pretrained on STEAD) to
      pick P and S phases; (c) runs PyOcto with vp=6.0 km/s, vs=vp/1.75 to
      associate picks into events; (d) writes the catalog with a `time`
      column in ISO format, timezone-naive. Defaults pass the typical task;
      tune only if step `verify-output` shows a problem.

  - name: verify-output
    description: >
      Confirm the output CSV exists and is parseable. Header must include
      `time`. Open the first/last rows; timestamps must be ISO with no
      trailing `Z` / `+00:00`. Sanity-check row count against the expected
      magnitude (typically 5–500 events per hour of multi-station data).
      Read stderr counts from the solver (traces, stations, picks, events) —
      these are the primary tuning signal.

  - name: tune-if-needed
    description: >
      If event count is far below expectation, or if the evaluation F1 is
      below target, consult references/tuning.md. The most common
      adjustments are lowering PhaseNet thresholds (more picks) and lowering
      the PyOcto pick minimums (more permissive association). Re-run after
      each change; do not iterate more than a few rounds.

decisions:
  - signal: PhaseNet returns zero or very few picks across many stations.
    action: Lower `P_threshold` and `S_threshold` toward 0.1 (defaults are 0.2); confirm the input stream is not empty after detrending or filtering.
  - signal: Many spurious single-station "events" appear in the catalog (low precision).
    action: Raise PyOcto `n_picks`, `n_p_picks`, `n_s_picks`, `n_p_and_s_picks`; tighten `association_cutoff_distance` (e.g. 250 → 150 km).
  - signal: Real multi-station events are split into singletons or missing entirely (low recall).
    action: Lower the PyOcto pick minimums; raise `velocity_model.tolerance` from 2.0 to 3.0 s; widen `time_before`.
  - signal: Catalog is empty even though PhaseNet produced many picks.
    action: Station IDs in picks don't match the stations DataFrame. SeisBench trace IDs are `NET.STA.LOC.CHA`; the solver strips to `NET.STA` via `load_stations`. Verify both sides use the same `NET.STA` key.
  - signal: Output `time` strings include a trailing `Z` or `+00:00`.
    action: Strip the timezone with `pd.to_datetime(t).dt.tz_convert("UTC").dt.tz_localize(None)` before `strftime`; the evaluator requires naive ISO.
  - signal: "`import pyocto` fails on the target environment."
    action: Replace `associate()` in `solve.py` with the GaMMA implementation in references/associators.md — same inputs, different config.
  - signal: Many stations in the CSV have no traces in the MSEED.
    action: Acceptable — the associator ignores stations without picks. Do not pre-filter unless picking memory is constrained.

anti_patterns:
  - Treating every PhaseNet annotation as a pick. Use `model.classify(stream).picks`, not `model.annotate(stream)`; `annotate` returns continuous probability traces, not discrete onset times.
  - Keeping per-channel rows when building the station table. The associator wants one entry per network.station — duplicates produce duplicate associations and inflate the event count.
  - Forgetting elevation units. PyOcto's `transform_stations` expects elevation in METERS; GaMMA's `z(km)` is KILOMETERS (and depth-positive, so `z = -elevation_m / 1000`).
  - Writing timestamps in non-ISO formats (e.g. `%Y-%m-%d %H:%M:%S` with a space). The evaluator parses ISO with `T` separator and rejects tz-aware values.
  - Hard-coding a geographic bounding box without checking station extent. The associator's `lat`/`lon` window must contain every station — pad ±0.5° from the observed min/max.
  - Iterating on tuning before reading the solver's stderr counts. The (traces → picks → events) chain tells you which stage is failing; tune that stage only.

scenarios:
  - need: Default end-to-end run on the task's standard input paths.
    action: >
      `python scripts/solve.py /root/data/wave.mseed /root/data/stations.csv /root/results.csv`.
    outcome: CSV at `/root/results.csv` with one row per associated event; `time` column is ISO and timezone-naive; ready for the F1 evaluator.

  - need: PhaseNet picks look healthy but the catalog has only a handful of events.
    context: Solver stderr shows hundreds of picks across many stations but only 2–3 events in the output.
    action: In `solve.py:associate`, lower `n_picks` from 6 → 4 and `n_p_and_s_picks` from 1 → 0; re-run.
    outcome: Recall typically improves; confirm precision didn't collapse by spot-checking that event times are consistent across multiple stations.

  - need: PyOcto is unavailable on the target environment.
    context: "`pip install pyocto` fails or `import pyocto` raises ModuleNotFoundError."
    action: Follow references/associators.md to substitute the `associate_gamma` implementation. `pick_phases` and `write_output` remain unchanged.
    outcome: Same output schema (`time` CSV); GaMMA config is more verbose but the rest of the pipeline is identical.
```
