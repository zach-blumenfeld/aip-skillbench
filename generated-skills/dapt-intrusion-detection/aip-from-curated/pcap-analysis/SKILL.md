---
name: pcap-analysis
description: "Guidance for analyzing network packet captures (PCAP files) and computing network statistics using Python, with tested utility functions. Covers protocol counts, byte/size stats, Shannon entropy of IPs and ports, directed-IP graph metrics, inter-arrival timing, producer/consumer ratios, 5-tuple flows, and strict-threshold detectors for port scans, DoS spikes, and C2 beaconing. Use when filling network_stats CSVs, classifying capture traffic as benign or malicious, or running DAPT2020-style intrusion-detection analyses."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Analyze a PCAP file and emit the full network-statistics block the
  DAPT2020 intrusion-detection task expects: per-protocol packet counts,
  duration and per-minute rates, packet-size stats, Shannon entropy of
  IPs and ports, directed-IP graph metrics, inter-arrival timing,
  producer/consumer counts, 5-tuple flow metrics, and three boolean
  detection flags (port scan, DoS pattern, beaconing) plus the derived
  is_traffic_benign flag. Helpers in `scripts/pcap_utils.py` enforce the
  calibrated thresholds — entropy > 6.0, SYN-only > 0.7, unique ports >
  100, max/avg PPM > 20, IAT CV < 0.5 — that hand-rolled detection
  routinely gets wrong. The orchestrator `scripts/compute_all_stats.py`
  collapses every helper call into a single dict keyed by the CSV
  template's exact metric names.

trigger_when:
  - User provides a PCAP file (e.g. `/root/packets.pcap`) and asks to
    compute network statistics or fill in `network_stats.csv`.
  - DAPT2020 / DAPT intrusion-detection task is active.
  - Need to classify capture traffic as benign vs malicious (port scan /
    DoS / beaconing).
  - Computing Shannon entropy over packet feature distributions (IPs,
    ports) or graph metrics on a directed IP communication graph.
  - Computing inter-arrival timing statistics, packets-per-minute rates,
    or 5-tuple flow metrics on captured traffic.

do_not_use_when:
  - Live network capture or pcap acquisition (this skill consumes an
    existing file, not a wire).
  - Deep packet inspection of application-layer payloads (HTTP request
    parsing, TLS fingerprinting, DNS tunneling decode) — the helpers
    only inspect IP/TCP/UDP/ICMP/ARP headers.
  - Streaming analysis of multi-gigabyte captures where `rdpcap` cannot
    load the file in memory. The helpers use `rdpcap`; for huge files
    refactor to `PcapReader` instead.

