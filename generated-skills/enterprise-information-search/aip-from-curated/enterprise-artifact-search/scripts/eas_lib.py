"""Shared helpers for the enterprise-artifact-search scripts (stdlib only).

Dataset layout (one workspace per product):
  <data_root>/products/<Product>.json  keys: slack, documents, meeting_transcripts,
                                       meeting_chats, urls, prs
  <data_root>/metadata/employee.json   {eid: {employee_id, name, role, location, org}}
Slack items are flat: {Channel{name}, Message{User{userId,timestamp,text}}, ThreadReplies, id}.
A conversation is the run of messages in one channel whose id shares the
"YYYYMMDD" prefix (id = "YYYYMMDD-<seq>-<hash>"); ThreadReplies is usually empty.
"""
import json
import os
import re
import sys
from functools import lru_cache

EID_RE = re.compile(r"\beid_[0-9a-f]{6,}\b")
URL_RE = re.compile(r"https?://[^\s<>|\"')\]]+")
DOC_LINK_RE = re.compile(r"/archives/docs/([A-Za-z0-9_\-]+)")
BOT_USERS = {"slack_admin_bot"}
GENERIC_ALIAS = {"aix", "pm", "planning", "product", "dev", "develop", "bug"}


def read_payload():
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    return payload.get("currentState", payload), payload.get("assets", {}), payload.get("expects")


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.write("\n")


def fail(msg, **extra):
    emit({"error": msg, **extra})
    sys.exit(1)


def resolve_root(data_root):
    """Accept the dataset root or its parent; return the folder holding products/."""
    cands = [data_root] if data_root else []
    cands += ["/root/DATA", "/root/data", "./DATA", "./data"]
    for c in cands:
        if not c:
            continue
        c = os.path.abspath(os.path.expanduser(c))
        if os.path.isdir(os.path.join(c, "products")):
            return c
        for sub in ("DATA", "data"):
            if os.path.isdir(os.path.join(c, sub, "products")):
                return os.path.join(c, sub)
    fail("dataset root with a products/ folder not found", tried=cands)


def product_files(root):
    pdir = os.path.join(root, "products")
    return {os.path.splitext(f)[0]: os.path.join(pdir, f)
            for f in sorted(os.listdir(pdir)) if f.endswith(".json")}


@lru_cache(maxsize=64)
def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_employees(root):
    path = os.path.join(root, "metadata", "employee.json")
    if not os.path.exists(path):
        return {}
    data = load_json(path)
    if isinstance(data, list):
        return {e["employee_id"]: e for e in data if "employee_id" in e}
    return data


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def camel_split(s):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s).strip()


def slack_items(prod):
    out = []
    for m in prod.get("slack", []) or []:
        msg = (m.get("Message") or {}).get("User") or {}
        out.append({
            "channel": (m.get("Channel") or {}).get("name", ""),
            "id": m.get("id") or msg.get("utterranceID", ""),
            "user": msg.get("userId", ""),
            "ts": msg.get("timestamp", ""),
            "text": msg.get("text", "") or "",
        })
        for r in m.get("ThreadReplies") or []:
            ru = r.get("User", r) if isinstance(r, dict) else {}
            out.append({
                "channel": (m.get("Channel") or {}).get("name", ""),
                "id": ru.get("utterranceID") or m.get("id", ""),
                "user": ru.get("userId", ""),
                "ts": ru.get("timestamp", ""),
                "text": ru.get("text", "") or "",
                "reply_to": m.get("id"),
            })
    return out


def conv_key(item):
    return item["channel"] + "|" + item["id"].split("-")[0]


def seq_of(item):
    parts = item["id"].split("-")
    try:
        return int(parts[1])
    except (IndexError, ValueError):
        return 0


def conversations(items):
    convs = {}
    for it in items:
        convs.setdefault(conv_key(it), []).append(it)
    for k in convs:
        convs[k].sort(key=lambda x: (seq_of(x), x["ts"]))
    return convs


