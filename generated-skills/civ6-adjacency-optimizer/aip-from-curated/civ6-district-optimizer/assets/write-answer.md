Write the optimizer's solution as the answer file the task asks for.

Task instructions:

{task_instructions}

Optimizer result (solution_valid = {solution_valid}):

{solution}

1. If solution_valid is false, read solution.validation_errors and solution.search.notes,
   fix the cause (wrong scenario_path or map_path, a constraint that leaves no valid center),
   and rerun from inspect-map. Do not hand-write placements.
2. Find in the task instructions the output path and the exact JSON shape required (key names,
   coordinate form, one file per scenario or one combined file). Follow it exactly.
   If the task names no path, write /output/<scenario id>.json when /output exists, else
   ./<scenario id>_solution.json.
   If it names no shape, write: city_center as [x, y]; placements as an object mapping each
   district name (e.g. CAMPUS) to [x, y]; total_adjacency as an integer; for several cities,
   a cities list of those objects.
3. Copy coordinates and district names from the solution exactly; do not move, add or drop
   districts. Use solution.total_adjacency as the total (it is civ6lib's own score). Map
   names to the task's vocabulary only if it requires one (e.g. DISTRICT_CAMPUS).
4. Write the file, then return answer_path: the absolute path you wrote.
