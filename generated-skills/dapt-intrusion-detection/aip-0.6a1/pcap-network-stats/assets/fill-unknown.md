The script `scripts/pcap_stats.py` filled every metric it knows in `{stats_csv_path}`, but the
template also lists metric names it does not compute:

{unknown_metrics}

Metrics already computed (reuse them; do not recompute or overwrite these rows):

{metrics}

Capture: `{pcap_path}`

Do this:
1. For each unknown name, work out its definition from the task statement you were given. If the
   task does not define it, use the closest convention in `references/metric-definitions.md`
   (same packet filters, same rounding style, `true`/`false` for flags).
2. Compute it from the capture with scapy (`from scapy.all import PcapReader, IP, TCP, UDP, ICMP, ARP`),
   streaming with `PcapReader` and using `Layer in pkt` membership tests like the script does.
   Never guess or hardcode a value.
3. Edit only those rows' `value` field in `{stats_csv_path}`. Leave the header, every `#` comment
   line, and every already-filled row byte-identical.
4. Answer with `manual_values`: an object mapping each unknown metric name to the value you wrote.
   If a name is genuinely undefinable, leave its cell empty and map it to null.
