---
name: pcap-triage-tshark
description: Fast tshark workflow to triage HTTP traffic in a PCAP — list requests, narrow by method/host/header, follow TCP streams, and export payload bytes. Use when you need to understand what HTTP requests, headers, paths, or body fields are present in a `.pcap` before writing a signature, rule, or parser. Keywords - tshark, pcap, HTTP triage, packet capture, follow stream, http.header, http.request.uri, X-TLM-Mode, exfil header.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Requires `tshark` (Wireshark CLI) on PATH and read access to the target `.pcap` files.
---

```yaml
purpose: >
  Triage a PCAP to learn the shape of its HTTP traffic — methods, paths,
  headers, body fields, and per-flow request/response pairs — using tshark.
  Goal is to surface where signal lives (URL vs header vs body) so a downstream
  signature, rule, or parser can target the right fields without guessing.

trigger_when:
  - A `.pcap` is available and the agent needs to know what HTTP traffic it contains before writing a Suricata/Snort/Zeek rule or other signature.
  - The agent must confirm where a string lives in HTTP — request line, header, URL query, or body — before matching on it.
  - Multiple PCAPs (e.g., positive vs negative samples) need a side-by-side comparison of headers and body fields.
  - "User mentions `tshark`, `wireshark`, `pcap triage`, \"follow stream\", or asks \"what's in this capture\"."
  - "Investigating suspected exfiltration over HTTP and needing to confirm header names (e.g., `X-TLM-Mode: exfil`), paths (e.g., `/telemetry/v2/report`), or body markers (e.g., `blob=`, `sig=`)."

do_not_use_when:
  - The PCAP carries non-HTTP protocols only (DNS, TLS without decryption, raw TCP) — pick a protocol-appropriate dissector instead.
  - You already know the exact field locations and only need to write the rule; skip triage and go straight to authoring.
  - "`tshark` is unavailable in the environment — install `wireshark-cli`/`tshark` first, or fall back to `tcpdump`/Python parsing."

scope_and_approval: >
  Read-only on the PCAP. Every step is a `tshark -r` invocation against a local
  file. No writes, no network egress, no destructive actions. Safe to run
  without confirmation.

steps:
  - name: quick-summary
    description: >
      Run the bundled helper to print the first 50 HTTP requests (time, src,
      method, URI) and a best-effort count of `X-TLM-Mode: exfil` headers
      across the PCAP. Use this as the first pass for any PCAP that may
      contain exfil-style traffic.
    script: scripts/summarize_http_requests.sh
    inputs:
      - name: pcap_path
        type: string
        description: Absolute path to the `.pcap` to summarize (e.g., `/root/pcaps/train_pos.pcap`).
    outputs:
      - name: request_summary
        type: string
        description: Stdout — request table plus the exfil-header count line.

  - name: broad-filter
    description: >
      List HTTP traffic broadly, then narrow. Start with `tshark -r file.pcap
      -Y http` to see every HTTP packet, then add a display-filter clause to
      focus — e.g., `-Y 'http.request.method == "POST"'` or `-Y 'http.host
      == "example.com"'`. Adjust the filter expression to the question you
      are answering; do not commit to one filter until you have seen the
      broad view.
    inputs:
      - name: pcap_path
        type: string
    outputs:
      - name: filtered_packets
        type: string
        description: tshark stdout — one line per matching packet.

  - name: field-extract
    description: >
      Print structured request fields with `-T fields`. Canonical invocation -
      `tshark -r file.pcap -Y http.request -T fields -e frame.time -e ip.src
      -e tcp.srcport -e http.request.method -e http.request.uri`. Swap or
      extend `-e` flags to surface other fields (`http.host`,
      `http.user_agent`, `http.content_type`, `http.file_data`, individual
      `http.header` instances). Use this to confirm where a string actually
      appears — request URI vs header vs body.
    inputs:
      - name: pcap_path
        type: string
      - name: tshark_fields
        type: list[string]
        description: List of `-e` field names to extract (default - frame.time, ip.src, tcp.srcport, http.request.method, http.request.uri).
        nullable: true
    outputs:
      - name: field_table
        type: string

  - name: follow-stream
    description: >
      View a request/response conversation end-to-end with `tshark -r
      file.pcap -z follow,tcp,ascii,0`. The trailing `0` is the stream
      index; bump it (`,1`, `,2`, …) to walk subsequent streams. Use this
      when you need to read the full HTTP body — including multi-line POST
      payloads and exact header ordering — that a packet-by-packet view
      fragments.
    inputs:
      - name: pcap_path
        type: string
      - name: stream_index
        type: integer
        description: Zero-based TCP stream index. Defaults to 0; increment to walk other streams.
        nullable: true
    outputs:
      - name: stream_transcript
        type: string

  - name: export-bytes
    description: >
      Dump raw payload bytes with `-x` (e.g., `tshark -r file.pcap -Y http
      -x`) when the printable rendering hides what you need — non-ASCII
      payloads, embedded binary, suspected base64 blobs, signature fields.
      The hex/ASCII side-by-side reveals byte-exact content.
    inputs:
      - name: pcap_path
        type: string
    outputs:
      - name: byte_dump
        type: string

  - name: narrow-and-note
    description: >
      Iterate filters from broad to narrow until you have one flow or stream
      pinned. For every match, record - which fields are invariant across
      the sample set (good rule anchors) and which are variable (must be
      matched by regex/length/charset, not literal). Note exact header names
      (case-sensitive in some matchers), exact path strings, and body-field
      delimiters - this is what the downstream rule/parser will key on.
    outputs:
      - name: triage_notes
        type: object
        description: Structured notes - invariants list, variables list, and per-string field-location map.

