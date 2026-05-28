# Source & authoring notes — seismic-phase-association

## Origin
Authored **from the task instruction alone** (no existing skill was read or
copied). The instruction describes a SkillsBench task: given MSEED waveforms
and a stations CSV, pick P/S phases with SeisBench deep-learning models,
associate the picks into earthquake events using a uniform velocity model
(vp=6 km/s, vs=vp/1.75), and write a catalog to `/root/results.csv` with an
ISO `time` column. Grading: events within 5 s of ground truth count as
matches; F1 ≥ 0.6 to pass.

## Schema choice
Reused the shared **procedure** schema (`procedure.schema.json`,
aip v0.3a2). The task is a linear execution graph (load → pick → associate →
write → tune), which is exactly what `procedure` models. No new schema needed.

## Design decisions
- **One skill, two script nodes.** Picking (GPU deep learning) and association
  (point-process clustering / inversion) are genuinely independent stages with
  a clean intermediate artifact (`picks.csv`), so they are separate scripts but
  one coherent skill.
- **PyOcto as the default associator, with a pure-numpy clustering fallback in
  the same script.** The task hands us a uniform velocity model, which maps
  directly onto PyOcto's homogeneous `VelocityModel0D` and is the modern
  SeisBench-companion associator. Because the sandbox may lack PyOcto or differ
  in API, `associate_events.py` wraps the PyOcto path in try/except and falls
  back to S-P origin-time clustering (numpy/pandas only), guaranteeing the
  pipeline still produces output. GaMMA is documented as a second alternative
  in `references/picking-and-association.md`.
- **All numeric logic lives in scripts** (thresholds, velocity constants, S-P
  distance formula, clustering windows, dedup, tz stripping) per AIP best
  practice — the SKILL body stays an execution graph.
- **Permissive picking, strict association.** Defaults favor recall at the pick
  stage and reject false picks downstream; this is the standard way to trade
  toward higher F1.

## Source content → body classification
- Inputs (`/root/data/wave.mseed`, `stations.csv` columns), velocity model,
  output contract (`/root/results.csv`, `time` ISO no tz, one row/event), the
  4 procedure steps, and the 5 s / F1≥0.6 grading → **Mapped** into
  `trigger_when`, steps, scenarios, anti_patterns, and the scripts/reference.
- Station columns `response` and `channel` and `elevation_m`: `channel` is used
  only to de-dup to one row per station; `elevation` feeds the associator;
  `response`/instrument sensitivity is **deliberately dropped** — it matters for
  amplitude-based magnitude/association, which this task does not require
  (association here is time/velocity based). Noted here per AIP completeness.
- "MSEED is standard format" — **deliberate drop** (general knowledge; ObsPy
  `read` handles it).

## Validation
`uv run scripts/validate.py <this-skill-folder>` (from the aip skill) — body
validates against the bundled procedure schema. Scripts byte-compile.

## Testing limitation
End-to-end functional testing against real seismic data was not possible in the
authoring environment (no `/root/data` waveforms, SeisBench weights, or GPU).
Scripts are written to the real ObsPy/SeisBench/PyOcto APIs with defensive
fallbacks; the PyOcto branch degrades to the dependency-free clustering method
on any error.
