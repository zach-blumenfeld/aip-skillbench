# Authoring notes — maven-dependency-management (AIP form)

## Source
- `source/SKILL.md` — original curated Agent Skill (reference-style Maven dependency management cheat sheet)
- `source/procedure.schema.json` — bundled copy of the AIP procedure schema this skill validates against

## Why the procedure schema
The original skill is reference documentation, but the consumer task
(`fix-build-google-auto`) is a build-repair workflow: read failing Maven log,
classify the failure, diagnose, decide on a fix, write `failed_reasons.txt`,
emit `patch_*.diff`, apply, verify. That is a procedure — a graph of nodes
where each node takes inputs and produces outputs — so the procedure schema
fits without modification.

## Script vs prose breakdown
| Step | Backing | Why |
|------|---------|-----|
| `capture-build-failure` | prose | Free-form invocation; phase/log shape varies per repo. |
| `classify-error` | **script** (`scripts/classify_maven_error.py`) | Regex over fixed Maven error-message templates → deterministic. |
| `diagnose` | **script** (`scripts/diagnose.sh`) | Always-the-same `mvn` invocations conditioned on error class. |
| `pick-fix-pattern` | prose, `one_of` | Requires judgment over diagnostic output; rules in `references/fix-patterns.md`. |
| `write-reasons-note` | prose | Free-text synthesis to a file the verifier only checks for non-emptiness. |
| `generate-patches` | prose | Depends on actual pom structure — agent edits then `git diff`s. |
| `apply-and-verify` | prose | Branchy: pass / fail-same / fail-other determines loop-back. |

Scripts deliberately use only Python 3 stdlib and bash + `mvn` so they run in
the BugSwarm container without `uv add` or pip installs.

## Content disposition vs original SKILL.md
- **Mapped into the body** — scope cheat sheet (as `search_shortcuts`), fix
  patterns (as `pick-fix-pattern` + `one_of`), diagnostic commands (as
  `search_shortcuts`), anti-patterns (BOM double-declare, `system` scope,
  `LATEST`/`RELEASE`, exclusion without alternative), worked scenarios
  (slf4j conflict, tomcat→jetty, package-not-found, missing artifact).
- **Mapped into `references/fix-patterns.md`** — XML templates per fix pattern
  (pin-in-DM, BOM import, exclusion, scope change, missing dep, repo config)
  and the decision rules from `pick-fix-pattern`.
- **Mapped into `references/maven-reference.md`** — verbatim Maven reference
  content (scope table, version-range syntax, multi-module parent pom,
  repository config, settings.xml, dependency-analysis commands, troubleshooting).
  Loaded on demand only when the body's quick cheat sheet is insufficient.
- **Deliberate drops** — "Best Practices" top-10 list was a generic Maven
  rubric not actionable for this task; the actionable items survive as
  `anti_patterns`. The "When to Use This Skill" bullet list collapses into
  `trigger_when`.

## Task-shape additions (not in original)
The original skill is generic Maven; the BugSwarm task expects very specific
artifacts. The skill adds:
- `failed_reasons.txt` path and non-empty requirement (`write-reasons-note`).
- `patch_<i>.diff` naming, repo-root location, and `git diff` (not raw
  `diff -u`) format (`generate-patches`, anti-patterns).
- Loop-back behavior after `git apply` + re-run (`apply-and-verify`).
