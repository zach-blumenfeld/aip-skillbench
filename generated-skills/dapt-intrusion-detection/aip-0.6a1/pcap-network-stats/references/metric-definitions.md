# Metric definitions and conventions (pcap-network-stats)

Everything `scripts/pcap_stats.py` computes, so an extra metric can be built in the same style.
Source: source/pcap-analysis/SKILL.md, pcap_utils.py, source/threat-detection/SKILL.md.

## Packet filters (scapy `Layer in pkt`)
- ip = IPv4 (`IP in p`); IPv6-only packets are NOT ip. tcp/udp/icmp/arp counted independently,
  so tcp+udp can exceed ip_total (TCP/UDP over IPv6).
- Packet length = `len(pkt)` (captured bytes). Timestamps = `float(pkt.time)`, sorted.

## Counts, sizes, time
- total_packets, protocol_* counts, total_bytes, avg/min/max packet size (avg rounded 2 dp).
- duration_seconds = last - first timestamp.
- packets_per_minute: bucket = int((ts - first_ts) / 60); only non-empty buckets; avg (2 dp), max, min.
- IAT over sorted timestamps: mean, population variance (divide by n), cv = std/mean (4 dp; 0 if mean 0).

## Entropy (bits, log2, 4 dp)
- src/dst IP entropy over IPv4 packets.
- src/dst port entropy over ALL TCP packets plus UDP packets that carry IPv4 (pcap_utils.port_counters).
- unique_src_ports / unique_dst_ports = distinct keys of those same counters.

## Graph (IPv4 only)
- nodes = distinct src or dst IPs; edges = distinct (src, dst).
- density = edges / (n*(n-1)), 6 dp, 0 when n < 2.
- max_indegree / max_outdegree = most UNIQUE peer IPs, never packet counts (bounded by n-1).

## Producer/consumer
- per IP: sent = bytes as src, recv = bytes as dst; PCR = (sent-recv)/(sent+recv), skip if 0.
- producer PCR > 0.2, consumer PCR < -0.2.

## Flows (packets with IPv4 AND TCP/UDP)
- key (src_ip, dst_ip, sport, dport, "TCP"|"UDP"); unique_flows, tcp_flows, udp_flows.
- bidirectional_flows = (flows whose reverse key exists) // 2, i.e. the number of A<->B pairs.

## Detection flags (exact thresholds; all comparisons strict)
- has_port_scan: some source with >= 50 TCP packets has dst-port entropy > 6.0 AND SYN-only
  (SYN set, ACK clear) ratio > 0.7 AND > 100 unique dst ports. Any condition failing = no scan.
  Many ports alone is normal service traffic (e.g. 1000 ports, entropy 4.28, SYN ratio 0.15 = not a scan).
- has_dos_pattern: ppm_max / ppm_avg > 20 (false if avg is 0). 5x, 10x, 15x are normal variation.
- has_beaconing: iat_cv < 0.5 (and at least 2 IAT gaps). Low CV = robotic regular timing; CV > 1.0 = bursty/human.
- is_traffic_benign: true only when all three flags are false.
- dominant_protocol (scripted, used only if the template asks) = argmax of tcp/udp/icmp/arp counts.
