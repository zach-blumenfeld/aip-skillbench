# Source materials — seismic-picker-selection (AIP compilation)

This skill was compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/earthquake-phase-association/environment/skills/seismic-picker-selection/`
into AIP format. The original SKILL.md is preserved verbatim in
`ORIGINAL_SKILL.md`, and the schema the AIP body validates against is bundled as
`procedure.schema.json` (the canonical `procedure` schema from the AIP spec —
`$id: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json`,
byte-identical to the spec copy).

The `name:` frontmatter is unchanged (`seismic-picker-selection`) so the mounted
skill name matches what the task expects.

## Task context

This skill is one of four shipped with the `earthquake-phase-association` task,
which asks an agent to build an earthquake catalog from raw waveforms: load data
→ pick P/S phases with a deep-learning model → associate picks into events →
write `/root/results.csv` (graded on F1 ≥ 0.6 against a human catalog). This skill
owns the **strategic method-selection** step — choosing the detection paradigm —
which is logically the *first* decision and the one that points the agent at deep
learning (the paradigm the task's reference solution uses). Its siblings cover the
rest:

- `obspy-data-api` — reading/manipulating the waveform and station files.
- `seisbench-model-api` — applying a pretrained deep-learning model to produce picks.
- `gamma-phase-associator` — associating the picks into events.

`do_not_use_when` routes each downstream concern to the right sibling so the four
skills compose without overlap and this one stays self-contained.

## Schema choice

The original is a **method-selection guide** — a comparison matrix plus
per-method advantages/limitations for STA/LTA, manual picking, deep learning, and
template matching, with the closing insight that "purpose and resources should
guide your choice." Framed as "consult before you commit to a detection
paradigm," that guide is a short decision procedure: gather your constraints →
review the tradeoffs → score the viable methods against your goal → decide and
record why. The `procedure` schema models exactly this (`steps` with `depends_on`
edges, `one_of` for the four mutually-exclusive method choices, `script` for the
node that carries the lookup table + viability rules), and its optional fields
carry the rest of the guide (`search_shortcuts` for the matrix and the per-method
profiles, `scenarios` for worked selection examples, `anti_patterns`,
`scope_and_approval`, `compatibility`). So `procedure` was adopted as-is rather
than drafting a new `decision-guide`/`rubric` schema — consistent with AIP's bias
toward schema reuse and with the three sibling skills in this same task, which
also compile to `procedure`.

## Value-add script

One script was authored that the original lacked: `scripts/recommend_picker.py`.
It is the AIP value-add — the original states the comparison matrix and the
selection rules in prose but ships nothing runnable. Per the AIP rule that lookup
tables and if/then rules belong in code rather than prose, the script makes the
guide's deterministic logic executable:

1. **The comparison matrix (a lookup table).** Each method's
   generalizability / sensitivity / speed-ease / false-positive ratings are
   encoded once as the structured source of truth (`METHODS`); `show` prints the
   table and the full per-method profiles.
2. **Viability rules (hard if/then gates from the guide).** Template matching
   "requires prior knowledge — template waveforms with good picks from a
   preexisting catalog," and deep learning "requires continuous seismic data." The
   script gates these out (`_viability`) instead of leaving the agent to remember
   them.
3. **Goal-weighted ranking.** Goal presets weight the four matrix dimensions and
   the script ranks the viable methods, attaching a per-method rationale and the
   method's watch-outs. Output is explicitly **decision support, not a verdict**
   (see "Over-restriction" below).

The script is pure standard library (argparse + json), so it runs anywhere with
no install, and `--self-test` covers the load-bearing behaviors offline: matrix
integrity, template matching non-viable without templates, deep learning
non-viable without continuous data, the task-default situation recommending Deep
Learning, max-sensitivity-with-templates recommending Template Matching, and the
ranking always being a full permutation of the four methods.

### One sourced refinement worth flagging

The comparison table rates Manual, Deep Learning, and Template Matching all
"High" on sensitivity, but the prose is explicit that template matching is
"optimally sensitive (more sensitive than deep-learning)" and that deep learning
is "not quite as sensitive as template-matching." A flat three-way tie would let
the recommender pick Manual over Template Matching for a pure maximum-sensitivity
goal, contradicting the guide. So the script keeps the **displayed** matrix label
faithful to the table ("High" for all three) but scores sensitivity on a finer
internal scale (`sensitivity_score`: Template Matching 3 > Manual/Deep Learning 2
> STA/LTA 0) that reflects the prose ordering. This is documented in code comments
and is the only place the script's scoring departs from the literal table cell.

## Over-restriction guard

Method selection is a genuine judgment call with unmodeled factors (compute
budget, analyst time, downstream spatial vs temporal resolution needs). The
script therefore **ranks and explains** rather than dictating: it returns all four
methods ordered viable-first then by score, with rationale and watch-outs, and the
`decide` step instructs the agent to reason over the full ranking and its own
constraints before committing. The hard gates only remove options the guide says
are *infeasible* (no templates → no template matching; no continuous data → no
deep learning), which is fact, not preference.

## Content mapping (completeness check)

Every distinct piece of the original SKILL.md was classified:

- **Overview tradeoff table** (Method × Generalizability/Sensitivity/Speed-Ease/
  False-Positives, all four rows) → `search_shortcuts[Comparison matrix]` + the
  `METHODS` table in the script (mapped, script-backed as the source of truth).
- **Definitions** of generalizability ("find arbitrary earthquake signals") and
  sensitivity ("find small earthquakes") → `search_shortcuts[Comparison matrix]`
  + `DEFINITIONS` in the script (mapped).
- **"Key insight: purpose and resources should guide your choice."** → `purpose`,
  the `review-tradeoffs` step, and an `anti_pattern` (mapped).
- **STA/LTA advantages & limitations** (fast/real-time, easy/tunable, no prior
  knowledge, amplitude-based for large signals; false detections, imprecise picks,
  needs manual review) → `search_shortcuts[STA/LTA]` + script profile +
  `anti_patterns` + the real-time scenario (mapped).
- **Template Matching advantages & limitations** (optimally sensitive / smallest
  events if similar to template; improves temporal resolution; high-threshold ⇒
  false detections less concerning; requires preexisting-catalog templates; no
  spatial-resolution gain for dissimilar sources; setup effort; computationally
  intensive) → `search_shortcuts[Template Matching]` + script profile + viability
  gate + `anti_patterns` + the sequence scenario (mapped).
- **Deep Learning — When to Use** (sparse/nonexistent networks; automatic catalog
  during active sequences; requires continuous data; broadband best but
  accelerometers/nodals/Raspberry Shakes usable; temporary-deployment use case) →
  `search_shortcuts[Deep Learning pickers]` + `sparse_network`/`continuous_data`
  constraints + the automatic-catalog scenario (mapped).
- **Deep Learning advantages & limitations** (no prior knowledge; lower Mc with
  fewer false detections than STA/LTA; easy setup, SeisBench APIs/pretrained
  models; out-of-distribution errors 0.1-0.5 s and missed picks; can't pick fully
  buried phases / less sensitive than template matching; sometimes misses obvious
  large-event picks) → `search_shortcuts[Deep Learning pickers]` + script profile
  + `anti_patterns` (mapped).
- **Manual method** (present only as a table row: High generalizability, High
  sensitivity, Slow/Difficult, Few false positives) → `search_shortcuts[Manual
  picking]` + script profile + the highest-precision scenario (mapped; the row's
  implications — gold-standard precision, does not scale — made explicit).
- **References** (Beauce et al. 2025 workshop; Allen 1978; Perol et al. 2018;
  Huang & Beroza 2015; Yoon & Shelly 2024) → `search_shortcuts[References]`
  (mapped).

### Deliberate drops

None. All source content is represented in the body and/or the script.

## Licensing

The original SKILL.md declared no `license:` field, so none is asserted here. It
cites academic references (preserved in `search_shortcuts[References]`) but ships
no license text. (The task bundles SeisBench/ObsPy licenses separately under
`environment/skills/licenses/`; those cover the sibling skills' dependencies, not
this selection guide.)
