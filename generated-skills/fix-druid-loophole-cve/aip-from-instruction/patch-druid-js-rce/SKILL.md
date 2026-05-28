---
name: patch-druid-js-rce
description: >
  Patch and rebuild Apache Druid 0.20.0 to close the JavaScript
  arbitrary-code-execution vulnerability (CVE-2021-25646 class) where an
  empty-string key ("") in a javascript filter/aggregator/extraction component
  overrides the server's JavaScriptConfig and bypasses
  druid.javascript.enabled. Use when asked to fix a Druid RCE / JavaScript
  loophole, patch @JacksonInject input-override injection in /root/druid, write
  patch files to /root/patches/, and rebuild the patched jar with Maven for
  redeployment.
compatibility: >
  Apache Druid 0.20.0 git checkout at /root/druid; Maven; JDK 8; git. Patch
  files written to /root/patches/. Verifier redeploys the rebuilt jar to
  /opt/druid/lib/.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Close the Apache Druid 0.20.0 JavaScript RCE: components that run
  user-supplied JavaScript (filters, aggregators, extraction functions, etc.)
  receive the server's JavaScriptConfig via an unnamed Jackson @JacksonInject
  parameter. Jackson's default lets request input override that injected value,
  so an attacker supplies a JavaScriptConfig under the empty-string key ("")
  with enabled=true, bypassing druid.javascript.enabled=false and gaining code
  execution. This procedure pins every injection site to the server value
  (useInput = OptBoolean.FALSE), writes the patch files, and rebuilds the jar.
  Behavior is preserved: legitimate JavaScript still runs when the server
  enables it; non-JavaScript requests are unaffected.

trigger_when:
  - Asked to fix / patch an RCE or arbitrary-code-execution vulnerability in Apache Druid (especially 0.20.0).
  - A Druid request bypasses druid.javascript.enabled via an empty-string key ("") inside a javascript filter, aggregator, or extraction component.
  - Hardening Druid against the CVE-2021-25646 class of Jackson @JacksonInject input-override attack.
  - Need to write patch files and rebuild patched Druid with Maven for a verifier that redeploys the jar.

do_not_use_when:
  - The target is not Apache Druid, or the bug is not the JavaScript / @JacksonInject injection class.
  - The Druid version differs materially from 0.20.0 and the @JacksonInject JavaScriptConfig pattern is absent — re-derive the fix from source first.

scope_and_approval: >
  Edits Java source in /root/druid (a git repo), writes patch files to
  /root/patches/, and runs a long Maven build. It does NOT deploy or restart
  Druid — the verifier copies the rebuilt jar to /opt/druid/lib/ and restarts.
  All actions stay inside the task sandbox; nothing external or irreversible.

steps:
  - name: understand-vulnerability
    description: Read references/vulnerability.md to understand the empty-key ("") @JacksonInject input-override mechanism and why useInput = OptBoolean.FALSE fixes it without breaking legitimate JavaScript.

  - name: locate-injection-sites
    description: Enumerate every vulnerable site by running the scanner in check mode over /root/druid; in a fresh tree it lists all un-pinned @JacksonInject JavaScriptConfig parameters. Cross-check with grep for completeness.
    script: scripts/patch_js_injection.py
    depends_on: [understand-vulnerability]
    outputs:
      - name: injection-sites
        type: list[string]
        description: Java files holding an un-pinned @JacksonInject JavaScriptConfig parameter.

  - name: apply-fix
    description: Pin every site to the injected config — rewrite each bare @JacksonInject to @JacksonInject(useInput = OptBoolean.FALSE) and add the OptBoolean import. Idempotent; run `uv run scripts/patch_js_injection.py /root/druid`.
    script: scripts/patch_js_injection.py
    depends_on: [locate-injection-sites]
    inputs:
      - name: injection-sites
        type: list[string]
    outputs:
      - name: modified-files
        type: list[string]
        description: Source files edited in the working tree (the applied fix).

  - name: emit-patch-files
    description: >
      Capture the working-tree edits as the required deliverable:
      `mkdir -p /root/patches && cd /root/druid && git diff >
      /root/patches/cve-druid-js-rce.patch`. The edits are already applied to
      source; this file lets the fix re-apply to a clean checkout via git apply.
    depends_on: [apply-fix]
    inputs:
      - name: modified-files
        type: list[string]
    outputs:
      - name: patch-path
        type: string
        description: Path to the generated patch file under /root/patches/.

  - name: build
    description: Rebuild with the exact verifier-required Maven command via `bash scripts/build_druid.sh /root/druid` (builds indexing-service plus -am dependencies, recompiling the patched processing jar; web-console and all quality gates skipped). Allow several minutes; do not abort early.
    script: scripts/build_druid.sh
    depends_on: [apply-fix]
    outputs:
      - name: built-jars
        type: list[string]
        description: Rebuilt jars, including druid-processing-0.20.0.jar.

  - name: verify
    description: Gate the result — run `uv run scripts/patch_js_injection.py --check /root/druid` (must exit 0, no un-pinned sites) and confirm the rebuilt druid-processing-0.20.0.jar exists under processing/target/. If --check fails, re-run apply-fix.
    script: scripts/patch_js_injection.py
    depends_on: [apply-fix, build]
    inputs:
      - name: built-jars
        type: list[string]
    outputs:
      - name: verification-status
        type: object
        description: All sites pinned and patched jar present.

anti_patterns:
  - Patching only JavaScriptDimFilter (the sampler example) and missing the other vectors — aggregator, post-aggregator, extractionFn, virtualColumn, parseSpec, worker/broker select strategies. The verifier sends multiple exploit vectors; patch every site the scanner finds.
  - Disabling JavaScript globally or deleting the feature instead of pinning the injected config — this breaks legitimate JavaScript requests when the server has it enabled.
  - Trying to fix by stripping or rejecting the empty-string key during JSON parsing — brittle and easy to evade; the real fix is useInput = OptBoolean.FALSE on the injection.
  - Hand-writing unified diffs with fragile line numbers; instead edit the source, then capture `git diff` as the patch file.
  - Changing the Maven flags or building the whole reactor — web-console OOMs and the quality gates reject the patched files. Use scripts/build_druid.sh verbatim.
  - Aborting the Maven build on a timeout — a clean package of this slice legitimately takes minutes.

scenarios:
  - need: >
      Sampler RCE — POST /druid/indexer/v1/sampler with a javascript transform
      filter carrying an empty-string key mapped to {"enabled": true} runs
      arbitrary code despite druid.javascript.enabled=false.
    context: >
      Scanner --check and grep find several @JacksonInject JavaScriptConfig
      sites across the processing module and indexing-service.
    action: >
      Run patch_js_injection.py to pin every site to useInput =
      OptBoolean.FALSE and add the import; capture git diff into /root/patches/;
      rebuild via build_druid.sh; re-run --check (exit 0).
    outcome: >
      Every JavaScript vector now reads the server config, so all exploit
      requests are blocked while legitimate (and non-JavaScript) requests still
      work; the rebuilt druid-processing jar is ready for the verifier to
      redeploy.
```
