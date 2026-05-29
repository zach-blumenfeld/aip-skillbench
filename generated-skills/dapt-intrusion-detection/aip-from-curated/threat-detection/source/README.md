# threat-detection — AIP conversion notes

## Source

Curated skill: `vendor/skillsbench/tasks/dapt-intrusion-detection/environment/skills/threat-detection/SKILL.md`

The original skill consists of a single SKILL.md that documents three
calibrated thresholds for malicious-pattern detection in PCAP captures
(port scan, DoS, beaconing) plus a benign-assessment rule. It carries
illustrative Python snippets and points readers at mirror functions in
the sibling `pcap-analysis` skill (`/root/skills/pcap-analysis/pcap_utils.py`).

## Schema choice

`procedure.schema.json` (bundled in this folder).

The skill is a four-step execution graph: three detector checks feeding a
benign-assessment combiner. Each node is deterministic threshold logic
over structured inputs — a textbook fit for `procedure` (scriptable nodes
connected by typed inputs/outputs).

No new schema was drafted.

## Script vs prose

All four steps are script-backed (`scripts/threat_detection.py`):

| Step               | Why scripted                                                                 |
|--------------------|------------------------------------------------------------------------------|
| port-scan-check    | Fixed thresholds (entropy>6.0, SYN-only>0.7, ports>100, min-packets>=50).    |
| dos-check          | Fixed ratio threshold (max/avg > 20).                                        |
| beaconing-check    | Fixed CV threshold (< 0.5).                                                  |
| benign-assessment  | Boolean OR / NOT — purely mechanical.                                        |

There is no judgement step; every node is deterministic. Prose steps would
invite re-derivation of thresholds, which the source explicitly warns against
("different values will produce incorrect results"). One script file holds
all four — they share constants and are tightly related.

## Mapping audit

| Source content                                           | Disposition                                              |
|----------------------------------------------------------|----------------------------------------------------------|
| Port-scan three-condition rule + thresholds              | Mapped → `detect_port_scan` in scripts; described in step |
| Port-scan "simple count fails" example (1000 ports, CV)  | Mapped → `scenarios[0]`                                  |
| Embedded port-scan Python implementation                 | Mapped → `scripts/threat_detection.py`                   |
| DoS ratio rule + threshold (>20)                         | Mapped → `detect_dos_pattern` in scripts; step body      |
| DoS example (2372/262.9 = 9.02 → no DoS)                 | Mapped → `scenarios[1]`                                  |
| Embedded DoS Python implementation                       | Mapped → `scripts/threat_detection.py`                   |
| Beaconing rule (IAT CV < 0.5)                            | Mapped → `detect_beaconing` in scripts; step body        |
| Embedded beaconing Python implementation                 | Mapped → `scripts/threat_detection.py`                   |
| Benign assessment rule (NOT (scan OR dos OR beacon))     | Mapped → `assess_benign` in scripts; benign-assessment step |
| Reference to sibling `pcap-analysis` `pcap_utils.py`     | Mapped → `integrations[]`                                |
| Summary table                                            | Implicit in step descriptions + anti_patterns            |
| "ALL THREE must be met" emphasis                         | Mapped → step description + anti_patterns                |

No deliberate drops. The "if ANY condition is not met, NO port scan" framing
becomes both step prose and an anti-pattern entry.
