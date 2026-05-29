# Source materials for the `pdf` AIP skill

This skill is converted from the curated PDF skill bundled with the
SkillsBench `court-form-filling` task. The name (`pdf`) is preserved because
the task mounts this skill folder by name; renaming it would break the harness.

## Source files

- `original-SKILL.md` — the source skill's main entry point. Mixed broad
  guidance (general PDF operations, library quick-reference) with a pointer to
  `forms.md` for form filling.
- `original-forms.md` — the deterministic form-filling procedure. Two strict
  paths: fillable form fields vs. non-fillable. This is the path the
  court-form-filling task exercises.
- `original-reference.md` — advanced features, alternate libraries, CLI flags,
  performance and troubleshooting.
- `procedure.schema.json` — bundled AIP schema this skill's body validates
  against (`procedure` family — fits the form-filling execution graph).

## Schema choice

`procedure` was chosen because the skill's most load-bearing content (the
form-filling workflow) is an execution graph with script-backed nodes,
inputs/outputs, and one mutually-exclusive branch (fillable vs. non-fillable).
A new bespoke schema would not pay back the cost; `procedure` already provides
`steps[].depends_on`, `script`, `inputs`, `outputs`, `one_of`, `parallel`,
plus `scenarios`, `search_shortcuts`, and `anti_patterns` for the
documentation-tier content.

## Script choices (script vs. prose)

Every original helper script is preserved verbatim and bound to its step in
the procedure body via `step.script`:

- `check_fillable_fields.py` — deterministic detection (pypdf form-field
  presence). Script.
- `extract_form_field_info.py` — structured extraction with non-trivial
  traversal of annotation tree and radio-group reconstruction. Script.
- `convert_pdf_to_images.py` — fixed-DPI render + bounded scale. Script.
- `fill_fillable_fields.py` — validation + write. Script.
- `check_bounding_boxes.py` — fixed intersection + height rule check. Script.
- `create_validation_image.py` — fixed drawing rules. Script.
- `fill_pdf_form_with_annotations.py` — coordinate transform + annotation
  write. Script.
- `check_bounding_boxes_test.py` — preserved as test documentation; not bound
  to a step.

Steps left as prose (no script) are those that require the agent to interpret
images and ambiguous form layouts:

- `analyze-rendered-fields` (fillable path) — map field rects onto rendered
  pages and decide each field's purpose.
- `author-field-values-json` — pick values for each field from user inputs.
- `derive-bounding-boxes-visually` (non-fillable path) — locate labels and
  entry areas in PNG renders.
- `author-fields-json` — translate the visual analysis into JSON.
- `inspect-validation-images` — required human/agent visual gate before
  filling.

These hinge on judging the input, not applying a fixed rule, so they stay
prose per AIP best practice.

## Content kept in body vs. pushed to references

The procedure body is form-focused because that is what `court-form-filling`
exercises and what justifies the deterministic scripting. Broader PDF
operations (text extract, merge, split, create, watermark, OCR, encryption,
advanced rendering libraries, JS libraries, CLI flags, troubleshooting) are
referenced under `references/pdf-general-ops.md` and `references/pdf-advanced.md`,
loaded only when the task is not form filling. This keeps the body lean and
preserves all source content without padding tier-2 tokens for every
invocation.

## Deliberate drops

None. Every distinct piece of source content is either represented in the
body, kept verbatim in a script, or relocated to a `references/` file. The
`check_bounding_boxes_test.py` file is preserved alongside its production
script as documentation of the validator's expected behavior; it is not
referenced from the body because it is not part of the agent's procedure.

## License

`LICENSE.txt` is copied verbatim from the source skill and applies unchanged.
