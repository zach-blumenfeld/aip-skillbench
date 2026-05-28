# Source materials for `pcap-analysis` AIP skill

This folder bundles everything used to author the AIP-format `SKILL.md` at the
skill root.

## Origin

The original Agent Skill lives at:

    vendor/skillsbench/tasks/dapt-intrusion-detection/environment/skills/pcap-analysis/

It is part of the `dapt-intrusion-detection` task in the SkillsBench corpus.
The original `SKILL.md` is preserved here as `ORIGINAL_SKILL.md` for traceability.

## Schema choice

`procedure.schema.json` (AIP v0.2 procedure schema) was selected because the
source skill is fundamentally a procedure: a multi-step PCAP-analysis workflow
with detection branches, decision thresholds, and concrete anti-patterns. The
shape (steps + decisions + anti_patterns + scenarios) matches one-to-one.

## Authoring notes

- The skill `name` is held fixed at `pcap-analysis` because the host task mounts
  the skill folder by that name. Renaming would break activation.
- The tested helper module `pcap_utils.py` is preserved verbatim at the skill
  root. The skill body steers the agent toward those functions rather than
  re-deriving thresholds.
- Detection thresholds (port-scan entropy > 6.0, SYN-only > 0.7, unique ports >
  100; DoS max/avg > 20; beaconing CV < 0.5) are encoded in the `decisions`
  block so they remain queryable across the corpus, not just inline in prose.

## Completeness check

Every distinct section of the source `SKILL.md` is captured as one of:
- a step (load, split, basic-stats, entropy, graph, temporal, flow, timeseries,
  detection, csv-output)
- a decision row (the three detection thresholds + benign assessment)
- an anti-pattern (degree-as-packet-count, weak port-scan heuristics, missing
  IP-layer guards, treating 5–15× spikes as DoS, reimplementing thresholds)
- a scenario (dominant-protocol pick, port-scan triage, beaconing call)

Deliberate drops: none. The "Common Issues" prose (memory, non-IP, UDP-without-
IP) is preserved as anti-patterns rather than a separate section.
