# AIP conversion notes — threat-detection

Source: `vendor/skillsbench/tasks/dapt-intrusion-detection/environment/skills/threat-detection/SKILL.md`.

Schema: bundled `procedure.schema.json` (procedure-style instruction — the
skill is a multi-step detection pipeline with thresholds and a benign-
assessment composition).

## Mapping

- Port scan detection requirements (entropy > 6.0, SYN-only ratio > 0.7,
  unique ports > 100, ALL THREE) → `steps[detect-port-scan]` body +
  `decisions` rows + `anti_patterns`.
- DoS pattern threshold (max/avg ratio > 20) → `steps[detect-dos]` +
  `decisions` row for 5–20× range + `anti_patterns`.
- Beaconing threshold (IAT CV < 0.5) → `steps[detect-beaconing]` +
  `decisions` row.
- Benign composition (all three false) → `steps[assess-benign]` with
  `depends_on` the three detectors + `decisions` row.
- Worked examples (1000-port non-scan, 9.02× non-DoS) → `scenarios`.
- Python reference implementations → `references/implementations.md`
  (progressive disclosure; body stays lean and links there).
- Import path `/root/skills/pcap-analysis/pcap_utils` → preserved in
  `references/implementations.md` exactly as in the source.

No source items were dropped.
