---
name: grpo
description: Reference for the GRPO (Group Relative Policy Optimization) algorithm. Use when implementing, debugging, or verifying a GRPO training pipeline — covers the mathematical formulation (group-relative advantages, clipped surrogate loss, KL penalty), the training loop (generate → score → advantage → loss), log-probability computation, advantage estimation, and relationship to PPO/REINFORCE.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Group Relative Policy Optimization (GRPO) is a policy gradient method that
  eliminates the learned critic by computing advantages from group statistics:
  for each prompt, G completions are sampled and their rewards are normalized
  within the group to produce advantages. This skill is a reference for the
  GRPO training loop (sample → score → advantage → log-prob → clipped surrogate
  loss + KL penalty → update), the math behind each stage, and the
  hyperparameters and failure modes that matter when implementing or debugging
  a GRPO pipeline (e.g., TRL's GRPOTrainer).

trigger_when:
  - Implementing a GRPO training pipeline from scratch or on top of a framework like TRL.
  - Debugging a GRPOTrainer where rewards, advantages, log-probs, ratio, KL, or loss look wrong.
  - Verifying that a specific implementation detail matches the GRPO algorithm specification.
  - User mentions GRPO, group-relative advantages, or RL fine-tuning without a learned critic.
  - Comparing GRPO to PPO or REINFORCE, or deciding which to use for a reasoning-style RL task.

steps:
  - name: sample-completions
    description: >
      For each prompt x in the batch, sample G completions y_1,...,y_G from the
      current generation policy pi_old (typically equal to pi_theta from the
      previous step). G is `num_generations` (typical range 4–16). More
      generations lower the variance of group-relative advantages at the cost
      of more compute.

  - name: decode-completions
    description: >
      Decode the sampled token sequences to text strings so they can be passed
      to the reward function. In TRL this is `decode_and_strip_padding(
      completion_ids, tokenizer)`; output shape is [batch_size * G] strings.

  - name: score-completions
    description: >
      Run the reward function(s) on the decoded completions to produce a scalar
      reward r_i = R(x, y_i) for i = 1..G. Reward functions may be Python
      callables or a reward model; output shape is [batch_size * G].

  - name: compute-advantages
    description: >
      Compute group-relative advantages by normalizing rewards within each
      prompt group:
        mu     = mean(r_1, ..., r_G)
        sigma  = std(r_1, ..., r_G)
        A_i    = (r_i - mu) / (sigma + epsilon)
      `epsilon` here is a small numerical-stability constant (1e-8 to 1e-4),
      NOT a tunable hyperparameter; it prevents division by zero when all
      rewards in a group are identical. Properties: advantages within a group
      sum to approximately zero, high-reward completions get positive
      advantages and low-reward get negative. In code (TRL), broadcast group
      stats back to per-completion shape with `repeat_interleave(G, dim=0)`
      before dividing.

  - name: compute-log-probs
    description: >
      Compute per-token log-probabilities for each completion under (a) the
      current policy pi_theta (with grad) and (b) the frozen reference policy
      pi_ref (no grad), via log-softmax:
        log_pi(t_j | x, t_<j) = logit(t_j) - logsumexp(logits)
      Sequence-level log-prob is the sum over tokens:
        log_pi(y|x) = sum_j log_pi(t_j | x, t_<j)
      Critical invariant: log_pi <= 0 always, since it is the log of a
      probability in (0, 1]. The "selective" variant (selective_log_softmax)
      avoids materializing the full [batch, seq_len, vocab_size] tensor by
      gathering only the selected token indices; math is identical — verify
      against `F.log_softmax` on a small deterministic input.

  - name: compute-loss
    description: >
      Combine a clipped surrogate objective with a KL divergence penalty:
        ratio  = exp(log_pi_theta(y|x) - log_pi_old(y|x))
        L_clip = min(ratio * A, clip(ratio, 1 - eps_clip, 1 + eps_clip) * A)
        L_kl   = beta * KL(pi_theta || pi_ref)
        loss   = -E[L_clip] + L_kl
      The `ratio` measures how much the policy has shifted from the generation
      policy. Clipping prevents destructively large updates. `beta * KL` keeps
      pi_theta close to pi_ref to prevent degeneration during RL fine-tuning.
      In TRL: `policy_loss = -torch.min(surr1, surr2).mean()` and
      `kl = (log_pi - log_pi_ref).mean() * beta`.

  - name: backprop-and-update
    description: >
      Call `loss.backward()` and `optimizer.step()` (plus scheduler/grad-clip
      as configured) to update pi_theta. pi_ref is frozen and never updated.

decisions:
  - signal: All (or nearly all) rewards within a group are identical.
    action: >
      The numerator (r_i - mu) collapses, so advantages → 0 and the learning
      signal vanishes regardless of epsilon. Diversify sampling (raise
      temperature, top-p) or fix the reward function so it actually
      discriminates between completions.

  - signal: epsilon in advantage normalization is comparable to typical sigma.
    action: >
      The denominator stops reflecting reward variance and advantages shrink
      toward 0 (signal washed out). Keep epsilon in 1e-8 to 1e-4 and much
      smaller than typical reward std. Do not treat advantage-epsilon as a
      knob to tune model behavior.

  - signal: G is too small (G=1 makes std undefined; G=2 is very noisy).
    action: >
      Raise `num_generations`. Typical range is 4–16; pick the smallest G that
      gives stable advantages within compute budget.

  - signal: A per-token log-probability comes out positive.
    action: >
      Invariant violation — log of a probability in (0, 1] must be <= 0.
      Suspect a sign flip in the log-softmax computation, or that raw
      probabilities (not log-probs) are being summed. Verify against
      `F.log_softmax` on a tiny deterministic input.

  - signal: Policy ratio explodes or KL grows unbounded during training.
    action: >
      Either eps_clip is too wide, beta is too small, or learning rate is too
      high. Tighten clipping toward 0.1, raise beta toward 0.1, or drop LR
      into 1e-7 to 5e-6.

  - signal: Need to verify whether a specific implementation detail matches the algorithm spec.
    action: Load `references/grpo-algorithm.md` for the full formulation, notation, and PPO/REINFORCE comparison.

  - signal: Tracing a bug through GRPOTrainer code paths or mapping algorithm steps to specific methods.
    action: Load `references/grpo-trainer-internals.md` for the method-by-method TRL breakdown and data-flow diagram.

search_shortcuts:
  - category: Key Hyperparameters
    body: |
      | Parameter             | Typical Range | Effect                                                                 |
      |-----------------------|---------------|------------------------------------------------------------------------|
      | num_generations (G)   | 4–16          | More = lower-variance group-relative advantages, higher compute cost.  |
      | beta (KL coefficient) | 0.01–0.1      | Higher = more conservative updates (policy stays closer to pi_ref).    |
      | epsilon (clip)        | 0.1–0.2       | Narrower = more conservative policy updates per step.                  |
      | epsilon (advantage)   | 1e-8 – 1e-4   | Numerical-stability only; must be small relative to typical sigma.     |
      | learning_rate         | 1e-7 – 5e-6   | Much lower than SFT; RL is sensitive to LR — high LR drives instability. |

  - category: PPO / REINFORCE Comparison
    body: |
      | Aspect       | REINFORCE         | PPO                       | GRPO                                |
      |--------------|-------------------|---------------------------|-------------------------------------|
      | Advantage    | Reward - baseline | Critic estimate (GAE)     | Group-relative normalization        |
      | Critic       | No                | Yes (value head)          | No                                  |
      | Clipping     | No                | Yes                       | Yes                                 |
      | KL penalty   | Optional          | Optional                  | Yes (typically)                     |
      | Memory       | Low               | High (critic)             | Medium                              |
      GRPO ≈ PPO with the critic replaced by a batch-statistics baseline; closer to REINFORCE with variance reduction via grouping.

  - category: Reference Files (load on demand)
    body: |
      - `references/grpo-algorithm.md` — Full mathematical formulation with notation table, step-by-step derivations, and comparison to PPO and REINFORCE. Load when verifying whether a specific implementation detail matches the algorithm specification.
      - `references/grpo-trainer-internals.md` — TRL GRPOTrainer internals: method-by-method breakdown (`__init__`, `_generate_and_score_completions`, `compute_loss`), data-flow diagram, and how each algorithm step maps to code. Load when tracing bugs through a GRPOTrainer implementation.

anti_patterns:
  - Treating epsilon in advantage normalization as a tunable hyperparameter — it is for numerical stability only and must be small (1e-8 to 1e-4) relative to typical reward std.
  - Dropping the reference policy / KL penalty during RL fine-tuning — without it the policy can degenerate (mode collapse, loss of base-model competencies).
  - Using an SFT-scale learning rate — GRPO needs much lower LR (1e-7 to 5e-6); higher LR drives ratio explosions and unstable KL.
  - Computing group statistics over the global batch instead of per-prompt — each completion must be normalized against the G rewards from its own prompt (use `repeat_interleave(num_generations)` to broadcast back).
  - Forgetting that pi_ref must be frozen (`requires_grad=False`) and run under `torch.no_grad()` — otherwise it tracks pi_theta and KL becomes meaningless.
  - Summing raw probabilities instead of log-probabilities at the sequence level, or producing positive per-token log-probs (invariant violation).
```
