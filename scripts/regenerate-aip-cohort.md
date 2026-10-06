# Regenerate the AIP skill cohort against a new spec version

Parallelizes mode-4 and mode-5 authoring across all 16 tasks currently under `generated-skills/`. Uses `aip-skillbench batch-convert`, which runs a `ThreadPoolExecutor` of `claude -p` Opus calls and skips already-done outputs unless `--force` is passed.

## Fill these in

```bash
AIP_REF=aip-0.5a0                         # aip (runtime/client/server) branch; bootstrap's default
AIP_SPEC_REF=v0.5a1                       # aip-spec (format, validator, authoring skill) tag; bootstrap's default
CONCURRENCY=4                             # parallel claude -p calls; raise for speed, lower if hitting rate limits
```

## 1. Tag the current cohort if you haven't already

Preserves the previous AIP spec version's skill packs so this regen doesn't lose them:

```bash
git tag -a aip-spec-vX.Y -m "AIP spec vX.Y cohort" && git push --tags
```

(Skip if already done — `aip-spec-v0.2` was tagged in commit `b8a5e32`.)

## 2. Update the aip and aip-spec clones

```bash
uv run aip-skillbench bootstrap --aip-ref "$AIP_REF" --aip-spec-ref "$AIP_SPEC_REF" --force
cat generated-skills/AIP_REF.json     # aip {remote, ref, sha}, aip_spec {remote, ref, sha}, aip_version — commit with the cohort
```

This clones both repos into `.claude/skills-src/`, installs the host `aip` and `aip-spec`
CLIs (authoring validates with `aip-spec validate` and functional-tests with `aip run`),
builds both wheels into `build/aip/` for trial containers, and writes the authoring skill
(`build/skills/aip/`) and the runtime skill (`build/aip-runtime-skill/aip-runtime/`).
`aip-0.5a0` is a branch: to reproduce an exact cohort later, pass
`--aip-sha <aip.sha from AIP_REF.json>`.

Verify the refs actually exist in the remotes first if you're not sure:

```bash
git ls-remote git@github.com:zach-blumenfeld/aip.git "$AIP_REF"
git ls-remote git@github.com:zach-blumenfeld/aip-spec.git "$AIP_SPEC_REF"
```

## 3. Regenerate all 16 task packs in parallel

`--force` overwrites the existing `generated-skills/<task>/aip-from-*/` directories. `--from both` does instruction + curated for each task (16 × 2 = 32 authoring calls).

```bash
uv run aip-skillbench batch-convert \
  --task 3d-scan-calc \
  --task debug-trl-grpo \
  --task earthquake-phase-association \
  --task fix-druid-loophole-cve \
  --task taxonomy-tree-merge \
  --task video-silence-remover \
  --task civ6-adjacency-optimizer \
  --task court-form-filling \
  --task crystallographic-wyckoff-position-analysis \
  --task dapt-intrusion-detection \
  --task dialogue-parser \
  --task drone-planning-control \
  --task earthquake-plate-calculation \
  --task energy-market-pricing \
  --task exoplanet-detection-period \
  --task financial-modeling-qa \
  --from both --concurrency $CONCURRENCY --force --yes
```

Expected: ~30–60 min wall clock at `--concurrency 4`, ~$15–25 in Opus tokens. The command prints a progress line per completion.

## 4. Sanity-check the output

Confirm every task got both packs and they validate against the new AIP schema:

```bash
for t in 3d-scan-calc debug-trl-grpo earthquake-phase-association fix-druid-loophole-cve \
         taxonomy-tree-merge video-silence-remover civ6-adjacency-optimizer \
         court-form-filling crystallographic-wyckoff-position-analysis \
         dapt-intrusion-detection dialogue-parser drone-planning-control \
         earthquake-plate-calculation energy-market-pricing \
         exoplanet-detection-period financial-modeling-qa; do
  for sub in aip-from-instruction aip-from-curated; do
    found=$(find generated-skills/$t/$sub -name SKILL.md 2>/dev/null | head -1)
    [ -z "$found" ] && echo "MISSING: $t / $sub"
  done
done
```

Every pack must validate against the bootstrapped format with no `runtime_block_outdated`
warning (`convert` already gates on this; `eval` and `run-matrix` refuse such packs):

```bash
for d in generated-skills/*/aip-from-*/*/; do
  out=$(aip-spec validate "$d" 2>&1); { [ $? -ne 0 ] || grep -q runtime_block_outdated <<<"$out"; } && echo "INVALID: $d"
done
head -6 generated-skills/3d-scan-calc/aip-from-instruction/*/SKILL.md
# Expect: metadata.aip-version: "0.5a1"
```

Curated-side packs can be authored one-per-curated-skill (default, names preserved) or
compiled into one procedure per task (`batch-convert --single`); pick one per cohort and
record it in the cohort commit message.

## 5. Commit

```bash
git add generated-skills/          # includes generated-skills/AIP_REF.json
git commit -m "Regenerate AIP cohort against spec $AIP_REF ($(python3 -c 'import json;print(json.load(open("generated-skills/AIP_REF.json"))["aip"]["sha"][:12])'))"
git tag -a aip-spec-$AIP_REF -m "AIP spec $AIP_REF cohort"
git push && git push --tags
```

## Notes on parallelism

`batch-convert --concurrency N` runs `N` `claude -p` Opus calls in parallel. Each call writes to a different `generated-skills/<task>/aip-from-{instruction,curated}/` so there are no filesystem collisions. The real ceiling on `N` is the Anthropic per-org rate limit for `claude-opus-4-7`; 4 has worked reliably so far, 8 starts to risk 429s on a fresh credit balance. Failures print as `FAIL(rc=…)` lines but don't abort the run — you can `--force` re-run just the failed tasks afterward by passing only those `--task` names.
