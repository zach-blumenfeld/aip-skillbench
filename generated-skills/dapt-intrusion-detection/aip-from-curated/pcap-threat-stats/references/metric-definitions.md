# PCAP metric definitions and threat thresholds

Exact definitions used by `scripts/analyze_pcap.py`. They match the curated, tested
helpers in `scripts/pcap_utils.py`. Load this file when you must compute or explain a
metric that the script did not fill, or justify a value.

## Reusing the helpers

`scripts/pcap_utils.py` is the curated helper module, copied verbatim. Use it as is
instead of writing your own logic, because it handles the edge cases:

```python
import sys; sys.path.insert(0, '<skill-dir>/scripts')
from pcap_utils import (load_packets, split_by_protocol, graph_metrics,
    detect_port_scan, detect_dos_pattern, detect_beaconing, port_counters,
    ip_counters, iat_stats, flow_metrics, packets_per_minute_stats,
    producer_consumer_counts, shannon_entropy, packet_timestamps)
packets = load_packets('/root/packets.pcap'); parts = split_by_protocol(packets)
```

`load_packets` calls `rdpcap`, which holds every packet in memory. For a large capture,
stream it with `scapy.all.PcapReader` (as analyze_pcap.py does), one packet at a time.

## Layer membership (scapy `Layer in pkt`)

| Set | Rule |
|---|---|
| ip | `IP in p` (IPv4 only; IPv6 packets are NOT in it) |
| tcp / udp / icmp / arp | `TCP in p`, `UDP in p`, `ICMP in p`, `ARP in p` |

- Some packets (ARP, IPv6, link-layer protocols) have no IPv4 layer. Check `IP in p` before you read `p[IP]`.
- UDP can appear without IPv4, e.g. over IPv6 or link-layer protocols. Skip it wherever an IP field is needed.

## Metrics

| Metric | Definition |
|---|---|
| protocol_tcp/udp/icmp/arp | count of packets containing that layer |
| protocol_ip_total | count of packets with an IPv4 layer |
| total_packets | all packets in the capture |
| dominant_protocol | argmax over {tcp, udp, icmp, arp} counts |
| duration_seconds | max(timestamp) − min(timestamp), all packets |
| packets_per_minute_avg/max/min | bucket = int((ts − first_ts)/60). Only non-empty minutes are buckets, so min ≥ 1. avg = mean of bucket counts, rounded to 2 dp |
| total_bytes | Σ len(pkt), the captured frame length, all packets |
| avg_packet_size | total_bytes / total_packets |
| min/max_packet_size | min/max len(pkt), all packets |
| dst_port_entropy / src_port_entropy | Shannon entropy H = −Σ p·log2 p (bits, 4 dp) of a Counter over ALL TCP packets' ports plus UDP packets' ports only when the UDP packet has IPv4 |
| unique_dst_ports / unique_src_ports | distinct keys in those same Counters |
| src_ip_entropy / dst_ip_entropy | entropy of IPv4 src / dst address counts |
| num_nodes | distinct IPv4 addresses appearing as src or dst |
| num_edges | distinct directed (src, dst) pairs |
| network_density | edges / (n·(n−1)) for a directed graph (6 dp) |
| max_indegree | max over nodes of the number of UNIQUE source IPs that sent to it |
| max_outdegree | max over nodes of the number of UNIQUE destination IPs it sent to |
| iat_mean / iat_variance / iat_cv | gaps between sorted timestamps of ALL packets. Variance is the population variance (÷N). cv = std/mean. Rounded to 6, 6, and 4 dp |
| num_producers / num_consumers | per IPv4 node, PCR = (bytes_sent − bytes_recv)/(sent + recv) using len(pkt). Producer if PCR > 0.2, consumer if PCR < −0.2 |
| unique_flows | distinct 5-tuples (src_ip, dst_ip, src_port, dst_port, proto), only from packets with BOTH IPv4 and TCP/UDP |
| tcp_flows / udp_flows | flows by protocol |
| bidirectional_flows | flows whose exact reverse tuple also exists, divided by 2 (each pair is counted once) |

Entropy interpretation: low entropy means traffic focused on a few items (normal). High entropy means traffic spread across many items (scanning).
Interpreting IAT CV: below 0.5 means regular, robotic timing (suspicious). Above 1.0 means bursty, human-like timing (normal).
Interpreting PCR: positive means the node is mostly a producer (server); negative means mostly a consumer (client).

**Common degree mistake:** counting packets instead of unique IPs. With 38 nodes,
max_indegree can be at most 37, not thousands.

## Threat thresholds (exact; any other values give wrong answers)

| Threat | Detected when | |
|---|---|---|
| Port scan | some single IPv4 source with ≥ 50 TCP packets has dst-port entropy > 6.0 AND SYN-only ratio > 0.7 AND unique dst ports > 100 | SYN-only = SYN flag (0x02) set, ACK (0x10) not set |
| DoS | packets_per_minute_max / packets_per_minute_avg > 20 (False if avg is 0) | ratios of 5x, 10x, even 15x are NORMAL variation |
| Beaconing (C2) | iat_cv < 0.5 | |
| Benign | port scan, DoS and beaconing are ALL false | |

If ANY of the three port-scan conditions fails, there is NO port scan. A high port count alone is not a scan:
simple threshold detection fails because legitimate users hit many ports over time, distributed
scans spread across many sources hitting few ports each, and half-open scans never complete the
handshake. Normal traffic repeatedly hits the same ports, which gives a low entropy of about 4–5 bits.

Worked examples:
- 1000 unique ports to one target, port entropy 4.28 bits, SYN-only ratio 0.15 → NOT a port scan.
- ppm_max = 2372, ppm_avg = 262.9 → ratio 9.02 < 20 → NO DoS.

## Writing the CSV

The stats file has a `metric,value` header. Keep rows that start with `#` (section
comments) unchanged and fill the value column of every metric row. Write booleans as
lowercase `true` or `false`.
