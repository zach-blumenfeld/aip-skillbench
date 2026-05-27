---
name: seismic-picker-selection
description: This is a summary the advantages and disadvantages of earthquake event detection and phase picking methods, shared by leading seismology researchers at the 2025 Earthquake Catalog Workshop. Use it when you have a seismic phase picking task at hand.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Guide selection among four earthquake event detection and phase picking
  methods — STA/LTA, Template Matching, Deep Learning, and Manual — based on
  their tradeoffs across generalizability (ability to find arbitrary
  earthquake signals), sensitivity (ability to find small earthquakes), speed
  and ease-of-use, and false-positive rate. Synthesizes guidance shared by
  leading seismology researchers at the 2025 SSA Earthquake Catalog Workshop
  (https://ai4eps.github.io/Earthquake_Catalog_Workshop/). Each method has
  strengths and weaknesses; purpose and resources should guide the choice.
  Key citations: Allen (1978) on STA/LTA; Perol et al. (2018) on deep
  learning for seismic detection; Huang & Beroza (2015) on template
  matching; Yoon and Shelly (2024), TSR on deep learning vs template
  matching comparison; and Beauce, Tepp, Yoon, Yu, and Zhu, "Building a High
  Resolution Earthquake Catalog from Raw Waveforms: A Step-by-Step Guide"
  (SSA Annual Meeting, 2025).

trigger_when:
  - Starting a seismic phase picking task and need to choose a method.
  - Building or expanding an earthquake catalog from raw waveforms.
  - Evaluating tradeoffs between automated and manual phase pickers for a specific deployment context.
  - Deciding between amplitude-based detection (STA/LTA), template matching, and deep-learning pickers.
  - Planning processing for a temporary broadband or nodal deployment that needs an automatically generated local earthquake catalog.

steps:
  - name: assess-context
    description: >
      Inventory data and constraints — continuous seismic data availability,
      station types (broadband, accelerometer, nodal, Raspberry Shake),
      network density, presence/absence of a preexisting catalog with usable
      template waveforms, compute budget, and whether processing must run in
      real-time or can be offline.
  - name: clarify-objective
    description: >
      Define the catalog requirements — desired completeness and magnitude
      of completeness (Mc), spatial vs temporal resolution priorities,
      whether the target is active sequences, sparse networks, or refining
      an existing catalog, and the acceptable tolerance for false detections
      and manual review effort.
  - name: review-tradeoffs
    description: >
      Compare candidate methods on four axes — generalizability,
      sensitivity, speed/ease-of-use, and false-positive rate — using the
      per-method details captured in `modes`. Summary table — STA/LTA
      (Generalizability High, Sensitivity Low, Speed Fast/Easy, False
      Positives Many); Manual (High, High, Slow/Difficult, Few); Deep
      Learning (High, High, Fast/Easy, Medium); Template Matching (Low,
      High, Slow/Difficult, Few).
  - name: select-method
    description: >
      Choose exactly one method based on context, objective, and tradeoffs,
      cross-checked against `decisions` and the per-method advantages and
      limitations in `modes`.
    one_of:
      - STA/LTA
      - Template Matching
      - Deep Learning
      - Manual

decisions:
  - signal: Need fast, real-time detection of large earthquakes with minimal setup and no prior catalog.
    action: Use STA/LTA — amplitude-based, fast, easy; accept many false detections and plan manual review.
  - signal: Preexisting catalog provides good template waveforms; goal is to find the smallest earthquakes similar to known sources or improve temporal resolution of a sequence.
    action: Use Template Matching — optimally sensitive, few false positives at high threshold; budget for setup and compute.
  - signal: Temporary broadband or nodal deployment in a sparse or nonexistent network needing an automatically generated, comprehensive local catalog from continuous data.
    action: Use Deep Learning pickers (e.g., via SeisBench) — low Mc, fewer false detections than STA/LTA, easy setup, reasonable runtime with parallel processing.
  - signal: Highest-quality, ground-truth picks are required regardless of effort, or a final QC pass is needed over automated picks.
    action: Use Manual picking — highest sensitivity and generalizability; slow and labor-intensive.
  - signal: Active earthquake sequence with high event rate where automated catalog completeness matters.
    action: Prefer Deep Learning over STA/LTA — STA/LTA produces a high rate of false detections during active sequences.
  - signal: Dataset is out-of-distribution for the deep-learning picker (unusual instrument, region, or noise environment).
    action: Expect larger automated pick errors (0.1–0.5 s) and missed picks; supplement with manual review, or use template matching where appropriate templates exist.
  - signal: Spatial resolution matters and unknown earthquake sources dissimilar to any template are expected.
    action: Do not rely on Template Matching alone — it does not improve spatial resolution; pair with Deep Learning or STA/LTA to find dissimilar sources.
  - signal: STA/LTA picks are being used as the basis for a quality catalog.
    action: Plan manual review and refinement of picks — automatic STA/LTA picks are not precise enough on their own.

modes:
  - name: STA/LTA
    body: |
      Short-Term Average / Long-Term Average detector.

      Advantages:
        - Runs very fast; automatically operates in real-time.
        - Easy to understand and implement; can optimize for different window
          lengths and ratios.
        - No prior knowledge needed; does not require information about
          earthquake sources or waveforms.
        - Amplitude-based detector; reliably detects large earthquake signals.

      Limitations:
        - High rate of false detections during active sequences.
        - Automatic picks not as precise.
        - Requires manual review and refinement of picks for a quality catalog.

      Tradeoff profile — Generalizability: High. Sensitivity: Low.
      Speed/Ease-of-Use: Fast, Easy. False Positives: Many.
  - name: Template Matching
    body: |
      Cross-correlation of continuous data against template waveforms drawn
      from a preexisting catalog.

      Advantages:
        - Optimally sensitive detector — more sensitive than deep learning.
          Can find the smallest earthquakes buried in noise, if similar
          enough to the template waveform.
        - Excellent for improving temporal resolution of earthquake sequences.
        - False detections are not as concerning when using a high detection
          threshold.

      Limitations:
        - Requires prior knowledge about earthquake sources — need template
          waveforms with good picks from a preexisting catalog.
        - Does not improve spatial resolution; unknown earthquake sources
          that are not similar enough to templates cannot be found.
        - Setup effort required — must extract template waveforms and
          configure processing.
        - Computationally intensive.

      Tradeoff profile — Generalizability: Low. Sensitivity: High.
      Speed/Ease-of-Use: Slow, Difficult. False Positives: Few.
  - name: Deep Learning
    body: |
      Pretrained neural-network phase pickers (e.g., available via SeisBench).

      When to use:
        - Adds most value when existing seismic networks are sparse or
          nonexistent.
        - Automatically and rapidly creates a more complete catalog during
          active sequences.
        - Requires continuous seismic data.
        - Best on broadband stations, but also produces usable picks on
          accelerometers, nodals, and Raspberry Shakes.
        - Typical use case — temporary deployment of broadband or nodal
          stations where you want an automatically generated local
          earthquake catalog.

      Advantages:
        - No prior knowledge needed about earthquake sources or waveforms.
        - Finds many small local earthquakes (lower magnitude of
          completeness, Mc) with fewer false detections than STA/LTA.
        - Relatively easy to set up and run; reasonable runtime with
          parallel processing. SeisBench provides easy-to-use model APIs
          and pretrained models.

      Limitations:
        - Out-of-distribution data issues — for datasets not represented in
          training data, expect larger automated pick errors (0.1–0.5 s)
          and missed picks.
        - Cannot pick phases completely buried in noise — not quite as
          sensitive as template matching.
        - Sometimes misses picks from larger earthquakes that are obvious
          to humans, for unexplained reasons.

      Tradeoff profile — Generalizability: High. Sensitivity: High.
      Speed/Ease-of-Use: Fast, Easy. False Positives: Medium.
  - name: Manual
    body: |
      Human analyst review and picking of seismic waveforms. Use as ground
      truth, for small datasets, or as a final QC pass over automated picks.

      Tradeoff profile — Generalizability: High. Sensitivity: High.
      Speed/Ease-of-Use: Slow, Difficult. False Positives: Few.

anti_patterns:
  - Choosing a method without first inventorying available data, station types, network density, and any preexisting catalog.
  - Defaulting to STA/LTA during active sequences, where the false-detection rate makes the catalog hard to use without heavy manual cleanup.
  - Using template matching without a preexisting catalog or representative template waveforms.
  - Assuming a deep-learning picker trained on broadband data will perform as well on accelerometers, nodals, Raspberry Shakes, or unusual noise environments without checking pick error against a held-out sample.
  - Relying on Template Matching alone when spatial resolution matters — it cannot find earthquakes whose waveforms are not similar to a template.
  - Treating automated STA/LTA picks as a finished catalog without manual review and refinement.
```
