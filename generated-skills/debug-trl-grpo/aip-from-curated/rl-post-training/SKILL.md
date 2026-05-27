---
name: rl-post-training
description: Diagnostic guide for RL-based post-training of language models (GRPO, PPO, REINFORCE, DPO). Use proactively when debugging a training pipeline that shows no improvement, loss anomalies, reward stagnation, NaN gradients, or other unexpected behavior during reinforcement learning fine-tuning. Work through all pipeline stages — reward, advantages, log-probs, loss, generation/decoding — before concluding the diagnosis is complete; stopping after one or two fixes is a common failure mode. Covers log-probability math, advantage estimation, numerical stability, reward processing, and generation/decoding pipeline issues.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Diagnose RL-based post-training failures in language models (GRPO, PPO,
  REINFORCE, DPO). RL post-training optimizes a policy with reward signals
  through the pipeline: prompt → generate completions → score with reward
  → compute advantages → policy-gradient update. Each stage has distinct
  failure modes, and "no improvement" can originate anywhere in the
  pipeline. This procedure walks all five stages in order so the
  diagnosis does not stop at the first plausible-looking fix.

trigger_when:
  - Debugging an RL training pipeline that shows no improvement or reward stagnation.
  - Loss anomalies, NaN gradients, or otherwise unexpected behavior during RL fine-tuning.
  - GRPO / PPO / REINFORCE / DPO training is producing flat or collapsing metrics.
  - Investigating a suspected bug in log-probability math, advantage estimation, reward processing, or the generation/decoding pipeline.
  - Auditing numerical-stability constants (additive epsilons, clipping bounds, temperature) in an RL training loop.
  - User mentions GRPO, PPO, REINFORCE, DPO, KL divergence, advantages, log-probs, or reward shaping in a debugging context.

scope_and_approval: >
  Diagnostic and code-fix work on a training pipeline. Edit narrowly: change
  only the branch or constant that violates an invariant, never rewrite a
  working multi-branch function. The five pipeline stages must all be walked
  before declaring the diagnosis complete — stopping after one or two fixes
  is the common failure mode this skill is designed to prevent. Run
  `scripts/verify_pipeline.py` before declaring a fix done.

