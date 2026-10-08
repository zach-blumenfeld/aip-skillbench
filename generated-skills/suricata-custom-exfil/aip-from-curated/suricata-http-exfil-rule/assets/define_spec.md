# Define the detection spec for the Suricata rule

Task statement:

{task_description}

Tools found on this host: {tools}
Current rules file content: {existing_rules}
Triage errors (fix the inputs and rerun if a pcap you need is missing): {triage_errors}

Every HTTP request reassembled from the training pcaps (method, uri, headers in wire order and case, raw body, and per-parameter length/charset):

{pcap_summaries}

Do this:

1. List every condition the task statement imposes (method, path, header name and value, each body parameter with its alphabet and length bound, the sid). Conditions come from the task text. The pcaps show where each string lives (request line vs header vs body vs URI query) and its real format. They do not add conditions: a value the positive and negative pcaps share (e.g. `src=telemetry`, `pad=000`, `v=2`) is not a condition unless the task says so.
2. Compare the positive and negative pcaps. The field that differs between them must be one of your conditions. If the task text and the pcaps disagree, follow the task text.
3. Write `detection_spec` in the format below. Be exactly as strict as the task: "exact path" means `exact_path`, "exactly N hex" means `exact_len`, "length >= N" means `min_len`. Header names are always matched case-insensitively.
4. Label each training pcap in `pcap_labels`: key = pcap file name (e.g. `train_pos.pcap`) or full path, value = `"alert"` or `"no-alert"`. Use the file name (`pos`/`neg`, `benign`, `exfil`) and the task text; every pcap that should not fire is `"no-alert"`.

{assets[detection_spec_format]}

Output JSON with `detection_spec` (object) and `pcap_labels` (object). The other keys the next step expects (`pcap_paths`, `rules_path`, `suricata_config`) are already in the state; do not resend them.
