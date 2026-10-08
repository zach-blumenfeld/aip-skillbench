"""Install the simulator modules into workdir, parse every command file, plan each trajectory
and check it against the acceleration limits derived from system_params.yaml."""
import filecmp
import glob
import os
import shutil
import sys

from stepio import PACK_LIB, emit, fail, read_input

state, assets = read_input()
for key in ("params_path", "commands_dir", "workdir"):
    if not state.get(key):
        fail(f"missing {key}")
params_path, commands_dir, workdir = state["params_path"], state["commands_dir"], state["workdir"]
if not os.path.isfile(params_path):
    fail(f"params file not found: {params_path}")
if not os.path.isdir(commands_dir):
    fail(f"commands dir not found: {commands_dir}")

# 1. Install the modules (back up any differing file already present).
os.makedirs(workdir, exist_ok=True)
installed, backed_up = [], []
for src in sorted(glob.glob(os.path.join(PACK_LIB, "*.py"))):
    dst = os.path.join(workdir, os.path.basename(src))
    if os.path.exists(dst) and not filecmp.cmp(src, dst, shallow=False):
        shutil.copy2(dst, dst + ".orig")
        backed_up.append(dst + ".orig")
    shutil.copy2(src, dst)
    installed.append(dst)

# 2. Plan with the pack's own copy (the installed one may be adapted later).
sys.path.insert(0, PACK_LIB)
from quad_params import load_params  # noqa: E402
from simulate import plan_all  # noqa: E402

try:
    params = load_params(params_path)
    planned = plan_all(commands_dir, params, stretch=False)
except Exception as e:  # parse errors name the offending line
    fail(f"{type(e).__name__}: {e}")

commands = [{
    "label": p["label"], "command": p["text"], "mode": p["mode"], "modes": p["modes"],
    "start": p["waypoints"][0:3, 0], "target": p["waypoints"][0:3, -1],
    "waypoint_times": p["times"], "duration_s": p["duration"],
    "accel_ok": p["check"]["ok"], "peak_up": round(p["check"]["peak_up"], 4),
    "peak_down": round(p["check"]["peak_down"], 4), "peak_horiz": round(p["check"]["peak_horiz"], 4),
    "violations": p["check"]["violations"],
} for p in planned]
infeasible = [c for c in commands if not c["accel_ok"]]

emit({
    "installed_modules": installed,
    "backed_up_files": backed_up,
    "pack_contract": assets.get("pack_contract", ""),
    "params_summary": {k: round(float(params[k]), 6) for k in (
        "sample_rate", "dt", "mass", "gravity", "T_max", "T_min", "twr", "hover_rpm",
        "accel_limit_up", "accel_limit_down", "accel_limit_horiz")},
    "commands": commands,
    "all_feasible": not infeasible,
    "infeasible": [{"label": c["label"], "command": c["command"], "violations": c["violations"]} for c in infeasible],
    "stretch_infeasible": False,
})
