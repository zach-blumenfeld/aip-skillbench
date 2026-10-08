# suricata-http-exfil-rule — source and compilation notes

## Provenance

Compiled 2026-10-08 from three curated Agent Skills describing one workflow (triage the PCAPs → write a Suricata HTTP rule → verify it offline via eve.json) and from the task environment they were written for. Copied here verbatim:

| Path | What it is |
|---|---|
| `pcap-triage-tshark/SKILL.md`, `scripts/summarize_http_requests.sh` | tshark filters, field extraction, follow-stream, `-x` bytes, triage tips, helper script |
| `suricata-offline-evejson/SKILL.md`, `scripts/run_suricata_offline.sh` | offline `suricata -r` invocation, flags, eve.json jq queries, `-T` → pos → neg feedback loop, helper script |
| `suricata-rules-basics/SKILL.md` | rule anatomy, content/PCRE, HTTP sticky buffers, the `suricata-custom-exfil` task scaffold, focused examples, failure modes |
| `environment/` (Dockerfile, suricata.yaml, local.rules, MANIFEST.md, generate_training_pcaps.py) | the task container: Suricata 7.0.11 (jasonish/suricata), python3 (3.9 on the EL9 base) + python3-scapy, jq, wireshark-cli (tshark), uv; `/root/local.rules`, `/root/suricata.yaml`, `/root/pcaps/train_{pos,neg}.pcap` |

The environment tells us facts the skills did not: the header is sent as lowercase `x-tlm-mode` (a case-sensitive `X-TLM-Mode` match never fires), the Base64 blob deliberately contains `+` and `/`, the body carries extra parameters (`v=`, `src=`, `pad=`), the HTTP request is split over three TCP segments on port 8080, and pos/neg pcaps differ only in the header value (`exfil` vs `normal`). Note: the Dockerfile copies the image's stock `/etc/suricata/suricata.yaml` to `/root/suricata.yaml`; the minimal `environment/suricata.yaml` (HOME_NET any, eve alert output) is not what the container uses, so the rule uses `any any -> any any` and does not rely on address variables.

## Procedure graph and step-kind choices

```
triage-pcaps (execution) → define-spec (client_task) → build-and-check (execution) → route-on-status (router)
    pass → end | exhausted → end | fail → revise-spec (client_task) → build-and-check
```

