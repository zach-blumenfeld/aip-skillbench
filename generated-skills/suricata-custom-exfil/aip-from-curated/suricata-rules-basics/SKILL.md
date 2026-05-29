---
name: suricata-rules-basics
description: Core building blocks of Suricata signatures and how to compose multi-condition HTTP DPI logic. Use when authoring a Suricata rule that must combine method, path, header, and body constraints with sticky buffers — including the `suricata-custom-exfil` task where the rule must alert only on POST /telemetry/v2/report with the X-TLM-Mode exfil header, a Base64-ish blob value ≥ 80 chars, and a 64-hex sig value.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Targets Suricata 6+ rule syntax. Lint script requires bash, awk, and grep. The script does not run Suricata; runtime testing (`suricata -T`, replay against pcaps) is out of scope for this skill.
---

```yaml
purpose: >
  Compose Suricata HTTP signatures that combine method, URI, header, and body
  constraints using sticky buffers, so the rule fires only on traffic that
  satisfies every condition and avoids spurious matches in unrelated bytes.
  Covers rule anatomy (header, flow, sid, rev), content vs PCRE matching, the
  HTTP sticky-buffer vocabulary, and the task template for
  `suricata-custom-exfil`.

trigger_when:
  - Authoring a Suricata rule that must AND together method, path, header, and body conditions.
  - Working on the `suricata-custom-exfil` task — alert on POST /telemetry/v2/report with X-TLM-Mode exfil, blob= Base64-ish ≥ 80 chars, sig= 64 hex chars; sid 1000001 in /root/local.rules.
  - Choosing between a literal `content:` match and a `pcre:` regex for a field.
  - Deciding which HTTP sticky buffer (`http.method`, `http.uri`, `http.header`, `http_client_body`) a candidate match belongs in.

do_not_use_when:
  - The traffic is not HTTP. HTTP sticky buffers will not match TLS, DNS, or custom binary protocols.
  - You need to identify where a string actually lives in a capture. Use the sibling `pcap-triage-tshark` skill first; this skill assumes the protocol location is already known.
  - You need to verify the rule fires correctly on real pcaps. The `check_exfil_rule.sh` script lints structure only; full validation needs `suricata -T` and replay, which are outside this skill.

scope_and_approval: >
  Read-write on a rules file (e.g. `/root/local.rules`). The skill edits that
  file in place and runs a local lint script. It does not start Suricata,
  reload a running engine, or touch network configuration. Confirm the target
  rules-file path before writing.

steps:
  - name: parse-task-conditions
    description: >
      Extract the structured AND-conditions from the task spec — proto, method,
      exact URI, required headers, body parameters with their length/charset
      constraints, and the target sid. For the `suricata-custom-exfil` task the
      five conditions are: HTTP POST; URI exactly /telemetry/v2/report; header
      `X-TLM-Mode: exfil`; body has `blob=` followed by ≥ 80 Base64-ish chars;
      body has `sig=` followed by exactly 64 hex chars; sid 1000001.
    inputs:
      - name: task-spec
        type: string
        description: Task instruction text or equivalent requirements list.
    outputs:
      - name: conditions
        type: list[object]
        description: One entry per AND-condition, each carrying a kind (method/uri/header/body) and the literal or pattern it constrains.
      - name: sid
        type: integer
        description: Target rule id (1000001 for this task).

  - name: map-conditions-to-buffers
    description: >
      For each condition, pick the HTTP sticky buffer it belongs in — `http.method`
      for the method, `http.uri` for the exact path, `http.header` for header
      presence/value, `http_client_body` for body params. See
      `references/sticky-buffers.md` for the buffer table and the hex-escape
      convention (`:` → `|3a|`). Skipping the sticky buffer makes the match
      run against the whole TCP stream and is a top failure mode.
    inputs:
      - name: conditions
        type: list[object]
    outputs:
      - name: buffer-plan
        type: list[object]
        description: For each condition, the chosen sticky buffer plus a literal-vs-regex decision.

  - name: compose-content-matches
    description: >
      Write the literal `content:` matches under each sticky buffer. Method
      under `http.method` (`content:"POST";`), exact path under `http.uri`
      (`content:"/telemetry/v2/report";`), header value under `http.header`
      with `:` hex-escaped (`content:"X-TLM-Mode|3a| exfil";`), and the body
      parameter markers under `http_client_body` (`content:"blob=";` and
      `content:"sig=";`). Repeat the buffer keyword before each content for
      clarity.
    inputs:
      - name: buffer-plan
        type: list[object]
    outputs:
      - name: content-block
        type: string

  - name: compose-pcre-matches
    description: >
      Write PCRE patterns for the constraints `content:` cannot express —
      length-bounded Base64-ish blob and exact-length hex sig. Anchor each
      regex to the parameter name so it cannot match unrelated body bytes.
      Use `pcre:"/blob=[A-Za-z0-9+\/]{80,}/";` (≥ 80 Base64-ish chars after
      `blob=`) and `pcre:"/sig=[0-9a-fA-F]{64}/";` (exactly 64 hex chars
      after `sig=`). Keep both inside the `http_client_body` buffer.
    inputs:
      - name: buffer-plan
        type: list[object]
    outputs:
      - name: pcre-block
        type: string

  - name: assemble-rule
    description: >
      Combine the content and pcre blocks into a single `alert http` rule
      whose body lists matches buffer-by-buffer in the order method → uri →
      header → body. Header line is `alert http any any -> any any`; constrain
      direction/state with `flow:established,to_server`; keep `msg` specific
      (e.g. `"TLM exfil"`); set `sid` to the task value and `rev:1;`. Append
      the assembled rule to the target rules file (commonly `/root/local.rules`).
    inputs:
      - name: content-block
        type: string
      - name: pcre-block
        type: string
      - name: sid
        type: integer
      - name: rules-file
        type: string
        description: Target rules file path (e.g. /root/local.rules).
    outputs:
      - name: rule-text
        type: string
      - name: rules-file-path
        type: string

  - name: lint-rule
    description: >
      Run the bundled lint script against the rules file to confirm the
      assembled rule covers all five exfil conditions, uses each sticky
      buffer correctly, and keeps the PCRE patterns anchored and bounded.
      Non-zero exit means at least one condition is missing — read the
      `[miss]` lines on stderr and revisit the failing step.
    script: scripts/check_exfil_rule.sh
    inputs:
      - name: rules-file-path
        type: string
      - name: sid
        type: integer
    outputs:
      - name: lint-report
        type: string
      - name: lint-ok
        type: boolean

scenarios:
  - need: >
      Custom telemetry exfil task — alert only when an HTTP POST to
      /telemetry/v2/report carries `X-TLM-Mode: exfil` plus a Base64-ish
      `blob=` (≥ 80 chars) and a 64-hex `sig=` in the body.
    context: >
      Source materials provide a scaffold but no working rule. The five
      AND-conditions map cleanly to four sticky buffers; `blob=` and `sig=`
      both need a literal `content:` plus an anchored `pcre:`.
    action: >
      Walk parse-task-conditions → map-conditions-to-buffers →
      compose-content-matches → compose-pcre-matches → assemble-rule →
      lint-rule. Set sid 1000001, rev 1, msg "TLM exfil", append to
      /root/local.rules.
    outcome: >
      A single `alert http` rule that fires on positives while ignoring
      benign POSTs that lack the header, ship the wrong path, or carry a
      blob too short or a sig of the wrong length.

  - need: >
      Rule has to match `X-TLM-Mode: exfil` but the literal colon in the
      content string is causing rule-parser surprises.
    action: >
      Hex-escape the colon as `|3a|`. Write `content:"X-TLM-Mode|3a| exfil";`
      under `http.header;`.
    outcome: >
      Header constraint matches the normalized header line without
      literal-character issues in the rule grammar.

anti_patterns:
  - Forgetting `http_client_body` and accidentally matching `blob=`/`sig=` strings in headers or URI.
  - Using `content:"POST";` without a preceding `http.method;` — POST can appear inside a body and would false-positive.
  - Making the Base64 regex too permissive (matches unrelated body bytes) or too strict (misses real exfil with padding).
  - Matching `sig=` literally but skipping the `pcre:` that enforces exactly 64 hex characters — alerts fire on truncated or wrong-encoding payloads.
  - Anchoring PCRE on Base64-ish characters alone without `blob=` in front, so the regex matches unrelated Base64-looking data elsewhere in the body.
  - Omitting `flow:established,to_server`, so the rule evaluates on stray packets that aren't part of a completed TCP handshake.
  - Writing a single mega-`pcre:` to cover all five conditions instead of stacked sticky-buffer matches — harder to read, harder to lint, and easy to misanchor.
```
