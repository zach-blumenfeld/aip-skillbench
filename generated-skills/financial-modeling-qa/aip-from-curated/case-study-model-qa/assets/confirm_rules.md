Check the default dice scoring rules below against the case-study text, and output the rules the scorer will use.

Question being answered:
{question}

Case-study text (from the PDF):
{pdf_text}

Default rules (assets/dice_rules.json):
{assets[dice_rules]}

Workbook profile (find the data sheet, header row, and any displaced or blank rows):
{workbook_profile}

Do this:
1. Walk the PDF's scoring table row by row. For each category confirm the criteria and the score: the three "any turn" formulas (highest x times rolled; sum of all rolls; highest x lowest x (highest - lowest)) and the three fixed-point patterns with their points (only two numbers, all the numbers 1-6, ordered run of four). Edit `points`, `run_length`, `rolls_per_turn`, `turns_per_game`, or `categories_unique_per_game` only where the PDF or the question says something different. Keep every `rule` value one of: max_times_count, sum, max_min_diff, only_two_numbers, all_faces, ordered_run.
2. "Only two numbers" means exactly two distinct values. A turn with a single repeated value scores 0 there unless the PDF or question says otherwise; then set `single_value_counts` to true.
3. "Ordered subset of four" means four ADJACENT rolls, in roll order, each exactly 1 higher than the last (1-2-3-4) or each exactly 1 lower (5-4-3-2). Gaps, sorted order, or non-adjacent rolls do not count.
4. If the question itself changes a rule (a "what if the score for X were Y" question), put the changed rule in `dice_rules`. Note in `rules_note` that the rule was changed.

Output `dice_rules`, the full rules object with the default's shape. Also output `rules_note`, one line on what you changed and why, or "defaults confirmed". If the workbook has more than one candidate data sheet, add `data_sheet` with the sheet name.
