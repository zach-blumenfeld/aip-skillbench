Verification of the filled document failed.

Output: {output_path}
Problems (leftover braces, leftover IF_/END_IF_ markers, missing values): {problems}
Values the template should show but the document lacks: {values_not_found}
Document text as saved:
{document_text}

Fix the output, then post `template_path`, `output_path`, `values`, and `conditions`
so the document is verified again:

- Wrong or missing value: correct `values` and re-run the fill yourself:
  pipe a JSON object with key currentState (holding template_path, output_path,
  values, conditions as absolute paths/objects) into `python scripts/fill_template.py`
  from the skill folder.
- Placeholder in a place the script does not reach (field code `w:instrText`, chart,
  SmartArt, embedded object) or a stray marker: open the saved .docx with python-docx
  (or edit its XML) and replace the text directly, keeping run formatting. Load the
  reference for the paragraph-level patterns.
- A value that appears with different formatting than the data (e.g. a number the
  template wraps) is a false alarm only if the document text shows the intended
  value; then leave it and say so in the final answer.

Do not loop more than twice; if it still fails, stop and report exactly what is left.
