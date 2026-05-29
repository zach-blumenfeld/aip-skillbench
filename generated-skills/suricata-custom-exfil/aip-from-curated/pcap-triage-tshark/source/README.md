# Source notes — pcap-triage-tshark (AIP-from-curated)

## Origin

Compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/suricata-custom-exfil/environment/skills/pcap-triage-tshark/`.

The curated skill is a short, freeform runbook of `tshark` invocations for
inspecting PCAPs during an HTTP-exfil investigation. It is one of three skills
mounted into the `suricata-custom-exfil` task environment; the other two cover
Suricata rule basics and offline `eve.json` analysis.

## Schema choice

Used [`procedure.schema.json`](procedure.schema.json) (AIP v0.3a3) — the workflow
is a small linear/parallel procedure of shell invocations, which is exactly the
procedure-skill shape: triggers, ordered steps, a backing helper script,
gotchas. No need to draft a new schema.

## Script vs prose decisions

- **Kept the helper script verbatim** at `scripts/summarize_http_requests.sh`.
  The curated source ships it and `SKILL.md` invokes it by path; reproducing
  byte-for-byte preserves the contract. It is wired into the `quick-summary`
  step.
- **Left every other step as prose.** Each `tshark` invocation is a one-liner
  the agent composes from filter knowledge — there is no deterministic
  if/then/else, lookup table, or threshold to encode. Wrapping these in a
  script would only hide the filter the agent already needs to read and adapt
  (different PCAP names, different streams, different fields).
- **Did not author new scripts.** The curated runbook deliberately stops at
  "broad → narrow → confirm" — judgment about *which* field a string lives in
  is exactly the kind of input-interpretation the AIP spec says to leave as
  prose.

## Content mapping

Every distinct piece of the curated `SKILL.md` is captured in the AIP body:

| Curated source                          | AIP body location                        |
|-----------------------------------------|------------------------------------------|
| "Fast workflow to inspect PCAPs…"       | `purpose`, `description` frontmatter     |
| Quick filters (`-Y http`, `-Y 'http.request.method == "POST"'`) | `steps[broad-filter]` |
| Inspect requests (`-T fields …`)        | `steps[field-extract]`                   |
| Follow a TCP stream (`-z follow,tcp,…`) | `steps[follow-stream]`                   |
| Export payload bytes (`-x`)             | `steps[export-bytes]`                    |
| Practical tips (broad→narrow, where strings live, invariant vs variable) | `steps[narrow-and-note]` + `anti_patterns` |
| Helper script invocation                | `steps[quick-summary]` with `script:` ref |

Task-specific context (the `X-TLM-Mode: exfil` header, `/telemetry/v2/report`
path, `blob=` / `sig=` body fields) is surfaced in `trigger_when` and
`scenarios` so the agent knows *what to look for* when this skill activates
inside the `suricata-custom-exfil` environment, without rewriting the curated
neutral tooling guidance.

No source content was dropped.

## Name

Preserved as `pcap-triage-tshark` to match the curated skill's mounted name
in the task environment (the task harness mounts skills by directory name).
