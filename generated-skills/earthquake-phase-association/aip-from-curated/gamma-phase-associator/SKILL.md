---
name: gamma-phase-associator
description: Run the GaMMA earthquake phase-association algorithm — cluster P/S phase picks plus station metadata into earthquake events with origin time, hypocenter location, and magnitude via Bayesian or standard Gaussian Mixture Models (unsupervised clustering + Expectation-Maximization). Use when associating seismic phase picks into events, building an earthquake catalog from picker output, or when the user mentions GaMMA, phase association, the `association` or `estimate_eps` functions, or needs event times/locations from P and S picks. Covers the picks/stations DataFrame schemas, the config dict keys, DBSCAN eps estimation, and the (events, assignments) output format.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 with the GaMMA library (pip install git+https://github.com/wayneweiqiang/GaMMA.git), pandas, and pyproj. Build-config script is stdlib-only.
---

```yaml
purpose: >
  Run GaMMA phase association: take P/S phase picks and station metadata and,
  through unsupervised clustering, group picks into earthquake events with
  source information (hypocenter location, origin time, and magnitude). GaMMA
  models each event's picks with a multivariate Gaussian and uses
  Expectation-Maximization to assign picks and estimate source parameters; it
  is exposed as the `gamma.utils.association` function with a companion
  `estimate_eps` helper for DBSCAN pre-clustering. Beyond general agent
  knowledge this skill supplies the exact `picks`/`stations` DataFrame schemas
  GaMMA requires, the full config-dict key reference, the documented defaults
  and the BGMM/GMM oversample rule (encoded in a config-builder script), and
  the shape of the `(events, assignments)` return value.

trigger_when:
  - Associating seismic P/S phase picks into earthquake events (clustering picks that belong to the same event).
  - Building an earthquake catalog (unique events with timestamps and locations) from phase-picker output.
  - Estimating event origin time, hypocenter, or magnitude from picks plus station coordinates.
  - User mentions GaMMA, phase association, BGMM/GMM phase clustering, or the `association` / `estimate_eps` functions.
  - Choosing or tuning a DBSCAN `eps` for pre-clustering picks before association.

do_not_use_when:
  - You still need to detect or pick P/S phases from raw waveforms — that is a picker's job (e.g. a SeisBench/PhaseNet model); return here once picks exist.
  - The task is single-station event detection with no association/clustering across stations.
  - A different associator (e.g. REAL, PyOcto) is explicitly required — the config keys and I/O here are GaMMA-specific.

scope_and_approval: >
  Read-and-compute: GaMMA reads the picks and stations DataFrames and computes
  events in memory; it performs no destructive operations. Writing the
  resulting event catalog to a file is done by the agent, not by GaMMA. Safe
  to run without prompting. Installing the GaMMA package from its git URL is a
  network/install action — proceed if the environment permits package installs.

steps:
  - name: install-gamma
    description: >
      Ensure the GaMMA library is importable. If not installed, run
      `pip install git+https://github.com/wayneweiqiang/GaMMA.git`. The public
      API is `from gamma.utils import association, estimate_eps`. pandas and
      pyproj are also needed for the DataFrame prep and coordinate projection.
    outputs:
      - name: gamma-available
        type: boolean
        description: True once `from gamma.utils import association, estimate_eps` succeeds.

  - name: prepare-stations
    description: >
      Build the `stations` DataFrame with the columns GaMMA requires: `id`,
      `x(km)`, `y(km)`, `z(km)`. Construct `id` to match the picks (commonly
      `network.station.` or `network.station.location.channel`). Project each
      station's longitude/latitude into a local km coordinate system with
      pyproj (e.g. an azimuthal-equidistant projection centered on the region
      origin) to get `x(km)`/`y(km)`; set `z(km)` from elevation as
      `-elevation_m / 1000` (depth-positive, so elevation is negative). Collapse
      to one row per `id`: identical attributes become a single value,
      conflicting metadata is preserved as a sorted list —
      `stations.groupby("id").agg(lambda x: x.iloc[0] if len(set(x)) == 1 else sorted(list(x))).reset_index()`.
      This step stays prose because the source CSV's column names and the
      projection origin are task-specific (not known at authoring time). Full
      column schema and notes are in references/association-api.md.
    depends_on: [install-gamma]
    inputs:
      - name: raw-stations
        type: object
        description: Source station metadata (e.g. a CSV with network/station/channel/longitude/latitude/elevation columns).
      - name: projection-origin
        type: object
        description: Region reference (longitude0, latitude0) used to build the local km projection.
    outputs:
      - name: stations
        type: object
        description: DataFrame with id, x(km), y(km), z(km), one row per station id.

  - name: prepare-picks
    description: >
      Build the `picks` DataFrame with columns `id`, `timestamp`, `type`,
      `prob`, and (only if `use_amplitude=True`) `amp`. `id` MUST exactly match
      the stations' `id` — pick one convention (e.g. `network.station.`) and
      apply it to BOTH frames. Pickers often emit a fuller trace id like
      `network.station.location.channel` (e.g. "CI.CCC..BHZ"), so normalize it
      down to the station-level id you used for stations; if the two formats
      differ, association silently drops every pick and you get zero events.
      `timestamp` must be UTC — a naive/tz-stripped UTC datetime or an ISO
      string like "2019-07-04T22:00:06.084" both work. `type` is the lowercase
      phase `"p"`/`"s"`; `prob` is the pick weight in 0-1. The DataFrame index
      tracks pick identity in the output `assignments`. When
      `use_amplitude=True`, GaMMA filters picks with `amp == 0` or `amp == -1`.
      This step stays prose because the picks come from a task-specific picker
      output. Full column schema in references/association-api.md.
    depends_on: [install-gamma]
    inputs:
      - name: raw-picks
        type: object
        description: Phase picks from a picker (per pick - station id, arrival time, phase type, probability, optional amplitude).
    outputs:
      - name: picks
        type: object
        description: DataFrame with id, timestamp, type, prob, optional amp.

  - name: build-config
    description: >
      Assemble the GaMMA `config` dict with scripts/build_gamma_config.py. It
      encodes the documented defaults and rules so the config is consistent:
      the method->oversample_factor rule (BGMM=5.0, GMM=1.0), numeric defaults
      (min_picks_per_eq=5, max_sigma11=2.0, max_sigma12=1.0, dbscan_min_samples=3,
      vel={"p":6.0,"s":3.47}), bfgs_bounds built in the documented
      ((x_min,x_max),(y_min,y_max),(z_min,z_max),(None,None)) shape from
      per-dim bounds, and the use_amplitude->max_sigma22 dependency. Supply the
      region bounds (project the region's lon/lat extent into km for x/y; depth
      range for z), the method, and use_amplitude. `dbscan_eps` is not computed
      by the script — estimate it with `estimate_eps(stations, config["vel"]["p"])`
      or set a manual value (10-15 s is common); see references/estimate-eps-api.md.
      Pass any other documented key (eikonal, covariance_prior, ncpu,
      min_p/s_picks_per_eq, min_stations, dbscan_min_cluster_size,
      dbscan_max_time_space_ratio) through `extra`. Prefer importing
      `build_gamma_config` so bfgs_bounds keeps Python tuples and the unbounded
      time slot stays (None, None). Full key reference in
      references/association-api.md.
    script: scripts/build_gamma_config.py
    depends_on: [prepare-stations]
    inputs:
      - name: bounds
        type: object
        description: 'Per-dim (min, max) km extents, e.g. {"x(km)": (xmin,xmax), "y(km)": (ymin,ymax), "z(km)": (0,30)}.'
      - name: method
        type: string
        description: '"BGMM" (Bayesian, default) or "GMM" (standard).'
      - name: use_amplitude
        type: boolean
      - name: dbscan_eps
        type: float
        description: DBSCAN eps in seconds, from estimate_eps(stations, vp) or a manual 10-15 s value.
    outputs:
      - name: config
        type: object
        description: Validated GaMMA config dict ready to pass to association().

  - name: run-association
    description: >
      Call `events, assignments = association(picks, stations, config, event_idx0, method)`
      with `event_idx0=0` and `method=config["method"]`. Returns a tuple:
      `events` (list[dict], one per associated earthquake) and `assignments`
      (list of (pick_index, event_index, gamma_score) tuples). If `events` is
      empty, no events were associated — revisit eps, min_picks_per_eq, the
      bounds, or the pick quality. Return-value schema in
      references/association-api.md.
    depends_on: [prepare-picks, build-config]
    inputs:
      - name: picks
        type: object
      - name: stations
        type: object
      - name: config
        type: object
    outputs:
      - name: events
        type: list[object]
        description: One dict per event with time, magnitude, x/y/z(km) hypocenter, gamma_score, pick counts, event_index.
      - name: assignments
        type: list[object]
        description: (pick_index, event_index, gamma_score) tuples mapping picks to events.

  - name: build-catalog
    description: >
      Turn `events` into the catalog the task needs. Each event dict carries
      `time` (ISO 8601 origin time with milliseconds), `x(km)`/`y(km)`/`z(km)`
      hypocenter, `magnitude` (999 when use_amplitude=False), and `gamma_score`.
      Convert to a DataFrame; project `x(km)`/`y(km)` back to longitude/latitude
      with the inverse pyproj transform if geographic coordinates are needed;
      depth is `z(km)`. A required `time` column should be ISO format without
      timezone. Optionally join `assignments` back to the picks (on pick_index)
      to label which picks formed each event.
    depends_on: [run-association]
    inputs:
      - name: events
        type: list[object]
      - name: assignments
        type: list[object]
        nullable: true
    outputs:
      - name: catalog
        type: object
        description: Event catalog (e.g. DataFrame / CSV) with at least an ISO time column per event.

search_shortcuts:
  - category: References and scripts
    body: >
      references/association-api.md — full `association` reference: input
      parameters, the picks and stations DataFrame column schemas, every config
      dict key (required, velocity, DBSCAN, filtering, other) with types and
      defaults, and the (events, assignments) return-value schema. Load when
      preparing DataFrames, populating config, or parsing output.
      references/estimate-eps-api.md — `estimate_eps` reference: signature,
      required station columns, the seconds-valued return, usage patterns, and
      practical notes (typical 10-20 s; often hardcoded to 10-15 s). Load when
      choosing dbscan_eps. scripts/build_gamma_config.py — assembles and
      validates the config dict (oversample rule, defaults, bfgs_bounds shape);
      import build_gamma_config or run it on a JSON params file.

scenarios:
  - need: Associate PhaseNet/SeisBench picks over a small network into an event catalog with timestamps.
    context: >
      Picks exist as (trace_id, peak_time, peak_value, phase). Stations are a
      CSV of network/station/channel/lon/lat/elevation_m. Amplitudes are not
      available.
    action: >
      Build picks (id=trace_id, timestamp=peak_time UTC, type=phase.lower(),
      prob=peak_value). Build stations (id=`network.station.`, project lon/lat
      to x/y km via pyproj aeqd centered on the region, z=-elevation_m/1000,
      collapse by id). Build config with use_amplitude=False, method="BGMM",
      dbscan_eps=estimate_eps(stations, 6.0), and region-derived x/y/z bounds.
      Run association; sort events by time and write the `time` column in ISO
      format without timezone.
    outcome: A unique list of earthquake events with origin times (and locations) suitable for catalog evaluation.
  - need: association returns an empty events list.
    action: >
      First verify the `id`s match between picks and stations (a format
      mismatch silently drops every pick), that pick `type` is lowercase, and
      that timestamps are UTC. Then re-check dbscan_eps (too small over-splits
      clusters; 10-15 s is a common manual value), lower or confirm
      min_picks_per_eq, and widen the bfgs_bounds / region extent so true
      hypocenters are inside. On a small or sparse network also lower
      min_stations (default 5) and dbscan_min_cluster_size (default 500) via
      `extra` — either can suppress otherwise-valid events.
    outcome: Clusters large enough to meet the thresholds form and events are produced.
  - need: Amplitudes are available and you want magnitude estimates.
    action: >
      Add an `amp` column (m/s) to picks, set use_amplitude=True so the
      config-builder includes max_sigma22, and drop picks with amp==0/-1
      (GaMMA also filters these). Read magnitude and sigma_amp from each event.
    outcome: Events carry real magnitude estimates instead of the 999 placeholder.

anti_patterns:
  - Passing uppercase phase types — `type` must be lowercase "p"/"s" (GaMMA lowercases internally, but build them lowercase to avoid mismatches).
  - Mismatched `id` values between picks and stations — association silently drops picks whose station id has no match. The usual cause is a granularity mismatch (picker emits `network.station.location.channel` while stations are `network.station.`); normalize both to one convention.
  - Leaving timestamps in local time — pick `timestamp` must be UTC.
  - Using BGMM with oversample_factor=1.0 (or GMM with 5.0) — the factor follows the method; let build_gamma_config set it.
  - Forgetting the (None, None) time slot in bfgs_bounds, or shaping it as (min,max) — time is unbounded.
  - Setting use_amplitude=True without an `amp` column (or without max_sigma22), or expecting a real magnitude when use_amplitude=False (it returns 999).
  - Treating the estimate_eps output as a hard requirement — practitioners often override it with a manual 10-15 s value per network.
  - Skipping the per-id station collapse — duplicate channel rows leave multiple rows per station and distort clustering.
```
