# Source materials — senior-java (AIP compilation)

This skill was compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/fix-druid-loophole-cve/environment/skills/senior-java/`
into AIP format. The original `SKILL.md` is preserved verbatim in
`ORIGINAL_SKILL.md`, the original `HOW_TO_USE.md` in `ORIGINAL_HOW_TO_USE.md`,
and the schema the AIP body validates against is bundled as
`procedure.schema.json` (the canonical `procedure` schema from the AIP spec —
`$id: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json`,
byte-identical to the spec copy).

The `name:` frontmatter is unchanged (`senior-java`) so the mounted skill name
matches what the `fix-druid-loophole-cve` task expects.

## Schema choice

The original is a broad **capability package** for enterprise Java/Spring Boot
development: six runnable Python generators/analyzers + five reference guides,
framed around "use this skill when starting projects, implementing JPA,
designing APIs, setting up security, optimizing performance, reviewing Java
code." That is naturally a procedure — *classify the development need → run the
matching generator/analyzer → harden the result against the relevant reference's
best practices → verify against the quality bars*. The `procedure` schema models
exactly this (`steps` with `depends_on` edges, `script` nodes,
`inputs`/`outputs`), and its optional fields carry the rest of the package
(`search_shortcuts` for the per-tool quick reference and the five reference
guides, `scenarios` for the four "Key Workflows", `anti_patterns` for the
common-pitfalls lists, `integrations` for composability, `scope_and_approval`
for the write/read-only distinction). So `procedure` was reused as-is rather
than drafting a new schema — consistent with AIP's bias toward schema reuse and
with the sibling curated conversions in this repo (`trl`, `pymatgen`, etc.) that
also compile to `procedure`.

The six generation/analysis steps all `depends_on` `classify-need` rather than
forming a strict chain, because they are **options invoked as the need calls for
them** (a new microservice uses scaffold + entity + security; a perf task uses
only the profiler). The body says this explicitly so the agent does not treat
them as a mandatory pipeline. `harden-and-apply-best-practices` and
`verify-quality` then depend on the generation/analysis steps.

## Scripts and references

All six scripts (`scripts/*.py`) and all five reference docs (`references/*.md`)
are copied **byte-identical** from the source skill and referenced by the same
relative paths the original `SKILL.md` used. They are real, functional tools
(pure stdlib Python 3.8+), so they were mirrored verbatim rather than rewritten —
the toolkit *is* the skill's value, and altering it would break faithful
conversion. No new script was authored; unlike some library-reference skills,
this one already ships runnable tooling.

The generation/analysis logic that AIP best practice wants script-backed (the
if/then branching over project type, database, auth method, field/relation
parsing, the CVE lookup table with severity-coded exit codes, the
query-pattern scan) already lives inside these scripts. The `steps` reference
them via `script:` edges; the step descriptions are one-line summaries, with the
scripts as the source of truth.

## Why some steps stay prose (not script-backed)

`classify-need`, `harden-and-apply-best-practices`, and `verify-quality` carry
no fixed-input computation a deterministic function could own. `classify-need`
is the agent reasoning about an arbitrary user request to pick tools and
constraints. `harden-and-apply-best-practices` is applying reference patterns to
whatever the generators produced — judgment over code, not a lookup.
`verify-quality` names the quality bars (80%+ coverage, 100% OpenAPI coverage,
zero critical/high CVEs, ~P99 < 200ms): these are **targets to design toward**,
not values the skill computes from structured input, so they stay prose. The one
quality bar that *is* mechanical — "dependencies scanned for vulnerabilities" —
is script-backed by `dependency_analyzer.py` (exit 2/1 on critical/high) and
wired through the `audit-dependencies` step, which `verify-quality` depends on.

## Content mapping (completeness check)

Every distinct piece of the original `SKILL.md` was classified:

- **Frontmatter identity** (`name`, `description`, `domain`/`subdomain`,
  `tech-stack`) → AIP `name` + `description` + `purpose` + `compatibility`
  (mapped). Website-display/analytics frontmatter (`difficulty`, `time-saved`,
  `frequency`, `stats`, `featured`, `verified`, `tags`, `created`/`updated`,
  `contributors`) is presentation metadata with no agent-behavior content →
  **deliberate drop** (AIP frontmatter is `name`/`description`/`metadata.aip.*`;
  `license`, `author`, and `version` are kept under allowed fields).
- **Overview / Core Capabilities / Core Value** → `purpose` (mapped).
- **Use this skill when** → `trigger_when` (mapped); added `do_not_use_when` to
  sharpen activation (new — not in the original, but additive, not lossy).
- **Quick Start + Python Tools (six tool sections with features/usage)** →
  `search_shortcuts[Capability tools]` for the CLI quick reference, and the six
  script-backed `steps` (scaffold-project, generate-entity-stack,
  generate-rest-endpoints, generate-security-config, audit-dependencies,
  profile-performance) for the per-tool detail (mapped).
- **Key Workflows 1-4** (microservice, REST API, JPA optimization, security) →
  `scenarios` (mapped — the four numbered workflows became four worked
  scenarios; per-step time estimates dropped as non-behavioral).
- **Reference Documentation / When to Use Each Reference** → one
  `search_shortcuts` category per reference, each with contents + load-guidance
  (mapped). All five reference files copied verbatim.
- **Best Practices → Quality Standards** → `verify-quality` step (mapped as
  targets).
- **Best Practices → Common Pitfalls to Avoid** → `anti_patterns` (mapped),
  merged with the pitfalls lists inside the JPA and performance references.
- **Performance Metrics** (dev-efficiency / code-quality / runtime targets) →
  folded into `verify-quality` (the runtime/quality numbers); the
  dev-efficiency timings are non-behavioral → **deliberate drop**.
- **Integration / Composability & Integration** (receives-from / provides-to /
  recommended combinations) → `integrations` (mapped).
- **Benefits / Next Steps / Additional Resources** → marketing and
  getting-started prose with no new agent-actionable content beyond what
  `purpose`/`scenarios`/`steps` already carry → **deliberate drop**.

## Deliberate drops (recorded with rationale)

1. **Website/analytics frontmatter** (`difficulty`, `time-saved`, `frequency`,
   `use-cases` duplicate of trigger_when, `related-agents`/`related-skills`/
   `orchestrated-by` partially captured by `integrations`, `stats`, `featured`,
   `verified`, `tags`, `examples` block, `created`/`updated`, `contributors`):
   presentation/marketing metadata for a skills marketplace, no bearing on agent
   behavior. The behavioral parts (related skills, examples) survive as
   `integrations` and `scenarios`.
2. **Per-workflow time estimates** ("30-45 minutes", "Time saved 60%") and the
   **Benefits/Next Steps/Additional Resources** sections: marketing framing, no
   agent-actionable procedure.
3. **The extension-less duplicate files** in the source skill
   (`scripts/spring_project_scaffolder`, `references/java-performance-tuning`,
   etc.): these are unreferenced placeholder stubs emitted by the source's
   `skill_builder.py` ("TODO: Implement actual functionality / This is a
   placeholder generated by skill_builder.py"). The original `SKILL.md` and its
   `dependencies` frontmatter reference only the `.py`/`.md` versions, which are
   the real implementations. Only the real files were mirrored; the stubs are
   cruft and were dropped.
4. **`HOW_TO_USE.md`** and the empty **`assets/`** dir (`.gitkeep` only): the
   source `HOW_TO_USE.md` is a fill-in-the-blank template ("[describe your
   task]", "[specific task related to this skill]") with no real content;
   `assets` is empty (original frontmatter `assets: []`). `HOW_TO_USE.md` is
   preserved in `source/ORIGINAL_HOW_TO_USE.md` for provenance but contributes
   no body content; the empty `assets/` dir was not recreated.

## One faithful correction

The original `SKILL.md` shows an example `performance_profiler.py --profile
http://localhost:8080/actuator`, but the shipped script implements only
`--analyze-queries DIR`. The AIP body describes the **real** interface
(`--analyze-queries`) and notes the absent `--profile` mode rather than
encoding a step the script cannot perform — AIP's "no surprises / match what the
description promises" principle. This is a correction of an over-claim in the
source, not a content drop.

## Functional test (three fresh agents)

Three fresh general-purpose agents were spawned against the skill folder with
prompts derived from `trigger_when`: (a) scaffold a new PostgreSQL + JWT
microservice and entity stack, then audit the pom; (b) audit a pom that
deserializes untrusted JSON for CVEs and ask for deserialization hardening; (c)
profile a source tree for N+1 query problems. All six scripts ran without
exceptions on valid input; the generators produced the promised project /
entity / controller / security files, and the references the body routes to
(spring-boot-best-practices, jpa-hibernate-guide) carried the correct hardening
patterns. Intent capture was good on all three; the body's step → script →
reference flow held up.

Two pre-existing limitations in the *source* scripts surfaced and were
independently confirmed:

1. **`dependency_analyzer.py` under-counts namespaced Maven POMs.** On a standard
   `<project xmlns="http://maven.apache.org/POM/4.0.0">` POM — including the one
   `spring_project_scaffolder.py` itself emits — it reports `Total
   Dependencies: 0`, "No known vulnerabilities found", and exits 0 (a false
   all-clear). On a namespace-free POM it correctly flags log4j-core 2.14.1 as
   CVE-2021-44228 CRITICAL and exits 2. Root cause: in `_parse_maven`,
   `dep.find("m:groupId", ns) or dep.find("groupId")` — an empty namespaced leaf
   Element is falsy, so the `or` collapses to the un-namespaced fallback
   (`None`) and the `if ... is not None` guard drops every dependency (this also
   produces the `DeprecationWarning` on stderr). It also requires the input file
   to be named exactly `pom.xml` / `build.gradle` / `build.gradle.kts` and ships
   a 3-entry static CVE table.
2. **`performance_profiler.py` N+1 detection is heuristic/brittle.** It flagged
   an EAGER collection as `EAGER_FETCH` and an unbounded `findAll()` as
   `UNBOUNDED_QUERY` (exit 1), but never emitted `POTENTIAL_N1_QUERY` /
   `MISSING_ENTITY_GRAPH`: `_check_n1_queries` skips EAGER collections (only
   fires on LAZY) and `_check_entity_graph` requires the relationship annotation
   and `interface`/`Repository` in the *same* file, which repositories rarely
   have. So an N+1 risk is surfaced indirectly rather than by name.

### Decision: scripts kept byte-identical; limitations surfaced in the body

The scripts were **not** patched. This is the `aip-from-curated` track, whose
purpose is an apples-to-apples comparison of AIP vs. the original markdown skill
on identical content and tooling — the markdown `senior-java` mounted in the
task ships these exact scripts, and fixing bugs here would confound that
comparison by making the AIP variant outperform for reasons unrelated to the AIP
format. Faithful mirroring is the dominant constraint.

Instead, the discovered limitations are surfaced where AIP's "no surprises /
match what the description promises" principle requires it — as honest usage
caveats in the `audit-dependencies` and `profile-performance` step descriptions
(clean exit ≠ proof of zero CVEs; corroborate against OSV/NVD; the profiler scan
is heuristic). These caveats change no tool behavior and add no capability; they
only stop the agent trusting a tool past its real envelope. (Documenting this is
itself an illustration of AIP's "drift caught at write time" value: the original
markdown skill markets the dependency audit as a clean security gate and is
silent about the namespaced-POM blind spot.) The benign stderr
`DeprecationWarning` is left as-is for the same fidelity reason.

## Relationship to the sibling skill in this task

The `fix-druid-loophole-cve` task also has an `aip-from-instruction`-style
conversion (`jackson-security`) that is tightly tailored to the CVE-2021-25646
deserialization fix. This `senior-java` conversion is the **curated** track: a
faithful, lossless rendering of the generic enterprise-Java skill as it was
authored. It deliberately does **not** inject Druid- or Jackson-specific
content — the curated skill is general-purpose, and its transferable value for
the host task is its generic security guidance (validate every controller input,
scan dependencies for CVEs, the security checklist) plus general Java/Maven
build competence, all of which are preserved.
