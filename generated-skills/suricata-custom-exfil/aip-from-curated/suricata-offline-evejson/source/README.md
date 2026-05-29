# Source / Authoring Notes

## Intent
This AIP skill is a faithful transition of the curated `suricata-offline-evejson` skill
(`source/original_SKILL.md`) used by the SkillsBench `suricata-custom-exfil` task. It
covers running Suricata against a PCAP offline and validating results via `eve.json`,
plus the recommended tight-feedback iteration loop on `/root/local.rules`.

## Schema
Reuses `procedure.schema.json` (the AIP procedure schema). The skill is a multi-step
graph: validate rule syntax → run on positive pcap → run on negative pcap → inspect
alerts → iterate. Conditional logic (e.g., bail on `suricata -T` failure, error if
`eve.json` missing) lives in `scripts/feedback_loop.sh` rather than prose.

## Scripts
- `scripts/run_suricata_offline.sh` — verbatim copy of the original script: run Suricata
  on one PCAP, print sid → count.
- `scripts/feedback_loop.sh` — added wrapper. Encodes the "tight feedback loop" the
  source SKILL.md documents inline as bash: `suricata -T` syntax check, then run on
  both a positive and a negative PCAP and print sid → count for each. The original
  prose lists these as three separate bash blocks; the script captures the procedure as
  a single repeatable node with explicit exit codes (2 args, 3 syntax fail, 4/5 missing
  eve.json) so the agent can iterate quickly.

## Source content classification
Every meaningful line from `source/original_SKILL.md` maps to:

- "Running Suricata against PCAPs offline / validating via eve.json" → `purpose`.
- "Typical offline invocation" + flag descriptions → `steps.run-on-pcap`
  (script-backed) and the `scenarios` block for documentation.
- "Inspect alerts in EVE JSON" jq snippets (count, list sid + signature) →
  `steps.inspect-alerts` plus retained as inline jq inside `scenarios` so the agent
  has the exact one-liners.
- "Practical tips" (clean exit, fresh `-l` dir, positive/negative pcap testing) →
  `anti_patterns`.
- "Tight feedback loop (recommended)" → `steps.validate-rules` + `run-on-positive` +
  `run-on-negative` + `iterate-on-rule`, with `scripts/feedback_loop.sh` as the
  script-backed single-command form.
- "If you prefer a one-command summary, see scripts/run_suricata_offline.sh" → step
  `run-on-pcap` references the script.

No deliberate drops.

## Task fit
The host task (`suricata-custom-exfil`) requires the agent to write a Suricata rule
with `sid:1000001` for a custom HTTP exfil pattern (POST, exact path, header, body
regex on `blob=` Base64 ≥80 chars, body `sig=` 64-hex-char). The agent supplies
the rule content; this skill supplies the iteration mechanics so the agent can
quickly tell whether the current rule fires on the positive pcap, stays silent on
the negative pcap, and parses cleanly.
