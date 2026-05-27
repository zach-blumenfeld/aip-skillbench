---
name: jackson-security
description: Security considerations for Jackson JSON deserialization in Java applications. Covers timing of validation, raw input interception, and common deserialization attack patterns (empty key, polymorphic type handling, duplicate keys, nested payloads). Use when reviewing or modifying Java code that calls Jackson's readValue, auditing a JSON-accepting endpoint for deserialization safety, or investigating a Jackson-related CVE.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Security knowledge for Jackson JSON deserialization in Java applications.
  Jackson transforms JSON text into Java objects inside a single readValue
  call — interpreting structure, resolving types, handling special keys, and
  instantiating objects all in one step. That step is the attack surface, and
  the resulting Java object retains no trace of how it was built. This skill
  names the structural attack patterns that survive ordinary
  post-deserialization validation and how to intercept them on the raw input.

trigger_when:
  - Reviewing or modifying Java code that calls Jackson's readValue or otherwise deserializes JSON via Jackson.
  - Auditing a JSON-accepting endpoint (Spring MVC, JAX-RS, Dropwizard, etc.) for deserialization safety.
  - Investigating a Jackson-related CVE, advisory, or "loophole" bug.
  - Designing validation logic for JSON input that will later be parsed by Jackson.
  - Configuring or reviewing ObjectMapper settings, @JsonTypeInfo annotations, or default typing.

do_not_use_when:
  - Working with non-Jackson JSON libraries (Gson, fastjson, org.json) — attack details and defaults differ.
  - Validating already-constructed POJOs that never originated from external JSON input.

steps:
  - name: locate-deserialization-boundary
    description: >
      Find where untrusted JSON enters Jackson. The relevant lifecycle is:
      (1) HTTP request arrives with JSON body, (2) framework deserializes
      JSON → Java object (Jackson runs here), (3) handler receives the Java
      object, (4) handler validates, (5) handler processes. The attack
      surface is step 2 — by the time the handler sees the object, any
      parsing-time effect has already executed.
  - name: validate-raw-input-before-readvalue
    description: >
      Inspect the raw JSON string or token stream before calling readValue.
      Post-deserialization validation examines the result, not the process,
      and cannot see structural artifacts — empty keys, type directives,
      duplicate keys — that have already influenced object construction or
      triggered side effects. This is the fundamental blind spot the skill
      exists to close.
  - name: check-empty-key
    description: >
      Detect and handle the empty-string key (""). JSON permits it (RFC 8259)
      and Jackson parses it without error, but some configurations assign it
      special meaning — injection points that set values on the root object,
      property override via @JsonAnySetter or custom deserializers, and
      framework behaviors that read "" as "apply to parent" or "default
      target". After readValue completes there is no standard way to tell
      from the Java object that "" was ever present, so the check must
      happen on the raw JSON.
  - name: check-polymorphic-type-handling
    description: >
      If @JsonTypeInfo or ObjectMapper.activateDefaultTyping is enabled,
      treat type discriminator keys (e.g., "@class", "@type") as
      code-execution primitives. JSON of the form
      {"@class": "com.attacker.MaliciousClass", "command": "..."} causes
      Jackson to attempt instantiation of whatever class is named; if the
      classpath contains exploitable gadget classes, arbitrary code may
      execute during deserialization — before any application code runs.
      Confirm an explicit subtype allowlist (PolymorphicTypeValidator) or
      disable default typing.
  - name: check-duplicate-keys
    description: >
      Jackson's default behavior on duplicate keys is last-value-wins. For
      {"role": "user", "role": "admin"} Jackson yields role = "admin". If
      an upstream WAF, input filter, or validator inspects only the first
      occurrence, the validator and Jackson observe different values and the
      validation can be bypassed. Either reject duplicate keys at the raw
      layer or ensure the validator uses identical semantics.
  - name: check-nested-payloads
    description: >
      Structural checks for empty keys, type directives, and duplicate keys
      must walk the entire JSON tree. Deeply nested structures can bury
      payloads (e.g., config.settings.internal."": "payload") past
      depth-limited string scans. Recurse fully, or parse into a JsonNode
      and traverse, before allowing Jackson to deserialize into the target
      type.

decisions:
  - signal: Code validates the deserialized Java object but never inspects the raw JSON.
    action: Add a pre-deserialization pass over the JSON tree (JsonNode traversal or a streaming token check) that rejects disallowed structural patterns before readValue is called against the target type.
  - signal: "@JsonTypeInfo, @JsonSubTypes, or ObjectMapper.activateDefaultTyping is in use."
    action: Confirm an explicit PolymorphicTypeValidator allowlist is configured. Treat any "@class"/"@type" key from untrusted JSON as untrusted class instantiation and verify the allowlist denies attacker-controlled class names.
  - signal: Untrusted JSON contains an empty-string key ("").
    action: Reject the request, or at minimum log and route through a configuration that has no special handling for "". Do not assume the resulting Java object reflects the empty key's effect — it usually will not.
  - signal: Duplicate keys observed in untrusted JSON.
    action: Reject the request or normalize the JSON before validation so the validator and Jackson agree on which value wins. Do not trust a validator that parses with first-wins semantics if Jackson uses last-wins.
  - signal: Existing validation uses a simple top-level string check or regex on the body.
    action: Replace with a recursive JsonNode walk. Surface-level checks miss nested injection (e.g., {"config":{"settings":{"internal":{"":"payload"}}}}).

scenarios:
  - need: Endpoint accepts a JSON config body and validates the resulting POJO with bean-validation annotations.
    context: Post-deserialization validation only sees the populated Java object; the original raw JSON has been discarded by the framework before the handler runs.
    action: Insert a pre-readValue step that parses to JsonNode and rejects empty keys, type discriminators, and duplicate keys anywhere in the tree.
    outcome: Structural attacks (empty-key injection, polymorphic instantiation, last-wins bypass) are blocked before Jackson constructs the target object.
  - need: Service uses ObjectMapper.activateDefaultTyping for convenience in serializing polymorphic value classes.
    context: Default typing instructs Jackson to honor "@class" hints from incoming JSON.
    action: Disable default typing or configure a PolymorphicTypeValidator allowlist restricted to known safe subtypes; add the raw-input pre-check for "@class"/"@type" keys.
    outcome: Attacker-controlled class names can no longer trigger gadget-class instantiation during readValue.

anti_patterns:
  - Treating Jackson deserialization as a transparent data copy. It is an interpretation step with its own attack surface, executed before any handler code runs.
  - Relying on post-deserialization object validation to catch structural attacks. By the time bean-validation runs, the parsing-time effect has already occurred.
  - Assuming JSON Schema or bean-validation annotations on the POJO would have observed an empty key or a duplicate key. They do not — the Java object retains no trace of those structural artifacts.
  - Checking only the top level of the JSON tree for disallowed patterns. Nested injection survives shallow scans.
  - Leaving default typing or @JsonTypeInfo enabled without an explicit PolymorphicTypeValidator allowlist.
  - Assuming a WAF or upstream validator that parses JSON with different semantics (first-wins on duplicate keys, no handling of empty keys) agrees with Jackson on what the payload means.
```
