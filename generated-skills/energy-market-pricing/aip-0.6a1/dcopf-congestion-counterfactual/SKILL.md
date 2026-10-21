---
name: dcopf-congestion-counterfactual
description: Counterfactual transmission-congestion analysis for electricity markets. Clears a DC-OPF with spinning-reserve co-optimization on a MATPOWER/PGLib network.json twice (base vs one line thermal limit raised by X%) and writes report.json with total cost, LMPs per bus, reserve clearing price (MCP), binding lines, cost reduction, largest LMP drops and congestion relief. Use for RTO/ISO day-ahead price-spike, LMP, shadow-price or "what if we relax this line" questions.
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
  "What if we relax this line?" analysis for a day-ahead electricity market. Clear a
  DC-OPF with spinning-reserve co-optimization twice from a MATPOWER network JSON: the
  base case, and a counterfactual where one transmission line's thermal limit (RATE_A)
  is raised by a percentage. Report total cost, the LMP at every bus, the reserve
  clearing price, binding lines (loading >= 99%), the cost reduction, the three buses
  with the largest LMP drop, and whether the relaxed line stops binding. Results go to
  report.json. Everything is computed from the given file; nothing is hardcoded.

trigger_when:
  - Asked to compare base vs counterfactual market clearing after increasing a transmission line's capacity or thermal limit.
  - Asked for LMPs, reserve market clearing price, binding lines, or congestion impact from a DC-OPF with reserves on a MATPOWER / PGLib-OPF network.json.
  - An RTO / ISO market analyst investigates a price spike suspected to come from one congested line.

do_not_use_when:
  - The task needs AC power flow, losses, voltage or reactive-power results.
  - Multi-period / unit-commitment problems (startup costs, ramping, time series).
  - Plain economic dispatch with no network (the script always enforces line limits).

requires:
  interpreter:
    name: python
    version: "3.10"

