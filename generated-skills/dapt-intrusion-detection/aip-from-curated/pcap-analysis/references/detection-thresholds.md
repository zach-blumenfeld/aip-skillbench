# Detection Thresholds Reference

All three detectors require **strict, calibrated thresholds**. Loosening any
of them produces false positives on the DAPT2020 traffic; tightening produces
false negatives. The thresholds below match `pcap_utils.py` exactly — do not
diverge.

## Port scan — `detect_port_scan(tcp_packets)`

Returns `True` only if **all** of these conditions hold for **at least one
source IP**:

1. **Port entropy > 6.0** (bits)
   Scanners hit many destination ports uniformly. Normal clients repeatedly
   reuse a few ports (entropy ~4–5 bits). Per-source entropy, not global.
2. **SYN-only ratio > 0.7**
   Half-open scans send SYN packets without completing the handshake. SYN-only
   = SYN flag set (`flags & 0x02`) AND ACK flag clear (`not (flags & 0x10)`).
3. **Unique destination ports > 100**
   Volume gate — must touch >100 distinct dports before "scanning" is
   meaningful.

A source is **ignored** if it has fewer than `min_packets=50` TCP packets
(noise threshold). If any single source clears all three bars, the function
returns `True` and short-circuits.

**Common false-trigger patterns the thresholds reject:**
- One host doing 200 retries to port 443 → entropy ~0, fails (1).
- Stealthy 50-port sweep with completed handshakes → fails (2) and (3).
- Casual telnet probe touching 80 ports → fails (3).

## DoS pattern — `detect_dos_pattern(ppm_avg, ppm_max)`

Returns `True` iff `ppm_max / ppm_avg > 20`.

DoS traffic produces **extreme** rate spikes. Ratios of 5×, 10×, even 15×
are normal diurnal / burst variation in production traffic — **not DoS**.

Edge case: `ppm_avg == 0` → returns `False` (no traffic, no attack).

## Beaconing — `detect_beaconing(iat_cv)`

Returns `True` iff `iat_cv < 0.5`, where `iat_cv = iat_std / iat_mean`.

Interpretation:
- **CV < 0.5** — inter-arrival times are highly regular ⇒ robotic /
  programmatic ⇒ likely C2 beacon.
- **CV ~ 1.0** — exponential-like spread ⇒ typical Poisson-ish human traffic.
- **CV > 1.0** — bursty / heavy-tailed ⇒ normal mixed workload.

CV is computed over **all** packets sorted by timestamp, not per-flow. A
single regular beacon hidden in a noisy capture can be diluted; the
DAPT2020 task only flags it when the dominant pattern is regular.

## Benign traffic

`is_traffic_benign = NOT (has_port_scan OR has_dos_pattern OR has_beaconing)`

If any of the three detectors fires, the traffic is **not** benign. There is
no separate benign signal — the absence of all three is the signal.

## Why scripts, not prose

These thresholds are deterministic numeric gates. Re-implementing them inline
in agent reasoning is exactly where the original task fails: agents lower the
SYN-only threshold to 0.5 "because that still seems half-open", or call DoS at
10× "because that's a big spike". The script is the source of truth — call
`detect_port_scan`, `detect_dos_pattern`, `detect_beaconing` from
`pcap_utils.py` and accept the booleans they return.
