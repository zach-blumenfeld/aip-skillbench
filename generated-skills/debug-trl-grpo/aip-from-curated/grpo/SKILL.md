---
name: grpo
description: Reference for the GRPO (Group Relative Policy Optimization) algorithm. Use when implementing, debugging, or verifying a GRPO training pipeline — covers the mathematical formulation (group-relative advantages, clipped surrogate loss, KL penalty), the training loop (generate → score → advantage → loss), log-probability computation, advantage estimation, numerical-stability constants, and relationship to PPO/REINFORCE. Includes a runnable verifier for the log-prob, advantage, and decoding invariants.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  GRPO (Group Relative Policy Optimization) is a policy-gradient method that
  eliminates the learned critic by computing advantages from group statistics:
  for each prompt it samples G completions and normalizes their rewards within
  the group, using the group mean as the baseline. This reference encodes the
  canonical algorithm as a training-step pipeline (sample -> decode -> score ->
  advantage -> log-probs -> loss -> update), with the exact per-stage math, the
  numerical invariants each stage must satisfy, the documented failure modes,
  the hyperparameter ranges, and the relationship to PPO/REINFORCE. Beyond
  general agent knowledge it adds the precise log-probability and advantage
  formulas, the sign and range constraints that catch silent bugs, and a
  runnable verifier for the three invariants that are checkable on fixed
  inputs. Use it as the spec to check an implementation against.

trigger_when:
  - Implementing a GRPO training pipeline from scratch.
  - Debugging a GRPO run that shows no improvement, flat loss, vanishing advantages, or NaN loss.
  - Verifying whether a specific implementation detail matches the GRPO algorithm specification.
  - Tracing a bug through a GRPOTrainer implementation (e.g. TRL) or mapping algorithm steps to code paths.
  - Reasoning about group-relative advantages, per-token log-probs / log-softmax, the clipped surrogate objective, or the KL penalty.
  - Auditing numerical-stability constants (advantage epsilon, clip range) or hyperparameters (num_generations G, beta, learning rate) in a GRPO loop.

do_not_use_when:
  - The algorithm is critic-based PPO (value head), REINFORCE, or DPO — group-relative advantage normalization is GRPO-specific and the advantage math here will not apply.
  - Debugging supervised fine-tuning (SFT) or pretraining with no reward / advantage / policy-gradient loop.
  - The problem is an inference- or serving-time issue (latency, throughput, deployment) unrelated to the training pipeline.

scope_and_approval: >
  This is an algorithm reference and verification aid. Reading the spec and
  running the verifier are read-only. If verification surfaces a deviation,
  fix it narrowly: change only the sign, constant, or branch that violates an
  invariant — never rewrite a working multi-branch function or strip the
  surrounding numerical-stability logic. Editing training, loss, or decoding
  code is a write action; on a shared or production pipeline, propose the
  change before applying it. Run scripts/verify_grpo_math.py before declaring
  an implementation spec-correct.

