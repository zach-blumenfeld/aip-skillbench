---
name: pcap-network-stats
description: >
  Compute the DAPT-style network-statistics battery (protocol counts,
  packets-per-minute rate, packet-size distribution, Shannon entropy over
  src/dst IPs and ports, directed IP-graph density and in/out-degree,
  inter-arrival timing, Producer/Consumer Ratio, 5-tuple flow accounting,
  bidirectional flows, plus heuristic port-scan / DoS / beaconing / benign
  flags) from a pcap and fill only the `value` column of a CSV template
  (e.g. `/root/network_stats.csv`), preserving comment lines (`#`) and the
  header. Use whenever the task references a pcap (DAPT2020 / packets.pcap)
  alongside a CSV template containing rows like `protocol_tcp`,
  `network_density`, `iat_cv`, `has_port_scan`, etc.
license: Apache-2.0
compatibility: Requires Python 3.10+ and scapy (`pip install scapy`).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Compute a fixed battery of network statistics from a pcap and write the
  results into the `value` column of a CSV template that the grader reads.
  The metrics span protocol mix, traffic rate over 60s buckets, packet size
  distribution, Shannon entropy of IP / port distributions, directed IP-graph
  shape, inter-arrival timing, Producer/Consumer Ratio per IP, 5-tuple flow
  accounting, and four boolean intrusion-detection flags
  (is_traffic_benign / has_port_scan / has_dos_pattern / has_beaconing).

trigger_when:
  - Task instruction references `packets.pcap` (or any pcap path) and a CSV
    template such as `/root/network_stats.csv` with a `value` column to fill.
  - Required metric names include any of `protocol_tcp`, `protocol_arp`,
    `packets_per_minute_avg`, `network_density`, `max_outdegree`,
    `src_ip_entropy`, `iat_cv`, `num_producers`, `bidirectional_flows`,
    `has_port_scan`, `has_dos_pattern`, `has_beaconing`, `is_traffic_benign`.
  - The traffic is described as DAPT2020 (or another labelled IDS dataset)
    and the deliverable is a filled CSV rather than a written report.

do_not_use_when:
  - Task requires live packet capture rather than offline pcap analysis.
  - Task asks for deep payload inspection / DPI / signature matching beyond
    the statistical metrics listed in `purpose`.
  - Task wants a free-form intrusion-detection narrative rather than a
    grader-readable CSV.

scope_and_approval: >
  Read-only on the pcap. The only write is to the CSV path the task names
  (`/root/network_stats.csv` by default). Comment lines (`#`-prefixed) and
  the header row are preserved verbatim; only the `value` column is updated;
  rows whose metric name is not in the computed set are left untouched. No
  network access, no privileged operations, no other filesystem writes.

steps:
  - name: locate-inputs
    description: >
      Confirm the pcap path (`packets.pcap` in CWD unless the task says
      otherwise) and the CSV path. Read the CSV once with `cat` to see which
      metric names appear and to register the order of comment lines and
      header columns so they can be preserved.
  - name: install-deps
    description: >
      Ensure scapy is importable (`python -c "import scapy"`); if not,
      `pip install scapy`. If scapy install is blocked, fall back to dpkt
      or pyshark — see `references/implementation-notes.md` for the
      drop-in plan.
  - name: dry-run-dump
    description: >
      Run `python scripts/compute_stats.py --pcap <pcap> --dump` first to
      see all 37 computed values. Eyeball-check sanity invariants
      (protocol counts sum sensibly, entropies are positive, density in
      [0,1]) before touching the CSV.
  - name: write-csv
    description: >
      Run `python scripts/compute_stats.py --pcap <pcap> --csv <csv>` to
      rewrite only the `value` column. The script preserves comments,
      header, and any metric rows it does not recognise.
  - name: verify
    description: >
      Re-read the CSV. Every non-comment data row should have a populated
      `value`. Boolean flags must be the lowercase strings `true` / `false`.
      Spot-check the invariants in `references/implementation-notes.md`
      ("Verification recipe" section).
  - name: tune-if-mismatch
    description: >
      If a value comes back wrong on grading, decide whether it is a
      *definitional ambiguity* (handled by the decisions table below) or a
      *threshold call* on one of the boolean flags. Adjust the script
      argument or override the cell, then re-verify. Do not silently
      regenerate every metric.

