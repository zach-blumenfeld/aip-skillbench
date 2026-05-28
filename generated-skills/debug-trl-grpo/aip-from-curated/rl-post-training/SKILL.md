---
name: rl-post-training
description: Diagnostic guide for RL-based post-training of language models (GRPO, PPO, REINFORCE, DPO). Use proactively when debugging a training pipeline that shows no improvement, loss anomalies, reward stagnation, NaN gradients, or other unexpected behavior during reinforcement learning fine-tuning. Work through all pipeline stages — reward, advantages, log-probs, loss, generation/decoding — before concluding the diagnosis is complete; stopping after one or two fixes is a common failure mode. Covers log-probability math, advantage estimation, numerical stability, reward processing, and generation/decoding pipeline issues.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Diagnose RL-based post-training failures in language models (GRPO, PPO,
  REINFORCE, DPO). RL post-training optimizes a policy with reward signals
  through the pipeline: prompt → generate completions → score with reward →
  compute advantages → policy-gradient update. Each stage has distinct
  failure modes, and "no improvement" can originate anywhere in the
  pipeline. This procedure walks all five stages in order — reward,
  advantages, log-probs, loss, generation/decoding — so the diagnosis does
  not stop at the first plausible-looking fix. Beyond general agent
  knowledge it adds the log-probability and advantage math, the numerical
  invariants each stage must satisfy, a catalog of recurring pitfalls, and a
  runnable verifier that prints stage values for comparison against the math.

trigger_when:
  - Debugging an RL training pipeline that shows no improvement or reward stagnation.
  - Loss anomalies, NaN gradients, or otherwise unexpected behavior during RL fine-tuning.
  - GRPO / PPO / REINFORCE / DPO training is producing flat or collapsing metrics.
  - Investigating a suspected bug in log-probability math, advantage estimation, reward processing, or the generation/decoding pipeline.
  - Auditing numerical-stability constants (additive epsilons, clipping bounds, temperature) in an RL training loop.
  - User mentions GRPO, PPO, REINFORCE, DPO, KL divergence, advantages, log-probs, or reward shaping in a debugging context.

do_not_use_when:
  - Debugging supervised fine-tuning (SFT) or pretraining with no reward / advantage / policy-gradient loop — the five pipeline stages here assume an RL reward signal.
  - The problem is an inference- or serving-time issue (latency, throughput, deployment) unrelated to the training pipeline.
  - There is a general model-quality complaint but no observed training-pipeline anomaly — characterize the failure mode first, then return here if it points at the RL pipeline.

scope_and_approval: >
  Diagnostic and code-fix work on a training pipeline. Edit narrowly: change
  only the branch or constant that violates an invariant, never rewrite a
  working multi-branch function. The five pipeline stages must all be walked
  before declaring the diagnosis complete — stopping after one or two fixes
  is the common failure mode this skill is designed to prevent. Editing the
  training loop, loss, reward, or decoding code is a write action; for a
  shared or production pipeline, propose the change before applying it. Run
  scripts/verify_pipeline.py before declaring a fix done.

