The PDF has no fillable form fields, so you will place text annotations where a person would write. Build the `fields_spec` plan for `{meta.name}`.

Case facts / instructions (the only source of values):
{case_facts}

Page images (path, width, height in pixels):
{page_images}

If the state already holds `box_messages` with FAILURE lines or `boxes_accurate` false, this is a retry: fix only the boxes those messages or the validation images show are wrong.

Steps:
1. Open every page image and find every place the person should enter data. For each text field determine two boxes in IMAGE PIXELS of that page image, as [left, top, right, bottom]: the label box (the printed caption) and the entry box (only the blank area where data goes). The two MUST NOT intersect, and no box may intersect any other field's boxes. Entry boxes must be tall and wide enough for their text (height at least the font size, default 14).
2. Typical layouts:
   - Label inside a box ("Name:" inside a rectangle): entry runs from right of the label to the box edge.
   - Label before a line ("Email: ______"): entry is above the line, its full width.
   - Label under a line (line, then "Name" below it; common for signature and date): entry is above the line, its full width.
   - Label above a line ("Special requests:" then a line): entry spans from the bottom of the label down to the line, full width.
   - Checkboxes ("Yes □  No □"): the entry box covers ONLY the small square, not the "Yes"/"No" text; the label box covers that text. Use "X" as the text to check it.
3. Fill each entry with the matching fact, copied exactly. Skip fields the facts do not cover and areas reserved for the clerk/court/office use.

{assets[fields-format]}

Output, merged over the state:
- `fields_spec`: the object described above (keys `pages` and `form_fields`).
- `output_pdf`: keep the requested output path unchanged.
