# Format of `field_info.json` (output of `extract_form_field_info.py`)

A JSON list. Each entry describes one fillable field discovered in the PDF.

```
[
  {
    "field_id": "<unique ID for the field>",
    "page": <1-based page number>,
    "rect": [left, bottom, right, top],
    "type": "text" | "checkbox" | "radio_group" | "choice"
  },

  // Checkbox fields carry additional values:
  {
    "field_id": "...",
    "page": 1,
    "type": "checkbox",
    "checked_value": "<value to assign to check the box>",
    "unchecked_value": "<value to assign to uncheck the box>"
  },

  // Radio groups carry the option list with per-option bounding rects:
  {
    "field_id": "...",
    "page": 1,
    "type": "radio_group",
    "radio_options": [
      { "value": "<value to assign to pick this option>", "rect": [l, b, r, t] }
    ]
  },

  // Choice (drop-down / list) fields carry options:
  {
    "field_id": "...",
    "page": 1,
    "type": "choice",
    "choice_options": [
      { "value": "<value to assign>", "text": "<display text>" }
    ]
  }
]
```

Bounding rects are in PDF coordinates: `[left, bottom, right, top]` with `y=0`
at the bottom of the page. When relating these rects to PNG renders produced by
`convert_pdf_to_images.py`, convert from PDF space (origin bottom-left) to
image space (origin top-left): image-y = page-height-points − pdf-y, then apply
the image-to-page scale ratio.
