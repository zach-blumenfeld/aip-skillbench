# simulation-metrics — AIP conversion notes

Source: `vendor/skillsbench/tasks/adaptive-cruise-control/environment/skills/simulation-metrics/SKILL.md` (Agent Skills format, single file, four Python snippets inline).

Schema: `procedure.schema.json` (procedure family). The skill is a small computational pipeline — load series → compute metrics → report — so the procedure schema fits without extension.

## Mapping decisions

- The four metric functions (`rise_time`, `overshoot_percent`, `steady_state_error`, `settling_time`) were moved verbatim into `scripts/metrics.py` and consolidated under one file per the AIP guidance "favor fewer script files for simplicity." Numeric thresholds (10/90, ±2%, final 10%) and conditional logic (`if max_val <= target`, `if v < lower or v > upper`) are exactly the cases that AIP says must live in scripts, not prose.
- `all_metrics()` was added as a convenience wrapper so the `compute-metrics` step is a single call; the individual functions remain importable so existing call sites keep working.
- A CLI (`--json` / `--json-file`) was added so an agent can invoke the script directly without writing Python. This is additive — it does not change the function behavior.
- The four separate step blocks in the original prose collapse into one script-backed `compute-metrics` step. Splitting them in the schema would multiply boilerplate without adding clarity, since they share the same inputs and the script computes all four anyway.

## Source-to-body classification

| Source content | Disposition |
|---|---|
| `rise_time` definition + code | **Mapped** — `scripts/metrics.py::rise_time`; semantics preserved in `compute-metrics` output description. |
| `overshoot_percent` definition + code | **Mapped** — same. |
| `steady_state_error` definition + code | **Mapped** — `final_fraction=0.1` default surfaced as a step input. |
| `settling_time` definition + code | **Mapped** — `tolerance=0.02` default surfaced as a step input. |
| Usage example (`times = [row['time'] for row in results]` …) | **Mapped** — promoted to a `scenarios` entry. |

No deliberate drops. No schema gaps surfaced.

## Frontmatter

`name` is preserved exactly as `simulation-metrics` — the host task mounts the skill by that name. `description` is preserved verbatim from the source so retrieval signals don't shift.