decisions:
  - signal: >
      The grader rejects `packets_per_minute_min` (or _avg) but other
      rate metrics look right.
    action: >
      Re-run with `--bucket-mode empty-included`. The default counts only
      non-empty 60s buckets; the alternate fills zero-count buckets in the
      time range, which changes min and avg.
  - signal: >
      `unique_src_ports` looks too low and you notice ICMP packets in
      the trace.
    action: >
      Expected — ICMP carries no ports, so ICMP packets are excluded from
      port counts and entropies by design. Do not "fix" by counting port 0.
  - signal: >
      `bidirectional_flows` is exactly twice the count you expected.
    action: >
      The default counts both directions of each pair (A→B and B→A each
      increment). If the grader wants the number of *pairs*, divide by 2.
  - signal: >
      A heuristic flag (port scan / DoS / beaconing) fires but the
      underlying numbers are tiny (e.g. only 20 IATs, low total traffic).
    action: >
      Treat as a false positive. Inspect the `--dump` output, manually set
      the flag to `false` (and reconsider `is_traffic_benign`).
  - signal: >
      Scapy is not installable in the environment.
    action: >
      Switch the implementation to dpkt or `tshark -T fields`; the CSV
      writer in the script is independent of the pcap reader. See
      `references/implementation-notes.md`.
  - signal: >
      The CSV row order or comment lines look altered after the script
      runs.
    action: >
      Stop and inspect — the script is supposed to be order-preserving and
      comment-preserving. Diff against a backup; the grader treats any
      mutation to non-`value` cells as a failure.

scenarios:
  - need: >
      Default DAPT2020 subset, pcap at `./packets.pcap`, CSV at
      `/root/network_stats.csv` already populated with metric names and
      empty `value` cells plus several `#`-prefixed section headers.
    action: >
      `pip install scapy` if missing → run
      `python scripts/compute_stats.py --pcap packets.pcap --dump` and eyeball
      values → run the same command with `--csv /root/network_stats.csv` →
      diff the CSV to confirm only `value` cells changed.
    outcome: >
      37 metric rows populated, all comment and header lines untouched,
      booleans rendered as lowercase `true`/`false`.
  - need: >
      Capture contains a Nmap-style sweep — one src IP, hundreds of
      distinct destination ports.
    action: >
      Run as normal. `max_outdegree` and `unique_dst_ports` come back
      high; `has_port_scan` flips to `true`; `is_traffic_benign` flips to
      `false`.
    outcome: >
      Flags correctly classify the trace as malicious port-scanning
      traffic without manual override.

anti_patterns:
  - Editing the CSV by hand metric-by-metric. The script writes all 37 in
    one pass and preserves formatting; ad-hoc edits drift the column
    layout and break the grader.
  - Counting ARP packets toward `protocol_ip_total` or assigning them
    src/dst IPs from the ARP payload. `protocol_ip_total` is IPv4 packets
    only; ARP is its own bucket.
  - Including ICMP packets in `unique_src_ports`, `unique_dst_ports`, or
    the port entropies. ICMP has no port fields.
  - Using `log10` instead of `log2` for Shannon entropy. The task spec
    uses bits.
  - Computing `network_density` with the undirected denominator
    `n*(n-1)/2`. The graph is directed; the denominator is `n*(n-1)`.
  - Capitalising the boolean flags (`True`/`False`). The grader expects
    the lowercase strings `true` / `false`.
  - Deleting or reordering `#`-prefixed lines or moving the header.
  - Declaring `is_traffic_benign` true while one of the three suspicious
    flags is true. By construction, `is_traffic_benign = not (port_scan
    or dos or beaconing)`.
  - Re-running the script with different bucket modes "to see which
    answer the grader likes" without inspecting `--dump` first. The
    decisions table tells you which single signal warrants the swap.
```
