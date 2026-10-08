# Deliver the orbital period ({meta.name})

Task: {task_request}

Refined result: period = {final_period} d, uncertainty = {period_uncertainty} d.
Refinement details (method, validation checks, notes, optional second-planet search):
{refine_summary}

1. Check `refine_summary.validation`. If `validated` is false, or `notes` say the
   refined peak sits at the window edge, state the caveat (which check failed and
   why) in the report; do not silently present a weak detection as certain. Load
   `references/validation-troubleshooting.md` if you need to explain a failure.
2. Deliver the answer exactly as the task asks: file path, file format, units (days
   unless asked otherwise), number of decimals, rounding. If the task names an output
   file, write only what it asks for there (for example just the number) and confirm
   it by reading it back. If no precision is specified, give the period in days to at
   least 5 decimals, never fewer decimals than the uncertainty supports.
3. If `additional_planet_search.significant` is true and the task asks about a
   specific planet, make sure the reported period is the one the task means.
4. Write a short report: period with uncertainty, T0, depth, duration, broad-search
   SDE and SNR, odd-even result, number of transits, preprocessing used (flag
   convention, flatten window, prewhitening), and any caveats.

Return JSON:
```json
{{"final_period": <float, days, unrounded>, "period_uncertainty": <float>,
 "answer": "<the answer exactly as delivered, e.g. the text written to the output file>",
 "report": "<the short report>"}}
```
