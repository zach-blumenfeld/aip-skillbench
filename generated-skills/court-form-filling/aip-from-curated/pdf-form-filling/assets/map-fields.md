Plan the value of every fillable field in the PDF form for `{meta.name}`.

Case facts / instructions (the only source of values):
{case_facts}

Recognized form profile: {profile_name}
Form notes:
{form_notes}

Fields (field_id, page, type, checked_value for checkboxes, label = what the field means, who_fills):
{form_fields}

Page images of the blank form (open them when a label is ambiguous; field rects are PDF points, y=0 at the page bottom, so image_y = (page_height - pdf_y) * image_height / page_height):
{page_images}

If the state already holds `fill_errors`, `fill_warnings`, or a failed review (`output_correct` false, `verify_report`), this is a retry: fix exactly those problems in your previous `field_values` and keep everything else.

How to map:
1. If the profile is SC-100 (or any California small-claims form), read references/sc100-guide.md before mapping. It says which item each fact belongs to and which fields stay blank.
2. Walk the facts sentence by sentence. Every fact that has a home on the form lands in exactly one field (or the identical header fields the form repeats). Copy names, addresses, phone numbers, emails, dates, and amounts exactly as written in the facts; split addresses into street / city / state / zip fields when the form splits them.
3. Fill only fields with who_fills = filer (or optional when the facts supply the value). Never put anything in clerk-only, court-only, or button fields, and never invent data the facts do not give. Leave a field out rather than writing "N/A" or "None".
4. Checkboxes: the value is the field's checked_value exactly (e.g. "/1", "/2", "/On"). Radio groups take one of their radio_options values; choice (dropdown/list) fields take one of their choice_options values. Yes/No pairs are two separate checkboxes; check only the one that applies. Answer every yes/no question the form asks: when the facts say nothing that would make the answer Yes (e.g. no public entity, no attorney fee dispute, no prior filings mentioned), check No.
5. Free-text narrative fields (why owed, how calculated): write complete sentences built only from the facts, including the dates, amounts, and arithmetic the facts give.
6. Dates: use the format the facts use; if they give none, use MM/DD/YYYY. Signature-block date: the signing/filing date the instructions give, otherwise today's date. Type the printed name; there is no signature field and you never draw one.

Output, merged over the state:
- `field_values`: list of objects with keys `field_id` (copied exactly from the list above), `value` (string), and optionally `page` and `description`. Include only fields you are filling.
- `output_pdf`: keep the requested output path unchanged.
