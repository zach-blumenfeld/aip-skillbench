"""Step `build-and-check`: compose the Suricata rule from detection_spec, write it to
rules_path, then verify it.

Verification (all automatic):
  1. `suricata -T` syntax check of the rules file.
  2. Every labeled pcap: Suricata alerts on sid iff the label says "alert", and never
     raises any other sid. A pure-Python emulator of the spec is checked too.
  3. Spec-driven near-miss pcaps synthesized from a positive request (one condition
     broken at a time -> must NOT alert; harmless variations -> MUST alert).
When Suricata is not installed, the emulator is the only judge (verified_with says so).

stdin: {"currentState": {detection_spec, pcap_labels, rules_path, suricata_config,
        pcap_paths, [rule_override], [attempt]}, "assets": {...}, "expects": [...]}
stdout: {"rule_text", "status": "pass"|"fail"|"exhausted", "failures", "checks", ...}
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcaplib  # noqa: E402

MAX_ATTEMPTS = 4
URI_MATCHES = ("exact_path", "exact", "prefix", "contains")


class SpecError(Exception):
    pass


# --------------------------------------------------------------------------- spec


def normalize_spec(spec):
    if not isinstance(spec, dict):
        raise SpecError("detection_spec must be an object")
    s = {
        "sid": int(spec.get("sid", 1000001)),
        "rev": int(spec.get("rev", 1)),
        "msg": str(spec.get("msg") or "Custom HTTP exfil"),
        "flow": str(spec.get("flow") or "established,to_server"),
        "method": spec.get("method"),
        "uri": spec.get("uri"),
        "headers": spec.get("headers") or [],
        "body_params": spec.get("body_params") or [],
        "body_contains": spec.get("body_contains") or [],
    }
    if '"' in s["msg"] or ";" in s["msg"]:
        raise SpecError('msg must not contain " or ;')
    if isinstance(s["uri"], str):
        s["uri"] = {"value": s["uri"], "match": "exact_path"}
    if s["uri"] is not None:
        s["uri"].setdefault("match", "exact_path")
        if s["uri"]["match"] not in URI_MATCHES:
            raise SpecError("uri.match must be one of %s" % (URI_MATCHES,))
        if not s["uri"].get("value"):
            raise SpecError("uri.value is required when uri is given")
    for h in s["headers"]:
        if not h.get("name") or h.get("value") is None:
            raise SpecError("each header needs name and value: %r" % (h,))
        h.setdefault("value_nocase", False)
        h.setdefault("match", "exact")
        if h["match"] not in ("exact", "contains"):
            raise SpecError("header match must be exact or contains")
    for p in s["body_params"]:
        if not p.get("name"):
            raise SpecError("each body_param needs a name: %r" % (p,))
        cs = p.get("charset")
        if not cs:
            raise SpecError("body_param %s needs charset, e.g. 'A-Za-z0-9+/' or '0-9a-fA-F'" % p["name"])
        if any(c in cs for c in '[]";'):
            raise SpecError("charset is the inside of a [...] class; no [ ] \" ; allowed: %r" % cs)
        try:
            re.compile("[%s]" % cs)
        except re.error as e:
            raise SpecError("charset %r is not a valid regex class: %s" % (cs, e))
        p["min_len"] = int(p["min_len"]) if p.get("min_len") is not None else None
        p["max_len"] = int(p["max_len"]) if p.get("max_len") is not None else None
        if p.get("exact_len") is not None:
            p["min_len"] = p["max_len"] = int(p["exact_len"])
        p.setdefault("allow_padding", False)
    return s


# --------------------------------------------------------------------------- rule text


def content_escape(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if ch in ';":\\|' or o < 0x20 or o > 0x7E:
            out.append("|%02x|" % o)
        else:
            out.append(ch)
    return "".join(out).replace("||", " ")


def pcre_lit(s: str) -> str:
    """Escape a literal for PCRE inside a Suricata rule: non-alnum -> \\xHH."""
    return "".join(ch if ch.isalnum() else "\\x%02x" % ord(ch) for ch in s)


def pcre_class(cs: str) -> str:
    return cs.replace("/", "\\x2f")


def quant(p) -> str:
    lo = p["min_len"] if p["min_len"] is not None else 1
    hi = p["max_len"]
    if hi is None:
        return "{%d,}" % lo
    if hi == lo:
        return "{%d}" % lo
    return "{%d,%d}" % (lo, hi)


def compose_rule(s) -> str:
    o = ['msg:"%s";' % s["msg"], "flow:%s;" % s["flow"]]
    if s["method"]:
        m = s["method"]
        o.append('http.method; content:"%s"; bsize:%d;' % (content_escape(m), len(m)))
    if s["uri"]:
        v, mt = s["uri"]["value"], s["uri"]["match"]
        if mt == "exact":
            o.append('http.uri; content:"%s"; bsize:%d;' % (content_escape(v), len(v)))
        elif mt == "exact_path":
            o.append('http.uri; content:"%s"; startswith; pcre:"/^%s(?:\\x3f|$)/";'
                     % (content_escape(v), pcre_lit(v)))
        elif mt == "prefix":
            o.append('http.uri; content:"%s"; startswith;' % content_escape(v))
        else:
            o.append('http.uri; content:"%s";' % content_escape(v))
    if s["headers"]:
        parts = ["http.header;"]
        for h in s["headers"]:
            name, val = h["name"], h["value"]
            val_re = ("(?i:%s)" % pcre_lit(val)) if h["value_nocase"] else pcre_lit(val)
            parts.append('content:"%s"; nocase;' % content_escape(name.lower()))
            if h["match"] == "exact":
                parts.append('pcre:"/(?:^|\\n)(?i:%s):[ \\t]*%s[ \\t]*\\r?(?:\\n|$)/";'
                             % (pcre_lit(name), val_re))
            else:
                parts.append('pcre:"/(?:^|\\n)(?i:%s):[^\\r\\n]*%s/";' % (pcre_lit(name), val_re))
        o.append(" ".join(parts))
    if s["body_params"] or s["body_contains"]:
        parts = ["http.request_body;"]
        for c in s["body_contains"]:
            parts.append('content:"%s";' % content_escape(c))
        for p in s["body_params"]:
            pad = "={0,2}" if p["allow_padding"] else ""
            parts.append('content:"%s=";' % content_escape(p["name"]))
            parts.append('pcre:"/(?:^|&)%s=[%s]%s%s(?:&|$)/";'
                         % (pcre_lit(p["name"]), pcre_class(p["charset"]), quant(p), pad))
        o.append(" ".join(parts))
    o.append("sid:%d; rev:%d;" % (s["sid"], s["rev"]))
    return "alert http any any -> any any (%s)" % " ".join(o)


# --------------------------------------------------------------------------- emulator


def value_ok(p, v) -> bool:
    if v is None:
        return False
    if p["allow_padding"]:
        v = re.sub(r"={1,2}$", "", v)
    lo = p["min_len"] if p["min_len"] is not None else 1
    if len(v) < lo or (p["max_len"] is not None and len(v) > p["max_len"]):
        return False
    return re.fullmatch("[%s]+" % p["charset"], v) is not None


def spec_matches(s, r) -> bool:
    if s["method"] and r["method"] != s["method"]:
        return False
    if s["uri"]:
        v, mt, u = s["uri"]["value"], s["uri"]["match"], r["uri"]
        ok = {"exact": u == v,
              "exact_path": u == v or u.startswith(v + "?"),
              "prefix": u.startswith(v),
              "contains": v in u}[mt]
        if not ok:
            return False
    for h in s["headers"]:
        hit = False
        for n, val in r["headers"]:
            if n.lower() != h["name"].lower():
                continue
            a, b = (val.lower(), h["value"].lower()) if h["value_nocase"] else (val, h["value"])
            if (a.strip() == b) if h["match"] == "exact" else (b in a):
                hit = True
        if not hit:
            return False
    for c in s["body_contains"]:
        if c not in r["body"]:
            return False
    params = pcaplib.body_params(r["body"])
    for p in s["body_params"]:
        if not any(n == p["name"] and value_ok(p, v) for n, v in params):
            return False
    return True


# --------------------------------------------------------------------------- mutations


def _clone(r):
    return {"method": r["method"], "uri": r["uri"], "version": r["version"],
            "headers": [list(h) for h in r["headers"]], "body": r["body"], "segments": 3}


def _set_param(r, name, value=None, remove=False, rename=None):
    out = []
    for n, v in pcaplib.body_params(r["body"]):
        if n == name:
            if remove:
                continue
            if rename is not None:
                n = rename
            if value is not None:
                v = value
        out.append(n if v is None else "%s=%s" % (n, v))
    r["body"] = "&".join(out)
    return r


def _resize(v, n):
    core = re.sub(r"=+$", "", v) or "A"
    return (core * (n // len(core) + 1))[:n]


def _bad_char(cs):
    for c in "!~*%g$#Z_-.":
        if not re.fullmatch("[%s]" % cs, c):
            return c
    return "\x01"


def mutations(s, base):
    m = []

    def add(name, r, expect):
        m.append((name, r, expect))

    add("rebuilt-3-segments", _clone(base), True)
    r = _clone(base); r["segments"] = 1; add("single-segment", r, True)
    r = _clone(base); r["segments"] = 15; add("many-segments", r, True)
    params = pcaplib.body_params(base["body"])
    if len(params) >= 2:
        r = _clone(base)
        r["body"] = "&".join(n if v is None else "%s=%s" % (n, v) for n, v in reversed(params))
        add("params-reversed", r, True)
    if s["method"]:
        r = _clone(base); r["method"] = "GET" if s["method"] != "GET" else "POST"
        add("wrong-method-%s" % r["method"], r, False)
    if s["uri"]:
        v, mt = s["uri"]["value"], s["uri"]["match"]
        r = _clone(base); r["uri"] = "/index.html"; add("uri-unrelated", r, False)
        if mt in ("exact", "exact_path"):
            r = _clone(base); r["uri"] = v + "x"; add("uri-suffixed", r, False)
            r = _clone(base); r["uri"] = v + "/extra"; add("uri-subpath", r, False)
        if mt in ("exact", "exact_path", "prefix"):
            r = _clone(base); r["uri"] = "/x" + v; add("uri-prefixed", r, False)
        r = _clone(base); r["uri"] = v + "?q=1"
        add("uri-with-query", r, mt != "exact")
    for h in s["headers"]:
        low = h["name"].lower()

        def rename_hdr(r, newname):
            for hh in r["headers"]:
                if hh[0].lower() == low:
                    hh[0] = newname
            return r

        def set_hdr(r, newval):
            for hh in r["headers"]:
                if hh[0].lower() == low:
                    hh[1] = newval
            return r

        add("hdr-%s-name-upper" % low, rename_hdr(_clone(base), h["name"].upper()), True)
        add("hdr-%s-name-lower" % low, rename_hdr(_clone(base), low), True)
        r = _clone(base); r["headers"] = [hh for hh in r["headers"] if hh[0].lower() != low]
        add("hdr-%s-missing" % low, r, False)
        other = "normal" if h["value"].lower() != "normal" else "other"
        add("hdr-%s-value-%s" % (low, other), set_hdr(_clone(base), other), False)
        if h["match"] == "exact":
            add("hdr-%s-value-suffixed" % low, set_hdr(_clone(base), h["value"] + "x"), False)
        if h["value"].swapcase() != h["value"]:
            add("hdr-%s-value-swapcase" % low, set_hdr(_clone(base), h["value"].swapcase()),
                bool(h["value_nocase"]))
        r = _clone(base); r["headers"] = [hh for hh in r["headers"] if hh[0].lower() != low]
        r["body"] = r["body"] + "&note=%s: %s" % (h["name"], h["value"])
        add("hdr-%s-only-in-body" % low, r, False)
    for p in s["body_params"]:
        n = p["name"]
        cur = next((v for nn, v in params if nn == n and v is not None), None)
        if cur is None:
            continue
        add("param-%s-missing" % n, _set_param(_clone(base), n, remove=True), False)
        add("param-%s-renamed-x%s" % (n, n), _set_param(_clone(base), n, rename="x" + n), False)
        lo, hi = p["min_len"], p["max_len"]
        if lo is not None:
            add("param-%s-len-%d-min" % (n, lo), _set_param(_clone(base), n, _resize(cur, lo)), True)
            if lo > 1:
                add("param-%s-len-%d-short" % (n, lo - 1),
                    _set_param(_clone(base), n, _resize(cur, lo - 1)), False)
        if hi is not None:
            if hi != lo:
                add("param-%s-len-%d-max" % (n, hi), _set_param(_clone(base), n, _resize(cur, hi)), True)
            add("param-%s-len-%d-long" % (n, hi + 1),
                _set_param(_clone(base), n, _resize(cur, hi + 1)), False)
        core = re.sub(r"=+$", "", cur)
        mid = len(core) // 2
        bad = core[:mid] + _bad_char(p["charset"]) + core[mid + 1:]
        add("param-%s-bad-char" % n, _set_param(_clone(base), n, bad), False)
        if s["uri"] is None or s["uri"]["match"] != "exact":
            r = _set_param(_clone(base), n, remove=True)
            r["uri"] = r["uri"] + ("&" if "?" in r["uri"] else "?") + "%s=%s" % (n, cur)
            add("param-%s-in-uri-not-body" % n, r, False)
    return m


# --------------------------------------------------------------------------- suricata


def suricata_test(bin_, cfg, rules, workdir):
    logd = tempfile.mkdtemp(prefix="T-", dir=workdir)
    cmd = [bin_, "-T", "-c", cfg, "-S", rules, "-l", logd]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    text = (r.stdout or "") + (r.stderr or "")
    for fn in ("suricata.log",):
        fp = os.path.join(logd, fn)
        if os.path.isfile(fp):
            with open(fp, errors="replace") as fh:
                text += fh.read()
    errs = [ln.strip() for ln in text.splitlines()
            if re.search(r"\berror\b|<Error>|E: ", ln, re.I)][:15]
    loaded = re.search(r"(\d+) rules? successfully loaded, (\d+) rules? failed", text)
    rule_errs = [e for e in errs if re.search(r"signature|rule|parse", e, re.I)]
    ok = (r.returncode == 0 and not rule_errs
          and not (loaded and (int(loaded.group(2)) > 0 or int(loaded.group(1)) == 0)))
    return {"ok": ok, "returncode": r.returncode, "errors": errs,
            "loaded_summary": loaded.group(0) if loaded else None, "command": " ".join(cmd)}


def suricata_alerts(bin_, cfg, rules, pcap, workdir):
    logd = tempfile.mkdtemp(prefix="run-", dir=workdir)
    cmd = [bin_, "-c", cfg, "-S", rules, "-k", "none", "-r", pcap, "-l", logd]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    eve = os.path.join(logd, "eve.json")
    if not os.path.isfile(eve):
        return None, "no eve.json (rc=%s): %s" % (r.returncode, (r.stderr or r.stdout)[-400:])
    sids = []
    with open(eve, errors="replace") as fh:
        for ln in fh:
            try:
                ev = json.loads(ln)
            except ValueError:
                continue
            if ev.get("event_type") == "alert":
                sids.append(ev.get("alert", {}).get("signature_id"))
    return sids, None


# --------------------------------------------------------------------------- main


def requests_in(pcap):
    out = []
    for st in pcaplib.client_streams(pcap):
        out.extend(pcaplib.parse_requests(st["data"]))
    return out


def main():
    req = json.load(sys.stdin)
    st = req.get("currentState", {})
    attempt = int(st.get("attempt") or 0) + 1
    rules_path = st.get("rules_path") or "/root/local.rules"
    cfg = st.get("suricata_config") or "/root/suricata.yaml"
    labels = st.get("pcap_labels") or {}
    failures, warnings, checks = [], [], []

    def finish(extra):
        status = "pass" if not failures else ("exhausted" if attempt >= MAX_ATTEMPTS else "fail")
        out = {"attempt": attempt, "status": status, "failures": failures,
               "warnings": warnings, "checks": checks}
        out.update(extra)
        json.dump(out, sys.stdout)

    try:
        spec = normalize_spec(st.get("detection_spec"))
    except (SpecError, ValueError, TypeError, AttributeError) as e:
        failures.append("detection_spec invalid: %s" % e)
        return finish({"rule_text": "", "rules_written": "", "verified_with": "none",
                       "suricata_syntax": {"ok": None, "note": "not run: spec invalid"}})

    override = (st.get("rule_override") or "").strip()
    rule = override if override else compose_rule(spec)
    if not re.search(r"\bsid\s*:\s*%d\s*;" % spec["sid"], rule):
        failures.append("rule does not carry sid:%d" % spec["sid"])
    if override and len([ln for ln in override.splitlines()
                         if ln.strip() and not ln.strip().startswith("#")]) != 1:
        warnings.append("rule_override has more than one rule line; only sid %d should alert" % spec["sid"])

    os.makedirs(os.path.dirname(os.path.abspath(rules_path)), exist_ok=True)
    with open(rules_path, "w", encoding="utf-8") as fh:
        fh.write("# %s (sid %d) - written by suricata-http-exfil-rule\n%s\n"
                 % (spec["msg"], spec["sid"], rule))

    bin_ = shutil.which("suricata")
    workdir = tempfile.mkdtemp(prefix="suri-check-")
    verified = "suricata+emulator" if bin_ else "emulator-only"
    suri_version = None
    if bin_:
        try:
            v = subprocess.run([bin_, "-V"], capture_output=True, text=True, timeout=30)
            suri_version = ((v.stdout or v.stderr).strip().splitlines() or [""])[0][:120]
        except Exception as e:  # noqa: BLE001
            suri_version = "version check failed: %s" % e
    if not bin_:
        warnings.append("suricata not on PATH: rule text was NOT executed; only the spec emulator ran")
    elif not os.path.isfile(cfg):
        failures.append("suricata config not found: %s" % cfg)
        bin_ = None

    syntax = {"ok": None, "note": "not run: suricata unavailable"}
    if bin_:
        syntax = suricata_test(bin_, cfg, rules_path, workdir)
        if not syntax["ok"]:
            failures.append("suricata -T failed: %s" % ("; ".join(syntax["errors"]) or syntax["loaded_summary"]))
            bin_ = None  # pointless to replay pcaps with a broken rule

    # Labeled pcaps + choose a base request for mutations.
    jobs = []  # (name, kind, expect, pcap_path, emulator_result)
    base = None
    for pcap in pcaplib.expand_pcap_paths(st.get("pcap_paths") or []):
        lab = labels.get(pcap, labels.get(os.path.basename(pcap)))
        if lab not in ("alert", "no-alert"):
            warnings.append("no alert/no-alert label for %s; skipped" % pcap)
            continue
        try:
            reqs = requests_in(pcap)
        except Exception as e:  # noqa: BLE001
            failures.append("cannot parse %s: %s" % (pcap, e))
            continue
        emu = any(spec_matches(spec, r) for r in reqs)
        if base is None and lab == "alert":
            base = next((r for r in reqs if spec_matches(spec, r)), None)
        jobs.append((os.path.basename(pcap), "labeled", lab == "alert", pcap, emu))
    if not any(j[2] for j in jobs):
        warnings.append("no pcap labeled 'alert': positives untested")
    if base is None:
        warnings.append("no positive request matched the spec: near-miss mutations skipped")
    else:
        for i, (name, r, expect) in enumerate(mutations(spec, base)):
            path = os.path.join(workdir, "mut-%02d-%s.pcap" % (i, re.sub(r"[^A-Za-z0-9_.-]", "_", name)))
            raw = pcaplib.build_request(r["method"], r["uri"], r["version"], r["headers"], r["body"])
            pcaplib.write_session_pcap(path, raw, sport=41000 + i, segments=r["segments"])
            jobs.append((name, "mutation", expect, path, spec_matches(spec, r)))

    results = {}
    if bin_:
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = {j[3]: ex.submit(suricata_alerts, bin_, cfg, rules_path, j[3], workdir) for j in jobs}
            results = {k: f.result() for k, f in futs.items()}

    for name, kind, expect, path, emu in jobs:
        c = {"name": name, "kind": kind, "expect_alert": expect, "emulator": emu}
        ok = True
        if emu != expect:
            ok = False
            failures.append("%s %s: spec emulator says %s, expected %s%s" % (
                kind, name, "alert" if emu else "no alert", "alert" if expect else "no alert",
                " (the detection_spec disagrees with the pcap label)" if kind == "labeled" else ""))
        if bin_:
            sids, err = results[path]
            if err:
                ok = False
                c["suricata_error"] = err
                failures.append("%s %s: suricata error: %s" % (kind, name, err))
            else:
                hit = sids.count(spec["sid"])
                other = sorted(set(x for x in sids if x != spec["sid"]))
                c["suricata_alerts"] = hit
                if other:
                    c["other_sids"] = other
                    ok = False
                    failures.append("%s %s: unexpected sids %s" % (kind, name, other))
                if bool(hit) != expect:
                    ok = False
                    failures.append("%s %s: suricata %s, expected %s" % (
                        kind, name, "alerted" if hit else "did not alert",
                        "alert" if expect else "no alert"))
        c["ok"] = ok
        checks.append(c)

    finish({"rule_text": rule, "rules_written": os.path.abspath(rules_path),
            "verified_with": verified, "suricata_version": suri_version, "suricata_syntax": syntax, "workdir": workdir,
            "detection_spec_normalized": spec})


if __name__ == "__main__":
    main()
