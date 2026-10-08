`fields_spec` format (the curated skill's fields.json). Bounding boxes are image pixels [left, top, right, bottom]:

```
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

`pages` lists every page that has fields, with the pixel size of its page image (from page_images). `font_size` (default 14) and `font_color` (RRGGBB, default 000000) are optional; font size/color rendering is not reliable across viewers.
