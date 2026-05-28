# Source & authoring notes — jackson-security (AIP, from curated skill)

## Origin

Converted from the curated Agent Skill `jackson-security` shipped with the
SkillsBench `fix-druid-loophole-cve` task
(`tasks/fix-druid-loophole-cve/environment/skills/jackson-security/SKILL.md`,
preserved here as `original-SKILL.md`). The curated skill is a *knowledge*
skill: it teaches the timing of Jackson deserialization and a catalog of
structural attack patterns, but prescribes no concrete procedure. The `name:`
frontmatter is unchanged (`jackson-security`) because the task mounts the skill
by that name.

This is the **from-curated** variant: it faithfully restructures the curated
skill's knowledge into AIP. It deliberately does **not** import task-specific
solution details (Apache Druid, the JavaScript filter, `JavaScriptConfig`, the
exact Maven build) that the curated skill does not contain — those belong to
the from-instruction variant. The agent is expected to apply this general
knowledge to the specific task.

## Schema choice

Reused `procedure.schema.json` (AIP v0.3a2) — the only AIP schema bundled with
the toolkit and a good fit. The curated skill's thesis ("validate the raw input
before deserialization, not the object after") is naturally a short execution
graph: understand timing → locate where Jackson runs → intercept the raw body →
scan it for attack structure → reject before `readValue()`. No new schema
needed.

## Why a scanner script

AIP best practice: rule-based detection against a fixed set of patterns belongs
in a script, not prose. The curated skill enumerates a fixed catalog of
structural attacks (empty keys, polymorphic `@`-type directives, duplicate
keys, nested variants), and "flag every occurrence at any depth" is exactly
find-all rule logic. `scripts/scan_raw_json.py` encodes that catalog: it walks
raw JSON (via a pairs hook that preserves duplicates and empty keys a
normalizing parser would hide), reports each finding with path/depth/severity,
and exits non-zero when any high-severity pattern is present. It is the
reference implementation of the skill's core move — a pre-deserialization
raw-input gate — that the agent ports into the target language.

The scanner is intentionally pattern-general (it knows nothing about Druid or
JavaScript filters). On this task the empty-key check alone is decisive: every
exploit payload injects `"": {"enabled": true}`, so the scan flags all of them
while the legitimate (empty-key-free) request passes.

## Source → body mapping (completeness)

| Curated SKILL.md content | Where captured |
|---|---|
| "Key Concept: Deserialization Timing" (one readValue, no trace left) | `purpose`; step `understand-deserialization-timing`; references (Key Concept) |
| Diagram: JSON String → [Jackson Processing] → Java Object, attack surface | references/jackson-deserialization-attacks.md (verbatim) |
| "Why Post-Deserialization Validation Is Insufficient" + 5-step lifecycle | step `locate-validation-placement`; `anti_patterns`[0]; references (lifecycle + "validate raw input" consequence) |
| Empty key `""` — what it is, why it matters, visibility problem | step `scan-raw-input` + `reject-before-deserializing`; `scenarios`[0]; `anti_patterns`[1]; references; `scan_raw_json.py` empty-key detection |
| Polymorphic type handling (`@class`, gadget RCE) | `scenarios`[1]; references; `scan_raw_json.py` type-directive detection |
| Duplicate keys (last wins, WAF mismatch) | `scenarios`[2]; `anti_patterns`[3]; references; `scan_raw_json.py` duplicate-key detection |
| Nested injection (depth-limited checks miss it) | step `scan-raw-input` (walk full tree); `scenarios`[3]; `anti_patterns`[2]; references; `scan_raw_json.py` recursive walk |
| RFC 8259 validity of empty keys ("valid JSON, parses without error") | references; `anti_patterns`[4] (validity ≠ safety) |

### Deliberate drops / additions

- **No source content dropped.** Every section of the curated skill maps to the
  body, the reference, or the scanner (usually all three).
- **Additions beyond the curated text** (faithful elaborations of its thesis,
  not new claims): the explicit five-step procedure and the script-backed
  raw-input scanner. The curated skill states *that* validation must happen on
  raw input before deserialization; the procedure and script make that
  actionable. The `@JacksonInject`/`@JsonAnySetter` note in the reference's
  empty-key section restates the curated skill's own "injection points" and
  "property override" bullets in concrete Jackson terms. No Druid/JS-specific
  solution detail was introduced.
