"""Step report-evidence: for a named document type of the target product, collect
candidate reports, apply the 2-signal product-grounding gate, pick the final/latest
version, and gather author + reviewer evidence (explicit fields, review-meeting turns,
Slack review-thread replies, meeting chats, PR reviews) with employee ids resolved."""
import re

from eas_lib import (BOT_USERS, DOC_LINK_RE, EID_RE, clip, conv_key, conversations,
                     derive_aliases, emit, fail, load_employees, load_json, mentions_any,
                     norm, parse_transcript, product_files, read_payload, resolve_name,
                     roster, slack_items)

REVIEWER_FIELDS = ("reviewers", "key_reviewers", "approvers", "requested_reviewers")
AUTHOR_FIELDS = ("author", "authors", "created_by", "owner")
ACK_RE = re.compile(r"^\W*(thanks|thank you|great|looks good|lgtm|sounds (good|perfect|great)|"
                    r"agreed|awesome|nice|perfect|count me in|looking forward)\b", re.I)


def as_ids(v):
    if isinstance(v, str):
        return EID_RE.findall(v) or [v]
    if isinstance(v, list):
        out = []
        for x in v:
            out += as_ids(x if not isinstance(x, dict) else (x.get("employee_id") or x.get("login") or x.get("id") or ""))
        return out
    if isinstance(v, dict):
        return as_ids(v.get("employee_id") or v.get("login") or v.get("id") or "")
    return []


def family_key(doc_id):
    """Version stem: drop final_/latest_ prefixes and _final/_latest suffixes (new_ starts its own family)."""
    k = re.sub(r"^((final|latest)_)+", "", doc_id or "")
    return re.sub(r"(_(final|latest))+$", "", k)


def marker(doc_id, link):
    blob = ((doc_id or "") + " " + (link or "")).lower()
    return 2 if "latest" in blob else 1 if "final" in blob else 0


def is_substantive(text):
    t = re.sub(r"<[^>]+>|@\S+", "", text or "").strip()
    if len(t) < 60 and ACK_RE.search(t):
        return False
    if ACK_RE.search(t) and not re.search(r"\b(could|should|suggest|add|include|expand|maybe|consider|how|what|why|\?)", t, re.I):
        return False
    return True