steps:
  - name: sample-completions
    description: >
      Step 1 — for each prompt x in the batch, sample G completions
      y_1..y_G ~ pi_old(.|x) from the current policy in eval mode. Output shape
      [batch_size * G, seq_len]. G = num_generations, typically 4–16 (more
      completions -> lower-variance advantages, higher compute cost). G <= 2 is
      a bug risk: per-group std is undefined at G=1 and extremely noisy at G=2.
    outputs:
      - name: completions
        type: object
        description: Sampled completion token ids, shape [batch_size * G, seq_len].

  - name: decode-completions
    description: >
      Step 2 — decode_and_strip_padding(completion_ids, tokenizer) -> text,
      shape [batch_size * G]. This decoded text is exactly what the reward
      function scores, so every completion shape the model can emit must
      survive with non-empty output where a human expects non-empty output:
      plain text with no reasoning markers must pass through unchanged; content
      after a closing reasoning marker (</think>) must be extracted; only a
      genuinely unfinished reasoning block (opened <think> with no close) should
      blank. A decode branch that blanks plain text starves the reward
      function. See references/grpo-trainer-internals.md for the decode path.
    depends_on: [sample-completions]
    inputs:
      - name: completions
        type: object
    outputs:
      - name: completion-text
        type: list[string]
        description: Decoded, padding-stripped completion strings, one per completion.

  - name: score-completions
    description: >
      Step 3 — evaluate each completion with the reward function:
      r_i = R(x, y_i) for i = 1..G, returning a tensor of shape
      [batch_size * G]. Rewards must vary across completions whose quality
      varies; a degenerate reward function that returns a single constant gives
      zero learning signal regardless of everything downstream.
    depends_on: [decode-completions]
    inputs:
      - name: completion-text
        type: list[string]
    outputs:
      - name: rewards
        type: object
        description: Per-completion rewards, shape [batch_size * G].

  - name: compute-advantages
    description: >
      Step 4 — group-relative advantage. Normalize rewards within each group of
      G: mu = mean(r_1..r_G), sigma = std(r_1..r_G),
      A_i = (r_i - mu) / (sigma + epsilon). In code: rewards.view(-1, G);
      per-group mean and std; repeat_interleave(G) to broadcast each group's
      stats back onto its completions; then normalize. epsilon is a tiny
      numerical-stability constant (1e-8 to 1e-4) ONLY — it must stay small
      relative to typical sigma, or it dominates the denominator and washes the
      advantage signal to ~0 (a classic "no improvement" bug). Properties:
      advantages are mean-centered per group (sum ~ 0); high-reward completions
      get positive advantages, low-reward negative; they collapse to 0 when all
      rewards in a group are identical.
    depends_on: [score-completions]
    inputs:
      - name: rewards
        type: object
    outputs:
      - name: advantages
        type: object
        description: Group-normalized advantages, shape [batch_size * G].

  - name: compute-log-probs
    description: >
      Step 5 — per-token log-probability via log-softmax:
      log_pi(t_j | x, t_<j) = logit(t_j) - logsumexp(logits). Critical
      invariant: log_pi <= 0 ALWAYS, since it is the log of a probability in
      (0, 1]; a positive value means a sign error (e.g. logsumexp - logit
      instead of logit - logsumexp). The "selective" variant that gathers only
      the selected-token indices is mathematically identical to
      F.log_softmax(logits, -1).gather(-1, idx) — verify against it on a small
      deterministic input. Compute for both the current policy (with grad) and
      the frozen reference policy (no grad). Sequence-level log-prob is the sum
      over tokens. For half precision, cast logits to float32 before logsumexp.
    depends_on: [sample-completions]
    inputs:
      - name: completions
        type: object
    outputs:
      - name: log-probs
        type: object
        description: Per-token log-probs [batch_size * G, seq_len] for current and reference policy.

  - name: compute-loss
    description: >
      Steps 5–7 — combine the clipped surrogate with the KL penalty.
      ratio = exp(log_pi_theta(y|x) - log_pi_old(y|x)) (log_pi_old is from the
      policy that generated the batch; equal to current for on-policy).
      Clipped surrogate: L_clip = min(ratio * A, clip(ratio, 1-eps, 1+eps) * A);
      clip eps typically 0.1–0.2 (narrower -> more conservative updates).
      KL penalty: L_kl = beta * KL(pi_theta || pi_ref); beta typically
      0.01–0.1 (higher -> closer to reference). Total loss = -E[L_clip] + L_kl.
      Learning rate 1e-7–5e-6 — far below SFT; RL is highly LR-sensitive.
    depends_on: [compute-advantages, compute-log-probs]
    inputs:
      - name: advantages
        type: object
      - name: log-probs
        type: object
    outputs:
      - name: loss
        type: float
        description: Scalar GRPO loss.

  - name: update
    description: >
      Step 7 — loss.backward() then optimizer.step(). The reference policy
      pi_ref is a frozen copy of the initial model (requires_grad=False, forward
      under torch.no_grad); the KL regularization stops working if the reference
      drifts or gradients flow through it.
    depends_on: [compute-loss]
    inputs:
      - name: loss
        type: float

  - name: verify-against-spec
    description: >
      Before declaring an implementation spec-correct, run
      scripts/verify_grpo_math.py. It checks the three input-independent
      invariants on small fixed inputs: log-prob (matches F.log_softmax,
      non-positive, dominant token near 0), advantage (additive epsilon << 1,
      non-zero and mean-centered when rewards vary), and decode (plain text
      preserved, content-after-marker extracted, unclosed reasoning blanked).
      Wire the adapters to the implementation (defaults target TRL). It exits
      non-zero only on unambiguous violations — inspect every line marked `?`.
    depends_on: [decode-completions, compute-advantages, compute-log-probs]
    script: scripts/verify_grpo_math.py
    inputs:
      - name: log_softmax_fn
        type: object
        description: Project's (logits, index) -> log_probs callable, wired into the verifier adapter.
      - name: decode_fn
        type: object
        description: Project's (input_ids, tokenizer) -> list[str] callable.
      - name: advantage_source_path
        type: string
        description: Path to the file holding the advantage-normalization line, for the epsilon scan.
    outputs:
      - name: verifier-report
        type: object
        description: Printed per-invariant values plus any unambiguous violations and `?`-flagged lines.

