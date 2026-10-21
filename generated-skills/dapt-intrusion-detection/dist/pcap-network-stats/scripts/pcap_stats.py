#!/usr/bin/env python3
"""Compute network statistics + threat flags from a PCAP and fill a metric,value CSV.

Requires: Python >= 3.8, scapy (tested with scapy==2.5.0). Standard library otherwise.

Usage:
    python3 scripts/pcap_stats.py --pcap /root/packets.pcap --csv /root/network_stats.csv
    python3 scripts/pcap_stats.py --pcap /root/packets.pcap            # print only, write nothing

One streaming pass over the capture (scapy PcapReader, so large files do not need
to fit in memory). Prints a JSON object {"metrics": {...}, "diagnostics": {...}}.
With --csv, fills the `value` column of every known metric row in place, keeps
'#' comment lines and the header byte-for-byte, then re-reads the file and exits 2
if any non-comment row is still empty.

Definitions follow the pcap-analysis / threat-detection source skills exactly
(protocol membership via scapy `Layer in pkt`, packet size = len(pkt), etc.).
"""

import argparse
import json
import math
import os
import sys
import tempfile
from collections import Counter, defaultdict

try:
    from scapy.all import ARP, ICMP, IP, TCP, UDP, PcapReader, conf
except ImportError:  # pragma: no cover
    sys.exit("ERROR: scapy is not installed. Install it (pip install scapy) or use the task image, which ships scapy==2.5.0.")

conf.verb = 0


def shannon_entropy(counter):
    """H = -sum p*log2(p) over observed frequencies, in bits."""
    total = sum(counter.values())
    if total == 0:
        return 0.0
    h = 0.0
    for c in counter.values():
        if c > 0:
            p = c / total
            h -= p * math.log2(p)
    return h


