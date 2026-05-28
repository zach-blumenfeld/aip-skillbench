# GRPO — correct algorithm and TRL trainer reference

Use this to build a precise mental model of what a *correct* GRPO update looks like,
then diff the local `trl` source against it. A planted "no improvement" bug is almost
always a small deviation at one of the computation sites below. You don't need RL basics
explained — this covers only the GRPO-specific math and TRL's exact computation sites.

## Pipeline (per training step)

GRPO (Group Relative Policy Optimization) replaces PPO's learned value/critic with a
*group baseline*: for each prompt, sample a group of `G = num_generations` completions,
score them, and use the group's mean reward as the baseline.

1. **Generate** `G` completions per prompt from the current policy (the "old" policy at
   generation time).
2. **Score** every completion with the reward function(s) → scalar reward `r_i`.
3. **Advantage**: normalize rewards *within each group of G* → `Â_i`.
4. **Log-probs**: forward the policy over `prompt+completion`, gather per-token log-probs
   of the realized completion tokens.
5. **Loss**: clipped policy-gradient surrogate, weighted by `Â_i`, optionally plus a KL
   penalty to a frozen reference model, **averaged over completion tokens only**.
6. **Backprop + optimizer step**: update the policy.

If the model shows *no improvement* (reward curve flat), the gradient signal is either
zero, detached from the parameters, or pointed at the wrong quantity. The four highest-yield
suspects are advantage, gradient connectivity, the completion mask, and the log-prob/token
alignment.

## Critical computation sites (correct forms)

### 1. Group-relative advantage

```python
# rewards: shape (B * G,)   — flat, grouped as [p0g0, p0g1, ..., p0g(G-1), p1g0, ...]
mean_grouped = rewards.view(-1, num_generations).mean(dim=1)   # (B,)
std_grouped  = rewards.view(-1, num_generations).std(dim=1)    # (B,)

# Map each group statistic back onto its G completions. MUST be repeat_interleave,
# NOT repeat/tile — interleave keeps [m0,m0,...,m0,m1,...]; repeat gives [m0,m1,...,m0,m1,...].
mean_grouped = mean_grouped.repeat_interleave(num_generations, dim=0)
std_grouped  = std_grouped.repeat_interleave(num_generations, dim=0)

advantages = rewards - mean_grouped
if scale_rewards:                       # TRL default: True
    advantages = advantages / (std_grouped + 1e-4)
```

Invariants when correct:
- Within any group, `advantages` sum to ≈ 0 (mean-centered).
- Across a batch with reward variation, `advantages` are **not** all zero and **not** constant.
- Zero advantage for a *single* group is normal when every completion in that group earned
  the identical reward (e.g. all 0 early in training). Zero advantage for *every* group across
  many steps is a bug.

### 2. Per-token log-probs (alignment is fragile)

```python
logits = model(input_ids, attention_mask=attention_mask).logits  # (B, L, V)
logits = logits[:, :-1, :]              # drop last position: it predicts the token AFTER the seq
ids    = input_ids[:, 1:]               # shift: logits[:,t] predicts ids_orig[:,t+1]
per_token_logps = selective_log_softmax(logits, ids)   # gather logp of the realized token
# then slice to completion region only (drop prompt tokens) before masking
```

Invariants when correct:
- `per_token_logps` line up with completion tokens (off-by-one shift handled).
- `per_token_logps.requires_grad is True` for the policy model (gradient must flow).

### 3. Probability ratio (importance weight)

```python
# old_per_token_logps: logps under the policy that GENERATED the samples.
# With the default num_iterations == 1, old == current.detach() (single inner step).
old_per_token_logps = inputs.get("old_per_token_logps")
if old_per_token_logps is None:
    old_per_token_logps = per_token_logps.detach()

coef_1 = torch.exp(per_token_logps - old_per_token_logps)         # ratio; grad flows via current
coef_2 = torch.clamp(coef_1, 1 - epsilon_low, 1 + epsilon_high)   # PPO clip
```

Invariants when correct:
- At the first inner step, `coef_1 ≈ 1.0` (current == old), but **`coef_1` still depends on
  the current parameters** — `per_token_logps` is NOT detached. This is the subtle part:
  `exp(current - current.detach())` equals 1 numerically yet carries gradient. If *both*
  terms are detached/old, the ratio is a constant and the gradient vanishes → no learning.

### 4. Clipped surrogate loss (sign + min)

```python
per_token_loss1 = coef_1 * advantages.unsqueeze(1)
per_token_loss2 = coef_2 * advantages.unsqueeze(1)
per_token_loss  = -torch.min(per_token_loss1, per_token_loss2)   # NEGATIVE: we maximize reward

if beta != 0.0:                          # optional KL penalty to frozen reference
    per_token_loss = per_token_loss + beta * per_token_kl
```

Invariants when correct:
- The leading sign is **negative** (loss = −surrogate; we ascend reward by descending loss).
  A flipped sign makes reward *decrease* (degradation/divergence), not flatten — but note it
  in the catalog.
- `advantages` is broadcast across the token axis (`.unsqueeze(1)`), shape compatible with
  the per-token tensors.

### 5. Masked aggregation over completion tokens

```python
# completion_mask: 1 for real completion tokens, 0 for padding/prompt. Aligns with per_token_loss.
loss = (per_token_loss * completion_mask).sum() / completion_mask.sum().clamp(min=1.0)
```

Invariants when correct:
- `completion_mask.sum() > 0` (there are tokens to learn from).
- The mask selects *completion* tokens, not prompt tokens, and is aligned with the same
  shift applied to log-probs.

### 6. KL penalty (only when `beta != 0`)

```python
per_token_kl = torch.exp(ref_logps - per_token_logps) - (ref_logps - per_token_logps) - 1
```

A `beta` that is far too large drowns the reward signal → policy can't move → flat reward.
`beta` is usually a config value, but a trainer that hardcodes or rescales it internally can
introduce this.

## Where the code lives

TRL's GRPO logic is in `trl/trainer/grpo_trainer.py` (class `GRPOTrainer`). The sites above
map to these methods (names vary slightly by TRL version — grep, don't assume):

- `_generate_and_score_completions` / `_prepare_inputs` → reward + advantage computation.
- `_get_per_token_logps` (or `_get_per_token_logps_and_entropies`) → site #2.
- `compute_loss` / `_compute_loss` → sites #3, #4, #5, #6.

Also check `trl/trainer/grpo_config.py` and any `utils.py` (e.g. `selective_log_softmax`) the
trainer imports — the bug may be in a helper, not the trainer method itself.

## Quick recall

| Symptom | Most likely broken site |
|---|---|
| `loss.requires_grad` is False / grad norm 0 | #2 (no_grad/detach) or #3 (both terms detached) |
| advantages all ≈ 0 every step | #1 (mean/std, repeat vs repeat_interleave, sign) |
| reward gets *worse* over time | #4 (loss sign flipped) |
| loss is NaN/Inf then frozen | #1 (std without eps) or #2 (gather OOB) |
| reward flat, grads non-zero, advantages fine | #5 (mask inverted/misaligned) or #2 (logp shift) |
| reward barely moves, very slow | #6 (beta too large) or #1 (scaling off) |