search_shortcuts:
  - category: References
    body: >
      references/grpo-algorithm.md — full mathematical formulation with the
      notation table, step-by-step derivations, log-prob and advantage detail
      with explicit failure modes, and the comparison to PPO and REINFORCE;
      load when you need to verify whether a specific implementation detail
      matches the spec. references/grpo-trainer-internals.md — GRPOTrainer
      (TRL) method-by-method breakdown (__init__, _generate_and_score_completions,
      compute_loss, training_step), the advantage-computation code
      (view / repeat_interleave), and a data-flow diagram; load when tracing a
      bug through a GRPOTrainer or mapping algorithm steps to code paths.
  - category: Verifier
    body: >
      scripts/verify_grpo_math.py — runnable check of the three
      numerically-verifiable invariants (log-prob, advantage, decode) on small
      fixed inputs; defaults target TRL. Run before declaring an implementation
      spec-correct and inspect lines marked `?`.

scenarios:
  - need: Per-token log-probabilities come out positive; training does not improve.
    context: >
      The selective log-softmax computes logsumexp - logit (negated), so the
      log_pi <= 0 invariant is violated and the values disagree with
      F.log_softmax on a deterministic input.
    action: >
      Confirm with verify_grpo_math.py (log-prob probe flags a positive max and
      a large diff vs F.log_softmax). Swap the subtraction order to
      logit - logsumexp; leave the gather and logsumexp structure intact.
    outcome: Log-probs are non-positive and match F.log_softmax; the ratio and clipped surrogate are well-defined again.
  - need: GRPO shows no improvement though rewards clearly vary within each group.
    context: >
      The advantage line divides by (std + 1e4) — the additive epsilon is 1e4,
      not 1e-4, so it dominates the denominator and collapses every advantage to
      ~0 (the 0 < epsilon << 1 constraint is violated).
    action: >
      verify_grpo_math.py advantage probe flags epsilon >= 1 and group-0 max |A|
      ~0 despite varied rewards. Replace 1e4 with a small stability epsilon
      (1e-4); leave the surrounding normalization untouched.
    outcome: Advantages become non-zero and mean-centered; the policy gradient sees signal again.
  - need: Rewards are zero even for completions a human would mark correct.
    context: >
      decode_and_strip_padding blanks every completion lacking a closing
      </think>, including plain answers that never opened a reasoning block, so
      the reward function scores empty strings.
    action: >
      Round-trip representative shapes (plain text, reasoning + answer, unclosed
      reasoning) through the decode probe. Fix only the branch that blanks plain
      text — gate the blank on startswith("<think>") so unclosed reasoning
      blanks but plain text passes through. Do not collapse the multi-branch
      decode function to a one-liner.
    outcome: Plain completions survive decoding, the reward function sees the answer text, and rewards discriminate good from bad.

anti_patterns:
  - Computing per-token log-probs as logsumexp - logit (or otherwise sign-flipped) so they come out positive — the log of a probability is always <= 0.
  - Treating the advantage epsilon as a tunable scale; it is a tiny numerical-stability guard (1e-8 to 1e-4), never ~1 or larger.
  - Letting an additive epsilon dominate the advantage denominator and wash the signal to ~0.
  - Rewriting a multi-branch decode or loss function when only one branch violates the spec — the other branches exist because other callers rely on them.
  - Collapsing a multi-branch function to a one-liner without re-reading the call sites first.
  - Calling the reward function on text whose answer-bearing content was stripped out during decoding.
  - Running with G <= 2 — per-group std is undefined (G=1) or extremely noisy (G=2).
  - Using an SFT-scale learning rate; RL post-training needs roughly 1e-7 to 5e-6.
  - Letting the reference model drift or gradients flow through it, so the KL penalty stops regularizing.
  - Declaring an implementation correct without running scripts/verify_grpo_math.py and inspecting the `?` lines.
```