scope_and_approval: >
  Read-only on the input PCAP. The only write is the filled
  `network_stats.csv` (the task's expected output). The CSV template's
  comment rows (lines starting with `#`) and column ordering are
  preserved exactly — only empty `value` cells are populated. No network
  access, no external API calls.

steps:
  - name: load-packets
    description: >
      Call `pcap_utils.load_packets(pcap_path)` to read the full capture
      with scapy `rdpcap`. Returns the scapy PacketList used by every
      downstream step.
    script: scripts/pcap_utils.py
    inputs:
      - name: pcap_path
        type: string
        description: Filesystem path to the input PCAP (e.g. `/root/packets.pcap`).
    outputs:
      - name: packets
        type: object
        description: scapy PacketList.

  - name: split-by-protocol
    description: >
      Call `pcap_utils.split_by_protocol(packets)` to obtain protocol-
      filtered packet lists keyed `ip`, `tcp`, `udp`, `icmp`, `arp`.
      Every UDP/IP-dependent downstream step pulls from this dict so
      that ARP and other non-IP frames are excluded correctly.
    script: scripts/pcap_utils.py
    inputs:
      - name: packets
        type: object
    outputs:
      - name: parts
        type: object
        description: dict[str, list[Packet]].

  - name: compute-all-stats
    description: >
      Prefer this single call over invoking each helper inline. Runs
      `compute_all_stats.compute_all_stats(pcap_path)` which orchestrates
      every per-domain helper (`shannon_entropy`, `graph_metrics`,
      `iat_stats`, `flow_metrics`, `producer_consumer_counts`,
      `packets_per_minute_stats`, plus the three detectors) and returns a
      flat dict keyed by the EXACT `metric` strings in
      `network_stats_template.csv`. Boolean detection flags are computed
      with the strict thresholds in `pcap_utils.py` (see
      `references/detection-thresholds.md`). If a sub-result looks wrong,
      do not patch values inline — fall through to the per-step nodes
      below to diagnose.
    script: scripts/compute_all_stats.py
    inputs:
      - name: pcap_path
        type: string
    outputs:
      - name: stats
        type: object
        description: >
          dict keyed by CSV `metric` strings. Includes every protocol
          count, size stat, entropy, graph metric, IAT stat,
          producer/consumer count, flow metric, and the four boolean
          flags (`has_port_scan`, `has_dos_pattern`, `has_beaconing`,
          `is_traffic_benign`).

  - name: compute-protocol-counts
    description: >
      Component breakout of `compute-all-stats`. `protocol_tcp/udp/icmp/arp`
      are `len(parts['tcp'])` etc. `protocol_ip_total` is
      `len(parts['ip'])` — the count of frames containing an IP layer,
      NOT the sum of tcp+udp+icmp (which double-counts when packets
      carry multiple layers and excludes non-TCP/UDP IP traffic).
    inputs:
      - name: parts
        type: object
    outputs:
      - name: protocol_counts
        type: object

  - name: compute-time-series
    description: >
      Call `pcap_utils.packet_timestamps(packets)` then
      `pcap_utils.packets_per_minute_stats(timestamps)`. Buckets are
      60-second windows anchored at the earliest timestamp. The CSV
      fields `packets_per_minute_avg/max/min` and `duration_seconds`
      come from this step. `duration_seconds = max - min` over the
      timestamp list (NOT bucket count × 60).
    script: scripts/pcap_utils.py
    inputs:
      - name: packets
        type: object
    outputs:
      - name: ppm_stats
        type: object
      - name: duration_seconds
        type: float

  - name: compute-size-stats
    description: >
      Compute `total_bytes`, `avg_packet_size`, `min_packet_size`,
      `max_packet_size` from `len(p) for p in packets`. Size stats run
      across the FULL packet stream, not just IP packets — ARP and
      malformed frames still contribute bytes on the wire.
    inputs:
      - name: packets
        type: object
    outputs:
      - name: size_stats
        type: object

  - name: compute-entropy-stats
    description: >
      Build `Counter`s for src_ip, dst_ip, src_port, dst_port (port
      Counters via `pcap_utils.port_counters(tcp, udp)`; IP Counters via
      `pcap_utils.ip_counters(ip_packets)`). Pass each to
      `pcap_utils.shannon_entropy(counter)` which returns
      `H = -Σ p log₂ p` rounded to 4 decimals. The CSV's
      `unique_src_ports` / `unique_dst_ports` are `len(src_ports)` /
      `len(dst_ports)`.
    script: scripts/pcap_utils.py
    inputs:
      - name: parts
        type: object
    outputs:
      - name: entropy_stats
        type: object

  - name: compute-graph-metrics
    description: >
      Call `pcap_utils.graph_metrics(parts['ip'])`. Returns a dict with
      `num_nodes`, `num_edges`, `network_density`, `max_indegree`,
      `max_outdegree`, and a `_graph_state` triple
      `(indegree, outdegree, all_nodes)` needed by
      `compute-producer-consumer`. Degrees count UNIQUE peer IPs, not
      packets — for a 38-node graph `max_indegree <= 37`, never
      thousands.
    script: scripts/pcap_utils.py
    inputs:
      - name: parts
        type: object
    outputs:
      - name: graph_stats
        type: object

  - name: compute-iat-stats
    description: >
      Call `pcap_utils.iat_stats(timestamps)` (timestamps must already
      be sorted ascending; `packet_timestamps` returns them sorted).
      Returns `iat_mean`, `iat_variance`, `iat_cv` (= std / mean, or 0
      when mean is 0). `iat_cv` feeds both the CSV and the beaconing
      detector.
    script: scripts/pcap_utils.py
    inputs:
      - name: timestamps
        type: list[float]
    outputs:
      - name: iat
        type: object

  - name: compute-producer-consumer
    description: >
      Call `pcap_utils.producer_consumer_counts(parts['ip'], all_nodes)`
      where `all_nodes` is the third element of `graph_stats._graph_state`.
      Counts IPs whose PCR = (sent - recv) / (sent + recv) exceeds +0.2
      (producers) or falls below -0.2 (consumers); the [-0.2, 0.2] band
      is "balanced" and ignored.
    script: scripts/pcap_utils.py
    inputs:
      - name: ip_packets
        type: object
      - name: all_nodes
        type: object
    outputs:
      - name: pc_stats
        type: object

  - name: compute-flow-metrics
    description: >
      Call `pcap_utils.flow_metrics(parts['tcp'], parts['udp'])`. Returns
      `unique_flows`, `tcp_flows`, `udp_flows`, `bidirectional_flows`.
      Flow key is the 5-tuple `(src_ip, dst_ip, src_port, dst_port,
      proto)`. The helper requires `IP in pkt` before reading IP fields
      so UDP-over-link-layer frames are skipped. `bidirectional_flows`
      counts pairs where the reversed key also exists, divided by 2 (so
      A→B and B→A together are 1 bidirectional flow, not 2).
    script: scripts/pcap_utils.py
    inputs:
      - name: parts
        type: object
    outputs:
      - name: flow_stats
        type: object

  - name: detect-port-scan
    description: >
      Call `pcap_utils.detect_port_scan(parts['tcp'])`. Returns `True`
      only when SOME source IP simultaneously satisfies port entropy
      > 6.0, SYN-only ratio > 0.7, and > 100 unique destination ports,
      with >= 50 TCP packets to be considered. Do NOT lower any
      threshold or invent a simpler "many ports => scan" rule — see
      `references/detection-thresholds.md` for the failure cases each
      gate rejects.
    script: scripts/pcap_utils.py
    inputs:
      - name: tcp_packets
        type: object
    outputs:
      - name: has_port_scan
        type: boolean

  - name: detect-dos-pattern
    description: >
      Call `pcap_utils.detect_dos_pattern(ppm_avg, ppm_max)`. Returns
      `True` iff `ppm_max / ppm_avg > 20`. Ratios of 5x, 10x, even 15x
      are NORMAL traffic variation, not DoS. If `ppm_avg == 0` the
      helper returns `False` to avoid divide-by-zero.
    script: scripts/pcap_utils.py
    inputs:
      - name: ppm_avg
        type: float
      - name: ppm_max
        type: integer
    outputs:
      - name: has_dos_pattern
        type: boolean

  - name: detect-beaconing
    description: >
      Call `pcap_utils.detect_beaconing(iat_cv)`. Returns `True` iff
      `iat_cv < 0.5`. CV < 0.5 means inter-arrival times are highly
      regular (robotic / programmatic); CV ~1 is Poisson-like human
      traffic; CV > 1 is bursty.
    script: scripts/pcap_utils.py
    inputs:
      - name: iat_cv
        type: float
    outputs:
      - name: has_beaconing
        type: boolean

  - name: assess-benign
    description: >
      `is_traffic_benign = NOT (has_port_scan OR has_dos_pattern OR
      has_beaconing)`. There is no independent benign signal — the
      absence of all three detector hits IS the signal.
      `compute_all_stats` performs this fold automatically; surface it
      here so the agent does not invent a separate threshold.
    inputs:
      - name: has_port_scan
        type: boolean
      - name: has_dos_pattern
        type: boolean
      - name: has_beaconing
        type: boolean
    outputs:
      - name: is_traffic_benign
        type: boolean

  - name: verify-detection-flags
    description: >
      Before writing the CSV, sanity-check the three detection booleans
      against the underlying numbers in `stats`. Patterns to confirm:
      (1) if `has_port_scan == True`, at least one source IP has
      port_entropy > 6.0 AND syn_only_ratio > 0.7 AND > 100 unique
      ports AND >= 50 TCP packets. (2) if `has_dos_pattern == True`,
      `stats['packets_per_minute_max'] / stats['packets_per_minute_avg']
      > 20`. (3) if `has_beaconing == True`, `stats['iat_cv'] < 0.5`.
      A mismatch means the orchestrator was bypassed — re-run
      `compute_all_stats` rather than overriding the booleans by hand.
    inputs:
      - name: stats
        type: object
    outputs:
      - name: verified_stats
        type: object

  - name: write-csv
    description: >
      Call `compute_all_stats.fill_csv_template(template_path, stats,
      output_path)`. Preserves all comment rows (lines starting with
      `#`), the header row, and the column ordering exactly. Only
      populates empty `value` cells; rows whose `metric` is not in
      `stats` are passed through unchanged. Booleans render as
      lowercase `true` / `false` to match the test harness. If
      `output_path == template_path` the file is overwritten in place
      (the DAPT task's default — agent writes to
      `/root/network_stats.csv`).
    script: scripts/compute_all_stats.py
    inputs:
      - name: template_path
        type: string
      - name: stats
        type: object
      - name: output_path
        type: string
    outputs:
      - name: csv_path
        type: string

  - name: load-thresholds-reference-when-stuck
    description: >
      If a detection flag looks wrong (port-scan firing on benign
      browsing, DoS missed on an obvious flood, beaconing flagged on a
      bursty workload) — read `references/detection-thresholds.md`
      before adjusting any number. Almost every "wrong" result is the
      agent rebuilding the detector with a softer threshold rather than
      a true bug in `pcap_utils.py`.

scenarios:
  - need: >
      Fill in `/root/network_stats.csv` for the DAPT2020 capture at
      `/root/packets.pcap`.
    context: >
      Template has ~30 empty `value` cells across protocol, time,
      size, entropy, graph, IAT, PCR, flow, and detection rows, plus
      comment rows that must be preserved.
    action: >
      `python scripts/compute_all_stats.py /root/packets.pcap
      --csv-template /root/network_stats.csv` — single call, fills in
      place, leaves comments and ordering untouched.
    outcome: >
      Every numeric cell populated by the calibrated helpers; the four
      booleans (`has_port_scan`, `has_dos_pattern`, `has_beaconing`,
      `is_traffic_benign`) computed via the strict-threshold detectors.

  - need: >
      Confirm a capture contains a port scan before flagging an alert.
    context: >
      Capture has 8000 TCP packets from a single source touching ~150
      destination ports, mostly SYN flags, no completed handshakes.
    action: >
      `parts = split_by_protocol(load_packets(path)); detect_port_scan
      (parts['tcp'])`. Returns `True` because all three gates fire for
      that source.
    outcome: >
      Single boolean, no threshold-tuning. If `False`, inspect the
      actual values via the helper internals (`port_scan_signals`) and
      fall back to `references/detection-thresholds.md` for the failure
      mode each gate rejects.

  - need: >
      max_indegree comes back as 38421 on a 38-node network. Obviously
      wrong.
    context: >
      Custom implementation accidentally counted packets per
      destination instead of unique source IPs per destination.
    action: >
      Replace the inline loop with `pcap_utils.graph_metrics(ip_packets)`
      and read `max_indegree` off the returned dict. The helper builds
      `defaultdict(set)` so degrees count UNIQUE peers.
    outcome: >
      `max_indegree <= num_nodes - 1`. For a 38-node graph, the value
      is at most 37.

  - need: >
      IAT CV is 0.42, just under the 0.5 beaconing threshold. Confirm
      whether the detector firing reflects real beaconing.
    context: >
      Source dataset is a mixed workload that includes some periodic
      heartbeat traffic.
    action: >
      Read `references/detection-thresholds.md` § Beaconing. CV < 0.5
      is the calibrated trigger; do not lower the threshold "because
      it's borderline". If the agent wants per-flow inspection (not
      part of the DAPT2020 CSV), it can call `iat_stats` per-flow
      manually outside this skill's scope.
    outcome: >
      Detector booleans match the helper output; the CSV records
      `has_beaconing = true` and `is_traffic_benign = false`.

