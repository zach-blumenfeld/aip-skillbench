The task requires interfaces that differ from what the pack installed in `{workdir}`.

Task statement:
{task_statement}

What was installed:
{pack_contract}

Adapt the installed copies in `{workdir}` (never the pack itself) so every file name, function name/signature, output path, file name and JSON key the task requires exists exactly as required:
- Add a new module or a thin wrapper/alias (e.g. `from trajectory_planner import trajectory_planner as plan_trajectory`) rather than renaming or rewriting the existing functions: the pack's later steps import `simulate.plan_all`, `simulate.tune` and `simulate.run_all` from `{workdir}` and must keep working.
- If the task's output layout or JSON keys differ, change `run_all` in `{workdir}/simulate.py` so it writes what the task asks, keeping `planned_trajectory.npy` saved immediately after `trajectory_planner()`.
- Keep the physics, controllers and metrics as they are unless the task explicitly defines them differently; load `references/model-reference.md` for the exact equations if you must change them.
- Import-check every module you touched: `cd {workdir} && python3 -c "import simulate, <your modules>"`.

Return JSON: `interface_changes` — list of strings, one per change made (file and what changed).
