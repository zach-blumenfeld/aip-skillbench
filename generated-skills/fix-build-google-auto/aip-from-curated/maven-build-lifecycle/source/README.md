# AIP Conversion Notes — `maven-build-lifecycle` (fix-build-google-auto host task)

## Source

- `ORIGINAL_SKILL.md` — verbatim copy of the curated source skill from
  `vendor/skillsbench/tasks/fix-build-google-auto/environment/skills/maven-build-lifecycle/SKILL.md`.
  A broad Maven reference covering the three lifecycles, profiles, resource
  filtering, multi-module reactor flags, Surefire/Failsafe, optimization, and
  debugging.
- `procedure.schema.json` — the AIP procedure schema this skill validates
  against. Bundled locally so the skill is self-contained even though the
  `$id` points at the shared canonical URL.

## Schema choice

Reused `procedure.schema.json`. The host task — `fix-build-google-auto` — is a
concrete repair workflow (analyze → write `failed_reasons.txt` → produce
`patch_{i}.diff` → apply). Build-repair maps cleanly to a procedure: locate the
failing phase → resolve effective config → classify → plan fix → apply →
verify. Reference content (phase tables, plugin XML, command lists) lives in
`references/` under progressive disclosure rather than inside the body.

No new schema authored.

## Why this skill exists for the task

The curated source is a Maven reference; on its own it is not a procedure.
`fix-build-google-auto` is a build-repair task with a strict output contract
(`failed_reasons.txt` + `patch_{i}.diff` files). The AIP version turns the
reference content into a six-step diagnostic-and-repair procedure tuned to
that contract, while preserving every piece of original content somewhere
agents can find it (body or references).

The AIP version adds:

- A typed procedure (`steps`) the agent walks for any Maven build failure:
  `locate-failing-phase` → `resolve-effective-config` → `classify-failure`
  → `plan-fix` → `apply-fix` → `verify-fix`.
- Two scripts:
  - `scripts/lookup_phase.py` — given a phase name, returns its lifecycle,
    position, and the phases that already ran. Removes the temptation to
    eyeball the lifecycle table from memory.
  - `scripts/diagnose_build.sh` — runs the standard read-only diagnostic
    sequence (`help:effective-pom`, `help:active-profiles`, `dependency:tree
    -Dverbose`, `dependency:analyze`, `clean compile`, `test`) into a single
    diagnostics directory with an index log.
- Six progressive-disclosure reference files under `references/` — the
  classify step explicitly directs the agent to load only the one matching
  the failure category, instead of dumping every section into the body.
- `integrations` pointing at `maven-dependency-management` and
  `maven-plugin-configuration` (the other two skills mounted on this task),
  so handoff is explicit rather than implicit.
- `scope_and_approval` distinguishing read-only diagnostics from
  patch-writing — relevant because the host task wants a specific output
  contract.

## Body-drop classification

Every distinct piece of the source `ORIGINAL_SKILL.md` was classified:

- **Mapped (body)** — `purpose`, `trigger_when`, the procedural backbone
  (locate → resolve → classify → plan → apply → verify), `search_shortcuts`
  (diagnostic commands, dependency inspection, reactor control, skip
  switches, profile activation), `scenarios` (worked compile/CI/reactor/test
  cases), `anti_patterns` (skipping tests blindly, eyeballing pom.xml,
  re-running reactor from top, etc.).
- **Mapped (references)** — every detailed table, XML snippet, and command
  list survives under `references/` and is pointed at from the `classify-failure`
  step via category-keyed loading:
  - `lifecycle-phases.md` — default / clean / site phases, phases-vs-goals,
    phase-to-goal bindings.
  - `profiles.md` — profile definition, activation, triggers, profile-driven
    failures.
  - `test-and-package.md` — Surefire, Failsafe, skip-option semantics,
    packaging gotchas.
  - `resources-and-customization.md` — source/target/encoding, custom
    directories, finalName, resource filtering, property substitution.
  - `multi-module-and-optimization.md` — reactor flags, build-order pitfalls,
    incremental/parallel builds, best practices.
  - `debugging-and-ci.md` — verbosity flags, effective config, dependency
    analysis, the standard debugging recipe, GitHub Actions / Jenkins CI
    snippets.
- **Schema gap** — none. The procedure schema accommodated every piece of
  procedural content; reference detail lives under `references/`.
- **Deliberate drop** — none. The original "Best Practices" and "Common
  Pitfalls" lists fold into `anti_patterns` (body) and the practice list in
  `references/multi-module-and-optimization.md`.

## Original skill `name`

Preserved exactly as `maven-build-lifecycle`. The task mounts the skill at
`<env>/skills/maven-build-lifecycle/`; renaming would break the mount.

## Future tuning

- If new Maven versions add lifecycle phases, update both
  `references/lifecycle-phases.md` *and* the `DEFAULT`/`CLEAN`/`SITE` lists
  inside `scripts/lookup_phase.py`. The script is the runtime source of
  truth for the agent; the reference is for human readers.
- If sibling tasks need the same lifecycle skill but with a different
  output contract (no `failed_reasons.txt`, different patch path), parameterize
  the `apply-fix` step rather than forking the skill.
