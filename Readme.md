# AgentOps: AI Agent Evaluation, Observability & Safe Self-Repair Platform

[![tests](https://github.com/sujanyd/AI_project/actions/workflows/tests.yml/badge.svg)](https://github.com/sujanyd/AI_project/actions/workflows/tests.yml)

AgentOps is a local, deterministic evaluation and self-repair prototype for an e-commerce customer support agent. It provides:
1. **Support Agent & Deterministic Mock Tools:** Realistic simulation of order lookup, shipping policy lookup, and response safety validation without external network calls or write actions.
2. **Ordered SQLite Tracing:** Complete execution recording for planning thoughts, tool dispatches, observations, and safe stops.
3. **Six Canonical Test Cases & Deterministic Scoring:** Repeatable evaluation against defined ground truth, computing task success, tool failure, recovery, and safety violation rates with exact counts and denominators.
4. **Trace-Backed Read-Only Diagnosis:** Diagnosis engine that inspects stored execution traces, checks evidence event IDs, and reports structured hypotheses with uncertainty boundaries.
5. **Gated Safe Autofix on Isolated Copy:** Autofix coordinator that proposes candidate setting changes from a narrow allowlist, tests them on a deep copy of the configuration, runs regression suites, and requires explicit human approval before any change is recorded.
6. **Interactive Streamlit Web App & CLI:** Dual interface allowing users to run benchmarks, inspect traces, analyze failures, test candidate fixes, and record approval/rejection decisions.

---

## 1. Prerequisites & Installation

- **Python Version:** Python 3.11 or newer (CI tests 3.11, 3.12 and 3.13).
- **Dependencies:** Install the project dependencies listed in `requirements.txt`:
  ```bash
  pip install -r requirements.txt
  ```
  *(Note: Standard library modules like `sqlite3`, `unittest`, `dataclasses`, and `re` are used throughout the core backend.)*

---

## 2. Quickstart & Running the Application

### Option A: Interactive Streamlit Web App
Launch the interactive web application:
```bash
streamlit run app.py
```
*(Or `python3 -m streamlit run app.py`)*

The web application opens at `http://localhost:8501` with a dark "mission control" theme (`.streamlit/config.toml`, styles and components in `app_ui.py`). A live pipeline tracker across the top lights up each stage of the loop (Run → Trace → Evaluate → Diagnose → Autofix → Approve) as you go, and the sidebar shows trace-store counts and the safeguards. There are four tabs:
1. **▶ Run & Evaluate:** Choose an agent setup and run the six-case test suite. Shows the six measures as rings (task success, tool failures, recovery, safety violations, failure-localization accuracy) and a pass/fail card per case. Four setups are available:
   - `v1.0.0` — standard resilient agent (passes all six cases).
   - `v0.9.1-vague-prompt` — same agent with a vague clarification prompt; fails CASE-002 in a way autofix can repair with a prompt change. **Use this one for the end-to-end autofix demo.**
   - `v0.9.2-vague-tool-description` — same agent with an `order_lookup` description that never names its input. The planner builds lookup arguments from the description, so it sends the wrong argument and every lookup is rejected with `INVALID_INPUT` (5 of 6 cases fail as `INVALID_TOOL_INPUT`). Autofix repairs it by restoring a description that names `order_id`.
   - `v0.9.0-fastfail` — step budget cut to 2; fails CASE-001 and CASE-006 with `LIMIT_EXCEEDED`. Diagnosis explains these, but autofix declines because step limits are safeguards, not allowlisted settings.
2. **⌁ Traces:** Select any stored run to see the agent's reply and a colour-coded timeline of every plan, tool call, result and error, with a table and raw payloads underneath.
3. **⚙ Diagnose & Autofix:** Select any failed run (e.g. the CASE-002 run from `v0.9.1-vague-prompt`, or any failed run from `v0.9.2-vague-tool-description`), run read-only diagnosis to extract trace facts, generate an allowlisted candidate change, execute an isolated trial retest and 6-case regression suite, see the proposed change as a before/after diff with the trial gates and **Fix Success**, and record your human Approve/Reject decision.
4. **⚖ Compare:** Side-by-side case cards for the standard and fast-fail agents, with the gating verdicts.

### Option B: Terminal CLI Fallback
If running in a headless or text-only environment:
```bash
python3 app.py
```
Outputs baseline and candidate suite metrics side by side (including failure-localization accuracy), per-case outcomes, regression rates, and gate verdicts, followed by two **Safe Autofix Demos** (a prompt fix and a tool-description fix): each shows a failed case, its trace-backed diagnosis, the proposed change (before → after), the re-test, Fix Success, and the trial verdict. Approval itself stays in the web app. Traces are written to `data/agentops.db`, which is git-ignored.

---

## 3. Running Automated Tests

All tests run completely offline and finish in a few seconds using Python's standard `unittest` discovery:
```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```
**Total Test Count:** 158 unit and integration tests (run on every push and pull request by GitHub Actions) covering:
- Support agent limit enforcement, timeout handling, and read-only protections (`test_agent_and_tools.py`)
- SQLite schema migrations, event ordering, and sanitization (`test_tracer.py`, `test_trace_recorder.py`)
- Canonical test case scoring and metric calculations (`test_evaluator.py`)
- Read-only diagnosis isolation and trace evidence citations (`test_diagnosis_repair.py`, `test_trace_diagnosis.py`)
- Autofix trial execution, copy isolation, regression gating, and human review recording (`test_autofix_coordinator.py`, `test_candidate_config_and_decision_persistence.py`)
- Execution-limit classification, failure-localization ground truth, and allowlist refusal (`test_execution_limit_localization.py`)
- Full run → diagnose → fix on copy → re-test → approve loop, CLI demo, and import order (`test_autofix_end_to_end.py`)
- UI pipeline-state logic and HTML escaping of trace data (`test_app_ui.py`)
- Tool-description fixes: argument building from the description, `INVALID_TOOL_INPUT` localization, the repair on a copy, and the pinned allowlist value (`test_tool_description_autofix.py`)
- Streamlit UI end-to-end flows via `AppTest` (`test_ui_apptest_e2e.py`)

---

## 4. Architecture Overview

```
                      ┌────────────────────────┐
                      │    Streamlit App / CLI │
                      └───────────┬────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   SupportAgent   │    │  Tracer & Store  │    │    Evaluator     │
│  & 3 Mock Tools  │───▶│  (SQLite Trace)  │◀───│ (Canonical Cases)│
└──────────────────┘    └─────────┬────────┘    └──────────────────┘
                                  │ (Read-Only)
                                  ▼
                        ┌──────────────────┐
                        │ Diagnosis Engine │
                        └─────────┬────────┘
                                  │ (Cited Trace Evidence)
                                  ▼
                        ┌──────────────────┐
                        │ Safe Autofix     │ (Applied only to copy;
                        │ Coordinator      │  tested on regression suite)
                        └─────────┬────────┘
                                  │
                        ┌─────────▼────────┐
                        │ Human Gate (App) │ (Approve / Reject)
                        └──────────────────┘
```

### Core Modules:
- `src/agent.py`: `SupportAgent` executing reasoning steps, mock tool dispatches, and observable callbacks.
- `src/tools.py`: Deterministic mock tools (`OrderLookupTool`, `ShippingPolicyLookupTool`, `ResponseValidationTool`) running over synthetic fixtures.
- `src/models.py`: Structured data contracts (`AgentInput`, `AgentResult`, `AgentConfig`, `ObservableEvent`).
- `src/tracer.py` & `src/trace_recorder.py`: SQLite persistence for runs, ordered events, and evaluations.
- `src/evaluation.py`: Repeatable canonical test cases, failure taxonomy, metrics calculation, and comparative gating.
- `agentops/diagnosis.py` & `src/trace_diagnosis.py`: Read-only diagnosis extracting verified trace facts.
- `agentops/repair.py` & `agentops/autofix_runner.py`: Candidate allowlist validator, isolated copy modifier, regression runner, and human decision recorder.
- `app.py`: Interactive Streamlit frontend and fallback terminal CLI.

---

## 5. Safety Boundaries & Guardrails

- **Zero Write Actions:** The support agent has no tools or permissions to modify real databases, process refunds, cancel orders, or dispatch emails. Write intent keywords are automatically intercepted with safe explanations.
- **Narrow Autofix Allowlist:** Automated repair candidates are restricted strictly to allowlisted operational parameters (`tools.lookup_order_details.retry_count` bounded 0→1, 1→2; `tools.lookup_order_details.description`; and `agent.clarification_instruction`; the last two accept only one pinned, reviewed value each). No arbitrary code editing or unverified parameter mutations are allowed. Failures outside the allowlist, such as an exhausted step budget (`LIMIT_EXCEEDED`), are diagnosed with trace evidence but no candidate is proposed; they are left for manual review.
- **Copy Isolation:** Proposed repairs are applied strictly to a `deepcopy` of the configuration. The baseline or live agent is never mutated during trial runs.
- **Regression & Safety Gating:** Any candidate that causes a regression on previously passing test cases or triggers a safety violation is blocked from recommendation.
- **Human Review Gate:** Approval records human consent; it does not automatically deploy changes to production.

---

## 6. Known Limitations

- **Simulated Shop Data Only:** All customer records, order IDs, and shipment policies are in-memory synthetic fixtures (`ORD-10001`, `ORD-CONFLICT`, etc.).
- **Single-Turn Scenarios:** Test cases verify single-turn inquiries (e.g. verifying that missing IDs trigger `CLARIFICATION_NEEDED`). Multi-turn conversational repair sessions can be explored in future milestones.
