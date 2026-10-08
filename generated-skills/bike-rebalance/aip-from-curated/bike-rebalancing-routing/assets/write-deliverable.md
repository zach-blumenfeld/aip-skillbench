# Write the deliverable report

The SCIP solve finished. Canonical solution (original station IDs, `depot_start`/`depot_end` labels):
`{solution_path}` — status `{solver_status}`, gap `{solver_gap}`, objective `{objective}`
(travel `{travel_distance}` + penalty `{penalty_cost}`, total deviation `{total_deviation}`).

Write the file the task asks for at `{output_path}` (absolute path).

1. Re-read the task's output specification in `task_text` (state). Does it name a file, keys, nesting,
   units, rounding, ID types, depot labels, or vehicle numbering?
2. If it specifies a schema, build the report **by transforming the canonical solution file
   programmatically** (a short Python snippet that loads `{solution_path}` and renames/reshapes keys).
   Never retype numbers or routes by hand.
   - Keep original station IDs exactly as the data gives them (never internal 0..n-1 indices).
   - Use the task's depot labels if it names them; otherwise keep `depot_start` / `depot_end`.
   - Express targets and achieved changes in the data's sign convention (`target`, `achieved` in the
     canonical `stations` list already are); `net_pickup` is always positive = picked up.
   - Round only in the written report, and only if the task asks; keep full precision otherwise.
   - Canonical `vehicle_id` is 1-based; renumber if the task wants 0-based or named vehicles.
   - Two vehicles may both serve one station (one picks up, one drops off). Station bounds are
     order-independent (total pickups ≤ initial bikes, total dropoffs ≤ free docks), so any arrival
     order is feasible; keep each vehicle's own quantities, do not merge them.
   - Include every vehicle, even one that does nothing, if the task wants one entry per vehicle.
   - Keep per-stop pickup/dropoff quantities and totals (travel distance, penalty, objective) when
     the schema has a place for them — the validator recomputes and compares them.
3. If the task gives no schema, copy the canonical solution to `{output_path}` unchanged.
4. If `solver_status` is not `optimal`, say so in your final answer (best incumbent + gap); do not
   claim optimality.

Return JSON with the validate step's inputs: `{{"data_path": ..., "output_path": "<absolute path written>", "solution_path": ...}}` (data_path and solution_path unchanged from the state).

Report shape reference (canonical):

{assets[canonical-solution-format]}
