# source/ — provenance for `video-silence-remover`

## Origin

Authored from the task instruction at
`vendor/skillsbench/tasks/video-silence-remover/instruction.md` only.
No prior human-written skill was consulted (mode: aip-from-instruction).

## Schema

Reuses the AIP `procedure.schema.json` from the AIP skill repository — the
work this skill encodes is a structured procedure (detect → plan → cut →
report → validate), which is exactly what that schema covers.

## Mapping the instruction to the skill body

| Instruction item | Where it lives in `SKILL.md` |
| --- | --- |
| "Input: data/input_video.mp4" | `steps[locate-input]` + script default arg |
| "Output: compressed_video.mp4 + compression_report.json under workspace" | `steps[run-processor]`, script defaults, scenarios |
| JSON report schema (5 top-level keys + `segments_removed[]`) | `steps[verify-report]`, anti-patterns, script writer |
| "Unnecessary opening needs to be removed" | `steps[plan-removals]`, freezedetect path in `scripts/process_video.py` |
| "Long pauses (> 2 sec) need to be removed" | `steps[plan-removals]` + `--silence-min 2.0` default |
| "Keep teaching content as much as possible" | `decisions` row about under/over cutting, `anti_patterns` |
| "Opening is static frames with noise" | `freezedetect` rationale, `references/tuning.md` |
| "Analyze pauses by audio" | `silencedetect` step + tuning reference |
| "Use ffmpeg or Python" | `compatibility` frontmatter + script implementation |
| "Processing < 10 min" | Encoder defaults (`libx264 -preset veryfast -crf 23`) + a decision row |
| Eval criteria: math consistency, valid JSON, segment values | Verification step + script computes removed from actual ffprobe |

Nothing from the instruction was dropped.
