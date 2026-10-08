## detection_spec format (consumed by scripts/build_and_check.py)

```json
{
  "sid": 1000001,
  "rev": 1,
  "msg": "TLM exfil",
  "flow": "established,to_server",
  "method": "POST",
  "uri": {"value": "/telemetry/v2/report", "match": "exact_path"},
  "headers": [
    {"name": "X-TLM-Mode", "value": "exfil", "value_nocase": false, "match": "exact"}
  ],
  "body_params": [
    {"name": "blob", "charset": "A-Za-z0-9+/", "min_len": 80, "max_len": null, "allow_padding": true},
    {"name": "sig",  "charset": "0-9a-fA-F", "exact_len": 64}
  ],
  "body_contains": []
}
```

Field rules (omit a field, or set it to null / [], when the task puts no condition on it):

- `sid` / `rev`: the sid the task statement requires (default 1000001 only when the task names none; the task text wins over comments in the rules file and over the examples here) and revision. Exactly one rule is written; it must be the only sid that ever fires.
- `msg`: short and specific; no `"` or `;`.
- `method`: exact, case-sensitive HTTP method (`http.method` + `bsize`).
- `uri.match`:
  - `exact_path` (default for "exact path"): the path must equal `value`; a `?query` suffix is allowed. `/telemetry/v2/report2` and `/x/telemetry/v2/report` do not match.
  - `exact`: the whole normalized URI equals `value` (query string not allowed).
  - `prefix`: URI starts with `value`. `contains`: `value` anywhere in the URI.
- `headers[]`: header names always match case-insensitively (HTTP header names are case-insensitive; the training traffic deliberately sends `x-tlm-mode` in lowercase). `value_nocase` (default false) makes the value case-insensitive too; set it true only if the task says the value is case-insensitive. `match`: `exact` (whole trimmed value equals `value`, default) or `contains`.
- `body_params[]`: one entry per required `name=value` parameter in the request body (`application/x-www-form-urlencoded`, `&`-separated, matched raw, not URL-decoded). The parameter must start at the body start or right after `&`, and the WHOLE value (up to the next `&` or end of body) must be in `charset` with the length bounds.
  - `charset`: the inside of a regex `[...]` class, e.g. `A-Za-z0-9+/` (Base64, includes `+` and `/`), `0-9a-fA-F` (hex, both cases), `A-Za-z0-9_-` (base64url). No `[ ] " ;`.
  - `min_len` / `max_len` (inclusive, null = unbounded) or `exact_len`. "length >= 80" means `min_len: 80`; "exactly 64 hex characters" means `exact_len: 64` (so 63 and 65 do not match).
  - `allow_padding`: allow up to two trailing `=` after the Base64 characters (not counted in the length). Use true for standard Base64 blobs; false when the task lists the exact alphabet without `=` (e.g. base64url).
- `body_contains[]`: extra literal strings that must appear anywhere in the request body.
