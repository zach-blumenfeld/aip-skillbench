#!/usr/bin/env python3
"""Lint a Suricata HTTP DPI rule for the common failure modes covered in
this skill. Reads a rule from a file path (argv[1]) or stdin. Emits a
single JSON object on stdout with `errors` and `warnings` arrays. Exits
0 on clean, 1 if any errors are reported (warnings alone do not fail).

Findings are heuristic — pass on a clean lint is necessary but not
sufficient. The agent must still verify the rule actually meets the
task's stated constraints.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

STICKY_BUFFERS = {
    "http.method",
    "http.uri",
    "http.header",
    "http.host",
    "http.user_agent",
    "http.cookie",
    "http.request_line",
    "http.request_body",
    "http_client_body",
    "http.response_body",
    "http_server_body",
    "http.stat_code",
    "http.stat_msg",
    "file.data",
}


def split_options(body: str) -> list[str]:
    """Split a Suricata rule option block on top-level semicolons.
    Respects double-quoted strings so semicolons inside content:"..." are
    not treated as separators."""
    out: list[str] = []
    buf: list[str] = []
    in_str = False
    esc = False
    for ch in body:
        if esc:
            buf.append(ch)
            esc = False
            continue
        if ch == "\\" and in_str:
            buf.append(ch)
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            buf.append(ch)
            continue
        if ch == ";" and not in_str:
            tok = "".join(buf).strip()
            if tok:
                out.append(tok)
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def parse_rule(text: str) -> tuple[str, list[str]] | None:
    """Return (header, options) or None if the rule cannot be parsed."""
    stripped = re.sub(r"#[^\n]*", "", text)
    m = re.search(r"^\s*(alert|drop|pass|reject)\b[^(]*\(", stripped, re.MULTILINE)
    if not m:
        return None
    paren_start = stripped.index("(", m.end() - 1)
    depth = 0
    end = -1
    for i in range(paren_start, len(stripped)):
        c = stripped[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    header = stripped[m.start():paren_start].strip()
    body = stripped[paren_start + 1:end]
    return header, split_options(body)


def content_value(opt: str) -> str | None:
    m = re.match(r'content\s*:\s*"((?:\\.|[^"\\])*)"', opt)
    return m.group(1) if m else None


def pcre_value(opt: str) -> str | None:
    m = re.match(r'pcre\s*:\s*"((?:\\.|[^"\\])*)"', opt)
    return m.group(1) if m else None


def is_sticky(opt: str) -> str | None:
    head = opt.split(":", 1)[0].strip()
    return head if head in STICKY_BUFFERS else None


def looks_like_method(val: str) -> bool:
    return val.strip().upper() in HTTP_METHODS


def looks_like_path(val: str) -> bool:
    return val.startswith("/") and " " not in val


def lint(text: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    parsed = parse_rule(text)
    if not parsed:
        return {"errors": ["could not parse rule: no `action proto ... ( ... )` block found"], "warnings": []}

    header, opts = parsed

    has_sid = any(o.startswith("sid:") or o.startswith("sid ") for o in opts)
    has_rev = any(o.startswith("rev:") or o.startswith("rev ") for o in opts)
    has_msg = any(o.startswith("msg:") or o.startswith("msg ") for o in opts)
    has_flow = any(o.startswith("flow:") or o.startswith("flow ") for o in opts)
    if not has_sid:
        errors.append("missing required `sid:` option")
    if not has_rev:
        errors.append("missing required `rev:` option")
    if not has_msg:
        warnings.append("missing `msg:` — without it, alerts are hard to triage")
    if not has_flow:
        warnings.append("missing `flow:` — consider `flow:established,to_server` to constrain direction/state")

    if "alert http " not in header and " http " not in (" " + header + " "):
        warnings.append(f"rule header does not declare `http` protocol: {header!r} — HTTP sticky buffers require `alert http ...`")

    current_buffer: str | None = None
    saw_method_buffer = False
    saw_uri_buffer = False
    saw_body_buffer = False
    saw_sig_content = False
    saw_blob_content = False
    saw_sig_64_hex_pcre = False
    saw_blob_length_pcre = False

    for opt in opts:
        sticky = is_sticky(opt)
        if sticky:
            current_buffer = sticky
            if sticky == "http.method":
                saw_method_buffer = True
            elif sticky == "http.uri":
                saw_uri_buffer = True
            elif sticky in ("http_client_body", "http.request_body"):
                saw_body_buffer = True
            continue

        cval = content_value(opt)
        if cval is not None:
            if looks_like_method(cval) and current_buffer != "http.method":
                errors.append(
                    f"content:\"{cval}\" looks like an HTTP method but is not anchored to `http.method;` "
                    f"(current buffer: {current_buffer or 'none / payload'}). Add `http.method;` before this content."
                )
            if looks_like_path(cval) and current_buffer != "http.uri":
                warnings.append(
                    f"content:\"{cval}\" looks like a URI path but is not anchored to `http.uri;` "
                    f"(current buffer: {current_buffer or 'none / payload'}). Add `http.uri;` before this content."
                )
            if cval.startswith("blob="):
                saw_blob_content = True
                if current_buffer not in ("http_client_body", "http.request_body"):
                    errors.append(
                        f"content:\"{cval}\" targets a request body param but is not anchored to `http_client_body;` "
                        f"(current buffer: {current_buffer or 'none / payload'})."
                    )
            if cval.startswith("sig="):
                saw_sig_content = True
                if current_buffer not in ("http_client_body", "http.request_body"):
                    errors.append(
                        f"content:\"{cval}\" targets a request body param but is not anchored to `http_client_body;` "
                        f"(current buffer: {current_buffer or 'none / payload'})."
                    )
            continue

        pval = pcre_value(opt)
        if pval is not None:
            inner = pval
            if inner.startswith("/"):
                inner = inner[1:]
            tail = re.search(r"/[a-zA-Z]*$", inner)
            if tail:
                inner = inner[: tail.start()]
            if re.search(r"sig\s*=\s*\[0-9a-fA-F\]\{64\}", inner) or re.search(r"sig\s*=\s*\[A-Fa-f0-9\]\{64\}", inner):
                saw_sig_64_hex_pcre = True
            if re.search(r"blob\s*=\s*\[[^\]]+\]\{\s*\d+\s*,", inner):
                saw_blob_length_pcre = True
            if re.search(r"(?<!\\)\.\*", inner) or re.search(r"(?<!\\)\.\+", inner):
                warnings.append(
                    f"pcre:\"{pval}\" contains `.*` or `.+` — likely too permissive and prone to false positives"
                )
            continue

    if saw_blob_content and not saw_blob_length_pcre:
        errors.append(
            "saw `blob=` content but no PCRE enforces a minimum length on the value "
            "(expected something like `blob=[A-Za-z0-9+/]{80,}`)"
        )
    if saw_sig_content and not saw_sig_64_hex_pcre:
        errors.append(
            "saw `sig=` content but no PCRE enforces exactly 64 hex characters "
            "(expected `sig=[0-9a-fA-F]{64}`)"
        )

    if (saw_blob_content or saw_sig_content) and not saw_body_buffer:
        errors.append(
            "rule references body params (`blob=` / `sig=`) but never enters the `http_client_body;` sticky buffer"
        )

    # Useful but not required:
    if saw_method_buffer and saw_uri_buffer and saw_body_buffer:
        pass
    else:
        missing = []
        if not saw_method_buffer:
            missing.append("http.method")
        if not saw_uri_buffer:
            missing.append("http.uri")
        if not saw_body_buffer:
            missing.append("http_client_body")
        warnings.append(
            "rule does not exercise all of (http.method, http.uri, http_client_body); "
            f"missing: {', '.join(missing)}. Multi-condition DPI usually wants all three."
        )

    return {"errors": errors, "warnings": warnings}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        text = Path(sys.argv[1]).read_text()
    else:
        text = sys.stdin.read()
    result = lint(text)
    print(json.dumps(result, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
