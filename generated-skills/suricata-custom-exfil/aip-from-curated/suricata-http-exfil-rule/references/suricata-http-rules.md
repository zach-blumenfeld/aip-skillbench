# Suricata HTTP rule reference (Suricata 7)

Load this when writing or fixing a rule by hand (`rule_override`), or when `suricata -T` rejects the composed rule.

## Rule anatomy

```
alert <proto> <src> <sport> -> <dst> <dport> (msg:"..."; flow:...; <buffer>; content:"..."; pcre:"/.../"; sid:1000001; rev:1;)
```

- `sid` is the unique rule id; `rev` the rule revision. The task requires exactly sid 1000001 to fire.
- `flow:established,to_server;` constrains direction/state to client requests.
- Use `alert http any any -> any any`: protocol detection finds HTTP on any port (the training traffic uses 8080), and `any` avoids depending on `HOME_NET`/`EXTERNAL_NET`.
- Keep the rule on one line; keep `msg` specific.

## Content, PCRE, buffers

- `content:"...";` matches fixed bytes. Write `:` `;` `"` `\` `|` as hex: `|3a|`, `|3b|`, `|22|`, `|5c|`, `|7c|` (e.g. `content:"X-TLM-Mode|3a| exfil";`).
- `nocase;` after a content makes it case-insensitive. `bsize:N;` pins the buffer length (exact match with one content). `startswith;` / `endswith;` anchor a content.
- `pcre:"/.../flags";` for patterns like "N hex chars" or "Base64-ish". A pcre after a sticky buffer runs on that buffer. Inline `(?i:...)` makes only part of a pattern case-insensitive.
- Sticky buffers (protocol aware; prefer them so strings in one part of the stream cannot satisfy a condition about another part). Every content/pcre after a buffer keyword applies to it until the next buffer keyword:
  - `http.method` — request method
  - `http.uri` — normalized request URI (path + query)
  - `http.header` — all request headers, one `Name: value\r\n` line each
  - `http.request_body` — request body (dechunked). Legacy name: `http_client_body`.

## Gotchas

- `http_client_body` (and `http_uri`, `http_header`, `http_method`) are legacy CONTENT MODIFIERS: they go AFTER the content they modify (`content:"blob="; http_client_body;`). Written before a content as if sticky (`http_client_body; content:"blob=";`) they modify the previous content instead, or fail to parse. Use the sticky names above.
- `content:"POST";` without `http.method;` can match inside the body.
- Header names are case-insensitive and the traffic sends `x-tlm-mode` lowercase: a literal `content:"X-TLM-Mode|3a| exfil";` without `nocase` never fires. Match the name case-insensitively; keep the value case-sensitive unless the task says otherwise.
- Unanchored `sig=[0-9a-fA-F]{64}` also matches 65+ hex characters. Enforce "exactly 64" with boundaries: `/(?:^|&)sig=[0-9a-fA-F]{64}(?:&|$)/`.
- Anchor parameter names: `(?:^|&)blob=` so `xblob=` or `noblob=` cannot satisfy it, and anchor `blob=` so unrelated Base64 elsewhere does not count.
- Base64 includes `+` and `/` (the training blob contains both): class `[A-Za-z0-9+\x2f]`, optional `={0,2}` padding. Too permissive a class causes false positives, too strict (alnum only) false negatives.
- Escaping inside a rules file: write `/` inside a pcre as `\/` or `\x2f`, not `\\/` (that adds a literal backslash to the class). Never put a raw `;` or `"` inside a pcre; use `\x3b` / `\x22`.
- "Exact path" with `content:"/telemetry/v2/report";` alone also matches `/telemetry/v2/report2` and `/x/telemetry/v2/report`; add `startswith;` plus `pcre:"/^\x2ftelemetry\x2fv2\x2freport(?:\x3f|$)/";` (or `bsize` when no query string is allowed).

## Scaffold (the shape scripts/build_and_check.py composes)

```
alert http any any -> any any (msg:"TLM exfil"; flow:established,to_server;
  http.method; content:"POST"; bsize:4;
  http.uri; content:"/telemetry/v2/report"; startswith; pcre:"/^\x2ftelemetry\x2fv2\x2freport(?:\x3f|$)/";
  http.header; content:"x-tlm-mode"; nocase; pcre:"/(?:^|\n)(?i:X\x2dTLM\x2dMode):[ \t]*exfil[ \t]*\r?(?:\n|$)/";
  http.request_body; content:"blob="; pcre:"/(?:^|&)blob=[A-Za-z0-9+\x2f]{80,}={0,2}(?:&|$)/";
  content:"sig="; pcre:"/(?:^|&)sig=[0-9a-fA-F]{64}(?:&|$)/";
  sid:1000001; rev:1;)
```

(Shown wrapped; the rules file holds it on one line.)
