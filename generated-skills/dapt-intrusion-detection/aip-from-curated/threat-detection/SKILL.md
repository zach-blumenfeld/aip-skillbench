---
name: threat-detection
description: "Exact, calibrated detection thresholds for identifying malicious network patterns in PCAP captures — port scans, DoS spikes, C2 beaconing — plus the rule for deciding when traffic is benign. Use when computing has_port_scan, has_dos_pattern, has_beaconing, or is_traffic_benign for PCAP / network-stats tasks. Different threshold values will produce incorrect results."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Provide the exact, calibrated thresholds for three malicious-pattern
  detectors over PCAP data — port scans, DoS spikes, and C2 beaconing —
  and the rule for combining them into a benign verdict. Thresholds are
  calibrated against DAPT2020-style traffic; using different numbers will
  produce wrong answers on calibrated datasets.

trigger_when:
  - Computing has_port_scan, has_dos_pattern, has_beaconing, or is_traffic_benign for a PCAP / network-stats task.
  - Deciding whether observed traffic is malicious vs normal variation.
  - Implementing port-scan, DoS, or beaconing detection from packet captures.

do_not_use_when:
  - The task asks only for descriptive PCAP stats (counts, sizes, entropy, flows) and never requests a malicious-pattern verdict.

steps:
  - name: port-scan-check
    description: >
      Port scan iff some source IP with >= 50 TCP packets simultaneously has
      port-entropy > 6.0 bits AND SYN-only-ratio > 0.7 AND unique destination
      ports > 100. A high port count alone is NOT a scan — all three
      conditions must hold for the same source. Backed by detect_port_scan
      in scripts/threat_detection.py.
    script: scripts/threat_detection.py
    inputs:
      - name: tcp-packets
        type: list[object]
        description: TCP packets, e.g. split_by_protocol(packets)['tcp'] from the pcap-analysis skill.
    outputs:
      - name: has-port-scan
        type: boolean
  - name: dos-check
    description: >
      DoS iff packets_per_minute_max / packets_per_minute_avg > 20.
      Ratios of 5x, 10x, even 15x are normal bursty traffic, not DoS.
      Returns False when ppm_avg is 0. Backed by detect_dos_pattern in
      scripts/threat_detection.py.
    script: scripts/threat_detection.py
    inputs:
      - name: ppm-avg
        type: float
        description: Average packets per 60-second bucket.
      - name: ppm-max
        type: float
        description: Max packets observed in any 60-second bucket.
    outputs:
      - name: has-dos
        type: boolean
  - name: beaconing-check
    description: >
      Beaconing iff inter-arrival-time coefficient of variation (std/mean)
      < 0.5. Low CV means robotic / periodic timing; CV >= 1.0 is human
      bursty traffic and is NOT beaconing. Backed by detect_beaconing in
      scripts/threat_detection.py.
    script: scripts/threat_detection.py
    inputs:
      - name: iat-cv
        type: float
        description: Inter-arrival-time coefficient of variation across all packets sorted by timestamp.
    outputs:
      - name: has-beaconing
        type: boolean
  - name: benign-assessment
    description: >
      Traffic is benign iff none of the three threat detectors fires —
      not (has-port-scan or has-dos or has-beaconing). Any single
      detection means not benign. Backed by assess_benign in
      scripts/threat_detection.py.
    script: scripts/threat_detection.py
    depends_on: [port-scan-check, dos-check, beaconing-check]
    inputs:
      - name: has-port-scan
        type: boolean
      - name: has-dos
        type: boolean
      - name: has-beaconing
        type: boolean
    outputs:
      - name: is-traffic-benign
        type: boolean

integrations:
  - partner: pcap-analysis
    body: >
      The sibling pcap-analysis skill (mounted at /root/skills/pcap-analysis
      in this task) ships pcap_utils.py with load_packets, split_by_protocol,
      packets_per_minute_stats, iat_stats, plus mirror detectors
      detect_port_scan, detect_dos_pattern, detect_beaconing using identical
      thresholds. Prefer that module for loading and feature extraction;
      either its detectors or this skill's scripts/threat_detection.py can
      issue the verdict — they return the same answer on the same inputs.

scenarios:
  - need: 1000 unique destination ports observed from one source IP.
    context: Port entropy is 4.28 bits (below 6.0) and SYN-only ratio is 0.15 (below 0.7).
    action: Apply port-scan-check.
    outcome: Returns False — normal service traffic, not a scan. High port count alone is insufficient.
  - need: Decide if a traffic spike is a DoS attack.
    context: ppm_max = 2372 and ppm_avg = 262.9, so the ratio is 9.02.
    action: Apply dos-check.
    outcome: Returns False — 9.02 < 20 is normal bursty variation, not DoS.
  - need: Decide whether traffic is benign after running all three detectors.
    context: has-port-scan False, has-dos False, has-beaconing False.
    action: Apply benign-assessment.
    outcome: Returns True — is_traffic_benign = True.

anti_patterns:
  - Calling port-scan on unique-port-count alone. High port count without high entropy AND high SYN-only ratio is normal service traffic.
  - Using a max/avg ratio below 20 as a DoS signal. 5x–15x is normal bursty variation, not DoS.
  - Treating high IAT CV as beaconing. Beaconing requires LOW CV (< 0.5); CV >= 1.0 is human bursty traffic.
  - Reporting traffic as benign when any of the three detectors fires.
  - Re-deriving thresholds with different numbers. The constants (6.0, 0.7, 100, 50, 20, 0.5) are calibrated; substituting other values produces wrong answers on calibrated datasets.
  - Splitting port-scan detection across sources. Aggregating ports across all source IPs hides the per-source signal; check each source independently and require all three conditions for the same source.
```
