# Source & authoring notes — patch-druid-js-rce

## Origin

Authored from a single task instruction (the SkillsBench
`fix-druid-loophole-cve` task) describing an RCE in Apache Druid 0.20.0: an
authenticated user can run arbitrary JavaScript by adding an empty-string key
(`""`) to a JavaScript component (filter/aggregator/etc.) in a request such as
`POST /druid/indexer/v1/sampler`, bypassing `druid.javascript.enabled=false`.
No existing skill was consulted — the procedure was derived from the
instruction plus domain knowledge of the CVE-2021-25646 mechanism.

## Schema choice

Reused `procedure.schema.json` (AIP v0.3a2). The task is a linear runbook —
locate sites → patch → emit patch files → rebuild → verify — which is exactly a
procedure / execution graph. No new schema was needed.

## Why a scanner script

The fix is one uniform edit (`useInput = OptBoolean.FALSE` + an import) applied
at *every* `@JacksonInject JavaScriptConfig` site. "Apply this rule to every
match" is rule-based, find-all logic — best practice says back it with a script,
not prose. `scripts/patch_js_injection.py` does the rewrite and also provides a
`--check` mode used as a post-edit/post-build validation gate. `build_druid.sh`
pins the exact Maven invocation the verifier expects (long, must not drift).

## Instruction → body mapping (completeness)

| Instruction content | Where captured |
|---|---|
| Druid 0.20.0, JS RCE via malicious payload | `purpose`, `trigger_when`, references/vulnerability.md |
| Empty-key `""` bypass mechanism | references/vulnerability.md (root cause), `apply-fix` step |
| Example sampler payload | references/vulnerability.md |
| "Write patch files in /root/patches/" | step `emit-patch-files` |
| "Apply patches to /root/druid/ (git repo)" | step `apply-fix` (edits working tree) + `emit-patch-files` |
| Exact Maven build command + skip flags + skip web-console | step `build`, `scripts/build_druid.sh` |
| "skip web-console to avoid OOM", "skip quality checks" | build_druid.sh comments, references/vulnerability.md |
| Verifier deploys JAR to /opt/druid/lib/ and restarts | references/vulnerability.md (build/deploy notes), `scope_and_approval` |
| Tests block exploits but keep legit requests working | `purpose`, references/vulnerability.md (behavior-preserving), `verify` step |
| "must work with Apache Druid 0.20.0" | `compatibility`, `purpose` |

### Deliberate drops

- None of the instruction content was dropped. The Java-8 build hint and the
  enumerated list of likely vulnerable classes are *additions* (domain context)
  that go beyond the instruction to make the procedure autonomously solvable.
