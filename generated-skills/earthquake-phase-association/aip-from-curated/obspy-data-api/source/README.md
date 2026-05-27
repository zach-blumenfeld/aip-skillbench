# obspy-data-api — AIP conversion notes

Conversion of the curated Agent Skill at
`vendor/skillsbench/tasks/earthquake-phase-association/environment/skills/obspy-data-api/`
into AIP format.

## Schema choice

Reused `procedure.schema.json` (bundled here in `source/`). The original
SKILL.md is reference material about ObsPy's data API rather than a strict
runbook, but the procedure schema fits well when the API surface is reframed
as a workflow: parse waveforms → inspect a Trace → manipulate the time series
→ parse events → parse stations. Tables and the worked REPL example map
naturally to `search_shortcuts` and `scenarios`. A new `reference` schema
was not warranted for a single skill.

## Source-to-body mapping

| Source section                       | AIP body field                                |
|--------------------------------------|-----------------------------------------------|
| Top-level description                | frontmatter `description`, body `purpose`     |
| Waveform Data → Summary / Structure  | `steps[parse-waveforms]`, `steps[inspect-trace]` |
| Trace methods                        | `steps[manipulate-trace]`                     |
| Waveform example (REPL block)        | `scenarios[0]`                                |
| Event Metadata                       | `steps[parse-events]`                         |
| Station Metadata                     | `steps[parse-stations]`                       |
| Classes & Functions table            | `search_shortcuts[Classes & Functions]`       |
| Modules table                        | `search_shortcuts[Modules]`                   |
| QuakeML / FDSN StationXML references | inlined into `steps[parse-events]` / `steps[parse-stations]` |

## Frontmatter

- `name` preserved as `obspy-data-api` (mounted skill name must match).
- `description` preserved verbatim from the source SKILL.md.
- `metadata.aip.spec` → `https://github.com/zach-blumenfeld/aip/tree/v0.2`
- `metadata.aip.schemaId` → canonical procedure schema `$id`.
