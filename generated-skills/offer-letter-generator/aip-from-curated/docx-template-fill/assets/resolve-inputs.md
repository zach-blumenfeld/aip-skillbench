Inspection of the Word template found problems that block a clean fill.

Template: {template_path}
Output:   {output_path}

Issues:
{issues}

Notes:
{notes}

Placeholders in the template: {placeholders}
Current values (KEY -> text to insert): {values}
Current conditional decisions (IF_ name -> include?): {conditions}
How each condition was decided: {condition_sources}

Resolve every issue, then post `template_path`, `output_path`, `values`, and `conditions`:

1. Missing placeholder value: look for it in the task instructions or the data under
   another name (e.g. `CANDIDATE_NAME` vs `CANDIDATE_FULL_NAME`, `SALARY` vs
   `BASE_SALARY`) and add `values[KEY]`. Only use a value the task or data actually
   gives; if none exists, use an empty string and say so in your final answer.
   Never invent compensation, dates, or names.
2. Undecided condition: set `conditions[NAME]` to true (keep the block, markers
   stripped) or false (remove the block). Decide from the data flag that governs it
   (`RELOCATION_PACKAGE: "Yes"` governs the IF_RELOCATION block) or from the task text.
3. Keep values as the data gives them. The template already supplies literal text
   around placeholders (`$` before amounts, `shares`, `days`, `per year`), so do not
   add symbols, units, or reformat numbers and dates.
4. Unmatched IF_/END_IF_ marker or output_path problems: fix the path, or set the
   condition so the stray marker is handled; a stray marker the script cannot pair
   must be removed by hand after the fill (see the reference).
