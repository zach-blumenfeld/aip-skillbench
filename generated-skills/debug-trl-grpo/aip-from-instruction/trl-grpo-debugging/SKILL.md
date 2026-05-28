---
name: trl-grpo-debugging
description: >
  Diagnose and fix a bug in the TRL (Transformer Reinforcement Learning) GRPO trainer
  that makes a training run show no improvement — a flat reward curve — on tasks such as
  countdown math. Encodes the correct GRPO algorithm (group-relative advantage, per-token
  log-prob alignment, clipped surrogate loss, completion masking, KL penalty), a catalog of
  no-improvement failure modes (detached gradients, zero or scrambled advantages, repeat vs
  repeat_interleave group broadcast, inverted/misaligned completion masks, log-prob token
  shift, KL domination, clip collapse), a triage script that surfaces version-control diffs
  and the key computation sites, and a runtime invariant checker. Use when a GRPO/TRL
  fine-tune will not learn, reward stays flat, GRPOTrainer is suspected, or the fix must stay
  inside the trl library source without touching the training script or reward function.
compatibility: >
  Requires a TRL GRPO training environment (Python, PyTorch, an editable/vendored `trl`
  source tree, plus the training script and reward function). git strongly recommended — a
  diff localizes a planted bug fastest.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Find and fix a bug inside a TRL GRPO trainer that causes a reinforcement-learning
  fine-tune to show no improvement (flat reward curve), when the training script and reward
  function are correct and off-limits. The bug is a small deviation from the correct GRPO
  computation in the trl library source. This skill carries the correct GRPO algorithm, the
  catalog of no-improvement failure modes, and a static-plus-runtime diagnostic loop so a
  downstream agent can localize and repair the deviation with a minimal edit, then prove the
  model now learns.

trigger_when:
  - A GRPO / TRL training run reports no improvement and the reward curve is flat across steps.
  - The user says a model "shows no improvement" after GRPO post-training and points at the trl source.
  - GRPOTrainer / grpo_trainer.py is the suspected location of a bug.
  - You must fix a training defect but are forbidden from editing the training script or reward function.
  - Debugging group-relative advantage, log-prob, clipped-surrogate-loss, or completion-mask code in trl.

do_not_use_when:
  - The training run crashes or raises an exception — debug the traceback first; this skill targets a *silent* flat-reward failure.
  - The suspected cause is in the training script or reward function AND you are permitted to edit them — use general debugging instead.
  - You are tuning an already-learning run for better performance (this is bug-finding, not hyperparameter optimization).

scope_and_approval: >
  Reading the trl source, adding temporary instrumentation to it, and running short training
  jobs are all safe to do autonomously. The fix is a WRITE to the trl library source only —
  never edit the training script (e.g. train_grpo.py) or the reward function (e.g.
  reward_fn.py); they are correct by assumption and explicitly out of scope. Keep the fix
  minimal: a planted bug is a small deviation, not a rewrite. Remove all temporary
  instrumentation before declaring the task complete.