- **triage-pcaps — execution.** Dumping the HTTP requests is deterministic. Implemented as a stdlib-only pcap/pcapng reader with TCP reassembly and HTTP parsing (`scripts/pcaplib.py`) instead of shelling out to tshark, so it works on any host and gives per-parameter length/charset summaries tshark does not. Also records which of suricata/tshark/jq exist and the current rules file.
- **define-spec — client_task.** Turning a free-text task statement into conditions is interpretation the agent must generate; the output is a typed `detection_spec` (format in `assets/detection_spec_format.md`) plus pcap labels, so everything downstream is mechanical. Not a decision: the answer space (names, values, lengths) is open.
- **build-and-check — execution.** Rule composition (escaping, sticky buffers, anchoring), writing the rules file, `suricata -T`, replaying pcaps, and reading eve.json are all deterministic and are exactly where the source's "common failure modes" live, so they are scripted. The script also synthesizes spec-derived near-miss pcaps (one condition broken at a time → must not alert; header-name case, param order, query string, TCP segmentation, boundary lengths → must alert). This mechanizes the source's "test positive and negative PCAPs" and "avoid overly generic / too strict" advice without hardcoding any sample values. A pure-Python emulator of the spec runs alongside Suricata; when Suricata is missing it is the only judge and `verified_with` says `emulator-only`.
- **route-on-status — router** on the script's `status` (`pass` / `fail` / `exhausted` after 4 attempts) so the loop cannot run forever.
- **revise-spec — client_task.** Diagnosing a failed check and choosing a fix is reasoning; it posts a corrected spec, or a verbatim `rule_override` when the spec format cannot express the fix (keeps the agent's full freedom; the override is still verified by the same checks).
- **No decision step.** The only judgments (which conditions the task imposes, which pcap should alert) have open answer spaces and are captured as typed fields of the spec; pos/neg labels are a fixed choice but come in the same breath as the spec, and a mislabel is caught by the emulator-vs-label check.

## Adaptations of source content

- The source scaffold uses `http_client_body;` before `content:` as if it were a sticky buffer. In Suricata it is a legacy content modifier applying to the previous content; the pack uses the `http.request_body` sticky buffer and records the trap as an anti-pattern and a reference gotcha.
- The source PCRE `[A-Za-z0-9+\\/]` written into a rules file adds a literal backslash to the class; the pack emits `\x2f`.
- The source's unanchored `sig=[0-9a-fA-F]{64}` also matches 65+ hex characters, and `blob=` unanchored matches `xblob=`; the composer anchors both on `(?:^|&)` … `(?:&|$)`.
- The source header example `content:"X-TLM-Mode|3a| exfil";` is case-sensitive while the traffic sends `x-tlm-mode`; the composer matches the header name case-insensitively and keeps the value case-sensitive (configurable via `value_nocase`).
- `scripts/summarize_http_requests.sh` is copied with one change: its header count used a case-sensitive `contains "X-TLM-Mode: exfil"` that counts 0 on the real pcaps; it now uses `matches "(?i)x-tlm-mode:[ \\t]*exfil"`. `scripts/run_suricata_offline.sh` is copied unchanged.
- "Exact path" is implemented as `content … startswith` + PCRE `^path(?:\?|$)` so `/telemetry/v2/report2` and `/x/telemetry/v2/report` do not match while a query string is tolerated (`uri.match: exact` forbids it).

## Completeness check (source item → where it lives)

pcap-triage-tshark: quick filters, field extraction, follow stream + stream index, `-x` bytes → `references/offline-verification.md`; "start broad, confirm where strings live, invariant vs variable" → reference + `assets/define_spec.md` steps 1–2 + triage script output (headers/body/URI per request); helper script → `scripts/summarize_http_requests.sh` (fixed) and `scripts/triage_pcaps.py`.

suricata-offline-evejson: invocation and flags (`-r -S -l -k none`) → `build_and_check.py` + reference; jq count / ids+messages → reference, eve.json parsing in script; "exits cleanly", "fresh -l dir per run", "test positive and negative" → script (`-T` gate, `mkdtemp` per run, labeled + mutation pcaps) + anti-patterns; tight feedback loop → script loop + reference; helper script → `scripts/run_suricata_offline.sh`.

suricata-rules-basics: anatomy, sid/rev, flow → composer + `references/suricata-http-rules.md`; content + modifiers, PCRE examples → composer + reference; sticky buffer list → reference (with the http_client_body correction); tips (strict method/path/header then body, avoid generic, readable + specific msg) → composer order, spec format `msg` rule, anti-patterns; task scaffold and its five conditions (method, exact path, header, blob Base64 ≥ 80, sig exactly 64 hex) → spec format example, define-spec template, reference scaffold; focused examples incl. `|3a|` tip, strict Base64 class, anchoring on `blob=` → composer escaping + reference; four common failure modes → anti-patterns + near-miss mutations (`hdr-*-only-in-body`, `wrong-method-GET`, `param-*-len-*`, `param-*-bad-char`).

environment: lowercase header, `+/` in blob, extra params, three-segment split, port 8080 → spec format notes, anti-patterns, mutations (`hdr-*-name-lower/upper`, `params-reversed`, `single-/many-segments`); container packages → scripts are python3.9-compatible stdlib only.

## Deliberate drops

- "This skill intentionally does **not** provide a full working rule. You should build the final rule by combining the conditions from the task." — dropped as an instruction: the pack's purpose is to produce and verify the rule, and it composes it from conditions the agent extracts from the task text (no sample values are hardcoded). The reference keeps a scaffold for hand edits.
- Intro sentences of each source SKILL.md ("This skill shows/covers …") — descriptive, not actionable; covered by `purpose` and `description`.
- tshark as the primary triage tool — kept as manual commands in the reference; the automated triage uses the stdlib parser because it needs no external binary and emits structured JSON.

## Functional test (2026-10-08, local `aip run`)

Inputs: `scratch/start.json` with pcaps produced by the environment's own `generate_training_pcaps.py` (run with scapy in a scratch venv). Suricata is not installed on the authoring host, so:
1. `aip run` → define-spec answered with a deliberately wrong Base64 class (`A-Za-z0-9`) → build-and-check `fail` (spec disagrees with the positive label) → revise-spec → corrected spec → `pass`, 32/32 checks, `verified_with: emulator-only`.
2. Same flow with a test-only `suricata` shim (Python regex over approximate HTTP buffers) on PATH → `pass`, `verified_with: suricata+emulator`, 32/32; a loose `rule_override` (body `sig=` only) failed 18 checks including train_neg; a syntactically broken override failed at `-T`; starting at attempt 3 with a wrong spec ended `exhausted`.
3. Parser checked on a pcapng with two sessions, chunked body, uppercase header name and padded Base64.
The composed rule has not been executed by a real Suricata 7 on this host; in the task container build-and-check runs it for real.
4. Two fresh agents ran the pack via `aip run` with the shim: the stock task (sid 1000001) and a variant (sid 2000042, PUT `/api/v1/upload`, `X-Exfil-Channel: on`, base64url `data` ≥ 100, `mac` exactly 40 hex). Both reached `end` with `pass`, 32/32, no script errors, no `rule_override` needed. Their feedback led to: clearer define-spec output-key wording, "task text wins" for the sid, `allow_padding` guidance for base64url, and `suricata_version` in the build-and-check output so a shim and the real binary can be told apart.
