# Source materials — seisbench-model-api (AIP compilation)

This skill was compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/earthquake-phase-association/environment/skills/seisbench-model-api/`
into AIP format. The original SKILL.md is preserved verbatim in
`ORIGINAL_SKILL.md`, and the schema the AIP body validates against is bundled as
`procedure.schema.json` (the canonical `procedure` schema from the AIP spec —
`$id: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json`,
byte-identical to the spec copy).

The `name:` frontmatter is unchanged (`seisbench-model-api`) so the mounted skill
name matches what the task expects.

## Task context

The skill is one of four shipped with the `earthquake-phase-association` task,
which asks an agent to build an earthquake catalog from raw waveforms: load data
→ pick P/S phases with a deep-learning model → associate picks into events →
write `/root/results.csv` (graded on F1 ≥ 0.6 against a human catalog). This
skill owns the **phase-picking** step — applying a pretrained SeisBench model to
an ObsPy stream and producing picks. Its siblings cover the rest:

- `obspy-data-api` — reading/manipulating the waveform and station files.
- `seismic-picker-selection` — strategic choice of detection paradigm (deep
  learning vs STA/LTA vs template matching vs manual).
- `gamma-phase-associator` — associating the picks this skill produces into
  events.

`do_not_use_when` in the body routes each of those concerns to the right sibling
so the four skills compose without overlap and this one stays self-contained.

## Schema choice

The original is an *API overview* of the SeisBench model interface — how to
install it, the `WaveformModel.annotate` / `classify` calls, how to load
pretrained weights, how to make application faster, the catalog of integrated
models, and best practices. Framed as "consult before you apply a model," that
overview is a short procedure: select a model from the catalog → load pretrained
weights and move to device → choose annotate vs classify → preprocess and run →
feed the stream as continuous data. The `procedure` schema models exactly this
(`steps` with `depends_on` edges, `one_of` for the annotate/classify fork,
`script` for the node that carries the numeric threshold), and its optional
fields carry the rest of the overview (`search_shortcuts` for the catalog and the
lookup/reference content, `scenarios` for worked examples, `anti_patterns`,
`scope_and_approval`, `compatibility`). So `procedure` was adopted as-is rather
than drafting a new `reference`-style schema — consistent with AIP's bias toward
schema reuse and with the curated skills in the sibling `debug-trl-grpo` task,
which also compile to `procedure`.

## Value-add script

One script was authored that the original skill lacked:
`scripts/apply_seisbench_picker.py`. It is the AIP value-add — the original
overview describes the API and the best-practice rules in prose but ships nothing
runnable. The script makes the two pieces of the picking step that are exact,
input-independent computation executable (per the AIP rule that numeric
thresholds and fixed mappings belong in code, not prose):

1. **Tiny-amplitude rescale (a numeric threshold).** The Best Practices section
   says waveforms with scale `<= 1e-10` risk having their signal destroyed by
   SeisBench's `(x - mean)/(std + epsilon)` normalization, and should be
   multiplied by a large factor (`1e10`) first. `rescale_if_tiny` encodes that
   rule (with a guard so flat all-zero traces are left untouched).
2. **Pick extraction (a fixed field mapping).** `classify(stream).picks` yields
   pick objects exposing `trace_id` / `peak_time` / `peak_value` / `phase`;
   `picks_to_records` maps them to the standard `{id, timestamp, prob, type}`
   pick-table columns a downstream associator expects, lower-casing the phase.

The deterministic functions are numpy-only and covered by `--self-test`
(rescale threshold incl. the `<=` boundary and the flat-trace guard, normalize
mean-centering, and the pick field mapping), so they run offline without the
heavy stack. The full `run` subcommand lazily imports `obspy` and `seisbench`
(declared as optional `--with` deps in the PEP 723 header) and executes the
whole pipeline: read stream → rescale → `from_pretrained` → move to device →
`classify` → pick CSV.

## Why the reasoning steps stay prose (not script-backed)

`select-model`, `load-pretrained`, `choose-output-type`, and
`feed-continuous-stream` carry no fixed-input computation — they describe how the
agent reasons about an arbitrary task and stream (which model fits, which weights
to load, annotate vs classify, how to feed continuous data). The catalog they
draw on is a reference lookup, surfaced in `search_shortcuts[Integrated model
catalog]` rather than as a decision function. The only step that *is* mechanical
computation over fixed inputs — the rescale threshold and the pick mapping in
`apply-picker` — is script-backed.

## Content mapping (completeness check)

Every distinct piece of the original SKILL.md was classified:

- **Installing SeisBench** (`pip install seisbench`) → `compatibility` +
  `search_shortcuts[Install and script]` (mapped).
- **Overview** — `WaveformModel`, auto-generated `annotate`/`classify`, the
  PyTorch↔ObsPy bridge (assembles streams into tensors, reassembles results,
  batch processing, GPU by moving the model) → `purpose` +
  `search_shortcuts[Core API]` (mapped).
- **annotate semantics** (returns a Stream; for pickers the characteristic
  functions / pick probabilities) and its code example → `search_shortcuts[Core
  API]`, the `choose-output-type` step's `one_of` (mapped).
- **classify semantics** (discrete, model-dependent results; picks vs
  picks+detections) and its code example → `search_shortcuts[Core API]`,
  `choose-output-type` `one_of`, and the `apply-picker` pick extraction (mapped).
- **Multi-station grouping** (both calls accept multiple stations and group
  traces automatically) → `choose-output-type` step (mapped).
- **Loading Pretrained Models** (weights required; common interface;
  download+cache; multiple versions; `list_pretrained`/`from_pretrained`;
  transfer-learning starting point) → `load-pretrained` step +
  `search_shortcuts[Loading pretrained weights]` (mapped).
- **Speeding Up Model Application** (GPU; large `batch_size`; `torch.compile` on
  torch 2.0+; asyncio `annotate_asyncio`/`classify_asyncio`; manual resampling +
  `model.sampling_rate`) → `search_shortcuts[Speeding up model application]`,
  plus a `scenario` and two `anti_patterns` (mapped).
- **Models Integrated into SeisBench** (the full class→task table, plus the note
  that SeisBench can build models for general seismic tasks) →
  `search_shortcuts[Integrated model catalog]` and the `select-model` step
  (mapped — the table's rows folded into prose).
- **Best Practices — tiny-amplitude rescale** (`<= 1e-10` → multiply by `1e10`
  before normalization/model) → `apply-picker` step + `rescale_if_tiny` in the
  script + `search_shortcuts[Numerical stability and normalization]` + an
  `anti_pattern` + a `scenario` (mapped, script-backed).
- **Best Practices — apply normalization yourself** (the epsilon formula
  `(x - mean)/(std + epsilon)`) → `search_shortcuts[Numerical stability and
  normalization]` + the script's `normalize` function + an `anti_pattern`
  (mapped).
- **Best Practices — arbitrary-length continuous stream** (don't segment; don't
  assume one P + one S; treat as continuous) → the `feed-continuous-stream` step
  + `anti_patterns` (mapped).

### Deliberate drops

- The two "for details, see…" pointers — *"check the documentation of
  `WaveformModel`"* (building your own model) and *"check out the Examples"* (how
  to apply models) — are not reproduced as standalone instructions. Building a
  custom model is out of scope for a skill about applying pretrained models; the
  intent is retained as `select-model`'s guidance to "prefer an integrated
  pretrained model over building one from scratch," and the application "how-to"
  is exactly what the rest of this skill provides. No factual content was lost.

No source content was dropped beyond the deliberate item above.

## Licensing

SeisBench and ObsPy ship their own licenses (the task bundles them under
`environment/skills/licenses/`). The original SKILL.md declared no `license:`
field, so none is asserted here.