def derive_aliases(product, prod):
    """Product name plus codenames found in its own workspace (planning channels,
    doc-id prefixes, meeting-series ids)."""
    raw = {product}
    for it in slack_items(prod):
        ch = it["channel"]
        if ch.startswith("planning-"):
            name = ch[len("planning-"):]
            name = re.sub(r"-PM$", "", name)
            raw.add(name)
    # A doc-id prefix counts only if a doc carrying it is linked from this workspace's
    # Slack; an unshared doc may be another product's report planted as a distractor.
    shared = set()
    for it in slack_items(prod):
        shared.update(DOC_LINK_RE.findall(it["text"]))
    for d in prod.get("documents", []) or []:
        if d.get("id") not in shared:
            continue
        did = re.sub(r"^(final|latest)_", "", d.get("id", ""))
        dtype = re.sub(r"[^a-z0-9]+", "_", (d.get("type") or "").lower()).strip("_")
        if dtype and did.endswith("_" + dtype):
            raw.add(did[: -len(dtype) - 1])
    for m in (prod.get("meeting_transcripts", []) or []) + (prod.get("meeting_chats", []) or []):
        mid = m.get("id", "")
        mm = re.match(r"^(?:product_dev_)?(.+?)_planning_\d+", mid) or re.match(r"^product_dev_(.+?)_\d+", mid)
        if mm:
            raw.add(mm.group(1))
    # PR repo names are not used: many PRs live in upstream open-source repos.
    seen, aliases = set(), []
    for a in sorted(raw, key=lambda s: (s != product, s)):
        variants = [a]
        split = camel_split(a)
        if split != a and all(len(w) >= 3 for w in split.split()):
            variants.append(split)
        for v in variants:
            if not v or norm(v) in GENERIC_ALIAS or len(norm(v)) < 4 or v.lower() in seen:
                continue
            seen.add(v.lower())
            aliases.append(v)
    return aliases


def mentions_any(text, aliases):
    t = (text or "").lower()
    tn = norm(text)
    for a in aliases:
        if a.lower() in t or (len(norm(a)) >= 6 and norm(a) in tn):
            return True
    return False


def roster(prod, employees):
    """Every employee id that appears anywhere in a product workspace."""
    ids = set()
    blob = json.dumps(prod)
    ids.update(EID_RE.findall(blob))
    return {i for i in ids if not employees or i in employees}


def name_index(ids, employees):
    idx = {}
    for i in ids:
        e = employees.get(i)
        if e:
            idx.setdefault(e["name"].lower(), []).append(i)
    return idx


def resolve_name(name, preferred, fallback, employees):
    """Map a display name to an eid, trying the narrowest id set first."""
    key = (name or "").strip().lower()
    for pool in (preferred, fallback):
        hits = name_index(pool, employees).get(key, [])
        if len(hits) == 1:
            return hits[0], "unique"
        if len(hits) > 1:
            return None, "ambiguous:" + ",".join(sorted(hits))
    return None, "not_found"


def parse_transcript(text):
    """Return (attendee names, [(speaker, utterance)])."""
    lines = (text or "").splitlines()
    attendees, turns, mode = [], [], None
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.lower() == "attendees":
            mode = "att"
            continue
        if s.lower() == "transcript":
            mode = "tr"
            continue
        if mode == "att":
            attendees += [a.strip() for a in s.split(",") if a.strip()]
        else:
            mm = re.match(r"^([A-Z][\w.'\- ]{1,40}?):\s+(.*)$", s)
            if mm:
                turns.append((mm.group(1).strip(), mm.group(2).strip()))
            elif turns:
                turns[-1] = (turns[-1][0], turns[-1][1] + " " + s)
    return attendees, turns


def find_urls(text):
    """URLs in text, without trailing sentence punctuation."""
    return [u.rstrip(".,;:!?") for u in URL_RE.findall(text or "")]


def clip(s, n):
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"
