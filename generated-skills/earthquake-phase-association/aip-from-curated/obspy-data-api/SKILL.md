---
name: obspy-data-api
description: An overview of the core data API of ObsPy, a Python framework for processing seismological data. It is useful for parsing common seismological file formats, or manipulating custom data into standard objects for downstream use cases such as ObsPy's signal processing routines or SeisBench's modeling API.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Overview of the core data API of ObsPy, a Python framework for processing
  seismological data. Covers parsing common seismological file formats
  (SAC, MiniSEED, GSE2, SEISAN, Q, QuakeML, FDSN StationXML) and
  manipulating custom data into ObsPy's standard `Stream`/`Trace`,
  `Catalog`/`Event`, and `Inventory` objects — the inputs expected by
  ObsPy's signal-processing routines and SeisBench's modeling API.

trigger_when:
  - Reading or writing seismic waveform files (SAC, MiniSEED, GSE2, SEISAN, Q, etc.) with ObsPy.
  - Loading or inspecting earthquake event metadata (origins, magnitudes, picks, focal mechanisms) from QuakeML or similar formats.
  - Loading station metadata from FDSN StationXML or Dataless SEED.
  - Manipulating waveform time series — filtering, tapering, resampling, integrating, deconvolving the instrument response.
  - Preparing input data for SeisBench models or other downstream ObsPy signal-processing routines.

steps:
  - name: parse-waveforms
    description: >
      Call `obspy.read()` to load a seismogram into a `Stream`. With no
      arguments it returns a built-in example stream; pass a filename for
      local files or an HTTP URL (e.g., https://examples.obspy.org/...) for
      remote files. The result is a list-like `Stream` of one or more
      `Trace` objects — gap-less continuous time series with their
      header/meta information.
  - name: inspect-trace
    description: >
      Index into the stream (`st[0]`) to get a `Trace`. Read `trace.data`
      for the time-series NumPy `ndarray`, and `trace.stats` (a dict-like
      `Stats` object) for header metadata. Identifying fields:
      `network`, `station`, `location`, `channel` (physical location and
      instrument). Sampling fields, all interrelated: `starttime`,
      `sampling_rate`, `delta`, `endtime`, `npts`. `starttime` and
      `endtime` are `UTCDateTime` objects.
  - name: manipulate-trace
    description: >
      Apply `Trace` (and `Stream`) helper methods to process the waveform:
      `taper()` tapers the data, `filter()` applies a digital filter,
      `resample()` resamples in the frequency domain, `integrate()`
      integrates with respect to time, `remove_response()` deconvolves the
      instrument response. A multitude of similar helper methods are
      attached to both `Stream` and `Trace`.
  - name: parse-events
    description: >
      Call `obspy.read_events()` to load event metadata into a `Catalog`
      (`Catalog.events` → list of `Event`). The class hierarchy is
      closely modelled after QuakeML (https://quake.ethz.ch/quakeml/).
      Each `Event` exposes `origins` (list of `Origin` with `latitude`,
      `longitude`, `depth`, `time`, ...), `magnitudes` (list of
      `Magnitude` with `mag`, `magnitude_type`, ...), `picks`, and
      `focal_mechanisms`. Use `Catalog.write()` for supported output
      formats.
  - name: parse-stations
    description: >
      Call `obspy.read_inventory()` to load station metadata into an
      `Inventory`. The hierarchy is `Inventory.networks` →
      `Network.stations` → `Station.channels` → `Channel`, closely
      modelled after FDSN StationXML (https://www.fdsn.org/xml/station/),
      developed as a human-readable XML replacement for Dataless SEED.
      `Network` carries `code`, `description`, ...; `Station` carries
      `code`, `latitude`, `longitude`, `elevation`, `start_date`,
      `end_date`, ...; `Channel` carries `code`, `location_code`,
      `latitude`, `longitude`, `elevation`, `depth`, `dip`, `azimuth`,
      `sample_rate`, `start_date`, `end_date`, `response`, .... Use
      `Inventory.write()` for supported output formats.

scenarios:
  - need: Load and inspect the built-in example seismogram.
    context: >
      A `Stream` with an example seismogram can be created by calling
      `read()` with no arguments. Local files load by filename; remote
      files load via URL (e.g., https://examples.obspy.org).
    action: |
      >>> from obspy import read
      >>> st = read()
      >>> print(st)
      3 Trace(s) in Stream:
      BW.RJOB..EHZ | 2009-08-24T00:20:03.000000Z - ... | 100.0 Hz, 3000 samples
      BW.RJOB..EHN | 2009-08-24T00:20:03.000000Z - ... | 100.0 Hz, 3000 samples
      BW.RJOB..EHE | 2009-08-24T00:20:03.000000Z - ... | 100.0 Hz, 3000 samples
      >>> tr = st[0]
      >>> print(tr)
      BW.RJOB..EHZ | 2009-08-24T00:20:03.000000Z - ... | 100.0 Hz, 3000 samples
      >>> tr.data
      array([ 0.        ,  0.00694644,  0.07597424, ...,  1.93449584,
              0.98196204,  0.44196924])
      >>> print(tr.stats)
               network: BW
               station: RJOB
              location:
               channel: EHZ
             starttime: 2009-08-24T00:20:03.000000Z
               endtime: 2009-08-24T00:20:32.990000Z
         sampling_rate: 100.0
                 delta: 0.01
                  npts: 3000
                 calib: 1.0
                 ...
      >>> tr.stats.starttime
      UTCDateTime(2009, 8, 24, 0, 20, 3)
    outcome: >
      A `Stream` of three `Trace` objects. Each `Trace` exposes a NumPy
      `data` array and a `stats` block containing identifying fields
      (network/station/location/channel) and sampling fields
      (starttime/endtime/sampling_rate/delta/npts) as a `UTCDateTime`
      where applicable.

search_shortcuts:
  - category: Classes & Functions
    body: |
      - `read` — Read waveform files into an ObsPy `Stream` object.
      - `Stream` — List-like object of multiple ObsPy `Trace` objects.
      - `Trace` — An object containing data of a continuous series, such as a seismic trace.
      - `Stats` — A container for additional header information of an ObsPy `Trace` object.
      - `UTCDateTime` — A UTC-based datetime object.
      - `read_events` — Read event files into an ObsPy `Catalog` object.
      - `Catalog` — Container for `Event` objects.
      - `Event` — Describes a seismic event which does not necessarily need to be a tectonic earthquake.
      - `read_inventory` — Function to read inventory files.
      - `Inventory` — The root object of the `Network` → `Station` → `Channel` hierarchy.
  - category: Modules
    body: |
      - `obspy.core.trace` — Module for handling ObsPy `Trace` and `Stats` objects.
      - `obspy.core.stream` — Module for handling ObsPy `Stream` objects.
      - `obspy.core.utcdatetime` — Module containing a UTC-based datetime class.
      - `obspy.core.event` — Module handling event metadata.
      - `obspy.core.inventory` — Module for handling station metadata.
      - `obspy.core.util` — Various utilities for ObsPy.
      - `obspy.core.preview` — Tools for creating and merging previews.
```
