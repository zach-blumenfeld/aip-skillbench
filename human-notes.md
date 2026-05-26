# Human notes

## Mode → Input mapping (concrete, for `3d-scan-calc`)

Paths are repo-relative from `/Users/zach/dev/aip-skillbench/`.

| Mode | Authored by | Input | Authored when | Trials use |
|---|---|---|---|---|
| 1 noskill | — | — | — | nothing |
| 2 human-curated | human | task domain expertise (no file) | offline | committed `vendor/skillsbench/tasks/3d-scan-calc/environment/skills/` |
| 3 skill-creator selfgen | same model as solver | `vendor/skillsbench/tasks/3d-scan-calc/instruction.md` | per trial (in-sandbox) | freshly-generated skill (sandbox-local, ephemeral) |
| 4 aip-from-instruction | Opus 4.7 | `vendor/skillsbench/tasks/3d-scan-calc/instruction.md` | once, locked | committed `generated-skills/3d-scan-calc/aip-from-instruction/` |
| 5 aip-from-curated | Opus 4.7 | `vendor/skillsbench/tasks/3d-scan-calc/instruction.md` + `vendor/skillsbench/tasks/3d-scan-calc/environment/skills/` | once, locked | committed `generated-skills/3d-scan-calc/aip-from-curated/` |
