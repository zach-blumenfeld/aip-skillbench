Some commands failed after simulating with the selected gains.

Failures (label, mode, failed checks, metrics):
{failures}

Current gains (`tuning_results`):
{tuning_results}

Best sweep candidates seen: {tuning_top_candidates}
Success criteria: {success_criteria}

Diagnose with the symptom→fix table in `references/tuning-guide.md` and choose new gains. To try a candidate quickly on one command before re-running everything, in `{simulator_lib}` run Python that does: `p = load_params('{params_path}')` (quad_params), `pl = plan_all('{commands_dir}', p)` (simulate), pick the item whose `label` failed, then `simulate(item['waypoints'], item['times'], item['modes'], p, gains, item['traj'])` and `stepinfo_3d(actual[0:3], item['waypoints'][0:3, -1], time_vec)` with `gains` a dict of the six arrays.

Rules: keep ki small (attitude ki ≤ 0.5; position x/y ki near 0 — integral wind-up shows up as x/y oscillation); keep the attitude loop clearly faster than the position loop (sqrt(kp_att) ≳ 3·sqrt(kp_pos)); gains are 3-element arrays.
A failure that is a planning issue (accel violation) or a missing file is not fixed by gains: fix its cause (e.g. set `stretch_infeasible` true, or repair the installed module) instead.

Return JSON: `tuning_results` (object with kp_pos, ki_pos, kd_pos, kp_att, ki_att, kd_att arrays, plus a `note` string) and `accept_failures` (boolean: true only when the remaining failures cannot be fixed, e.g. the criteria are unreachable for this vehicle — explain in `note`).
