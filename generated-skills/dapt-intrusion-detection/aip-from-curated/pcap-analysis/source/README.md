# pcap-analysis — AIP Author Notes

## Source

Converted from the curated Agent Skill at
`vendor/skillsbench/tasks/dapt-intrusion-detection/environment/skills/pcap-analysis/SKILL.md`
(see `SKILL.original.md`) and the tested helper module `pcap_utils.py`.

The skill is consumed by the `dapt-intrusion-detection` SkillsBench task,
where the agent loads `/root/packets.pcap` (a subset of DAPT2020 traffic),
computes ~30 metrics, and fills in the `value` column of
`/root/network_stats.csv`. The CSV template is preserved verbatim; only
empty `value` cells are populated.

## Schema choice

Picked `procedure.schema.json` (bundled at
`source/procedure.schema.json`). The source skill is a structured walk
through "load packets → compute these metrics → run these detectors →
write the CSV" — a procedural DAG with deterministic numeric steps and
strict detector gates. No new schema needed; reuse over invention per
AIP best practices.

## Script vs prose decisions

**Scripted (deterministic, mechanical):**

- All entropy, graph, IAT, flow, and PCR computations live in
  `scripts/pcap_utils.py` (copied verbatim from the source). Every helper
  is a pure reduction over the packet list — exactly the kind of
  "numeric calculation / lookup / fixed formula" the AIP best-practice
  guide says to script.
- The three detectors (`detect_port_scan`, `detect_dos_pattern`,
  `detect_beaconing`) are scripted because their failure mode is agents
  inventing softer thresholds. The script enforces entropy > 6.0,
  SYN-only > 0.7, ports > 100, ppm ratio > 20, IAT CV < 0.5 with no wiggle
  room.
- `scripts/compute_all_stats.py` is a new orchestrator that calls every
  helper and emits a dict keyed by the exact CSV `metric` strings.
  Reason: the source skill leaves the orchestration to the agent, which is
  where metrics get dropped or recomputed with wrong formulas. The
  orchestrator collapses 30+ separate computations into one call. It also
  ships a `fill_csv_template` helper so the CSV write step is a single
  function call instead of a hand-written loop the agent might botch.

**Prose (judgment, orchestration, or trivial wrapping):**

- The step labels (`load-packets`, `compute-protocol-counts`, ...) are
  prose nodes that describe *which* helper to call. The helpers
  themselves are scripted; only the call-site is described.
- `verify-detection-flags` is prose because it's a guardrail the agent
  should reason about (not an automated check) — the source SKILL.md
  states the rule "use the helpers, not hand-rolled detection" and we
  preserve that as a checklist step.
- `write-csv` is partly scripted (`fill_csv_template`) and partly prose
  (the agent confirms the comment lines and key names match).

## Mapping the source content

| Source section                                    | Destination                                                    |
|---------------------------------------------------|----------------------------------------------------------------|
| "Quick Start: Using the Helper Module"            | `purpose` + step `load-packets` + anti_patterns                |
| "Overview" (5-bullet list)                        | `purpose`                                                      |
| "Reading PCAP Files with Scapy"                   | step `load-packets` (→ `pcap_utils.load_packets`)              |
| "Basic Statistics: Packet and Byte Counts"        | step `compute-size-stats` (→ `compute_all_stats`)              |
| "Protocol Distribution"                           | step `compute-protocol-counts` (→ `compute_all_stats`)         |
| "Entropy Calculation" + Shannon snippet           | step `compute-entropy-stats` (→ `pcap_utils.shannon_entropy`)  |
| "Graph/Topology Metrics" + unique-IP warning      | step `compute-graph-metrics` + anti_pattern + `pcap_utils.graph_metrics` |
| "Temporal Metrics: Inter-Arrival Time"            | step `compute-iat-stats` (→ `pcap_utils.iat_stats`)            |
| "Producer/Consumer Ratio (PCR)" + ±0.2 rule       | step `compute-producer-consumer` (→ `pcap_utils.producer_consumer_counts`) |
| "Flow Analysis" + bidirectional-flow rule         | step `compute-flow-metrics` (→ `pcap_utils.flow_metrics`)      |
| "Time Series Analysis" / packets-per-minute       | step `compute-time-series` (→ `pcap_utils.packets_per_minute_stats`) |
| "Writing Results to CSV" snippet                  | step `write-csv` (→ `compute_all_stats.fill_csv_template`)     |
| "Dominant Protocol" subsection                    | Deliberate drop — task CSV does not ask for `dominant_protocol`; protocol counts are emitted instead. Recorded below. |
| "Port Scan Detection (Robust Method)" + 3 rules   | step `detect-port-scan` + `references/detection-thresholds.md` + anti_pattern |
| "DoS Pattern Detection" + 20× threshold           | step `detect-dos-pattern` + `references/detection-thresholds.md` + anti_pattern |
| "C2 Beaconing Detection" + CV < 0.5               | step `detect-beaconing` + `references/detection-thresholds.md` + anti_pattern |
| "Benign Traffic Assessment"                       | step `assess-benign` (computed inside `compute_all_stats`)     |
| "Common Issues: Memory with Large PCAPs"          | Deliberate drop — DAPT2020 task PCAP fits comfortably in memory; streaming would complicate `pcap_utils` and confer no benefit. Noted below. |
| "Common Issues: Non-IP Packets / UDP Without IP"  | Encoded as guards inside `pcap_utils` (every helper checks `IP in pkt` before reading IP fields). Noted in step descriptions but not surfaced as a separate step. |

### Deliberate drops

- **"Dominant Protocol" subsection.** The source includes a small
  illustrative snippet for picking the most-common protocol. The DAPT2020
  CSV does not ask for it — `protocol_tcp/udp/icmp/arp/ip_total` are
  emitted directly. Including the helper would add noise without value.
- **"Memory with Large PCAPs" (PcapReader streaming).** The task's
  capture is small enough for `rdpcap` to load fully into memory. The
  source's streaming guidance is sound but irrelevant here; surfacing it
  would tempt the agent to refactor working code.

## Extensions beyond the source

- **`compute_all_stats.py` orchestrator.** New; not in the source. The
  source provides per-domain helpers and expects the agent to wire them
  together. We add a single entry point that emits the full CSV-keyed
  dict, removing the risk that the agent forgets `unique_dst_ports` or
  reuses a wrong variable. Calls into `pcap_utils.py`; introduces no new
  detection logic.
- **`fill_csv_template`.** New; not in the source. The source shows the
  CSV-write loop inline. We package it as a function that preserves
  comments and untouched rows, and that converts Python `True/False` to
  the lowercase `true/false` the test harness expects.
- **`references/detection-thresholds.md`.** Promoted from inline prose in
  the source SKILL.md to a dedicated reference, loaded on demand. Lets
  the body stay tight (~5K tokens) while preserving the per-threshold
  reasoning the source supplied.
