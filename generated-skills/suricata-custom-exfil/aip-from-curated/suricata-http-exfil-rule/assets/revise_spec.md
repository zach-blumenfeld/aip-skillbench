# Fix the rule: verification attempt {attempt} failed

Rule that was written to the rules file:

{rule_text}

detection_spec used: {detection_spec}

Failures: {failures}

Warnings: {warnings}

Suricata syntax check (`suricata -T`): {suricata_syntax}

All checks (labeled = training pcaps; mutation = a near-miss built from the positive request, one condition broken (expect no alert) or one harmless variation (expect alert)): {checks}

Diagnose, then fix:

- `detection_spec invalid` or `suricata -T failed`: fix the spec field named in the error (charset, msg characters). Load references/suricata-http-rules.md for buffer/keyword syntax.
- `spec emulator says ... (the detection_spec disagrees with the pcap label)`: the spec is too strict or too loose for the training traffic, or a pcap label is wrong. Re-read the request in the triage output: wrong header name, value case, param name, charset (missing `+` `/`), or length bound. Fix the spec or the label, not both blindly.
- A mutation fails only under Suricata (emulator ok): the generated rule text diverges from the spec in Suricata's real buffers. Inspect the pcap and eve.json under the reported `workdir` (references/offline-verification.md has the commands). If a spec change cannot express the fix, write the full single-line rule yourself in `rule_override` (it is used verbatim instead of the composed rule; keep the same sid). Set `rule_override` to "" to go back to the composed rule.
- `unexpected sids`: something besides the one required sid fired; the rules file must hold only this one rule.

Output JSON with `detection_spec` (object, the full corrected spec), and `pcap_labels` (object) if you changed a label, and `rule_override` (string) only if you need it.
