---
name: gamma-phase-associator
description: An overview of the python package for running the GaMMA earthquake phase association algorithm. The algorithm expects phase picks data and station data as input and produces (through unsupervised clustering) earthquake events with source information like earthquake location, origin time and magnitude. The skill explains commonly used functions and the expected input/output format.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Reference for using the GaMMA Python library (https://github.com/AI4EPS/GaMMA) to
  associate seismic P/S phase picks with earthquake events. GaMMA treats association
  as unsupervised clustering: a Bayesian (or standard) Gaussian Mixture Model fit via
  Expectation-Maximization assigns picks to events and estimates each event's
  hypocenter (x, y, z), origin time, and magnitude. This skill documents the core
  API (`association`, `estimate_eps`), the expected DataFrame schemas for picks and
  stations, the configuration dictionary, and the returned event/assignment
  structures. It assumes P/S picks have already been produced upstream.
  Citation - Zhu, W., McBrearty, I. W., Mousavi, S. M., Ellsworth, W. L., & Beroza,
  G. C. (2022). Earthquake phase association using a Bayesian Gaussian mixture
  model. Journal of Geophysical Research - Solid Earth, 127(5).

trigger_when:
  - User needs to associate already-extracted P/S phase picks into discrete earthquake events.
  - User mentions GaMMA, phase association, pick-to-event clustering, or unsupervised earthquake catalog building.
  - User wants to estimate hypocenter location, origin time, or magnitude from a stream of phase picks plus station metadata.
  - User asks about the input DataFrame schema, configuration dictionary, or return structure for the `gamma` / `gamma.utils` library.
  - User needs an appropriate DBSCAN `eps` value for pre-clustering picks by time (use `estimate_eps`).

do_not_use_when:
  - Raw waveform data has not yet been processed into P/S picks - run a phase picker first (e.g., PhaseNet, EQTransformer).
  - The task is single-event location refinement from already-associated picks (use a dedicated locator like HypoInverse, NonLinLoc).
  - The task is moment tensor inversion, focal mechanism estimation, or waveform-based magnitude refinement.

scope_and_approval: >
  Read-only reference for an agent that will write Python that imports
  `gamma.utils.association` and `gamma.utils.estimate_eps`. The skill prescribes
  input shapes, config keys, and output handling; it does not itself execute
  association runs. Installing the GaMMA package via pip (a network + environment
  mutation) should be confirmed with the user before running.

steps:
  - name: install-gamma
    description: |
      Install the GaMMA package from its upstream Git repository:

      ```
      pip install git+https://github.com/wayneweiqiang/GaMMA.git
      ```

      GaMMA is not on PyPI; the git URL is the canonical install path. Confirm
      with the user before adding it to a managed environment.

  - name: prepare-picks-dataframe
    description: |
      Build the `picks` DataFrame. Each row is one phase pick.

      Required columns:

      | Column      | Type          | Description                                                  | Example                                                       |
      |-------------|---------------|--------------------------------------------------------------|---------------------------------------------------------------|
      | `id`        | str           | Station identifier (must match the `stations` DataFrame)     | `network.station.` or `network.station.location.channel`      |
      | `timestamp` | datetime/str  | Pick arrival time (ISO format or datetime)                   | `"2019-07-04T22:00:06.084"`                                   |
      | `type`      | str           | Phase type: `"p"` or `"s"` (lowercase)                       | `"p"`                                                         |
      | `prob`      | float         | Pick probability / weight in [0, 1]                          | `0.94`                                                        |
      | `amp`       | float         | Amplitude in m/s (required if `use_amplitude=True`)          | `0.000017`                                                    |

      Notes:
      - Timestamps must be in UTC or converted to UTC.
      - Phase types are forced to lowercase internally.
      - Picks with `amp == 0` or `amp == -1` are filtered when `use_amplitude=True`.
      - The DataFrame index is used to track pick identities in the output `assignments`.

  - name: prepare-stations-dataframe
    description: |
      Build the `stations` DataFrame. Each row is one station with a projected
      local coordinate.

      Required columns:

      | Column   | Type  | Description                                       | Example       |
      |----------|-------|---------------------------------------------------|---------------|
      | `id`     | str   | Station identifier                                | `"CI.CCC..BH"`|
      | `x(km)`  | float | X coordinate in km (projected)                    | `-35.6`       |
      | `y(km)`  | float | Y coordinate in km (projected)                    | `45.2`        |
      | `z(km)`  | float | Z coordinate (elevation, typically negative)      | `-0.67`       |

      Notes:
      - Coordinates should be in a projected local coordinate system. The
        `pyproj` package is a typical choice for projecting lat/lon to km.
      - The `id` column must match the `id` values in the `picks` DataFrame
        (e.g., `network.station.` or `network.station.location.channel`).
      - Group stations by unique `id`: identical attributes collapse to a single
        value; conflicting metadata is preserved as a sorted list.

  - name: configure-association
    description: |
      Build the `config` dictionary that controls association behavior.

      Required keys:

      | Key                 | Type        | Description                                          | Example                                            |
      |---------------------|-------------|------------------------------------------------------|----------------------------------------------------|
      | `dims`              | list[str]   | Location dimensions to solve for                     | `["x(km)", "y(km)", "z(km)"]`                      |
      | `min_picks_per_eq`  | int         | Minimum picks required per earthquake                | `5`                                                |
      | `max_sigma11`       | float       | Maximum allowed time residual in seconds             | `2.0`                                              |
      | `use_amplitude`     | bool        | Whether to use amplitude in clustering               | `True`                                             |
      | `bfgs_bounds`       | tuple       | Bounds for BFGS optimization                         | `((-35, 92), (-128, 78), (0, 21), (None, None))`   |
      | `oversample_factor` | float       | Factor for oversampling initial GMM components       | `5.0` for `BGMM`, `1.0` for `GMM`                  |

      Notes on `dims`:
      - Valid options: `["x(km)", "y(km)", "z(km)"]`, `["x(km)", "y(km)"]`, or `["x(km)"]`.

      Notes on `bfgs_bounds`:
      - Format: `((x_min, x_max), (y_min, y_max), (z_min, z_max), (None, None))`.
      - The last tuple is for time and is unbounded.

      Velocity model keys:

      | Key       | Type      | Default                       | Description                            |
      |-----------|-----------|-------------------------------|----------------------------------------|
      | `vel`     | dict      | `{"p": 6.0, "s": 3.47}`       | Uniform velocity model (km/s)          |
      | `eikonal` | dict/None | `None`                        | 1D velocity model for travel times     |

      DBSCAN pre-clustering keys (optional):

      | Key                             | Type  | Default | Description                                         |
      |---------------------------------|-------|---------|-----------------------------------------------------|
      | `use_dbscan`                    | bool  | `True`  | Enable DBSCAN pre-clustering                        |
      | `dbscan_eps`                    | float | `25`    | Max time between picks (seconds)                    |
      | `dbscan_min_samples`            | int   | `3`     | Min samples in DBSCAN neighborhood                  |
      | `dbscan_min_cluster_size`       | int   | `500`   | Min cluster size for hierarchical splitting         |
      | `dbscan_max_time_space_ratio`   | float | `10`    | Max time/space ratio for splitting                  |

      Set `dbscan_eps` from the `estimate-dbscan-eps` step.

      Filtering keys (optional):

      | Key                   | Type  | Default | Description                                                            |
      |-----------------------|-------|---------|------------------------------------------------------------------------|
      | `max_sigma22`         | float | `1.0`   | Max phase amplitude residual in log scale (required if `use_amplitude=True`) |
      | `max_sigma12`         | float | `1.0`   | Max covariance                                                         |
      | `max_sigma11`         | float | `2.0`   | Max phase time residual (s)                                            |
      | `min_p_picks_per_eq`  | int   | `0`     | Min P-phase picks per event                                            |
      | `min_s_picks_per_eq`  | int   | `0`     | Min S-phase picks per event                                            |
      | `min_stations`        | int   | `5`     | Min unique stations per event                                          |

      Other optional keys:

      | Key                | Type        | Default | Description                                       |
      |--------------------|-------------|---------|---------------------------------------------------|
      | `covariance_prior` | list[float] | auto    | Prior for covariance `[time, amp]`                |
      | `ncpu`             | int         | auto    | Number of CPUs for parallel processing            |

  - name: estimate-dbscan-eps
    description: |
      Use `gamma.utils.estimate_eps` to derive a DBSCAN `eps` (time-distance
      threshold in seconds) from station geometry and P-wave velocity.

      Signature:

      ```python
      def estimate_eps(stations, vp, sigma=2.0)
      ```

      Input parameters:

      | Parameter  | Type      | Default  | Description                                       |
      |------------|-----------|----------|---------------------------------------------------|
      | `stations` | DataFrame | required | Station metadata with 3D coordinates              |
      | `vp`       | float     | required | P-wave velocity in km/s                           |
      | `sigma`    | float     | `2.0`    | Number of standard deviations above the mean      |

      Required `stations` columns: `x(km)`, `y(km)`, `z(km)` (floats, km).

      Returns: float, an epsilon value in **seconds** for use with DBSCAN clustering.

      Example:

      ```python
      from gamma.utils import estimate_eps

      vp = 6.0  # P-wave velocity in km/s
      eps = estimate_eps(stations, vp, sigma=2.0)

      config = {
          "use_dbscan": True,
          "dbscan_eps": eps,
          "dbscan_min_samples": 3,
          # ... other config options
      }
      ```

      Practical notes:
      - In example notebooks, this function is often commented out in favor of
        hardcoded values (10-15 seconds).
      - Practitioners may prefer manual tuning for specific networks/regions.
      - Typical output values range from 10-20 seconds depending on station density.
      - Most useful when optimal `eps` is unknown or when working with a new network.

  - name: run-association
    description: |
      Call `gamma.utils.association` to cluster picks into events.

      Signature:

      ```python
      def association(picks, stations, config, event_idx0=0, method="BGMM", **kwargs)
      ```

      Input parameters:

      | Parameter    | Type      | Default   | Description                                       |
      |--------------|-----------|-----------|---------------------------------------------------|
      | `picks`      | DataFrame | required  | Seismic phase pick data                           |
      | `stations`   | DataFrame | required  | Station metadata with locations                   |
      | `config`     | dict      | required  | Configuration parameters                          |
      | `event_idx0` | int       | `0`       | Starting event index for numbering                |
      | `method`     | str       | `"BGMM"`  | `"BGMM"` (Bayesian) or `"GMM"` (standard)         |

      The function clusters picks on arrival time and amplitude, then fits GMMs
      to estimate hypocenters, origin times, and magnitudes.

  - name: interpret-results
    description: |
      `association` returns a tuple `(events, assignments)`.

      `events` is a `list[dict]`. Each dict represents one associated earthquake:

      | Key            | Type  | Description                                          |
      |----------------|-------|------------------------------------------------------|
      | `time`         | str   | Origin time (ISO 8601 with milliseconds)             |
      | `magnitude`    | float | Estimated magnitude (`999` if `use_amplitude=False`) |
      | `sigma_time`   | float | Time uncertainty (seconds)                           |
      | `sigma_amp`    | float | Amplitude uncertainty (log10 scale)                  |
      | `cov_time_amp` | float | Time-amplitude covariance                            |
      | `gamma_score`  | float | Association quality score                            |
      | `num_picks`    | int   | Total picks assigned                                 |
      | `num_p_picks`  | int   | P-phase picks assigned                               |
      | `num_s_picks`  | int   | S-phase picks assigned                               |
      | `event_index`  | int   | Unique event index                                   |
      | `x(km)`        | float | X coordinate of hypocenter                           |
      | `y(km)`        | float | Y coordinate of hypocenter                           |
      | `z(km)`        | float | Z coordinate (depth)                                 |

      `assignments` is a `list[tuple]`. Each tuple is
      `(pick_index, event_index, gamma_score)`:
      - `pick_index`: index in the original `picks` DataFrame.
      - `event_index`: associated event index (matches `events[i]["event_index"]`).
      - `gamma_score`: probability/confidence of the assignment.

decisions:
  - signal: User has not specified a clustering method.
    action: Default to `method="BGMM"` (Bayesian GMM) with `oversample_factor=5.0`; switch to `"GMM"` (with `oversample_factor=1.0`) only if the user requests standard GMM or BGMM is too slow.
  - signal: Amplitude data (`amp` column) is unavailable or unreliable.
    action: Set `use_amplitude=False`. Magnitudes in returned events will be `999` (sentinel); do not surface them as real magnitudes.
  - signal: Optimal DBSCAN `eps` for the network is unknown.
    action: Call `estimate_eps(stations, config["vel"]["p"])` and assign to `config["dbscan_eps"]`. For a familiar network, hardcoded 10-15 s is a common practitioner default.
  - signal: Picks DataFrame contains rows with `amp == 0` or `amp == -1`.
    action: Leave them in place when `use_amplitude=True` - GaMMA filters them internally. If `use_amplitude=False`, they are ignored.
  - signal: User wants to solve for hypocenter in 2D only (e.g., shallow regional study).
    action: Set `dims=["x(km)", "y(km)"]` and adjust `bfgs_bounds` to match the reduced dimensionality.

scenarios:
  - need: Run GaMMA on a freshly picked dataset with automatic DBSCAN eps.
    context: Picks and stations DataFrames are already projected to km and indexed by station `id`.
    action: |
      ```python
      from gamma.utils import association, estimate_eps

      config["dbscan_eps"] = estimate_eps(stations, config["vel"]["p"])
      events, assignments = association(picks, stations, config, method="BGMM")
      ```
    outcome: "`events` holds associated earthquake hypocenters/origins; `assignments` maps each pick row to one of those events with a confidence score."
  - need: Reuse a hand-tuned DBSCAN eps for a familiar network instead of estimating it.
    context: Operator has a long-running deployment and knows 15 s works well.
    action: |
      ```python
      config["dbscan_eps"] = 15  # seconds, manual override
      events, assignments = association(picks, stations, config)
      ```
    outcome: "Skips the `estimate_eps` call; behavior identical otherwise."

anti_patterns:
  - Passing pick timestamps in local time. GaMMA assumes UTC; mixed time zones silently corrupt clustering.
  - Using lat/lon (degrees) in the `x(km)` / `y(km)` columns. Coordinates must be projected to a local km-based system (e.g., via `pyproj`) before passing to `association`.
  - Mismatched `id` values between `picks` and `stations`. Picks whose station `id` is absent from `stations` cannot be associated.
  - Forgetting to set `oversample_factor` per method (`5.0` for BGMM, `1.0` for GMM). Wrong values degrade convergence.
  - Setting `use_amplitude=True` without populating `amp` (m/s) in `picks` or without setting `max_sigma22`.
  - Treating the `magnitude=999` sentinel as a real magnitude. It only appears when `use_amplitude=False`.
  - Using uppercase phase labels in `type` (e.g., `"P"`, `"S"`). They are forced lowercase internally; relying on the original case downstream will break joins.
  - Confusing the index meanings in `assignments`. The first element is the pick DataFrame index, not a sequential pick counter - preserve the original `picks` index.
```
