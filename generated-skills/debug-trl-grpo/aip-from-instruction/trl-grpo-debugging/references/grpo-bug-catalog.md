# GRPO "no improvement" bug catalog

Load this when localizing a planted bug in the `trl` GRPO trainer. Each entry gives the
**symptom**, the **site** (see `grpo-algorithm.md`), how to **detect** it (static read +
runtime metric), and the **buggy → correct** shape of the code. Work the catalog top-down:
the first three categories cause a *fully flat* reward curve and are the most common plants.

The constraint that matters: the bug is in `trl` library source, never in `train_grpo.py`
or `reward_fn.py`. So rewards arrive at the trainer correctly — the trainer mishandles them.

---

## A. Gradient detached / no_grad — *strongest no-improvement signal*

**Symptom:** reward perfectly flat from step 0; `loss` is a finite number but the model
never changes. Weights identical before/after `optimizer.step()`.

**Site:** #2 (per-token logps) or #3 (ratio).

**Detect:**
- Static: search the policy log-prob path for `torch.no_grad()`, `.detach()`,
  `with torch.inference_mode()`, or `@torch.no_grad()` decorators wrapping the *current*
  model forward. The reference model forward SHOULD be under no_grad; the policy forward
  must NOT.
- Static: in the ratio, check that `coef_1 = exp(per_token_logps - old_per_token_logps)`
  uses the **non-detached** `per_token_logps` for the minuend. A plant that writes
  `exp(old_per_token_logps - old_per_token_logps)` or detaches both terms makes the ratio a
  constant 1.0 with no parameter dependence → zero gradient.
- Runtime: `loss.requires_grad` is `False`, or `grad_norm == 0`, or `per_token_logps.requires_grad`
  is `False`.

**Correct:** policy forward runs with grad enabled; only the reference/old pass is detached.

---

## B. Zero / constant advantages

**Symptom:** reward flat; gradients may be non-zero but tiny/noise; advantages print as all
≈ 0 (or a single constant) every step.

**Site:** #1 (advantage).

**Detect:**
- Static: check the centering and scaling. Bugs include:
  - `advantages = rewards - rewards` (or subtracting the per-sample value instead of the
    group mean) → identically 0.
  - dividing by `std` when `scale_rewards` should leave it, or multiplying by 0.
  - subtracting a **global** mean/std instead of the **per-group** mean/std (loses the
    group-relative signal; advantages become weak/near-zero when groups are similar).
- Runtime: log `advantages.abs().mean()` and `advantages.std()`. Both ≈ 0 across many steps
  with varied rewards ⇒ this bug. (A single all-equal-reward group giving 0 is normal.)

**Correct:** `advantages = rewards - mean_grouped[/ (std_grouped + eps)]` with per-group stats.

---

## C. `repeat` vs `repeat_interleave` (group scrambling) — *GRPO-specific*

**Symptom:** reward flat or erratic with no upward trend; advantages are non-zero but
*assigned to the wrong completions*, so the policy gets contradictory signal.

**Site:** #1 (advantage), the step that broadcasts group stats back to completions.

**Detect:**
- Static: the group mean/std are shape `(B,)` and must map onto `(B*G,)` completions ordered
  `[p0g0..p0g(G-1), p1g0..]`. `repeat_interleave(G)` gives `[m0,m0,...,m0,m1,...]` (correct).
  `repeat(G)`/`tile` gives `[m0,m1,...,m0,m1,...]` (wrong — baseline subtracted from the wrong
  prompt's completions). Also check `rewards.view(-1, num_generations)` uses the right
  dimension order (not `view(num_generations, -1)`, which transposes the grouping).
- Runtime: within-group advantage sums should be ≈ 0. If they aren't, the grouping is scrambled.

**Correct:** `stat.repeat_interleave(num_generations, dim=0)` and `view(-1, num_generations)`.

---

## D. Completion mask inverted or misaligned

**Symptom:** reward flat; loss is non-zero and grads flow, but the policy is being trained on
the wrong tokens (prompt/padding) so completion quality never improves. Or
`completion_mask.sum() == 0` ⇒ loss has no real tokens.

**Site:** #5 (masked aggregation) and the mask construction.

**Detect:**
- Static: look for `1 - completion_mask`, a mask built from the prompt instead of the
  completion, or a normalizer that divides by the wrong count (e.g. by total length instead
  of `completion_mask.sum()`). Verify the mask is sliced/shifted the same way as
  `per_token_logps`.
- Runtime: log `completion_mask.sum()` (should be > 0 and ≈ total completion tokens) and the
  fraction of masked-in tokens that are actually completion tokens.

**Correct:** mask = 1 on real completion tokens, aligned with the log-prob shift; divide by
`completion_mask.sum().clamp(min=1)`.

---

## E. Log-prob / token off-by-one (gather shift)

**Symptom:** reward flat; loss looks plausible but log-probs correspond to the wrong tokens,
so the gradient pushes meaningless directions.

**Site:** #2 (per-token logps).

**Detect:**
- Static: confirm `logits = logits[:, :-1, :]` paired with `ids = input_ids[:, 1:]`. A plant
  drops one of the slices, shifts the wrong way, or gathers with mismatched indices in
  `selective_log_softmax`/`torch.gather`. Check helper functions the trainer imports.
- Runtime: for a held-out known sequence, recompute one token's logp by hand and compare.

**Correct:** logits at position `t` score `input_ids[t+1]`; gather realized-token logp accordingly.

---

## F. Loss sign flipped

**Symptom:** reward *decreases* / model degrades or diverges (NOT a flat curve). Listed for
completeness — if the curve trends down, suspect this first.

**Site:** #4. **Detect (static):** the surrogate must be negated: `-min(loss1, loss2)`. A
missing/extra sign turns gradient ascent into descent. **Correct:** `per_token_loss = -min(...)`.

---

## G. KL penalty too strong

**Symptom:** reward improves extremely slowly or not at all; KL term dominates the loss.

**Site:** #6. **Detect:** static — trainer hardcodes/rescales `beta` to a large value, or
applies the KL with the wrong sign so it actively pulls toward the reference. Runtime — the
KL term magnitude dwarfs the policy term. **Correct:** `beta` honored from config; KL added,
not subtracted, with a small coefficient.

---

## H. Clip range collapses the update

**Symptom:** reward flat; effective gradient ≈ 0 because nearly all tokens are clipped.

**Site:** #3/#4. **Detect:** static — `epsilon_low`/`epsilon_high` set to 0 (or
`clamp(coef_1, 1, 1)`), so `coef_2` is pinned and `min` always picks the constant branch →
no gradient. Runtime — clip fraction ≈ 100%. **Correct:** small non-zero epsilon (e.g. 0.2).

---

## Triage order

1. **A** and **B/C** first — they produce the textbook flat curve and are the usual plant.
2. If grads are non-zero and advantages look right, go to **D** then **E**.
3. If reward *worsens*, jump to **F**.
4. If reward barely creeps, check **G** then **H**.

Always confirm with a runtime metric, not just a code read — a single change can look right
in isolation but break an invariant (e.g. a detach that "looks harmless").
