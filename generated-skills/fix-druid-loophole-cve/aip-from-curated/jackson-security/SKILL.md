---
name: jackson-security
description: "Security considerations for Jackson JSON deserialization in Java applications: why validation must run on the raw input before readValue() rather than on the resulting object, plus the structural attack patterns Jackson is exposed to — empty-key (\"\") injection, polymorphic @class/@type directives, duplicate-key confusion, and deeply nested variants. Use when securing, patching, or reviewing Java endpoints that deserialize untrusted JSON with Jackson, when fixing a deserialization vulnerability (config override, RCE, gadget chains), or when the user mentions Jackson, readValue, deserialization attacks, or the empty-key bypass."
compatibility: Concerns Java applications that deserialize untrusted JSON with the Jackson (com.fasterxml.jackson) library.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Encapsulates how Jackson turns untrusted JSON into Java objects and why that
  makes input validation a timing problem. Jackson interprets structure,
  resolves types, handles special keys, and runs configured behavior inside a
  single readValue() call, so any attack that rides the parse — empty-key
  injection, polymorphic @class type directives, duplicate keys, nested
  variants — has already fired by the time your code sees the object and
  leaves no trace on it. The defense this skill encodes: validate the raw JSON
  text or bytes before deserialization, never the resulting object.

trigger_when:
  - Securing, patching, or reviewing a Java endpoint that deserializes untrusted JSON with Jackson (ObjectMapper.readValue, @RequestBody, framework auto-binding).
  - A request body can reach readValue() before any application validation runs.
  - Investigating or fixing a deserialization vulnerability (config override, RCE, gadget chains) in a Jackson-based service.
  - User mentions Jackson, readValue, deserialization attacks, the empty-key ("") bypass, @class/polymorphic type handling, or duplicate-key confusion.

do_not_use_when:
  - The JSON is trusted/internal and never crosses a security boundary.
  - The service parses JSON with a non-Jackson library; still validate raw input, but the specific patterns here are Jackson-shaped.
  - The concern is schema/business validation of otherwise-legitimate data, not deserialization-time attacks.

scope_and_approval: >
  scripts/scan_raw_json.py is read-only diagnosis — it inspects a payload and
  reports findings, it changes nothing. Editing source, writing patch files,
  rebuilding, and deploying are write actions; follow the host task's approval
  and verification norms for those.

steps:
  - name: understand-deserialization-timing
    description: >
      Internalize the timing model: Jackson interprets structure, resolves
      types, handles special keys, and instantiates objects all inside one
      readValue() call, and the resulting object keeps no trace of how it was
      built. Read references/jackson-deserialization-attacks.md for the full
      model before designing any fix.
  - name: locate-validation-placement
    description: >
      Find every point where untrusted JSON reaches Jackson (readValue,
      @RequestBody, framework auto-deserialization) and where current
      validation runs relative to it. Any check that runs on the deserialized
      object is too late — parse-time attacks have already executed.
    depends_on: [understand-deserialization-timing]
    outputs:
      - name: deserialization-sites
        type: list[object]
        description: Locations where untrusted JSON is handed to Jackson, with the surrounding validation (if any).
  - name: intercept-raw-input
    description: >
      Capture the raw JSON string or bytes of the request body before it is
      handed to readValue(). This is the only place the attack structure is
      still visible.
    depends_on: [locate-validation-placement]
    inputs:
      - name: deserialization-sites
        type: list[object]
    outputs:
      - name: raw-json
        type: string
        description: The untrusted request body as received, before any deserialization.
  - name: scan-raw-input
    description: >
      Scan the raw input for the structural attack patterns — empty-string
      keys, @-prefixed type directives, and duplicate keys — walking the full
      tree to arbitrary depth. Script-backed so detection is exhaustive and
      consistent rather than an ad-hoc substring check.
    script: scripts/scan_raw_json.py
    depends_on: [intercept-raw-input]
    inputs:
      - name: raw-json
        type: string
    outputs:
      - name: findings
        type: list[object]
        description: Each detected pattern with its type, severity, JSON path, and depth.
      - name: is_malicious
        type: boolean
        description: True if any high-severity pattern was found.
  - name: reject-before-deserializing
    description: >
      If the scan flags any high-severity pattern, reject the request before
      calling readValue() (throw, return 4xx, or filter). For a production fix,
      port scan_raw_json.py's checks into the target application's language as a
      guard that runs on the raw body ahead of deserialization — do not rely on
      validating the object afterward. Keep the guard precise so legitimate
      payloads (no empty key, no type directive, no duplicates) still pass.
    depends_on: [scan-raw-input]
    inputs:
      - name: findings
        type: list[object]
      - name: is_malicious
        type: boolean

scenarios:
  - need: 'A request body carries an empty-string key alongside normal fields, e.g. {"name":"test","":{"enabled":true}}.'
    context: The empty key is valid JSON (RFC 8259) and Jackson parses it without error; after deserialization the object looks normal and gives no sign "" was present.
    action: Scan the raw body before readValue — scan-raw-input flags the empty-key pattern even when nested — and reject.
    outcome: The injection that would have overridden a server-controlled value is blocked before deserialization runs.
  - need: 'A polymorphic payload names its own class, e.g. {"@class":"com.attacker.MaliciousClass","command":"..."}.'
    context: With @JsonTypeInfo enabled, Jackson tries to instantiate the named class; a gadget on the classpath can execute code during deserialization, before your code runs.
    action: scan-raw-input flags the @class type directive on the raw input; reject before readValue.
    outcome: Gadget instantiation never happens because the request is rejected pre-parse.
  - need: 'A payload repeats a key, e.g. {"role":"user","role":"admin"}.'
    context: Jackson keeps the last value ("admin") while an upstream WAF that checked the first occurrence sees "user" — validation and processing disagree.
    action: scan-raw-input inspects the raw key/value pairs rather than a normalized object, so it sees the duplicate and flags it.
    outcome: The validation/processing mismatch is caught instead of silently trusting the first occurrence.
  - need: An attack pattern is buried deep, e.g. an empty key under config.settings.internal.
    context: Depth-limited or top-level-only string checks miss patterns hidden in nested structures.
    action: scan-raw-input walks the entire tree to arbitrary depth and reports the JSON path and depth of each finding.
    outcome: Nested injection is detected where a shallow check would have passed it through.

anti_patterns:
  - Validating the deserialized Java object instead of the raw input — parse-time attacks have already fired and leave no trace on the object.
  - Assuming the resulting object reveals whether an empty key was used; whether and where "" lands depends on Jackson configuration and is not observable from the object.
  - Top-level-only or depth-limited string checks — nested empty keys and type directives slip past them.
  - Trusting a normalizing JSON parser to surface duplicate keys; it collapses them to one value while Jackson keeps the last.
  - Treating "" or @class as harmless because the JSON is well-formed — RFC validity is not safety.
```