def analyze(pcap_path, args):
    n_pkts = 0
    proto = Counter()
    sizes_total = 0
    size_min = None
    size_max = None
    timestamps = []

    src_ip_c, dst_ip_c = Counter(), Counter()
    src_port_c, dst_port_c = Counter(), Counter()
    edges = set()
    indeg = defaultdict(set)
    outdeg = defaultdict(set)
    bytes_sent = defaultdict(int)
    bytes_recv = defaultdict(int)
    flows = set()

    # port-scan signals, per IPv4 source (TCP only)
    scan_ports = defaultdict(Counter)
    scan_syn_only = defaultdict(int)
    scan_total = defaultdict(int)

    udp_without_ipv4 = 0
    tcp_without_ipv4 = 0

    with PcapReader(pcap_path) as reader:
        for pkt in reader:
            n_pkts += 1
            size = len(pkt)
            sizes_total += size
            size_min = size if size_min is None or size < size_min else size_min
            size_max = size if size_max is None or size > size_max else size_max
            timestamps.append(float(pkt.time))

            has_ip = IP in pkt
            has_tcp = TCP in pkt
            has_udp = UDP in pkt
            if has_tcp:
                proto["tcp"] += 1
            if has_udp:
                proto["udp"] += 1
            if ICMP in pkt:
                proto["icmp"] += 1
            if ARP in pkt:
                proto["arp"] += 1

            # Ports: every TCP packet; UDP only when an IPv4 layer exists (source rule).
            if has_tcp:
                t = pkt[TCP]
                src_port_c[t.sport] += 1
                dst_port_c[t.dport] += 1
                if not has_ip:
                    tcp_without_ipv4 += 1
            if has_udp:
                if has_ip:
                    u = pkt[UDP]
                    src_port_c[u.sport] += 1
                    dst_port_c[u.dport] += 1
                else:
                    udp_without_ipv4 += 1

            if not has_ip:
                continue
            proto["ip"] += 1
            ip = pkt[IP]
            s, d = ip.src, ip.dst
            src_ip_c[s] += 1
            dst_ip_c[d] += 1
            edges.add((s, d))
            indeg[d].add(s)
            outdeg[s].add(d)
            bytes_sent[s] += size
            bytes_recv[d] += size

            # Flows need BOTH IPv4 and a transport layer.
            if has_tcp:
                t = pkt[TCP]
                flows.add((s, d, t.sport, t.dport, "TCP"))
                flags = int(t.flags)
                scan_ports[s][t.dport] += 1
                scan_total[s] += 1
                if flags & 0x02 and not flags & 0x10:  # SYN without ACK
                    scan_syn_only[s] += 1
            if has_udp:
                u = pkt[UDP]
                flows.add((s, d, u.sport, u.dport, "UDP"))

    if n_pkts == 0:
        sys.exit(f"ERROR: {pcap_path} contains no packets; nothing to compute.")

    m = {}
    m["total_packets"] = n_pkts
    m["protocol_tcp"] = proto["tcp"]
    m["protocol_udp"] = proto["udp"]
    m["protocol_icmp"] = proto["icmp"]
    m["protocol_arp"] = proto["arp"]
    m["protocol_ip_total"] = proto["ip"]
    counts4 = {k: proto[k] for k in ("tcp", "udp", "icmp", "arp")}
    m["dominant_protocol"] = max(counts4, key=counts4.get)

    # ---- time series: sort by timestamp; 60 s buckets from the first packet; only non-empty buckets count
    timestamps.sort()
    t0, t1 = timestamps[0], timestamps[-1]
    m["duration_seconds"] = t1 - t0
    buckets = Counter(int((ts - t0) / 60) for ts in timestamps)
    ppm = list(buckets.values())
    m["packets_per_minute_avg"] = sum(ppm) / len(ppm)
    m["packets_per_minute_max"] = max(ppm)
    m["packets_per_minute_min"] = min(ppm)

    # ---- sizes
    m["total_bytes"] = sizes_total
    m["avg_packet_size"] = sizes_total / n_pkts
    m["min_packet_size"] = size_min
    m["max_packet_size"] = size_max

    # ---- entropy
    m["dst_port_entropy"] = shannon_entropy(dst_port_c)
    m["src_port_entropy"] = shannon_entropy(src_port_c)
    m["src_ip_entropy"] = shannon_entropy(src_ip_c)
    m["dst_ip_entropy"] = shannon_entropy(dst_ip_c)
    m["unique_dst_ports"] = len(dst_port_c)
    m["unique_src_ports"] = len(src_port_c)

    # ---- graph (degree = UNIQUE peer IPs, never packet counts)
    nodes = set(indeg) | set(outdeg)
    nn = len(nodes)
    m["num_nodes"] = nn
    m["num_edges"] = len(edges)
    m["network_density"] = len(edges) / (nn * (nn - 1)) if nn >= 2 else 0.0
    m["max_indegree"] = max((len(v) for v in indeg.values()), default=0)
    m["max_outdegree"] = max((len(v) for v in outdeg.values()), default=0)

    # ---- inter-arrival times (population variance)
    if len(timestamps) > 1:
        iats = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
        mean = sum(iats) / len(iats)
        var = sum((x - mean) ** 2 for x in iats) / len(iats)
        cv = math.sqrt(var) / mean if mean > 0 else 0.0
    else:
        mean = var = cv = 0.0
    m["iat_mean"] = mean
    m["iat_variance"] = var
    m["iat_cv"] = cv

    # ---- producer / consumer ratio
    producers = consumers = 0
    for node in nodes:
        sent, recv = bytes_sent.get(node, 0), bytes_recv.get(node, 0)
        tot = sent + recv
        if tot == 0:
            continue
        pcr = (sent - recv) / tot
        if pcr > 0.2:
            producers += 1
        elif pcr < -0.2:
            consumers += 1
    m["num_producers"] = producers
    m["num_consumers"] = consumers

    # ---- flows
    with_reverse = sum(1 for (s, d, sp, dp, pr) in flows if (d, s, dp, sp, pr) in flows)
    conversations = len({tuple(sorted([f, (f[1], f[0], f[3], f[2], f[4])])) for f in flows})
    bidir_variants = {
        "conversations": conversations,          # flow + reverse canonicalised, distinct set (one-way included)
        "pairs": with_reverse // 2,              # two-way pairs counted once (source pcap_utils rule)
        "flows_with_reverse": with_reverse,      # each directional flow whose reverse key exists
    }
    m["unique_flows"] = len(flows)
    m["bidirectional_flows"] = bidir_variants[args.bidir]
    m["tcp_flows"] = sum(1 for f in flows if f[4] == "TCP")
    m["udp_flows"] = sum(1 for f in flows if f[4] == "UDP")

    # ---- threat flags (strict thresholds; ALL port-scan conditions must hold for one source)
    scan_candidates = []
    has_scan = False
    for src, ports in scan_ports.items():
        total = scan_total[src]
        if total < args.scan_min_packets:
            continue
        ent = round(shannon_entropy(ports), 4)
        syn_ratio = scan_syn_only[src] / total
        uniq = len(ports)
        hit = ent > args.scan_entropy and syn_ratio > args.scan_syn_ratio and uniq > args.scan_unique_ports
        has_scan = has_scan or hit
        scan_candidates.append({"src": src, "tcp_packets": total, "port_entropy": ent,
                                "syn_only_ratio": round(syn_ratio, 4), "unique_dst_ports": uniq, "meets_all": hit})
    scan_candidates.sort(key=lambda c: (c["meets_all"], c["unique_dst_ports"]), reverse=True)

    ppm_avg_r = round(m["packets_per_minute_avg"], 2)
    dos_ratio = m["packets_per_minute_max"] / ppm_avg_r if ppm_avg_r else 0.0
    has_dos = ppm_avg_r > 0 and dos_ratio > args.dos_ratio
    # CV needs >= 2 inter-arrival gaps to mean anything; a 1-2 packet capture is not beaconing.
    has_beacon = len(timestamps) >= 3 and round(cv, 4) < args.beacon_cv
    m["is_traffic_benign"] = not (has_scan or has_dos or has_beacon)
    m["has_port_scan"] = has_scan
    m["has_dos_pattern"] = has_dos
    m["has_beaconing"] = has_beacon

    diag = {
        "total_packets": n_pkts,
        "non_ipv4_packets": n_pkts - proto["ip"],
        "udp_without_ipv4_excluded_from_ports_and_flows": udp_without_ipv4,
        "tcp_without_ipv4_excluded_from_flows": tcp_without_ipv4,
        "minute_buckets_nonempty": len(ppm),
        "minute_buckets_span": max(buckets) + 1,
        "ppm_max_over_avg_ratio": round(dos_ratio, 4),
        "bidirectional_variants": bidir_variants,
        "bidirectional_mode_used": args.bidir,
        "port_scan_top_candidates": scan_candidates[:5],
        "port_scan_sources_considered": len(scan_candidates),
        "thresholds": {"scan_entropy_gt": args.scan_entropy, "scan_syn_only_ratio_gt": args.scan_syn_ratio,
                       "scan_unique_ports_gt": args.scan_unique_ports, "scan_min_packets": args.scan_min_packets,
                       "dos_ppm_ratio_gt": args.dos_ratio, "beacon_iat_cv_lt": args.beacon_cv},
    }
    return m, diag


