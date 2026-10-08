The PCAP metrics script for {meta.name} has already run on `{pcap_path}` and filled `{csv_written}`. Your job is to finish whatever the task still needs.

Task request:
{task_request}

Template rows the script could not fill (empty means all rows were filled):
{unfilled_metrics}

Computed metrics (authoritative; do not recompute or override these values):
{metrics}

Detection evidence:
{detection_signals}

Do this:
1. For each unfilled row, work out what it means from its name, its CSV section comment, and the task request. Compute it from the capture with the curated helpers in `scripts/pcap_utils.py`, or by streaming the file with scapy's `PcapReader`. Follow the conventions in the metric-definitions reference: IPv4-only graphs, ports from all TCP plus UDP-with-IPv4, population variance, 1-minute buckets measured from the first packet, and booleans written as `true` or `false`. Then write the value into its row of `{csv_written}`. Leave every other row unchanged.
2. Produce any other output the task asks for: answers to questions, another file, or an explanation. Base it on the metrics above. Threat verdicts must use the exact thresholds: port scan needs entropy > 6.0 AND SYN-only ratio > 0.7 AND unique ports > 100 from one source with at least 50 TCP packets; DoS needs a max/avg packets-per-minute ratio > 20; beaconing needs IAT CV < 0.5; traffic is benign only when all three are false. Never loosen these thresholds based on your own intuition.
3. Re-read `{csv_written}` and confirm it still has its header, its comment rows, and a value in every metric row.

Return a JSON object with two keys: `extra_outputs`, an object mapping each metric or artifact you added to its value or path, and `summary`, one paragraph giving the key metrics, the three threat verdicts with the numbers that decided them, and what you added. Do not send back `metrics` or `csv_written`: they are already in the state and carry through to the end step unchanged. Correct `metrics` only if you find a genuine script error, and then explain why in `summary`.
