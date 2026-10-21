This form has no fillable fields, so text is added as annotations at visually located boxes. Produce the fields.json object under the output key `annotation_fields`.

Page images (rendered from {form_pdf_path}): {page_images}

Case description / task statement:

{case_description}

Do these in order; every step is required.

1. Visual analysis. Open each page image and find every place the filer enters data. For each, determine two boxes in IMAGE pixel coordinates [left, top, right, bottom]: the label box (the printed label text) and the entry box (only the blank area where data goes). The two MUST NOT intersect, and the entry box must be tall and wide enough for its text. Typical layouts:
   - Label inside a box ("Name: ____" inside a rectangle): entry runs from right of the label to the box edge.
   - Label before a line ("Email: ______"): entry is above the line, its full width.
   - Label under a line (signature/date lines): entry is above the line, its full width.
   - Label above a line ("Please enter any special requests:" then a line): entry spans from the bottom of the label to the line, full width.
   - Checkboxes: target the small square itself (not the "Yes"/"No" text, which is the label box); enter "X" to check it.
2. Build the object in this shape (a text field and a checkbox shown):

{assets[fields_json_example]}

   image_width/height come from the page images above. font_size defaults to 14 and must not exceed the entry box height; use a smaller size (e.g. 9-10) for tight lines. Fill only what the case supplies; dates in {date_format}.
3. Validate. Save the object to a scratch file and, from the skill's scripts/ folder, run `python check_bounding_boxes.py <fields.json>` until it prints SUCCESS (fix intersecting or too-short boxes). Then for each page run `python create_validation_image.py <page_number> <fields.json> <page image> <validation image>` and INSPECT each validation image: red (entry) rectangles cover only blank input areas and contain no printed text; blue rectangles cover the labels; for checkboxes the red box is centered on the square. Fix and regenerate until all are right. Do not proceed without this visual check.
4. Return the final object as `annotation_fields`. The next step re-runs the bounding-box check and writes the annotated PDF.
