# GRPO Algorithm Architecture (TRL Reference)

Background reference for the `debug-trl-grpo` skill. Read only when the
known-bug-site scan finds nothing and you need to instrument the trainer
against algorithmic invariants.

## What GRPO Does

Group Relative Policy Optimization (DeepSeek, 2024) is a variant of PPO
that removes the value/critic model. For each prompt `q`, the trainer
samples `G` completions `{o_1, ..., o_G}` from the current policy `π_θ`,
scores each with a reward function `r(q, o_i)`, and computes a
**group-relative advantage**:

```
A_i = (r_i - mean(r_1..r_G)) / (std(r_1..r_G) + eps)
```

The advantage is a pure scalar per completion — no value network, no GAE,
no bootstrapping. The baseline is the group mean.

The loss is a clipped surrogate (PPO-style) plus a KL penalty against a
fixed reference model `π_ref`:

```
ratio_t = exp(logπ_θ(a_t|s_t) - logπ_old(a_t|s_t))      # importance ratio
surr1   = ratio_t * A_i
surr2   = clip(ratio_t, 1-ε, 1+ε) * A_i
policy_loss_t = -min(surr1, surr2)
kl_t          = exp(logπ_ref - logπ_θ) - (logπ_ref - logπ_θ) - 1   # k3 estimator
loss_t        = policy_loss_t + beta * kl_t
loss          = mean over completion tokens (mask out prompt + padding) per sequence,
                then mean over sequences
```

(For single-step on-policy GRPO with `π_old == π_θ`, `ratio_t == 1` and
the surrogate collapses to `-A_i * logπ_θ`. Many implementations skip the
clip in this regime.)

## TRL File Layout

```
/app/trl/
├── trl/
│   ├── __init__.py
│   ├── trainer/
│   │   ├── grpo_trainer.py        # GRPOTrainer class — primary debug target
│   │   ├── grpo_config.py         # GRPOConfig dataclass
│   │   └── utils.py               # selective_log_softmax, pad, etc.
│   └── models/
│       └── ...                    # ref model wrappers
└── ...
```

Confirm with:

```bash
find /app/trl -name "grpo_trainer.py"
python -c "import trl; print(trl.__file__)"
```

## The Five Methods That Matter

All five live in `GRPOTrainer` in `trl/trainer/grpo_trainer.py`. The
exact names may have small variations across TRL versions — search by
behaviour, not just name.

### 1. `_generate_and_score_completions`

- Samples `G` completions per prompt (total batch = `B * G`).
- Calls every reward function in `self.reward_funcs`.
- Returns prompt_ids, completion_ids, attention_mask, rewards.

**Invariants:**
- `completion_ids.shape[0] == prompts * G`.
- `rewards.shape == (prompts * G,)` (sum or mean across reward funcs, depending on `reward_weights`).
- Reward values are real numbers; not all identical across the batch (if they are, the reward function is degenerate).

### 2. Advantage computation (often inside `_generate_and_score_completions`)

```python
# Correct
mean_grouped_rewards = rewards.view(-1, self.num_generations).mean(dim=1)
std_grouped_rewards  = rewards.view(-1, self.num_generations).std(dim=1)
mean_grouped_rewards = mean_grouped_rewards.repeat_interleave(self.num_generations, dim=0)
std_grouped_rewards  = std_grouped_rewards.repeat_interleave(self.num_generations, dim=0)
advantages = (rewards - mean_grouped_rewards) / (std_grouped_rewards + 1e-4)
```

**Invariants:**
- Reduction is over `dim=1` (the within-group axis), not the full batch.
- `+ eps` in the denominator (small constant; 1e-4 to 1e-8 typical).
- `advantages.shape == rewards.shape`.
- For a group with non-identical rewards, at least one advantage value is non-zero.

### 3. `_get_per_token_logps`

Given `input_ids` and `attention_mask`, runs a forward pass and gathers
the logprob of the actual next token at every position.

