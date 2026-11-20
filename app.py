"""
AgentOps: Streamlit evaluation summary, trace inspector, diagnosis, and safe autofix UI.
Compatible with local offline mock mode and persistent SQLite trace store.

Run with:
    streamlit run app.py
Or test directly in terminal:
    python3 app.py
"""

import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from agentops.autofix_runner import AutofixCoordinator, AutofixTrialResult
from agentops.repair import ApprovalStatus, RepairCandidate
from src.agent import SupportAgent
from src.evaluation import (
    Case,
    ComparisonReport,
    EvaluationResult,
    SuiteReport,
    build_canonical_case_list,
    compare_agents,
    run_baseline_comparison,
    run_suite_evaluation,
)
from src.models import (
    get_baseline_fast_fail_config,
    get_default_config,
)
from src.tracer import (
    get_run_trace,
    init_db,
    list_evaluations,
    list_human_decisions,
    list_runs,
    run_trace_to_dict,
)

# Default local database path
DEFAULT_DB_PATH = "data/agentops.db"


def run_evaluation_data(db_path: Optional[str] = None) -> Tuple[SuiteReport, SuiteReport, ComparisonReport]:
    """Execute the baseline and candidate suites and compute the comparison report."""
    if db_path:
        init_db(db_path)
    return run_baseline_comparison(db_path=db_path)


def format_rate(rate_dict: Dict[str, Any], key: str, count_key: str, total_key: str) -> str:
    """Format a metric dictionary into a readable string showing count and denominator."""
    val = rate_dict.get(key)
    count = rate_dict.get(count_key, 0)
    total = rate_dict.get(total_key, 0)
    if val is None:
        return f"N/A ({count}/{total})"
    return f"{count}/{total} ({val * 100:.1f}%)"


def render_cli_summary(baseline_report: SuiteReport, fastfail_report: SuiteReport, comparison: ComparisonReport) -> None:
    """Renders a clean terminal summary for non-Streamlit environments or test runs."""
    print("=" * 80)
    print("AgentOps — Offline Evaluation, Observability & Safe Autofix")
    print("=" * 80)
    print(f"Baseline Agent Version : {baseline_report.agent_version}")
    print(f"Candidate Agent Version: {fastfail_report.agent_version}")
    print("-" * 80)

    # Metrics Summary
    b_ts = baseline_report.metrics.get("task_success", {})
    b_tf = baseline_report.metrics.get("tool_failures", {})
    b_rec = baseline_report.metrics.get("recovery", {})
    b_sv = baseline_report.metrics.get("safety_violations", {})
    b_fla = baseline_report.metrics.get("failure_localization", {})
    rfr = comparison.regression_rate
    rsr = getattr(comparison, "repair_success", {})

    print("BASELINE METRICS (Counts & Denominators):")
    print(f"  • Task Success Rate       : {format_rate(b_ts, 'task_success_rate', 'passed_count', 'total_cases')}")
    print(f"  • Tool Failure Rate        : {format_rate(b_tf, 'tool_failure_rate', 'failed_tool_calls', 'total_tool_calls')}")
    print(f"  • Recovery Rate            : {format_rate(b_rec, 'recovery_rate', 'recovered_count', 'error_cases_total')}")
    print(f"  • Safety Violations        : {format_rate(b_sv, 'safety_violation_rate', 'violation_count', 'total_cases')}")
    print(f"  • Localization Accuracy    : {format_rate(b_fla, 'localization_accuracy', 'matched_count', 'failed_cases_total')}")
    print("-" * 80)

    # Case Outcomes
    print("CASE OUTCOMES:")
    print(f"{'Case ID':<26} | {'Baseline':<8} | {'Candidate':<10} | {'Delta Status':<16}")
    print("-" * 80)
    for row in comparison.case_comparisons:
        print(f"{row['case_id']:<26} | {row['baseline_verdict']:<8} | {row['candidate_verdict']:<10} | {row['delta_status']:<16}")
    print("-" * 80)

    # Comparison Gating
    print("CANDIDATE COMPARISON & GATING (Counts & Denominators):")
    print(f"  • Comparison Verdict     : {comparison.verdict}")
    print(f"  • Gating Reason          : {comparison.reason}")
    print(f"  • Safety Gate            : {comparison.safety_status}")
    print(f"  • Regression Rate (RFR)  : {format_rate(rfr, 'regression_rate', 'regressed_count', 'baseline_passed_count')}")
    if rsr:
        print(f"  • Repair Success (RSR)   : {format_rate(rsr, 'repair_success_rate', 'repaired_count', 'targeted_failing_count')}")
    print("=" * 80)


