---
name: seismic-picker-selection
description: Choose an earthquake event-detection / phase-picking method — STA/LTA, manual picking, deep-learning pickers, or template matching — by weighing generalizability, sensitivity, speed/ease-of-use, and false-positive rate against your data, resources, and goal. Consolidates tradeoff guidance shared by leading seismology researchers at the 2025 Earthquake Catalog Workshop. Use it whenever you have a seismic phase-picking or event-detection task and must pick the detection paradigm before building a catalog.
compatibility: Method-selection guidance for seismic catalog building. The bundled recommender (`scripts/recommend_picker.py`) is pure-Python standard library — no external packages. Applying the chosen method needs its own stack (e.g. SeisBench + ObsPy + PyTorch for deep-learning picking).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Decide which earthquake event-detection / phase-picking method to use before
  building a catalog. Four methods are on the table — STA/LTA, manual picking,
  deep-learning pickers, and template matching — and each trades off
  generalizability (finding arbitrary earthquake signals), sensitivity (finding
  small earthquakes), speed/ease-of-use, and false-positive rate. This skill adds
  the consolidated tradeoff knowledge that leading seismology researchers shared
  at the 2025 Earthquake Catalog Workshop, plus a recommender that encodes the
  comparison matrix and the guide's hard viability rules (template matching needs
  a preexisting catalog of template waveforms; deep learning needs continuous
  data) and returns a ranked, explained recommendation. Purpose and resources —
  not defaults — should drive the choice.

trigger_when:
  - You have a seismic phase-picking or event-detection task and must choose a method.
  - Deciding among STA/LTA, manual picking, deep-learning pickers, and template matching.
  - Building an earthquake catalog from raw or continuous waveforms and choosing the detection paradigm.
  - Weighing sensitivity vs false positives vs speed vs setup effort for detection/picking.
  - Unsure whether your data and resources support template matching or deep learning at all.

do_not_use_when:
  - You have already chosen deep learning and need to apply a model (which model, which weights, annotate vs classify) — use the `seisbench-model-api` skill.
  - You need to read, parse, or manipulate the waveform / station files (MSEED/SAC I/O, Stream/Trace handling, response removal) — use the `obspy-data-api` skill.
  - You already have phase picks and need to associate them into earthquake events — use the `gamma-phase-associator` skill.
  - You are tuning the parameters of an already-chosen method rather than selecting one.

scope_and_approval: >
  Read-only and advisory. This skill produces a method recommendation and
  rationale; it does not run detection, modify data, or write outputs.
  `scripts/recommend_picker.py` only reads its CLI/JSON inputs and prints to
  stdout. The ranking is decision support, not a mandate — reason over the full
  ranking (and its watch-outs) before committing, and confirm the choice with the
  user if the task is ambiguous about goals or available data.

steps:
  - name: gather-requirements
    description: >
      Establish the constraints that drive the choice. Do you have a preexisting
      catalog with good picks to extract template waveforms from? Is continuous
      seismic data available? Is the existing network sparse or nonexistent? Do
      you need real-time operation, maximum sensitivity to tiny events, low false
      positives, or minimal setup/operator effort? What is the primary goal —
      an automatic local catalog, real-time monitoring, maximum sensitivity, or
      highest-precision picks? Capture these as a structured object.
    outputs:
      - name: requirements
        type: object
        description: >
          Constraints + goal, e.g. {goal, have_templates, continuous_data,
          sparse_network, find_novel_sources, active_sequence}.

  - name: review-tradeoffs
    description: >
      Review the comparison matrix and per-method advantages/limitations before
      deciding — see search_shortcuts (Comparison matrix; STA/LTA; Template
      Matching; Deep Learning pickers; Manual picking). For the full table and
      profiles printed in one place, run `recommend_picker.py show`. Key insight:
      each method has real strengths and weaknesses; match the method to purpose
      and resources rather than reaching for a default.
    depends_on: [gather-requirements]

  - name: recommend-method
    description: >
      Turn the requirements into a ranked, explained recommendation. The script
      gates out non-viable methods using the guide's hard rules (template matching
      requires template waveforms from a preexisting catalog; deep learning
      requires continuous data) and scores the rest against the goal's weighting
      of the four matrix dimensions. Output is decision support, not a verdict.
    depends_on: [review-tradeoffs]
    script: scripts/recommend_picker.py
    inputs:
      - name: requirements
        type: object
    outputs:
      - name: ranked_recommendation
        type: object
        description: >
          {recommended, ranking:[{method, score, viable, rationale, watch_outs}]}
          — methods ordered viable-first then by score.

  - name: decide
    description: >
      Pick the method. Reason over the full ranking — the top-ranked viable method
      is the default suggestion, but weigh its watch-outs and your unmodeled
      constraints (compute budget, analyst time, downstream resolution needs)
      before committing. Record the choice, the rationale, and the key limitations
      to watch (e.g. deep-learning out-of-distribution pick errors; STA/LTA false
      detections during active sequences requiring manual review).
    depends_on: [recommend-method]
    inputs:
      - name: ranked_recommendation
        type: object
    outputs:
      - name: chosen_method
        type: string
      - name: rationale
        type: string
    one_of:
      - "STA/LTA"
      - "Manual"
      - "Deep Learning"
      - "Template Matching"

