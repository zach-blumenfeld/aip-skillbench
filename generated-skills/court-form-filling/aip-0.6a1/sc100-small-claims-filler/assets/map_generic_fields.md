Map the case below onto the fillable fields of this PDF form and return the list under the output key `generic_field_values`: one object per field you fill, with keys `field_id`, `page`, and `value`.

Form: {form_summary}

Fields (field_id, page, type, rect in PDF points [left, bottom, right, top] with y=0 at the bottom, tooltip = printed label when present, and checked_value / radio_options / choice_options):

{form_fields}

Case description / task statement:

{case_description}

Rules:
- Work out each field's purpose from its tooltip and field_id. If those are unclear, render the pages (`pdftoppm -png -r 100 <form.pdf> <dir>/p`) and look at where each rect sits (image y = page height - PDF y), and/or run `pdftotext -layout` for the printed labels.
- Fill only fields the case supplies or that the form requires the filer to answer (yes/no questions whose answer follows from the case). Leave court/clerk-only fields (case number, hearing/trial dates, clerk signature, "for court use") and fields the case does not mention empty: do not list them at all.
- Checkbox: value must be its `checked_value` exactly (e.g. "/1"); for a Yes/No pair check exactly one. Radio group: one of its `radio_options` values. Choice: one of its `choice_options` values. Text: a string.
- Dates in the format {date_format}. Amounts as plain numbers when the form prints "$" already. Copy names, phones, and emails as written.
- If this is an SC-100 revision whose field ids changed, follow references/sc100-guide.md for what each item needs.
- The next step validates every id/value and stops with the exact error if one is wrong; fix the list and rerun that step.
