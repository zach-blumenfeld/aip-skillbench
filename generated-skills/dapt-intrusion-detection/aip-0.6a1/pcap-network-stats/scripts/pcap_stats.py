#!/usr/bin/env python3
"""Compute network statistics from a PCAP and fill the `value` column of a metric/value CSV.

AIP execution step. Reads one JSON object on stdin:
  {"state": {"pcap_path": str, "stats_csv_path": str}, "assets": {...}, "expects": [...]}
Writes one JSON object on stdout with exactly the step's declared outputs.

Semantics follow the curated pcap-analysis helper (source/pcap-analysis/pcap_utils.py) and the
threat-detection thresholds (source/threat-detection/SKILL.md). Protocol membership uses scapy's
`Layer in pkt` test, exactly as the helper does, so counts match a scapy-based reference.
Packets are streamed with PcapReader (the capture can be tens of MB) and reduced to the few
fields every metric needs, so memory stays small.
"""

import json
import logging
import math
import os
import sys
from collections import Counter, defaultdict

logging.getLogger("scapy.runtime").setLevel(logging.ERROR)
logging.getLogger("scapy.loading").setLevel(logging.ERROR)
logging.getLogger("scapy.interface").setLevel(logging.ERROR)

from scapy.all import ARP, ICMP, IP, TCP, UDP, PcapReader  # noqa: E402

# Detection thresholds: exact values from threat-detection; ALL port-scan conditions must hold.
SCAN_ENTROPY = 6.0        # per-source dst-port entropy, bits, strictly greater
SCAN_SYN_ONLY = 0.7       # per-source SYN-without-ACK ratio, strictly greater
SCAN_UNIQUE_PORTS = 100   # per-source distinct dst ports, strictly greater
SCAN_MIN_PACKETS = 50     # sources with fewer TCP packets are ignored
DOS_RATIO = 20            # ppm_max / ppm_avg strictly greater; 5x-15x is normal variation
BEACON_CV = 0.5           # global IAT coefficient of variation strictly below


def entropy(counter, digits=4):
    """Shannon entropy in bits over observed frequencies (rounded like pcap_utils)."""
    total = sum(counter.values())
    if total == 0:
        return 0.0
    h = 0.0
    for c in counter.values():
        if c > 0:
            p = c / total
            h -= p * math.log2(p)
    return round(h, digits) if digits is not None else h


def sig(x, n=10):
    """Round a float to n significant digits (keeps tiny IAT variances meaningful)."""
    if x == 0 or not math.isfinite(x):
        return x
    return round(x, n - 1 - int(math.floor(math.log10(abs(x)))))


