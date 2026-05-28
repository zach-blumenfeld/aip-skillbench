---
name: seisbench-model-api
description: An overview of the core model API of SeisBench, a Python framework for training and applying machine learning algorithms to seismic data. It is useful for annotating waveforms using pretrained SOTA ML models, for tasks like phase picking, earthquake detection, waveform denoising and depth estimation. For any waveform, you can manipulate it into an obspy stream object and it will work seamlessly with seisbench models.
compatibility: Requires Python and SeisBench (`pip install seisbench`), plus ObsPy and PyTorch. GPU optional. Internet access needed on first use of each pretrained weight (downloaded then cached locally).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Apply pretrained SeisBench deep-learning models to ObsPy waveform streams to
  produce seismic annotations or discrete results — phase picks (P/S),
  earthquake detections, denoised waveforms, or depth estimates. SeisBench's
  `WaveformModel` bridges the PyTorch model interface and the ObsPy stream
  interface: it assembles streams into tensors, runs the model (with batching,
  optional GPU), and reassembles results. Two core calls cover everything:
  `annotate` (continuous output — e.g. pick-probability characteristic
  functions, returned as a Stream) and `classify` (discrete output — e.g. a list
  of picks and/or detections). Beyond general agent knowledge this skill adds the
  SeisBench-specific API (loading pretrained weights, the integrated model
  catalog, the speed knobs), the numerical-stability rule that protects
  tiny-amplitude waveforms from being flattened by internal normalization, and a
  runnable picker that emits a standard, association-ready pick table.

trigger_when:
  - You need to pick phases (P/S), detect earthquakes, denoise waveforms, or estimate depth from seismic data using a pretrained ML model.
  - You have one or more ObsPy `Stream`s and need either continuous annotations or discrete picks/detections.
  - About to apply a SeisBench model and want the right call (`annotate` vs `classify`), the right preprocessing, and the right pretrained weights.
  - Choosing among the models integrated into SeisBench for a seismic task.
  - Speeding up model application over a large waveform dataset.

