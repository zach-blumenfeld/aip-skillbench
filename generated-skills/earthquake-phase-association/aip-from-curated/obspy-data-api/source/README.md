# obspy-data-api — AIP conversion notes

## What this skill is

A faithful AIP conversion of the curated Agent Skill `obspy-data-api`
(`original-SKILL.md` in this folder). It is a **reference / knowledge skill**:
it teaches an agent the core *data* API of ObsPy — the standard objects
(`Stream`/`Trace`, `Catalog`/`Event`, `Inventory`) used to parse common
seismological file formats (MiniSEED, SAC, GSE2, …) and to manipulate data
into the shape downstream consumers expect (ObsPy signal-processing routines
or SeisBench's modeling API).

In the `earthquake-phase-association` task the agent loads
`/root/data/wave.mseed` into a `Stream` and hands it to SeisBench's PhaseNet
picker — this skill supplies exactly that ObsPy-side knowledge. The skill is
deliberately scoped to ObsPy's data API and does **not** cover the picking
model or the association algorithm (those are separate concerns).

## Schema choice

Reuses `procedure.schema.json` (AIP v0.3a2), the only schema bundled in the
project's `assets/aip-schemas/` and the schema every other skill in
`generated-skills/` validates against. There is no dedicated `reference`
schema in the project, and the AIP guidance biases strongly toward schema
reuse over drafting a near-duplicate. The procedure schema fits: the API is
expressed as a small graph of usage steps (load → inspect → process; read
events; read stations; hand off downstream) connected by the objects that
flow between them.

## Why no `scripts/`

AIP best practice prioritizes `scripts/` for steps that contain conditional
logic, lookup tables, numeric thresholds, or validation against fixed rules.
This skill has **none of that** — it is pure API reference knowledge ("call
`read()` to get a `Stream`; `Trace.stats` holds the metadata"). There is no
decision logic to make consistent via code, so every step stays prose. The
curated source likewise shipped no scripts. Inventing scripts here would add
nothing an agent doesn't already get from the API description.

## Where source content went

| Source section (`original-SKILL.md`) | Destination |
|---|---|
| Waveform Data — Summary | body `purpose` + `read-waveforms` / `inspect-trace` steps |
| Stream/Trace class structure (attrs + methods) | `read-waveforms` / `inspect-trace` / `process-traces` steps + `references/obspy-api-reference.md` |
| Waveform worked example (`read()` REPL session) | `references/obspy-api-reference.md` |
| Event Metadata (QuakeML, Catalog→Event hierarchy) | `read-event-metadata` step + reference file |
| Station Metadata (StationXML, Inventory hierarchy) | `read-station-metadata` step + reference file |
| Classes & Functions table | `references/obspy-api-reference.md` |
| Modules table | `references/obspy-api-reference.md` |

The full class-attribute breakdowns, the worked REPL example, and the two
tables are bulky and only needed on demand, so they live in
`references/obspy-api-reference.md` (progressive disclosure) and are pointed to
from the relevant steps. The body keeps the high-frequency "how to use it"
calls inline.

## Deliberate notes

- The `name` frontmatter field is kept exactly as the curated source
  (`obspy-data-api`) so the task's mounted skill name matches.
- The `description` is kept verbatim from the curated source — it is already
  specific and keyword-rich, and the benchmark matches against it.
- A `prepare-for-downstream` step was added to make explicit the handoff the
  source description promises ("downstream use cases such as ObsPy's signal
  processing routines or SeisBench's modeling API"). It is grounded in that
  sentence and adds only a thin, accurate handoff hint — that SeisBench models
  accept an ObsPy `Stream` (via `.classify()` / `.annotate()`) and that trace
  ids and timing must be preserved. It is not a SeisBench tutorial; the picking
  model and association logic stay out of scope (see `do_not_use_when`).
