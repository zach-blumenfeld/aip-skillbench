Answer this financial-modelling question from the case files.

Question: {question}
Workbook: {data_path}
Workbook profile (sheets, header rows, sample rows, layout anomalies): {workbook_summary}
Case background (from the PDF): {background_text}

1. Read references/xlsx-analysis.md before writing code; read references/pdf-reference.md only if the background text is empty or garbled.
2. Extract every rule, definition, and assumption the question depends on from the background; list them as named variables.
3. Load the data with pandas using the header row in the profile. Resolve any NOTE anomalies (blank rows, records pasted outside the table, text numbers) by record id before computing.
4. Build the calculation as a small pandas model under a scratch folder, check 2-3 records by hand against the rules, then compute the answer.
5. Re-read the question for units, sign, rounding, and what exactly is asked; multiple choice: pick the matching option.

Return `model_answer`: only the final value as the question wants it written.
