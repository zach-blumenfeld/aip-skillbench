"""Helpers behind scripts/compile-collection.sh and scripts/run-campaign.sh (docs/campaigns.md).

    uv run python scripts/campaign.py tasks N                      # the collection's tasks, one per line
    uv run python scripts/campaign.py to-compile N --variant V [--force]
                                                                   # tasks needing a V pack: "<task>\t<why>"
    uv run python scripts/campaign.py check N --variant V          # V's gate sweep + _authoring audit
    uv run python scripts/campaign.py report OUT                   # per-scenario summary + per-cell skill signals

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

from aip_skillbench._aip import VARIANTS, Variant, validate_packs  # noqa: E402

GENERATED = ROOT / "generated-skills"
COLLECTIONS = ("1", "5", "10", "27", "ablation")
AIP_RUNTIME_MODES = {"aip-runtime", "aip-from-curated"}  # the alias: campaign dirs from before 2026-10-20
SEARCH_HIT = re.compile(r"^[\w.-]+@[0-9a-f]{8,}\s+\d", re.M)
AIP_ERROR = re.compile(r"^aip: \w+", re.M)


def config(n: str) -> dict:
    if n not in COLLECTIONS:
        sys.exit(f"collection must be one of {', '.join(COLLECTIONS)} (got {n!r})")
    return yaml.safe_load((ROOT / "configs" / f"campaign-{n}.yaml").read_text())


def variant_arg(argv: list[str]) -> Variant:
    if "--variant" not in argv or argv.index("--variant") + 1 >= len(argv):
        sys.exit("--variant <name> is required; one of " + ", ".join(VARIANTS))
    name = argv[argv.index("--variant") + 1]
    if name not in VARIANTS:
        sys.exit(f"unknown variant {name!r}; one of " + ", ".join(VARIANTS))
    return VARIANTS[name]


def has_pack(task: str, v: Variant) -> bool:
    d = v.pack_root(task)
    return d.is_dir() and any((p / "SKILL.md").exists() for p in d.iterdir() if p.is_dir())


def cmd_tasks(n: str) -> int:
    print("\n".join(config(n)["tasks"]))
    return 0


def cmd_to_compile(n: str, v: Variant, force: bool) -> int:
    for task in config(n)["tasks"]:
        if force:
            why = "forced"
        elif not has_pack(task, v):
            why = "missing"
        elif validate_packs(v, v.pack_root(task)):
            why = "invalid"
        else:
            continue
        print(f"{task}\t{why}")
    return 0


def cmd_check(n: str, v: Variant) -> int:
    bad = 0
    for task in config(n)["tasks"]:
        problems = validate_packs(v, v.pack_root(task)) if has_pack(task, v) else ["no pack"]
        audit = v.record_dir(task) / "single" / "audit.json"
        if not audit.exists():
            problems.append(f"no {audit.relative_to(GENERATED)}")
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


def _scenario_of(r: dict) -> str:
    return r.get("scenario") or r["mode"]


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
            latest[(r["task"], r["model"], _scenario_of(r), r["trial"])] = r
    rows = list(latest.values())
    camp = out_dir / "campaign.json"
    campaign = json.loads(camp.read_text()) if camp.exists() else {}
    if "scenarios" in campaign:
        scenarios = [(sc["name"], sc["mode"], sc.get("variant")) for sc in campaign["scenarios"]]
    else:  # a campaign dir from before scenarios existed: one per mode
        modes = campaign.get("modes") or sorted({r["mode"] for r in rows})
        scenarios = [(m, m, None) for m in modes]

    print(f"\nPer-scenario summary ({out_dir})")
    print(f"{'scenario':<14}{'mode':<22}{'variant':<11}{'n':>4}{'pass':>6}{'pass%':>7}{'error':>7}{'reward':>8}{'tools':>7}{'wall s':>8}")
    for name, mode, var in scenarios:
        rs = [r for r in rows if _scenario_of(r) == name]
        n = len(rs)
        p = sum(r["status"] == "pass" for r in rs)
        e = sum(r["status"] == "error" for r in rs)
        rew = [r["reward"] for r in rs if r["reward"] is not None]
        print(f"{name:<14}{mode:<22}{var or "-":<11}{n:>4}{p:>6}{(f'{100 * p / n:.0f}%' if n else '-'):>7}{e:>7}"
              f"{(f'{sum(rew) / len(rew):.2f}' if rew else '-'):>8}"
              f"{_mean([r['n_tool_calls'] for r in rs]):>7}{_mean([r['wall_clock'] for r in rs]):>8}")

    # Per-cell signals for every scenario that mounts or publishes a skill: which skill
    # the solver launched (so a solver that ignored the pack is visible), the AIP step
    # signals for AIP packs, and the protocol signals for aip-runtime.
    skilled = [(n, m, v) for n, m, v in scenarios if m not in ("noskill",)]
    cells = sorted((r for r in rows if _scenario_of(r) in {n for n, _, _ in skilled}),
                   key=lambda r: (_scenario_of(r), r["task"], r["model"], r["trial"]))
    if not cells:
        return 0
    print("\nPer-cell signals (aip-runtime: search hits, run/resume results, pauses, failures, done; "
          "AIP packs mounted as a skill: JSON step outputs, `aip` mentions; every skill scenario: the skill launched)")
    print(f"{'scenario':<12}{'task':<44}{'t':>2}{'reward':>7}{'tools':>6}{'wall s':>8}  signals")
    kinds = {n: (m, (VARIANTS[v].is_aip if v and v in VARIANTS else m in ("aip-spec", *AIP_RUNTIME_MODES))) for n, m, v in skilled}
    for r in cells:
        name = _scenario_of(r)
        mode, is_aip = kinds[name]
        s = signals(r.get("trial_dir"))
        if mode in AIP_RUNTIME_MODES:
            sig = (f"skill={s['skill']} search={s['search']} run/resume={s['run_resume']} "
                   f"paused={s['paused']} failed={s['failed']} done={'yes' if s['done'] else 'NO'}")
        elif is_aip:
            sig = f"skill={s['skill']} json_steps={s['json_steps']} aip_mentions={s['aip_mentions']}"
        else:
            sig = f"skill={s['skill']}"
        reward = "-" if r["reward"] is None else f"{r['reward']:g}"
        wall = "-" if r["wall_clock"] is None else f"{r['wall_clock']:.0f}"
        tools = "-" if r["n_tool_calls"] is None else str(r["n_tool_calls"])
        print(f"{name:<12}{r['task'][:43]:<44}{r['trial']:>2}{reward:>7}{tools:>6}{wall:>8}  "
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
        return cmd_to_compile(arg, variant_arg(argv[2:]), "--force" in argv[2:])
    if cmd == "check":
        return cmd_check(arg, variant_arg(argv[2:]))
    return cmd_report(arg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
