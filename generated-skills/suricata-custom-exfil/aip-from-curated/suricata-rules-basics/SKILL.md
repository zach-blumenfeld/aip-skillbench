---
name: suricata-rules-basics
description: Core building blocks of Suricata signatures and multi-condition HTTP DPI logic. Use when writing or extending a Suricata rule for HTTP traffic, composing detection over HTTP method + URI + headers + body, or working the `suricata-custom-exfil` task family. Covers rule anatomy, HTTP sticky buffers (`http.method`, `http.uri`, `http.header`, `http_client_body`), content vs PCRE matching, Base64-and-hex body patterns, and the common failure modes that cause silent over- or under-matching.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Compose multi-condition Suricata HTTP signatures by stacking protocol-aware
  sticky buffers (http.method, http.uri, http.header, http_client_body) with
  content and PCRE matches. Covers rule anatomy, buffer selection, regex
  patterns for hex tokens and Base64-shaped blobs, and the failure modes
  that produce silent over- or under-matching. Intentionally teaches
  composition rather than emitting a finished rule — the agent assembles
  the final signature from the task's stated constraints.

trigger_when:
  - Writing or extending a Suricata rule that inspects HTTP traffic.
  - Detecting custom telemetry exfil over HTTP — e.g., the suricata-custom-exfil task family.
  - Expressing multi-condition DPI logic across method + URI + header + body.
  - Combining fixed `content:` matches with `pcre:` regex inside `http_client_body`.
  - Reviewing a candidate Suricata rule for the common sticky-buffer and regex-calibration mistakes.

do_not_use_when:
  - Writing rules for a non-Suricata IDS (Snort syntax overlaps but differs in buffer names and semantics).
  - Authoring threshold-only or rate-only rules with no DPI content.
  - Working on non-HTTP application protocols — buffer names differ (e.g., `tls.sni`, `dns.query`).

scope_and_approval: >
  Read-only by default — emit the proposed rule for the user or task harness
  to install. Do not load rules into a running Suricata instance, modify
  `suricata.yaml`, or restart the engine without explicit confirmation.

steps:
  - name: parse-task-requirements
    description: >
      Read the task brief and extract the concrete detection constraints —
      HTTP method, exact URI/path, required header field(s) and value(s),
      required body parameter names, and any encoding/length constraints
      on body values (e.g., "blob is Base64-ish, length ≥ 80", "sig is
      exactly 64 hex chars"). Do not guess — if the brief is silent on a
      dimension, note it and continue without inventing constraints.
    outputs:
      - name: rule-spec
        type: object
        description: Structured view of required method, uri, headers, body params, and value constraints.

  - name: select-buffers
    description: >
      Map each constraint in `rule-spec` to the right HTTP sticky buffer:
      method → `http.method`, exact path → `http.uri`, header
      field/value → `http.header` (use `|3a|` for `:` to avoid formatting
      surprises), body parameter presence and shape → `http_client_body`.
      Prefer protocol-aware buffers over raw payload matching so the rule
      cannot accidentally match unrelated bytes in the TCP stream.
    inputs:
      - name: rule-spec
        type: object
    outputs:
      - name: buffer-plan
        type: object
        description: Ordered list of (buffer, intended match) pairs covering every constraint.

  - name: compose-conditions
    description: >
      For each (buffer, intended match) in `buffer-plan`, draft the
      condition. Start strict — method and exact path first, then header,
      then body. For body values, decide between `content:` (fixed bytes,
      cheap) and `pcre:` (regex, expensive but expressive). Anchor each
      regex to its parameter name (e.g., `sig=[0-9a-fA-F]{64}`,
      `blob=[A-Za-z0-9+\/]{80,}`) so it cannot drift onto unrelated
      Base64-shaped data. See `references/focused-examples.md` for
      composable fragments.
    inputs:
      - name: buffer-plan
        type: object
    outputs:
      - name: conditions
        type: list[object]
        description: One entry per condition with the buffer line and the content/pcre line(s).

  - name: assemble-rule
    description: >
      Drop the conditions into the scaffold from
      `references/focused-examples.md`. Add `flow:established,to_server`
      to constrain direction/state, a specific `msg:` (e.g.,
      "TLM exfil — POST /telemetry/v2/report with blob+sig"), a unique
      `sid:` not already in the ruleset, and `rev:1`. Group related
      matches and keep the rule readable.
    inputs:
      - name: conditions
        type: list[object]
    outputs:
      - name: candidate-rule
        type: string
        description: Full rule text, suitable for writing to a .rules file.

  - name: lint-rule
    description: >
      Run the lint script over `candidate-rule`. It checks the common
      failure modes mechanically: method content without preceding
      `http.method;`, path content without preceding `http.uri;`, body
      params without preceding `http_client_body;`, `sig=` without a
      64-hex PCRE, `blob=` without a length-bounded PCRE, overly
      permissive `.*`/`.+`, and missing `sid:`/`rev:`. Output is JSON
      with `errors` (must fix) and `warnings` (review).
    script: scripts/lint_rule.py
    inputs:
      - name: candidate-rule
        type: string
    outputs:
      - name: lint-report
        type: object
        description: '{"errors": list[string], "warnings": list[string]}'

  - name: fix-lint-findings
    description: >
      For each error, apply the correction (most commonly: re-state the
      sticky buffer before the offending content/pcre, or tighten an
      under-constrained regex). For each warning, decide whether the
      task's brief justifies it or whether the rule should be adjusted —
      `.*`/`.+` in particular almost always indicates an
      under-anchored regex. Re-run `lint-rule` until errors are clear.
      Lint passing is necessary but not sufficient — re-read the task
      brief and confirm every stated constraint is enforced before
      emitting the final rule.
    inputs:
      - name: candidate-rule
        type: string
      - name: lint-report
        type: object
    outputs:
      - name: final-rule
        type: string

anti_patterns:
  - Forgetting `http_client_body;` before body content/pcre — match falls through to raw payload and hits headers or URI bytes.
  - Using `content:"POST";` without `http.method;` — `POST` matches inside body or header bytes.
  - Writing a path match (e.g., `content:"/telemetry/v2/report"`) without `http.uri;` — same drift problem.
  - Making the Base64 regex too permissive (e.g., bare `.*` or `[A-Za-z0-9+/=]*`) — false positives explode.
  - Matching `sig=` but not enforcing exactly 64 hex characters — partial token detections that miss the real signature.
  - Omitting `{N,}` length bounds on Base64 blobs — short noise tokens trigger the rule.
  - Re-using a `sid:` already present in the ruleset — silent override of an existing rule.
  - Copy-pasting the scaffold or a focused example as the final rule without verifying it covers every constraint the task brief stated.
  - Generic `msg:` ("alert", "exfil") that makes downstream triage impossible.
```