steps:
  - name: clear-markets
    kind: execution
    description: >
      Solve the base and counterfactual DC-OPF + reserve markets with cvxpy/CLARABEL and
      compute every report field (about 5 s on 2,900 buses). The script is stdlib-only
      at entry. If numpy/scipy/cvxpy/clarabel are missing (the task container has bare
      python3), it creates a venv at $DCOPF_CF_VENV (default
      ~/.cache/dcopf-congestion-counterfactual/venv), pip-installs them (the first run
      needs PyPI access, ~1 min) and re-runs itself there. In the container, launch it
      with `python3`. The model and its gotchas, all handled in the script: bus numbers
      mapped (never bus-1); b = 1/X; TAP/SHIFT ignored; out-of-service gens/branches
      dropped; RATE_A = 0 is unlimited; slack θ = 0; Pg + Rg <= PMAX, Rg <=
      reserve_capacity, ΣRg >= reserve_requirement. LMP = −dual of the MW nodal balance:
      the source's `dual * baseMVA` is wrong by a factor of −10⁴, and a +/-1 MW re-solve
      verifies the sign and scale every run. Negative or large LMPs are valid under
      congestion. The target line's limit is scaled for every in-service circuit
      between the two buses in either orientation.
    inputs:
      - name: network_path
        type: string
        description: Path to the MATPOWER-format network JSON (in the task container, /root/network.json).
      - name: line_from_bus
        type: integer
        description: One end bus number of the line to relax, as named in the task (e.g. 64).
      - name: line_to_bus
        type: integer
        description: The other end bus number (e.g. 1501). Orientation does not matter.
      - name: capacity_increase_pct
        type: float
        description: Percent increase of the line's RATE_A in the counterfactual; "increased by 20%" is 20.0, not 1.2.
      - name: report_path
        type: string
        description: Where to write report.json. Use the location the task names, or /root/report.json (the container WORKDIR) if it names none.
    script: scripts/clear_markets.py
    outputs:
      - name: status
        type: string
        description: '"ok" when both markets cleared and prices passed the finite-difference check, "failed" otherwise.'
      - name: status_detail
        type: string
        description: Why it failed (line not found, infeasible, solver error, price check), or "both markets cleared".
      - name: base_case
        type: object
        description: Report section for the base case. Fields are total_cost_dollars_per_hour, lmp_by_bus [{bus, lmp_dollars_per_MWh}] in file bus order, reserve_mcp_dollars_per_MWh, and binding_lines [{from, to, flow_MW, limit_MW}] (signed flow in file orientation). Empty when failed.
      - name: counterfactual
        type: object
        description: The same section for the relaxed-limit case. Empty when failed.
      - name: impact_analysis
        type: object
        description: cost_reduction_dollars_per_hour (base − cf); buses_with_largest_lmp_drop, the 3 most negative cf − base deltas [{bus, base_lmp, cf_lmp, delta}]; congestion_relieved (true when the relaxed line is NOT binding in the counterfactual). Empty when failed.
      - name: target_line
        type: object
        description: The relaxed line's circuits, limits, flows and loading % in both cases, plus binding_in_base / binding_in_cf. Empty when failed.
      - name: diagnostics
        type: object
        description: Sizes, total load, reserve data, solver status, binding counts, and the price_check (dual vs left/right finite difference). Empty when failed.
    inputs_to: by-status

  - name: by-status
    kind: router
    description: Write the report when both markets cleared; otherwise diagnose why.
    branch_on: status
    branches:
      ok: write-report
      failed: diagnose-failure

  - name: write-report
    kind: execution
    description: >
      Check the three sections against the required report.json structure (keys,
      types, 3 drop entries, a boolean flag) and write {base_case, counterfactual,
      impact_analysis} with no extra keys. Do not edit or round the numbers further;
      they are already rounded to cents.
    inputs:
      - name: base_case
        type: object
      - name: counterfactual
        type: object
      - name: impact_analysis
        type: object
      - name: report_path
        type: string
    script: scripts/write_report.py
    outputs:
      - name: report_file
        type: string
        description: Absolute path of the report.json written.
      - name: report_summary
        type: object
        description: Headline numbers, including both costs, cost reduction, binding-line counts, the top-drop buses and congestion_relieved.
    inputs_to: end

  - name: diagnose-failure
    kind: client_task
    description: Find the root cause of the failed clearing from the network file and propose corrected inputs if the evidence supports them.
    inputs:
      - name: status_detail
        type: string
      - name: network_path
        type: string
      - name: line_from_bus
        type: integer
      - name: line_to_bus
        type: integer
      - name: capacity_increase_pct
        type: float
    template: assets/diagnose-failure.md
    references:
      - path: references/market-model.md
        description: MATPOWER columns, the exact market formulation, price sign conventions and the checklist of failure causes. Load for every diagnosis.
      - path: references/cost-functions.md
        description: gencost polynomial / piecewise-linear formats with examples. Load only if the failure mentions gencost or cost terms.
    outputs:
      - name: failure_diagnosis
        type: string
        description: Root cause in one or two sentences, citing the numbers checked.
      - name: corrected_inputs
        type: object
        description: Corrected start inputs to rerun with, or {} when no evidence-backed correction exists.
    inputs_to: end

  - name: end
    kind: end
    description: Run outcome; on success report.json is on disk at report_path.
    inputs:
      - name: status
        type: string
      - name: status_detail
        type: string
      - name: impact_analysis
        type: object
      - name: target_line
        type: object

anti_patterns:
  - Taking LMP = dual * baseMVA (the source snippet). With cvxpy that is −10⁴ times the true price; use the script, which takes −dual of the MW balance and verifies it by re-solve.
  - Indexing buses as bus_number − 1. Bus numbers are non-contiguous; use the bus-number map.
  - Treating negative or very large LMPs as a bug and "fixing" them. They are valid under congestion and the finite-difference check already confirmed them.
  - Writing congestion_relieved as "was binding in base and not in cf". The task defines it as the relaxed line NOT binding in the counterfactual.
  - Applying the increase as a factor (1.2) in capacity_increase_pct, or scaling RATE_B/RATE_C. Only RATE_A is the limit.
  - Hardcoding or hand-editing numbers in report.json, or writing a report after a failed clearing.
  - Reading the multi-MB network.json with sed/head/cat instead of json.load.
  - pip-installing into the system python3 of the Ubuntu 24.04 container (PEP 668 blocks it). Let the script bootstrap its own venv.
```
