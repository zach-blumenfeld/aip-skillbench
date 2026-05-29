# Source notes — suricata-rules-basics (AIP)

Compiled from the curated `SKILL.md` at
`vendor/skillsbench/tasks/suricata-custom-exfil/environment/skills/suricata-rules-basics/SKILL.md`
into AIP procedure form.

## Intent

The curated skill teaches Suricata signature anatomy plus the specific
sticky-buffer pattern needed to write a multi-condition HTTP DPI rule for the
`suricata-custom-exfil` task. The AIP version preserves all of that knowledge,
re-expresses it as a step graph an agent walks from "I have a task spec" to
"I have a `local.rules` file Suricata will accept and that fires on positives
without false positives."

## Source-coverage classification

| Source section | Disposition |
| --- | --- |
| Rule anatomy (header, sids, rev, flow) | Mapped → `purpose`, `assemble-rule` step |
| Content matching | Mapped → `compose-content-matches` step |
| PCRE | Mapped → `compose-pcre-matches` step |
| Sticky buffers (HTTP) | Mapped → `map-conditions-to-buffers` step + `references/sticky-buffers.md` |
| Practical tips | Mapped → `assemble-rule` step description + `anti_patterns` |
| Task template (custom telemetry exfil) | Mapped → `parse-task-conditions`, `assemble-rule`, `scenarios` |
| Focused examples (method/URI/header/body) | Mapped → `compose-content-matches`, `compose-pcre-matches`, `scenarios` |
| Common failure modes | Mapped → `anti_patterns` |

No deliberate drops. Everything in the source is reachable from the AIP body
or from the bundled reference.

## Scripts

- `scripts/check_exfil_rule.sh` — lint a candidate rule against the five
  required conditions from the task (`POST`, exact URI, header,
  `blob=` Base64-ish ≥ 80 chars, `sig=` 64-hex). Returns non-zero with a
  per-condition checklist when something is missing. The script is a
  self-check the agent runs before declaring the rule complete; it does
  not run Suricata.

## References

- `references/sticky-buffers.md` — quick lookup table for HTTP sticky
  buffers, when to reach for each, and the hex-escape convention for
  header values containing `:`.
