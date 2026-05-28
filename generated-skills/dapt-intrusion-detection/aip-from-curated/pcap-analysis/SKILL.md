---
name: pcap-analysis
description: "Analyze network packet captures (PCAP files) with Scapy and compute network statistics — packet/byte/protocol counts, Shannon entropy, communication-graph metrics, inter-arrival timing, flow tuples, and detection signals for port scans, DoS spikes, and C2 beaconing. Use whenever a task involves reading a .pcap, computing traffic statistics, populating a network_stats.csv, or classifying traffic as benign vs scan/DoS/beaconing. Pairs with the bundled tested helper module pcap_utils.py whose detection thresholds are calibrated — do not reimplement."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 with scapy installed. The helper module pcap_utils.py sits at the skill root; add the skill folder to sys.path before importing.
---

```yaml
purpose: >
  Analyze a PCAP file end-to-end: load packets, split by protocol, compute basic
  counts, entropy, communication-graph metrics, temporal and flow statistics,
  and run calibrated detectors for port scans, DoS spikes, and C2 beaconing.
  The bundled pcap_utils.py module holds tested implementations with the
  correct thresholds — the agent must use those helpers rather than rolling its
  own, because the most common failure mode is divergent thresholds producing
  silently-wrong answers.

trigger_when:
  - User points at a .pcap file and asks for traffic statistics or a summary.
  - Task requires populating a network_stats.csv or similar metrics template.
  - Need to classify traffic as benign vs scan / DoS / beaconing for intrusion-detection workflows.
  - Computing graph metrics (indegree, outdegree, density) over IP communications.
  - Computing Shannon entropy of port or IP distributions.
  - Computing inter-arrival-time statistics or producer/consumer ratios.

do_not_use_when:
  - Working with NetFlow / IPFIX / Zeek logs rather than raw PCAPs (different libraries and abstractions).
  - Performing deep packet inspection of application-layer payloads (HTTP, DNS, TLS) — this skill stops at the 5-tuple and counters.
  - Live capture or interface sniffing — this skill assumes an existing .pcap on disk.

scope_and_approval: >
  Read-only over the PCAP. The agent may freely import pcap_utils, run analysis
  scripts, and write derived results (e.g., network_stats.csv) to the working
  directory. No network operations; no modifications to the source capture.

steps:
  - name: import-helpers
    description: >
      Add the skill folder to sys.path and import from pcap_utils. Prefer the
      helper functions over hand-rolled equivalents — they encode the calibrated
      thresholds. Typical import set: load_packets, split_by_protocol,
      graph_metrics, port_counters, ip_counters, iat_stats, flow_metrics,
      packets_per_minute_stats, producer_consumer_counts, shannon_entropy,
      detect_port_scan, detect_dos_pattern, detect_beaconing.
  - name: load-packets
    description: "Load the capture with load_packets(path) (wraps scapy.rdpcap). For very large PCAPs that exceed memory, stream with scapy.PcapReader instead."
  - name: split-by-protocol
    description: "Call split_by_protocol(packets) to get the canonical {ip, tcp, udp, icmp, arp} bucketing. Downstream steps consume these slices."
  - name: basic-stats
    description: "Compute total_packets = len(packets), total_bytes = sum(len(p) for p in packets), avg packet size, and per-protocol counts from the split buckets."
  - name: entropy
    description: "Use shannon_entropy(counter) on port and IP Counters (via port_counters / ip_counters). Low entropy = focused traffic (normal); high entropy = scanning-like spread."
  - name: graph-metrics
    description: >
      Call graph_metrics(parts['ip']) to get num_nodes, num_edges,
      network_density, max_indegree, max_outdegree. Degree counts UNIQUE IPs,
      not packets — a 38-node network cannot have indegree > 37.
  - name: temporal-metrics
    description: "Derive sorted timestamps, then call iat_stats(timestamps) for iat_mean / iat_variance / iat_cv, and packets_per_minute_stats(timestamps) for ppm_avg / ppm_max / ppm_min."
  - name: producer-consumer
    description: "Call producer_consumer_counts(parts['ip'], all_nodes) to count IPs with PCR > 0.2 (producers) and PCR < -0.2 (consumers). PCR = (sent - recv) / (sent + recv) on byte totals."
  - name: flow-metrics
    description: >
      Call flow_metrics(parts['tcp'], parts['udp']) to obtain unique_flows,
      tcp_flows, udp_flows, bidirectional_flows. Flows are 5-tuples (src_ip,
      dst_ip, src_port, dst_port, proto); only packets with an IP layer count.
  - name: detect-signals
    description: >
      Run the three detectors in parallel: detect_port_scan(parts['tcp']),
      detect_dos_pattern(ppm_avg, ppm_max), detect_beaconing(iat_cv). Each
      returns a boolean. Traffic is benign iff all three are False.
    parallel: true
  - name: write-results
    description: >
      If the task supplies a network_stats.csv template, read it, fill the
      `value` column for each known `metric` row, preserve `#`-prefixed comment
      rows, and write back. Otherwise emit a dict / JSON summary.

