# Source notes — fix-druid-js-rce-bypass

## Origin
Authored from the task instruction at:
`vendor/skillsbench/tasks/fix-druid-loophole-cve/instruction.md`

The task asks an agent to patch Apache Druid 0.20.0 against an authenticated
remote-code-execution vulnerability (CVE-2021-25646 family). The published
exploit smuggles an empty-string JSON key `""` into a JavaScript filter spec;
the empty key causes Druid's Jackson-deserialized filter to ignore the
injected `JavaScriptConfig` and run attacker-controlled JS through Nashorn,
which has unrestricted access to `java.lang.Runtime`.

## Why a procedure schema
The work is a multi-step, fragile, build-aware patching workflow with
branching decisions (which JS handlers to patch, which fix strategy to use).
The `procedure` schema captures exactly this shape (`steps`, `decisions`,
`scenarios`, `anti_patterns`), so no new schema was drafted.

## Coverage classification (instruction → skill body)
- "Vulnerability: empty `\"\"` key bypasses JavaScriptConfig" → **mapped**
  (purpose, scenarios, references/vulnerability-details.md)
- "Write patches in /root/patches/" → **mapped** (steps:write-patch-file)
- "Apply patches to /root/druid/" → **mapped** (steps:apply-patch)
- "Rebuild with the specific Maven command" → **mapped** (steps:rebuild,
  scripts/build-druid.sh — flags reproduced verbatim)
- "Skip web-console to avoid OOM; skip code quality checks for patched files"
  → **mapped** (gotchas in steps:rebuild + anti_patterns)
- "Verifier deploys to /opt/druid/lib/ and restarts" → **mapped**
  (purpose; informs that the build must produce a deployable JAR in
  indexing-service/target/)
- "Must work with Apache Druid 0.20.0" → **mapped** (compatibility, purpose)
- Exploit example payload → **mapped** (references/vulnerability-details.md
  retains the full HTTP request so the agent can pattern-match against the
  bypass shape).

No source content was deliberately dropped.
