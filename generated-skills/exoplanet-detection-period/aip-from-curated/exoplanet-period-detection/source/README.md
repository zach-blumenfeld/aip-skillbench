# Source materials and compilation notes

This AIP skill was compiled from five curated Agent Skills under
`./inputs/skills/`:

| Source                        | Role in the compiled procedure                                         |
|-------------------------------|------------------------------------------------------------------------|
| `exoplanet-workflows`         | Overall pipeline shape, decision rubric for signal strength            |
| `light-curve-preprocessing`   | `load-qc` quality-flag convention, `preprocess` sigma-clip + flatten    |
| `transit-least-squares`       | `tls-search` and `refine` scripts; refinement window; metrics          |
| `box-least-squares`           | Fallback-method guidance in `references/method-selection.md`           |
| `lomb-scargle-periodogram`    | Non-transit-signal escape hatch in `references/method-selection.md`    |

The five original SKILL.md files are copied verbatim under this directory
with their folder names unchanged, so the provenance of any specific claim
in the compiled skill can be chased back to its source.

## Step-kind choices

Every step is an `execution` or a decision + router. The pipeline is a
mostly-linear deterministic numeric pipeline, so scripts dominate:

- `load-qc` — **execution**. File parsing, flag filtering, finite checks,
  sorting, and cache writing are all deterministic rules over structured
  inputs. No judgment element.
- `preprocess` — **execution**. Sigma-clip thresholds (3 then 5) and the
  cadence-driven Savitzky-Golay window length are deterministic. The
  flatten library call is domain logic.
- `tls-search` — **execution**. TLS is the specialised algorithm; wrapping
  it is a tool call. Period window defaults (cadence * 3 .. baseline/2,
  capped at 50 days) are hard-coded per source guidance.