do_not_use_when:
  - You need to read, parse, or manipulate the raw waveform/station files themselves (MSEED/SAC I/O, Trace/Stats handling, resampling, response removal) — that is the ObsPy data API; use the `obspy-data-api` skill.
  - You are choosing a detection *paradigm* at a strategic level (deep learning vs STA/LTA vs template matching vs manual review) — use the `seismic-picker-selection` skill, then come here to apply the chosen deep-learning model.
  - You already have phase picks and need to associate them into earthquake events — use the `gamma-phase-associator` skill.
  - The model is not a SeisBench `WaveformModel` (a different framework's file layout and contracts do not apply here).

scope_and_approval: >
  Reading this skill, running `scripts/apply_seisbench_picker.py --self-test`,
  and applying models to local waveforms are read-only with respect to your data.
  Two side effects to know: (1) `from_pretrained` downloads model weights over
  the internet on first use and caches them locally, and (2) running a model is
  compute-bound (and may move the model to GPU). Neither destroys data. Writing a
  pick table to disk (`--out`) creates/overwrites that one CSV.

steps:
  - name: select-model
    description: >
      Pick a model from the integrated SeisBench catalog that matches the task —
      phase picking (PhaseNet, EQTransformer, GPD, BasicPhaseAE, ...), earthquake
      detection (EQTransformer, CRED), denoising (DeepDenoiser, SeisDAE), or depth
      estimation (DepthPhaseNet, DepthPhaseTEAM). See search_shortcuts
      "Integrated model catalog" for the full table. Prefer an integrated
      pretrained model over building one from scratch.
    outputs:
      - name: model_class
        type: string
        description: SeisBench model class name, e.g. "PhaseNet".

  - name: load-pretrained
    description: >
      List the available weights with `Model.list_pretrained()`, then load one
      with `Model.from_pretrained("<weights>")`. Weights download on first use and
      cache locally; some weights have multiple versions (see `from_pretrained`
      docs). Move the model to the best device — `model.to_preferred_device()` (or
      `model.cuda()`) — before applying it. Pretrained weights are also a good
      starting point for transfer learning.
    depends_on: [select-model]
    inputs:
      - name: model_class
        type: string
    outputs:
      - name: model
        type: object
        description: A loaded SeisBench WaveformModel ready to annotate/classify.

  - name: choose-output-type
    description: >
      Decide which core call you need. `annotate(stream)` returns continuous
      output as an ObsPy Stream — for pickers, the characteristic functions
      (pick probabilities over time). `classify(stream)` returns discrete,
      model-dependent results — a picking model returns a list of picks; a
      picking+detection model returns picks and detections. Both accept a stream
      from multiple stations at once and handle trace grouping automatically.
    depends_on: [load-pretrained]
    one_of:
      - "annotate: continuous characteristic-function Stream (pick probabilities over time)"
      - "classify: discrete results (e.g. a PickList; each pick has trace_id, peak_time, peak_value, phase)"

  - name: apply-picker
    description: >
      Run the model and produce results. The script rescales any tiny-amplitude
      trace (scale <= 1e-10) by 1e10 before the model sees it — SeisBench's
      internal epsilon normalization would otherwise flatten the signal — then
      calls `classify` and extracts each pick into a standard pick table
      (id=trace_id, timestamp=peak_time, prob=peak_value, type=phase lower-cased)
      ready for a downstream associator. Pass a larger batch_size to go faster.
      Use the script's pure functions (rescale_if_tiny, picks_to_records) directly
      if you are wiring the steps into your own code; run `--self-test` to verify
      the deterministic logic offline (numpy only).
    depends_on: [choose-output-type]
    script: scripts/apply_seisbench_picker.py
    inputs:
      - name: model
        type: object
      - name: stream_path
        type: string
        description: Path to an ObsPy-readable waveform file (e.g. MSEED).
      - name: weights
        type: string
        description: Pretrained weights name passed to from_pretrained.
      - name: batch_size
        type: integer
        nullable: true
        description: Larger is faster, especially on GPU, as long as it fits in memory.
    outputs:
      - name: picks_table
        type: object
        description: Rows of {id, timestamp, prob, type} — one per pick, association-ready.

  - name: feed-continuous-stream
    description: >
      Feed the stream as the continuous data it is. SeisBench processes a stream
      of arbitrary length, so do NOT segment the data yourself, and do NOT assume
      a stream contains only one P-wave and one S-wave — a continuous record can
      hold many events. Let annotate/classify handle windowing and multi-station
      grouping internally.
    depends_on: [apply-picker]

anti_patterns:
  - Segmenting the stream into fixed windows yourself, or assuming a single P and single S per stream — treat the stream as continuous data and let the model window it.
  - Feeding tiny-amplitude waveforms (scale <= 1e-10) to the model raw — SeisBench's `(x - mean)/(std + epsilon)` normalization can destroy the signal; rescale by ~1e10 first (the apply-picker script does this automatically).
  - Relying solely on the model's internal normalization — applying your own normalization (after any rescale) is still recommended.
  - Using `annotate` when you need discrete picks, or `classify` when you actually need the continuous characteristic function.
  - Building a model from scratch when an integrated pretrained model already covers the task (picking, detection, denoising, depth).
  - Ignoring the model's required sampling rate — check `model.sampling_rate`; manual resampling beforehand can be faster than letting SeisBench resample on the fly.
  - Leaving the model on CPU for a large dataset without considering GPU, a larger batch_size, torch.compile, or the asyncio interface.

search_shortcuts:
  - category: Core API
    body: >
      Every SeisBench model subclasses `WaveformModel` and exposes two
      auto-generated calls. `annotate(stream)` -> ObsPy Stream of continuous
      output (for pickers, the pick-probability characteristic functions over
      time). `classify(stream)` -> discrete, model-dependent results (a picking
      model returns a PickList; a picking+detection model returns picks and
      detections). Example: `annotations = model.annotate(stream)`;
      `outputs = model.classify(stream)`. Both assemble ObsPy streams into PyTorch
      tensors, batch internally, reassemble results into streams/objects, and
      group traces from multiple stations automatically. For classify pickers,
      `result.picks` is the list of picks; each pick exposes `trace_id`,
      `peak_time` (UTCDateTime; `.datetime` for a plain datetime), `peak_value`
      (probability), and `phase` ("P"/"S"). `trace_id` comes from the stream's
      trace headers (network.station.location.channel), so the picker needs only
      the waveform stream — station coordinates/metadata are not consumed here
      (they belong to a downstream associator).
  - category: Loading pretrained weights
    body: >
      `import seisbench.models as sbm`. `sbm.PhaseNet.list_pretrained()` lists
      available weights; `model = sbm.PhaseNet.from_pretrained("original")` loads
      one (other examples: "instance", "ethz", "scedc"). Weights download on first
      use and cache locally; some have multiple versions — see the `from_pretrained`
      docs. Pretrained weights also seed transfer learning. Move to GPU with
      `model.cuda()` or `model.to_preferred_device()`.
  - category: Integrated model catalog
    body: >
      Models integrated into SeisBench (class -> task): BasicPhaseAE -> Phase
      Picking; CRED -> Earthquake Detection; DPP -> Phase Picking; DepthPhaseNet
      -> Depth estimation from depth phases; DepthPhaseTEAM -> Depth estimation
      from depth phases; DeepDenoiser -> Denoising; SeisDAE -> Denoising;
      EQTransformer -> Earthquake Detection/Phase Picking; GPD -> Phase Picking;
      LFEDetect -> Phase Picking (low-frequency earthquakes); OBSTransformer ->
      Earthquake Detection/Phase Picking; PhaseNet -> Phase Picking; PhaseNetLight
      -> Phase Picking; PickBlue -> Earthquake Detection/Phase Picking; Skynet ->
      Phase Picking; VariableLengthPhaseNet -> Phase Picking. Currently integrated
      models cover earthquake detection and phase picking, waveform denoising,
      depth estimation, and low-frequency earthquake phase picking. SeisBench can
      also be used to build models for general seismic tasks (magnitude/source
      parameter estimation, hypocentre determination, etc.).
  - category: Speeding up model application
    body: >
      Run time matters on large datasets. (1) Run on GPU — usually faster, though
      not always the most economical (a handful of CPU machines can be cheaper and
      comparably fast in the cloud). (2) Use a large `batch_size` (optional arg to
      all models) — especially on GPU, as long as the batch fits in memory.
      (3) Compile the model on torch 2.0+: `model = torch.compile(model)` — pays
      off when annotating large amounts of data; compile options affect the gain.
      (4) Use the asyncio interface (`annotate_asyncio`, `classify_asyncio`) to
      load data in parallel while computing — usually much faster since loading is
      IO-bound and annotation is compute-bound. (5) Manual resampling can beat
      SeisBench's on-the-fly resampling (ObsPy's routines were not parallelised as
      of 2023); check the needed rate with `model.sampling_rate` (alternatives
      exist, e.g. Pyrocko).
  - category: Numerical stability and normalization
    body: >
      For extremely small-scale waveforms (scale <= 1e-10) there is risk of
      numerical instability: SeisBench normalizes as
      `(waveform - mean(waveform)) / (std(waveform) + epsilon)`, and at that scale
      the epsilon dominates and can destroy the signal. Multiply the waveform by a
      large factor (e.g. 1e10) BEFORE normalization / before passing to the model.
      Although the model normalizes internally, applying normalization yourself is
      still highly recommended. `scripts/apply_seisbench_picker.py` applies the
      rescale automatically (functions `rescale_if_tiny` and `normalize`).
  - category: Install and script
    body: >
      Install with `pip install seisbench` (also needs ObsPy and PyTorch).
      `scripts/apply_seisbench_picker.py run --stream <file> --model PhaseNet
      --weights instance --batch-size 256 --out picks.csv` runs the full pipeline
      (rescale -> load weights -> move to device -> classify -> pick table).
      `--self-test` checks the deterministic rescale/extract logic offline (numpy
      only); the full `run` lazily imports obspy + seisbench.

scenarios:
  - need: Pick P/S phases on an hour of continuous multi-station waveforms for downstream event association.
    context: select-model -> PhaseNet (phase picking); load-pretrained -> from_pretrained("instance") and move to device.
    action: >
      Run apply-picker on the MSEED with batch_size 256. The script rescales any
      tiny-amplitude traces, calls classify, and extracts each pick to
      {id=trace_id, timestamp=peak_time, prob=peak_value, type=phase}.
    outcome: A pick table (id/timestamp/prob/type) ready to hand to a phase associator like GaMMA.
  - need: A station's traces are on the order of 1e-11 and the model returns almost no picks.
    context: choose-output-type -> classify, but raw tiny amplitudes are being flattened by internal normalization.
    action: Rescale the trace by 1e10 before passing it to the model (apply-picker does this automatically; standalone, call rescale_if_tiny).
    outcome: The signal survives normalization and the model recovers the picks.
  - need: Annotating a very large dataset is too slow.
    context: Default is single-batch CPU inference.
    action: Increase batch_size, run on GPU, optionally torch.compile (torch 2.0+), and use classify_asyncio/annotate_asyncio so IO and compute overlap.
    outcome: Substantially faster throughput without changing the model or the results' meaning.
```
