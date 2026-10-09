"""Where the solver's model calls go: Anthropic (default) or an open-weight model
served through Hugging Face Inference Providers.

Claude Code inside the container honours ANTHROPIC_BASE_URL, and Hugging Face's
router speaks the Anthropic Messages protocol, so `hf` only changes the solver's
environment. The token never rides a command line: `eval` hands the secret part to
the `bench` subprocess as JSON in SECRET_AGENT_ENV, and `_benchflow_patch` merges it
into the agent env as explicit keys (so it beats anything inherited from `.env`).
"""

from __future__ import annotations

from enum import Enum

HF_ROUTER_URL = "https://router.huggingface.co"
HF_TOKEN_ENV = "HF_TOKEN"
HF_REQUEST_TIMEOUT_MS = 120_000
HF_MAX_OUTPUT_TOKENS = 32_000

# JSON object of agent env entries too secret for argv; read in the `bench` subprocess.
SECRET_AGENT_ENV = "AIP_SKILLBENCH_SECRET_AGENT_ENV"

# Same filter as benchflow's config.json writer, plus nothing else.
_SECRET_SUBSTRINGS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIALS")
REDACTED = "<redacted>"


class Provider(str, Enum):
    anthropic = "anthropic"
    hf = "hf"


def is_secret_key(key: str) -> bool:
    k = key.upper()
    if k.endswith("_TOKENS"):  # a count, e.g. MAX_THINKING_TOKENS, not a credential
        return False
    return any(s in k for s in _SECRET_SUBSTRINGS)


def redact_kv(kv: str) -> str:
    """`KEY=value` -> `KEY=<redacted>` when KEY names a secret; anything else unchanged."""
    k, sep, _ = kv.partition("=")
    return f"{k}={REDACTED}" if sep and is_secret_key(k) else kv


def redact_argv(args: list[str]) -> list[str]:
    """Redact every secret `KEY=value` argument (e.g. after `--agent-env`)."""
    return [redact_kv(a) for a in args]


def hf_agent_env(model: str, token: str) -> tuple[list[str], dict[str, str]]:
    """(public KEY=VALUE entries for --agent-env, secret entries for SECRET_AGENT_ENV).

    `model` carries the provider pin, e.g. `Qwen/Qwen3.5-9B:featherless-ai`. Every Claude
    tier name maps to it so Claude Code's side calls never ask the router for Claude.
    ANTHROPIC_API_KEY is overridden so the real Anthropic key is never sent to the router.
    """
    public = [
        f"BENCHFLOW_PROVIDER_BASE_URL={HF_ROUTER_URL}",
        f"ANTHROPIC_DEFAULT_HAIKU_MODEL={model}",
        f"ANTHROPIC_DEFAULT_SONNET_MODEL={model}",
        f"ANTHROPIC_DEFAULT_OPUS_MODEL={model}",
        f"CLAUDE_CODE_SUBAGENT_MODEL={model}",
        # Claude Code's default request timeout is 600 s, the same as benchflow's idle
        # watchdog, so one hung request ended a trial before Claude Code retried it. A
        # normal turn on featherless-ai takes 4 to 13 s.
        f"API_TIMEOUT_MS={HF_REQUEST_TIMEOUT_MS}",
        # Claude Code asks for 64k output tokens; featherless-ai rejects anything above
        # about 32k and the router turns that into an empty 200, which ends the turn.
        f"CLAUDE_CODE_MAX_OUTPUT_TOKENS={HF_MAX_OUTPUT_TOKENS}",
    ]
    secret = {
        "BENCHFLOW_PROVIDER_API_KEY": token,
        "ANTHROPIC_AUTH_TOKEN": token,
        "ANTHROPIC_API_KEY": token,
    }
    return public, secret


def safe_path_part(s: str) -> str:
    """A model string as one path component: `/` and `:` become `_`."""
    return s.replace("/", "_").replace(":", "_")
