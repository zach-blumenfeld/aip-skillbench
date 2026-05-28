# Source materials — trl (AIP compilation)

This skill was compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/debug-trl-grpo/environment/skills/trl/` into AIP
format. The original SKILL.md is preserved verbatim in `ORIGINAL_SKILL.md`, and
the schema the AIP body validates against is bundled as `procedure.schema.json`
(the canonical `procedure` schema from the AIP spec — `$id:
https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json`,
byte-identical to the spec copy).

The `name:` frontmatter is unchanged (`trl`) so the mounted skill name matches
what the task expects.

## Schema choice

The original is a *codebase reference* for the TRL library — a map of the
trainer hierarchy, the shared utilities in `trainer/utils.py`, the configuration
system, the model wrappers, and the data-flow conventions, framed by its own
`description` as something to consult "before reading or editing any file under
`trl/` so you have the intended contracts and invariants in mind, not just what
the current code says."

That "consult before you edit" framing is a short procedure: classify what you
are touching → locate it in the package map → read the contract it must honor →
trace the data flow → change narrowly enough to preserve the contract. The
`procedure` schema models exactly this (`steps` with `depends_on` edges and
`inputs`/`outputs`), and its optional fields carry the rest of the reference
content (`search_shortcuts` for the lookup tables, `scenarios` for worked
navigation examples, `anti_patterns`, `scope_and_approval`). So `procedure` was
adopted as-is rather than drafting a new `reference`-style schema — consistent
with AIP's bias toward schema reuse and with the two sibling skills in this same
task (`grpo`, `rl-post-training`), which also compile to `procedure`.

### Relationship to the sibling skills

The three curated skills in `debug-trl-grpo` play distinct roles and this one
stays self-contained (it does not require the others to be mounted):

- **`trl`** (this skill) — the *codebase map*: where things live in TRL and the
  contracts each symbol must honor. Answers "where is this / what is it supposed
  to do."
- **`grpo`** — the *algorithm spec*: the precise per-stage GRPO math, invariants,
  and hyperparameter ranges. Answers "what is mathematically correct."
- **`rl-post-training`** — the *diagnostic procedure*: the triage table and
  five-stage debugging walk. Answers "how do I find the bug."

`do_not_use_when` in the body routes algorithm-math questions to `grpo` and the
generic diagnostic walk to `rl-post-training`, so the three compose without
overlap.

## Content mapping (completeness check)

Every distinct piece of the original SKILL.md was classified:

- **Intro** ("organized around a trainer hierarchy that extends
  transformers.Trainer") → `purpose` (mapped).
- **Package Structure** (the `trl/` directory tree) → `search_shortcuts[Package
  layout]`, plus the `locate-source` step's prose and the locator script
  (mapped).
- **Trainer Hierarchy** (all extend transformers.Trainer; each overrides
  compute_loss; RL trainers override training_step for a generation phase) →
  `search_shortcuts[Trainer hierarchy]` and the `trace-data-flow` step (mapped).
- **Shared Utility Functions** — `selective_log_softmax` contract (input/output
  shapes, non-positive, must match `F.log_softmax`), `decode_and_strip_padding`
  contract (list[str] length B, strips padding/artefacts, reasoning-block
  policy), and the padding helpers → `search_shortcuts[Shared utilities]`, the
  `read-intended-contract` step, and the locator's reprinted contracts (mapped).
- **Configuration System** (all configs extend `TrainingArguments`; the
  SFT/DPO/GRPO/KTO field table) → `search_shortcuts[Configuration system]`
  (mapped — the table's rows folded into prose per config).
- **Available References** table (`references/trl-codebase.md` + "when to load")
  → `search_shortcuts[References and locator]` and inline load-guidance in
  `read-intended-contract` (mapped).
- **`references/trl-codebase.md`** (the full module-by-module guide, including
  OnlineDPOTrainer detail, the models layer, data utilities, and the GRPOConfig
  / DPOConfig specifics tables) → copied verbatim and referenced by the same
  relative path; the load-guidance lives in `search_shortcuts[References and
  locator]` (mapped). OnlineDPOTrainer, the models layer, and the data utilities
  — present in the reference doc but only thinly in the original SKILL.md body —
  are now also surfaced directly in the body's `search_shortcuts` so the agent
  sees them without opening the reference.

No source content was dropped.

## Why the navigation steps stay prose (not script-backed)

AIP best practice asks that steps carrying lookup tables, thresholds, or
conditional logic be script-backed. The navigation steps here
(`identify-target`, `read-intended-contract`, `trace-data-flow`,
`change-preserving-contract`) carry no fixed-input computation: they describe how
the agent reads and reasons about an arbitrary external TRL checkout, whose
structure is not available as structured data to a deterministic function. The
one step that *is* a mechanical lookup over the installed tree — `locate-source`
— is script-backed by `scripts/locate_trl_symbols.py`, reached via the step's
`script:` edge.

## Scripts and references

`references/trl-codebase.md` is copied verbatim from the source skill
(byte-identical; the AIP body references it by the same relative path the
original SKILL.md used).

One new script was authored — `scripts/locate_trl_symbols.py` — that the
original skill lacked. It is the AIP value-add: the original reference is a hand
map ("trainers in trainer/, utilities in trainer/utils.py …") and repeatedly
advises reading the source before modifying, but ships nothing runnable. The
locator makes the package map executable against the *installed* TRL: it indexes
every `def`/`class` in the tree, maps each documented symbol to its file:line,
reprints the two shared-utility contracts next to their definitions, and flags
with `?` any documented symbol it cannot find (drift between the reference and
the installed code — exactly the gap the skill's `description` calls out:
"intended contracts … not just what the current code says"). Pure stdlib, no
torch import, so it runs even before the training stack is set up. It exits
non-zero only on the unambiguous failure of not finding the TRL root; a missing
individual symbol is a `?`, mirroring the diagnostic style of the sibling
skills' verifiers.
