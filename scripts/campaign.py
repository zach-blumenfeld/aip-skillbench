"""Helpers behind scripts/compile-collection.sh and scripts/run-campaign.sh (docs/campaigns.md).

    uv run python scripts/campaign.py tasks N           # the collection's tasks, one per line
    uv run python scripts/campaign.py to-compile N [--force]
                                                        # tasks needing a pack: "<task>\t<why>"
    uv run python scripts/campaign.py check N           # validation sweep + _authoring audit
    uv run python scripts/campaign.py report OUT        # per-mode summary + per-AIP-cell signals

The collection's task list lives only in configs/campaign-N.yaml.

Trajectory signals: the ACP trajectory keeps each Terminal call's description and output,
not its command line, so `aip` calls are recognised by their output. A search prints
`name@revision  score  ...`; `aip run` and `aip resume` print a JSON object with `paused`
or `done`, or fail with an `aip: <error>` line; an aip-spec step script prints its JSON
output object.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aip_skillbench._aip import validate_packs  # noqa: E402

GENERATED = ROOT / "generated-skills"
COLLECTIONS = ("1", "5", "10", "27")
AIP_RUNTIME_MODES = {"aip-runtime", "aip-from-curated"}
SEARCH_HIT = re.compile(r"^[\w.-]+@[0-9a-f]{8,}\s+\d", re.M)
AIP_ERROR = re.compile(r"^aip: \w+", re.M)


def config(n: str) -> dict:
    if n not in COLLECTIONS:
        sys.exit(f"collection must be one of {', '.join(COLLECTIONS)} (got {n!r})")
    return yaml.safe_load((ROOT / "configs" / f"campaign-{n}.yaml").read_text())


def pack_dir(task: str) -> Path:
    return GENERATED / task / "aip-from-curated"


def has_pack(task: str) -> bool:
    d = pack_dir(task)
    return d.is_dir() and any((p / "SKILL.md").exists() for p in d.iterdir() if p.is_dir())


def cmd_tasks(n: str) -> int:
    print("\n".join(config(n)["tasks"]))
    return 0


def cmd_to_compile(n: str, force: bool) -> int:
    for task in config(n)["tasks"]:
        if force:
            why = "forced"
        elif not has_pack(task):
            why = "missing"
        elif validate_packs(pack_dir(task)):
            why = "invalid"
        else:
            continue
        print(f"{task}\t{why}")
    return 0


def cmd_check(n: str) -> int:
    bad = 0
    for task in config(n)["tasks"]:
        problems = validate_packs(pack_dir(task)) if has_pack(task) else ["no pack"]
        audit = GENERATED / task / "_authoring" / "curated" / "single" / "audit.json"
        if not audit.exists():
            problems.append("no _authoring/curated/single/audit.json")
        elif not json.loads(audit.read_text()).get("ok"):
            problems.append(f"audit not ok: {audit}")
        if problems:
            bad += 1
            print(f"FAIL  {task}")
            for p in problems:
                print("      " + p.replace("\n", "\n      "))
        else:
            print(f"ok    {task}")
    print(f"{len(config(n)['tasks']) - bad} ok, {bad} failing")
    return 1 if bad else 0


def _console_json(text: str) -> dict | None:
    """The first JSON object in a Terminal output block, if the output starts with one."""
    body = text.strip().strip("`")
    body = re.sub(r"^(console)?\s*", "", body)
    body = re.sub(r"^Exit code \d+\s*", "", body)
    if not body.startswith("{"):
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(body)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def signals(trial_dir: str | None) -> dict:
    s = {"skill": "-", "search": 0, "run_resume": 0, "paused": 0, "failed": 0, "done": False,
         "json_steps": 0, "aip_mentions": 0}
    if not trial_dir:
        return s
    traj = Path(trial_dir) / "agent" / "acp_trajectory.jsonl"
    if not traj.exists():
        return s
    raw = traj.read_text()
    s["aip_mentions"] = raw.count('"aip ') + raw.count("`aip ")
    skills: list[str] = []
    for line in raw.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") != "tool_call":
            continue
        texts = [c["content"].get("text", "") for c in ev.get("content") or []
                 if c.get("type") == "content" and isinstance(c.get("content"), dict)]
        if ev.get("title") == "Skill":
            skills += [t.removeprefix("Launching skill: ") for t in texts]
            continue
        if ev.get("title") != "Terminal":
            continue
        out = next((t for t in texts if t.startswith("```")), "")
        if SEARCH_HIT.search(out.strip("`").removeprefix("console")):
            s["search"] += 1
        if AIP_ERROR.search(out):
            s["run_resume"] += 1
            s["failed"] += 1
            continue
        obj = _console_json(out)
        if obj is None:
            continue
        if "paused" in obj or "done" in obj:
            s["run_resume"] += 1
            s["paused"] += "paused" in obj
            s["done"] = s["done"] or obj.get("done") is True
        else:
            s["json_steps"] += 1
    s["skill"] = ",".join(skills) or "-"
    return s


def _mean(xs: list) -> str:
    xs = [x for x in xs if x is not None]
    return f"{sum(xs) / len(xs):.1f}" if xs else "-"


def cmd_report(out: str) -> int:
    out_dir = Path(out)
    summary = out_dir / "summary.jsonl"
    if not summary.exists():
        print(f"no {summary} yet")
        return 1
    latest: dict[tuple, dict] = {}
    for line in summary.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            latest[(r["task"], r["model"], r["mode"], r["trial"])] = r
    rows = list(latest.values())
    camp = out_dir / "campaign.json"
    modes = json.loads(camp.read_text())["modes"] if camp.exists() else sorted({r["mode"] for r in rows})

    print(f"\nPer-mode summary ({out_dir})")
    print(f"{'mode':<16}{'n':>4}{'pass':>6}{'pass%':>7}{'error':>7}{'reward':>8}{'tools':>7}{'wall s':>8}")
    for m in modes:
        rs = [r for r in rows if r["mode"] == m]
        n = len(rs)
        p = sum(r["status"] == "pass" for r in rs)
        e = sum(r["status"] == "error" for r in rs)
        rew = [r["reward"] for r in rs if r["reward"] is not None]
        print(f"{m:<16}{n:>4}{p:>6}{(f'{100 * p / n:.0f}%' if n else '-'):>7}{e:>7}"
              f"{(f'{sum(rew) / len(rew):.2f}' if rew else '-'):>8}"
              f"{_mean([r['n_tool_calls'] for r in rs]):>7}{_mean([r['wall_clock'] for r in rs]):>8}")

    aip = sorted((r for r in rows if r["mode"] == "aip-spec" or r["mode"] in AIP_RUNTIME_MODES),
                 key=lambda r: (r["mode"], r["task"], r["model"], r["trial"]))
    if not aip:
        return 0
    print("\nAIP cells (aip-runtime: search hits, run/resume results, pauses, failures, done; "
          "aip-spec: JSON step outputs, `aip` mentions)")
    print(f"{'mode':<17}{'task':<44}{'t':>2}{'reward':>7}{'tools':>6}{'wall s':>8}  signals")
    for r in aip:
        s = signals(r.get("trial_dir"))
        if r["mode"] in AIP_RUNTIME_MODES:
            sig = (f"skill={s['skill']} search={s['search']} run/resume={s['run_resume']} "
                   f"paused={s['paused']} failed={s['failed']} done={'yes' if s['done'] else 'NO'}")
        else:
            sig = f"skill={s['skill']} json_steps={s['json_steps']} aip_mentions={s['aip_mentions']}"
        reward = "-" if r["reward"] is None else f"{r['reward']:g}"
        wall = "-" if r["wall_clock"] is None else f"{r['wall_clock']:.0f}"
        tools = "-" if r["n_tool_calls"] is None else str(r["n_tool_calls"])
        print(f"{r['mode']:<17}{r['task'][:43]:<44}{r['trial']:>2}{reward:>7}{tools:>6}{wall:>8}  "
              f"{sig}{'  status=error' if r['status'] == 'error' else ''}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in {"tasks", "to-compile", "check", "report"}:
        print(__doc__)
        return 2
    cmd, arg = argv[0], argv[1]
    if cmd == "tasks":
        return cmd_tasks(arg)
    if cmd == "to-compile":
        return cmd_to_compile(arg, "--force" in argv[2:])
    if cmd == "check":
        return cmd_check(arg)
    return cmd_report(arg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
