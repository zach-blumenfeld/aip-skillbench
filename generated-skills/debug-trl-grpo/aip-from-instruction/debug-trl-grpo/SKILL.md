---
name: debug-trl-grpo
description: Diagnose and fix a TRL GRPO trainer (source at /app/trl) when a countdown-math training run reports no model improvement, without modifying /app/train_grpo.py or /app/reward_fn.py. Walks the GRPO algorithm step-by-step against the file layout in trl/trainer/, isolates the regions where regressions silently kill the learning signal (advantage normalization, per-token logprob alignment, completion mask, loss reduction, KL/reference flow), uses git history as the first-pass diff source, and verifies fixes with a short smoke training run that surfaces reward, reward_std, kl, and loss. Use when GRPO training is flat or noisy, the training script and reward function are confirmed off-limits, and the suspected bug lives inside the TRL package source.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
compatibility: Requires a working /app environment with a vendored TRL checkout at /app/trl, a training script at /app/train_grpo.py, a reward function at /app/reward_fn.py, plus python, pip/uv, and torch already installed. Smoke training assumes a GPU is available but degrades to CPU.
---

```yaml
purpose: >
  Find and patch the single regression inside /app/trl that is silently
  killing the learning signal of a countdown-math GRPO run. The training
  script (/app/train_grpo.py) and the reward function (/app/reward_fn.py)
  are off-limits — the bug is inside the TRL package. GRPO has a small set
  of well-known failure modes (advantage normalization that collapses to
  zero, per-token logprob/mask misalignment by one position, a sign flip
  in the policy-gradient loss, a KL term that overwhelms the policy,
  reference-model logprobs computed under no_grad on the wrong tokens, or
  a group reshape that breaks the within-prompt baseline). This skill
  walks those sites in order, uses git history to spot recent regressions
  first, and validates the fix with a short training loop that surfaces
  reward, reward_std, kl, and loss.

trigger_when:
  - A TRL GRPO training run shows flat or noisy reward with no upward trend after dozens of steps.
  - User reports "model isn't improving", "loss is 0", or "advantage is 0" with TRL GRPO.
  - The task names /app/trl as the source under investigation and forbids edits to /app/train_grpo.py and /app/reward_fn.py.
  - A countdown / math-reasoning GRPO task where rewards are clearly being computed but the policy never shifts.
  - Recent change to a vendored TRL checkout coincided with the regression.

do_not_use_when:
  - The fix would require editing /app/train_grpo.py or /app/reward_fn.py (the task forbids it — re-scope or stop).
  - The task is hyperparameter tuning a working GRPO run (use a tuning skill instead — this skill assumes a regression, not slow convergence).
  - The trainer in use is PPO, DPO, ORPO, or SFT, not GRPO (the bug sites listed here are GRPO-specific).
  - The bug is in dataset construction, tokenizer, or chat template (those live outside /app/trl).

scope_and_approval: >
  Read freely across /app/trl, /app/train_grpo.py, /app/reward_fn.py, and
  anything else in /app. Apply edits only under /app/trl/. Reinstall the
  edited package in-place (`pip install -e /app/trl` or equivalent) so the
  training script picks up the change. Smoke training runs are bounded
  (max 50 steps) and write only to a scratch output_dir under /tmp. Do
  not push changes anywhere, do not modify the two forbidden files, and
  do not change GRPOConfig values in the training script to "force"
  learning before isolating the bug.

steps:
  - name: read-contract
    description: >
      Read /app/train_grpo.py and /app/reward_fn.py end-to-end (read-only).
      Record the exact GRPOConfig values that the trainer must satisfy:
      `num_generations` (group size G), `per_device_train_batch_size`,
      `gradient_accumulation_steps`, `beta` (KL coefficient), `max_prompt_length`,
      `max_completion_length`, `learning_rate`, `loss_type` if set. Record
      what `reward_fn` returns (single scalar per completion vs list of
      scalars per reward function; range and typical magnitude on countdown).
      This is the contract the patched trainer must honour. Treat these
      two files as immutable.

  - name: map-trl-source
    description: >
      Locate the GRPO trainer inside /app/trl. Standard layout
      (transformers/trl vendored): `trl/trainer/grpo_trainer.py` holds
      `GRPOTrainer`; `trl/trainer/grpo_config.py` holds `GRPOConfig`;
      shared helpers live in `trl/trainer/utils.py` and `trl/models/`.
      Confirm with `find /app/trl -name "grpo_trainer.py"` and
      `python -c "import trl; print(trl.__file__)"`. If `import trl`
      resolves somewhere other than /app/trl, the editable install is
      stale — fix that first (`pip install -e /app/trl`) before anything
      else, because every subsequent edit will be invisible to the
      training script otherwise.

  - name: git-history-scan
    description: >
      Run `git -C /app/trl log --oneline -20` and
      `git -C /app/trl log --oneline -- trl/trainer/grpo_trainer.py trl/trainer/grpo_config.py`.
      Diff the most recent commits that touch the GRPO trainer:
      `git -C /app/trl show HEAD -- trl/trainer/grpo_trainer.py`,
      then `git -C /app/trl diff HEAD~1 -- trl/trainer/grpo_trainer.py`
      (and a few revisions back). A regression is the most common
      cause of "trained fine before, stuck now" and is almost always
      one commit deep. If a single hunk in `_generate_and_score_completions`,
      `_get_per_token_logps`, `compute_loss`, the advantage block, or the
      reward aggregation looks suspicious, treat that as the prime
      suspect for the rest of the procedure.

  - name: scan-known-bug-sites
    description: >
      Open references/known-bug-sites.md and walk every entry against
      the actual code in /app/trl/trl/trainer/grpo_trainer.py. Each
      entry names the function, the correct behaviour, the broken
      pattern, and the smallest-possible fix. Order: (1) advantage
      normalization and group reshape, (2) per-token logprob gather
      and shift, (3) completion mask construction and alignment,
      (4) loss sign and reduction, (5) reference-model logprobs and
      KL term, (6) reward aggregation across multiple reward funcs.
      Stop scanning once a confirmed bug is found.
    depends_on: [map-trl-source, git-history-scan]

  - name: deepen-on-algorithm
    description: >
      If the bug-site scan finds nothing obvious, read
      references/grpo-architecture.md for the algorithm derivation
      and the per-method invariants the trainer must satisfy
      (advantage = (r - mean_group) / (std_group + eps); loss = -E[A *
      logπ(a|s)] + β·KL; gradient must flow only through the policy
      logprobs, never through rewards or advantages). Use these
      invariants to instrument the trainer (see full-audit mode) and
      catch a violation the bug-site list missed.
    depends_on: [scan-known-bug-sites]

  - name: smoke-test-baseline
    description: >
      Before patching, capture a baseline. Run scripts/smoke_train.sh
      for ~10 steps and record `reward`, `reward_std`, `kl`, `loss`,
      and `completion_length` from the TRL logger. A healthy GRPO run
      has reward_std > 0 within each group (otherwise advantages are
      zero), kl small but non-zero, and loss non-zero. A baseline of
      reward_std == 0 confirms the regression collapses the within-group
      signal; loss == 0 confirms either mask or gradient is broken.
    depends_on: [map-trl-source]

  - name: localize-and-patch
    description: >
      Apply the smallest possible change in /app/trl/. Prefer reverting
      a regression hunk identified by `git diff` over rewriting. Do not
      refactor surrounding code, do not "improve" naming, do not add
      defensive try/excepts. Only the regression. If trl was installed
      editable (`pip install -e`), the change is live immediately. If
      installed normally, reinstall: `pip install -e /app/trl --force-reinstall --no-deps`.
    depends_on: [scan-known-bug-sites]

  - name: smoke-test-fix
    description: >
      Re-run scripts/smoke_train.sh and compare against the baseline.
      A correct fix produces: reward_std > 0 across groups within a
      few steps; loss in a normal range (1e-3 to 1.0, not 0 and not
      NaN); mean reward begins to trend upward within ~20 steps. If
      reward moves but is unstable, accept the fix — GRPO is noisy by
      design — and verify over more steps. If reward is still flat,
      return to scan-known-bug-sites; the regression has more than
      one site.
    depends_on: [localize-and-patch]

  - name: confirm-and-document
    description: >
      Run one longer smoke (30–50 steps) and confirm mean reward trends
      upward. Write a one-line summary noting the file:line of the
      regression, what was wrong, and what changed. Do not refactor.
      Do not modify the two forbidden files.
    depends_on: [smoke-test-fix]

decisions:
  - signal: All sampled completions inside a group earn identical reward, every step.
    action: >
      Advantage = (reward - mean_group) / (std_group + eps) collapses to
      0/eps = 0 → no gradient. Inspect the group reshape: the correct call
      is `rewards.view(-1, num_generations)` followed by per-row mean and
      std (`dim=1, keepdim=True`). A regression that drops `dim=1` reduces
      across the whole batch and produces zero within-group variance even
      when completions differ. Also check that `eps` isn't so large it
      dominates std and squashes the signal.

  - signal: reward_std > 0 in the logged metrics but every advantage value is still 0.
    action: >
      The reshape is correct in the metric but wrong in the loss path
      (or vice versa — two separate reshapes that drifted apart). Verify
      the advantage tensor fed into the loss uses the same view as the
      logged metric.

  - signal: Loss is exactly 0.0 from step 1, no NaN, no error.
    action: >
      Either the completion mask is all zeros (so the per-token loss
      sums to nothing) or the per-token logprobs are detached from the
      graph. Check `_get_per_token_logps` for a stray `.detach()` or
      `with torch.no_grad():` around the policy forward (the reference
      forward must be no_grad; the policy forward must not). Then check
      the completion mask alignment: per-token logprobs cover positions
      `1..L` predicting tokens `1..L`, so the mask must be sliced to the
      completion region of `input_ids[:, 1:]`, not `input_ids[:, :-1]`.

  - signal: Loss is NaN or Inf from step 1.
    action: >
      Almost always a numerical issue: division by std without `+ eps`
      when a group has identical rewards, log of zero in the KL term,
      or fp16/bf16 overflow in the exponentiated importance ratio.
      Inspect the order of operations and add the missing `eps` (typical
      value 1e-4 to 1e-8) without rewriting the formula.

  - signal: Reward varies across completions but model weights never change between steps.
    action: >
      Gradient is not connected to the policy parameters. Confirm
      `model.train()` is set, `requires_grad` is True on the policy
      params (not just adapters if PEFT), and the loss tensor's
      `requires_grad` and `grad_fn` are non-None just before
      `loss.backward()`. Also confirm the optimizer's parameter group
      includes the actual trainable params.

  - signal: KL term dominates total loss; policy collapses toward the reference distribution.
    action: >
      `beta` may be wrong sign or magnitude in the loss, or the KL is
      computed per-token without masking padding (so padding tokens
      add a huge spurious KL). Verify the formula:
      `loss = -E[A · logπ] + beta · KL(π || π_ref)`, with the KL
      summed over completion tokens only, then averaged.

  - signal: Recent commit in /app/trl touches grpo_trainer.py.
    action: >
      Diff that commit first; revert or repair the changed region
      before broadening the search. A single-commit regression is the
      most common pattern in this task.

  - signal: "`import trl` resolves to a path other than /app/trl."
    action: >
      Editable install is stale; the training script is using a wheel-
      installed TRL, not the source under /app/trl. Run
      `pip install -e /app/trl --force-reinstall --no-deps`, then
      re-verify with `python -c "import trl; print(trl.__file__)"`.
      Until this resolves to /app/trl/trl/__init__.py, no edit you
      make can take effect.

  - signal: Smoke test shows reward improves but loss is negative and growing in magnitude.
    action: >
      Expected for `loss = -E[A · logπ]`: negative loss simply means
      A · logπ is positive on average (good completions getting more
      probability). Do not "fix" the sign; check reward instead.

modes:
  - name: quick-triage
    body: >
      Time-boxed first pass (~10 min). Read /app/train_grpo.py and
      /app/reward_fn.py for the contract, run `git -C /app/trl log
      --oneline -20`, diff the most recent commit touching
      grpo_trainer.py, and walk the six known-bug sites in
      references/known-bug-sites.md against the current code. If a
      regression jumps out, patch it, run scripts/smoke_train.sh, and
      check for reward movement. Most regressions in this scenario
      surface here.

  - name: full-audit
    body: >
      Used when quick-triage finds nothing. Instrument the trainer
      with prints (or torch hooks) at four points: (1) inside
      `_generate_and_score_completions` after rewards are computed,
      print mean/std/min/max per group; (2) after advantage
      computation, print the advantage tensor's shape, mean, and std;
      (3) inside `compute_loss`, print policy/ref logprob magnitudes,
      mask sum, KL value, and the two loss components separately;
      (4) just before `loss.backward()`, assert
      `loss.requires_grad and loss.grad_fn is not None`. Cross-check
      logged values against the invariants in
      references/grpo-architecture.md. Remove the instrumentation
      before declaring done.

  - name: revert-and-verify
    body: >
      When `git log` shows a single suspect commit and you have low
      confidence in a manual patch, revert just the hunk
      (`git -C /app/trl checkout HEAD~1 -- trl/trainer/grpo_trainer.py`
      if the regression is the whole file, or `git apply -R` a
      targeted patch). Re-run scripts/smoke_train.sh. If reward
      starts moving, the revert is the fix; either keep the revert or
      reapply the commit's non-buggy parts manually.

scenarios:
  - need: After 50 steps, mean reward is flat at the baseline; logged reward_std within group is 0 every step.
    context: >
      `git -C /app/trl log -p -1 -- trl/trainer/grpo_trainer.py` shows
      a recent commit that changed
      `advantages = (rewards - rewards.view(-1, self.num_generations).mean(dim=1, keepdim=True)) / (rewards.view(-1, self.num_generations).std(dim=1, keepdim=True) + 1e-4)`
      to
      `advantages = (rewards - rewards.mean()) / (rewards.std() + 1e-4)`,
      collapsing the per-group baseline into a single batch-wide baseline.
    action: >
      Revert the advantage normalization to the per-group form (mean
      and std reduced over the `num_generations` axis with `keepdim=True`,
      broadcast back to the flat rewards tensor). Reinstall is not
      needed if the install is editable.
    outcome: >
      reward_std becomes non-zero immediately; loss leaves zero; mean
      reward begins trending up by ~step 15.

  - need: Loss reports as 0.0 from step 1, no NaN; reward is computed and varies.
    context: >
      `_get_per_token_logps` returns logprobs aligned to positions
      `1..L` (gathered from `logits[:, :-1]` against `input_ids[:, 1:]`),
      but the completion mask in `compute_loss` is sliced as
      `completion_mask = attention_mask[:, :-1]` — off by one. Every
      position the mask marks "loss applies here" is actually a prompt
      token under the logprob alignment, and the actual completion
      positions are masked to zero.
    action: >
      Slice the mask as `attention_mask[:, 1:]` (or apply the equivalent
      shift) so that mask position `i` aligns with the logprob for
      predicting `input_ids[:, i+1]`. Single-character fix; do not
      rewrite the surrounding logic.
    outcome: >
      Loss becomes small but non-zero; gradient flows; reward begins
      moving within ~20 steps.

  - need: Reward varies across completions, advantages are non-zero, loss is non-zero, but model never improves and weights are unchanged.
    context: >
      A recent refactor wrapped the policy forward pass in
      `with torch.no_grad():` so `per_token_logps_policy.requires_grad
      is False`. The loss still computes a number but has no `grad_fn`,
      so `loss.backward()` is a no-op.
    action: >
      Remove the `torch.no_grad()` around the policy forward. The
      reference forward stays under `no_grad`; the policy forward must
      not be.
    outcome: >
      `loss.grad_fn is not None`; weights move; reward trends upward.

  - need: GRPO loss is NaN by step 2.
    context: >
      One group of completions all earned identical reward; advantage
      computation divides by `std(dim=1)` without `+ eps`, producing
      0/0 → NaN that propagates into the loss.
    action: >
      Restore the `+ 1e-4` (or whatever eps the surrounding code uses)
      to the std denominator. Do not change the eps to a much larger
      value to "stabilize" — that flattens real signal.
    outcome: >
      Loss is finite; training proceeds.

  - need: Edited /app/trl/trl/trainer/grpo_trainer.py multiple times but logs show no behaviour change.
    context: >
      `python -c "import trl; print(trl.__file__)"` resolves to a
      site-packages wheel install, not /app/trl. The training script
      never sees the edits.
    action: >
      `pip install -e /app/trl --force-reinstall --no-deps`, then
      re-verify `import trl` resolves to /app/trl/trl/__init__.py.
      Re-run scripts/smoke_train.sh.
    outcome: >
      Edits are now live; subsequent fixes take effect on the next
      training step.

anti_patterns:
  - Editing /app/train_grpo.py or /app/reward_fn.py. They are off-limits. The bug is inside /app/trl.
  - Rewriting grpo_trainer.py wholesale instead of localizing the regression. Almost every "no improvement" GRPO bug is a single-hunk regression that `git diff` will surface.
  - Increasing learning rate, num_generations, or temperature to "force" learning before finding the bug. Hyperparameter changes mask regressions rather than fixing them.
  - Trusting that `loss > 0` means the gradient is connected. Verify `loss.grad_fn is not None` and that a tracked parameter actually changes between steps.
  - Trusting that `loss == 0` means the run is broken. With proper masking and identical-reward groups, loss can be exactly 0 for a single step. Look across multiple steps.
  - Skipping the `git log` check in /app/trl. Regressions are usually one commit deep and the diff is the fastest path to the bug.
  - Forgetting to reinstall after editing. If `import trl` doesn't resolve to /app/trl, no edit will take effect — confirm before debugging in circles.
  - Replacing `+ eps` with a larger constant to silence NaNs. That hides the bug and flattens the advantage signal.
  - Wrapping the policy forward pass in `torch.no_grad()` "for memory". The policy forward must contribute to the graph; only the reference forward is no_grad.
  - Computing KL across all tokens (including prompt and padding) instead of only completion tokens. Padding KL is spurious and can dominate the loss.
  - Refactoring while fixing. Make the smallest possible change; refactors invite new bugs and obscure the diff.
```
