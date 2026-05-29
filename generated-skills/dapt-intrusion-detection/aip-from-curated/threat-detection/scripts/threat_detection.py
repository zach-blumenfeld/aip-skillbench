#!/usr/bin/env python3
"""
Threat detection thresholds for PCAP analysis.

Calibrated for DAPT2020-style traffic. The threshold constants below
are load-bearing — changing them will produce incorrect verdicts on
calibrated datasets.

Importable functions (preferred when the agent already has packets loaded):

    from threat_detection import (
        detect_port_scan,      # (tcp_packets)              -> bool
        detect_dos_pattern,    # (ppm_avg, ppm_max)         -> bool
        detect_beaconing,      # (iat_cv)                   -> bool
        assess_benign,         # (has_scan, has_dos, has_beacon) -> bool
    )

CLI (one verdict per invocation, prints 'true' or 'false' on stdout):

    python threat_detection.py port-scan --pcap /root/packets.pcap
    python threat_detection.py dos       --ppm-avg 262.9 --ppm-max 2372
    python threat_detection.py beaconing --iat-cv 0.3
    python threat_detection.py benign    --port-scan false --dos false --beaconing false
"""

import argparse
import math
import sys
from collections import Counter, defaultdict

# Calibrated thresholds — do not modify.
PORT_ENTROPY_THRESHOLD = 6.0
SYN_ONLY_RATIO_THRESHOLD = 0.7
UNIQUE_PORTS_THRESHOLD = 100
MIN_PACKETS_PER_SRC = 50
DOS_RATIO_THRESHOLD = 20
BEACONING_CV_THRESHOLD = 0.5


def detect_port_scan(tcp_packets):
    """
    Port scan iff some source IP (with >= MIN_PACKETS_PER_SRC TCP packets)
    simultaneously satisfies:
        port-entropy        > PORT_ENTROPY_THRESHOLD     (6.0)
        SYN-only-ratio      > SYN_ONLY_RATIO_THRESHOLD   (0.7)
        unique-dst-ports    > UNIQUE_PORTS_THRESHOLD     (100)
    Any single high port count alone is NOT a scan.
    """
    try:
        from scapy.all import IP, TCP
    except ImportError as e:
        raise ImportError(
            "scapy is required for detect_port_scan(tcp_packets); install scapy or use the CLI"
        ) from e

    src_port_counts = defaultdict(Counter)
    src_syn_only = defaultdict(int)
    src_total = defaultdict(int)

    for pkt in tcp_packets:
        if IP not in pkt or TCP not in pkt:
            continue
        src = pkt[IP].src
        dst_port = pkt[TCP].dport
        flags = pkt[TCP].flags

        src_port_counts[src][dst_port] += 1
        src_total[src] += 1

        # SYN flag (0x02) set, ACK (0x10) clear.
        if flags & 0x02 and not (flags & 0x10):
            src_syn_only[src] += 1

    for src, ports in src_port_counts.items():
        if src_total[src] < MIN_PACKETS_PER_SRC:
            continue
        total = sum(ports.values())
        entropy = -sum((c / total) * math.log2(c / total) for c in ports.values() if c > 0)
        syn_ratio = src_syn_only[src] / src_total[src]
        unique_ports = len(ports)
        if (
            entropy > PORT_ENTROPY_THRESHOLD
            and syn_ratio > SYN_ONLY_RATIO_THRESHOLD
            and unique_ports > UNIQUE_PORTS_THRESHOLD
        ):
            return True
    return False


def detect_dos_pattern(ppm_avg, ppm_max):
    """DoS iff packets_per_minute_max / packets_per_minute_avg > DOS_RATIO_THRESHOLD (20)."""
    if ppm_avg == 0:
        return False
    return (ppm_max / ppm_avg) > DOS_RATIO_THRESHOLD


def detect_beaconing(iat_cv):
    """Beaconing iff inter-arrival-time CV < BEACONING_CV_THRESHOLD (0.5)."""
    return iat_cv < BEACONING_CV_THRESHOLD


def assess_benign(has_port_scan, has_dos, has_beaconing):
    """Benign iff none of the three threat detectors fire."""
    return not (has_port_scan or has_dos or has_beaconing)


def _parse_bool(s):
    v = str(s).strip().lower()
    if v in ("1", "true", "t", "yes", "y"):
        return True
    if v in ("0", "false", "f", "no", "n"):
        return False
    raise argparse.ArgumentTypeError(f"expected boolean, got {s!r}")


def _print(result):
    print("true" if result else "false")


def main():
    parser = argparse.ArgumentParser(
        description="Threat-detection threshold checks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("port-scan", help="Run port-scan detector against a PCAP file")
    p.add_argument("--pcap", required=True, help="Path to PCAP file")

    d = sub.add_parser("dos", help="Run DoS detector against ppm stats")
    d.add_argument("--ppm-avg", required=True, type=float)
    d.add_argument("--ppm-max", required=True, type=float)

    b = sub.add_parser("beaconing", help="Run beaconing detector against iat_cv")
    b.add_argument("--iat-cv", required=True, type=float)

    bn = sub.add_parser("benign", help="Combine the three threat flags into a benign verdict")
    bn.add_argument("--port-scan", required=True, type=_parse_bool)
    bn.add_argument("--dos", required=True, type=_parse_bool)
    bn.add_argument("--beaconing", required=True, type=_parse_bool)

    args = parser.parse_args()

    if args.cmd == "port-scan":
        from scapy.all import TCP, rdpcap
        packets = rdpcap(args.pcap)
        tcp = [pkt for pkt in packets if TCP in pkt]
        _print(detect_port_scan(tcp))
    elif args.cmd == "dos":
        _print(detect_dos_pattern(args.ppm_avg, args.ppm_max))
    elif args.cmd == "beaconing":
        _print(detect_beaconing(args.iat_cv))
    elif args.cmd == "benign":
        _print(assess_benign(args.port_scan, args.dos, args.beaconing))
    else:
        parser.error("unknown command")
    return 0


if __name__ == "__main__":
    sys.exit(main())