```python
# Correct alignment
logits = model(input_ids, attention_mask=attention_mask).logits   # (B, L, V)
logits = logits[:, :-1, :]                                        # drop final position
input_ids = input_ids[:, 1:]                                      # shift to predicted tokens
per_token_logps = selective_log_softmax(logits, input_ids)        # (B, L-1)
```

**Invariants:**
- Output shape is `(B, L-1)` — one fewer than input length.
- `per_token_logps[:, i]` is the logprob of `input_ids[:, i+1]` under the model after seeing `input_ids[:, :i+1]`.
- Policy variant has `requires_grad=True`; reference variant runs under `with torch.no_grad():`.

### 4. Completion mask and loss reduction (inside `compute_loss`)

The loss must only be computed over completion tokens, not prompt or
padding tokens.

```python
# Correct
completion_mask = attention_mask[:, 1:]                  # shifted to match logprob alignment
# Optionally also zero out prompt positions:
prompt_length = prompt_ids.shape[1]
completion_mask[:, :prompt_length - 1] = 0               # the -1 accounts for the shift

per_token_loss = -advantages.unsqueeze(1) * per_token_logps   # (B, L-1)
loss = (per_token_loss * completion_mask).sum(dim=1) / completion_mask.sum(dim=1).clamp(min=1)
loss = loss.mean()
```

**Invariants:**
- Mask is shifted by 1 to match the logprob alignment.
- Mask is non-zero on completion tokens, zero elsewhere.
- Per-sequence reduction divides by mask sum (not by L) so short completions aren't penalized.
- Final loss is a scalar with `requires_grad=True` and a non-None `grad_fn`.

### 5. KL term and reference logprobs

```python
# Correct
with torch.no_grad():
    ref_per_token_logps = _get_per_token_logps(self.ref_model, input_ids, attention_mask)

# k3 unbiased KL estimator (DeepSeek)
log_ratio = ref_per_token_logps - per_token_logps
kl = torch.exp(log_ratio) - log_ratio - 1                # (B, L-1)
per_token_loss = -advantages.unsqueeze(1) * per_token_logps + self.beta * kl
# ... mask and reduce as above
```

**Invariants:**
- Reference forward is under `no_grad`; policy forward is not.
- KL is computed on the same tokens as the policy logprob (same alignment).
- KL is masked to completion tokens (padding KL is spurious).
- `beta >= 0`; sign is `+ beta * kl` (penalize divergence).

## Diagnostic Invariants Cheatsheet

| Quantity | Healthy | Broken interpretation |
|----------|---------|-----------------------|
| reward_std (within group) | > 0 most steps | == 0 every step → group reshape broken or rewards degenerate |
| advantage tensor | mean ≈ 0, std ≈ 1 | all zeros → reshape/eps broken; NaN → missing eps |
| per_token_logps shape | (B, L-1) | (B, L) → alignment off by one |
| completion_mask sum | matches completion token count | 0 → mask sliced wrong direction; == L → prompt tokens included |
| loss | finite, non-zero, has grad_fn | 0 → mask or detach bug; NaN → eps or overflow; no grad_fn → no_grad wraps policy forward |
| KL | small positive (0.001–0.1) | huge → mask includes padding; or beta wrong sign |
| weight delta between steps | non-zero on trainable params | 0 → grad disconnected, requires_grad off, or optimizer missing the params |

## Why a Group Baseline Is Load-Bearing

GRPO's whole point is that the **within-group baseline** subtracts the
average performance of the policy on that exact prompt. If you reduce
across the entire batch instead, you subtract a global average over
*different prompts* — easy vs hard prompts get mixed, the per-prompt
signal collapses, and the policy receives no gradient because every
completion is "average" relative to the wrong reference. This is the
single most common GRPO regression: a one-character `dim=1` deletion
in the mean/std call.

## References

- DeepSeek GRPO paper: arXiv:2402.03300 (DeepSeekMath, §4.1).
- TRL upstream: https://github.com/huggingface/trl/blob/main/trl/trainer/grpo_trainer.py — use as canonical reference but expect drift; the vendored /app/trl is the source of truth for this task.
