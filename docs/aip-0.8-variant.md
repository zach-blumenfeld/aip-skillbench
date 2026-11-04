# The `aip-0.8.0` variant

Added 2026-11-04. Format 0.8 is the first breaking format change since 0.6a1 (the aip
CHANGELOG, `[0.8.0]`); the harness gets it as a fourth compile variant beside
`aip-0.6a1`, so the 0.6a1 packs and campaign A's cells stay comparable.

## What changed upstream, and what the harness does about it

| upstream (aip 0.7.0 / 0.8.0) | harness |
|---|---|
| One repository: `aip-spec` is `packages/aip-spec/` inside aip; the authoring skill is `skills/aip-compile/` (renamed from `aip`) | variant kind `aip-mono`: one clone under `build/aip-0.8.0/src/aip`; `skill_name` is `aip-compile` |
| The runtime's distribution is `agent-instruction-protocol` (the `aip` command is unchanged) | the wheel glob is `agent_instruction_protocol-*.whl`; the container install is otherwise the same |
| Format 0.8: explicit `start` step, keys may be overwritten, `thresholds` and the `review` pause gone, `confidence` keys plus a router check, `fallback` on decisions | the authoring note in `_prompts.py` states the 0.8 contract; the gate adds `no_model_gate` (below) |
| `aip skill install` keeps a record under `~/.aip/skills.json` | bootstrap runs it with `AIP_HOME=build/aip-0.8.0/aip-home` so the record stays in `build/` |

The variant's `aip` and `aip-spec` are `uv tool` installs under `build/aip-0.8.0/bin`
(`UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`), not on the global PATH: the gate runs them from there,
and `convert` prepends the dir to PATH for the authoring session only. So bootstrapping
`aip-0.8.0` does not touch the host's `aip`, unlike `aip-0.6a1`, which `uv tool install`s
globally.

## The no-decision-model gate

The ablation campaign runs `decision_model: false`: the solver answers every decision by
hand. In format 0.8 that is allowed only where the decision sets `fallback: true`;
otherwise the run stops with `no_decision_model`. And a hand answer writes no
`<question>_confidence` key, so a router's `confidence` check would fire on every run and
its value branches would never be taken. `no_model_gate` in `_variants.py` refuses both,
after `aip-spec validate` passes; the authoring prompt tells the author the same. The
validator's `unmeasured_route` warnings on such packs are expected. When a decision-model
arm is added, this gate is the thing to relax (per variant or per scenario).

## Bootstrapping before the release is tagged

`bootstrap --variant aip-0.8.0` pins tag `v0.8.0`. Until that tag exists, pin the release
branch at a commit from GitHub, which any machine can reproduce:

```bash
SHA=$(git -C ~/dev/aip rev-parse origin/release-0.8.0)
uv run aip-skillbench bootstrap --variant aip-0.8.0 --force --aip-ref release-0.8.0 --aip-sha $SHA
```

`--aip-remote <dir>` builds from a local checkout instead; REFS.json then carries a
`local` block under `aip`, which means the packs were authored against bytes nobody else
can fetch: do not publish a dataset on that. Once `v0.8.0` is tagged, rebuild with
`bootstrap --variant aip-0.8.0 --force` and no overrides; the packs do not change, so
only REFS.json does.
