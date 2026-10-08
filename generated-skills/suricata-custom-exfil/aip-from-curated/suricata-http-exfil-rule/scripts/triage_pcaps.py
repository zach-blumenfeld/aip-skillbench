"""Step `triage-pcaps`: inventory tools and dump every HTTP request in the given pcaps.

stdin: {"currentState": {...pcap_paths, rules_path, suricata_config...}, "assets": {}, "expects": [...]}
stdout: {"pcap_summaries": [...], "tools": {...}, "existing_rules": str}
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcaplib  # noqa: E402

BODY_PREVIEW = 4000


def tool_info():
    info = {}
    for name in ("suricata", "tshark", "jq"):
        path = shutil.which(name)
        ver = None
        if path:
            try:
                flag = "-V" if name == "suricata" else "--version"
                r = subprocess.run([path, flag], capture_output=True, text=True, timeout=20)
                ver = (r.stdout or r.stderr).strip().splitlines()[0][:120]
            except Exception as e:  # noqa: BLE001
                ver = "version check failed: %s" % e
        info[name] = {"path": path, "version": ver}
    return info


def main():
    req = json.load(sys.stdin)
    st = req.get("currentState", {})
    paths = pcaplib.expand_pcap_paths(st.get("pcap_paths") or [])
    errors = []
    summaries = []
    for p in paths:
        if not os.path.isfile(p):
            errors.append("pcap not found: %s" % p)
            continue
        try:
            streams = pcaplib.client_streams(p)
        except Exception as e:  # noqa: BLE001
            errors.append("cannot parse %s: %s" % (p, e))
            continue
        reqs = []
        for s in streams:
            for r in pcaplib.parse_requests(s["data"]):
                params = pcaplib.body_params(r["body"])
                reqs.append({
                    "flow": "%s:%s -> %s:%s" % (s["src"], s["sport"], s["dst"], s["dport"]),
                    "method": r["method"],
                    "uri": r["uri"],
                    "version": r["version"],
                    "headers": r["headers"],
                    "body": r["body"][:BODY_PREVIEW],
                    "body_len": len(r["body"]),
                    "body_params": [
                        {"name": n, "len": (len(v) if v is not None else None),
                         "charset": (_charset(v) if v is not None else None)}
                        for n, v in params
                    ],
                })
        summaries.append({"pcap": p, "tcp_client_streams": len(streams), "http_requests": reqs})
    rules_path = st.get("rules_path") or "/root/local.rules"
    existing = None
    if os.path.isfile(rules_path):
        with open(rules_path, encoding="utf-8", errors="replace") as fh:
            existing = fh.read()
    cfg = st.get("suricata_config") or "/root/suricata.yaml"
    out = {
        "pcap_summaries": summaries,
        "tools": tool_info(),
        "existing_rules": existing if existing is not None else "(missing: %s)" % rules_path,
        "suricata_config_exists": os.path.isfile(cfg),
        "triage_errors": errors,
    }
    if not paths:
        out["triage_errors"].append("pcap_paths is empty: pass the training pcaps (e.g. /root/pcaps)")
    json.dump(out, sys.stdout)


def _charset(v: str) -> str:
    """Describe a value's character classes, e.g. 'hex', 'base64', 'base64+padding', 'other'."""
    import re
    if v == "":
        return "empty"
    if re.fullmatch(r"[0-9a-f]+", v):
        return "hex-lower" if re.search(r"[a-f]", v) else "digits"
    if re.fullmatch(r"[0-9a-fA-F]+", v):
        return "hex"
    if re.fullmatch(r"[A-Za-z]+", v):
        return "alpha"
    if re.fullmatch(r"[A-Za-z0-9+/]+", v):
        return "base64" + ("(has +/)" if re.search(r"[+/]", v) else "")
    if re.fullmatch(r"[A-Za-z0-9+/]+={1,2}", v):
        return "base64+padding"
    if re.fullmatch(r"[A-Za-z0-9_-]+", v):
        return "base64url/word"
    return "other"


if __name__ == "__main__":
    main()
