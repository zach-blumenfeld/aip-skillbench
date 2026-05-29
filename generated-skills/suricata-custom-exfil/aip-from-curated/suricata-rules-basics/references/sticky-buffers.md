# HTTP sticky buffers — quick reference

Sticky buffers scope a `content:` or `pcre:` match to a specific protocol
region. Without one, the match runs against the whole TCP stream and you get
false positives (e.g. the literal `POST` appearing inside a body).

| Buffer | Scope | Use for |
| --- | --- | --- |
| `http.method` | Request method | `GET`, `POST`, ... |
| `http.uri` | Request URI (path + query) | Exact path match, path prefix |
| `http.header` | Request headers, normalized | Named header presence/value |
| `http_client_body` | Request body bytes | Form params, JSON fields, blob/sig values |

## Usage shape

A sticky buffer is a keyword on its own line; every `content:` / `pcre:` that
follows applies to that buffer until another buffer keyword appears.

```
http.method;
content:"POST";

http.uri;
content:"/telemetry/v2/report";

http.header;
content:"X-TLM-Mode|3a| exfil";

http_client_body;
content:"blob=";
http_client_body;
pcre:"/blob=[A-Za-z0-9+\/]{80,}/";

http_client_body;
content:"sig=";
http_client_body;
pcre:"/sig=[0-9a-fA-F]{64}/";
```

## Hex-escape convention

Inside a `content:"..."` string, escape any character that would confuse
the rule parser (most commonly `:` and `;`) using its hex byte wrapped in
pipes. `:` becomes `|3a|`, `;` becomes `|3b|`.

```
content:"X-TLM-Mode|3a| exfil";   # matches "X-TLM-Mode: exfil"
```

## Anchoring PCRE inside a body buffer

`http_client_body` scopes the regex to the request body, but the regex
itself still has to anchor to the parameter name so it doesn't match
unrelated Base64-looking bytes elsewhere in the body.

```
pcre:"/blob=[A-Za-z0-9+\/]{80,}/"   # anchored to blob=
pcre:"/sig=[0-9a-fA-F]{64}/"        # anchored to sig=
```

## When not to use a sticky buffer

If the protocol parser hasn't classified the traffic as HTTP (e.g. you're
matching raw TCP or a non-HTTP custom protocol), HTTP sticky buffers will
match nothing. Fall back to raw `content:` matches with explicit `offset`,
`depth`, or `pcre:` anchors instead.