# Decimal places per metric (source helper conventions). Integers/booleans are written as-is.
ROUNDING = {
    "duration_seconds": 6, "packets_per_minute_avg": 2, "avg_packet_size": 2,
    "dst_port_entropy": 4, "src_port_entropy": 4, "src_ip_entropy": 4, "dst_ip_entropy": 4,
    "network_density": 6, "iat_mean": 6, "iat_variance": 6, "iat_cv": 4,
}


def fmt(name, value):
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    dp = ROUNDING.get(name, 6)
    r = round(value, dp)
    # Never let rounding wipe out a small non-zero value: fall back to 6 significant digits.
    if value != 0 and (r == 0 or abs(r - value) / abs(value) > 0.005):
        return f"{value:.6g}"
    return repr(r)


def fill_csv(path, values):
    with open(path, "r", newline="") as f:
        lines = f.read().splitlines(keepends=True)
    out, filled, unknown = [], [], []
    for i, line in enumerate(lines):
        body = line.rstrip("\r\n")
        eol = line[len(body):]
        stripped = body.strip()
        if i == 0 or not stripped or stripped.startswith("#"):
            out.append(line)  # header, blanks, comments untouched
            continue
        metric = body.split(",", 1)[0].strip()
        if metric in values:
            out.append(f"{metric},{values[metric]}{eol}")
            filled.append(metric)
        else:
            out.append(line)
            unknown.append(metric)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)) or ".")
    with os.fdopen(fd, "w", newline="") as f:
        f.writelines(out)
    os.replace(tmp, path)
    return filled, unknown


def validate_csv(path):
    empty = []
    with open(path, newline="") as f:
        for i, line in enumerate(f):
            s = line.strip()
            if i == 0 or not s or s.startswith("#"):
                continue
            parts = s.split(",", 1)
            if len(parts) < 2 or parts[1].strip() == "":
                empty.append(parts[0])
    return empty


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcap", required=True, help="capture file (pcap/pcapng)")
    ap.add_argument("--csv", help="metric,value CSV to fill in place (e.g. /root/network_stats.csv)")
    ap.add_argument("--json", help="also write the full JSON result here")
    ap.add_argument("--bidir", choices=["pairs", "flows_with_reverse", "conversations"], default="conversations",
                    help="bidirectional_flows definition (SKILL.md decision 'bidir_mode'); default conversations")
    ap.add_argument("--scan-entropy", type=float, default=6.0)
    ap.add_argument("--scan-syn-ratio", type=float, default=0.7)
    ap.add_argument("--scan-unique-ports", type=int, default=100)
    ap.add_argument("--scan-min-packets", type=int, default=50)
    ap.add_argument("--dos-ratio", type=float, default=20.0)
    ap.add_argument("--beacon-cv", type=float, default=0.5)
    args = ap.parse_args()

    if not os.path.isfile(args.pcap):
        sys.exit(f"ERROR: pcap not found: {args.pcap}")
    if args.csv and not os.path.isfile(args.csv):
        sys.exit(f"ERROR: CSV not found: {args.csv} (the task image copies the template there)")

    metrics, diag = analyze(args.pcap, args)
    formatted = {k: fmt(k, v) for k, v in metrics.items()}
    result = {"metrics": formatted, "diagnostics": diag}

    if args.csv:
        filled, unknown = fill_csv(args.csv, formatted)
        result["csv"] = {"path": args.csv, "filled": len(filled), "rows_not_known_to_script": unknown,
                         "empty_after_write": validate_csv(args.csv)}

    text = json.dumps(result, indent=2)
    print(text)
    if args.json:
        with open(args.json, "w") as f:
            f.write(text + "\n")
    if args.csv and result["csv"]["empty_after_write"]:
        print(f"ERROR: rows still empty in {args.csv}: {result['csv']['empty_after_write']} "
              "- compute them per the task statement and fill them by hand.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
