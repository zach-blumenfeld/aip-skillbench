# eve.json — fields and `jq` recipes for offline rule iteration

`eve.json` is Suricata's primary structured log: one JSON object per line,
one line per event. When iterating on a rule against a PCAP, the only
event_type that matters is `alert`. The fields below are the minimum the
agent needs to confirm whether a candidate rule fired on the right
traffic and only on the right traffic.

## Field cheat sheet (alert events)

- `event_type` — `"alert"` for matches. Always filter on this first.
- `alert.signature_id` — the `sid:` from the rule that fired. Integer.
- `alert.signature` — the `msg:` from the rule. Useful for triage but
  not for pass/fail (sid is the contract).
- `alert.rev` — the `rev:` from the rule. Surfaces stale cached rules.
- `src_ip`, `dest_ip`, `src_port`, `dest_port` — flow tuple.
- `http.url`, `http.http_method`, `http.hostname`,
  `http.http_request_body_printable`,
  `http.http_response_body_printable` — populated when the alert sits on
  HTTP traffic (and the config emits these payload fields, which the
  task's `suricata.yaml` does). Read these to confirm the alert fired on
  the body bytes you expected.

Other event types Suricata writes (`http`, `flow`, `tls`, `dns`,
`fileinfo`, ...) are noise for rule iteration. Filter them out unless
debugging why an alert *didn't* fire.

## Common `jq` recipes

Count alerts per sid (most useful summary while iterating):

```bash
jq -r 'select(.event_type=="alert") | .alert.signature_id' /tmp/suri/eve.json \
  | sort -n | uniq -c
```

List sid + msg per alert:

```bash
jq -r 'select(.event_type=="alert") | [.alert.signature_id, .alert.signature] | @tsv' \
  /tmp/suri/eve.json
```

Confirm a specific sid fired at least once (exit 0 = fired, 1 = silent):

```bash
jq -e --argjson sid 1000001 \
  'select(.event_type=="alert" and .alert.signature_id==$sid)' \
  /tmp/suri/eve.json >/dev/null
```

Inspect the request body for the alert that fired (debug
over-/under-matching against the actual bytes):

```bash
jq -r 'select(.event_type=="alert") |
       {sid:.alert.signature_id, uri:.http.url,
        method:.http.http_method,
        body:.http.http_request_body_printable}' \
  /tmp/suri/eve.json
```

List every distinct sid that fired across a run (sanity check that the
rules file did not silently produce extra alerts):

```bash
jq -r 'select(.event_type=="alert") | .alert.signature_id' /tmp/suri/eve.json \
  | sort -u
```

## Interpreting `jq` output during a positive/negative loop

- Positive PCAP, target sid missing from the count → rule is
  under-matching. Loosen the *most specific* constraint first (regex
  bounds, exact case in header value) and re-run.
- Negative PCAP, target sid present in the count → rule is
  over-matching. Identify which constraint the negative traffic violates
  (compare to the task's stated detection criteria) and tighten the rule
  to enforce it.
- Both PCAPs silent on the target sid → either the rule failed to load
  (re-run `suricata -T` and re-read its stderr) or the sticky buffer is
  wrong (the bytes you wanted to match are not in the buffer you
  selected).
- Extra sids firing that you did not author → another file under the
  `default-rule-path` was picked up. Check `rule-files:` in
  `suricata.yaml`.

## Why a fresh `-l` directory matters

Suricata appends to `eve.json` rather than truncating, and writes
several other artifacts (`stats.log`, `fast.log`, `suricata.log`) into
the same directory. Re-using a log dir across runs mixes alerts from
multiple rule revisions and makes the per-sid counts above lie. The
provided scripts always `rm -rf` the log dir before invocation; if
running Suricata by hand, do the same.
