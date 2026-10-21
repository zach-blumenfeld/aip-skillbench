"""Step `rerun-failed`: re-run the failed commands with the agent's retry_spec.

stdin : {"state": {"commands_dir", "params_path", "results_dir", "retry_spec"}, ...}
retry_spec: {"<label>": {"command": <canonical command text or null>,
                         "gains": <six-key gain object or null>,
                         "skip_reason": <string or null>}}
stdout: {"retry_report": [...], "still_failed": [...]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drone_sim as D  # noqa: E402

GAIN_KEYS = ("kp_pos", "ki_pos", "kd_pos", "kp_att", "ki_att", "kd_att")


def main():
    state = json.load(sys.stdin)["state"]
    params = D.load_params(state["params_path"])
    originals = dict(D.list_commands(state["commands_dir"]))
    out = []
    for label, spec in sorted(state["retry_spec"].items()):
        spec = spec or {}
        if spec.get("skip_reason"):
            out.append({"label": label, "status": "skipped", "pass": False, "reason": spec["skip_reason"]})
            continue
        text = spec.get("command") or originals.get(label)
        if text is None:
            out.append({"label": label, "status": "unknown_label", "pass": False})
            continue
        gains = spec.get("gains")
        if gains:
            missing = [k for k in GAIN_KEYS if k not in gains]
            if missing:
                print(f"{label}: gains missing {missing}", file=sys.stderr)
                sys.exit(1)
            base = {k: [float(v) for v in gains[k]] for k in GAIN_KEYS}
        else:
            base = None
        rec = D.run_command(label, text, params, state["results_dir"],
                            candidates=D.candidate_gains(base, wide=True))
        rec["rewritten_from"] = originals.get(label, "").strip() if spec.get("command") else None
        out.append(rec)
    print(json.dumps({"retry_report": out, "still_failed": [r["label"] for r in out if not r["pass"]]}))


if __name__ == "__main__":
    main()
