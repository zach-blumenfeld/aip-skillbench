---
name: seisbench-model-api
description: An overview of the core model API of SeisBench, a Python framework for training and applying machine learning algorithms to seismic data. It is useful for annotating waveforms using pretrained SOTA ML models, for tasks like phase picking, earthquake detection, waveform denoising and depth estimation. For any waveform, you can manipulate it into an obspy stream object and it will work seamlessly with seisbench models.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Reference for using the SeisBench Python framework
  (https://github.com/seisbench/seisbench) to apply pretrained machine learning
  models to seismic waveform data. SeisBench wraps PyTorch models behind a
  common `WaveformModel` interface that consumes and returns ObsPy `Stream`
  objects, automatically batching traces and reassembling outputs. The skill
  documents the two core methods (`annotate` for continuous characteristic
  functions, `classify` for discrete picks/detections), how to load pretrained
  weights via `from_pretrained`, optimizations for large-scale annotation
  (GPU, batch size, `torch.compile`, asyncio, manual resampling), the catalog
  of integrated models (phase picking, earthquake detection, denoising, depth
  estimation, low-frequency earthquakes), and numerical-stability best
  practices for very small-amplitude waveforms.

trigger_when:
  - User wants to annotate seismic waveforms with a pretrained ML model (phase picking, earthquake detection, denoising, depth estimation).
  - User mentions SeisBench, PhaseNet, EQTransformer, GPD, CRED, DeepDenoiser, DepthPhaseNet, or any other SeisBench-integrated model.
  - User has an ObsPy `Stream` (or raw waveform data convertible to one) and needs characteristic functions, pick lists, or detection lists.
  - User asks how to load pretrained model weights for a seismic ML model.
  - User needs to speed up large-scale waveform annotation (GPU, batching, `torch.compile`, asyncio data loading, resampling).
  - User asks how to choose between `annotate` (continuous output) and `classify` (discrete output) on a SeisBench model.
  - User reports numerical issues with very small-amplitude waveforms (`<= 1e-10`) fed to SeisBench.

do_not_use_when:
  - User needs phase association (clustering picks into events) rather than producing picks. Use a phase associator (e.g., GaMMA) instead.
  - User needs to read or manipulate waveforms but not apply an ML model. Use ObsPy directly.
  - User is training a new model from scratch with custom architecture. This skill covers application of `WaveformModel` subclasses and `from_pretrained`; consult SeisBench's `WaveformModel` and dataset docs for training.
  - User needs source parameter estimation, hypocenter determination, or magnitude estimation as the primary task — SeisBench can support these but no integrated pretrained models ship for them today.

scope_and_approval: >
  Read-only reference for an agent writing Python that imports
  `seisbench.models`. The skill prescribes how to load models, prepare ObsPy
  streams, call `annotate` / `classify`, and tune performance; it does not
  itself execute model runs. `pip install seisbench` and the first-use weight
  download (`from_pretrained`) both touch the network and the local cache —
  confirm with the user before running in a managed environment.

steps:
  - name: install-seisbench
    description: |
      Install SeisBench via pip:

      ```
      pip install seisbench
      ```

      Confirm with the user before adding the dependency to a managed
      environment. SeisBench pulls in PyTorch and ObsPy as dependencies.

  - name: select-and-load-pretrained-model
    description: |
      Pick a model class from `seisbench.models` matching the task (see the
      `Integrated models` entry under `search_shortcuts`), then load
      pretrained weights via `from_pretrained`. Weights are downloaded on
      first use and cached locally.

      ```python
      import seisbench.models as sbm

      sbm.PhaseNet.list_pretrained()                    # List available weight sets
      model = sbm.PhaseNet.from_pretrained("original")  # Load the original PhaseNet weights
      ```

      Some model classes expose multiple weight versions; consult the
      `from_pretrained` docstring for version selection. Pretrained models
      are also a good starting point for transfer learning.

  - name: prepare-obspy-stream
    description: |
      Build an ObsPy `Stream` from the waveform source. Any waveform format
      ObsPy can read works; the model consumes the `Stream` directly and
      handles per-station grouping internally.

      ```python
      import obspy
      stream = obspy.read("my_waveforms.mseed")
      ```

      The stream may contain traces from multiple stations and arbitrary
      length — do **not** pre-segment it and do **not** assume a single
      P/S pair per stream. SeisBench treats the input as continuous data.

  - name: normalize-or-rescale-if-tiny-amplitudes
    description: |
      If raw waveform amplitudes are extremely small (`<= 1e-10`), the
      framework's internal normalization
      `(waveform - mean(waveform)) / (std(waveform) + epsilon)` can collapse
      the signal because of the epsilon term. Rescale before passing to the
      model (e.g., multiply by `1e10`) and/or normalize the waveform yourself.
      Even when amplitudes are well-scaled, applying your own normalization
      is recommended for stability.

  - name: annotate-or-classify
    description: |
      Pick the appropriate inference method based on the desired output shape.

      `annotate` returns a continuous-output `Stream` (e.g., pick
      probabilities over time for picking models):

      ```python
      annotations = model.annotate(stream)  # Returns an ObsPy Stream of characteristic functions
      ```

      `classify` returns discrete results whose structure depends on the
      model — a picking model returns a list of picks; a combined
      picking/detection model returns picks plus detections:

      ```python
      outputs = model.classify(stream)
      print(outputs)
      ```

      Both methods accept multi-station streams and handle trace grouping
      automatically. Pass `batch_size` to control inference batching.

  - name: tune-performance
    description: |
      For large datasets, apply the optimizations listed in the
      `decisions` table (GPU placement, larger `batch_size`, `torch.compile`
      under PyTorch 2.0+, the `annotate_asyncio` / `classify_asyncio`
      interfaces, and manual resampling to `model.sampling_rate` before
      inference). GPU is usually fastest but not always the most economical
      — for cloud workloads a fleet of CPU machines can match a single GPU
      machine at lower cost.

decisions:
  - signal: Need a continuous characteristic function (e.g., pick probability over time).
    action: Call `model.annotate(stream)`; output is an ObsPy `Stream`.
  - signal: Need discrete results (pick list, detection list).
    action: Call `model.classify(stream)`; output structure is model-dependent (list of picks, or picks plus detections).
  - signal: Inference is slow and a GPU is available.
    action: Move the model to GPU (`model.cuda()` or `.to("cuda")`). Speed-up varies by model.
  - signal: Inference is slow on cloud infrastructure and cost matters.
    action: Consider a fleet of CPU machines instead of a single GPU — often comparable speed at lower cost.
  - signal: Memory headroom is available during inference.
    action: Increase `batch_size` (passed as a kwarg to `annotate` / `classify`). Especially impactful on GPUs.
  - signal: PyTorch version is 2.0 or newer and the workload is large.
    action: Compile the model with `model = torch.compile(model)`. First call is slow; subsequent calls amortize the cost. Explore `torch.compile` options for further gains.
  - signal: Data loading appears to bottleneck annotation (IO-bound).
    action: Use `model.annotate_asyncio` / `model.classify_asyncio` to overlap data loading with compute.
  - signal: Many waveforms need resampling to the model's expected rate.
    action: Resample manually (e.g., with the Pyrocko library) before calling the model, since ObsPy's resampling routines used by SeisBench are not parallelised. The required rate is `model.sampling_rate`.
  - signal: Raw waveform amplitudes are extremely small (`<= 1e-10`).
    action: Multiply the waveform by a large factor (e.g., `1e10`) before normalization or passing to the model to avoid numerical instability from the normalization epsilon.

search_shortcuts:
  - category: Integrated models
    body: |
      Models shipped under `seisbench.models` (loadable via `from_pretrained`):

      | Model                    | Task                                            |
      |--------------------------|-------------------------------------------------|
      | `BasicPhaseAE`           | Phase picking                                   |
      | `CRED`                   | Earthquake detection                            |
      | `DPP`                    | Phase picking                                   |
      | `DepthPhaseNet`          | Depth estimation from depth phases              |
      | `DepthPhaseTEAM`         | Depth estimation from depth phases              |
      | `DeepDenoiser`           | Denoising                                       |
      | `SeisDAE`                | Denoising                                       |
      | `EQTransformer`          | Earthquake detection / phase picking            |
      | `GPD`                    | Phase picking                                   |
      | `LFEDetect`              | Phase picking (low-frequency earthquakes)       |
      | `OBSTransformer`         | Earthquake detection / phase picking            |
      | `PhaseNet`               | Phase picking                                   |
      | `PhaseNetLight`          | Phase picking                                   |
      | `PickBlue`               | Earthquake detection / phase picking            |
      | `Skynet`                 | Phase picking                                   |
      | `VariableLengthPhaseNet` | Phase picking                                   |

      Capabilities span earthquake detection, phase picking (including
      low-frequency earthquakes), denoising, and depth estimation. SeisBench
      can also be used to build models for magnitude / source parameter
      estimation and hypocentre determination, though no pretrained weights
      are integrated for those tasks today.

scenarios:
  - need: Apply PhaseNet to a multi-station miniSEED file and obtain pick probability traces.
    context: A `.mseed` file with several stations of continuous data is available locally.
    action: |
      ```python
      import obspy
      import seisbench.models as sbm

      model = sbm.PhaseNet.from_pretrained("original")
      stream = obspy.read("my_waveforms.mseed")
      annotations = model.annotate(stream)
      ```
    outcome: "`annotations` is an ObsPy `Stream` of P/S pick probability time series, with per-station grouping handled automatically."
  - need: Produce a discrete list of P/S picks for downstream phase association.
    context: A combined picking model (e.g., EQTransformer or PhaseNet) is preferred and the user wants events, not probability traces.
    action: |
      ```python
      outputs = model.classify(stream)
      ```
    outcome: "`outputs` contains a list of picks (and, for combined detection/picking models, a list of detections) ready to feed an associator."
  - need: Accelerate annotation across a large continuous dataset.
    context: PyTorch 2.0+ is available; a GPU is attached; data loading is IO-bound.
    action: |
      ```python
      model = model.to("cuda")
      model = torch.compile(model)
      annotations = await model.annotate_asyncio(stream, batch_size=256)
      ```
    outcome: "Compute and data loading overlap; large `batch_size` saturates the GPU; compiled graph amortizes over the long run."

anti_patterns:
  - Passing very small-amplitude waveforms (`<= 1e-10`) without rescaling. SeisBench's normalization epsilon can suppress the signal entirely; rescale or normalize manually first.
  - Relying solely on SeisBench's internal normalization for ill-scaled inputs. Even when amplitudes look reasonable, applying explicit normalization is the safer default.
  - Pre-segmenting streams into single-event windows. SeisBench handles arbitrary-length streams and may detect multiple P/S pairs per stream — let it.
  - Assuming a stream contains exactly one P-wave and one S-wave. Treat the input as continuous data with potentially many or zero arrivals.
  - Resampling inside SeisBench when the workload is large. ObsPy's resampling (as of 2023) is single-threaded; resample manually with a parallel routine (e.g., Pyrocko) to the rate reported by `model.sampling_rate`.
  - Reaching for a GPU by default. GPU is usually faster but for cloud workloads a fleet of CPU machines may match the throughput at lower cost.
  - Calling `annotate` when the downstream consumer needs discrete picks, or `classify` when it needs the underlying characteristic function. Pick the method that matches the output shape.
```
