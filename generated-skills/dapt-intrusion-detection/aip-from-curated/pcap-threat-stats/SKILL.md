---
name: pcap-threat-stats
description: Compute network statistics from a PCAP packet capture (protocol counts, packets per minute, packet sizes, port/IP Shannon entropy, graph topology and degree, inter-arrival time, producer/consumer, flows), fill a metric,value stats CSV, and decide port scan, DoS, C2 beaconing and benign verdicts with exact calibrated thresholds. Use for pcap/scapy traffic analysis, intrusion detection, network_stats.csv templates, or threat-pattern questions about a capture.
metadata:
  aip-version: "0.5a1"
  compiled-from: "pcap-analysis, threat-detection"
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
  Analyze one network packet capture end to end. A single streaming scapy pass computes
  the full metric set: protocol distribution, time series, packet sizes, entropy, graph
  topology, temporal, producer/consumer, and flows. It applies the exact threat-detection
  thresholds (port scan, DoS, beaconing, benign) and fills the metric,value stats CSV in
  place. The metric definitions and calibrated thresholds come from tested helpers.
  Deviating from them, for example by counting packets instead of unique IPs for degree,
  using a single-signal port-scan rule, or using a lower DoS ratio, produces wrong answers.
  A decision then checks whether the task needs anything beyond the filled CSV. If so,
  the agent completes it with the same definitions.

trigger_when:
  - A task gives a .pcap/.pcapng file and asks for network statistics, metrics, or a filled stats CSV (e.g. /root/packets.pcap with /root/network_stats.csv).
  - A task asks whether captured traffic is benign or shows port scanning, DoS, or C2 beaconing.
  - Computing entropy, degree/density, inter-arrival-time, flow, or producer/consumer metrics from packets with scapy.

do_not_use_when:
  - Live packet capture or sniffing is required rather than analysis of a saved capture.
  - The input is flow logs (NetFlow/Zeek/firewall CSV) rather than raw packets.
  - Deep payload or protocol forensics (file carving, TLS decryption, malware reversing) is the goal.

steps:
  - name: analyze-capture
    kind: execution
    description: >
      Stream the capture once with scapy and compute every metric plus the port-scan, DoS,
      beaconing, and benign verdicts. Mirrors scripts/pcap_utils.py exactly. Fill stats_csv
      in place, keeping its header and '#' comment rows, and report the template rows it
      did not recognize. It needs a python with scapy importable; the task container's python3 ships scapy 2.5.0. It
      takes about 10 s per 100k packets.
    inputs:
      - name: pcap_path
        type: string
        description: Absolute path to the capture, e.g. /root/packets.pcap. Classic pcap and pcapng are both read.
      - name: stats_csv
        type: string
        description: metric,value CSV to fill in place, e.g. /root/network_stats.csv. If it is missing, it is created from assets/network_stats_template.csv.
      - name: task_request
        type: string
        description: The task's instructions verbatim, so the scope check can see what else is asked.
    script: scripts/analyze_pcap.py
    assets:
      - assets/network_stats_template.csv
    timeout: 1800
    inputs_to: scope-check

  - name: scope-check
    kind: decision
    description: Decide whether the task needs anything beyond the CSV the script already filled.
    inputs:
      - name: task_request
        type: string
      - name: unfilled_metrics
        type: list[*]
        description: Template metric rows the script left empty.
      - name: csv_written
        type: string
    questions:
      extra_work_needed:
        type: noul
        instructions: >
          Does the task still require output the script did not produce? Answer yes if
          unfilled_metrics is non-empty, or if the task asks for any of the following:
          another output file or format, prose answers or an explanation, or a metric or
          question not in the CSV. Answer no when the task only asks to fill the stats CSV
          and unfilled_metrics is empty. A request to "decide" or "determine" whether
          traffic is benign or shows a port scan, DoS, or beaconing counts as covered by
          the CSV's true/false rows. It is not a prose request unless the task explicitly
          asks for a written answer, explanation, or report.
        criteria:
          true: Unfilled rows remain, or the task asks for additional files, answers, or explanations.
          false: All requested values are already in the filled CSV.
    thresholds:
      extra_work_needed: 0.3
    inputs_to: by-scope

  - name: by-scope
    kind: router
    description: Finish now if the CSV covers the task; otherwise complete the remaining outputs.
    branch_on: extra_work_needed
    branches:
      "true": complete-outputs
      "false": end

  - name: complete-outputs
    kind: client_task
    description: Compute any unfilled rows and produce any extra outputs, keeping the exact definitions and thresholds.
    inputs:
      - name: pcap_path
        type: string
      - name: csv_written
        type: string
      - name: task_request
        type: string
      - name: unfilled_metrics
        type: list[*]
      - name: metrics
        type: object
      - name: detection_signals
        type: object
    template: assets/complete-outputs.md
    references:
      - path: references/metric-definitions.md
        description: >
          Exact definition, layer rule, and rounding for every metric. Also the threat
          threshold table with worked examples, how to import scripts/pcap_utils.py, and
          CSV conventions. Load it before computing any metric the script did not fill or
          answering a threat question in prose.
    inputs_to: end

  - name: end
    kind: end
    description: The filled stats CSV on disk plus every computed metric and verdict.
    inputs:
      - name: metrics
        type: object
        description: All metrics, including has_port_scan, has_dos_pattern, has_beaconing, and is_traffic_benign.
      - name: csv_written
        type: string
        description: Absolute path of the filled metric,value CSV.

anti_patterns:
  - Counting packets instead of UNIQUE peer IPs for max_indegree/max_outdegree. With n nodes, a degree can never exceed n-1.
  - Flagging a port scan on one signal, such as many unique ports. Entropy > 6.0 AND SYN-only ratio > 0.7 AND unique ports > 100 must all hold for a single source with at least 50 TCP packets.
  - Calling a 5x, 10x, or 15x packets-per-minute spike a DoS. Only max/avg > 20 counts.
  - Reporting traffic as benign when any detector fired, or as malicious when all three are false.
  - Counting flows from packets that lack an IPv4 layer, or counting each bidirectional pair twice instead of halving.
  - Replacing the script's values with your own re-implementation using different thresholds, rounding, or layer rules.
  - Dropping the CSV's '#' comment rows or header, or writing booleans as anything other than lowercase true/false.
  - Loading a large capture with rdpcap when memory is tight. Stream it with PcapReader instead.
```