steps:
  - name: confirm-symptom-and-scope
    description: >
      Confirm the failure is silent no-improvement (flat reward), not a crash or a
      degrading/diverging curve. Read any existing training logs or reward history to record a
      baseline. Lock scope: only the trl library source may be edited; the training script and
      reward function are off-limits.
    outputs:
      - name: symptom-profile
        type: object
        description: "{trend: flat|decreasing|slow, baseline_reward, notes}; trend steers triage order."

  - name: study-correct-grpo
    description: >
      Read references/grpo-algorithm.md to internalize the correct forms and invariants for
      each GRPO computation site (advantage, log-prob/shift, ratio, clipped loss sign, mask,
      KL). Read references/grpo-bug-catalog.md for the no-improvement failure modes (A–H).
    depends_on: [confirm-symptom-and-scope]
    outputs:
      - name: reference-model
        type: object
        description: Correct-form expectations + invariants + the bug-category map A–H.

  - name: locate-trl-and-changes
    description: >
      Surface the fastest lead: run the triage script to detect whether the trl tree is
      version-controlled (a non-empty git diff is almost always the plant), locate the GRPO
      trainer and helper files, and grep the key computation sites.
    script: scripts/locate_trl_changes.py
    depends_on: [confirm-symptom-and-scope]
    outputs:
      - name: triage-report
        type: object
        description: git diff/status/log intel plus matched computation-site line numbers.
      - name: candidate-sites
        type: list[object]
        description: Files + lines for advantage, ratio, loss, mask, logp-shift, KL.

  - name: compare-static
    description: >
      Diff each candidate site against the correct form. If git diff was non-empty, read it
      first — that is the plant. Produce ranked hypotheses tagged by bug category (A–H), each
      with file + line and the expected correct form.
    depends_on: [locate-trl-and-changes, study-correct-grpo]
    inputs:
      - name: candidate-sites
        type: list[object]
      - name: reference-model
        type: object
      - name: triage-report
        type: object
    outputs:
      - name: hypotheses
        type: list[object]
        description: Ranked {bug_category, file, line, correct_form, confidence}.

  - name: instrument-and-capture
    description: >
      Add TEMPORARY instrumentation inside the trl trainer (never the training script or
      reward function) to dump per-step summary stats to a metrics JSON, then run a few steps.
      Capture the fields the invariant checker reads — see the header of
      scripts/grpo_invariants.py for the exact schema (grad_norm and requires_grad flags,
      advantages_abs_mean, within_group_adv_sum_absmax, completion_mask_sum, coef1_mean /
      clip_fraction, kl/policy term magnitudes, reward_mean / reward_std). Prioritize the
      fields tied to the leading hypotheses, but capturing all is cheap and disambiguates.
    depends_on: [study-correct-grpo, locate-trl-and-changes]
    outputs:
      - name: metrics-json
        type: string
        description: Path to the captured per-step metrics JSON.

  - name: diagnose
    description: >
      Run the invariant checker on the captured metrics to confirm which invariant is
      violated and its bug category, then reconcile with the static hypotheses to pin a single
      root cause. Prefer a runtime metric to confirm the diagnosis rather than concluding from
      a code read alone. If checks all pass but reward is still flat, widen instrumentation and
      re-capture. Static-only fallback (when the trainer genuinely cannot be run — e.g. no
      GPU/torch): a version-control diff that exactly matches a known buggy→correct form in
      references/grpo-bug-catalog.md is sufficient on its own; say so explicitly.
    script: scripts/grpo_invariants.py
    depends_on: [instrument-and-capture, compare-static]
    inputs:
      - name: metrics-json
        type: string
      - name: hypotheses
        type: list[object]
    outputs:
      - name: root-cause
        type: object
        description: "{file, line, bug_category, correct_form} — the confirmed single defect."

  - name: fix
    description: >
      Apply the minimal correction at the confirmed site in the trl source only, matching the
      correct form from references/grpo-algorithm.md. Do not refactor or touch surrounding
      code, and do not edit the training script or reward function.
    depends_on: [diagnose]
    inputs:
      - name: root-cause
        type: object
    outputs:
      - name: patch
        type: object
        description: "{file, edit} — the single applied change."

  - name: verify
    description: >
      Re-run training long enough to see the reward curve move, capturing metrics again. Run
      the invariant checker in verify mode to confirm no invariant is violated AND the reward
      is improving versus the baseline. If it still fails, loop back to compare-static /
      diagnose. Once it passes, remove all temporary instrumentation.
    script: scripts/grpo_invariants.py
    depends_on: [fix]
    inputs:
      - name: patch
        type: object
      - name: symptom-profile
        type: object
    outputs:
      - name: verification
        type: object
        description: "{invariants_pass, reward_improving, baseline_vs_now} — the exit gate."

modes:
  - name: diagnose
    body: >
      Default run of scripts/grpo_invariants.py on a buggy-run metrics JSON. Flags the violated
      invariant and its bug category (A–H); exits 1 on any failure.
  - name: verify
    body: >
      scripts/grpo_invariants.py --verify on a post-fix metrics JSON. Adds the reward-improving
      gate (last-third mean must beat first-third by the configured margin) on top of the
      invariant checks. Use only after applying the fix.

scenarios:
  - need: Flat reward from step 0 on a countdown-math GRPO run; trl tree is a git repo.
    context: >
      locate-trl-and-changes shows a non-empty git diff adding `.detach()` to per_token_logps
      in _get_per_token_logps. Instrumentation reports grad_norm == 0 and loss_requires_grad
      == False; grpo_invariants flags gradient-flows -> category A.
    action: Remove the detach so the policy forward keeps its gradient; leave the reference pass detached.
    outcome: Reward climbs over steps; verify mode passes the reward-improving gate.

  - need: Reward never trends up; no version control on the trl tree.
    context: >
      Static compare of the advantage broadcast shows `.repeat(num_generations)` where
      `.repeat_interleave(num_generations)` is required. Instrumentation reports a large
      within_group_adv_sum_absmax; grpo_invariants flags group-centered -> category C.
    action: Replace repeat with repeat_interleave so each group's baseline maps to its own completions.
    outcome: Within-group advantages re-center to ~0; reward begins improving.

  - need: Reward flat although gradients flow and advantages look reasonable.
    context: >
      completion_mask_sum is ~0 (or the mask is inverted), so the loss trains on prompt/padding
      tokens. grpo_invariants flags mask-nonempty -> category D.
    action: Fix the mask construction/alignment so it selects real completion tokens, aligned with the logp shift.
    outcome: Loss now covers completion tokens; the model learns the task.

anti_patterns:
  - Editing the training script or reward function to mask the symptom — they are correct and out of scope; the bug is in the trl library.
  - Concluding a root cause from a code read alone without confirming it with a runtime metric.
  - Treating a single all-equal-reward group's zero advantage as the bug — that is expected; only zero advantage across many varied-reward steps is a defect.
  - Rewriting large sections of the trainer — a planted bug is a small deviation, so make the minimal edit.
  - Assuming method or variable names — grep the actual source; names vary across TRL versions.
  - Tuning hyperparameters (learning rate, beta, num_generations) instead of fixing the planted code defect.
  - Leaving temporary instrumentation in the trl source after verification.
```
