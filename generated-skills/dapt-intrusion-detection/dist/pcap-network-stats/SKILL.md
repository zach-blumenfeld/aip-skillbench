---
name: pcap-network-stats
description: Compute network statistics from a PCAP with scapy and fill a metric,value CSV - protocol counts, packets-per-minute, packet sizes, Shannon entropy of IPs/ports, directed IP-graph degree/density, inter-arrival times, producer/consumer ratio, 5-tuple flows - plus port-scan, DoS, beaconing, and benign flags from calibrated thresholds. Use for DAPT2020-style traffic-stats tasks (network_stats.csv, packets.pcap) and any PCAP intrusion/threat triage that asks for these metrics.
compatibility: Python >= 3.8 with scapy (task image ships scapy==2.5.0; pandas/numpy not needed). No other tools.
---

# PCAP Network Stats

## Trigger When
- A task hands you a `.pcap` and a `metric,value` CSV (e.g. `/root/packets.pcap`, `/root/network_stats.csv`) to fill.
- Asked for protocol distribution, packets per minute, entropy of IPs/ports, IP-graph degree/density, IAT, producer/consumer ratio, or 5-tuple flow counts from a capture.
- Asked whether captured traffic is benign, or shows a port scan, DoS/flood, or C2 beaconing.
- Network forensics / intrusion-detection triage over DAPT2020 or similar enterprise traffic.

## Purpose
Turns one packet capture into the full metric set plus four threat flags with a single streaming script, using the exact definitions and strict detection thresholds these tasks are graded against (unique-IP degrees, IPv4-only graph, UDP-without-IPv4 skipped for ports, three-signal port-scan rule, >20x DoS ratio, CV<0.5 beaconing). Hand-rolled versions usually get these conventions wrong; the script reproduces them.

## Procedure

Progress:
- [ ] 1. Check environment (execution)
- [ ] 2. Answer `definitions` (decision)
- [ ] 3. Compute and fill the CSV (execution)
- [ ] 4. Fill any leftover rows (client task, only if step 3 exits 2)
- [ ] 5. Report (client task)

### 1. Check environment (execution)
Run from this skill's folder:
```bash
python3 -c "import sys, scapy; print(sys.version.split()[0], scapy.__version__)"
```
Needs Python >= 3.8 and scapy. If anything is missing, name it; then `pip3 install --break-system-packages scapy` if the network allows.

### 2. Answer `definitions` (decision)
Input: the task statement, plus any reference/ground-truth extraction script shipped with the task.
```yaml
bidir_mode:
  type: choice
  instructions: Which definition of bidirectional_flows does the task use? Read the statement and any reference code. The one-line wording used in DAPT2020 network-stats tasks ("count of flows whose reverse key also exists") does not on its own pick pairs or flows_with_reverse; that task family's reference extractor counts conversations.
  criteria:
    conversations: Default. Each flow and its reverse are merged into one canonical key and the distinct keys are counted, one-way flows included (bidirectional flow records / biflows; DAPT2020 network-stats family).
    pairs: The task or its reference code explicitly counts only two-way pairs, each once (e.g. counts flows with a reverse and divides by 2).
    flows_with_reverse: The task explicitly says to count both directions of a two-way pair separately / not to halve.
thresholds_overridden:
  type: noul
  instructions: Does the task state its own numeric threshold for port scan, DoS, or beaconing that differs from the defaults (scan entropy > 6.0, SYN-only ratio > 0.7, unique ports > 100, >= 50 TCP packets per source; DoS ppm max/avg > 20; beaconing IAT CV < 0.5)?
  criteria:
    true: The task gives an explicit different number for one of these.
    false: The task only describes the flags qualitatively ("extreme spike", "low IAT variance") or gives the same numbers.
```
A wrong `thresholds_overridden: true` silently changes graded flags, so reconsider any close call that leans true. Reconsider `bidir_mode` if you picked anything but `conversations` without explicit wording or code to point to.

### 3. Compute and fill the CSV (execution)
```bash
python3 scripts/pcap_stats.py --pcap /root/packets.pcap --csv /root/network_stats.csv --bidir <bidir_mode> --json /tmp/pcap_stats.json
```
- If `thresholds_overridden` is true, add the matching flags: `--scan-entropy`, `--scan-syn-ratio`, `--scan-unique-ports`, `--scan-min-packets`, `--dos-ratio`, `--beacon-cv`.
- Omit `--csv` to compute without writing. ~10 s for a 33 MB / 114k-packet capture.
- It fills only the `value` column of rows it knows, keeps the header and `#` lines byte-for-byte, then re-checks the file. Exit 0 = every row filled. Exit 2 = rows listed in `csv.empty_after_write` (names the script does not compute) still need values; go to step 4. Exit 1 with `ERROR:` = missing file/scapy or an empty capture; fix and rerun.
- Stdout JSON: `metrics` (exact strings written) and `diagnostics` - `ppm_max_over_avg_ratio`, `port_scan_top_candidates` (per-source entropy / SYN-only ratio / unique ports), `bidirectional_variants` (all three counts), and counts of non-IPv4 packets skipped.

### 4. Fill leftover rows (client task, only on exit 2)
Read [references/metric-definitions.md](references/metric-definitions.md), compute each listed metric with the same conventions (reuse `shannon_entropy` / the parsing in `scripts/pcap_stats.py`), and write only its `value` cell. Rerun nothing else; then confirm no non-comment row is empty.

### 5. Report (client task)
Reply briefly: path written, the key metrics, each flag with the number that decided it (scan: top candidate's entropy / SYN-only ratio / unique ports vs thresholds; DoS: the max/avg ratio vs 20; beaconing: `iat_cv` vs 0.5), and the `bidir_mode` used with the other two variant counts.

## Gotchas
- Thresholds are strict and the flags follow them only. Don't flip a flag because the dataset is known for APT activity or because one IP hits 1000 ports: high unique ports with low entropy or low SYN-only ratio is normal service traffic, and a 9x minute spike is not DoS.
- Degrees count UNIQUE peer IPs; a max degree above `num_nodes - 1` means packets were counted.
- `IP in pkt` is IPv4 only. IPv6 packets count toward `protocol_udp`/`protocol_tcp` but are left out of IP entropy, the graph, PCR, and flows. UDP without IPv4 is also left out of port counts, but TCP ports count for every TCP packet.
- Protocol counts overlap (ICMP errors, tunnels); never "fix" them to sum to the total.
- Packets-per-minute uses only non-empty 60 s buckets anchored at the first packet; IAT variance is population variance (divide by N).
- Don't use `rdpcap` + a list comprehension per metric on large captures; the script streams one pass.
- Don't edit, reorder, or drop the CSV's `#` comment lines or header; booleans are lowercase `true`/`false`.
