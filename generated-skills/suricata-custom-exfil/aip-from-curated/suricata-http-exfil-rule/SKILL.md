---
name: suricata-http-exfil-rule
description: Write and verify a Suricata 7 signature (e.g. sid 1000001 in /root/local.rules) that detects a custom HTTP exfiltration pattern — exact method, exact URI path, a header such as X-TLM-Mode exfil, and body parameters like a Base64 blob= of length >= 80 and a sig= of exactly 64 hex chars — using HTTP sticky buffers (http.method, http.uri, http.header, http.request_body) and PCRE. Triages training PCAPs (tshark-style request dump), composes the rule, checks syntax with suricata -T, and replays positive/negative PCAPs plus auto-generated near-miss PCAPs offline, reading alerts from eve.json. Use for Suricata DPI rule authoring, custom telemetry exfil detection, local.rules tasks, or validating a rule against pcaps.
metadata:
  aip-version: "0.5a1"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Produce one Suricata 7 alert rule that fires on a custom HTTP exfiltration request and on
  nothing else, written to the task's rules file (default /root/local.rules, sid 1000001), and
  prove it offline. A script reassembles every HTTP request in the training PCAPs so the
  conditions are grounded in where each string really lives; the agent turns the task text into
  a typed detection spec; a script composes the rule with HTTP sticky buffers and anchored PCRE,
  runs `suricata -T`, replays the labeled PCAPs and spec-derived near-miss PCAPs (one condition
  broken at a time, plus harmless variations such as header-name case, parameter order and TCP
  segmentation), and reads alerts from eve.json. Failures loop back to a spec revision.

trigger_when:
  - A task asks for a Suricata signature/rule (often in /root/local.rules with a required sid such as 1000001) that detects a custom HTTP exfil or telemetry pattern.
  - The detection combines HTTP method, URI path, a request header, and body-parameter shape (Base64-ish blob with a length bound, fixed-length hex signature).
  - You have training PCAPs (e.g. /root/pcaps/train_pos.pcap, train_neg.pcap) and need the rule to alert on positives only, verified offline with eve.json.

do_not_use_when:
  - Tuning or managing a large ruleset (ET/Snort rule updates, suricata-update), or live-capture IDS deployment.
  - The pattern is not HTTP (DNS, TLS SNI, raw TCP payload); the composer only emits HTTP sticky-buffer rules.
  - Only PCAP forensics is wanted with no rule to write.

