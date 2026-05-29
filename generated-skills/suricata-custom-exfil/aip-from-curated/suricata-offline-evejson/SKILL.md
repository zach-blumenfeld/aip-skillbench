---
name: suricata-offline-evejson
description: Drive Suricata in offline (PCAP replay) mode and read alerts back from eve.json to iterate on a candidate rule. Use when a Suricata rules file is being authored or refined against fixed positive/negative PCAP fixtures — e.g., the `suricata-custom-exfil` task family — or when answering "did sid N fire on this PCAP?". Covers the standard offline invocation (`suricata -c ... -S ... -k none -r ... -l ...`), syntax pre-flight (`suricata -T`), eve.json schema for alerts, jq recipes for counting by signature_id, and the positive-then-negative feedback loop that distinguishes under-matching from over-matching rules.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Run Suricata against PCAP fixtures offline and validate a candidate
  rule by reading alerts back from eve.json. Wraps the full iteration
  loop the agent uses while authoring a rule: pre-flight the rules file
  with `suricata -T`, replay positive traffic and confirm the target sid
  fired, replay negative traffic and confirm the target sid stayed
  silent, then interpret the per-sid alert counts to decide whether the
  rule under-matches (positive silent) or over-matches (negative fires).

trigger_when:
  - Iterating on a Suricata rule against fixed PCAP fixtures (positive + negative).
  - Working the `suricata-custom-exfil` task family or any task where rule correctness is judged by alerts on canned PCAPs.
  - Answering "did sid N fire on this PCAP?" or "which sids fired?".
  - Verifying a freshly-authored rule does not silently fail to load.
  - Reading or filtering Suricata `eve.json` for alert events.

do_not_use_when:
  - Running Suricata in live-interface mode (different flags, no PCAP replay, runtime concerns this skill does not cover).
  - Authoring the content of the rule itself — see `suricata-rules-basics` for sticky buffers, content vs pcre, and Base64/hex body patterns.
  - Doing raw packet triage beyond what `eve.json` surfaces (TCP-stream reassembly, decoding non-HTTP protocols) — see `pcap-triage-tshark`.

scope_and_approval: >
  Read-only against the PCAP fixtures, `suricata.yaml`, and the rules
  file under test. Writes a fresh log directory under `/tmp/` per run
  (the scripts `rm -rf` it first to avoid cross-run alert mixing) and
  prints summaries to stdout. Does not modify the rules file,
  `suricata.yaml`, or the PCAPs.

steps:
  - name: locate-fixtures
    description: >
      Confirm the paths for the rules file, config, positive PCAP, and
      negative PCAP. In the suricata-custom-exfil task family these are
      `/root/local.rules`, `/root/suricata.yaml`,
      `/root/pcaps/train_pos.pcap`, and `/root/pcaps/train_neg.pcap`.
      In a different environment, list the relevant directory and pick
      the PCAPs whose names (or accompanying notes) identify them as
      known-positive vs known-negative. Note the target sid the task
      requires (e.g., 1000001 for suricata-custom-exfil).
    outputs:
      - name: fixtures
        type: object
        description: '{rules_path, config_path, pos_pcap, neg_pcap, target_sid}'

  - name: validate-rule-syntax
    description: >
      Pre-flight the rules file with `suricata -T`. Catches parse errors
      cheaply before any PCAP runs — a silently-broken rule will produce
      an empty (or no) `eve.json` and look identical to an
      under-matching rule, wasting iteration time. Forwards Suricata's
      stderr so the agent sees the line number of any parse error.
    script: scripts/validate_syntax.sh
    inputs:
      - name: rules_path
        type: string
      - name: config_path
        type: string
    outputs:
      - name: syntax_ok
        type: boolean
      - name: parser_output
        type: string

  - name: run-tight-loop
    description: >
      One-shot positive/negative feedback loop. Runs `suricata -T`,
      replays the positive PCAP into a fresh log dir, replays the
      negative PCAP into a second fresh log dir, then summarises per-sid
      alert counts for each and emits a PASS/FAIL verdict against the
      target sid (positive must fire ≥1, negative must fire 0). Use
      this as the default iteration command — the per-PCAP `run-on-pcap`
      step below is for ad-hoc inspection.
    script: scripts/tight_loop.sh
    inputs:
      - name: target_sid
        type: integer
      - name: rules_path
        type: string
      - name: pos_pcap
        type: string
      - name: neg_pcap
        type: string
      - name: config_path
        type: string
    outputs:
      - name: verdict
        type: string
        description: PASS, FAIL-undermatch, or FAIL-overmatch.
      - name: pos_counts
        type: list[object]
        description: Per-sid alert counts on the positive PCAP.
      - name: neg_counts
        type: list[object]
        description: Per-sid alert counts on the negative PCAP.

  - name: run-on-pcap
    description: >
      Ad-hoc single-PCAP run. Same invocation pattern as `run-tight-loop`
      but against one PCAP at a time — useful for inspecting an
      unfamiliar PCAP, or when triaging a single failing case. Always
      writes to a fresh log dir to avoid mixing alerts across runs.
    script: scripts/run_suricata_offline.sh
    inputs:
      - name: pcap_path
        type: string
      - name: rules_path
        type: string
      - name: log_dir
        type: string
    outputs:
      - name: alerts_by_sid
        type: list[object]
      - name: eve_path
        type: string

  - name: interpret-and-iterate
    description: >
      Read the verdict and per-sid counts. Decide which way the rule is
      wrong and what to change before re-running:
        * Positive PCAP silent on target sid → under-matching. Loosen
          the most specific constraint first (e.g., regex length
          bounds, header case sensitivity); confirm the rule actually
          loaded by re-reading the syntax-check output.
        * Negative PCAP fires target sid → over-matching. Identify
          which detection criterion from the task brief the negative
          traffic violates and tighten the rule to enforce it.
        * Both PCAPs silent → rule did not load, or the sticky buffer
          is wrong (you matched bytes in the wrong buffer). Re-read
          `suricata -T` output and reconsider the buffer choice.
        * Extra unrelated sids firing → another rules file is being
          loaded via `suricata.yaml`'s `rule-files:`; check the config.
      For deeper inspection — e.g., reading the actual request body
      bytes that Suricata saw — load
      `references/eve-json.md` for jq recipes against
      `http.http_request_body_printable` and related fields. Then edit
      the rule and loop back to `validate-rule-syntax`.
    inputs:
      - name: verdict
        type: string
      - name: pos_counts
        type: list[object]
      - name: neg_counts
        type: list[object]
    outputs:
      - name: next_action
        type: string

anti_patterns:
  - Skipping `suricata -T` and going straight to PCAP runs — a parse error looks identical to an under-matching rule in the alert counts and burns iteration time.
  - Re-using the same `-l` log directory across runs — Suricata appends to `eve.json`, so per-sid counts mix old and new revisions and lie about the current rule.
  - Only running the positive PCAP — without the negative run, an over-matching rule that alerts on everything passes the positive check and looks correct.
  - Judging success by alert *count* or `msg:` rather than `signature_id` — sid is the task contract; `msg:` is for humans.
  - Reading `fast.log` instead of `eve.json` — `fast.log` lacks the structured fields needed to confirm which traffic an alert fired on.
  - Editing the rule between the positive and negative runs — you no longer know which rule revision produced which set of alerts.
  - Treating "no eve.json produced" as "no alerts" — it almost always means Suricata refused to load the rule. Re-check `suricata -T`.
  - Ignoring stderr from Suricata when scripts swallow it — the included scripts surface parse errors on stderr; do not redirect them away when adapting the commands.
```
