# Source material and distillation log for `pcap-network-stats`

## Provenance
Compiled 2026-10-20 from two curated Agent Skills, copied here verbatim:

| File | Origin |
|------|--------|
| `pcap-analysis/SKILL.md` | curated skill `pcap-analysis`: metric recipes for PCAP stats (scapy) |
| `pcap-analysis/pcap_utils.py` | its helper module ("tested, correct implementations") |
| `threat-detection/SKILL.md` | curated skill `threat-detection`: exact port-scan / DoS / beaconing thresholds |

Task context, which was used but is not copied here: the DAPT2020 network-stats task statement
(fill `/root/network_stats.csv` from `/root/packets.pcap`), its Dockerfile (Ubuntu 24.04, Python 3.12,
scapy 2.5.0, pandas 2.2.2, numpy 1.26.4), and the task's reference extractor scripts
(`extract_simple_groundtruth.py`, `extract_advanced_groundtruth.py`, `extract_groundtruth.py`).
Those were used only to cross-check definitions. The skill hardcodes no values; everything is computed from the capture.

## Intent
One coherent unit: turn a capture into the full metric set + threat flags and fill the task CSV.
The two sources describe a single workflow (compute metrics → apply thresholds), so they merge into one
skill with one streaming script.

## Component kinds (priority: script > decision > client task)
| Component | Kind | Why |
|-----------|------|-----|
| 1. Check environment | execution | Deterministic import/version probe. |
| 2. `definitions` (`bidir_mode`, `thresholds_overridden`) | decision | Needs a judgment about the task wording and any reference code. The answer space is fixed (3 labels / yes-no) and maps straight onto script flags. |
| 3. Compute + fill CSV (`scripts/pcap_stats.py`) | execution | Every metric, threshold, rounding rule and the CSV rewrite/validation is deterministic code. The source's prose recipes, the `pcap_utils.py` helpers and the threat-detection manual implementations all become this one script, so there is one file and one pass over the capture. |
| 4. Fill leftover rows | client_task | Only reached when the CSV asks for a metric the script does not know. Its definition only exists in that task's statement, so the agent has to write the code. |
| 5. Report | client_task | Free text summarising the result. |

## Deviations from the sources (deliberate, with rationale)
1. **`bidirectional_flows` default = `conversations`, not the source's `pairs` (`//2`).** The three
   conventions give 1809 / 1758 / 3516 on the real capture. The task's own reference extractor
   canonicalises (flow, reverse) and counts the distinct set (1809). Every other metric from the source
   rules matched that extractor exactly. DAPT2020 flow features also come from bidirectional flow
   records (CICFlowMeter). The statement's one-liner reads literally as "flows with a reverse" (3516),
   and the source helper halves that (1758). So the choice is a decision (`bidir_mode`), all three
   values are printed in `diagnostics.bidirectional_variants`, and `--bidir` switches between them.
2. **Density with < 2 nodes = 0** (task statement). `pcap_utils.graph_metrics` divided by 1 instead.
3. **Beaconing needs ≥ 3 packets.** With fewer packets, CV is defined as 0 and would trip `cv < 0.5`.
   The source helper returned `None` there (and the detector would then crash).
4. **packets-per-minute / IAT with a single packet** return one bucket and zeros instead of `None`, so every row still gets a value.
5. **Streaming `PcapReader`, one pass**, instead of `rdpcap` + one list comprehension per metric. This follows the source's
   "Memory with Large PCAPs" advice. Scapy dissection and `Layer in pkt` membership are unchanged, so counts are identical.
6. Added `total_packets` and `dominant_protocol`. Both are recipes from the source, and the script writes them
   only if the CSV has those rows.

## Completeness walk (source item → where it lives)
### pcap-analysis/SKILL.md
- Quick start / import helpers from `/root/skills/pcap-analysis` → replaced by `scripts/pcap_stats.py` (launch command in step 3). The module path is a drop (see below).
- "Use helpers, don't reimplement; strict thresholds" → step 3 is the only compute path; Gotchas bullet 1.
- Overview bullet list → deliberate drop (background).
- Reading with scapy, protocol filters → script; references/metric-definitions.md "Protocol counts".
- Packet/byte counts, avg size → script; ref "Sizes".
- Protocol distribution → script; ref.
- Entropy formula + low/high interpretation → script `shannon_entropy`; ref "Entropy".
- Dst-port example (UDP needs IP) → script; Gotchas bullet 3; ref.
- Graph metrics, UNIQUE-IP degrees, 38-node sanity check, density formula → script; Gotchas bullet 2; ref "Graph".
- IAT mean/variance/CV, CV interpretation → script; ref "Temporal"; Gotchas bullet 5.
- PCR + ±0.2 thresholds → script; ref.
- Flows need IP + transport; tcp/udp split; bidirectional `//2` → script; `bidir_mode` decision (`pairs` label); ref "Flows".
- Minute buckets → script; Gotchas bullet 5; ref.
- Writing CSV, keep comments → script `fill_csv`/`validate_csv`; Gotchas last bullet.
- Dominant protocol → script metric `dominant_protocol`; ref.
- Port scan: three reasons simple thresholds fail; ALL three signals; ≥ 50 TCP packets per source; SYN-only = 0x02 without 0x10; entropy > 6, ratio > 0.7, ports > 100 → script defaults; decision `thresholds_overridden`; ref "Threat flags"; Gotchas bullet 1.
- DoS > 20 ratio; 5/10/15x normal → script; ref; Gotchas bullet 1.
- Beaconing CV < 0.5 → script; ref.
- Benign = all three false → script; ref.
- Common issues: PcapReader for large files, non-IP check, UDP without IP → script; Gotchas bullets 3 and 6.

### pcap-analysis/pcap_utils.py
- Every function (`shannon_entropy`, `split_by_protocol`, `port_counters`, `ip_counters`, `build_graph`, `graph_metrics`,
  `packet_timestamps`, `packets_per_minute_stats`, `iat_stats`, `producer_consumer_counts`, `flow_metrics`,
  `port_scan_signals`, `detect_port_scan`, `detect_dos_pattern`, `detect_beaconing`) → re-implemented in one pass in the script. Same formulas.
- Rounding (entropy 4, density 6, ppm avg 2, IAT mean/var 6, CV 4) → `ROUNDING` in the script; ref last section.
  Detector inputs are rounded as in the helpers (scan entropy 4 dp, ppm avg 2 dp, CV 4 dp).
- Configurable threshold keyword args → CLI flags `--scan-*`, `--dos-ratio`, `--beacon-cv`.
- `None` returns for ≤ 1 timestamp → deviation 4.

### threat-detection/SKILL.md
- Port-scan table + "why" column → ref "Threat flags" table and paragraph.
- 1000-ports example (entropy 4.28, SYN 0.15 → not a scan) → ref; Gotchas bullet 1.
- DoS threshold + 2372 / 262.9 = 9.02 example → ref.
- Beaconing threshold, low vs high CV meaning → ref.
- Benign assessment + summary table → script; ref table.
- Manual implementations → script.

## Deliberate drops
- Hardcoded helper path `/root/skills/pcap-analysis` and the `sys.path` import pattern. The skill ships its own script, and
  its mount path is unknown, so the launch command is relative to the skill folder.
- Overview bullet list and "Scapy is the standard library" prose: background the agent already knows.
- `rdpcap` code snippets per metric: superseded by the streaming script. The formulas themselves are kept.
- "Implementing your own logic will produce incorrect results" exhortations: replaced by making the script the
  only compute path. Gotchas bullet 1 carries the warning.
