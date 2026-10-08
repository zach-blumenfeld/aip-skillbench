Read the task statement below and extract what this drone-simulation run needs.

Task statement:
{task_statement}

What the pack installs and writes by default:
{assets[pack_contract]}

Produce JSON with exactly these keys:
- `params_path`: path of system_params.yaml named by the task (default `/root/system_params.yaml`).
- `commands_dir`: folder holding the NNN.txt flight-command files (default `/root/commands`).
- `results_dir`: root of the per-command output folders (default `/root/results`).
- `workdir`: folder where the task expects its Python source files (default `/root`; use the folder the task names if it names one).
- `success_criteria`: object with any numeric pass limits the task states, using only these keys: `max_rise_time`, `max_settling_time`, `max_overshoot_pct`, `max_steady_state_error` (metres), `max_tracking_rms` (metres). Omit keys the task does not state; never invent limits. An empty object when the task states none.

Verify the paths exist when you can (e.g. `ls`). Copy numbers exactly as the task writes them; convert units to seconds, percent and metres.
