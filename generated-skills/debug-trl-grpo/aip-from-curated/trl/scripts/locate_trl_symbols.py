"""Locate the documented TRL symbols in the installed source tree.

Run with:
    python locate_trl_symbols.py [path/to/trl]

This script does NOT judge correctness. It is a navigation aid: it confirms the
package map in SKILL.md against the *actual* installed TRL source, so you edit
from where a symbol really lives (and against the contract it is supposed to
honor) rather than from what you assume. For each documented trainer, config,
shared utility, model wrapper, and data helper it prints `path:line` for every
definition it finds, and reprints the intended contract for the two shared
utilities whose invariants callers across trainers rely on.

Symbols the doc expects but that are missing from the tree are flagged with a
`?` so you notice drift between the reference and the installed code without the
run short-circuiting. The script exits non-zero only on an unambiguous failure:
the TRL package root cannot be located. A missing individual symbol is a `?`,
not an error — TRL versions move things around.

No third-party dependencies (pure stdlib); it never imports torch or runs TRL.
"""

from __future__ import annotations

import os
import re
import sys

# ---------------------------------------------------------------------------
# Documented symbols, grouped by layer. (name, kind, expected_relpath, note)
#   kind: "class" | "def"  -> matched as `class NAME` / `def NAME`
#   expected_relpath: where SKILL.md says it lives, relative to the trl package
#                     root; None for methods that live inside a trainer file.
#   note: intended-contract reminder reprinted next to the location (or "").
# ---------------------------------------------------------------------------

GROUPS = [
    ("Trainers (extend transformers.Trainer; override compute_loss)", [
        ("SFTTrainer", "class", "trainer/sft_trainer.py", ""),
        ("DPOTrainer", "class", "trainer/dpo_trainer.py", ""),
        ("GRPOTrainer", "class", "trainer/grpo_trainer.py",
         "RL trainer: also overrides training_step to add a generation phase."),
        ("KTOTrainer", "class", "trainer/kto_trainer.py", ""),
        ("OnlineDPOTrainer", "class", "trainer/online_dpo_trainer.py",
         "RL trainer: also overrides training_step to add a generation phase."),
    ]),
    ("Trainer methods (the override surface; RL adds the last two)", [
        ("compute_loss", "def", None,
         "Each trainer overrides this with its objective."),
        ("training_step", "def", None,
         "RL trainers (GRPO, OnlineDPO) override this to generate before optimizing."),
        ("_generate_and_score_completions", "def", None,
         "GRPOTrainer: sampling + reward scoring."),
    ]),
    ("Shared utilities (trainer/utils.py) — contracts callers rely on", [
        ("selective_log_softmax", "def", "trainer/utils.py",
         "Input logits[B,T,V], index[B,T] -> log_probs[B,T]. Every entry is a "
         "valid log-prob (NON-POSITIVE) and must agree with "
         "F.log_softmax(logits,-1).gather(-1, index.unsqueeze(-1)).squeeze(-1) "
         "within numerical tolerance. Used by GRPO/DPO/OnlineDPO."),
        ("decode_and_strip_padding", "def", "trainer/utils.py",
         "Input input_ids[B,T], tokenizer -> list[str] of length B. Strips "
         "padding and decoder artefacts; handles the library's reasoning-block "
         "conventions (complete / incomplete / absent markers — policy lives in "
         "the implementation). Used by GRPO/OnlineDPO; this text is what the "
         "reward function scores."),
        ("pad", "def", "trainer/utils.py",
         "pad(tensors, padding_value, padding_side) -> uniform length."),
        ("pad_to_length", "def", "trainer/utils.py",
         "pad_to_length(tensor, length, padding_value) -> pad/truncate to exact."),
    ]),
    ("Configs (extend transformers.TrainingArguments)", [
        ("SFTConfig", "class", "trainer/sft_config.py", ""),
        ("DPOConfig", "class", "trainer/dpo_config.py", ""),
        ("GRPOConfig", "class", "trainer/grpo_config.py", ""),
        ("KTOConfig", "class", "trainer/kto_config.py", ""),
    ]),
    ("Models layer", [
        ("AutoModelForCausalLMWithValueHead", "class", "models/modeling_value_head.py",
         "PPO-style critic head. NOT used by GRPO, DPO, or SFT."),
        ("PreTrainedModelWrapper", "class", None,
         "Base wrapper preserving the underlying model API."),
    ]),
    ("Data utilities (data_utils.py)", [
        ("maybe_extract_prompt", "def", "data_utils.py", ""),
        ("apply_chat_template", "def", "data_utils.py", ""),
    ]),
]


def find_trl_root(argv: list[str]) -> str | None:
    """Return the path to the `trl` package dir (the one containing trainer/)."""

    def looks_like_root(p: str) -> bool:
        return os.path.isfile(os.path.join(p, "trainer", "utils.py"))

    # 1. explicit path argument
    if len(argv) > 1:
        p = os.path.abspath(argv[1])
        if looks_like_root(p):
            return p
        # caller may have pointed at the parent that contains trl/
        child = os.path.join(p, "trl")
        if looks_like_root(child):
            return child
        print(f"  ? argv path '{argv[1]}' is not a TRL package root", file=sys.stderr)

    # 2. installed package
    try:
        import trl  # type: ignore
        p = os.path.dirname(os.path.abspath(trl.__file__))
        if looks_like_root(p):
            return p
    except Exception:
        pass

    # 3. search outward from cwd for a `trl` package dir
    start = os.getcwd()
    for base, dirs, _ in os.walk(start):
        # skip noise
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules", ".venv")]
        if os.path.basename(base) == "trl" and looks_like_root(base):
            return base
    return None


def iter_py_files(root: str):
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(base, f)


def index_definitions(root: str) -> dict[str, list[str]]:
    """Map 'kind name' -> ['relpath:line', ...] for every def/class in the tree."""
    index: dict[str, list[str]] = {}
    pat = re.compile(r"^\s*(?:async\s+)?(def|class)\s+([A-Za-z_]\w*)")
    for path in iter_py_files(root):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    m = pat.match(line)
                    if m:
                        key = f"{m.group(1)} {m.group(2)}"
                        rel = os.path.relpath(path, root)
                        index.setdefault(key, []).append(f"{rel}:{lineno}")
        except OSError:
            continue
    return index


def main(argv: list[str]) -> int:
    root = find_trl_root(argv)
    if root is None:
        print(
            "ERROR: could not locate the TRL package root. Pass it explicitly:\n"
            "    python locate_trl_symbols.py /path/to/trl",
            file=sys.stderr,
        )
        return 1

    print(f"TRL package root: {root}\n")
    index = index_definitions(root)
    missing = 0

    for group_name, symbols in GROUPS:
        print(f"## {group_name}")
        for name, kind, expected, note in symbols:
            locations = index.get(f"{kind} {name}", [])
            if locations:
                shown = ", ".join(locations[:8])
                more = "" if len(locations) <= 8 else f"  (+{len(locations) - 8} more)"
                print(f"  {kind} {name}: {shown}{more}")
                if expected and not any(loc.startswith(expected + ":") for loc in locations):
                    print(f"      ? expected in {expected}; found elsewhere (doc/source drift?)")
            else:
                missing += 1
                where = f" (expected {expected})" if expected else ""
                print(f"  ? {kind} {name}: NOT FOUND{where}")
            if note:
                print(f"      contract: {note}")
        print()

    if missing:
        print(f"{missing} documented symbol(s) not found — inspect the `?` lines "
              "above for drift between the reference and the installed TRL.")
    else:
        print("All documented symbols located.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