steps:
  - name: verify-reward-signal
    description: >
      Stage 1 — Check the reward signal. Are rewards non-constant? If all
      rewards are identical, there is no learning signal. Do rewards
      correlate with completion quality? Spot-check decoded completions
      against their scores. Is the reward function being called on the
      correct text? Decoding/stripping must preserve the content the
      reward function needs to evaluate.

  - name: verify-advantage-computation
    description: >
      Stage 2 — Check advantage computation. Are advantages non-zero when
      rewards vary? If they collapse to ~0, the policy gradient vanishes.
      Audit the magnitude and dtype of every numerical-stability constant
      on the advantage path (additive epsilons, clipping bounds) against
      what the math requires. Check the group size `G` — `G ≤ 2` makes
      `std` either undefined or extremely noisy.
    depends_on: [verify-reward-signal]

  - name: verify-log-prob-computation
    description: >
      Stage 3 — Check log-probabilities. Verify bounds: log-probs of valid
      tokens must be non-positive. Compare the implementation against
      `F.log_softmax` on a small deterministic input — a numerical match
      rules out sign errors, wrong gathering axis, and off-by-one
      subtraction. On a near-one-hot input, confirm the dominant token's
      log-prob is close to 0 (not close to the min).
    depends_on: [verify-advantage-computation]

  - name: verify-loss-computation
    description: >
      Stage 4 — Check the loss. Is the loss changing across steps? Flat
      loss suggests zero gradients upstream. Log the KL term and the
      policy-gradient term separately — either dominating the other is
      diagnostic. Check the fraction of clipped samples; near-100%
      clipping means the clip range is starving the signal.
    depends_on: [verify-log-prob-computation]

  - name: verify-generation-and-decoding
    description: >
      Stage 5 — Check generation and decoding. Padding and decoder
      artefacts must be stripped from the text the reward function sees.
      Every completion shape the model can emit must survive the decoding
      path with non-empty output where a human would expect non-empty
      output — include degenerate cases (no formatting markers, only a
      prefix, only a suffix) in the round-trip test. Print or log a
      sample of the actual strings handed to the reward function;
      mismatches between "what the model generated" and "what the reward
      saw" are often visible at a glance.
    depends_on: [verify-loss-computation]

  - name: match-against-pitfall-catalog
    description: >
      Once a suspicious area is identified, match it against known
      pattern shapes. The seven pitfall categories are:
      (1) sign errors in log-space (log-softmax, KL divergence, DPO log-ratio);
      (2) numerical-stability constants out of range (additive epsilons, clip bounds, temperature);
      (3) string processing in decoding (cleanup that blanks shapes the rules didn't anticipate);
      (4) reward / decoding format mismatch (reward function sees text with the shape it needs removed);
      (5) reference model drift (reference model not frozen, or gradients flowing through it);
      (6) gradient flow breakage (detached tensors, in-place ops, `.item()` / numpy round-trips in the loss path);
      (7) configuration misuse (SFT-scale LR, KL coefficient dominating, clip range too tight, `G` too small).
      For the full catalog with symptoms and detection strategies, load
      `references/common-pitfalls.md`. For stage-by-stage diagnostic
      procedures with verification snippets, load
      `references/diagnostic-workflow.md`.

  - name: fix-narrowly
    description: >
      A bug in a branched function is a bug in one branch, not a verdict
      on the whole function. Before editing, enumerate the input shapes
      the function handles today and the output each branch produces —
      the branches exist because callers rely on them. Identify which
      input-output pairs violate the intended contract; those are the
      only branches to change. The same principle applies to epsilon
      values, sign conventions, and clipping bounds — if a constant
      looks wrong, replace it with a correct constant; do not remove
      the surrounding numerical-stability logic. If the diff collapses
      a multi-branch function to a one-liner, a different caller's
      contract has almost certainly been broken — re-read the call
      sites before committing.

  - name: run-verifier
    description: >
      Before declaring the fix done, run `scripts/verify_pipeline.py`.
      It prints log-prob, advantage, and decoding values on small fixed
      inputs so you can compare them against the invariants. Inspect
      the output, paying attention to lines marked `?`.
    depends_on: [fix-narrowly]

decisions:
  - signal: A log-prob of a valid token is > 0 (the invariant `log_prob <= 0` is violated).
    action: >
      There is a bug. Check sign convention and the gather axis; compare
      manual log-probs against `F.log_softmax` on a deterministic input.
      Check method — `assert (log_probs <= 1e-6).all()`.
  - signal: Manual log-prob implementation does not match `F.log_softmax` on a deterministic input.
    action: >
      Suspect sign error, wrong gather axis, or off-by-one subtraction
      in the log-prob path. Check method —
      `torch.allclose(manual, F.log_softmax(...).gather(...))`.
  - signal: Softmax output does not sum to 1 along the vocabulary axis.
    action: >
      Bug in the softmax path or in the gathering/masking that produced
      it. Check method —
      `assert torch.allclose(softmax.sum(-1), ones)`.
  - signal: An additive epsilon is not in `(0, 1)` (≥ 1, negative, or wrong dtype).
    action: >
      Replace the constant with one in the correct range; do not remove
      the surrounding numerical-stability logic. Check method —
      `assert 0 < epsilon < 1`.
  - signal: Advantages are ~0 even though rewards vary (the invariant `advantages != 0` when rewards vary is violated).
    action: >
      The policy gradient is vanishing — audit the advantage path
      (normalization, group size `G`, dtype, clipping). Check method —
      `assert advantages.abs().max() > 0.1`.
  - signal: Round-tripping a representative generation through the decoding path produces empty output where non-empty is expected.
    action: >
      Bug in decoding/stripping — the reward function is not seeing the
      content it needs. Include degenerate generation shapes (no
      formatting markers, only a prefix, only a suffix) in the
      round-trip set.
  - signal: Rewards are constant across a batch.
    action: >
      There is no learning signal. Fix the reward function or the inputs
      it sees before continuing diagnosis downstream.
  - signal: Near-100% of samples are being clipped.
    action: >
      Clip range is starving the signal. Widen it, or check that
      log-prob ratios are not blowing up (which would indicate a
      log-prob or reference-model bug upstream).
  - signal: Loss is flat across training steps.
    action: >
      Gradients are zero upstream. Walk Stages 1–3
      (verify-reward-signal → verify-advantage-computation →
      verify-log-prob-computation) before re-examining the loss itself.
  - signal: KL term or policy-gradient term silently dominates the loss.
    action: >
      Log the two terms separately every step. If KL dominates, the KL
      coefficient is too high; if PG dominates without learning, suspect
      the advantage path.

anti_patterns:
  - Stopping after one or two fixes without walking all five pipeline stages.
  - Rewriting a multi-branch function when only one branch is wrong — the other branches exist because other callers rely on them.
  - Collapsing a multi-branch function to a one-liner without re-reading the call sites first.
  - Removing surrounding numerical-stability logic instead of correcting the one bad constant inside it.
  - Treating a bug in one branch as a verdict on the whole function.
  - Skipping `scripts/verify_pipeline.py` before declaring the diagnosis complete.
  - Letting `G ≤ 2` ride — `std` is undefined or extremely noisy at that group size.
  - Letting the KL term or the policy-gradient term dominate the loss without logging them separately to confirm.
  - Calling the reward function on text that has had the shape it needs to score stripped out during decoding.
  - Allowing gradients to flow through the reference model, or letting the reference model drift during training.
```