steps:
  - name: triage
    description: >
      Characterize the failure before touching any single component, and
      pick the stage to start at. Use the observation → likely-culprit
      mapping: outputs unchanged from base model → zero advantages or zero
      gradients (Stage 2); flat loss → zero advantages, broken log-probs, or
      a gradient issue (Stage 2 then 3); NaN loss → numerical issue in
      log-probs or very large gradients (Stage 3); rewards all zero →
      decoding strips valid completions or reward-fn mismatch (Stage 1);
      rewards vary but no improvement → advantage bug (Stage 2); model
      degenerates into gibberish → learning rate too high or KL penalty
      broken (Stage 4). Triage chooses where to focus first; it does not
      excuse skipping stages. Full triage table is in
      references/diagnostic-workflow.md.
    outputs:
      - name: failure-characterization
        type: object
        description: The observed symptom and the stage(s) it most likely implicates.

  - name: verify-reward-signal
    description: >
      Stage 1 — Check the reward signal. Are rewards non-constant? If all
      rewards are identical, there is no learning signal. Do rewards
      correlate with completion quality? Spot-check decoded completions
      against their scores. Is the reward function being called on the
      correct text? Decoding/stripping must preserve the content the reward
      function needs to evaluate. Invariant: rewards must vary across a batch
      where completion quality varies.
    inputs:
      - name: failure-characterization
        type: object
        nullable: true

  - name: verify-advantage-computation
    description: >
      Stage 2 — Check advantage computation. Are advantages non-zero when
      rewards vary? If they collapse to ~0, the policy gradient vanishes
      (invariant: advantages.abs().max() > 0.1 when rewards vary). Audit the
      magnitude and dtype of every numerical-stability constant on the
      advantage path (additive epsilons, clipping bounds) against what the
      math requires — an additive epsilon exists only as a rounding guard,
      so it must satisfy 0 < epsilon << 1. Check the group size G: G ≤ 2
      makes std either undefined (G=1) or extremely noisy (G=2). Each group's
      advantages should be mean-centered (sum ≈ 0).
    depends_on: [verify-reward-signal]

  - name: verify-log-prob-computation
    description: >
      Stage 3 — Check log-probabilities. Verify bounds: log-probs of valid
      tokens must be non-positive (assert (log_probs <= 1e-6).all()). Compare
      the implementation against F.log_softmax on a small deterministic input
      (torch.allclose(manual, F.log_softmax(...).gather(-1,
      idx.unsqueeze(-1)).squeeze(-1))) — a numerical match rules out sign
      errors, wrong gathering axis, and off-by-one subtraction. On a
      near-one-hot input, confirm the dominant token's log-prob is close to 0
      (not close to the min). Confirm softmax sums to 1 along the vocab axis.
      For half-precision, cast logits to float32 before logsumexp and compare.
    depends_on: [verify-advantage-computation]

  - name: verify-loss-computation
    description: >
      Stage 4 — Check the loss. Is the loss changing across steps? Flat loss
      suggests zero gradients upstream — walk Stages 1–3 before re-examining
      the loss itself. Confirm the loss is finite (not NaN/Inf) and that the
      gradient norm is non-trivial (> 1e-8); a near-zero norm with a
      non-trivial loss means the loss is disconnected from the policy params
      (a .item()/.tolist()/numpy round-trip broke the graph). Log the KL term
      and the policy-gradient term separately — either dominating the other
      is diagnostic (KL ≥ ~10× the PG term means beta is too large). Check
      the fraction of clipped samples; near-100% clipping means the clip
      range is starving the signal.
    depends_on: [verify-log-prob-computation]

  - name: verify-generation-and-decoding
    description: >
      Stage 5 — Check generation and decoding. Padding and decoder artefacts
      must be stripped from the text the reward function sees. Every
      completion shape the model can emit must survive the decoding path with
      non-empty output where a human would expect non-empty output — include
      degenerate cases (no formatting markers, only a prefix, only a suffix,
      unclosed reasoning block) in the round-trip test. Print or log a sample
      of the actual strings handed to the reward function; mismatches between
      "what the model generated" and "what the reward saw" are often visible
      at a glance. Watch for skip_special_tokens stripping load-bearing custom
      tags. Reasoning-model completion shapes and the three decode behaviors
      (pass-through, extract-after-marker, empty) are cataloged in
      references/common-pitfalls.md.
    depends_on: [verify-loss-computation]

  - name: match-against-pitfall-catalog
    description: >
      Once a suspicious area is identified, match it against known pattern
      shapes. The seven pitfall categories are:
      (1) sign errors in log-space (log-softmax, KL divergence, DPO log-ratio);
      (2) numerical-stability constants out of range (additive epsilons, clip bounds, temperature);
      (3) string processing in decoding (cleanup that blanks shapes the rules didn't anticipate);
      (4) reward / decoding format mismatch (reward function sees text with the shape it needs removed);
      (5) reference model drift (reference model not frozen, or gradients flowing through it);
      (6) gradient flow breakage (detached tensors, in-place ops, .item() / numpy round-trips in the loss path);
      (7) configuration misuse (SFT-scale LR, KL coefficient dominating, clip range too tight, G too small).
      For the full catalog with symptoms and detection strategies, load
      references/common-pitfalls.md. For stage-by-stage diagnostic procedures
      with verification snippets, load references/diagnostic-workflow.md.

  - name: fix-narrowly
    description: >
      A bug in a branched function is a bug in one branch, not a verdict on
      the whole function. Before editing, enumerate the input shapes the
      function handles today and the output each branch produces — the
      branches exist because callers rely on them. Identify which
      input-output pairs violate the intended contract; those are the only
      branches to change. The same principle applies to epsilon values, sign
      conventions, and clipping bounds — if a constant looks wrong, replace it
      with a correct constant; do not remove the surrounding
      numerical-stability logic. If the diff collapses a multi-branch function
      to a one-liner, a different caller's contract has almost certainly been
      broken — re-read the call sites before committing.
    depends_on: [match-against-pitfall-catalog]

  - name: run-verifier
    description: >
      Before declaring the fix done, run scripts/verify_pipeline.py. Wire its
      three adapters (log-softmax fn, decode fn, advantage fn) to the project,
      then run it. It prints log-prob bounds, log-prob-vs-F.log_softmax,
      concentrated-logit spot checks, group-relative advantages, and decoding
      round-trips on small fixed inputs so you can compare them against the
      invariants. It exits non-zero only on unambiguous violations (e.g. a
      positive log-prob); inspect every line marked `?` before concluding.
    depends_on: [fix-narrowly]
    script: scripts/verify_pipeline.py
    inputs:
      - name: log_softmax_fn
        type: object
        description: Project's (logits, index) -> log_probs callable, wired into the verifier adapter.
      - name: decode_fn
        type: object
        description: Project's (input_ids, tokenizer) -> list[str] callable.
      - name: advantage_fn
        type: object
        description: Project's (rewards, num_generations) -> advantages callable.
    outputs:
      - name: verifier-report
        type: object
        description: Printed stage values plus any unambiguous invariant violations and `?`-flagged lines.

search_shortcuts:
  - category: References and verifier
    body: >
      references/common-pitfalls.md — catalog of pitfall categories
      (log-prob, advantage, decoding, reward, gradient/optimization,
      configuration) with symptoms and detection strategies; load when you
      have a suspicious area and want to match it against known pattern
      shapes. references/diagnostic-workflow.md — triage table plus
      stage-by-stage diagnostic procedures with runnable verification
      snippets; load when you need which invariant to check in which order.
      scripts/verify_pipeline.py — runnable diagnostic that prints
      log-prob / advantage / decoding values on small fixed inputs; run
      before declaring a fix done and inspect lines marked `?`.

scenarios:
  - need: GRPO training shows no improvement after many steps; loss is flat though rewards clearly vary within each group.
    context: >
      Triage points to Stage 2. Reading the advantage-normalization line
      shows advantages = (rewards - mean) / (std + 1.0) — the additive
      epsilon is 1.0, washing out the reward-normalized signal (0 < epsilon
      << 1 is violated).
    action: >
      Confirm with the verify_pipeline.py advantages probe (group-0 max |A|
      flagged ~0 despite varied rewards). Replace 1.0 with a correct
      stability epsilon (e.g. 1e-8); leave the surrounding normalization
      untouched.
    outcome: Advantages become non-zero on varied rewards and the policy gradient sees signal again.
  - need: KL divergence stays pinned near zero across training and the policy drifts into degenerate outputs.
    context: >
      Stage 4 / pitfall category 5 — the reference model was built as an
      alias of the policy (or with requires_grad=True), so the optimizer
      updates it alongside the policy and the regularization vanishes.
    action: >
      Assert all(not p.requires_grad for p in ref_model.parameters()) and
      ref_model is not policy_model; freeze the reference and wrap its
      forward in torch.no_grad().
    outcome: KL regularization is restored; the reference stays fixed and training stabilizes.
  - need: Rewards are all zero even for completions that look correct to a human reader.
    context: >
      Stage 5 — the decoder splits on a reasoning marker and returns empty
      for a completion shape the rules did not anticipate, so the reward
      function never sees the answer text it needs to score.
    action: >
      Round-trip representative completion shapes (plain text, completed
      reasoning + answer, unclosed reasoning, prefix-only) through the decode
      path and print what comes out. Fix only the branch that blanks a shape
      the reward must score — do not collapse the multi-branch decode
      function to a one-liner.
    outcome: The reward function again sees the answer text and rewards discriminate good completions from bad.
  - need: Model outputs degrade into gibberish within a handful of steps; loss and KL oscillate wildly.
    context: >
      Triage "model degenerates" → Stage 4 / pitfall category 7. The learning
      rate is 2e-5 — an SFT-scale value — where RL post-training typically
      needs 1e-7 to 5e-6.
    action: >
      Log KL per step; if it exceeds ~1.0 within the first few steps the LR is
      too high. Lower it into the RL range and re-run.
    outcome: KL stays bounded, outputs remain coherent, and the policy improves instead of collapsing.

anti_patterns:
  - Stopping after one or two fixes without walking all five pipeline stages.
  - Rewriting a multi-branch function when only one branch is wrong — the other branches exist because other callers rely on them.
  - Collapsing a multi-branch function to a one-liner without re-reading the call sites first.
  - Removing surrounding numerical-stability logic instead of correcting the one bad constant inside it.
  - Treating a bug in one branch as a verdict on the whole function.
  - Skipping scripts/verify_pipeline.py before declaring the diagnosis complete.
  - Letting G ≤ 2 ride — std is undefined or extremely noisy at that group size.
  - Letting the KL term or the policy-gradient term dominate the loss without logging them separately to confirm.
  - Calling the reward function on text that has had the shape it needs to score stripped out during decoding.
  - Allowing gradients to flow through the reference model, or letting the reference model drift during training.
```
