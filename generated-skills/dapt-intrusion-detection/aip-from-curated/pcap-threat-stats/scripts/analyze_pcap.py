#!/usr/bin/env python3
"""Compute network statistics and threat verdicts from a PCAP and fill the stats CSV.

AIP execution step. stdin: {"currentState": {...}, "assets": {...}, "expects": [...]}
  currentState.pcap_path   path to the .pcap/.pcapng capture
  currentState.stats_csv   metric,value CSV to fill in place (created from the
                           bundled template if it does not exist)
stdout: one JSON object (metrics, detection_signals, csv_written, unfilled_metrics).

Semantics mirror pcap_utils.py (the curated, tested helpers) exactly, but the
capture is streamed in one pass with scapy's PcapReader instead of rdpcap, so a
large capture does not have to be held in memory as scapy objects.
"""

import csv
import io
import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict

# Thresholds from the threat-detection skill. ALL must hold for a port scan.
PORT_SCAN_ENTROPY = 6.0        # per-source dst-port entropy, bits, strictly greater
PORT_SCAN_SYN_ONLY = 0.7       # per-source SYN-without-ACK ratio, strictly greater
PORT_SCAN_UNIQUE_PORTS = 100   # per-source unique dst ports, strictly greater
PORT_SCAN_MIN_PACKETS = 50     # sources with fewer TCP packets are ignored
DOS_RATIO = 20                 # ppm_max / ppm_avg strictly greater
BEACON_CV = 0.5                # IAT coefficient of variation strictly less
PCR_THRESHOLD = 0.2            # producer if PCR > 0.2, consumer if PCR < -0.2


def fail(msg):
    print(json.dumps({"error": msg}))
    sys.exit(1)


def import_scapy():
    try:
        from scapy.all import ARP, ICMP, IP, TCP, UDP, PcapReader, conf  # noqa: F401
    except ImportError:
        # Bootstrap once if the interpreter lacks scapy (the task container ships 2.5.0).
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "scapy==2.5.0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        try:
            from scapy.all import ARP, ICMP, IP, TCP, UDP, PcapReader, conf  # noqa: F401
        except ImportError:
            fail("scapy is not importable and could not be installed; run with the container's python3 (scapy 2.5.0).")
    from scapy.all import ARP, ICMP, IP, TCP, UDP, PcapReader, conf
    conf.verb = 0
    return ARP, ICMP, IP, TCP, UDP, PcapReader


def shannon_entropy(counter):
    total = sum(counter.values())
    if total == 0:
        return 0.0
    h = 0.0
    for c in counter.values():
        if c > 0:
            p = c / total
            h -= p * math.log2(p)
    return round(h, 4)


