---
name: pcap-triage-tshark
description: Fast workflow to inspect PCAPs and extract protocol-level details using tshark. Use when a PCAP needs HTTP-level inspection — listing requests, filtering by method/host, extracting fields, following TCP streams, or exporting raw bytes — typically as the front-half of designing or validating a detection signature.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires tshark (wireshark-cli) and bash. PCAP files reachable on the local filesystem.
---

```yaml
purpose: >
  Inspect PCAPs and extract HTTP-level details with tshark. Covers the fast
  filter → narrow → extract → follow → export loop used to find request
  shapes (method, URI, headers, body bytes) and to confirm exactly where a
  candidate string lives before encoding it into a detection signature.

trigger_when:
  - A PCAP file needs inspection for HTTP-level evidence (requests, headers, body).
  - You need to confirm where a string lives — URL query, header, or request body — before writing a rule.
  - You don't yet know whether a candidate pattern is present in a sample PCAP.
  - You need to distinguish invariant from variable parts of a request to pick literal-match vs regex constraints.

do_not_use_when:
  - PCAP carries only non-HTTP traffic (TLS, DNS, raw TCP). The filters here assume HTTP; you'll see empty output and learn nothing.
  - You already have Suricata `eve.json` output for the same capture — query that with jq instead of re-parsing the PCAP.

steps:
  - name: broad-protocol-filter
    description: >
      Start broad to see what HTTP traffic exists. Run
      `tshark -r <file.pcap> -Y http`. Skim volume and request shapes before narrowing.
    inputs:
      - name: pcap-path
        type: string
        description: Absolute path to the PCAP to inspect.
    outputs:
      - name: http-overview
        type: string
        description: One-line-per-frame listing of HTTP traffic.

  - name: narrow-by-method-or-host
    description: >
      Narrow to the request shape of interest. Examples:
      `-Y 'http.request.method == "POST"'`, `-Y 'http.host == "telemetry.example"'`.
      Stack conditions with `&&`. Goal: a small, homogeneous candidate set.
    inputs:
      - name: http-overview
        type: string
    outputs:
      - name: candidate-frames
        type: string

  - name: extract-request-fields
    description: >
      Pull structured fields so request shape is readable. Use `-T fields` with one
      `-e` per field, e.g.
      `tshark -r <file.pcap> -Y http.request -T fields -e frame.time -e ip.src -e tcp.srcport -e http.request.method -e http.request.uri`.
      Add `-e http.host`, `-e http.user_agent`, `-e http.header` as needed.
    inputs:
      - name: candidate-frames
        type: string
    outputs:
      - name: structured-rows
        type: string

  - name: follow-tcp-stream
    description: >
      Read a single request/response end to end — headers and body together — with
      `tshark -r <file.pcap> -z follow,tcp,ascii,0`. Change `0` for other streams;
      use the `tcp.stream eq <n>` display filter to find the right index first.
    inputs:
      - name: candidate-frames
        type: string
    outputs:
      - name: stream-transcript
        type: string

  - name: export-payload-bytes
    description: >
      When fields are ambiguous (encoding, casing, chunked transfer), print raw bytes
      with `-x`: `tshark -r <file.pcap> -Y http -x`. Use this to confirm the exact
      byte sequence a signature must match.
    inputs:
      - name: candidate-frames
        type: string
    outputs:
      - name: raw-bytes
        type: string

  - name: summarize-http-requests
    description: >
      Alternative quick-start entry point. Bundled helper prints the first 50 HTTP
      request rows and counts frames matching the `X-TLM-Mode: exfil` header heuristic.
      Treat the count as best-effort — confirm with `extract-request-fields` or
      `export-payload-bytes` before trusting it as ground truth.
    script: scripts/summarize_http_requests.sh
    inputs:
      - name: pcap-path
        type: string
        description: Absolute path to the PCAP file (e.g. /root/pcaps/train_pos.pcap).
    outputs:
      - name: request-summary
        type: string
        description: First 50 request rows plus a header-match count.

  - name: locate-strings-precisely
    description: >
      For every candidate literal, confirm its protocol location — URL query,
      request header, or request body. The same byte sequence can appear in
      different places across captures, and each maps to a different Suricata
      sticky buffer (`http.uri`, `http.header`, `http.request_body`). Locating
      wrong puts the rule on the wrong buffer.
    inputs:
      - name: structured-rows
        type: string
      - name: stream-transcript
        type: string
      - name: raw-bytes
        type: string
    outputs:
      - name: string-location-map
        type: object
        description: For each candidate string, its protocol location (uri | header | body).

  - name: classify-invariant-vs-variable
    description: >
      For each candidate string, note which bytes are invariant across captures
      (must match literally) versus variable (need a length, charset, or regex
      constraint). This is the input the rule-writing skill consumes.
    inputs:
      - name: string-location-map
        type: object
    outputs:
      - name: invariant-variable-notes
        type: object

anti_patterns:
  - Starting with a narrow filter before confirming the protocol is present — empty output reads as "nothing here" when the filter was just wrong.
  - Encoding a literal into a header buffer when the bytes actually live in the body, or vice versa. Confirm with `-T fields` or `-x` first.
  - Reading only the request frame and skipping the response — `follow,tcp,ascii,<n>` catches reply codes and chunked-encoding quirks single-frame views miss.
  - Trusting `http.header contains "X"` as ground truth across captures. Header casing and folding vary; cross-check with `-x` raw bytes when a count looks off.
  - Treating the summarizer's exfil-header count as definitive. It is a heuristic; the rule-writing step needs a string location confirmed by `-T fields` or `-x`.
```
