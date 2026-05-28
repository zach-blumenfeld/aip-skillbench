"""Profile the human-curated skill set of every SkillsBench task.

Walks `vendor/skillsbench/tasks/<task>/environment/skills/` and measures the
*structure* of each task's bundled human skills — the axis that predicts how
much an AIP conversion can improve them (prose-only skills have the most room;
already-scripted, terse skills have the least). Joins task difficulty/category
from `task.toml` and a one-line description from `instruction.md`.

Output: skill-analysis/skill-metrics.csv — one row per task.

Run from the repo root:
    uv run python skill-analysis/analyze_skills.py
"""

from __future__ import annotations

import csv
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "vendor" / "skillsbench" / "tasks"
OUT = ROOT / "skill-analysis" / "skill-metrics.csv"

SCRIPT_EXT = {".py", ".sh", ".bash", ".js", ".ts", ".rb", ".go", ".r", ".pl", ".jl"}
TEXT_EXT = {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".csv", ".toml", ".cfg"}


def first_sentence(task_dir: Path) -> str:
    f = task_dir / "instruction.md"
    if not f.exists():
        return ""
    for raw in f.read_text(errors="ignore").splitlines():
        s = raw.strip().lstrip("#").strip()
        if not s or s.startswith("```"):
            continue
        s = re.sub(r"`([^`]*)`", r"\1", s)
        m = re.search(r"^(.*?[.!?])(\s|$)", s)
        out = m.group(1) if m else s
        return (out[:147].rstrip() + "…") if len(out) > 150 else out
    return ""


def line_count(path: Path) -> int:
    try:
        return path.read_text(errors="ignore").count("\n") + 1
    except (OSError, UnicodeDecodeError):
        return 0


def classify(path: Path, skill_root: Path) -> str:
    parts = path.relative_to(skill_root).parts
    if path.name == "SKILL.md":
        return "skill_md"
    if "scripts" in parts:
        return "script"
    if "references" in parts:
        return "reference"
    if "assets" in parts or "examples" in parts:
        return "asset"
    ext = path.suffix.lower()
    if ext in SCRIPT_EXT:
        return "script"
    if ext in TEXT_EXT:
        return "reference"
    return "asset"


def profile_task(task_dir: Path) -> dict:
    meta = {}
    toml_path = task_dir / "task.toml"
    if toml_path.exists():
        meta = tomllib.load(open(toml_path, "rb")).get("metadata", {})

    skills_root = task_dir / "environment" / "skills"
    skill_dirs = (
        [p for p in skills_root.iterdir() if p.is_dir() and (p / "SKILL.md").exists()]
        if skills_root.exists()
        else []
    )

    m = dict(
        n_skills=len(skill_dirs),
        skill_md_loc=0,
        n_scripts=0,
        script_loc=0,
        n_refs=0,
        ref_loc=0,
        n_assets=0,
        total_files=0,
        total_bytes=0,
    )
    skill_names = []
    for sd in skill_dirs:
        skill_names.append(sd.name)
        for f in sd.rglob("*"):
            if not f.is_file():
                continue
            kind = classify(f, sd)
            m["total_files"] += 1
            try:
                m["total_bytes"] += f.stat().st_size
            except OSError:
                pass
            if kind == "skill_md":
                m["skill_md_loc"] += line_count(f)
            elif kind == "script":
                m["n_scripts"] += 1
                m["script_loc"] += line_count(f)
            elif kind == "reference":
                m["n_refs"] += 1
                m["ref_loc"] += line_count(f)
            else:
                m["n_assets"] += 1

    prose_loc = m["skill_md_loc"] + m["ref_loc"]
    # structure_class: the AIP-upside axis
    if m["n_skills"] == 0:
        sclass = "none"  # no curated skill → not eligible for mode 2/5
    elif m["script_loc"] == 0:
        sclass = "prose-only"  # most AIP upside (no executable knowledge yet)
    elif m["script_loc"] >= prose_loc:
        sclass = "script-heavy"  # least AIP upside (already executable)
    else:
        sclass = "mixed"

    return {
        "task": task_dir.name,
        "difficulty": meta.get("difficulty", ""),
        "category": meta.get("category", ""),
        "structure_class": sclass,
        "n_skills": m["n_skills"],
        "skill_names": ";".join(skill_names),
        "skill_md_loc": m["skill_md_loc"],
        "n_scripts": m["n_scripts"],
        "script_loc": m["script_loc"],
        "n_refs": m["n_refs"],
        "ref_loc": m["ref_loc"],
        "n_assets": m["n_assets"],
        "prose_loc": prose_loc,
        "prose_to_code_ratio": round(prose_loc / m["script_loc"], 2) if m["script_loc"] else "",
        "total_files": m["total_files"],
        "total_kb": round(m["total_bytes"] / 1024, 1),
        "description": first_sentence(task_dir),
    }


def main() -> None:
    rows = [profile_task(d) for d in sorted(TASKS.iterdir()) if (d / "task.toml").exists()]
    cols = [
        "task", "difficulty", "category", "structure_class", "n_skills", "skill_names",
        "skill_md_loc", "n_scripts", "script_loc", "n_refs", "ref_loc", "n_assets",
        "prose_loc", "prose_to_code_ratio", "total_files", "total_kb", "description",
    ]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    import collections
    print(f"Wrote {OUT} ({len(rows)} tasks).")
    print("structure_class:", dict(collections.Counter(r["structure_class"] for r in rows)))
    have = [r for r in rows if r["n_skills"] > 0]
    print(f"tasks with curated skills (mode-2/5 eligible): {len(have)}")


if __name__ == "__main__":
    main()