modes:
  - name: quick
    body: >
      Run `quick-summary` only. Sufficient when you just need to know whether
      a suspect header or path appears at all, and roughly how often.
  - name: full
    body: >
      Run the full chain - `quick-summary` → `broad-filter` → `field-extract`
      → `follow-stream` (per interesting stream) → `export-bytes` (only when
      bytes are non-printable) → `narrow-and-note`. Use when authoring a
      signature or parser and you need byte-exact certainty on field locations.

integrations:
  - partner: suricata-rules-basics
    body: >
      `pcap-triage-tshark` surfaces the exact header names, path strings, and
      body delimiters; `suricata-rules-basics` turns those into rule keywords
      (`content`, `http.uri`, `http.header`, `pcre`, etc.). Run triage first,
      then hand the invariants to rule authoring.
  - partner: suricata-offline-evejson
    body: >
      After a rule is drafted, replay the same PCAPs through Suricata and
      inspect `eve.json` to confirm the rule fires on positives and stays
      silent on negatives. If `eve.json` shows misses, return to
      `pcap-triage-tshark` to re-check field locations.

scenarios:
  - need: >
      Confirm that an HTTP POST to `/telemetry/v2/report` carries an
      `X-TLM-Mode: exfil` header in a sample PCAP.
    context: User is investigating suspected exfil over HTTP telemetry; PCAP at `/root/pcaps/train_pos.pcap`.
    action: >
      Run `scripts/summarize_http_requests.sh /root/pcaps/train_pos.pcap`. If
      the exfil-header count is non-zero, drill in with `tshark -r
      /root/pcaps/train_pos.pcap -Y 'http.request.method == "POST" &&
      http.request.uri == "/telemetry/v2/report"' -T fields -e frame.number
      -e http.host -e http.request.uri` and then `-Y http.request -x` to
      eyeball the raw header line.
    outcome: >
      Confirmed location of `X-TLM-Mode: exfil` (request header, not URL or
      body) and the literal path `/telemetry/v2/report` — both safe to use
      as rule anchors.

  - need: Determine whether a body field looks like a fixed-length hex signature or a variable-length base64 blob.
    context: Suspected exfil POSTs contain `blob=` and `sig=` parameters and the rule must distinguish them by charset and length.
    action: >
      Follow the relevant TCP stream - `tshark -r file.pcap -z
      follow,tcp,ascii,0` - to see the full POST body. Confirm `sig=` is
      exactly 64 hex chars and `blob=` is a base64-charset string ≥80 chars
      across multiple samples. Cross-check with `-Y http.request -x` on a
      sample where rendering looks suspicious.
    outcome: Rule author can encode `sig=[0-9a-fA-F]{64}` and `blob=[A-Za-z0-9+/=]{80,}` with confidence.

  - need: Compare positive vs negative sample PCAPs to find the discriminator.
    context: Two PCAPs - `train_pos.pcap` (exfil) and `train_neg.pcap` (benign telemetry). Need to know what differs.
    action: >
      Run `scripts/summarize_http_requests.sh` against each PCAP. Diff the
      method/URI tables and the exfil-header counts. For any URI that
      appears in both, follow one stream from each with `-z
      follow,tcp,ascii,N` and visually compare headers and body fields.
    outcome: Identified invariants (path, header name) and variables (blob/sig content) — fed into rule authoring.

anti_patterns:
  - Writing a rule before confirming the field location — strings can live in the URL query, a header, or the body, and the matcher keyword differs by location.
  - Treating a single PCAP as ground truth — invariant-vs-variable judgments need multiple samples, ideally positive and negative.
  - Skipping `-x` when the rendered text looks suspicious — non-printable bytes or unusual encodings will mislead a regex written from the ASCII view.
  - Hard-coding the TCP stream index `0` without checking whether the PCAP has multiple streams — the conversation you want may be at index 3 or 17.
  - Letting `tshark` print all packets when you only need request lines — `-Y http.request` is almost always tighter than `-Y http` for request-level questions.
```
