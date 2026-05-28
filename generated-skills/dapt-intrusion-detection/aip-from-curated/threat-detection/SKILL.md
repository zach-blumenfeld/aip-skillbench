---
name: threat-detection
description: "Exact detection thresholds for identifying malicious network patterns including port scans, DoS attacks, and beaconing behavior."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Classify network traffic patterns as port scan, DoS, C2 beaconing, or
  benign using exact numeric thresholds. Different threshold values
  produce incorrect results, so the procedure pins them precisely and
  encodes the composition rules (e.g., port scan requires ALL THREE
  conditions; benign requires all detectors false).

trigger_when:
  - Analyzing TCP packets or PCAP captures for malicious patterns.
  - Classifying network traffic as malicious vs benign.
  - User mentions port scans, DoS, C2 beaconing, or intrusion detection thresholds.
  - Implementing or reviewing detection logic that needs the exact thresholds.

do_not_use_when:
  - An upstream IDS/IPS already classifies the traffic and you only consume its verdict.
  - The input is non-network data (logs, files, host telemetry without packet metrics).

steps:
  - name: detect-port-scan
    description: >
      Port scan is detected for a source only when ALL THREE conditions
      are true: port entropy > 6.0 bits, SYN-only ratio > 0.7, and unique
      ports > 100. Compute per source over TCP packets, skipping sources
      with fewer than 50 total packets. SYN-only means the SYN flag is
      set without ACK. High unique-port counts alone are insufficient —
      normal service traffic can hit many ports with low entropy and a
      low SYN-only ratio. See references/implementations.md for the
      reference Python (preferred path: import detect_port_scan from
      /root/skills/pcap-analysis/pcap_utils).
  - name: detect-dos
    description: >
      DoS is detected when packets_per_minute_max / packets_per_minute_avg
      > 20. Guard against ppm_avg == 0 (return False). Ratios in the 5×
      to 20× range are normal traffic variation, not DoS. See
      references/implementations.md (preferred: import detect_dos_pattern
      from /root/skills/pcap-analysis/pcap_utils).
  - name: detect-beaconing
    description: >
      C2 beaconing is detected when the inter-arrival-time coefficient of
      variation (CV = std / mean) is < 0.5. Low CV reflects robotic,
      periodic timing; CV > 1.0 indicates bursty human traffic. See
      references/implementations.md (preferred: import detect_beaconing
      from /root/skills/pcap-analysis/pcap_utils).
  - name: assess-benign
    description: >
      Traffic is benign only when all three detectors return False.
      Compose as: is_benign = not (has_port_scan or has_dos or
      has_beaconing). If any detector returns True, the traffic is not
      benign — surface which detector(s) fired.
    depends_on: [detect-port-scan, detect-dos, detect-beaconing]

decisions:
  - signal: Source has > 100 unique ports but port entropy ≤ 6.0 or SYN-only ratio ≤ 0.7.
    action: Do not flag as port scan — at least one required condition fails.
  - signal: Source has fewer than 50 total TCP packets.
    action: Skip port-scan evaluation for that source (insufficient sample).
  - signal: packets_per_minute ratio max/avg is between 5 and 20.
    action: Treat as normal traffic variation, not DoS.
  - signal: ppm_avg == 0.
    action: Return False for DoS (guard against division by zero).
  - signal: IAT CV < 0.5.
    action: Flag as C2 beaconing.
  - signal: All three detectors return False.
    action: Classify the traffic as benign.
  - signal: Any detector returns True.
    action: Do not classify as benign; report which detector(s) fired.

scenarios:
  - need: TCP traffic with 1000 unique destination ports hitting one target.
    context: Measured port entropy 4.28 bits and SYN-only ratio 0.15 on the source.
    action: Run detect-port-scan — entropy 4.28 ≤ 6.0 and SYN ratio 0.15 ≤ 0.7 both fail the AND.
    outcome: Not a port scan; this is normal service traffic despite the high port count.
  - need: Bursty traffic with ppm_max = 2372 and ppm_avg = 262.9.
    context: Ratio = 2372 / 262.9 = 9.02.
    action: Run detect-dos — 9.02 is below the > 20 threshold.
    outcome: No DoS pattern; the burst is within normal variation.

anti_patterns:
  - Using unique port count alone to flag port scans — entropy and SYN-only ratio are required gates.
  - Treating max/avg packet-rate ratios of 5×–15× as DoS; the threshold is strictly > 20.
  - Skipping the 50-packet minimum and evaluating port scans on tiny sources.
  - Omitting the ppm_avg == 0 guard and producing division-by-zero errors.
  - Classifying traffic as benign while one of the three detectors returned True.
  - Re-implementing detectors with different threshold values; the thresholds are exact.
```