def is_streamlit_running() -> bool:
    """Detect whether app is executing inside a live Streamlit server or AppTest context."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


def main():
    """Main entrypoint: renders Streamlit UI if running under streamlit, else CLI."""
    if not is_streamlit_running():
        # Run in offline CLI mode
        b_rep, c_rep, comp = run_evaluation_data(DEFAULT_DB_PATH)
        render_cli_summary(b_rep, c_rep, comp)
        print("\n[Notice] To launch interactive UI, run: streamlit run app.py")
        return

    # -------------------------------------------------------------------------
    # Streamlit Interactive Web Application
    # -------------------------------------------------------------------------
    import streamlit as st

    st.set_page_config(
        page_title="AgentOps: Evaluation, Observability & Safe Self-Repair",
        page_icon="🛡️",
        layout="wide",
    )

    st.title("🛡️ AgentOps — AI Agent Evaluation, Observability & Safe Self-Repair")
    st.caption("Local Prototype: Simulated shop-support agent evaluation, ordered SQLite tracing, trace-backed diagnosis, and gated autofix.")

    # Sidebar configuration
    st.sidebar.header("Configuration & Trace Store")
    db_path = st.sidebar.text_input("SQLite Database Path", value=DEFAULT_DB_PATH)
    init_db(db_path)

    # Navigation Tabs
    tab_eval, tab_traces, tab_autofix, tab_baseline = st.tabs([
        "🚀 Run Evaluation",
        "🔍 Results & Traces",
        "🔧 Diagnosis & Safe Autofix",
        "⚖️ Fast-Fail Comparison",
    ])

    # -------------------------------------------------------------------------
    # TAB 1: RUN EVALUATION
    # -------------------------------------------------------------------------
    with tab_eval:
        st.subheader("Run Evaluation Suite Against Support Agent")
        st.write("Execute the six canonical synthetic shop test cases against a selected agent configuration.")

        col_cfg, col_btn = st.columns([3, 1])
        with col_cfg:
            selected_agent_type = st.selectbox(
                "Choose Agent Configuration",
                options=["Standard Resilient Agent (v1.0.0)", "Controlled Fast-Fail Baseline (v0.9.0-fastfail)"],
            )
        with col_btn:
            st.write("")
            st.write("")
            run_btn = st.button("Run 6 Cases", type="primary", use_container_width=True)

        if run_btn:
            cfg = get_default_config() if "v1.0.0" in selected_agent_type else get_baseline_fast_fail_config()
            with st.spinner(f"Running 6 test cases for {cfg.version}..."):
                agent = SupportAgent(config=cfg)
                report = run_suite_evaluation(agent=agent, db_path=db_path)
                st.session_state["latest_suite_report"] = report
            st.success(f"Evaluation complete for {cfg.version}! {report.passed_cases}/{report.total_cases} passed.")

        # Show results if available
        if "latest_suite_report" in st.session_state and st.session_state["latest_suite_report"]:
            rep: SuiteReport = st.session_state["latest_suite_report"]
            st.markdown(f"### Evaluation Metrics — Agent Version `{rep.agent_version}`")

            # Metrics cards with counts and denominators
            c1, c2, c3, c4 = st.columns(4)
            ts = rep.metrics.get("task_success", {})
            tf = rep.metrics.get("tool_failures", {})
            rec = rep.metrics.get("recovery", {})
            sv = rep.metrics.get("safety_violations", {})

            c1.metric("Task Success Rate", format_rate(ts, "task_success_rate", "passed_count", "total_cases"))
            c2.metric("Tool Failure Rate", format_rate(tf, "tool_failure_rate", "failed_tool_calls", "total_tool_calls"))
            c3.metric("Recovery Rate", format_rate(rec, "recovery_rate", "recovered_count", "error_cases_total"))
            c4.metric("Safety Violations", format_rate(sv, "safety_violation_rate", "violation_count", "total_cases"))

            # Outcomes Table
            st.markdown("#### Test Case Outcomes")
            rows = []
            for ev in rep.evaluations:
                rows.append({
                    "Case ID": ev.case_id,
                    "Run ID": ev.run_id,
                    "Verdict": "✅ PASS" if ev.passed else "❌ FAIL",
                    "Score": f"{ev.score:.1f}",
                    "Failure Category": ev.failure_category.value if ev.failure_category else "None",
                    "Observed Tool Calls": ev.details.get("observed_tool_calls", 0),
                    "Evidence Count": len(ev.evidence_event_ids),
                })
            st.dataframe(rows, use_container_width=True)

    # -------------------------------------------------------------------------
    # TAB 2: RESULTS & TRACES
    # -------------------------------------------------------------------------
    with tab_traces:
        st.subheader("Stored Run History & Ordered Trace Events")
        runs = list_runs(db_path)
        if not runs:
            st.info("No runs found in the trace database yet. Run an evaluation first.")
        else:
            run_options = [f"{r.run_id} | {r.case_id} | {r.agent_version} | {r.status}" for r in runs]
            selected_run_str = st.selectbox("Select Run to Inspect", run_options)
            selected_run_id = selected_run_str.split(" | ")[0]

            run_trace = get_run_trace(db_path, selected_run_id)
            if run_trace and run_trace.run:
                r_info = run_trace.run
                st.markdown(f"#### Run Details: `{r_info.run_id}`")
                meta_col1, meta_col2, meta_col3, meta_col4 = st.columns(4)
                meta_col1.write(f"**Case ID:** `{r_info.case_id}`")
                meta_col2.write(f"**Agent Version:** `{r_info.agent_version}`")
                meta_col3.write(f"**Config Role:** `{r_info.config_role or 'original'}`")
                meta_col4.write(f"**Status:** `{r_info.status}`")

                if r_info.baseline_run_id:
                    st.caption(f"Linked Baseline Run ID: `{r_info.baseline_run_id}`")

                st.markdown("##### Final Agent Output")
                st.code(r_info.final_output or "(No output)", language="text")

                st.markdown("##### Ordered Trace Events")
                ev_table = []
                for ev in run_trace.events:
                    ev_table.append({
                        "Seq": ev.sequence_no,
                        "Type": ev.event_type,
                        "Tool Name": ev.tool_name or "-",
                        "Stage": ev.stage or "-",
                        "Status": ev.status or "-",
                        "Duration (ms)": f"{ev.duration_ms:.1f}" if ev.duration_ms is not None else "-",
                        "Error Code": ev.error_code or "-",
                        "Event ID": ev.event_id,
                    })
                st.dataframe(ev_table, use_container_width=True)

                with st.expander("Inspect Raw Event Payloads"):
                    for ev in run_trace.events:
                        st.write(f"**Event #{ev.sequence_no} — {ev.event_type} ({ev.tool_name or 'agent'})** [ID: `{ev.event_id}`]")
                        if ev.input:
                            st.write("*Input:*", ev.input)
                        if ev.output:
                            st.write("*Output:*", ev.output)
                        st.divider()

    # -------------------------------------------------------------------------
    # TAB 3: DIAGNOSIS & SAFE AUTOFIX (Human Approval Gate)
    # -------------------------------------------------------------------------
    with tab_autofix:
        st.subheader("Trace-Based Diagnosis & Safe Autofix Trial")
        st.write(
            "Select any failed run to view trace-supported hypotheses, propose an allowlisted candidate, "
            "test on an isolated copy, run regression gating, and record human approval/rejection."
        )

        coordinator = AutofixCoordinator(db_path=db_path)
        all_stored_runs = list_runs(db_path)
        
        # Select runs whose latest persisted evaluation result failed
        failed_run_items = []
        for r in all_stored_runs:
            evals = list_evaluations(db_path, run_id=r.run_id)
            if evals:
                latest_eval = evals[-1]
                if latest_eval.verdict == "FAIL":
                    fail_cat = latest_eval.failure_category or "UNKNOWN"
                    failed_run_items.append((r, fail_cat))

        if not failed_run_items:
            st.info("No failed evaluations currently found in the trace database. Run an evaluation with 'Controlled Fast-Fail Baseline' to generate failed runs.")
        else:
            failed_options = {
                f"{r.run_id} | Case: {r.case_id} | Version: {r.agent_version} | Category: {cat}": r.run_id
                for r, cat in failed_run_items
            }
            chosen_label = st.selectbox("Select Failed Run to Diagnose", list(failed_options.keys()))
            target_run_id = failed_options[chosen_label]

            col_diag_btn, col_prop_btn = st.columns(2)
            with col_diag_btn:
                do_diag = st.button("Run Read-Only Diagnosis", use_container_width=True)

            if do_diag or "current_diagnosis" not in st.session_state or st.session_state.get("diag_run_id") != target_run_id:
                try:
                    diag_result = coordinator.diagnose_run(target_run_id)
                    st.session_state["current_diagnosis"] = diag_result
                    st.session_state["diag_run_id"] = target_run_id
                    st.session_state["current_trial_result"] = None
                except Exception as e:
                    st.error(f"Diagnosis failed: {e}")

            if "current_diagnosis" in st.session_state and st.session_state["current_diagnosis"]:
                diag = st.session_state["current_diagnosis"]
                st.markdown("#### Diagnosis Report")
                st.info(f"**Likely Cause:** {diag.likely_cause}")
                st.write(f"**Recommended Next Step:** {diag.recommended_next_step}")
                st.write(f"**Uncertainty Assessment:** {diag.uncertainty}")

                st.markdown("##### Trace-Backed Evidence")
                for fact in diag.observed_facts:
                    st.markdown(f"- {fact}")
                st.write("**Cited Event IDs:**", list(diag.cited_evidence_event_ids))

                st.divider()
                st.markdown("#### Safe Repair Candidate Generation")

                if st.button("Generate & Test Allowlisted Candidate on Copy", type="primary"):
                    with st.spinner("Proposing candidate and running isolated regression trial..."):
                        try:
                            candidate = coordinator.propose_candidate_from_diagnosis(target_run_id, diag)
                            trial = coordinator.execute_repair_trial(candidate)
                            st.session_state["current_trial_result"] = trial
                        except Exception as ex:
                            st.error(f"Candidate generation or trial execution failed: {ex}")

            if "current_trial_result" in st.session_state and st.session_state["current_trial_result"]:
                trial: AutofixTrialResult = st.session_state["current_trial_result"]
                cand = trial.candidate

                st.markdown("### Repair Candidate Trial & Gating Results")
                prop_c1, prop_c2 = st.columns(2)
                prop_c1.write(f"**Candidate ID:** `{cand.repair_id}`")
                prop_c1.write(f"**Setting Path:** `{cand.setting_path}`")
                prop_c1.write(f"**Change:** `{cand.old_value}` ➔ `{cand.new_value}`")
                prop_c2.write(f"**Rationale:** {cand.rationale}")
                prop_c2.write(f"**Cited Trace Evidence:** `{cand.evidence_event_ids}`")

                st.markdown("#### Isolated Trial Verification")
                g1, g2, g3 = st.columns(3)
                g1.metric("Failed Case Retest", "PASS" if trial.retest_passed else "FAIL")
                g2.metric("Safety Gate Status", "PASS" if trial.safety_passed else "FAIL")
                g3.metric("Regression Gate Status", trial.comparison_report.verdict)

                if trial.is_acceptable:
                    st.success(f"**Trial Passed:** {trial.decision_reason}")
                else:
                    st.error(f"**Trial Blocked:** {trial.decision_reason}")

                st.markdown("#### Regression Suite Comparison (6 Cases)")
                st.dataframe(trial.comparison_report.case_comparisons, use_container_width=True)

                # Human Approval Gate
                st.markdown("### Human Review & Approval Gate")
                st.warning("Decision policy: approval records human sign-off; the original/live agent configuration is NEVER automatically modified.")

                h_col1, h_col2 = st.columns(2)
                with h_col1:
                    if st.button("✅ Approve Candidate", use_container_width=True, disabled=not trial.is_acceptable):
                        approved_cand = coordinator.record_human_decision(cand, ApprovalStatus.APPROVED)
                        st.session_state["decision_record"] = ("APPROVED", approved_cand.repair_id)
                        st.success(f"Candidate {approved_cand.repair_id} marked as APPROVED by human reviewer.")

                with h_col2:
                    if st.button("❌ Reject Candidate", use_container_width=True):
                        rejected_cand = coordinator.record_human_decision(cand, ApprovalStatus.REJECTED)
                        st.session_state["decision_record"] = ("REJECTED", rejected_cand.repair_id)
                        st.info(f"Candidate {rejected_cand.repair_id} marked as REJECTED.")

                if "decision_record" in st.session_state:
                    dec, c_id = st.session_state["decision_record"]
                    st.info(f"Recorded Human Decision: **{dec}** for candidate `{c_id}`.")

                # Show existing persisted decision if any
                persisted_dec = coordinator.get_latest_decision_for_run(target_run_id)
                if persisted_dec:
                    st.success(
                        f"Stored Human Sign-Off in Database: **{persisted_dec.decision}** "
                        f"(Repair ID: `{persisted_dec.repair_id}`, Recorded at: `{persisted_dec.timestamp}`)"
                    )

    # -------------------------------------------------------------------------
    # TAB 4: FAST-FAIL COMPARISON
    # -------------------------------------------------------------------------
    with tab_baseline:
        st.subheader("Controlled Baseline Comparison (v1.0.0 vs v0.9.0-fastfail)")
        st.info("Demonstrates baseline divergence between standard resilient configuration and zero-retry fast-fail configuration.")

        if st.button("Run Side-by-Side Comparison"):
            b_rep, c_rep, comp = run_evaluation_data(db_path=db_path)
            st.session_state["cached_baseline_comp"] = (b_rep, c_rep, comp)

        if "cached_baseline_comp" in st.session_state:
            b_rep, c_rep, comp = st.session_state["cached_baseline_comp"]
            m1, m2, m3 = st.columns(3)
            m1.metric("Gate Status", comp.verdict)
            m2.metric("Safety Gate", comp.safety_status)
            m3.metric("Regressions", f"{comp.regression_rate.get('regressed_count', 0)}/{comp.regression_rate.get('baseline_passed_count', 0)}")

            st.dataframe(comp.case_comparisons, use_container_width=True)


if __name__ == "__main__":
    main()
