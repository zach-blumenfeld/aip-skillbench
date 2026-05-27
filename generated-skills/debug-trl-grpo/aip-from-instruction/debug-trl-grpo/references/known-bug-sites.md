# Known GRPO Bug Sites in /app/trl

Ordered by likelihood. Open `trl/trainer/grpo_trainer.py` in /app/trl
alongside this list. Each entry: where to look, what correct code does,
what a regression looks like, the smallest fix.

> **Method names vary across TRL versions.** Search by behaviour (the
> reshape, the gather, the mask) rather than by an exact name.

---

## 1. Advantage normalization collapsed to batch-wide

**Where:** Advantage block, usually at the tail of
`_generate_and_score_completions` or in a helper like `_compute_advantages`.

**Correct:**
```python
mean_grouped = rewards.view(-1, self.num_generations).mean(dim=1)
std_grouped  = rewards.view(-1, self.num_generations).std(dim=1)
mean_grouped = mean_grouped.repeat_interleave(self.num_generations, dim=0)
std_grouped  = std_grouped.repeat_interleave(self.num_generations, dim=0)
advantages   = (rewards - mean_grouped) / (std_grouped + 1e-4)
```

**Regression patterns:**
- `rewards.mean()` / `rewards.std()` (no view, no dim).
- `.view(-1, num_generations).mean()` without `dim=1` — reduces to a scalar.
- `dim=0` instead of `dim=1` — reduces across the wrong axis.
- Reshape with `num_generations` swapped with another dim (e.g.
  `view(num_generations, -1)`).

**Symptom:** Every group's rewards collapse to identical advantages
(typically all 0 or all NaN). Logged `reward_std` is 0 every step.

**Fix:** Restore the per-group reduction with `dim=1, keepdim=True` (or
the explicit repeat_interleave pattern above).

---

## 2. Missing eps in the advantage denominator

**Where:** Same advantage block as above.

**Correct:** `(rewards - mean) / (std + 1e-4)` (eps in 1e-4 .. 1e-8).

**Regression patterns:**
- `eps` removed entirely.
- `eps` moved outside the parens: `(rewards - mean) / std + 1e-4` —
  division happens first, so eps is added to the advantage, not the std.

**Symptom:** NaN advantage and NaN loss within a few steps (as soon as
one group has identical rewards).

**Fix:** Restore `+ eps` *inside* the denominator.

---

## 3. Per-token logprob alignment off by one

**Where:** `_get_per_token_logps` (or whatever helper gathers per-token
logprobs).

**Correct:**
```python
logits = model(input_ids, attention_mask=attention_mask).logits[:, :-1, :]
target = input_ids[:, 1:]
per_token_logps = selective_log_softmax(logits, target)   # (B, L-1)
```

**Regression patterns:**
- `logits[:, 1:]` and `input_ids[:, :-1]` (slices swapped).
- No slicing at all → tries to gather logprobs for the BOS token, off
  by one everywhere downstream.
- `selective_log_softmax(logits, input_ids)` without the shift.

**Symptom:** Loss values that look plausible but never decrease, or a
mask alignment that no longer matches (loss == 0 every step because the
mask zeros every position).

**Fix:** Restore the `logits[:, :-1]` and `input_ids[:, 1:]` pair so
position `i` of the output predicts `input_ids[:, i+1]`.

---

## 4. Completion mask sliced wrong

**Where:** `compute_loss`, just before the per-token loss reduction.

**Correct:**
```python
completion_mask = attention_mask[:, 1:]   # shifted to match logprob alignment
# (optionally also zero out prompt positions in the shifted frame)
```

**Regression patterns:**
- `attention_mask[:, :-1]` — slices off the wrong end.
- `attention_mask` with no slice — shape mismatch with `(B, L-1)`
  per-token loss; broadcast or runtime error, or silently zero loss if
  the broadcast happens to align.
- Mask built from prompt-only ids instead of full input ids.

**Symptom:** `loss == 0.0` exactly, every step, no NaN, no error.

**Fix:** Slice the mask as `attention_mask[:, 1:]`. If the trainer also
needs to zero out prompt positions, do that on the shifted mask:
`completion_mask[:, :prompt_length - 1] = 0`.

---

## 5. Loss sign flipped or reduction broken

**Where:** `compute_loss`, where the per-token loss is assembled and
reduced.

**Correct:**
```python
per_token_loss = -advantages.unsqueeze(1) * per_token_logps + self.beta * kl
loss = (per_token_loss * completion_mask).sum(dim=1) / completion_mask.sum(dim=1).clamp(min=1)
loss = loss.mean()
```

