# Tuning the phase-association pipeline

Read this when default `solve.py` parameters produce too few or too many
events, or when F1 against the ground truth is below target.

## Knob 1 — PhaseNet pick thresholds

In `pick_phases(stream, p_threshold, s_threshold)`:

- Defaults: `P_threshold=0.2`, `S_threshold=0.2`.
- Lower (e.g. `0.1`) → more raw picks, higher recall on small events.
- Higher (e.g. `0.3`) → fewer picks, less noise, lower recall.

Symptom: `PhaseNet produced N picks` (in stderr) is much smaller than
`#stations × #expected events × ~2` → lower the thresholds first.

## Knob 2 — PyOcto minimum-pick requirements

In `associate(picks, stations)`, in the `OctoAssociator.from_area(...)` call:

| Parameter             | Default | Meaning                                                |
|-----------------------|---------|--------------------------------------------------------|
| `n_picks`             | 6       | Total picks (P+S across stations) required per event.  |
| `n_p_picks`           | 2       | Minimum P picks across distinct stations.              |
| `n_s_picks`           | 1       | Minimum S picks across distinct stations.              |
| `n_p_and_s_picks`     | 1       | Minimum stations with BOTH P and S.                    |

- Raise these → fewer, higher-confidence events (precision↑, recall↓).
- Lower these → more events, including small ones (recall↑, precision↓).

Symptom: many single-blip "events" near one station → raise `n_picks`
and/or `n_p_and_s_picks`.

Symptom: real multi-station events split into singletons → lower `n_picks`.

## Knob 3 — Velocity-model tolerance

In `pyocto.VelocityModel0D(..., tolerance=2.0)`:

- Travel-time slack in seconds. The associator considers a pick consistent
  with a hypocenter if its arrival is within `tolerance` of the predicted
  travel time.
- Raise (e.g. `3.0`) when the uniform `vp=6 km/s` is too lossy for the real
  geology and arrivals look "off" by a few seconds.
- Lower (e.g. `1.0`) when noise is producing chimera events.

## Knob 4 — Association cutoff distance

`association_cutoff_distance` (km) caps station-event separation. Default
`250.0`. If station array is dense and local (<100 km), tightening to `150`
removes spurious far-field associations.

## Knob 5 — Region padding and depth window

`from_area(lat=..., lon=..., zlim=(0, 60), time_before=300)`:

- `lat`/`lon` window is padded ±0.5° from station extent. Widen only if
  events are expected outside the array (offshore, regional).
- `zlim` caps hypocentral depth in km. Increase to `100` for deep tectonic
  zones.
- `time_before` (seconds) sets how far before the first pick the associator
  searches for origin time. Widen for distant events.

## Diagnostic loop

1. Run `solve.py` and read the stderr counts (`traces`, `stations`, `picks`,
   `events`).
2. If `picks` is low → adjust Knob 1.
3. If `picks` is healthy but `events` is low → adjust Knob 2 (down) and
   Knob 3 (up).
4. If `events` is high but F1 is bad → likely precision problem; adjust
   Knob 2 (up) and Knob 4 (down).
5. Re-run; iterate at most a few rounds. Don't chase noise.

## Output-format pitfalls (silent F1 killers)

- Timestamps with a trailing `Z` or `+00:00` — the evaluator expects naive
  ISO. `solve.py` strips this; preserve that step in any rewrite.
- Wrong column name — must be `time` (lowercase). Extra columns are fine.
- Empty rows / NaT — `solve.py` drops NaT after coercion; keep that.
