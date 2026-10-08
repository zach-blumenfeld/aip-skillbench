# Offline verification and PCAP triage commands

Load this when you need to debug a failing check by hand: replay one pcap, read eve.json, or look at the raw packets. scripts/build_and_check.py already runs this loop automatically and leaves every pcap and log dir under its `workdir`.

## Suricata offline + EVE JSON

```bash
# 1) Validate rule syntax (look for "rules successfully loaded, 0 rules failed")
suricata -T -c /root/suricata.yaml -S /root/local.rules

# 2) Known-positive traffic
suricata -c /root/suricata.yaml -S /root/local.rules -k none -r /root/pcaps/train_pos.pcap -l /tmp/suri-pos
jq -r 'select(.event_type=="alert") | .alert.signature_id' /tmp/suri-pos/eve.json | sort -n | uniq -c

# 3) Known-negative traffic
suricata -c /root/suricata.yaml -S /root/local.rules -k none -r /root/pcaps/train_neg.pcap -l /tmp/suri-neg
jq -r 'select(.event_type=="alert") | .alert.signature_id' /tmp/suri-neg/eve.json | sort -n | uniq -c

# ids and messages
jq -r 'select(.event_type=="alert") | [.alert.signature_id,.alert.signature] | @tsv' /tmp/suri-pos/eve.json
```

Flags: `-r <pcap>` replay offline; `-S <rules>` load only that rules file; `-l <dir>` log dir (gets `eve.json`; use a fresh dir per run so logs never mix); `-k none` ignore checksum issues. Always confirm Suricata exits cleanly with no rule parse errors. Test both positive and negative pcaps so the rule fires only on the intended traffic.

One-command summary (prints `signature_id<TAB>count`): `bash scripts/run_suricata_offline.sh <pcap> [rules_path] [log_dir]` (defaults `/root/local.rules`, `/tmp/suri`; it hides Suricata's own output, so run `suricata -T` first when it reports no eve.json).

## tshark triage

```bash
tshark -r file.pcap -Y http                                    # all HTTP
tshark -r file.pcap -Y 'http.request.method == "POST"'         # by method
tshark -r file.pcap -Y http.request -T fields -e frame.time -e ip.src -e tcp.srcport -e http.request.method -e http.request.uri
tshark -r file.pcap -z follow,tcp,ascii,0                      # whole conversation; change 0 for other streams
tshark -r file.pcap -Y http -x                                 # raw bytes for tricky parsing
```

Start broad (`-Y http`), then narrow to one flow/stream. Confirm where each string lives (headers vs body vs URL query) and note which parts are invariant and which vary between requests.

Summary across a pcap (method, uri, count of requests carrying the exfil header, header name matched case-insensitively): `bash scripts/summarize_http_requests.sh /root/pcaps/train_pos.pcap`.

Without tshark, `python3 scripts/triage_pcaps.py` (stdin `{"currentState": {"pcap_paths": ["/root/pcaps"]}}`) dumps every reassembled request as JSON.