def analyze(pcap_path):
    ARP, ICMP, IP, TCP, UDP, PcapReader = import_scapy()

    n_total = n_ip = n_tcp = n_udp = n_icmp = n_arp = 0
    total_bytes = 0
    min_size = None
    max_size = 0
    timestamps = []
    src_ports, dst_ports = Counter(), Counter()
    src_ips, dst_ips = Counter(), Counter()
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
            min_size = size if min_size is None else min(min_size, size)
            max_size = max(max_size, size)
            if hasattr(pkt, "time"):
                timestamps.append(float(pkt.time))

            has_ip = IP in pkt
            has_tcp = TCP in pkt
            has_udp = UDP in pkt
            n_ip += has_ip
            n_tcp += has_tcp
            n_udp += has_udp
            n_icmp += ICMP in pkt
            n_arp += ARP in pkt

            if has_ip:
                ip = pkt[IP]
                s, d = ip.src, ip.dst
                src_ips[s] += 1
                dst_ips[d] += 1
                edges.add((s, d))
                indeg[d].add(s)
                outdeg[s].add(d)
                bytes_sent[s] += size
                bytes_recv[d] += size

            # Port counters: every TCP packet (even without IPv4), UDP only with IPv4.
            if has_tcp:
                t = pkt[TCP]
                sport, dport = t.sport, t.dport
                src_ports[sport] += 1
                dst_ports[dport] += 1
                if has_ip:
                    flows.add((s, d, sport, dport, "TCP"))
                    scan_ports[s][dport] += 1
                    scan_total[s] += 1
                    flags = int(t.flags)
                    if flags & 0x02 and not (flags & 0x10):
                        scan_syn_only[s] += 1
            if has_udp and has_ip:
                u = pkt[UDP]
                src_ports[u.sport] += 1
                dst_ports[u.dport] += 1
                flows.add((s, d, u.sport, u.dport, "UDP"))

    if n_total == 0:
        fail(f"no packets read from {pcap_path}")

    m = {}
    m["total_packets"] = n_total
    m["protocol_tcp"] = n_tcp
    m["protocol_udp"] = n_udp
    m["protocol_icmp"] = n_icmp
    m["protocol_arp"] = n_arp
    m["protocol_ip_total"] = n_ip
    proto = {"tcp": n_tcp, "udp": n_udp, "icmp": n_icmp, "arp": n_arp}
    m["dominant_protocol"] = max(proto, key=proto.get)

    timestamps.sort()
    m["duration_seconds"] = round(timestamps[-1] - timestamps[0], 6) if timestamps else 0.0
    if len(timestamps) > 1:
        start = timestamps[0]
        buckets = defaultdict(int)
        for ts in timestamps:
            buckets[int((ts - start) / 60)] += 1
        ppm = list(buckets.values())  # empty minutes are NOT buckets (curated helper semantics)
        m["packets_per_minute_avg"] = round(sum(ppm) / len(ppm), 2)
        m["packets_per_minute_max"] = max(ppm)
        m["packets_per_minute_min"] = min(ppm)
        iats = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
        iat_mean = sum(iats) / len(iats)
        iat_var = sum((x - iat_mean) ** 2 for x in iats) / len(iats)  # population variance
        m["iat_mean"] = round(iat_mean, 6)
        m["iat_variance"] = round(iat_var, 6)
        m["iat_cv"] = round(math.sqrt(iat_var) / iat_mean, 4) if iat_mean > 0 else 0
    else:
        m["packets_per_minute_avg"] = m["packets_per_minute_max"] = m["packets_per_minute_min"] = len(timestamps)
        m["iat_mean"] = m["iat_variance"] = m["iat_cv"] = 0

    m["total_bytes"] = total_bytes
    m["avg_packet_size"] = round(total_bytes / n_total, 4)
    m["min_packet_size"] = min_size
    m["max_packet_size"] = max_size

    m["dst_port_entropy"] = shannon_entropy(dst_ports)
    m["src_port_entropy"] = shannon_entropy(src_ports)
    m["src_ip_entropy"] = shannon_entropy(src_ips)
    m["dst_ip_entropy"] = shannon_entropy(dst_ips)
    m["unique_dst_ports"] = len(dst_ports)
    m["unique_src_ports"] = len(src_ports)

    nodes = set(indeg) | set(outdeg)
    nn = len(nodes)
    m["num_nodes"] = nn
    m["num_edges"] = len(edges)
    m["network_density"] = round(len(edges) / (nn * (nn - 1) if nn > 1 else 1), 6)
    m["max_indegree"] = max((len(v) for v in indeg.values()), default=0)    # UNIQUE source IPs
    m["max_outdegree"] = max((len(v) for v in outdeg.values()), default=0)  # UNIQUE destination IPs

    producers = consumers = 0
    for node in nodes:
        sent, recv = bytes_sent.get(node, 0), bytes_recv.get(node, 0)
        if sent + recv > 0:
            pcr = (sent - recv) / (sent + recv)
            if pcr > PCR_THRESHOLD:
                producers += 1
            elif pcr < -PCR_THRESHOLD:
                consumers += 1
    m["num_producers"] = producers
    m["num_consumers"] = consumers

    bidir = sum(1 for (a, b, sp, dp, pr) in flows if (b, a, dp, sp, pr) in flows)
    m["unique_flows"] = len(flows)
    m["bidirectional_flows"] = bidir // 2
    m["tcp_flows"] = sum(1 for f in flows if f[4] == "TCP")
    m["udp_flows"] = sum(1 for f in flows if f[4] == "UDP")

    # Port scan: some single source (>= 50 TCP pkts) must meet ALL THREE thresholds.
    has_scan = False
    scan_sources = []
    best = None
    for src, ports in scan_ports.items():
        total = scan_total[src]
        if total < PORT_SCAN_MIN_PACKETS:
            continue
        ent = shannon_entropy(ports)
        syn = scan_syn_only[src] / total
        uniq = len(ports)
        row = {"src": src, "tcp_packets": total, "port_entropy": ent,
               "syn_only_ratio": round(syn, 4), "unique_dst_ports": uniq}
        if ent > PORT_SCAN_ENTROPY and syn > PORT_SCAN_SYN_ONLY and uniq > PORT_SCAN_UNIQUE_PORTS:
            has_scan = True
            scan_sources.append(row)
        if best is None or (uniq, ent) > (best["unique_dst_ports"], best["port_entropy"]):
            best = row

    ppm_avg, ppm_max = m["packets_per_minute_avg"], m["packets_per_minute_max"]
    dos_ratio = (ppm_max / ppm_avg) if ppm_avg else 0.0
    has_dos = bool(ppm_avg) and dos_ratio > DOS_RATIO
    # With <2 timestamps there is no interval to judge; do not call it beaconing.
    has_beacon = len(timestamps) > 1 and m["iat_cv"] < BEACON_CV

    m["has_port_scan"] = has_scan
    m["has_dos_pattern"] = has_dos
    m["has_beaconing"] = has_beacon
    m["is_traffic_benign"] = not (has_scan or has_dos or has_beacon)

    signals = {
        "port_scan": {
            "rule": "some src with >=50 TCP pkts has dst-port entropy > 6.0 AND SYN-only ratio > 0.7 AND unique dst ports > 100",
            "sources_meeting_all_three": scan_sources[:20],
            "most_port_diverse_source": best,
        },
        "dos": {"rule": "packets_per_minute_max / packets_per_minute_avg > 20",
                "ratio": round(dos_ratio, 4)},
        "beaconing": {"rule": "iat_cv < 0.5", "iat_cv": m["iat_cv"]},
        "benign": {"rule": "benign only if port scan, DoS and beaconing are ALL false"},
    }
    return m, signals


def fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def fill_csv(path, metrics, template_text):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, newline="") as f:
            rows = list(csv.reader(f))
    else:
        rows = list(csv.reader(io.StringIO(template_text)))
    out, unfilled, filled = [], [], 0
    for i, row in enumerate(rows):
        if not row:
            out.append(row)
            continue
        key = row[0].strip()
        if i == 0 and key.lower() == "metric":
            out.append(row)
        elif key.startswith("#"):
            out.append(row)  # keep section comments as-is
        elif key in metrics:
            out.append([row[0], fmt(metrics[key])])
            filled += 1
        else:
            out.append(row)
            unfilled.append(key)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(out)
    return filled, unfilled


def main():
    payload = json.load(sys.stdin)
    state = payload.get("currentState", payload)
    assets = payload.get("assets", {}) or {}
    pcap_path = state.get("pcap_path")
    stats_csv = state.get("stats_csv")
    if not pcap_path or not os.path.isfile(pcap_path):
        fail(f"pcap_path not found: {pcap_path!r}")
    if not stats_csv:
        fail("stats_csv is required (the metric,value CSV to fill)")
    template = assets.get("network_stats_template")
    if template is None:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "assets", "network_stats_template.csv")) as f:
            template = f.read()

    metrics, signals = analyze(pcap_path)
    filled, unfilled = fill_csv(stats_csv, metrics, template)
    print(json.dumps({
        "metrics": metrics,
        "detection_signals": signals,
        "csv_written": os.path.abspath(stats_csv),
        "metrics_filled": filled,
        "unfilled_metrics": unfilled,
    }))


if __name__ == "__main__":
    main()
