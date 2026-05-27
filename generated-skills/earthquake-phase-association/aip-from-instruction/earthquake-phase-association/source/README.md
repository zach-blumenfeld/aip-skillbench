## Source materials

- `instruction.md` — the task instruction (verbatim copy from
  `vendor/skillsbench/tasks/earthquake-phase-association/instruction.md`).
- `procedure.schema.json` — AIP procedure schema, bundled so the skill is
  self-contained.

## Authoring intent

The task is a fixed three-stage seismic pipeline:

1. Load MSEED waveforms + station CSV.
2. Pick P/S arrivals with SeisBench (deep-learning models).
3. Associate picks across stations into discrete earthquake events using a
   1-D velocity model (`vp=6 km/s`, `vs=vp/1.75`).
4. Emit CSV with a `time` column (ISO, no timezone). Evaluation matches at
   ±5 s; pass threshold is F1 ≥ 0.6.

Because the pipeline is procedural and the same shape every time, the
`procedure` schema is the natural fit — `steps` carry the canonical order,
`decisions` cover the tuning knobs, `anti_patterns` capture the common
output-format and station-id mistakes that silently tank F1.

The skill ships a working `scripts/solve.py` that the agent can run as-is or
adapt. It uses PhaseNet (pretrained on STEAD) for picking and PyOcto for
association — both are the current-standard SeisBench-compatible tools. A
GaMMA fallback is documented in `references/associators.md` for environments
where PyOcto is unavailable.

## Coverage of the source instruction

Every instruction line maps to skill content:

- Input paths (`/root/data/wave.mseed`, `/root/data/stations.csv`) → mentioned
  in `purpose`, `scope_and_approval`, and the default `scenarios` invocation.
- MSEED format → `inspect-inputs` step uses `obspy.read`.
- Station CSV columns → `load_stations` in `solve.py` consumes them; the
  per-channel duplication is called out as an anti-pattern.
- Velocity model (`vp=6`, `vs=vp/1.75`) → hard-coded in `associate()` and
  cited in `purpose`.
- Step 1 (load) → `inspect-inputs`.
- Step 2 (pick with SeisBench) → `run-solver` and `solve.py:pick_phases`.
- Step 3 (associate into events) → `run-solver` and `solve.py:associate`.
- Step 4 (write CSV with ISO `time` column) → `solve.py:write_output`,
  `verify-output` step, anti-pattern on timezone suffix, decision on tz strip.
- Evaluation tolerance / F1 ≥ 0.6 → informs the `tune-if-needed` step and the
  recall/precision decisions, but not surfaced as a literal number (the skill
  shouldn't overfit to the threshold).
