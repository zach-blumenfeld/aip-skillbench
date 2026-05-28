#!/usr/bin/env python3
"""Compute DAPT-style network statistics from a pcap and fill a CSV value column.

Usage:
    python compute_stats.py --pcap packets.pcap --csv /root/network_stats.csv
    python compute_stats.py --pcap packets.pcap --dump      # print metrics, do not write
    python compute_stats.py --pcap packets.pcap --csv ... --bucket-mode empty-included

Reads `packets.pcap` with scapy, computes the metric set described in the task
(protocol counts, rate, sizes, entropy, IP graph, IAT, PCR, 5-tuple flows,
heuristic intrusion-detection flags), then rewrites only the `value` column of
the target CSV. Lines beginning with `#` and the header row are preserved
verbatim. Rows whose metric name is not in the computed set are left untouched.

Dependencies: scapy. Install with `pip install scapy` if missing.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from io import StringIO
from pathlib import Path


def _import_scapy():
    try:
        from scapy.all import ARP, ICMP, IP, TCP, UDP, rdpcap  # noqa: F401
    except ImportError as exc:
        sys.stderr.write(
            "ERROR: scapy is required. Install with `pip install scapy`.\n"
            f"Underlying import error: {exc}\n"
        )
        sys.exit(2)
    return rdpcap, IP, TCP, UDP, ICMP, ARP


def shannon_entropy(counts) -> float:
    """Shannon entropy (bits) over an iterable/Counter of counts. Skips zeros."""
    total = sum(counts.values()) if isinstance(counts, dict) else sum(counts)
    if total <= 0:
        return 0.0
    values = counts.values() if isinstance(counts, dict) else counts
    h = 0.0
    for c in values:
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log2(p)
    return h


def compute_stats(pcap_path: str, bucket_mode: str = "non-empty") -> dict:
    rdpcap, IP, TCP, UDP, ICMP, ARP = _import_scapy()
    packets = rdpcap(pcap_path)

    tcp_count = udp_count = icmp_count = arp_count = ip_count = 0
    sizes: list[int] = []
    timestamps: list[float] = []

    src_ips: Counter = Counter()
    dst_ips: Counter = Counter()
    src_ports: Counter = Counter()
    dst_ports: Counter = Counter()

    edges: set[tuple[str, str]] = set()
    out_neighbors: dict[str, set[str]] = defaultdict(set)
    in_neighbors: dict[str, set[str]] = defaultdict(set)
    all_nodes: set[str] = set()

    bytes_sent: dict[str, int] = defaultdict(int)
    bytes_recv: dict[str, int] = defaultdict(int)

    flow_keys: set[tuple] = set()
    tcp_flow_keys: set[tuple] = set()
    udp_flow_keys: set[tuple] = set()

    src_to_dst_ports: dict[str, set[int]] = defaultdict(set)

    for pkt in packets:
        size = len(pkt)
        sizes.append(size)
        timestamps.append(float(pkt.time))

        if pkt.haslayer(ARP):
            arp_count += 1

        if not pkt.haslayer(IP):
            continue

        ip_count += 1
        ip_layer = pkt[IP]
        src = ip_layer.src
        dst = ip_layer.dst

        src_ips[src] += 1
        dst_ips[dst] += 1
        edges.add((src, dst))
        out_neighbors[src].add(dst)
        in_neighbors[dst].add(src)
        all_nodes.add(src)
        all_nodes.add(dst)
        bytes_sent[src] += size
        bytes_recv[dst] += size

        proto_name = None
        sport = dport = None
        if pkt.haslayer(TCP):
            tcp_count += 1
            sport = int(pkt[TCP].sport)
            dport = int(pkt[TCP].dport)
            proto_name = "TCP"
        elif pkt.haslayer(UDP):
            udp_count += 1
            sport = int(pkt[UDP].sport)
            dport = int(pkt[UDP].dport)
            proto_name = "UDP"
        elif pkt.haslayer(ICMP):
            icmp_count += 1
            proto_name = "ICMP"

        if sport is not None:
            src_ports[sport] += 1
        if dport is not None:
            dst_ports[dport] += 1
            src_to_dst_ports[src].add(dport)

        if proto_name in ("TCP", "UDP"):
            key = (src, dst, sport, dport, proto_name)
            flow_keys.add(key)
            (tcp_flow_keys if proto_name == "TCP" else udp_flow_keys).add(key)
        elif proto_name == "ICMP":
            flow_keys.add((src, dst, None, None, "ICMP"))

    n = len(packets)

    if timestamps:
        ts_sorted = sorted(timestamps)
        duration = ts_sorted[-1] - ts_sorted[0]
        t0 = ts_sorted[0]
        bucket_counts: Counter = Counter()
        for t in ts_sorted:
            bucket_counts[int((t - t0) // 60)] += 1
        if bucket_mode == "empty-included" and duration > 0:
            last_b = int(duration // 60)
            for b in range(last_b + 1):
                bucket_counts.setdefault(b, 0)
        counts = list(bucket_counts.values())
        ppm_avg = sum(counts) / len(counts) if counts else 0.0
        ppm_max = max(counts) if counts else 0
        ppm_min = min(counts) if counts else 0
    else:
        duration = 0.0
        ppm_avg = 0.0
        ppm_max = 0
        ppm_min = 0
        ts_sorted = []

    total_bytes = sum(sizes)
    avg_size = (total_bytes / n) if n else 0.0
    min_size = min(sizes) if sizes else 0
    max_size = max(sizes) if sizes else 0

    src_ip_ent = shannon_entropy(src_ips)
    dst_ip_ent = shannon_entropy(dst_ips)
    src_port_ent = shannon_entropy(src_ports)
    dst_port_ent = shannon_entropy(dst_ports)

    num_nodes = len(all_nodes)
    num_edges = len(edges)
    density = (num_edges / (num_nodes * (num_nodes - 1))) if num_nodes >= 2 else 0.0
    max_out = max((len(v) for v in out_neighbors.values()), default=0)
    max_in = max((len(v) for v in in_neighbors.values()), default=0)

    iats = [ts_sorted[i + 1] - ts_sorted[i] for i in range(len(ts_sorted) - 1)]
    if iats:
        iat_mean = sum(iats) / len(iats)
        iat_var = sum((x - iat_mean) ** 2 for x in iats) / len(iats)
        iat_std = math.sqrt(iat_var)
        iat_cv = (iat_std / iat_mean) if iat_mean else 0.0
    else:
        iat_mean = iat_var = iat_cv = 0.0

    num_producers = num_consumers = 0
    for ip in set(bytes_sent) | set(bytes_recv):
        s = bytes_sent.get(ip, 0)
        r = bytes_recv.get(ip, 0)
        denom = s + r
        if denom == 0:
            continue
        pcr = (s - r) / denom
        if pcr > 0.2:
            num_producers += 1
        elif pcr < -0.2:
            num_consumers += 1

    bidirectional = 0
    for key in flow_keys:
        s, d, sp, dp, p = key
        if (d, s, dp, sp, p) in flow_keys:
            bidirectional += 1

    max_unique_dst_ports_per_src = max(
        (len(v) for v in src_to_dst_ports.values()), default=0
    )
    has_port_scan = max_unique_dst_ports_per_src >= 100 or (
        dst_port_ent >= 6.0 and dst_ip_ent <= 2.0 and len(dst_ports) >= 50
    )
    has_dos_pattern = bool(
        ppm_avg
        and ppm_max >= 5 * ppm_avg
        and ppm_max >= 1000
    )
    has_beaconing = bool(
        iat_cv and iat_cv < 0.3 and len(iats) >= 50
    )
    is_benign = not (has_port_scan or has_dos_pattern or has_beaconing)

    return {
        "protocol_tcp": tcp_count,
        "protocol_udp": udp_count,
        "protocol_icmp": icmp_count,
        "protocol_arp": arp_count,
        "protocol_ip_total": ip_count,
        "duration_seconds": duration,
        "packets_per_minute_avg": ppm_avg,
        "packets_per_minute_max": ppm_max,
        "packets_per_minute_min": ppm_min,
        "total_bytes": total_bytes,
        "avg_packet_size": avg_size,
        "min_packet_size": min_size,
        "max_packet_size": max_size,
        "src_ip_entropy": src_ip_ent,
        "dst_ip_entropy": dst_ip_ent,
        "src_port_entropy": src_port_ent,
        "dst_port_entropy": dst_port_ent,
        "unique_src_ports": len(src_ports),
        "unique_dst_ports": len(dst_ports),
        "num_nodes": num_nodes,
        "num_edges": num_edges,
        "network_density": density,
        "max_outdegree": max_out,
        "max_indegree": max_in,
        "iat_mean": iat_mean,
        "iat_variance": iat_var,
        "iat_cv": iat_cv,
        "num_producers": num_producers,
        "num_consumers": num_consumers,
        "unique_flows": len(flow_keys),
        "tcp_flows": len(tcp_flow_keys),
        "udp_flows": len(udp_flow_keys),
        "bidirectional_flows": bidirectional,
        "is_traffic_benign": is_benign,
        "has_port_scan": has_port_scan,
        "has_dos_pattern": has_dos_pattern,
        "has_beaconing": has_beaconing,
    }


def _format_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isfinite(v) and v == int(v) and abs(v) < 1e15:
            return f"{int(v)}"
        return f"{v:.6f}"
    return str(v)


def update_csv(csv_path: str, stats: dict) -> int:
    text = Path(csv_path).read_text()
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()

    out: list[str] = []
    header_seen = False
    metric_idx = 0
    value_idx = 1
    updates = 0

    for line in lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue

        row = next(csv.reader([line]))
        if not header_seen:
            cols = [c.strip().lower() for c in row]
            if "value" in cols:
                value_idx = cols.index("value")
            if "metric" in cols:
                metric_idx = cols.index("metric")
            elif "name" in cols:
                metric_idx = cols.index("name")
            header_seen = True
            out.append(line)
            continue

        if metric_idx >= len(row) or value_idx >= len(row):
            out.append(line)
            continue

        metric = row[metric_idx].strip()
        if metric in stats:
            row[value_idx] = _format_value(stats[metric])
            updates += 1

        buf = StringIO()
        csv.writer(buf, lineterminator="").writerow(row)
        out.append(buf.getvalue())

    Path(csv_path).write_text(eol.join(out) + eol)
    return updates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pcap", required=True, help="path to packets.pcap")
    ap.add_argument(
        "--csv",
        default="/root/network_stats.csv",
        help="path to the CSV whose `value` column will be filled",
    )
    ap.add_argument(
        "--dump",
        action="store_true",
        help="print computed metrics to stdout instead of writing the CSV",
    )
    ap.add_argument(
        "--bucket-mode",
        choices=("non-empty", "empty-included"),
        default="non-empty",
        help=(
            "how to count 60s buckets for packets_per_minute: "
            "`non-empty` (default) counts only buckets that contain packets; "
            "`empty-included` includes zero-count buckets in the time range"
        ),
    )
    args = ap.parse_args()

    stats = compute_stats(args.pcap, bucket_mode=args.bucket_mode)

    if args.dump:
        width = max(len(k) for k in stats)
        for k, v in stats.items():
            print(f"{k.ljust(width)}  {_format_value(v)}")
        return 0

    updated = update_csv(args.csv, stats)
    print(f"Updated {updated} value cell(s) in {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
