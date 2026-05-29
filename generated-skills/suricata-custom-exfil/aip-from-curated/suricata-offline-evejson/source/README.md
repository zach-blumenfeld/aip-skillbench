# Source notes — suricata-offline-evejson → AIP

## Origin

`source/SKILL.md` is the verbatim curated Agent Skill from
`vendor/skillsbench/tasks/suricata-custom-exfil/environment/skills/suricata-offline-evejson/`.
It is the canonical source of truth for translating to AIP.

## Schema choice

Schema: `procedure.schema.json` (procedure / runbook family). The
curated skill is a multi-step iteration loop — syntax-check, run on
PCAP, inspect `eve.json`, iterate — so the procedure schema fits without
contortion. No new schema needed.

## Script-vs-prose decisions

Script-backed steps (deterministic invocations the agent should run the
same way every time):

- `validate-rule-syntax` (`scripts/validate_syntax.sh`) — wraps
  `suricata -T -c ... -S ...`. The flag combination and stderr handling
  are mechanical and easy to get wrong; the script makes them uniform.
- `run-on-pcap` (`scripts/run_suricata_offline.sh`) — copied verbatim
  from the source skill. Runs Suricata offline on one PCAP and prints
  per-sid alert counts via `jq`.
- `run-tight-loop` (`scripts/tight_loop.sh`) — orchestrates syntax
  check + positive PCAP + negative PCAP + PASS/FAIL verdict against a
  target sid. This is the agent's main iteration command; collapsing
  the three runs into one script eliminates the "I forgot to re-run
  the negative PCAP" failure mode and gives a single output to read.

Prose steps (judgment, interpretation):

- `locate-fixtures` — picking which PCAPs are positive vs negative is
  environment-specific; fixed defaults are baked into the scripts for
  the suricata-custom-exfil task family, but the agent has to confirm
  them.
- `interpret-and-iterate` — diagnosing under-match vs over-match vs
  rule-not-loaded vs wrong-sticky-buffer requires reading the task
  brief alongside the alert counts. Not a fixed lookup.

## Content mapping

Every section of the source SKILL.md is captured:

- Standard offline invocation (`suricata -c ... -S ... -k none -r ...
  -l ...`) → `run_suricata_offline.sh` and `tight_loop.sh`.
- Flag explanations (`-r`, `-S`, `-l`, `-k none`) → embedded in step
  descriptions and `references/eve-json.md`.
- `jq` recipes for counting and listing alerts →
  `references/eve-json.md` (expanded with extra recipes for body-byte
  inspection and exit-code checks).
- "Practical tips" (clean exit, fresh `-l` dir, positive + negative
  testing) → `anti_patterns` plus the fresh-log-dir note in
  `references/eve-json.md`.
- Tight feedback loop (validate, positive, negative) →
  `scripts/tight_loop.sh` (one-shot) and the `run-tight-loop` step.
- Reference to the source `run_suricata_offline.sh` → kept as the
  single-PCAP `run-on-pcap` step.

Additions beyond the source SKILL.md that the agent needs to solve the
task autonomously:

- Explicit target-sid concept and PASS/FAIL verdict in `tight_loop.sh`.
  The curated source surfaces counts but leaves "did the right sid
  fire?" implicit; the AIP version makes it the script's contract so
  the agent gets a single signal per iteration.
- `references/eve-json.md` documents the alert-event schema fields
  Suricata emits with the task's config (`http.url`,
  `http.http_request_body_printable`, etc.) so the agent can debug
  *why* a rule mis-fired, not just *that* it did.
- `interpret-and-iterate` enumerates the four failure modes
  (under-match, over-match, both silent, extra sids) so the agent
  reads the verdict correctly instead of just retrying randomly.

No content was dropped.