- `classify` — **decision**. SDE/SNR thresholds *could* be a script, but
  the source material explicitly describes judgment nuance ("warning
  signs" like period aliasing, odd-even mismatch, transit_count sanity).
  A decision step lets the client override the pure-numeric call when the
  context (e.g. small transit_count, obvious aliasing) warrants it, and
  the threshold on `strength` surfaces close calls for review. It is still
  cheap: one SystemOne call with a well-defined rubric.
- `refine-router` — **router**. Branches on the `strength` label the
  decision produced; strong/moderate refine, weak skips to end.
- `refine` — **execution**. Narrow-window TLS pass, same wrapper as
  `tls-search` with a +/-5% period window.
- `end` — **end**. Declares the final-state shape (period, uncertainty,
  SDE, SNR, T0, depth, duration, strength).

No `client_task` steps: nothing in the pipeline requires the client to
author text, synthesise a plan, or produce free-form output. The output
is a measurement plus metrics.

## Why a single procedure graph

The five source skills jointly describe one workflow:
quality-filter → preprocess → broad-search → validate → refine. Keeping
them as five skills forces the agent to context-switch between SKILL.mds
and reconstruct the ordering on every invocation. Compiling them into one
graph gates the ordering, enforces the input shape at each stage, and
puts the TLS SDE/SNR classification rubric in a decision step where it
can be audited and tuned.

## Deliberate drops

Items from the source skills intentionally not represented in the
compiled procedure, with rationale:

### `box-least-squares/SKILL.md`

- **Full BLS code example (lines 30-144)**, `autopower` / `power` /
  `compute_stats` recipes. **Dropped — recorded in reference.** BLS is
  the fallback method and the skill never calls it; the agent is pointed
  to `references/method-selection.md` to switch if TLS is unavailable.
  Full code is a one-line reach into the source skill when needed.
- **BLS vs TLS pros/cons table (lines 236-263)**. **Dropped — captured.**
  The condensed selection matrix in `references/method-selection.md`
  carries the actionable version; the full prose is background.
- **Objective-function discussion** (`likelihood` vs `snr`, lines 84-103).
  **Dropped — not actionable here.** TLS has no equivalent switch, and
  BLS is not in the default pipeline.
- **"Comparing multiple peaks" and top-5 enumeration (lines 196-216)**.
  **Dropped — out of scope.** This skill reports the single dominant
  period; multi-peak comparison is a downstream workflow (noted in
  `do_not_use_when`).

### `lomb-scargle-periodogram/SKILL.md`

- **All code recipes (lines 14-93)**: `to_periodogram`, period range
  selection, model fitting. **Dropped — recorded in reference.** LS is
  not in the default pipeline; the agent is pointed to the reference and
  the source skill if the signal turns out to be non-transit.
- **Harmonics / aliasing warnings (lines 70-75)**. **Captured — in
  `references/troubleshooting.md`.** TLS has the same aliasing failure
  mode and the troubleshooting reference consolidates the guidance.

### `transit-least-squares/SKILL.md`

- **Phase-folding plot recipes (lines 108-126) and model-light-curve
  recipes (lines 171-188)**. **Dropped — out of scope.** This skill
  measures the period; visualisation and the full model are a downstream
  concern.
- **Transit-masking recipe for multi-planet search (lines 128-146)**.
  **Dropped — flagged in `do_not_use_when`.** Multi-planet discovery is
  the "run this skill again on masked data" workflow, not a step inside
  this procedure.
- **"flux_err required" warning (line 236-238)**. **Captured** — as a
  gate in `scripts/load_qc.py` (any cadence with zero/non-finite flux_err
  is dropped) and in the `compatibility` + anti-patterns of SKILL.md.
- **oversampling_factor / duration_grid_step / T0_fit_margin tuning
  (lines 94-105)**. **Captured partially** — `refine.py` passes
  `oversampling_factor=3` for the dense pass. The rest are left to TLS
  defaults; exposing them as state keys would be premature.
- **SDE/SNR thresholds (6, 9 for SDE; 7 for SNR)**. **Captured** in the
  `classify` decision rubric and `references/troubleshooting.md`.

### `light-curve-preprocessing/SKILL.md`

- **Symmetric `sigma=3` outlier-removal recipe (lines 25-35)**.
  **Deliberate deviation — recorded here.** The source recipe runs
  `lc.remove_outliers(sigma=3)` symmetrically before flattening. That
  wipes out transits deeper than ~1% because the raw-flux standard
  deviation is dominated by the signal itself (a 2% hot-Jupiter transit
  sits well outside the 3-sigma band and gets clipped). `preprocess.py`
  instead runs `remove_outliers(sigma_upper=3, sigma_lower=np.inf)` on
  both passes, keeping all negative excursions. The transit search is a
  negative-outlier hunt by construction, so low-side clipping is always
  wrong here. Verified empirically: a synthetic 2% transit survives
  the modified clip (SDE 30) and is destroyed by the symmetric clip
  (SDE 6, wrong period).
- **Manual (non-lightkurve) outlier-removal recipe (lines 36-49)**.
  **Dropped — redundant.** `preprocess.py` uses the lightkurve path
  with the asymmetric-sigma fix noted above.
- **Iterative sine-fitting recipe for stellar-variability removal
  (lines 69-85)**. **Dropped — explicitly warned against in the source
  itself** ("This removes periodic signals, so use carefully if you're
  searching for periodic transits"). We are searching for periodic
  transits; sine-fitting would be an active footgun here.
- **"Alternative formats where flag=0 is BAD" (lines 103-108)**.
  **Deliberate drop — recorded here.** The input format for this task
  (per `inputs/environment/data/tess_lc.txt` and MANIFEST) is standard
  TESS where `flag == 0` is good. Supporting the inverted convention
  would require a format-detection heuristic without a reliable signal
  from the file itself; false positives would silently drop all data.
  The convention is called out in the `load_qc.py` docstring; if a user
  presents the alternative format they must pre-flip the flag column.
- **Window length guidance "100-200 short, 300-500 medium, 500-1000 long"
  (lines 59-64)**. **Captured** — `preprocess.py` computes the window
  from cadence to span ~16 hours; for 2-min TESS cadence this lands at
  ~481 cadences, in the middle of the source's recommended range.

### `exoplanet-workflows/SKILL.md`

- **General multi-planet strategy (lines 112-121)**. **Deferred** — this
  skill reports the single dominant period, as flagged in
  `do_not_use_when`. The strategy itself is one-sentence prose and does
  not add instructions beyond "mask and repeat".
- **"Expected Transit Depths" table (lines 152-159) and "Period Range
  Guidelines" (lines 161-170)**. **Captured** —
  `references/troubleshooting.md` carries the depth table, and the
  period-range sanity ("baseline/2" cap, 0.5-50 day defaults) is coded
  into `tls_search.py` with the rationale in its docstring.
- **"Best Practices" numbered list (lines 170-182)**. **Fully
  distributed.** Items 1 (flux_err), 4 (sigma values), 5 (refine), 6
  (SDE/SNR validation), 7 (data gaps / aliasing) are encoded in scripts
  or the classify rubric. Items 2 (visualise), 3 (check flag convention),
  8 (document workflow) are human-process items that an autonomous agent
  invocation of this skill cannot act on, and are not represented.
- **"Dependencies" installation lines in every source skill**.
  **Dropped — captured in `compatibility` on SKILL.md.** Single source
  of truth; the duplicated per-skill `pip install` blocks were redundant.
- **"References / Papers / Official Documentation" sections across all
  five skills**. **Deliberate drops** — background rather than
  actionable. An agent executing the skill does not need the Kovács 2002
  citation to pick a sigma value; a researcher inspecting the source
  tree can still find them in the verbatim copies under this directory.
