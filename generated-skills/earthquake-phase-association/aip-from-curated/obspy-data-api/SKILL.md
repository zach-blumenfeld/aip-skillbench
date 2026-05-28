---
name: obspy-data-api
description: An overview of the core data API of ObsPy, a Python framework for processing seismological data. It is useful for parsing common seismological file formats, or manipulating custom data into standard objects for downstream use cases such as ObsPy's signal processing routines or SeisBench's modeling API.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 and the obspy package (`pip install obspy`). Reading from a URL needs network access. SeisBench is only needed for the optional downstream handoff, not for the ObsPy data API itself.
---

```yaml
purpose: >
  Use ObsPy's core data API to parse common seismological file formats and
  manipulate seismic data into ObsPy's standard objects for downstream use.
  `read()` parses waveforms (MiniSEED, SAC, GSE2, SEISAN, Q, …) into a `Stream`
  of `Trace` objects; each `Trace` carries its samples in `.data` (a NumPy
  array) and its metadata in `.stats`. `read_events()` parses event metadata
  into a `Catalog` (modelled on QuakeML); `read_inventory()` parses station
  metadata into an `Inventory` (modelled on FDSN StationXML). Once data is in
  these objects it is ready for ObsPy's signal-processing helpers or for handoff
  to a modeling API such as SeisBench. Scope is the data API itself — not
  signal-processing algorithms, picking models, or association logic.

trigger_when:
  - Parsing seismological waveform files (MiniSEED/.mseed, SAC, GSE2, SEISAN, Q, …) into usable objects.
  - Building or inspecting `Stream`/`Trace` objects, or reading their `.data`/`.stats`.
  - Reading earthquake/event metadata (QuakeML) into a `Catalog`.
  - Reading station/channel metadata (FDSN StationXML) into an `Inventory`.
  - Preparing waveform data to feed ObsPy signal-processing routines or SeisBench's modeling/picking API.
  - User mentions ObsPy, MiniSEED/SAC seismograms, traces, or seismic station inventories.

do_not_use_when:
  - Implementing the picking model or the phase-association algorithm itself — those belong to SeisBench/GaMMA, not the ObsPy data API.
  - Working with non-seismological time series that have no ObsPy reader.
  - Station/event data already supplied as a CSV or JSON table that pandas reads directly (no StationXML/QuakeML involved).

steps:
  - name: read-waveforms
    description: >
      Load seismograms with `from obspy import read; st = read("path/or/URL")`.
      The format (MiniSEED, SAC, GSE2, SEISAN, Q, …) is auto-detected. A local
      filename reads a local file; an http(s) URL (e.g.
      https://examples.obspy.org/…) reads a remote file; calling `read()` with
      no argument returns a built-in 3-trace example `Stream` (handy for smoke
      tests). The result is a list-like `Stream` of gap-less `Trace` objects.
    inputs:
      - name: source
        type: string
        nullable: true
        description: File path or http(s) URL to the waveform file; omit for the built-in example stream.
    outputs:
      - name: stream
        type: object
        description: A Stream — a list-like container of Trace objects.
  - name: inspect-trace
    description: >
      A `Stream` indexes like a list (`tr = st[0]`, or `for tr in st`). Each
      `Trace` exposes `.data` (a NumPy `ndarray` of the samples) and `.stats`
      (a dict-like `Stats`). Key `stats` fields: `network`, `station`,
      `location`, `channel` (identify location and instrument) plus the
      interrelated timing fields `starttime`, `sampling_rate`, `delta`,
      `endtime`, `npts`. `starttime` and `endtime` are `UTCDateTime` objects.
      See `references/obspy-api-reference.md` for the full attribute list and a
      worked REPL example.
    depends_on: [read-waveforms]
    inputs:
      - name: stream
        type: object
    outputs:
      - name: traces
        type: list[object]
        description: Per-trace sample array (`.data`) plus `.stats` metadata.
  - name: process-traces
    description: >
      Only when preprocessing is needed. `Stream` and `Trace` share in-place
      helper methods: `taper()`, `filter()`, `resample()` (frequency-domain
      resampling), `integrate()` (integrate with respect to time), and
      `remove_response()` (deconvolve the instrument response). Apply to the
      whole Stream or a single Trace. Many pickers expect raw or only lightly
      processed traces, so do not filter/resample unless the downstream step
      requires it.
    depends_on: [read-waveforms]
    inputs:
      - name: stream
        type: object
    outputs:
      - name: processed_stream
        type: object
        nullable: true
        description: The same Stream after in-place processing; null when no preprocessing is applied.
  - name: read-event-metadata
    description: >
      Read event/earthquake metadata with `from obspy import read_events; cat =
      read_events("events.xml")` → a `Catalog` of `Event` objects (modelled on
      QuakeML). Each `Event` holds `origins` (each `Origin`: `latitude`,
      `longitude`, `depth`, `time`), `magnitudes` (each `Magnitude`: `mag`,
      `magnitude_type`), `picks`, and `focal_mechanisms`. Write with
      `Catalog.write()`. See `references/obspy-api-reference.md`.
    inputs:
      - name: event_file
        type: string
    outputs:
      - name: catalog
        type: object
  - name: read-station-metadata
    description: >
      Read station/channel metadata with `from obspy import read_inventory; inv
      = read_inventory("stations.xml")` → an `Inventory` (modelled on FDSN
      StationXML). Hierarchy: `Inventory` → `networks` → `Network` → `stations`
      → `Station` → `channels` → `Channel`. `Station` carries `code`,
      `latitude`, `longitude`, `elevation`, `start_date`/`end_date`; `Channel`
      adds `location_code`, `depth`, `dip`, `azimuth`, `sample_rate`, and
      `response`. Write with `Inventory.write()`. Station metadata supplied as
      CSV/JSON is read with pandas, not `read_inventory` — this step is for
      StationXML. See `references/obspy-api-reference.md`.
    inputs:
      - name: inventory_file
        type: string
    outputs:
      - name: inventory
        type: object
  - name: prepare-for-downstream
    description: >
      Hand the `Stream` to the downstream consumer. ObsPy signal-processing
      routines operate on the Stream/Trace directly. A modeling API such as
      SeisBench accepts an ObsPy `Stream` (its pretrained models expose methods
      like `.classify(stream)` / `.annotate(stream)`), reading samples from
      `Trace.data` and timing from `Trace.stats`. Keep each trace's
      `network.station.location.channel` id and its `starttime`/`sampling_rate`
      intact, since downstream picks/annotations are keyed back to trace id and
      absolute time.
    depends_on: [read-waveforms]
    inputs:
      - name: stream
        type: object
        description: The Stream from read-waveforms (or processed_stream from process-traces).
    outputs:
      - name: downstream_input
        type: object
        description: The Stream as accepted by the downstream signal-processing routine or model.

scenarios:
  - need: Load MiniSEED waveforms and pass them to a SeisBench picker.
    action: >
      `st = read("/path/wave.mseed")`, then call the SeisBench model on `st`
      (it reads `Trace.data`/`Trace.stats` internally). No manual array
      extraction is needed.
    outcome: A Stream the picker consumes directly; picks return keyed by trace id and absolute time.
  - need: Experiment with the API without a data file.
    action: Call `read()` with no arguments to get the built-in 3-trace example Stream.
    outcome: A populated Stream (BW.RJOB EHZ/EHN/EHE @ 100 Hz) for smoke-testing code paths.
  - need: Get a trace's sample array and absolute timing.
    action: '`tr = st[0]; samples = tr.data; t0 = tr.stats.starttime; fs = tr.stats.sampling_rate`.'
    outcome: NumPy samples plus a UTCDateTime start and sampling rate, enough to reconstruct per-sample timestamps.
  - need: Read an earthquake catalog and pull origin times and locations.
    action: '`cat = read_events("events.xml"); ev = cat[0]; o = ev.origins[0]` → `o.time`, `o.latitude`, `o.longitude`, `o.depth`; magnitude via `ev.magnitudes[0].mag`.'
    outcome: Origin time and hypocenter (and magnitude) for each event in the catalog.

anti_patterns:
  - Hand-parsing MiniSEED/SAC bytes instead of calling `read()` — ObsPy auto-detects the format and returns standard objects.
  - Reaching for `read_inventory` on station data that is actually a CSV/JSON table — use pandas for that; `read_inventory` is for FDSN StationXML.
  - Treating `Trace.stats.starttime`/`endtime` as plain strings or floats — they are `UTCDateTime` objects; do datetime arithmetic with them or convert explicitly.
  - Assuming a `Stream` is a single time series — it is a list of `Trace` objects; index or iterate to reach the data.
  - Filtering or resampling traces before a picker that expects raw waveforms — apply `filter()`/`resample()` only when the downstream step requires it.
  - Dropping or rewriting trace ids (`network.station.location.channel`) before handoff — downstream picks/annotations are keyed to them.
```