def main():
    state, _, _ = read_payload()
    root = state.get("data_root") or fail("state.data_root is required")
    product = state.get("target_product") or fail("report-evidence needs target_product; route to plan-search instead")
    doc_type = state.get("doc_type") or ""
    files = product_files(root)
    prod = load_json(files[product])
    employees = load_employees(root)
    aliases = state.get("aliases") or derive_aliases(product, prod)
    other_names = [a for p, f in files.items() if p != product
                   for a in derive_aliases(p, load_json(f)) if norm(a) not in {norm(x) for x in aliases}]
    team = roster(prod, employees)
    items = slack_items(prod)
    convs = conversations(items)
    meetings = prod.get("meeting_transcripts", []) or []
    chats = prod.get("meeting_chats", []) or []

    docs = [d for d in prod.get("documents", []) or []
            if not doc_type or (d.get("type") or "").lower() == doc_type.lower()
            or doc_type.lower() in (d.get("id", "") + " " + d.get("content", "")[:300]).lower()]
    if not docs:
        emit({"report_status": "NEED_MORE_SEARCH", "report_candidates": [],
              "note": "no document of type '%s' in %s; search other artifacts" % (doc_type, product)})
        return

    def shares_of(doc_id):
        return [it for it in items if doc_id in DOC_LINK_RE.findall(it["text"])]

    cands = []
    for d in docs:
        did = d.get("id", "")
        text = d.get("content", "") or ""
        shares = shares_of(did)
        mtgs = [m for m in meetings if (m.get("document_type") or "").lower() == (d.get("type") or "").lower()
                and mentions_any(m.get("id", "") + " " + m.get("transcript", "")[:600], aliases)]
        chat_links = {family_key(x) for c in chats for x in DOC_LINK_RE.findall(c.get("text", ""))}
        names_product = mentions_any(text[:3000], aliases)
        sig = {
            "A_in_product_workspace": True,
            "B_content_names_product": names_product,
            "C_shared_in_product_channel": any(mentions_any(s["channel"], aliases) for s in shares),
            "D_id_or_link_has_product_token": mentions_any(did + " " + d.get("document_link", ""), aliases),
            # Doc-specific: a product meeting on this type whose chat links this report
            # family, or (no linking chat) whose type matches a report naming the product.
            "E_product_meeting_discusses_doc": bool(mtgs) and (family_key(did) in chat_links
                                                                or (names_product and not chat_links)),
        }
        own = sum(text.count(a) for a in aliases)
        other = max([text.count(a) for a in other_names if len(norm(a)) >= 6] or [0])
        n = sum(sig.values())
        cands.append({
            "doc_id": did, "type": d.get("type"), "date": d.get("date"), "author": d.get("author"),
            "link": d.get("document_link"), "signals": sig, "signal_count": n,
            "valid": n >= 2 and not (other > own and not sig["B_content_names_product"]),
            "distractor": other > own and not sig["B_content_names_product"],
            "times_shared": len(shares), "family": family_key(did),
            "content_head": clip(text, 140),
        })
    valid = [c for c in cands if c["valid"]]
    if not valid:
        emit({"report_status": "AMBIGUOUS", "report_candidates": cands,
              "note": "no candidate passed 2 grounding signals"})
        return

    def rank(c):
        return (marker(c["doc_id"], c["link"]), c["date"] or "", c["times_shared"])
    selected = max(valid, key=rank)
    fam = family_key(selected["doc_id"])
    family = [c for c in valid if family_key(c["doc_id"]) == fam]
    fam_ids = [c["doc_id"] for c in family]
    sel_doc = next(d for d in docs if d.get("id") == selected["doc_id"])

    # Authors: document fields first.
    authors = []
    for f in AUTHOR_FIELDS:
        for c in [sel_doc] + [d for d in docs if d.get("id") in fam_ids]:
            authors += [i for i in as_ids(c.get(f)) if i.startswith("eid_")]
    explicit = []
    for f in REVIEWER_FIELDS:
        for c in [d for d in docs if d.get("id") in fam_ids]:
            explicit += [{"employee_id": i, "field": f, "doc_id": c.get("id")} for i in as_ids(c.get(f))]

    # Slack: share messages of any version, then the rest of that conversation.
    slack_ev, share_posters = [], []
    for did in fam_ids:
        for s in shares_of(did):
            share_posters.append(s["user"])
            conv = convs.get(conv_key(s), [])
            after = [m for m in conv if (m["id"], m["ts"]) != (s["id"], s["ts"]) and m["ts"] >= s["ts"]]
            replies = []
            for m in after:
                if m["user"] in BOT_USERS:
                    continue
                if DOC_LINK_RE.search(m["text"]) and m["user"] == s["user"] and m is not after[0]:
                    break
                replies.append({"message_id": m["id"], "user": m["user"],
                                "name": employees.get(m["user"], {}).get("name"),
                                "is_author": m["user"] in authors or m["user"] == s["user"],
                                "substantive": is_substantive(m["text"]),
                                "text": clip(m["text"], 420)})
            slack_ev.append({"doc_id": did, "channel": s["channel"], "share_message_id": s["id"],
                             "shared_by": s["user"], "share_text": clip(s["text"], 300), "replies": replies})
    if not authors:
        authors = list(dict.fromkeys(share_posters))

    # Meetings about this document type, grounded to the product.
    meet_ev = []
    for m in meetings:
        if (m.get("document_type") or "").lower() != (selected["type"] or "").lower():
            continue
        if not mentions_any(m.get("id", "") + " " + m.get("transcript", "")[:800], aliases):
            continue
        parts = [p for p in m.get("participants", []) or []]
        attendees, turns = parse_transcript(m.get("transcript", ""))
        chat = next((c for c in chats if c.get("id", "").startswith(m.get("id", "") + "_chat")), None)
        speakers = {}
        for name, utt in turns:
            pid, how = resolve_name(name, set(parts) | set(authors), team, employees)
            sp = speakers.setdefault(name, {"name": name, "employee_id": pid, "resolution": how,
                                            "is_author": pid in authors, "turns": []})
            sp["turns"].append(clip(utt, 300))
        for sp in speakers.values():
            sp["n_turns"] = len(sp["turns"])
            sp["turns"] = sp["turns"][:4]
        meet_ev.append({
            "meeting_id": m.get("id"), "date": m.get("date"), "participants": parts,
            "attendees_named": attendees,
            "silent_participants": [p for p in parts if p not in {s["employee_id"] for s in speakers.values()}],
            "chat": clip(chat.get("text", ""), 300) if chat else None,
            "chat_links_version": [d for d in fam_ids if chat and d in chat.get("text", "")],
            "speakers": list(speakers.values()),
        })

    # PR reviews linking this document (rare for reports).
    pr_ev = []
    for p in prod.get("prs", []) or []:
        blob = " ".join([p.get("title", ""), p.get("summary", "")])
        if any(d in blob for d in fam_ids):
            pr_ev.append({"pr_id": p.get("id"), "author": (p.get("user") or {}).get("login"),
                          "reviewers": [(r.get("user") or {}).get("login") for r in p.get("reviews", [])]})

    # Conversations that talk about this document type without linking any version:
    # brainstorms of an upcoming report, or reports on a competitor's product.
    unlinked = []
    dt = (selected["type"] or "").lower()
    for key, conv in convs.items():
        human = [m for m in conv if m["user"] not in BOT_USERS]
        if not any(dt in m["text"].lower() for m in human):
            continue
        if any(d in DOC_LINK_RE.findall(m["text"]) for m in human for d in fam_ids):
            continue
        first = next(m for m in human if dt in m["text"].lower())
        unlinked.append({"channel": conv[0]["channel"], "conversation": key.split("|")[1],
                         "message_id": first["id"], "user": first["user"],
                         "people": list(dict.fromkeys(m["user"] for m in human)),
                         "text": clip(first["text"], 260)})

    # Default suggestion: explicit > meeting contributors > slack substantive repliers.
    sugg, why = [], {}
    for e in explicit:
        sugg.append(e["employee_id"]); why.setdefault(e["employee_id"], []).append("field:" + e["field"])
    for me in meet_ev:
        for sp in me["speakers"]:
            if sp["employee_id"] and not sp["is_author"]:
                sugg.append(sp["employee_id"]); why.setdefault(sp["employee_id"], []).append("meeting:" + me["meeting_id"])
    for se in slack_ev:
        for r in se["replies"]:
            if r["substantive"] and not r["is_author"]:
                sugg.append(r["user"]); why.setdefault(r["user"], []).append("slack:" + r["message_id"])
    sugg = [i for i in dict.fromkeys(sugg) if i not in authors]
    unresolved = [sp["name"] + " (" + sp["resolution"] + ")" for me in meet_ev
                  for sp in me["speakers"] if not sp["employee_id"]]

    families = sorted({c["family"] for c in valid})
    status = "USE_EVIDENCE" if (explicit or meet_ev or slack_ev) else "NEED_MORE_SEARCH"
    if len(families) > 1 and len({c["author"] for c in valid}) > 1:
        status = "AMBIGUOUS"
    emit({
        "report_status": status,
        "valid_report_families": families,
        "report_candidates": cands,
        "selected_report": {k: selected[k] for k in ("doc_id", "type", "date", "link")},
        "report_versions": fam_ids,
        "author_ids": list(dict.fromkeys(authors)),
        "reviewer_evidence": {
            "explicit_fields": explicit,
            "unattributed_feedback": {d.get("id"): clip(d.get("feedback", ""), 900)
                                      for d in docs if d.get("id") in fam_ids and d.get("feedback")},
            "meetings": meet_ev,
            "slack_threads": slack_ev,
            "prs": pr_ev,
        },
        "suggested_reviewer_ids": sugg,
        "suggested_reviewer_basis": why,
        "unresolved_names": unresolved,
        "unlinked_doc_type_threads": unlinked[:10],
    })


if __name__ == "__main__":
    main()