**Regression patterns:**
- `per_token_loss = advantages.unsqueeze(1) * per_token_logps` — wrong
  sign; the model unlearns.
- Reduction divides by `L` (sequence length) instead of mask sum →
  short completions get a free pass, long ones over-weighted.
- `.sum()` instead of `.mean()` at the end → loss magnitude scales with
  batch size, gradient explodes or learning rate becomes wrong.

**Symptom (wrong sign):** Reward trends *downward*, not upward.
**Symptom (wrong reduction):** Loss magnitudes way off (10s or 1000s);
gradient norms huge or tiny.

**Fix:** Restore the negative sign in front of `advantages *
per_token_logps`; restore the mask-sum normalization.

---

## 6. Policy forward wrapped in `torch.no_grad()`

**Where:** Wherever `_get_per_token_logps` is called for the policy
(not the reference).

**Correct:**
```python
per_token_logps = self._get_per_token_logps(self.model, input_ids, attention_mask)
with torch.no_grad():
    ref_per_token_logps = self._get_per_token_logps(self.ref_model, input_ids, attention_mask)
```

**Regression patterns:**
- A `with torch.no_grad():` block wrapping *both* calls.
- A stray `.detach()` on `per_token_logps` before it enters the loss.
- The trainer's `_get_per_token_logps` itself wraps the forward in
  `no_grad` unconditionally.

**Symptom:** Loss computes a normal finite number but
`loss.requires_grad` is False, `loss.grad_fn` is None,
`loss.backward()` errors or no-ops, model weights never change.

**Fix:** Remove the `no_grad` wrap from the *policy* call. Keep it on
the reference call.

---

## 7. KL term included over all tokens (or wrong sign)

**Where:** `compute_loss`, KL section.

**Correct:** KL uses the k3 estimator (DeepSeek), is masked to
completion tokens, and added to the loss with `+ self.beta`.

```python
log_ratio = ref_per_token_logps - per_token_logps
kl        = torch.exp(log_ratio) - log_ratio - 1
per_token_loss = -advantages.unsqueeze(1) * per_token_logps + self.beta * kl
# masked reduction as above
```

**Regression patterns:**
- KL summed without applying `completion_mask` (padding KL inflates loss).
- `- self.beta * kl` (wrong sign — model pushed away from reference).
- `self.beta` accidentally set to a huge value in a config default.

**Symptom:** KL term dominates total loss; logged `kl` is large
(>> 0.1); policy collapses toward reference or runs away from it.

**Fix:** Mask the KL to completion tokens; verify `+ beta * kl`;
verify `beta` is a sensible scalar (0.0 to ~0.1 typical for GRPO).

---

## 8. Reward aggregation across multiple reward funcs broken

**Where:** Inside `_generate_and_score_completions`, where individual
reward function outputs are combined.

**Correct:**
```python
rewards_per_func = torch.tensor([rf(...) for rf in self.reward_funcs])   # (R, B*G)
rewards = (rewards_per_func * self.reward_weights[:, None]).sum(dim=0)   # (B*G,)
```

**Regression patterns:**
- Reduces over the wrong dim (collapses across batch instead of across
  reward functions).
- Drops all but the first reward function silently.
- Weights vector wrong length or all zeros.

**Symptom:** Logged reward components don't match what `reward_fn`
returns in isolation; mean reward is much smaller or larger than
expected; only some reward functions appear to be doing work.

**Fix:** Restore the per-function reduction and weight broadcast. For
single-reward setups (just one reward fn), the reward tensor should
equal that function's output directly.

---

## 9. Stale install — edits never take effect

**Where:** Not in the code itself. In the environment.

**Symptom:** You edit /app/trl/trl/trainer/grpo_trainer.py, re-run, and
behaviour is identical.

**Check:**
```bash
python -c "import trl; print(trl.__file__)"
```

If this doesn't resolve to `/app/trl/trl/__init__.py`, the training
script is using a wheel-installed TRL.

**Fix:**
```bash
pip install -e /app/trl --force-reinstall --no-deps
```

Then re-verify. Until `import trl` resolves to /app/trl, debugging is
pointless because no edit takes effect.

---

## Quick-Scan Order

When time is short, eyeball in this order — these are the patterns
most likely to be the bug given the "no improvement on countdown" signal:

1. Advantage normalization reduction axis (`dim=1` vs `dim=0` vs missing).
2. Completion mask shift (`[:, 1:]` vs `[:, :-1]`).
3. Policy forward `no_grad` wrap.
4. Loss sign in front of `advantages * per_token_logps`.
5. Reward aggregation when multiple reward functions are configured.
