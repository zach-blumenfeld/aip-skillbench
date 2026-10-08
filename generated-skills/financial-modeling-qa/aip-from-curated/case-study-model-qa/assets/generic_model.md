Build the model this case study describes and answer the question. No dedicated scorer exists for this case, so you do the modelling yourself.

Question:
{question}

Expected answer format: {answer_format}

Case-study text (from the PDF):
{pdf_text}

Workbook profile:
{workbook_profile}

Workbook: {xlsx_path}

Do this:
1. List every rule, input, and definition in the PDF that the question depends on. Quote the exact wording of anything ambiguous and pick the reading that fits the PDF's own examples.
2. Load the data with pandas or openpyxl using the profile: the right sheet, the real header row, and only the data columns. Recover records the profile shows outside the main block (`numeric_cells_outside_main_block`). Skip blank rows, but do not drop records. Coerce numbers stored as text. Assert the record count matches what the PDF says (e.g. "6,000 turns").
3. Compute in Python, vectorised over every record. Test your rule functions on 2-3 hand-checked rows and on the PDF's examples first.
4. If the task asks for a workbook deliverable, follow references/xlsx-guide.md: live Excel formulas rather than hardcoded results, zero formula errors, and its colour and number-format conventions.
5. Answer as in a multiple-choice exam: compute the value first, then match it to an option at the options' precision.
6. Output `answer`, the final answer as the question wants it, and `working`, a few lines on the method, the denominators, and any data issues.
