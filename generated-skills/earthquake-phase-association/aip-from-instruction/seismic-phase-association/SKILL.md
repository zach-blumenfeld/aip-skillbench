---
name: seismic-phase-association
description: >
  Build an earthquake catalog from raw seismograms by deep-learning phase
  picking and phase association. Use when given MSEED waveform data plus a
  station table and asked to detect/associate earthquakes, find common events
  across stations, pick P and S waves, or produce a list of event origin times.
  Covers SeisBench (PhaseNet/EQTransformer) picking, PyOcto/GaMMA association
  with a uniform velocity model, and writing an ISO-time event catalog CSV.
compatibility: >
  Python with obspy, seisbench (downloads pretrained weights on first use),
  pandas, numpy. pyocto recommended for association (pip install pyocto); the
  pipeline falls back to a dependency-free clustering associator otherwise. GPU
  optional but speeds up picking. Network or warm cache needed for model weights.
license: Apache-2.0
allowed-tools: Bash Read Write Edit
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Turn raw seismograms into an earthquake catalog. Given MSEED waveforms and a
  station table, pick P and S phases with SeisBench deep-learning models, then
  associate the picks into distinct earthquake events using a uniform velocity
  model, and write a unique list of event origin times. Adds the specific
  tooling (SeisBench picking, PyOcto/clustering association), the velocity model
  wiring, the pick<->station id matching, and the output/grading contract that a
  general agent would otherwise get wrong.

trigger_when:
  - Given MSEED/seismic waveform data and a station CSV and asked to find,
    detect, or catalog earthquake events.
  - Asked to perform "phase association" or to group picks/waveforms across
    stations into common events.
  - Asked to pick P and S waves from seismograms with deep learning (SeisBench,
    PhaseNet, EQTransformer).
  - Asked to produce a list of earthquake events with origin times / timestamps.

do_not_use_when:
  - The task is single-station phase picking only, with no association into
    events.
  - The task needs full location/magnitude inversion or focal mechanisms beyond
    producing event origin times.
  - No waveform data is available (only an existing catalog to analyze).

scope_and_approval: >
  Reads the waveform and station files; writes a picks CSV (intermediate) and
  the final events catalog (default /root/results.csv). May need to
  `pip install pyocto` and to download SeisBench model weights on first use.
  These are expected, non-destructive setup actions for this task; proceed
  without extra confirmation unless the environment forbids installs or network.

steps:
  - name: load-and-inspect
    description: >
      Read the MSEED stream with obspy.read and the station table with pandas.
      Confirm traces loaded (len(stream) > 0) and note the station id format
      (network.station) and lat/lon extent. Velocity model is fixed: vp=6 km/s,
      vs=vp/1.75.
    inputs:
      - name: waveform-path
        type: string
        description: Path to MSEED file (e.g. /root/data/wave.mseed).
      - name: stations-path
        type: string
        description: Path to stations.csv (network, station, channel, longitude, latitude, elevation_m, response).
    outputs:
      - name: load-ok
        type: boolean
        description: Stream non-empty and stations parsed.

  - name: pick-phases
    description: >
      Run a SeisBench model over the stream to detect P and S arrivals. Defaults
      to PhaseNet with permissive thresholds (favor recall; the associator drops
      false picks). Writes one row per pick with the network.station id.
    script: scripts/pick_phases.py
    depends_on: [load-and-inspect]
    inputs:
      - name: waveform-path
        type: string
      - name: stations-path
        type: string
    outputs:
      - name: picks-csv
        type: string
        description: CSV with columns trace_id, station, phase (P/S), time (ISO, no tz), probability.

  - name: associate-events
    description: >
      Associate the picks into distinct events with a uniform velocity model.
      Default tries PyOcto (homogeneous VelocityModel0D) and falls back to S-P
      origin-time clustering. Produces a deduplicated catalog and writes the
      required output CSV.
    script: scripts/associate_events.py
    depends_on: [pick-phases]
    inputs:
      - name: picks-csv
        type: string
      - name: stations-path
        type: string
    outputs:
      - name: results-csv
        type: string
        description: Events catalog at /root/results.csv with a `time` column, one row per event.

  - name: validate-output
    description: >
      Confirm results.csv exists, has a `time` column in ISO-8601 with NO
      timezone, one row per event, and a plausible event count (not zero, not
      wildly inflated). Spot-check that times parse and are unique within a few
      seconds.
    depends_on: [associate-events]
    inputs:
      - name: results-csv
        type: string
    outputs:
      - name: output-ok
        type: boolean

  - name: tune-if-needed
    description: >
      If event count looks wrong or F1 is below target, tune one knob at a time
      and re-run. For low recall: lower pick thresholds, try other SeisBench
      weights/model, lower --min-stations / PyOcto n_*picks. For low precision:
      raise pick thresholds, raise --min-stations, raise --dedup. Re-run only
      associate_events.py when tuning association. See
      references/picking-and-association.md for full guidance and the GaMMA
      alternative.
    depends_on: [validate-output]
    outputs:
      - name: final-catalog
        type: string