decisions:
  - signal: A source has port_entropy > 6.0 AND syn_only_ratio > 0.7 AND unique_ports > 100 (and ≥ 50 TCP packets observed).
    action: Flag has_port_scan = True. All three conditions are required — partial matches are not scans.
  - signal: packets_per_minute_max / packets_per_minute_avg > 20.
    action: Flag has_dos_pattern = True. Ratios of 5×, 10×, even 15× are normal traffic variation, NOT DoS.
  - signal: Inter-arrival-time coefficient of variation (iat_cv = std/mean) < 0.5.
    action: Flag has_beaconing = True (regular, robotic periodicity). CV > 1.0 is bursty/human traffic — normal.
  - signal: has_port_scan, has_dos_pattern, and has_beaconing are ALL False.
    action: Classify the capture as benign. If any detector fires, the capture is not benign.
  - signal: An IP receives from / sends to more unique peers than there are nodes in the graph (e.g., indegree > num_nodes).
    action: You are counting packets, not unique IPs. Switch to len(set_of_peers). Use graph_metrics() to avoid this.
  - signal: A packet lacks an IP layer (ARP, link-layer artifacts) or a UDP packet lacks IP.
    action: Skip it for any IP-keyed metric. Guard with `if IP in pkt:` before reading pkt[IP].src.

anti_patterns:
  - Reimplementing detect_port_scan / detect_dos_pattern / detect_beaconing with different thresholds. The bundled thresholds are calibrated; divergent ones silently produce wrong verdicts.
  - Computing max_indegree / max_outdegree from packet counts instead of unique-IP sets. Degree is a count of distinct peers, capped at num_nodes - 1.
  - Calling any TCP/UDP-only port_scan or flow logic without first checking `if IP in pkt:` — link-layer UDP and bare ARP will raise on pkt[IP].src.
  - Treating a 5×, 10×, or 15× packets-per-minute spike as DoS. The threshold is strictly > 20×.
  - Declaring a capture "benign" while one of the three detectors fires. Benign requires ALL three booleans to be False.
  - Using a simple "many ports touched = scan" heuristic. Without high entropy AND SYN-only ratio AND port count, it misfires on normal multi-service hosts.
  - Loading a multi-gigabyte PCAP with rdpcap into memory. Use scapy.PcapReader for streaming when the file is too large.
  - Overwriting `#`-prefixed comment rows when filling network_stats.csv. Preserve them verbatim.

scenarios:
  - need: Identify the dominant protocol in a capture.
    action: Build {tcp, udp, icmp, arp} counts from split_by_protocol, then max(counts, key=counts.get).
    outcome: A single protocol label (e.g., "tcp") suitable for the dominant_protocol metric row.
  - need: Decide whether a capture contains a port scan.
    context: A single source sends ~5000 TCP packets to 250 distinct destination ports, mostly SYN, no ACKs returned.
    action: Call detect_port_scan(parts['tcp']). It checks per-source entropy, SYN-only ratio, and unique-port count against the calibrated thresholds.
    outcome: Returns True only when all three conditions hold for the same source, avoiding false positives on benign multi-port hosts.
  - need: Detect C2 beaconing in long-running traffic.
    context: Hosts that beacon to a controller produce highly regular inter-arrival times.
    action: Compute iat_stats(timestamps)['iat_cv'], then detect_beaconing(iat_cv).
    outcome: True when CV < 0.5 — flagging the robotic periodicity that distinguishes beacons from bursty human traffic.
  - need: Populate a provided network_stats.csv with computed metrics.
    action: Read the CSV, build a results dict keyed by metric name, then rewrite the file preserving `#` comment rows and only updating known metric rows.
    outcome: A filled CSV with calibrated metric values and the original template structure intact.
```
