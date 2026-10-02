# exoplanet-transit-detection — source provenance and deliberate-drop log

## Provenance

This skill compiles five curated Agent Skills from the SkillsBench task
`exoplanet-detection-period` into one AIP procedure. All originals are preserved
verbatim under `source/curated/`:

- `exoplanet-workflows/SKILL.md` — pipeline design principles, method selection, signal validation.
- `light-curve-preprocessing/SKILL.md` — quality flags, sigma-clipping, `flatten()`, order-of-operations.
- `transit-least-squares/SKILL.md` — TLS basic usage, refinement strategy, SDE/SNR thresholds, transit masking.
- `box-least-squares/SKILL.md` — astropy BLS `autopower`/`power`, objective functions, `compute_stats`.
- `lomb-scargle-periodogram/SKILL.md` — lightkurve LS usage, period range guidance, harmonics/aliasing.

The task's own `instruction.md` and reference `solution/solve.sh` are copied in
as `source/task-instruction.md` and `source/reference-solve.sh` so the exact
success criteria (period at 5 decimal places, written to `/root/period.txt`) and
reference algorithm choice (TLS with default range + ±5% refinement) are
preserved next to the curated method docs.

## Step-kind choices

The workflow reduces to a linear preprocessing → search → write pipeline with a
one-way branch at the algorithm choice. Kind selections follow AIP's
"scripts for deterministic logic, decisions for judgment, client tasks only for
generation" rule:

- **preprocess** (`execution`): quality-flag filter, sigma-clip, and `flatten()`
  are deterministic numeric operations over an array. Script.
- **pick-method** (`choice` decision): choosing between TLS / BLS / LS is a
  judgment over the signal type and the source-material guidance in
  `exoplanet-workflows` and `transit-least-squares`. The answer space is
  three labeled options — a `choice` primitive. Threshold 0.4 flags borderline
  cases (e.g. deep box vs shallow grazing) to the client.
- **route-method** (`router`): pure server-side branch on the decision output.
- **tls-search / bls-search / ls-search** (`execution`): each is a two-stage
  numeric period search (broad → ±5% refinement). Scripts, one per algorithm to
  keep dependencies local to the branch that needs them.
- **write-output** (`execution`): deterministic formatting (`f"{period:.5f}\n"`)
  and a filesystem write. Script.
- **end**: the final `{period, output_path}` shape the client receives.

Rejected alternatives:
- A `client_task` for method selection was rejected because the choice space is
  small, described, and the source material spells out the mapping — a decision
  captures it more consistently.
- A validation `decision` step after the search (SDE / SNR thresholds, odd/even
  mismatch) was rejected because the thresholds are hard numbers already
  documented in the source (SDE > 6, depth_snr > 7, odd-even < 3σ). A better
  future extension is a `validate` execution step that reads these metrics off
  the search output and either passes or flags; kept out of this compilation to
  match the reference solution's flow verbatim.

## Deliberate-drop log

Content from the source SKILL.md files that was intentionally left out of the
compiled procedure and lives only under `source/curated/` for the reader:

- **Prose narrative about pipeline design principles** (exoplanet-workflows §
  "Overview", "Pipeline Design Principles" preambles). Background; the same
  principles are encoded operationally in the step ordering and the
  `anti_patterns` list.
- **Method comparison prose** (exoplanet-workflows § "Choosing the Right
  Method" tables of advantages/disadvantages). Distilled into the `pick-method`
  decision's `criteria`. Full comparison remains in `source/curated/`.
- **Multi-planet transit-mask workflow** (transit-least-squares § "Transit
  Masking", exoplanet-workflows § "Multi-Planet Systems"). The task only asks
  for one period; masking + re-search is a separate procedure. Not needed for
  correctness on this task type.
- **Iterative sine-fitting detrending** (light-curve-preprocessing §
  "Iterative Sine Fitting"). Intentionally not the reference method: it removes
  periodic signals, so it risks eating the transit. `flatten()` (Savitzky-Golay)
  is used instead per the reference solution.
- **Alternative quality-flag convention `flag != 0`** (light-curve-preprocessing).
  The TESS data for this task uses the standard convention (`flag == 0` = good);
  the alternative convention exists in the source but the loader assumes the
  standard convention. Documented in `source/README.md` for the reader.
- **Explicit period-range guidelines by planet type** (exoplanet-workflows §
  "Period Range Guidelines" — hot Jupiter 0.5-10 d, warm 10-100 d, habitable
  zone 200-400 d). The TLS default grid already covers 0.5-10 d for
  hot-Jupiter-class signals; the BLS branch script uses `autopower`; the LS
  branch uses 0.5-50 d. Numeric ranges preserved in the scripts.
- **Phase-folding and model-plotting code** (transit-least-squares, box-least-
  squares § "Phase-Folded Light Curve", "Model Light Curve"). Diagnostic /
  visualization only; the task requires a single number in `period.txt`.
- **Manual outlier removal snippet using `np.median`/`np.std`**
  (light-curve-preprocessing). Superseded by `lightkurve.remove_outliers(sigma=3)`
  which the reference solution uses.
- **Detailed BLS `compute_stats` odd/even mismatch validation and top-5
  ranking loop** (box-least-squares § "Peak Statistics for Validation",
  "Comparing BLS Results"). The BLS branch computes `depth`, `snr` and `t0`
  from `compute_stats`; the full odd/even and multi-peak workflow is a manual
  follow-up, not required for a single-number answer.
- **Installation instructions** (`pip install ...` in every source SKILL.md).
  Captured once in the top-level `compatibility:` field.
- **General references / URLs** (Lightkurve tutorials, TLS GitHub, key papers).
  Kept verbatim under `source/curated/` for provenance; not surfaced in the
  procedure body because the schema's `references` field only attaches to
  `client_task` steps and this procedure has none.

## Numeric parameters preserved

Values that the procedure must carry are encoded in the scripts (not prose):

- `sigma=3` outlier removal — matches reference solve.
- `lightkurve.flatten()` default window — matches reference solve.
- TLS `power()` default period grid for stage 1 — matches reference solve.
- Refinement window `0.95 * P0` to `1.05 * P0` — matches reference solve.
- BLS duration grid `np.linspace(0.05, 0.30, 10) * u.day` — from box-least-squares source.
- LS bounds `minimum_period=0.5, maximum_period=50` days — from lomb-scargle-periodogram + exoplanet-workflows period guidance.
- Output precision `f"{period:.5f}\n"` — matches task instruction.

## Container dependencies (informational)

The SkillsBench task container installs Python 3.12 with:
`lightkurve==2.4.2`, `transitleastsquares==1.32`, `astropy==6.0.1`,
`numpy==1.26.4`, `scipy==1.13.1`, `batman-package==2.5.2`,
`setuptools<81` (distutils shim for batman on 3.12+). The scripts assume these
are on `PYTHONPATH`.
