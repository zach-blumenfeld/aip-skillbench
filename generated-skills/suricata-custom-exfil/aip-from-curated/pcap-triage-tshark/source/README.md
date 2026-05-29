# pcap-triage-tshark — AIP conversion notes

## Source

- `source/original-SKILL.md` — verbatim copy of the curated SKILL.md at
  `vendor/skillsbench/tasks/suricata-custom-exfil/environment/skills/pcap-triage-tshark/SKILL.md`.
- `scripts/summarize_http_requests.sh` — verbatim copy of the bundled helper.

## Schema

`procedure.schema.json` — the original is a procedure/workflow (broad filter →
narrow → extract → follow stream → export bytes → summarize). Procedure fits;
no new schema needed.

## Mapping

| Source content | AIP target |
|---|---|
| `name` / `description` frontmatter | `name` unchanged; `description` lightly extended with task-context keywords |
| "Quick filters" — `tshark -r f.pcap -Y http` | step `broad-protocol-filter` |
| "Quick filters" — filter by method/host | step `narrow-by-method-or-host` |
| "Inspect requests" — `-T fields -e ...` | step `extract-request-fields` |
| "Follow a TCP stream" | step `follow-tcp-stream` |
| "Export payload bytes" — `-x` | step `export-payload-bytes` |
| "Helper script" — `summarize_http_requests.sh` | step `summarize-http-requests` (script-backed) |
| Practical tip "start broad, then narrow" | step ordering + `anti_patterns` |
| Practical tip "confirm where strings live" | step `locate-strings-precisely` |
| Practical tip "note invariant vs variable" | step `classify-invariant-vs-variable` |

## Decisions

- `name` is preserved (`pcap-triage-tshark`) — required by the host task's skill mount.
- The procedure is mostly linear; downstream steps reference upstream outputs
  by `name` rather than using explicit `depends_on`, since list order matches
  the dependency graph.
- `summarize-http-requests` is presented as an alternative quick-start entry
  point, not in the linear chain — it gives a fast overview without the
  manual filter-narrow-extract cycle.
- The tshark one-liner steps are NOT script-backed: each is a single
  parameter-driven command with no conditional logic, lookup, or threshold —
  wrapping them in scripts would add ceremony without consistency gain. The
  one step with heuristic logic (the `X-TLM-Mode: exfil` count) is already
  in the bundled script.
- No content was dropped. Every distinct piece of the source SKILL.md is
  reflected in either a step, the anti-patterns list, or the script.
