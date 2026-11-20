# AgentOps: AI Agent Evaluation, Observability & Safe Self-Repair Platform

AgentOps is a local, deterministic evaluation and self-repair prototype for an e-commerce customer support agent. It provides:
1. **Support Agent & Deterministic Mock Tools:** Realistic simulation of order lookup, shipping policy lookup, and response safety validation without external network calls or write actions.
2. **Ordered SQLite Tracing:** Complete execution recording for planning thoughts, tool dispatches, observations, and safe stops.
3. **Six Canonical Test Cases & Deterministic Scoring:** Repeatable evaluation against defined ground truth, computing task success, tool failure, recovery, and safety violation rates with exact counts and denominators.
4. **Trace-Backed Read-Only Diagnosis:** Diagnosis engine that inspects stored execution traces, checks evidence event IDs, and reports structured hypotheses with uncertainty boundaries.
5. **Gated Safe Autofix on Isolated Copy:** Autofix coordinator that proposes candidate setting changes from a narrow allowlist, tests them on a deep copy of the configuration, runs regression suites, and requires explicit human approval before any change is recorded.
6. **Interactive Streamlit Web App & CLI:** Dual interface allowing users to run benchmarks, inspect traces, analyze failures, test candidate fixes, and record approval/rejection decisions.

---

## 1. Prerequisites & Installation

- **Python Version:** Python 3.11, 3.12, 3.13, 3.14, or 3.15.
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

The web application opens at `http://localhost:8501` and is divided into four tabs:
1. **🚀 Run Evaluation:** Run the six-case test suite against the resilient agent (`v1.0.0`) or the controlled fast-fail baseline (`v0.9.0-fastfail`). Displays task success, recovery rates, and case breakdowns.
2. **🔍 Results & Traces:** Select any stored run to inspect metadata, final outputs, and ordered trace events with duration and payload details.
3. **🔧 Diagnosis & Safe Autofix:** Select any failed run (e.g. from the fast-fail baseline), run read-only diagnosis to extract trace facts, generate an allowlisted candidate change, execute an isolated trial retest and 6-case regression suite, and record your human Approve/Reject decision.
4. **⚖️ Fast-Fail Comparison:** Side-by-side comparison matrix showing performance deltas and gating verdicts.

### Option B: Terminal CLI Fallback
If running in a headless or text-only environment:
```bash
python3 app.py
```
Outputs the side-by-side comparison report, counts/denominators, regression rates, and gate verdicts directly to standard output.

---

## 3. Running Automated Tests

All tests run completely offline and finish in under a second using Python's standard `unittest` discovery:
```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```
**Total Test Count:** 109 unit and integration tests covering:
- Support agent limit enforcement, timeout handling, and read-only protections (`test_agent_and_tools.py`)
- SQLite schema migrations, event ordering, and sanitization (`test_tracer.py`, `test_trace_recorder.py`)
- Canonical test case scoring and metric calculations (`test_evaluator.py`)
- Read-only diagnosis isolation and trace evidence citations (`test_diagnosis_repair.py`, `test_trace_diagnosis.py`)
- Autofix trial execution, copy isolation, regression gating, and human review recording (`test_autofix_coordinator.py`)

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
- **Narrow Autofix Allowlist:** Automated repair candidates are restricted strictly to allowlisted operational parameters (`tools.lookup_order_details.retry_count` bounded 0→1, 1→2 and `agent.clarification_instruction`). No arbitrary code editing or unverified parameter mutations are allowed.
- **Copy Isolation:** Proposed repairs are applied strictly to a `deepcopy` of the configuration. The baseline or live agent is never mutated during trial runs.
- **Regression & Safety Gating:** Any candidate that causes a regression on previously passing test cases or triggers a safety violation is blocked from recommendation.
- **Human Review Gate:** Approval records human consent; it does not automatically deploy changes to production.

---

## 6. Known Limitations

- **Simulated Shop Data Only:** All customer records, order IDs, and shipment policies are in-memory synthetic fixtures (`ORD-10001`, `ORD-CONFLICT`, etc.).
- **Single-Turn Scenarios:** Test cases verify single-turn inquiries (e.g. verifying that missing IDs trigger `CLARIFICATION_NEEDED`). Multi-turn conversational repair sessions can be explored in future milestones.
