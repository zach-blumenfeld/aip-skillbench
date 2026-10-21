# Source for pcap-network-stats

## Provenance

Compiled from two curated Agent Skills, copied here verbatim:

- `pcap-analysis/SKILL.md` and `pcap-analysis/pcap_utils.py`: how to compute PCAP statistics with scapy, plus the reference implementations ("tested, correct") of every metric and detector.
- `threat-detection/SKILL.md`: the exact port-scan / DoS / beaconing / benign thresholds.

The task it targets: fill the `value` column of `/root/network_stats.csv` from `/root/packets.pcap` (a DAPT2020 subset) inside an Ubuntu 24.04 container that has python3 (3.12), scapy 2.5.0, pandas 2.2.2, and numpy 1.26.4.

## Intent

One deterministic script does all the numeric work and the threshold rules, so the agent cannot drift on conventions that are easy to get wrong (degree as unique IPs, //2 bidirectional pairs, strict thresholds). The agent only steps in when the template asks for a metric the script does not know.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| `compute-stats` | execution (`scripts/pcap_stats.py`) | Every metric is a deterministic formula, and every flag is a fixed numeric threshold ("use these exact thresholds"). That is script territory. The script also writes the CSV, because preserving comment lines byte for byte is mechanical work. |
| `check-template` | router on `template_status` | Another instance of the task could add rows. `complete` goes to the end; `needs_manual` goes to the agent. |
| `fill-unknown` | client_task | An unknown metric has to be defined and coded by the agent. A decision step cannot produce that. |
| (no decision step) | | The sources forbid judgment on the flags ("different thresholds will produce incorrect results"), so a decision step would only add a way to override them. |

All the scripts are merged into one file (`scripts/pcap_stats.py`), which streams packets with `PcapReader` and does a single pass. `pcap_utils.py` uses `rdpcap` plus several list passes. On the real 32.7 MB / 114,099-packet capture the merged script takes about 10 s.

## Where each source item lives

- Protocol filters (`IP/TCP/UDP/ICMP/ARP in p`), byte counts, average/min/max size: script `analyze()`. The filters are also listed in `references/metric-definitions.md`.
- Shannon entropy (log2, 4 dp as in pcap_utils), port counters (every TCP packet, but UDP only when it carries IPv4, matching `port_counters`), IP counters: script.
- Graph: IPv4-only nodes and edges, density n(n-1), degree counted as UNIQUE IPs (the "38 nodes → ≤37" mistake): script, plus an anti_pattern.
- IAT: sorted timestamps, population variance, CV = std/mean, 0 if the mean is 0: script.
- PCR producer > 0.2 / consumer < -0.2 over all nodes: script.
- Flows: only packets with IPv4 and a transport layer; 5-tuple; bidirectional = reverse hits // 2: script, plus an anti_pattern.
- Packets per minute: buckets of int((ts - first)/60), non-empty buckets only, avg rounded to 2 dp: script.
- CSV writing that keeps comment lines: script `fill_csv()`. It rewrites line by line instead of with the source's DictWriter, which would turn `# Protocol Distribution` into `# Protocol Distribution,`.
- Dominant protocol: script (`dominant_protocol`, used only if a template asks for it).
- Port scan: all three conditions (entropy > 6.0, SYN-only > 0.7, unique ports > 100), sources with < 50 TCP packets ignored, SYN-only = SYN without ACK: script constants, `detection_evidence`, anti_pattern, and reference. The "1000 ports, entropy 4.28, SYN 0.15 ⇒ not a scan" example: reference and anti_pattern.
- DoS: max/avg > 20, 5x/10x/15x is normal, false if avg = 0. The 2372/262.9 = 9.02 example: script, anti_pattern, and reference.
- Beaconing: CV < 0.5; CV > 1.0 means bursty/human: script and reference.
- Benign: all three flags false: script and anti_pattern.
- Large PCAPs: stream with PcapReader: script, plus an anti_pattern.
- Non-IP packets / UDP without IP: guarded by `has_ip` throughout the script.

## Deliberate drops and deviations

- Prose about using the helper module through `sys.path.insert(0, '/root/skills/pcap-analysis')` and the import snippets: replaced by the AIP execution step. The helper's logic was ported, not imported.
- "Overview" bullets and the explanation of what scapy is: background the agent already knows.
- The "Simple threshold is NOT robust because…" rationale (time-insensitivity, distributed scans): the rationale was dropped, but the rule it justifies is kept in full.
- **Deviation:** pcap_utils rounds `iat_mean` and `iat_variance` to 6 decimal places. The script writes 10 significant digits instead, so very small variances keep their meaning. On this capture the values agree with the 6-dp ones to that precision. `duration_seconds` also uses 10 significant digits (the source does not round it).
- **Judgment call:** the task statement words `bidirectional_flows` as "count of flows whose reverse key also exists". Both curated sources divide that count by 2 (one count per A↔B pair). The script follows the curated sources. If a future task explicitly asks for the undivided count, the undivided number is `2 * bidirectional_flows`.
- **Degenerate-case guard:** beaconing additionally needs at least 2 inter-arrival gaps (3 or more timestamps). pcap_utils' `iat_stats` returns None for 0 or 1 packet, and a CV of 0 there would otherwise flag a lone packet as beaconing.
- The task folder's `scripts/extract_*groundtruth.py` were deliberately not read or used. They are grader material, not skill knowledge, and the skill computes everything from the capture.
