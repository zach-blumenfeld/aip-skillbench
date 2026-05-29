#!/usr/bin/env python3
"""
End-to-end PCAP stats computer for the DAPT intrusion-detection task.

Calls `pcap_utils.py` for every per-domain helper (entropy, graph, IAT,
producer/consumer, flow, detectors) and returns one flat dict keyed by
the exact `metric` strings in `network_stats_template.csv`.

Boolean detection flags use the strict, calibrated thresholds in
`pcap_utils.py` (entropy > 6.0, SYN-only > 0.7, unique ports > 100,
max/avg PPM > 20, IAT CV < 0.5) — do not loosen these or fabricate
your own.

CLI:
    python compute_all_stats.py <pcap_path> [--json | --csv-template <path>]

Library:
    from compute_all_stats import compute_all_stats
    stats = compute_all_stats('/root/packets.pcap')
"""

import argparse
import csv
import json
import math
import sys
from collections import Counter

from scapy.all import ARP, ICMP, IP, TCP, UDP

from pcap_utils import (
    detect_beaconing,
    detect_dos_pattern,
    detect_port_scan,
    flow_metrics,
    graph_metrics,
    iat_stats,
    ip_counters,
    load_packets,
    packet_timestamps,
    packets_per_minute_stats,
    port_counters,
    producer_consumer_counts,
    shannon_entropy,
    split_by_protocol,
)


def compute_all_stats(pcap_path: str) -> dict:
    """Compute every metric in network_stats_template.csv from a PCAP."""
    packets = load_packets(pcap_path)
    parts = split_by_protocol(packets)
    ip_pkts, tcp_pkts, udp_pkts, icmp_pkts, arp_pkts = (
        parts["ip"],
        parts["tcp"],
        parts["udp"],
        parts["icmp"],
        parts["arp"],
    )

    stats: dict = {}

    # Protocol distribution: packets containing each protocol layer.
    stats["protocol_tcp"] = len(tcp_pkts)
    stats["protocol_udp"] = len(udp_pkts)
    stats["protocol_icmp"] = len(icmp_pkts)
    stats["protocol_arp"] = len(arp_pkts)
    stats["protocol_ip_total"] = len(ip_pkts)

    # Time / rate: duration is last - first timestamp; ppm buckets are 60s wide.
    timestamps = packet_timestamps(packets)
    if len(timestamps) >= 2:
        stats["duration_seconds"] = round(max(timestamps) - min(timestamps), 6)
    else:
        stats["duration_seconds"] = 0.0

    ppm = packets_per_minute_stats(timestamps)
    if ppm is not None:
        stats["packets_per_minute_avg"] = ppm["packets_per_minute_avg"]
        stats["packets_per_minute_max"] = ppm["packets_per_minute_max"]
        stats["packets_per_minute_min"] = ppm["packets_per_minute_min"]
    else:
        stats["packets_per_minute_avg"] = 0
        stats["packets_per_minute_max"] = 0
        stats["packets_per_minute_min"] = 0

    # Size stats over the full packet stream (every captured frame).
    sizes = [len(p) for p in packets]
    stats["total_bytes"] = sum(sizes)
    if sizes:
        stats["avg_packet_size"] = round(sum(sizes) / len(sizes), 2)
        stats["min_packet_size"] = min(sizes)
        stats["max_packet_size"] = max(sizes)
    else:
        stats["avg_packet_size"] = 0
        stats["min_packet_size"] = 0
        stats["max_packet_size"] = 0

    # Shannon entropy of src/dst port and IP distributions.
    src_ports, dst_ports = port_counters(tcp_pkts, udp_pkts)
    src_ips, dst_ips = ip_counters(ip_pkts)
    stats["dst_port_entropy"] = shannon_entropy(dst_ports)
    stats["src_port_entropy"] = shannon_entropy(src_ports)
    stats["src_ip_entropy"] = shannon_entropy(src_ips)
    stats["dst_ip_entropy"] = shannon_entropy(dst_ips)
    stats["unique_dst_ports"] = len(dst_ports)
    stats["unique_src_ports"] = len(src_ports)

    # Directed IP graph metrics — degrees count UNIQUE peers, not packets.
    g = graph_metrics(ip_pkts)
    stats["num_nodes"] = g["num_nodes"]
    stats["num_edges"] = g["num_edges"]
    stats["network_density"] = g["network_density"]
    stats["max_indegree"] = g["max_indegree"]
    stats["max_outdegree"] = g["max_outdegree"]
    all_nodes = g["_graph_state"][2]

    # Inter-arrival time stats (across all packets, sorted by timestamp).
    iat = iat_stats(timestamps)
    if iat is not None:
        stats["iat_mean"] = iat["iat_mean"]
        stats["iat_variance"] = iat["iat_variance"]
        stats["iat_cv"] = iat["iat_cv"]
    else:
        stats["iat_mean"] = 0
        stats["iat_variance"] = 0
        stats["iat_cv"] = 0

    # Producer/consumer counts via byte-balance PCR with ±0.2 thresholds.
    pc = producer_consumer_counts(ip_pkts, all_nodes)
    stats["num_producers"] = pc["num_producers"]
    stats["num_consumers"] = pc["num_consumers"]

    # 5-tuple flow metrics (TCP and UDP only; require IP layer).
    f = flow_metrics(tcp_pkts, udp_pkts)
    stats["unique_flows"] = f["unique_flows"]
    stats["bidirectional_flows"] = f["bidirectional_flows"]
    stats["tcp_flows"] = f["tcp_flows"]
    stats["udp_flows"] = f["udp_flows"]

    # Detection flags — strict thresholds; all calibrated in pcap_utils.
    has_port_scan = detect_port_scan(tcp_pkts)
    has_dos = detect_dos_pattern(
        stats["packets_per_minute_avg"], stats["packets_per_minute_max"]
    )
    has_beacon = detect_beaconing(stats["iat_cv"])
    stats["has_port_scan"] = has_port_scan
    stats["has_dos_pattern"] = has_dos
    stats["has_beaconing"] = has_beacon
    stats["is_traffic_benign"] = not (has_port_scan or has_dos or has_beacon)

    return stats


def _format_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return v


def fill_csv_template(template_path: str, stats: dict, output_path: str) -> None:
    """Read CSV template, fill `value` for known metrics, preserve comments."""
    with open(template_path, "r", newline="") as f:
        rows = list(csv.reader(f))

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        for row in rows:
            if not row:
                writer.writerow(row)
                continue
            metric = row[0]
            if metric.startswith("#") or metric == "metric":
                writer.writerow(row)
                continue
            if metric in stats:
                writer.writerow([metric, _format_value(stats[metric])])
            else:
                writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pcap", help="Path to the PCAP file")
    parser.add_argument(
        "--json", action="store_true", help="Print stats as JSON to stdout"
    )
    parser.add_argument(
        "--csv-template",
        help="Path to network_stats_template.csv to fill in place",
    )
    parser.add_argument(
        "--csv-output",
        help="Where to write the filled CSV (defaults to overwriting --csv-template)",
    )
    args = parser.parse_args()

    stats = compute_all_stats(args.pcap)

    if args.csv_template:
        out = args.csv_output or args.csv_template
        fill_csv_template(args.csv_template, stats, out)
        print(f"Wrote filled CSV to {out}", file=sys.stderr)

    if args.json or not args.csv_template:
        print(json.dumps(stats, indent=2, default=_format_value))


if __name__ == "__main__":
    main()
