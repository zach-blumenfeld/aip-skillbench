# Non-fillable PDF forms: text-annotation workflow

Use only when `pdf_forms.py check` reports `"fillable": false` (e.g. a scanned or flattened
copy of the form). Perform every step; skipping the visual checks puts text in the wrong place.
Run all commands from the skill root.

## Step 1: Visual analysis

`python3 scripts/pdf_forms.py render <file.pdf> <img_dir>` writes `page_N.png` per page (longest side ≤ 1000 px).

Examine each image and find every place the user should enter data. For each text field record
two boxes in **image pixel coordinates**: the label box and the entry box. They MUST NOT intersect;
the entry box covers only the writable area (usually right of, above, or below the label) and must be
tall and wide enough for its text.

Common structures:

*Label inside box* — `┌ Name: ________ ┐` → entry starts right of "Name:" and runs to the box edge.

*Label before line* — `Email: ________` → entry is above the line, full line width.

*Label under line* — line with "Name" printed below → entry is above the line, full line width
(typical for signature and date fields).

*Label above line* — "Please enter any special requests:" with a line below → entry runs from the
bottom of the label down to the line, full line width.

*Checkboxes* — `Are you a US citizen? Yes □  No □`
- Target the small square (□), which may sit left or right of its label.
- Keep the label text ("Yes", "No") out of the entry box; the entry box covers ONLY the square.

## Step 2: fields.json and validation images

```json
{
  "pages": [
    {"page_number": 1, "image_width": 772, "image_height": 1000}
  ],
  "form_fields": [
    {
      "page_number": 1,
      "description": "The user's last name should be entered here",
      "field_label": "Last name",
      "label_bounding_box": [30, 125, 95, 142],
      "entry_bounding_box": [100, 125, 280, 142],
      "entry_text": {"text": "Johnson", "font_size": 14, "font_color": "000000"}
    },
    {
      "page_number": 1,
      "description": "Checkbox that should be checked if the user is over 18",
      "field_label": "Yes",
      "label_bounding_box": [100, 525, 132, 540],
      "entry_bounding_box": [140, 525, 155, 540],
      "entry_text": {"text": "X"}
    }
  ]
}
```

- Boxes are `[left, top, right, bottom]` in image pixels; `image_width/height` are the rendered PNG sizes.
- `font_size` defaults to 14, `font_color` (RRGGBB) to `000000`; `font` defaults to Arial. Check a box with text `"X"`.
- Fields with no `entry_text.text` are skipped.

For each page: `python3 scripts/pdf_forms.py validation-image <page> fields.json <img_dir>/page_<page>.png <img_dir>/check_<page>.png`
(red = entry boxes, blue = label boxes).

## Step 3: Validate the boxes

Automated: `python3 scripts/pdf_forms.py check-boxes fields.json` — fails on any intersecting boxes or
an entry box shorter than its font size. Fix and rerun until it prints `SUCCESS`.

Manual (do not skip): open every validation image and confirm
- red boxes cover only input areas and contain no printed text;
- blue boxes contain the label text;
- checkbox red boxes are centred on the square, blue boxes on its label.
If anything is off, fix fields.json, regenerate the images, and look again.

## Step 4: Write the annotations

`python3 scripts/pdf_forms.py annotate <input.pdf> fields.json <output.pdf>` converts image
coordinates to PDF coordinates (y flipped) and adds one FreeText annotation per entry.
Font size/colour are not honoured by every viewer. Render the output and inspect it.
