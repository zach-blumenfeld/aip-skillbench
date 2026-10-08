"""Step search-artifacts: keyword sweep over one product workspace (or every workspace
when no product is known). Returns whole Slack conversations that match, URL-bearing
messages with their sharer, the workspace URL registry, document / meeting / PR hits,
entity hints for the next hop, and a cross-product sweep flagged for rejection."""
import re
from collections import Counter

from eas_lib import (BOT_USERS, clip, find_urls, conversations, emit, fail, load_employees,
                     load_json, mentions_any, norm, parse_transcript, product_files, read_payload,
                     resolve_name, roster, slack_items)

MAX_CONVS, MAX_MSGS, MAX_HITS = 25, 30, 25
INTERNAL_HOSTS = ("sf-internal.slack.com", "github.com/salesforce")
STOP = {"Hi", "Hey", "Thanks", "The", "This", "That", "Great", "Good", "Also", "Yes", "Absolutely",
        "Agreed", "Let", "Let's", "We", "I", "It", "They", "Their", "What", "How", "Do", "Does",
        "Wow", "Sounds", "Count", "Exactly", "Sure", "Maybe", "One", "Overall", "AI", "CRM", "UX",
        "Looking", "Here", "Check", "Read", "Stay", "Dive", "Explore", "Discover", "Facebook", "Twitter"}


def compile_terms(terms):
    pats = []
    for t in terms:
        t = (t or "").strip()
        if t:
            pats.append((t, re.compile(r"(?<![A-Za-z0-9])" + re.escape(t), re.I)))
    return pats


def hits_in(text, pats):
    return [t for t, p in pats if p.search(text or "")]


def snippet(text, pats, width=220):
    for _, p in pats:
        m = p.search(text or "")
        if m:
            a = max(0, m.start() - width // 2)
            return ("…" if a else "") + text[a:a + width].replace("\n", " ") + "…"
    return clip(text, width)


def main():
    state, _, _ = read_payload()
    root = state.get("data_root") or fail("state.data_root is required")
    terms = state.get("search_terms") or fail("state.search_terms (non-empty list) is required")
    pats = compile_terms(terms)
    product = state.get("target_product") or ""
    aliases = state.get("aliases") or ([product] if product else [])
    files = product_files(root)
    employees = load_employees(root)
    scope = [product] if product in files else list(files)

    convs_out, url_msgs, reg, docs, meets, prs = [], [], [], [], [], []
    names = Counter()
    for p in scope:
        prod = load_json(files[p])
        team = roster(prod, employees)
        items = slack_items(prod)
        for key, conv in conversations(items).items():
            human = [m for m in conv if m["user"] not in BOT_USERS]
            matched = [m for m in human if hits_in(m["text"], pats)]
            if not matched:
                continue
            convs_out.append({
                "product": p, "channel": conv[0]["channel"], "conversation": key.split("|")[1],
                "started_by": human[0]["user"] if human else None,
                "matched_terms": sorted({t for m in matched for t in hits_in(m["text"], pats)}),
                "n_matched": len(matched), "n_messages": len(human),
                "messages": [{"id": m["id"], "user": m["user"],
                              "name": employees.get(m["user"], {}).get("name"),
                              "text": clip(m["text"], 520)} for m in human[:MAX_MSGS]],
            })
            for m in matched:
                names.update(w for w in re.findall(r"\b[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\b|\b[A-Z][a-z]{3,}\b", m["text"])
                             if w not in STOP and not any(w in (e.get("name") or "") for e in employees.values()))
        for m in items:
            urls = find_urls(m["text"])
            if not urls or m["user"] in BOT_USERS:
                continue
            if not (hits_in(m["text"], pats)):
                continue
            url_msgs.append({
                "product": p, "channel": m["channel"], "message_id": m["id"], "user": m["user"],
                "name": employees.get(m["user"], {}).get("name"), "urls": urls,
                "internal": any(h in u for u in urls for h in INTERNAL_HOSTS),
                "about_own_product": bool(re.search(r"\b(our|my) (product|demo|feature)\b", m["text"], re.I)),
                "text": clip(m["text"], 300),
            })
        for u in prod.get("urls", []) or []:
            if hits_in(u.get("link", "") + " " + u.get("description", ""), pats):
                reg.append({"product": p, "id": u.get("id"), "link": u.get("link"),
                            "description": clip(u.get("description", ""), 200)})
        for d in prod.get("documents", []) or []:
            blob = d.get("content", "") + " " + (d.get("feedback") or "")
            if hits_in(blob, pats):
                docs.append({"product": p, "doc_id": d.get("id"), "type": d.get("type"),
                             "author": d.get("author"), "snippet": snippet(blob, pats)})
        for mt in prod.get("meeting_transcripts", []) or []:
            att, turns = parse_transcript(mt.get("transcript", ""))
            lines = [(n, u) for n, u in turns if hits_in(u, pats)]
            if not lines:
                continue
            parts = set(mt.get("participants", []) or [])
            meets.append({"product": p, "meeting_id": mt.get("id"), "document_type": mt.get("document_type"),
                          "lines": [{"speaker": n, "employee_id": resolve_name(n, parts, team, employees)[0],
                                     "text": clip(u, 300)} for n, u in lines[:12]]})
        for pr in prod.get("prs", []) or []:
            blob = " ".join([pr.get("title", ""), pr.get("summary", "")] +
                            [r.get("comment", "") for r in pr.get("reviews", []) or []])
            if hits_in(blob, pats):
                prs.append({"product": p, "pr_id": pr.get("id"), "link": pr.get("link"),
                            "internal": "github.com/salesforce/" in (pr.get("link") or ""),
                            "author": (pr.get("user") or {}).get("login"),
                            "state": pr.get("state"), "merged": pr.get("merged"),
                            "reviews": [{"user": (r.get("user") or {}).get("login"), "state": r.get("state"),
                                         "comment": clip(r.get("comment", ""), 160)}
                                        for r in pr.get("reviews", []) or []],
                            "title": pr.get("title"), "snippet": snippet(blob, pats)})

    alias_norm = {norm(a) for a in aliases}
    cross = []
    if product in files and aliases:
        for p, f in files.items():
            if p == product:
                continue
            n = sum(1 for m in slack_items(load_json(f)) if mentions_any(m["text"], aliases) and hits_in(m["text"], pats))
            if n:
                cross.append({"product_file": p, "matching_messages": n})

    prs.sort(key=lambda x: not x["internal"])
    convs_out.sort(key=lambda c: (-c["n_matched"], c["conversation"]))
    emit({
        "search_scope": scope,
        "search_terms_used": [t for t, _ in pats],
        "conversations": convs_out[:MAX_CONVS],
        "conversations_total": len(convs_out),
        "url_messages": url_msgs[:MAX_HITS * 2],
        "url_registry": reg[:MAX_HITS * 2],
        "document_hits": docs[:MAX_HITS],
        "meeting_hits": meets[:MAX_HITS],
        "pr_hits": prs[:MAX_HITS],
        "entity_hints": sorted([w for w, _ in names.most_common(40) if norm(w) not in alias_norm],
                               key=lambda w: (not re.search(r"[a-z][A-Z]", w), -names[w]))[:20],
        "cross_product_sweep": cross,
    })


if __name__ == "__main__":
    main()
