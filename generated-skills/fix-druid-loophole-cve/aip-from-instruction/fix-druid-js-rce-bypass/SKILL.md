---
name: fix-druid-js-rce-bypass
description: Patch Apache Druid 0.20.0 against the authenticated JavaScript-RCE bypass where an empty-string JSON key (`""`) inside a `javascript` filter/transform/aggregator spec overrides the injected JavaScriptConfig and lets attacker-controlled Nashorn code reach `java.lang.Runtime`. Use when the user asks to fix the Druid 0.20.0 loophole/CVE-2021-25646, patch the empty-key JS exploit reaching `/druid/indexer/v1/sampler`, or build a Druid indexing-service JAR that blocks the published proof-of-concept while keeping legitimate JS filters working. Covers locating the vulnerable JS handlers, drafting a defense-in-depth fix, capturing the diff as patch files under `/root/patches/`, applying it to `/root/druid/`, and rebuilding with the exact Maven invocation the verifier expects (web-console skipped, code-quality plugins skipped, `-pl indexing-service -am`).
compatibility: Apache Druid 0.20.0 source tree at /root/druid (git repo). Requires Maven, JDK 8, git. Patch files land in /root/patches/. The verifier deploys indexing-service/target/*.jar to /opt/druid/lib/ and restarts the server.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Close the empty-string-JSON-key bypass in Apache Druid 0.20.0's JavaScript
  filter/transform/aggregator/extraction handlers, so the published exploit
  against `/druid/indexer/v1/sampler` is blocked while legitimate JS specs
  continue to work. Produce patch files under `/root/patches/`, apply them
  to the git tree at `/root/druid/`, and rebuild only what the verifier
  ships — the indexing-service JAR — using the exact Maven invocation the
  verifier expects (web-console and all code-quality plugins skipped).

trigger_when:
  - 'User asks to fix the Druid 0.20.0 loophole, CVE-2021-25646, or the "empty key" JavaScript RCE.'
  - 'A task supplies an exploit POST to /druid/indexer/v1/sampler containing a javascript filter with an empty "" key whose value enables the JavaScript config.'
  - 'User asks to patch Druid 0.20.0 in /root/druid/ and emit patch files to /root/patches/.'
  - 'User asks to build a Druid indexing-service JAR that blocks the published JS-RCE proof-of-concept.'

do_not_use_when:
  - Target is a Druid version other than 0.20.0 — patch locations and
    Jackson behavior differ across releases; re-verify before reusing.
  - The task is to *exploit* Druid, audit unrelated CVEs, or modify
    runtime configuration (e.g. `druid.javascript.enabled`) instead of
    patching source.
  - The build environment does not provide Maven + JDK 8 at `/root/druid/`.

scope_and_approval: >
  All edits are local to `/root/druid/` (a git working tree) and
  `/root/patches/` (output). The skill never pushes commits, never modifies
  `/opt/druid/`, and never restarts services — the verifier owns deployment.
  Do not weaken or remove the existing `JavaScriptConfig.isEnabled()` check;
  the fix *strengthens* it. Do not edit `pom.xml` files to disable
  individual checks — pass the documented `-D*.skip=true` flags on the
  Maven command line instead.

steps:
  - name: read-vulnerability-details
    description: >
      Load `references/vulnerability-details.md` for the bypass mechanics,
      the expected patch sites, and the layered fix strategy. The exploit
      shape (`"": {"enabled": true}` inside a `javascript` spec) and the
      Jackson-override mechanism are non-obvious and must be understood
      before editing code.

  - name: locate-js-handlers
    description: >
      Run `scripts/find-js-handlers.sh /root/druid` to list every Java
      class that uses `JavaScriptConfig`, every `@JacksonInject
      JavaScriptConfig` constructor parameter, and the sampler endpoint
      class. These are the patch sites. Expect hits in
      `processing/src/main/java/org/apache/druid/query/filter/JavaScriptDimFilter.java`,
      `.../segment/filter/JavaScriptFilter.java`,
      `.../segment/transform/JavaScriptTransform.java`,
      `.../query/aggregation/JavaScriptAggregatorFactory.java`,
      `.../query/aggregation/post/JavaScriptPostAggregator.java`, and
      `.../query/extraction/JavaScriptExtractionFn.java`.
    depends_on: [read-vulnerability-details]

  - name: design-defense-in-depth
    description: >
      Pick at least two layers from `references/vulnerability-details.md`.
      Default combination: (a) add `@JsonAnySetter` that throws on any
      unmapped key in every JS-handler class so `""` is rejected at
      deserialization, AND (b) gate every script-compile/run path on the
      `@JacksonInject`-supplied `JavaScriptConfig.isEnabled()` stored in a
      `private final` field that no JSON property can replace. Optionally
      add (c) a sampler-resource pre-check that walks the parsed JSON and
      rejects any object with a zero-length key.
    depends_on: [locate-js-handlers]

  - name: edit-source
    description: >
      Apply the chosen layers to each handler class identified in
      `locate-js-handlers`. Keep edits minimal and uniform across classes
      so the patch is easy to review. Do not relax `JavaScriptConfig`
      defaults or change `pom.xml` files.
    depends_on: [design-defense-in-depth]

  - name: write-patch-file
    description: >
      Capture the working-tree diff as patch file(s) under `/root/patches/`
      with `scripts/make-patch.sh combined cve-2021-25646.patch` (single
      file, recommended) or `scripts/make-patch.sh per-file` (one per
      class). The output is unified-diff format produced by `git diff`, so
      it re-applies cleanly with `git apply` or `patch -p1`.
    depends_on: [edit-source]

  - name: rebuild
    description: >
      Run `scripts/build-druid.sh /root/druid` (which executes the exact
      Maven invocation the task specifies). The build must skip
      `web-console` (OOM otherwise) and skip checkstyle, pmd,
      forbiddenapis, spotbugs, animal-sniffer, enforcer, jacoco, and
      dependency-check (these reject patched files on style/policy
      grounds). The `-pl indexing-service -am` selector builds only what
      the verifier deploys.
    depends_on: [write-patch-file]

  - name: verify-artifact
    description: >
      Confirm `indexing-service/target/druid-indexing-service-0.20.0.jar`
      (or a same-named-pattern JAR) exists and is newer than the build
      start. The verifier copies this JAR into `/opt/druid/lib/`; if it is
      missing or stale, the patch will not be deployed.
    depends_on: [rebuild]

decisions:
  - signal: >
      `scripts/find-js-handlers.sh` lists JS classes but none declare
      `@JacksonInject JavaScriptConfig` in their `@JsonCreator`.
    action: >
      Inspect each `@JsonCreator` constructor manually — older Druid code
      sometimes injects via field setter or a `Supplier<JavaScriptConfig>`.
      Patch wherever the config is resolved, plus add Layer 1
      (`@JsonAnySetter` reject) on all JS-named classes regardless.

  - signal: >
      The patch compiles but the published exploit still succeeds against
      a freshly-built JAR.
    action: >
      Re-check that the script-compile path (the method that hands the
      function string to Nashorn) reads from a `private final` config
      field set only from the injected parameter. The bypass survives if
      *any* JS handler still resolves config from a JSON-deserialized
      field.

  - signal: >
      Maven fails with `OutOfMemoryError` during the web-console module.
    action: >
      The `-pl '!web-console'` exclusion is missing or mistyped. The
      single quotes around `!web-console` are required so the shell does
      not interpret `!`. Re-run `scripts/build-druid.sh` verbatim.

  - signal: >
      Maven fails with a checkstyle / spotbugs / forbiddenapis /
      animal-sniffer / enforcer / jacoco / dependency-check error on the
      patched file.
    action: >
      One of the `-D*.skip=true` flags is missing. Run
      `scripts/build-druid.sh` which passes the full set. Do not edit the
      module's `pom.xml` to disable checks — the verifier may rebuild from
      the patch and expects the source pom unchanged.

  - signal: >
      Maven succeeds but `indexing-service/target/` is empty or contains
      only the parent POM.
    action: >
      The `-am` flag was dropped. Re-run with `-pl indexing-service -am`
      so dependent modules build first and the indexing-service JAR is
      produced.

  - signal: >
      A legitimate (non-exploit) `javascript` filter is now rejected with
      "Unknown property" even though it contains no empty key.
    action: >
      The `@JsonAnySetter` is firing on a legitimately-unmapped optional
      field. Tighten the check to reject only zero-length keys
      (`key == null || key.isEmpty()`) rather than every unknown key, OR
      add the missing `@JsonProperty` annotations to the constructor for
      the legitimate field.

scenarios:
  - need: >
      Block the published proof-of-concept that POSTs a `javascript` filter
      with `"": {"enabled": true}` to `/druid/indexer/v1/sampler`.
    context: >
      `find-js-handlers.sh` shows `JavaScriptDimFilter.java`,
      `JavaScriptTransform.java`, and three other JS classes all carrying
      `@JacksonInject JavaScriptConfig` in their `@JsonCreator`.
    action: >
      Add `@JsonAnySetter` rejecting zero-length keys in each of the five
      classes; mark each class's `config` field `private final`; gate the
      script-compile method on `Preconditions.checkState(config.isEnabled())`.
      Capture the diff via `make-patch.sh combined cve-2021-25646.patch`.
      Rebuild via `build-druid.sh`.
    outcome: >
      Exploit payload returns 4xx with "Unknown property ''", well-formed
      JS specs with `druid.javascript.enabled=true` still execute, and
      `indexing-service/target/druid-indexing-service-0.20.0.jar` is ready
      for the verifier to deploy.

  - need: >
      Hand the verifier per-file patches instead of one combined file
      because the reviewer wants to inspect changes class-by-class.
    action: >
      After `edit-source`, run `scripts/make-patch.sh per-file`. Each
      modified class becomes `/root/patches/<ClassName>.patch`. The
      rebuild step is identical.
    outcome: >
      `/root/patches/` contains one unified-diff file per touched class,
      each independently re-appliable with `git apply` or `patch -p1`.

anti_patterns:
  - Editing only `JavaScriptConfig.java` (e.g. forcing `enabled = true`
    or `false` in the constructor). The bypass works by *replacing* the
    injected config; hardening the class itself does not stop replacement.
  - Patching only the filter that the published exploit happens to use
    (`JavaScriptDimFilter`). Transforms, aggregators, post-aggregators,
    and extraction functions take the same JSON shape and are equally
    exploitable — fix all of them.
  - Disabling the JS extension globally as the "fix". The verifier expects
    legitimate JS specs to keep working when the operator has opted in.
  - Editing `pom.xml` files to silence checkstyle / spotbugs / etc. The
    verifier may re-run the build from the patch with the original poms.
    Pass the `-D*.skip=true` flags on the command line instead.
  - Dropping the `-am` from `-pl indexing-service -am`. Without it, the
    `processing` module (where most JS handlers live) is not rebuilt and
    the indexing-service JAR pulls in the unpatched classes.
  - Removing the quotes around `!web-console`. The shell expands `!` as
    a history reference and the exclusion silently fails, after which the
    web-console module OOMs the build.
  - Re-running `mvn` from a directory other than `/root/druid/`. The
    multi-module reactor must start at the repo root.
  - Writing patches by hand instead of `git diff`. Hand-rolled hunks
    routinely fail to apply because of whitespace or context drift.
```