search_shortcuts:
  - category: Comparison matrix
    body: >
      Tradeoffs across the four methods (the structured source of truth lives in
      `scripts/recommend_picker.py`; `recommend_picker.py show` prints it).
      STA/LTA — generalizability High, sensitivity Low, speed/ease Fast & Easy,
      false positives Many. Manual — generalizability High, sensitivity High,
      speed/ease Slow & Difficult, false positives Few. Deep Learning —
      generalizability High, sensitivity High, speed/ease Fast & Easy, false
      positives Medium. Template Matching — generalizability Low, sensitivity High
      (optimally sensitive — more than deep learning), speed/ease Slow & Difficult,
      false positives Few. Definitions: generalizability = ability to find
      arbitrary earthquake signals; sensitivity = ability to find small
      earthquakes.
  - category: STA/LTA (Short-Term Average / Long-Term Average)
    body: >
      Advantages: runs very fast and operates automatically in real-time; easy to
      understand and implement (tune window lengths and the ratio); no prior
      knowledge of sources or waveforms needed; amplitude-based detector that
      reliably detects large earthquake signals. Limitations: high rate of false
      detections during active sequences; automatic picks are not as precise;
      requires manual review and refinement of picks for a quality catalog.
  - category: Template Matching
    body: >
      Advantages: optimally sensitive detector (more sensitive than deep learning)
      — can find the smallest earthquakes buried in noise, if similar enough to a
      template waveform; excellent for improving the temporal resolution of
      earthquake sequences; false detections are not as concerning when using a
      high detection threshold. Limitations: requires prior knowledge — template
      waveforms with good picks from a preexisting catalog; does not improve
      spatial resolution (sources not similar enough to templates cannot be found);
      setup effort to extract templates and configure processing; computationally
      intensive.
  - category: Deep Learning pickers
    body: >
      When to use: adds the most value when existing networks are sparse or
      nonexistent; to automatically and rapidly build a more complete catalog
      during active sequences; requires continuous seismic data; best on broadband
      stations but also produces usable picks on accelerometers, nodals, and
      Raspberry Shakes. Canonical use case: temporary deployment of broadband or
      nodal stations where you want an automatically generated local earthquake
      catalog. Advantages: no prior knowledge of sources/waveforms needed; finds
      many small local earthquakes (lower magnitude of completeness, Mc) with fewer
      false detections than STA/LTA; relatively easy to set up and run with
      reasonable runtime under parallel processing — SeisBench provides easy-to-use
      model APIs and pretrained models. Limitations: out-of-distribution data →
      larger automated pick errors (0.1-0.5 s) and missed picks; cannot pick phases
      completely buried in noise (not quite as sensitive as template matching);
      sometimes misses picks from larger earthquakes that are obvious to humans.
  - category: Manual picking
    body: >
      The analyst-driven baseline (from the comparison matrix): high
      generalizability and high sensitivity with few false positives — the
      highest-quality, most precise picks — but slow and difficult, so it does not
      scale to large continuous datasets. Use when picks must be as precise as
      possible and analyst time is available, or to review/refine automatic picks.
  - category: Recommender script
    body: >
      `python scripts/recommend_picker.py show` prints the comparison matrix and
      full per-method profiles. `python scripts/recommend_picker.py recommend
      --goal <automatic-catalog|real-time-monitoring|max-sensitivity|highest-precision|balanced>`
      ranks the methods; add `--no-templates`/`--have-templates`,
      `--continuous-data`/`--no-continuous-data`, `--sparse-network`,
      `--find-novel-sources`, `--active-sequence`, per-dimension `--weight-*`
      overrides, or pass a constraints object via `--requirements-json '{...}'`;
      `--json` emits machine-readable output. `python scripts/recommend_picker.py
      --self-test` runs offline deterministic checks (stdlib only).
  - category: References
    body: >
      Derivative of Beauce, Tepp, Yoon, Yu, Zhu, "Building a High Resolution
      Earthquake Catalog from Raw Waveforms: A Step-by-Step Guide," SSA Annual
      Meeting 2025 (https://ai4eps.github.io/Earthquake_Catalog_Workshop/). Also:
      Allen (1978) — STA/LTA; Perol et al. (2018) — deep learning for seismic
      detection; Huang & Beroza (2015) — template matching; Yoon and Shelly (2024),
      TSR — deep learning vs template matching comparison.

anti_patterns:
  - Reaching for template matching without a preexisting catalog of good picks to build template waveforms from — it requires that prior knowledge.
  - Expecting template matching to find earthquakes dissimilar to your templates — it does not improve spatial resolution; unknown sources are missed.
  - Trusting STA/LTA automatic picks during active sequences without manual review — expect many false detections and imprecise picks.
  - Treating deep-learning picks as infallible — out-of-distribution data gives larger errors (0.1-0.5 s) and missed picks, it cannot recover phases fully buried in noise, and it occasionally misses picks obvious to a human.
  - Forgetting deep learning needs continuous seismic data.
  - Choosing a fast, easy method when the goal demands maximum sensitivity (or an expensive sensitive method when speed/coverage is what matters) — match the method to purpose and resources.

scenarios:
  - need: Temporary broadband/nodal deployment; want an automatically generated local catalog from continuous data, with no preexisting catalog to seed templates.
    context: gather-requirements → goal=automatic-catalog, have_templates=false, continuous_data=true; recommend-method gates out template matching (no templates) and ranks Deep Learning top.
    action: Choose Deep Learning (e.g. a SeisBench pretrained picker); plan manual spot-checks for out-of-distribution stations.
    outcome: Lower Mc with fewer false detections than STA/LTA and reasonable runtime — a more complete automatic catalog.
  - need: Tighten the temporal resolution of a known aftershock sequence; a catalog of well-picked events is already available.
    context: gather-requirements → goal=max-sensitivity, have_templates=true; recommend-method finds template matching viable and ranks it first (optimally sensitive).
    action: Choose Template Matching with a high detection threshold; extract template waveforms from the existing catalog.
    outcome: Detects the smallest events buried in noise that match templates, improving temporal resolution of the sequence.
  - need: Real-time monitoring for large events with minimal setup and no prior source knowledge.
    context: gather-requirements → goal=real-time-monitoring; recommend-method favors fast methods (STA/LTA, Deep Learning).
    action: Choose STA/LTA for the real-time amplitude trigger, accepting that picks need later manual review and refinement.
    outcome: Fast, automatic real-time detection of large signals; quality catalog requires downstream review.
  - need: Build a small but maximally precise reference catalog and analyst time is available.
    context: gather-requirements → goal=highest-precision; recommend-method ranks Manual top (few false positives, high sensitivity) despite being slow.
    action: Choose Manual picking (or use it to review automatic picks) where precision matters more than scale.
    outcome: The highest-quality picks, at the cost of throughput — not suitable for large continuous datasets.
```
