# sc100-form-filling — Source

This skill was authored from a single task instruction (no prior
human-written skill available). The instruction asks an agent to fill
California's `SC-100` small claims complaint PDF from a plain-English
case description, leaving court-filled and unmentioned fields blank,
and using `YYYY-MM-DD` for dates.

## Schema choice

`procedure.schema.json` — the work is a multi-step workflow with
ordered execution, signal-to-action decisions, and a worked scenario.
No category-specific schema existed, so the generic procedure schema
applies cleanly.

## Source content classification

The instruction's content was classified against the compiled body:

- **Filling steps** (`/root/sc100-blank.pdf` → `/root/sc100-filled.pdf`)
  → Mapped: `steps.read-input`, `steps.inspect-form`,
  `steps.plan-mapping`, `steps.fill-form`, `steps.verify-output`.
- **"Only fill necessary fields"** → Mapped:
  `decisions` (case-omitted → leave blank), `anti_patterns`
  ("don't fabricate court-filled fields"), and `references/sc100-field-guide.md`
  (court-filled section).
- **"Use date format xxxx-xx-xx"** → Mapped: `decisions` (date format)
  and gotcha in `references/sc100-field-guide.md`.
- **Case description specifics** (plaintiff, defendant, amount, dates,
  venue choice, first-time filer) → Mapped: `scenarios[0]` as a worked
  example with the case description's exact data shape (not the
  literal values, since the skill is reusable).
- **"Filing where defendant lives" + "we both live in Sunnyvale"** →
  Mapped: venue-selection decision and `references/sc100-field-guide.md`
  Section 5.

No source content was dropped.