steps:
  - name: triage-pcaps
    kind: execution
    description: Inventory suricata/tshark/jq, read the rules file, and dump every reassembled HTTP request (method, uri, headers with original case, raw body, per-parameter length and charset) from the training PCAPs.
    inputs:
      - name: task_description
        type: string
        description: The task statement describing the exfil pattern and the required sid, verbatim.
      - name: pcap_paths
        type: list[*]
        description: Training PCAP files or directories, e.g. ["/root/pcaps"] (expands *.pcap, *.pcapng, *.cap).
      - name: rules_path
        type: string
        description: Rules file to write, e.g. /root/local.rules.
      - name: suricata_config
        type: string
        description: Suricata config, e.g. /root/suricata.yaml.
    script: scripts/triage_pcaps.py
    timeout: 120
    inputs_to: define-spec

  - name: define-spec
    kind: client_task
    description: Turn the task text and the triaged requests into a typed detection_spec and label each training PCAP alert / no-alert.
    inputs:
      - name: task_description
        type: string
      - name: pcap_summaries
        type: list[*]
        description: Per-PCAP list of reassembled HTTP requests.
      - name: tools
        type: object
        description: Paths and versions of suricata, tshark, jq (null path = missing).
      - name: existing_rules
        type: string
      - name: triage_errors
        type: list[*]
    template: assets/define_spec.md
    assets:
      - assets/detection_spec_format.md
    references:
      - path: references/suricata-http-rules.md
        description: Suricata rule anatomy, HTTP sticky buffers, content/PCRE escaping, and the gotchas (legacy http_client_body modifier order, header-name case, anchoring exact lengths). Load if the task asks for a condition the spec format does not obviously express.
    inputs_to: build-and-check

  - name: build-and-check
    kind: execution
    description: Compose the single-line rule from detection_spec (or use rule_override verbatim), write it as the only rule in rules_path, run suricata -T, replay labeled and near-miss PCAPs, and report pass / fail / exhausted.
    inputs:
      - name: detection_spec
        type: object
        description: Typed conditions (sid, rev, msg, method, uri, headers, body_params, body_contains); format in assets/detection_spec_format.md.
      - name: pcap_labels
        type: object
        description: PCAP file name or path -> "alert" | "no-alert".
      - name: pcap_paths
        type: list[*]
      - name: rules_path
        type: string
      - name: suricata_config
        type: string
    script: scripts/build_and_check.py
    timeout: 900
    inputs_to: route-on-status

  - name: route-on-status
    kind: router
    description: Finish when every check passed or attempts ran out; otherwise revise the spec and re-verify.
    branch_on: status
    branches:
      pass: end
      fail: revise-spec
      exhausted: end

  - name: revise-spec
    kind: client_task
    description: Diagnose the failed checks and post a corrected detection_spec (and, only if a spec cannot express the fix, a verbatim rule_override).
    inputs:
      - name: attempt
        type: integer
      - name: failures
        type: list[*]
      - name: warnings
        type: list[*]
      - name: checks
        type: list[*]
      - name: rule_text
        type: string
      - name: detection_spec
        type: object
      - name: suricata_syntax
        type: object
    template: assets/revise_spec.md
    references:
      - path: references/suricata-http-rules.md
        description: Rule syntax, sticky buffers, escaping, and gotchas. Load when suricata -T failed or when writing a rule_override by hand.
      - path: references/offline-verification.md
        description: Manual suricata -T / -r / eve.json jq loop and tshark triage commands (follow stream, -x bytes, helper scripts). Load when a check fails only under Suricata and you need to inspect the pcap or eve.json in the reported workdir.
    inputs_to: build-and-check

  - name: end
    kind: end
    description: The rule as written to the rules file, how it was verified, and every check result. status "exhausted" means checks still fail; report the failures instead of claiming success.
    inputs:
      - name: rule_text
        type: string
      - name: rules_written
        type: string
      - name: status
        type: string
      - name: verified_with
        type: string
        description: '"suricata+emulator" when Suricata replayed the pcaps; "emulator-only" means the rule text was never executed.'
      - name: checks
        type: list[*]
      - name: failures
        type: list[*]

anti_patterns:
  - Writing `http_client_body; content:"blob=";` as if it were a sticky buffer; it is a legacy modifier that applies to the PREVIOUS content. Use `http.request_body;` (or put `http_client_body;` after the content).
  - Matching the header name case-sensitively (`content:"X-TLM-Mode|3a| exfil";` with no nocase); the traffic sends `x-tlm-mode`, so the rule never fires.
  - Using `content:"POST";` without `http.method;`, or matching the path without anchoring so `/telemetry/v2/report2` also alerts.
  - Leaving `sig=[0-9a-fA-F]{64}` or `blob=` unanchored, so 65-hex signatures, `xsig=`, or Base64 found elsewhere satisfy the rule.
  - Base64 class without `+` and `/`, or so permissive (`.{80,}`) it alerts on anything long.
  - Adding conditions the task did not state because a value appears in the sample (e.g. requiring `src=telemetry`), or hardcoding the sample's blob/sig values; the hidden traffic varies them.
  - Leaving extra rules or a second sid in the rules file; only the required sid may fire.
  - Reusing an eve.json log dir across runs, or declaring success from `suricata -T` alone without replaying positive and negative PCAPs.
  - Reporting success when verified_with is "emulator-only" without saying the rule was never run through Suricata.
```
