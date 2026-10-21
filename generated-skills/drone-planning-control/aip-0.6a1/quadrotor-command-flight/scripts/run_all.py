"""Step `tune-and-simulate`: run every command file end to end.

stdin : {"state": {"commands_dir", "params_path", "results_dir"}, ...}
stdout: {"report": [...], "failed": [...], "run_status": "all_pass" | "some_failed"}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drone_sim as D  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402


def _run(job):
    return D.run_command(*job)


def main():
    state = json.load(sys.stdin)["state"]
    params = D.load_params(state["params_path"])
    commands = D.list_commands(state["commands_dir"])
    if not commands:
        print(f"no *.txt command files in {state['commands_dir']}", file=sys.stderr)
        sys.exit(1)
    os.makedirs(state["results_dir"], exist_ok=True)
    # Commands are independent: run them across the available CPUs.
    jobs = [(label, text, params, state["results_dir"]) for label, text in commands]
    workers = max(1, min(len(jobs), os.cpu_count() or 1))
    if workers == 1:
        report = [D.run_command(*j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            report = list(ex.map(_run, jobs))
    failed = [r["label"] for r in report if not r["pass"]]
    print(json.dumps({"report": report, "failed": failed,
                      "run_status": "some_failed" if failed else "all_pass"}))


if __name__ == "__main__":
    main()
