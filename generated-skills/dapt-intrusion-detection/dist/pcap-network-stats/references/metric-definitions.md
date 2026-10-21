# Metric definitions (what `scripts/pcap_stats.py` computes, and how to hand-compute a row it does not know)

All parsing uses scapy dissection; a packet "has" a protocol when `Layer in pkt` is true
(`IP` means IPv4 only; IPv6 packets are not IP here). Packet size is `len(pkt)` (captured bytes).

## Protocol counts
- `protocol_tcp/udp/icmp/arp` = packets with `TCP/UDP/ICMP/ARP in pkt`. Counts may overlap; do not force
  mutually exclusive categories. IPv6 UDP still counts toward `protocol_udp`.
- `protocol_ip_total` = packets with `IP in pkt`.
- Dominant protocol (if ever asked) = the max of the four counts.

## Time series
- Timestamps `float(pkt.time)`, sorted. `duration_seconds = last - first`.
- Minute buckets: `int((ts - first) / 60)`; only buckets that received packets exist (an empty minute is
  not a zero bucket). avg/max/min are over those bucket counts.

## Sizes
- `total_bytes = sum(len(p))`, `avg = total/packets`, `min`, `max` over all packets (ARP included).

## Entropy (Shannon, bits): H = -Σ p·log2 p over observed frequencies
- Ports: every TCP packet's sport/dport + UDP packets **that have IPv4** (UDP without IPv4 is skipped).
- IPs: IPv4 packets' src / dst.
- `unique_src_ports / unique_dst_ports` = distinct keys of those same port counters.
- Low entropy = traffic focused on few items (normal, ~4-5 bits for ports); high = spread (scanning).

## Graph (directed, IPv4 only)
- Nodes = distinct src ∪ dst IPs; edges = distinct (src, dst) pairs.
- `network_density = edges / (n·(n-1))`, 0 if n < 2.
- Degree = number of **UNIQUE peer IPs**, never packet counts: `max_indegree` = most distinct sources
  seen by one destination; `max_outdegree` = most distinct destinations contacted by one source.
  Sanity check: with 38 nodes the max degree is at most 37 — a value in the thousands means packets were counted.

## Temporal
- IAT = consecutive differences of the sorted timestamps (all packets). Mean, **population** variance
  (divide by N), `cv = std/mean` (0 if mean = 0). Low CV (< 0.5) = regular/robotic; high (> 1.0) = bursty/human.
- PCR per IPv4 node: `(sent - recv)/(sent + recv)` from byte totals as src/dst; skip if total 0.
  Producer: PCR > 0.2 (server-like). Consumer: PCR < -0.2 (client-like). Others are balanced.

## Flows
- Key (src_ip, dst_ip, src_port, dst_port, proto) from packets with BOTH IPv4 and TCP/UDP.
- `tcp_flows/udp_flows` = keys per protocol; `unique_flows` = all keys.
- `bidirectional_flows`: three conventions exist; the script reports all three in
  `diagnostics.bidirectional_variants` and writes the one chosen by decision `bidir_mode`:
  - `conversations` — map every flow and its reverse to one canonical key, count the distinct set
    (one-way flows included). The DAPT2020 network-stats reference extractor uses this.
  - `pairs` — flows whose reverse exists, divided by 2 (each A↔B pair once). The source helper uses this.
  - `flows_with_reverse` — flows whose reverse exists, not halved.

## Threat flags (strict, calibrated thresholds; do not tune them by eye)
| Flag | Rule |
|------|------|
| `has_port_scan` | For some IPv4 source with ≥ 50 TCP packets: dst-port entropy > 6.0 **and** SYN-only ratio (SYN set, ACK clear) > 0.7 **and** unique dst ports > 100. Any condition missing → no scan. |
| `has_dos_pattern` | `packets_per_minute_max / packets_per_minute_avg > 20` (avg 0 → false). 5x, 10x, even 15x is normal variation. |
| `has_beaconing` | global `iat_cv < 0.5`. |
| `is_traffic_benign` | true only when all three flags above are false. |

Why the three-signal scan rule: a simple unique-port threshold misfires — legitimate clients hit many
ports over time, distributed scans spread over many sources, and half-open scans never complete the
handshake. Example: 1000 unique ports to one target with port entropy 4.28 and SYN-only 0.15 is normal
service traffic, not a scan. DoS example: ppm_max 2372 / ppm_avg 262.9 = 9.02 → no DoS.

## Writing the CSV by hand (only if the script cannot)
Keep the header and every `#` line unchanged; write `metric,value`; booleans lowercase `true/false`.
Round like the script: entropy 4 dp, density 6 dp, ppm avg 2 dp, avg size 2 dp, IAT mean/variance 6 dp, CV 4 dp.
