---
name: trl
description: Reference for the TRL (Transformer Reinforcement Learning) library codebase. Use proactively before reading or editing any file under `trl/` so you have the intended contracts and invariants in mind, not just what the current code says. Covers the trainer hierarchy (SFT, DPO, GRPO, KTO, OnlineDPO), shared utility functions (selective_log_softmax, decode_and_strip_padding, padding helpers), the configuration system, model wrappers, and how data flows through any TRL trainer. Includes a runnable locator that maps each documented symbol to its place in the installed source tree.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Codebase reference for TRL (Transformer Reinforcement Learning), organized
  around a trainer hierarchy that extends transformers.Trainer. It encodes the
  intended contracts and invariants — the trainer layer (SFT, DPO, GRPO, KTO,
  OnlineDPO), the shared utilities in trainer/utils.py (selective_log_softmax,
  decode_and_strip_padding, padding helpers), the configuration system, the
  model wrappers, and how data flows through any trainer — i.e. what callers
  rely on, not just what the current code happens to do. Use it as an
  orientation step before reading or editing any file under trl/: classify what
  you are touching, locate it in the package map, read the contract it must
  honor, then make a change narrow enough to preserve that contract. Beyond
  general agent knowledge it adds the per-symbol contracts (especially the two
  shared utilities multiple trainers depend on) and a runnable locator that maps
  each documented symbol to its file:line in the installed tree.

trigger_when:
  - About to read or edit any file under trl/ and you want the intended contract before the current code.
  - Navigating the trainer hierarchy (SFT, DPO, GRPO, KTO, OnlineDPO) or deciding which trainer owns a behavior.
  - Looking up the contract of a shared utility (selective_log_softmax, decode_and_strip_padding, pad, pad_to_length) before changing it.
  - Understanding the configuration system — which *Config maps to which trainer and what its key fields are.
  - Tracing how data flows through a TRL trainer (compute_loss override, training_step generation phase).
  - Locating where a documented trainer, utility, config, or model wrapper is defined in the installed TRL source.

do_not_use_when:
  - You need the GRPO algorithm math itself (advantage normalization, clipped surrogate, KL penalty, the numerical invariants) rather than where it lives in TRL — use the `grpo` skill.
  - You are running the generic RL-pipeline diagnostic walk (triage table, five-stage stage-by-stage debugging) — use the `rl-post-training` skill.
  - The code under inspection is not part of the TRL library, or is a different RL framework — the file layout and contracts here are TRL-specific.

scope_and_approval: >
  Reading this reference, reading the TRL source, and running
  scripts/locate_trl_symbols.py are read-only. The contracts documented here are
  what callers across multiple trainers rely on, so read the actual source
  before modifying and change narrowly: a bug in one branch of a shared utility
  is not a license to rewrite the whole function — the other branches exist
  because other trainers call them. Editing TRL code is a write action; on a
  shared or production pipeline, propose the change before applying it.

