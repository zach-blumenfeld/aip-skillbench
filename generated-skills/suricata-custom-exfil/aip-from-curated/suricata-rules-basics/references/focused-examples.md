# Focused examples — composable Suricata fragments

Use these as building blocks. Do not concatenate them blindly — pick the
ones that match the task's stated requirements, then assemble inside the
scaffold below.

## Scaffold

```
alert http any any -> any any (
  msg:"<short, specific>";
  flow:established,to_server;

  # 1) Method constraint
  # 2) Exact path constraint
  # 3) Header constraint
  # 4) Body constraints

  sid:<unique>;
  rev:1;
)
```

## Exact HTTP method

```
http.method;
content:"POST";
```

`http.method;` is required — without it `content:"POST"` can match
inside body bytes.

## Exact URI / path match

```
http.uri;
content:"/telemetry/v2/report";
```

## Header contains a specific field/value

Represent `:` as hex (`|3a|`) to avoid formatting surprises:

```
http.header;
content:"X-TLM-Mode|3a| exfil";
```

## Body contains required parameters

Each `content:` resets relative to the sticky buffer; you must re-state
`http_client_body;` for each match:

```
http_client_body;
content:"blob=";

http_client_body;
content:"sig=";
```

## Regex for 64 hex characters (for `sig=...`)

```
http_client_body;
pcre:"/sig=[0-9a-fA-F]{64}/";
```

## Regex for Base64-ish blob with a length constraint

- Keep the character class fairly strict to avoid false positives.
- Anchor the match to `blob=` so you don't match unrelated Base64-looking
  data.

```
http_client_body;
pcre:"/blob=[A-Za-z0-9+\\/]{80,}/";
```