anti_patterns:
  - Re-implementing the detectors inline with softer thresholds (e.g.
    `entropy > 5.0`, `syn_only > 0.5`, `unique_ports > 50`,
    `ppm_max/ppm_avg > 10`, `iat_cv < 0.7`). The source-skill thresholds
    are calibrated; loosening them produces false positives that fail
    the task tests.
  - Counting `max_indegree` / `max_outdegree` as total packets to a
    destination rather than unique source IPs. Use `graph_metrics`
    which wraps `defaultdict(set)` — degrees are bounded by
    `num_nodes - 1`.
  - Computing flow stats over packets that lack an IP layer (UDP over
    link-layer frames, raw scapy). `flow_metrics` guards with
    `if IP in pkt`; hand-rolled loops drop this guard and produce
    KeyErrors or undercounts.
  - Counting `bidirectional_flows` without dividing by 2. Every
    bidirectional pair contributes both A→B and B→A to the count;
    forgetting the `// 2` doubles the answer.
  - Forgetting to skip rows whose `metric` is missing from `stats`
    when writing the CSV. The template's comment rows (`#` prefix) and
    column ordering must round-trip exactly — `fill_csv_template`
    handles this.
  - Emitting `True` / `False` (Python repr) in CSV booleans instead of
    `true` / `false`. The test harness is case-sensitive;
    `fill_csv_template` converts booleans correctly.
  - Calling `detect_dos_pattern` with `ppm_avg = 0` and treating the
    `False` return as "no spike". When `ppm_avg = 0` the capture
    contains <2 packets — surface the empty-capture case explicitly
    rather than reading the boolean.
  - Calling the detectors before splitting by protocol. `detect_port_scan`
    expects TCP packets; passing the raw PacketList wastes work and may
    mis-classify ARP frames as part of the TCP flow set.
  - Overriding a detector's boolean by hand "because the value seems
    off". The detectors are the source of truth; if a value looks wrong,
    re-run `compute_all_stats` or read
    `references/detection-thresholds.md`, do not toggle the bool.
  - Mutating `network_stats.csv` row order or stripping comment lines
    while filling values. The test harness reads the file with
    `DictReader` and tolerates extra rows, but order-sensitive tooling
    may compare line-by-line.
```
