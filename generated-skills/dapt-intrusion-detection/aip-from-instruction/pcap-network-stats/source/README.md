# Source rationale — pcap-network-stats

This skill was authored from a single instruction file describing a pcap-
analysis task on a subset of DAPT2020 traffic. The agent must compute a fixed
set of network statistics and fill in only the `value` column of an existing
CSV template (`/root/network_stats.csv`), preserving comment lines and the
header.

## Scope encoded

- Protocol counts (TCP, UDP, ICMP, ARP, IP total)
- Time/rate (duration, packets per 60s bucket: avg/max/min)
- Packet-size distribution (sum, avg, min, max)
- Shannon entropy over src/dst IPs and src/dst ports, plus distinct port counts
- Directed IP-graph metrics (nodes, edges, density, max in/out-degree)
- Inter-arrival timing (mean, variance, coefficient of variation)
- Producer/Consumer Ratio (PCR) — count of producers and consumers
- 5-tuple flow accounting (unique, TCP, UDP, bidirectional)
- Heuristic intrusion-detection flags
  (`is_traffic_benign`, `has_port_scan`, `has_dos_pattern`, `has_beaconing`)

## Schema choice

The task is a deterministic procedure executed end-to-end: read pcap → compute
metrics → write CSV → verify. That is the exact shape `procedure.schema.json`
describes (purpose + trigger_when + steps + decisions + anti_patterns). No new
schema is justified — reuse keeps the corpus governance-clean.

## What lives in the body vs references

The SKILL body stays under 200 lines: trigger, scope, ordered steps, decision
table for ambiguous metric interpretations, and the anti-patterns the agent
would otherwise stumble into. Every other detail (exact metric formulas,
threshold defaults, gotchas, verification invariants, fallback libraries) is
parked in `references/implementation-notes.md`, which the body tells the
agent when to read.

## What is intentionally not in the skill

- No discussion of *why* DAPT2020 exists or what APT stages look like; the
  agent doesn't need attacker taxonomy to compute the requested metrics.
- No deep payload-inspection guidance; the task is statistical, not DPI.
- No threshold *justification* for the heuristic flags — the script encodes
  the chosen defaults and the reference documents the rules so the agent can
  override them if a value seems wrong.
