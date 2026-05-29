# Common failure modes

These are the mistakes that pass syntax checks but produce wrong
detections. The `lint_rule.py` script catches the first three
mechanically; the rest require judgment.

## Sticky-buffer omissions

- **Forgetting `http_client_body;`** before body content/pcre. The match
  falls through to the raw TCP payload and accidentally hits strings in
  headers or URI.
- **Using `content:"POST";` without `http.method;`** — `POST` can appear
  inside a body or header and false-fire.
- **Path content without `http.uri;`** — content can match in raw
  payload bytes that resemble a path.

## Regex calibration

- **Too permissive Base64 regex** (e.g. `[A-Za-z0-9+/=]*` or `.*`) —
  matches unrelated data and produces false positives.
- **Too strict** — e.g. requiring padding `=` when the producer may emit
  unpadded Base64. Real payloads vary; check the task's stated payload
  shape.
- **Forgetting length constraints** on a Base64 blob. Without `{N,}`,
  short noise tokens match.
- **Matching `sig=` but not enforcing exactly 64 hex characters.** Use
  `pcre:"/sig=[0-9a-fA-F]{64}/";` — both the character class and the
  exact `{64}` count.

## Buffer-reset gotchas

- Suricata resets the sticky buffer per option in some versions. If you
  have two `content:` lines that both target `http_client_body`, re-state
  `http_client_body;` before each.

## Rule-metadata mistakes

- **Missing `sid:`** — Suricata won't load the rule.
- **Reusing a `sid:`** already present in the ruleset — silent override.
- **Vague `msg:`** ("alert", "exfil") — makes triage painful. Be
  specific: `"TLM exfil — POST /telemetry/v2/report with blob+sig"`.
