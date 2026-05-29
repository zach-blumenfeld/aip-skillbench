---
name: suricata-offline-evejson
description: Run Suricata against PCAPs offline and validate results via eve.json. Use when iterating on Suricata signatures (e.g. /root/local.rules), replaying a PCAP with -r, checking sid syntax with `suricata -T`, or counting and inspecting alerts in eve.json with jq. Covers the tight positive/negative pcap feedback loop used to author and tune custom rules.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires the `suricata` binary and `jq` on PATH. Assumes a Suricata config at /root/suricata.yaml and a rules file at /root/local.rules unless overridden.
---

```yaml
purpose: >
  Run Suricata against PCAPs in offline replay mode and validate the resulting
  alerts via eve.json. Covers the syntax-check / positive-pcap / negative-pcap
  feedback loop used when authoring or tuning a custom rule (for example a new
  sid in /root/local.rules) so the agent can quickly see whether the rule fires
  on intended traffic and stays silent on benign traffic.

trigger_when:
  - Authoring or editing a Suricata rule in /root/local.rules (or any rules file) and needing to know whether it fires.
  - Replaying a PCAP through Suricata with `-r` for analysis or signature testing.
  - User asks to count, list, or inspect Suricata alerts from eve.json.
  - Iterating to remove false positives or false negatives on a known-positive vs known-negative PCAP pair.
  - Validating Suricata rule syntax before a run (`suricata -T`).

do_not_use_when:
  - Running Suricata live on an interface (this skill is offline / PCAP-replay only).
  - The task is about parsing eve.json events other than alerts (flow, http, dns, tls records) — the jq filters here are alert-scoped.

scope_and_approval: >
  Read-only against the supplied PCAPs and config. The skill writes only to a
  log directory the caller specifies (default /tmp/suri*) and may delete that
  directory before each run to avoid mixing logs. It does NOT edit rules
  files; the agent edits /root/local.rules itself between iterations.

steps:
  - name: validate-rules
    description: Run `suricata -T -c <config> -S <rules>` to catch rule parse errors before replaying a PCAP. Bail out of the loop on non-zero exit; the run-on-pcap steps would fail noisily otherwise.
    outputs:
      - name: syntax-ok
        type: boolean
        description: True iff Suricata's rule parser accepted the file.

  - name: run-on-pcap
    description: Replay one PCAP through Suricata offline and emit eve.json into a fresh log dir. Source of truth for the invocation is the script; see Practical Tips below for the flag glossary.
    script: scripts/run_suricata_offline.sh
    depends_on:
      - validate-rules
    inputs:
      - name: pcap-path
        type: string
        description: Absolute path to the PCAP to replay.
      - name: rules-path
        type: string
        nullable: true
        description: Path to the rules file. Defaults to /root/local.rules.
      - name: log-dir
        type: string
        nullable: true
        description: Directory Suricata writes eve.json into. Defaults to /tmp/suri. Wiped before the run.
    outputs:
      - name: eve-json-path
        type: string
        description: Path to eve.json inside the log dir.
      - name: sid-counts
        type: object
        description: Map of signature_id -> alert count, printed to stdout.

  - name: run-on-positive
    description: Replay the known-positive PCAP. Expectation is that the target sid (e.g. 1000001) fires at least once.
    depends_on:
      - validate-rules
    inputs:
      - name: pos-pcap-path
        type: string
    outputs:
      - name: pos-sid-counts
        type: object

  - name: run-on-negative
    description: Replay the known-negative PCAP. Expectation is that the target sid does NOT fire (zero false positives on benign traffic).
    depends_on:
      - validate-rules
    inputs:
      - name: neg-pcap-path
        type: string
    outputs:
      - name: neg-sid-counts
        type: object

  - name: inspect-alerts
    description: >
      Query eve.json with jq to count alerts and list signature_id + signature
      text. Standard one-liners:
        Count alerts:
          jq -r 'select(.event_type=="alert") | .alert.signature_id' <log_dir>/eve.json | wc -l
        List sid + message:
          jq -r 'select(.event_type=="alert") | [.alert.signature_id,.alert.signature] | @tsv' <log_dir>/eve.json
        sid -> count histogram:
          jq -r 'select(.event_type=="alert") | .alert.signature_id' <log_dir>/eve.json | sort -n | uniq -c
    inputs:
      - name: eve-json-path
        type: string
    outputs:
      - name: alerts-table
        type: list[object]
        description: Rows of {sid, signature, count} as printed to stdout.

  - name: iterate-on-rule
    description: >
      One-command tight feedback loop. Runs validate-rules + run-on-positive +
      run-on-negative and prints sid -> count for both. Use after every edit to
      the rules file. Source of truth is the script; exit codes 3/4/5 surface
      syntax failures and missing eve.json so the agent can react.
    script: scripts/feedback_loop.sh
    depends_on:
      - validate-rules
    inputs:
      - name: pos-pcap-path
        type: string
      - name: neg-pcap-path
        type: string
      - name: rules-path
        type: string
        nullable: true
      - name: config-path
        type: string
        nullable: true
      - name: log-root
        type: string
        nullable: true
        description: Parent dir for suri-pos/ and suri-neg/ log directories. Defaults to /tmp.
    outputs:
      - name: pos-sid-counts
        type: object
      - name: neg-sid-counts
        type: object

modes:
  - name: one-command
    body: >
      Single-shot iteration via scripts/feedback_loop.sh. Validates rule syntax,
      replays the positive PCAP, replays the negative PCAP, and prints sid -> count
      for both. Preferred while iterating on a rule.
  - name: per-pcap
    body: >
      Run scripts/run_suricata_offline.sh against a single PCAP with a custom log
      dir. Use when investigating one PCAP in isolation, or when there is no
      negative PCAP yet.

scenarios:
  - need: Typical offline invocation flags glossary.
    action: >
      suricata -c /root/suricata.yaml -S /root/local.rules -k none -r /root/sample.pcap -l /tmp/suri
      Flags: -r <pcap> replay a PCAP offline; -S <rules> load only that rules file;
      -l <dir> log directory (will contain eve.json); -k none ignore checksum issues.
    outcome: eve.json lands in /tmp/suri/eve.json for jq inspection.

  - need: Quick count of total alerts emitted on a PCAP.
    action: |
      jq -r 'select(.event_type=="alert") | .alert.signature_id' /tmp/suri/eve.json | wc -l
    outcome: Single integer count of alert events.

  - need: List every alert's sid and signature text.
    action: |
      jq -r 'select(.event_type=="alert") | [.alert.signature_id,.alert.signature] | @tsv' /tmp/suri/eve.json
    outcome: TSV table of (sid, signature) — one row per alert event.

  - need: Iterating a new rule with positive and negative training PCAPs.
    context: >
      User has /root/pcaps/train_pos.pcap and /root/pcaps/train_neg.pcap and is
      editing /root/local.rules to make sid 1000001 fire only on the positive.
    action: >
      After each rules edit, run scripts/feedback_loop.sh
      /root/pcaps/train_pos.pcap /root/pcaps/train_neg.pcap. Stop when the positive
      shows sid 1000001 at the expected count and the negative shows zero.
    outcome: "Rule converges: fires on positive, silent on negative, syntax-clean."

anti_patterns:
  - Editing rules without first running `suricata -T` — silently broken rules produce no alerts and look like a false-negative bug.
  - Reusing the same `-l` log directory across runs, mixing eve.json events from old and new rules.
  - Testing on positive-only traffic and shipping a rule with no negative-PCAP check — high false-positive risk.
  - Skipping `-k none` on PCAPs with bad checksums; Suricata silently drops the offending packets and the rule appears not to fire.
  - Editing rules in any file other than the one passed via `-S` and wondering why nothing changes.
```