search_shortcuts:
  - category: Phase pickers (SeisBench)
    body: >
      seisbench.models.PhaseNet (default; fast, robust), EQTransformer (joint
      detect+pick), GPD. Load with .from_pretrained(weights) where weights is
      one of instance, stead, ethz, scedc, neic, geofon. Use model.classify
      (stream, P_threshold=, S_threshold=) -> outputs.picks (peak_time, phase,
      peak_value, trace_id).
  - category: Associators
    body: >
      PyOcto (pyocto.OctoAssociator + VelocityModel0D) — default, homogeneous
      velocity model, inverts for origin time, handles P-only stations. GaMMA
      (gamma.utils.association) — GMM associator, needs a local x/y/z projection
      via pyproj; see reference. Built-in S-P origin-time clustering — no extra
      deps, fallback.
  - category: I/O
    body: >
      obspy.read for MSEED; pandas for stations.csv and the output catalog.
      Output time must be ISO-8601 without timezone.

scenarios:
  - need: >
      /root/data/wave.mseed + /root/data/stations.csv; produce /root/results.csv
      of earthquake events.
    context: >
      stream reads with hundreds of traces across ~tens of stations; uniform
      velocity model vp=6, vs=6/1.75 given.
    action: >
      python scripts/pick_phases.py --waveform /root/data/wave.mseed --stations
      /root/data/stations.csv --out picks.csv; then python
      scripts/associate_events.py --picks picks.csv --stations
      /root/data/stations.csv --out /root/results.csv.
    outcome: >
      results.csv with one `time` row per associated event, ISO without tz,
      matched within 5 s of ground truth for F1 scoring.
  - need: Too few events detected; recall looks low.
    action: >
      Re-pick with lower thresholds (--p-threshold 0.1 --s-threshold 0.1) or a
      different --weights; re-associate with --min-stations 2.
    outcome: More events recovered without re-running the expensive picking blindly.
  - need: PyOcto not installed in the sandbox.
    action: >
      Run associate_events.py as-is; it catches the import failure and falls
      back to S-P origin-time clustering automatically (or pip install pyocto if
      allowed).
    outcome: A catalog is still produced from the same picks.

anti_patterns:
  - Writing event times with a timezone suffix or as non-ISO strings — the
    grader expects ISO-8601 without timezone.
  - Treating each station row as a separate station — stations.csv has one row
    per channel; de-duplicate to one row per network.station before association.
  - Emitting one row per pick or per station instead of one row per associated
    event.
  - Skipping association and reporting raw picks as events.
  - Setting pick thresholds so high that small events are never picked (picking
    is the recall ceiling), or emitting many near-duplicate events that wreck
    precision.
  - Hand-coding a velocity/location inversion when a homogeneous-model
    associator (PyOcto/GaMMA) already fits the given uniform velocity model.
```
