---
name: pcap-network-stats
description: Compute network traffic statistics from a PCAP (e.g. DAPT2020 captures) with scapy and fill a metric/value CSV - protocol counts, packets-per-minute, packet sizes, Shannon entropy of IPs/ports, directed IP graph metrics (nodes, edges, density, max in/out degree as unique IPs), inter-arrival time mean/variance/CV, producer/consumer ratio counts, 5-tuple flow counts, and true/false threat flags (port scan, DoS, beaconing, benign) using exact calibrated thresholds. Use for network_stats.csv style intrusion-detection / traffic-analysis tasks.
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Turn one packet capture into a filled metric/value statistics CSV. A single scapy script streams
  the capture, computes every standard metric with the exact conventions of the curated
  pcap-analysis helper (unique-IP degrees, IPv4-only graph, //2 bidirectional pairs, non-empty
  minute buckets) and the exact threat-detection thresholds, and rewrites only the value column.
  Template rows the script does not know are handed to the agent to compute in the same style.

trigger_when:
  - A task gives a .pcap and a metric,value CSV (e.g. /root/network_stats.csv) to fill with traffic statistics.
  - Asked for protocol counts, entropy, IP-graph, inter-arrival, producer/consumer, or flow metrics from a capture.
  - Asked whether captured traffic is benign or shows port scanning, DoS spikes, or C2 beaconing.

do_not_use_when:
  - Live packet capture or IDS rule writing (Snort/Suricata) rather than offline stats over a pcap.
  - Payload forensics (file carving, credential extraction, protocol decoding beyond L2-L4 headers).

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - scapy>=2.5

steps:
  - name: compute-stats
    kind: execution
    description: >
      Stream the pcap with scapy, compute all metrics and threat flags, and fill the CSV's value
      column in place (header and '#' comment lines untouched). Pass container paths from the task
      statement, e.g. /root/packets.pcap and /root/network_stats.csv. Takes ~10-20 s per 30 MB.
    inputs:
      - name: pcap_path
        type: string
        description: Absolute path to the capture (pcap or pcapng).
      - name: stats_csv_path
        type: string
        description: Absolute path to the metric,value CSV to fill in place (the task's output file).
    script: scripts/pcap_stats.py
    timeout: 900
    outputs:
      - name: metrics
        type: object
        description: Every computed metric name to its value (flags as booleans), same values written to the CSV.
      - name: detection_evidence
        type: object
        description: Per-flag rule, the numbers it was judged on, and the most port-diverse TCP source.
      - name: filled_metrics
        type: list[*]
        description: Template metric names whose value was written.
      - name: unknown_metrics
        type: list[*]
        description: Template metric names the script does not compute (left untouched).
      - name: template_status
        type: string
        description: complete when every template row was filled, needs_manual otherwise.
    inputs_to: check-template

  - name: check-template
    kind: router
    description: Finish if every template row was filled; otherwise compute the leftover rows by hand.
    branch_on: template_status
    branches:
      complete: end
      needs_manual: fill-unknown

  - name: fill-unknown
    kind: client_task
    description: Compute and write the template metrics the script does not know, in the same conventions.
    inputs:
      - name: pcap_path
        type: string
      - name: stats_csv_path
        type: string
      - name: metrics
        type: object
      - name: unknown_metrics
        type: list[*]
    template: assets/fill-unknown.md
    references:
      - path: references/metric-definitions.md
        description: Exact filters, formulas, rounding, and thresholds behind every scripted metric. Load to define a new metric consistently.
    outputs:
      - name: manual_values
        type: object
        description: Each previously unknown metric name mapped to the value written (null if undefinable).
    inputs_to: end

  - name: end
    kind: end
    description: The CSV at stats_csv_path is filled; metrics and detection evidence are the result.
    inputs:
      - name: stats_csv_path
        type: string
      - name: metrics
        type: object
      - name: detection_evidence
        type: object

anti_patterns:
  - Counting packets instead of unique peer IPs for max_indegree/max_outdegree; with 38 nodes the max is 37, not thousands.
  - Calling a port scan from many unique ports alone; it needs entropy > 6.0 AND SYN-only ratio > 0.7 AND > 100 ports from one source with >= 50 TCP packets.
  - Calling DoS on a 5x-15x spike; only ppm_max/ppm_avg > 20 counts.
  - Marking traffic malicious because the dataset (DAPT2020) is an attack dataset; is_traffic_benign is true exactly when all three flags are false.
  - Overriding the script's flags or numbers with your own heuristics or re-deriving them by hand; if the script fails, report the error.
  - Counting bidirectional_flows as every flow with a reverse; each A<->B pair counts once (reverse hits // 2).
  - Rewriting the CSV with csv.DictWriter (adds trailing commas to comment lines) or touching '#' lines; edit value cells only.
  - Loading the whole capture with rdpcap on large files; stream with PcapReader.
```