def analyze(pcap_path):
    n_total = 0
    proto = Counter()
    timestamps = []
    sizes_min = None
    sizes_max = None
    total_bytes = 0

    src_ip_c, dst_ip_c = Counter(), Counter()
    src_port_c, dst_port_c = Counter(), Counter()
    edges = set()
    indeg, outdeg = defaultdict(set), defaultdict(set)
    bytes_sent, bytes_recv = defaultdict(int), defaultdict(int)
    flows = set()
    scan_ports = defaultdict(Counter)
    scan_syn_only = defaultdict(int)
    scan_total = defaultdict(int)

    with PcapReader(pcap_path) as reader:
        for pkt in reader:
            n_total += 1
            size = len(pkt)
            total_bytes += size
            sizes_min = size if sizes_min is None else min(sizes_min, size)
            sizes_max = size if sizes_max is None else max(sizes_max, size)
            if hasattr(pkt, "time"):
                timestamps.append(float(pkt.time))

            has_ip = IP in pkt
            has_tcp = TCP in pkt
            has_udp = UDP in pkt
            if has_ip:
                proto["ip"] += 1
            if has_tcp:
                proto["tcp"] += 1
            if has_udp:
                proto["udp"] += 1
            if ICMP in pkt:
                proto["icmp"] += 1
            if ARP in pkt:
                proto["arp"] += 1

            if has_ip:
                ip = pkt[IP]
                src, dst = ip.src, ip.dst
                src_ip_c[src] += 1
                dst_ip_c[dst] += 1
                edges.add((src, dst))
                indeg[dst].add(src)
                outdeg[src].add(dst)
                bytes_sent[src] += size
                bytes_recv[dst] += size

            # Port counters: every TCP packet, but UDP only when it rides on IPv4 (pcap_utils.port_counters).
            if has_tcp:
                t = pkt[TCP]
                src_port_c[t.sport] += 1
                dst_port_c[t.dport] += 1
                if has_ip:
                    flows.add((src, dst, t.sport, t.dport, "TCP"))
                    flags = int(t.flags)
                    scan_ports[src][t.dport] += 1
                    scan_total[src] += 1
                    if flags & 0x02 and not (flags & 0x10):
                        scan_syn_only[src] += 1
            if has_udp and has_ip:
                u = pkt[UDP]
                src_port_c[u.sport] += 1
                dst_port_c[u.dport] += 1
                flows.add((src, dst, u.sport, u.dport, "UDP"))

    if n_total == 0:
        raise SystemExit(f"no packets read from {pcap_path}")

    m = {}
    m["total_packets"] = n_total
    m["protocol_tcp"] = proto["tcp"]
    m["protocol_udp"] = proto["udp"]
    m["protocol_icmp"] = proto["icmp"]
    m["protocol_arp"] = proto["arp"]
    m["protocol_ip_total"] = proto["ip"]
    m["dominant_protocol"] = max(("tcp", "udp", "icmp", "arp"), key=lambda k: proto[k])

    timestamps.sort()
    # Time series: minute buckets offset from the first packet; only non-empty buckets count.
    if len(timestamps) > 1:
        start = timestamps[0]
        buckets = Counter(int((ts - start) / 60) for ts in timestamps)
        ppm = list(buckets.values())
        m["duration_seconds"] = sig(timestamps[-1] - start)
        m["packets_per_minute_avg"] = round(sum(ppm) / len(ppm), 2)
        m["packets_per_minute_max"] = max(ppm)
        m["packets_per_minute_min"] = min(ppm)
        iats = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
        iat_mean = sum(iats) / len(iats)
        iat_var = sum((x - iat_mean) ** 2 for x in iats) / len(iats)  # population variance
        m["iat_mean"] = sig(iat_mean)
        m["iat_variance"] = sig(iat_var)
        m["iat_cv"] = round(math.sqrt(iat_var) / iat_mean, 4) if iat_mean > 0 else 0
    else:
        m["duration_seconds"] = 0
        m["packets_per_minute_avg"] = float(len(timestamps))
        m["packets_per_minute_max"] = len(timestamps)
        m["packets_per_minute_min"] = len(timestamps)
        m["iat_mean"] = 0
        m["iat_variance"] = 0
        m["iat_cv"] = 0

    m["total_bytes"] = total_bytes
    m["avg_packet_size"] = round(total_bytes / n_total, 2)
    m["min_packet_size"] = sizes_min
    m["max_packet_size"] = sizes_max

    m["dst_port_entropy"] = entropy(dst_port_c)
    m["src_port_entropy"] = entropy(src_port_c)
    m["src_ip_entropy"] = entropy(src_ip_c)
    m["dst_ip_entropy"] = entropy(dst_ip_c)
    m["unique_dst_ports"] = len(dst_port_c)
    m["unique_src_ports"] = len(src_port_c)

    nodes = set(indeg) | set(outdeg)
    n_nodes = len(nodes)
    m["num_nodes"] = n_nodes
    m["num_edges"] = len(edges)
    m["network_density"] = round(len(edges) / (n_nodes * (n_nodes - 1)), 6) if n_nodes >= 2 else 0
    # Degree = count of UNIQUE peer IPs, never packets.
    m["max_indegree"] = max((len(v) for v in indeg.values()), default=0)
    m["max_outdegree"] = max((len(v) for v in outdeg.values()), default=0)

    producers = consumers = 0
    for node in nodes:
        sent, recv = bytes_sent.get(node, 0), bytes_recv.get(node, 0)
        if sent + recv > 0:
            pcr = (sent - recv) / (sent + recv)
            if pcr > 0.2:
                producers += 1
            elif pcr < -0.2:
                consumers += 1
    m["num_producers"] = producers
    m["num_consumers"] = consumers

    reverse_hits = sum(1 for (s, d, sp, dp, pr) in flows if (d, s, dp, sp, pr) in flows)
    m["unique_flows"] = len(flows)
    m["tcp_flows"] = sum(1 for f in flows if f[4] == "TCP")
    m["udp_flows"] = sum(1 for f in flows if f[4] == "UDP")
    m["bidirectional_flows"] = reverse_hits // 2  # each A<->B pair is seen from both ends

    # --- detections ---
    scan_sources = []
    best = None
    for s, ports in scan_ports.items():
        total = scan_total[s]
        if total < SCAN_MIN_PACKETS:
            continue
        sig_s = {
            "src": s,
            "tcp_packets": total,
            "port_entropy": entropy(ports),
            "syn_only_ratio": round(scan_syn_only[s] / total, 4),
            "unique_dst_ports": len(ports),
        }
        hit = (sig_s["port_entropy"] > SCAN_ENTROPY and sig_s["syn_only_ratio"] > SCAN_SYN_ONLY
               and sig_s["unique_dst_ports"] > SCAN_UNIQUE_PORTS)
        if hit:
            scan_sources.append(sig_s)
        if best is None or sig_s["unique_dst_ports"] > best["unique_dst_ports"]:
            best = sig_s
    has_port_scan = bool(scan_sources)

    ppm_avg, ppm_max = m["packets_per_minute_avg"], m["packets_per_minute_max"]
    dos_ratio = (ppm_max / ppm_avg) if ppm_avg else 0.0
    has_dos = ppm_avg != 0 and dos_ratio > DOS_RATIO
    # Needs >= 2 inter-arrival gaps: a CV of 0 from 0-1 gaps is not periodicity.
    has_beacon = len(timestamps) > 2 and m["iat_cv"] < BEACON_CV

    m["has_port_scan"] = has_port_scan
    m["has_dos_pattern"] = bool(has_dos)
    m["has_beaconing"] = bool(has_beacon)
    m["is_traffic_benign"] = not (has_port_scan or has_dos or has_beacon)

    evidence = {
        "port_scan": {
            "rule": "any source with >=50 TCP pkts and entropy>6.0 AND syn_only>0.7 AND unique_ports>100",
            "matching_sources": scan_sources[:10],
            "most_port_diverse_source": best,
        },
        "dos": {"rule": "ppm_max/ppm_avg > 20", "ppm_max": ppm_max, "ppm_avg": ppm_avg,
                "ratio": round(dos_ratio, 4)},
        "beaconing": {"rule": "iat_cv < 0.5", "iat_cv": m["iat_cv"]},
        "non_ip_packets": n_total - proto["ip"],
    }
    return m, evidence


def fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return repr(v)
    return str(v)


def fill_csv(csv_path, metrics):
    """Rewrite only the value column; comment lines and the header stay byte-identical."""
    with open(csv_path, newline="") as f:
        lines = f.read().splitlines()
    out, filled, unknown = [], [], []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if i == 0 or not stripped or stripped.startswith("#"):
            out.append(line)
            continue
        name = line.split(",", 1)[0].strip()
        if name in metrics:
            out.append(f"{name},{fmt(metrics[name])}")
            filled.append(name)
        else:
            out.append(line)
            unknown.append(name)
    with open(csv_path, "w", newline="") as f:
        f.write("\n".join(out) + "\n")
    return filled, unknown


def main():
    payload = json.load(sys.stdin)
    state = payload.get("state", {})
    pcap_path = state["pcap_path"]
    csv_path = state["stats_csv_path"]
    for p in (pcap_path, csv_path):
        if not os.path.isfile(p):
            raise SystemExit(f"file not found: {p}")
    metrics, evidence = analyze(pcap_path)
    filled, unknown = fill_csv(csv_path, metrics)
    json.dump({
        "metrics": metrics,
        "detection_evidence": evidence,
        "filled_metrics": filled,
        "unknown_metrics": unknown,
        "template_status": "needs_manual" if unknown else "complete",
    }, sys.stdout)


if __name__ == "__main__":
    main()
