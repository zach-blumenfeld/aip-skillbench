# Check the deliverable by hand

The validator could not locate per-vehicle routes in `{output_path}` (the task's schema is unusual).
Verify it yourself against `{solution_path}` (canonical solution):

0. First validate the canonical file independently: run `scripts/validate_report.py` from the skill
   folder with stdin `{{"currentState": <state with output_path set to {solution_path}>}}`. It must
   return `"verdict": "pass"`; if not, go back to the solver (wrong assumptions) before anything else.
1. Every vehicle's route starts and ends at the depot and lists original station IDs in the solved order.
2. Per-stop pickups/dropoffs match the canonical `stops`; no load leaves `[0, vehicle_capacity]`.
3. Reported totals equal the canonical `travel_distance`, `penalty_cost`, `objective` (no rounding
   unless the task asks).
4. The file parses as the format the task requires.

Fix anything that differs by regenerating from `{solution_path}` in code.
Return JSON: `{{"manual_check_summary": "<what you checked and fixed>"}}`.