steps:
  - name: identify-target
    description: >
      Classify what you are about to touch before opening any file: a trainer
      (and which one — SFT, DPO, GRPO, KTO, OnlineDPO), a shared utility in
      trainer/utils.py, a *Config dataclass, a model wrapper, or a data helper.
      This decides which contract applies and how widely a change ripples — a
      shared utility is called by several trainers, a single trainer's
      compute_loss is not.
    outputs:
      - name: target
        type: object
        description: The layer (trainer / utility / config / model / data) and the specific symbol involved.

  - name: locate-source
    description: >
      Map the symbol to its file using the package layout (trainers in
      trainer/*_trainer.py, configs in trainer/*_config.py, shared utilities in
      trainer/utils.py, model wrappers in models/, data helpers in
      data_utils.py). Run scripts/locate_trl_symbols.py against the installed
      tree to get the actual file:line for each documented symbol and to surface
      drift between this reference and the installed TRL — pass the trl package
      path if it is not auto-detected.
    depends_on: [identify-target]
    script: scripts/locate_trl_symbols.py
    inputs:
      - name: target
        type: object
      - name: trl_root
        type: string
        nullable: true
        description: Path to the installed trl package; omit to let the locator auto-detect.
    outputs:
      - name: locations
        type: object
        description: file:line for each documented symbol, with `?` flags for anything missing or moved.

  - name: read-intended-contract
    description: >
      Before editing, read the documented contract/invariant for the symbol
      (this body's search_shortcuts, then references/trl-codebase.md for the
      module-by-module detail), THEN read the actual source. The two shared
      utilities carry the load-bearing invariants: selective_log_softmax returns
      per-token log-probs that are always non-positive and must agree with
      F.log_softmax within tolerance; decode_and_strip_padding returns one
      cleaned string per sequence and must handle every completion shape the
      model can emit (it produces exactly the text the reward function scores).
    depends_on: [locate-source]
    inputs:
      - name: locations
        type: object
    outputs:
      - name: contract
        type: object
        description: The invariant(s) the symbol must keep satisfying, and the set of callers that rely on it.

  - name: trace-data-flow
    description: >
      Confirm how data flows through the trainer before changing behavior. Every
      TRL trainer extends transformers.Trainer (inheriting the training loop,
      checkpointing, logging) and overrides compute_loss with its objective;
      RL-based trainers (GRPO, OnlineDPO) additionally override training_step to
      add a generation phase before the optimization step. For GRPO the
      generation path runs through _generate_and_score_completions (sample ->
      decode_and_strip_padding -> reward) and the loss path through compute_loss.
    depends_on: [read-intended-contract]
    inputs:
      - name: target
        type: object

  - name: change-preserving-contract
    description: >
      Make the change as narrow as the contract allows. If the symbol is a
      shared utility, the fix must keep every existing caller's contract intact —
      change only the branch, sign, or constant that violates the invariant; do
      not collapse a multi-branch function to a one-liner or strip surrounding
      numerical-stability logic. Locating the symbol is not the same as
      confirming the fix: after editing a shared utility, re-check the invariant
      itself (the `grpo` and `rl-post-training` skills carry runnable verifiers
      for the log-prob, advantage, and decode invariants).
    depends_on: [trace-data-flow]
    inputs:
      - name: contract
        type: object

search_shortcuts:
  - category: Package layout
    body: >
      trl/trainer/ holds the trainers and their configs — grpo_trainer.py
      (GRPOTrainer), grpo_config.py (GRPOConfig), sft_trainer.py (SFTTrainer),
      dpo_trainer.py (DPOTrainer), kto_trainer.py (KTOTrainer),
      online_dpo_trainer.py (OnlineDPOTrainer), and utils.py (shared log-prob,
      decoding, padding helpers). trl/models/modeling_value_head.py holds the
      value head for PPO-style trainers. trl/data_utils.py holds dataset
      helpers. trl/commands/ holds CLI entry points.
  - category: Trainer hierarchy
    body: >
      All trainers extend transformers.Trainer and override compute_loss with
      their objective; RL trainers (GRPO, OnlineDPO) also override training_step
      to add a generation phase before optimization. SFTTrainer — supervised
      fine-tuning; dataset packing, max_seq_length, dataset_text_field,
      instruction formats via formatting_func. DPOTrainer — direct preference
      optimization from (chosen, rejected) pairs, no RL; beta sets KL strength;
      loss_type in {sigmoid (default), hinge, ipo, kto_pair}; can run
      reference-free. GRPOTrainer — group relative policy optimization; overrides
      training_step; _generate_and_score_completions does sampling + reward
      scoring; compute_loss is clipped surrogate + KL (see the `grpo` skill for
      the algorithm). KTOTrainer — Kahneman-Tversky optimization from unpaired
      good/bad labels; desirable_weight / undesirable_weight set loss asymmetry;
      KL term from a reference model. OnlineDPOTrainer — DPO with on-policy
      generation; GRPO-like generation loop, pairs completions by reward ranking.
  - category: Shared utilities (trainer/utils.py)
    body: >
      selective_log_softmax(logits [B,T,V], index [B,T]) -> log_probs [B,T]:
      memory-efficient per-token log-probability; every entry is a valid
      log-prob (NON-POSITIVE) and must agree with
      F.log_softmax(logits,-1).gather(-1, index.unsqueeze(-1)).squeeze(-1) within
      numerical tolerance. Used by GRPO, DPO, OnlineDPO.
      decode_and_strip_padding(input_ids [B,T], tokenizer) -> list[str] of length
      B: converts token-id tensors to the cleaned text the reward function
      scores; strips padding and decoder artefacts and handles whatever
      reasoning-block conventions the library supports (the policy for complete,
      incomplete, and absent markers is defined in the implementation — enumerate
      the shapes the model can emit and confirm each survives). Used by GRPO,
      OnlineDPO. pad(tensors, padding_value, padding_side) and
      pad_to_length(tensor, length, padding_value) handle variable-length and
      exact-length padding, alongside various tokenizer helpers for batch
      processing. Read the source before modifying — the contracts are what
      callers rely on.
  - category: Configuration system
    body: >
      Every *Config extends transformers.TrainingArguments (learning rate, batch
      size, gradient accumulation, etc.) and adds trainer-specific fields.
      SFTConfig (SFTTrainer): max_seq_length, packing, dataset_text_field.
      DPOConfig (DPOTrainer): beta (~0.1), loss_type ("sigmoid"), reference_free
      (False), label_smoothing (0.0). GRPOConfig (GRPOTrainer): num_generations
      (4-16, completions per prompt for advantage estimation),
      max_completion_length (256-1024), beta (0.01-0.1 KL penalty), epsilon
      (0.1-0.2 clip range), temperature (0.7-1.0), reward_functions (list of
      callables). KTOConfig (KTOTrainer): beta, desirable_weight,
      undesirable_weight.
  - category: Models layer
    body: >
      AutoModelForCausalLMWithValueHead (models/modeling_value_head.py) wraps a
      causal LM with a scalar value head for PPO-style trainers that need a
      critic — NOT used by GRPO, DPO, or SFT. PreTrainedModelWrapper is the base
      class for wrappers that modify forward-pass behavior while preserving the
      underlying model's API.
  - category: Data utilities (data_utils.py)
    body: >
      maybe_extract_prompt extracts the prompt from conversation-format
      datasets; apply_chat_template applies the tokenizer chat template to
      conversation data; plus dataset-formatting helpers for various training
      paradigms.
  - category: References and locator
    body: >
      references/trl-codebase.md — module-by-module guide to the TRL source:
      detailed breakdown of each trainer (including the non-GRPO ones), the
      models layer, data utilities, and the GRPOConfig / DPOConfig specifics
      tables; load when navigating unfamiliar parts of TRL beyond the trainer
      layer or when you need detail on a specific non-GRPO trainer.
      scripts/locate_trl_symbols.py — maps every documented symbol to its
      file:line in the installed tree, reprints the two shared-utility contracts,
      and flags drift with `?`; run it (optionally with the trl path) to orient
      before editing.

scenarios:
  - need: A GRPO reward function is scoring empty strings; you suspect the decoder but do not know where it lives.
    context: >
      identify-target -> shared utility (decoding). locate-source /
      scripts/locate_trl_symbols.py points to decode_and_strip_padding in
      trainer/utils.py, flagged as used by GRPO and OnlineDPO.
    action: >
      Read its contract (one cleaned string per sequence; every completion shape
      must survive) and then the source. Fix only the branch that blanks a shape
      the reward must score; leave the other branches intact because OnlineDPO
      calls the same function.
    outcome: The reward function sees the answer text again, and the OnlineDPO caller is unaffected.
  - need: Per-token log-probs look wrong inside a DPO run.
    context: >
      locate-source shows selective_log_softmax in trainer/utils.py, shared by
      DPO, GRPO, and OnlineDPO; its contract is non-positive output that matches
      F.log_softmax within tolerance.
    action: >
      Verify the implementation against F.log_softmax on a small deterministic
      input. If a sign is flipped, correct only that subtraction; do not rewrite
      the gather/logsumexp structure that the other two trainers depend on.
    outcome: Log-probs are non-positive and consistent across all three trainers that call the utility.
  - need: You need to add a hyperparameter to GRPO's configuration.
    context: >
      identify-target -> config. The package layout puts GRPOConfig in
      trainer/grpo_config.py, extending transformers.TrainingArguments.
    action: >
      Add the field in grpo_config.py alongside num_generations / beta / epsilon;
      do not redefine inherited TrainingArguments fields.
    outcome: The new field lives with the other GRPO-specific config fields and inherits the base training arguments cleanly.

anti_patterns:
  - Editing TRL code from what the current implementation does rather than the intended contract — the skill exists precisely to supply the contract the code may have drifted from.
  - Rewriting a shared utility (selective_log_softmax, decode_and_strip_padding, pad) to satisfy one trainer when GRPO / DPO / OnlineDPO all call it.
  - Collapsing a multi-branch shared function to a one-liner, or stripping its numerical-stability logic, instead of correcting the single offending branch or constant.
  - Assuming a behavior lives in a specific trainer when it actually lives in trainer/utils.py (or vice versa) — confirm with the package layout / locator before editing.
  - Looking for a value head in GRPO, DPO, or SFT — the value head is PPO-style only and lives in models/modeling_value_head.py.
  - Redefining inherited transformers.TrainingArguments fields on a *Config instead of adding only the trainer-specific ones.
  - Treating this skill as the GRPO algorithm spec — the per-stage math and invariants live in the `grpo` skill, the diagnostic walk in `rl-post-training`.
```
