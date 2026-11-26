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
    AgentConfig,
    get_baseline_fast_fail_config,
    get_default_config,
    get_vague_clarification_config,
    get_vague_tool_description_config,
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

# Agent setups a person can choose before running the suite.
AGENT_SETUPS = {
    "Standard Resilient Agent (v1.0.0)": get_default_config,
    "Vague Clarification Prompt (v0.9.1-vague-prompt) — fixable by autofix": get_vague_clarification_config,
    "Vague Tool Description (v0.9.2-vague-tool-description) — fixable by autofix": get_vague_tool_description_config,
    "Controlled Fast-Fail Baseline (v0.9.0-fastfail) — step-limit failures": get_baseline_fast_fail_config,
}


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


# (label, metrics key, rate key, numerator key, denominator key)
METRIC_ROWS: List[Tuple[str, str, str, str, str]] = [
    ("Task Success Rate", "task_success", "task_success_rate", "passed_count", "total_cases"),
    ("Tool Failure Rate", "tool_failures", "tool_failure_rate", "failed_tool_calls", "total_tool_calls"),
    ("Recovery Rate", "recovery", "recovery_rate", "recovered_count", "error_cases_total"),
    ("Safety Violations", "safety_violations", "safety_violation_rate", "violation_count", "total_cases"),
    ("Localization Accuracy", "failure_localization", "localization_accuracy", "matched_count", "failed_cases_total"),
]


def render_cli_summary(baseline_report: SuiteReport, fastfail_report: SuiteReport, comparison: ComparisonReport) -> None:
    """Renders a clean terminal summary for non-Streamlit environments or test runs."""
    print("=" * 80)
    print("AgentOps — Offline Evaluation, Observability & Safe Autofix")
    print("=" * 80)
    print(f"Baseline Agent Version : {baseline_report.agent_version}")
    print(f"Candidate Agent Version: {fastfail_report.agent_version}")
    print("-" * 80)

    # Metrics Summary (baseline and candidate side by side)
    rfr = comparison.regression_rate
    rsr = getattr(comparison, "repair_success", {})

    print("SUITE METRICS (Counts & Denominators):")
    print(f"  {'Metric':<24} | {'Baseline':<18} | {'Candidate':<18}")
    for label, metric_key, rate_key, count_key, total_key in METRIC_ROWS:
        b_val = format_rate(baseline_report.metrics.get(metric_key, {}), rate_key, count_key, total_key)
        c_val = format_rate(fastfail_report.metrics.get(metric_key, {}), rate_key, count_key, total_key)
        print(f"  {label:<24} | {b_val:<18} | {c_val:<18}")
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


# Fixable demo setups the CLI walks through: one prompt fix, one tool-description fix.
AUTOFIX_DEMO_SETUPS = (get_vague_clarification_config, get_vague_tool_description_config)


def run_autofix_demo(db_path: str, config_factory=get_vague_clarification_config) -> Dict[str, Any]:
    """
    End-to-end autofix loop on a fixable demo setup: run the six cases, diagnose the
    first failure from its trace, propose an allowlisted fix, and re-test it on a copy.
    Nothing is approved here; approval stays with a person in the web app.
    """
    agent = SupportAgent(config=config_factory())
    report = run_suite_evaluation(agent=agent, db_path=db_path)
    failed = [e for e in report.evaluations if not e.passed]
    if not failed:
        return {"report": report, "failed": None}
    target = failed[0]
    coordinator = AutofixCoordinator(db_path)
    diagnosis = coordinator.diagnose_run(target.run_id)
    candidate = coordinator.propose_candidate_from_diagnosis(target.run_id, diagnosis)
    trial = coordinator.execute_repair_trial(candidate)
    return {"report": report, "failed": target, "diagnosis": diagnosis, "trial": trial}


def render_cli_autofix(demo: Dict[str, Any]) -> None:
    """Print the autofix demo: before, diagnosis, proposed change, after, and gates."""
    report: SuiteReport = demo["report"]
    print("SAFE AUTOFIX DEMO")
    print(f"  Setup                   : {report.agent_version} ({report.passed_cases}/{report.total_cases} cases pass)")
    target = demo.get("failed")
    if target is None:
        print("  No failing case; nothing to repair.")
        print("=" * 80)
        return
    diag = demo["diagnosis"]
    trial: AutofixTrialResult = demo["trial"]
    cand = trial.candidate
    print(f"  Failed case             : {target.case_id} ({target.failure_category.value if target.failure_category else 'UNKNOWN'})")
    print(f"  Diagnosis               : {diag.likely_cause}")
    print(f"  Cited trace events      : {len(diag.cited_evidence_event_ids)}")
    print(f"  Proposed change (copy)  : {cand.setting_path}")
    print(f"      before              : {cand.old_value!r}")
    print(f"      after               : {cand.new_value!r}")
    print(f"  Failed case retest      : {'PASS' if trial.retest_passed else 'FAIL'}")
    print(f"  Fix Success             : {format_rate(trial.comparison_report.repair_success, 'repair_success_rate', 'repaired_count', 'targeted_failing_count')}")
    print(f"  Regressions             : {format_rate(trial.comparison_report.regression_rate, 'regression_rate', 'regressed_count', 'baseline_passed_count')}")
    print(f"  Safety gate             : {'PASS' if trial.safety_passed else 'FAIL'}")
    print(f"  Trial verdict           : {'READY FOR HUMAN APPROVAL' if trial.is_acceptable else 'BLOCKED'} — {trial.decision_reason}")
    print("  Approve or reject it in the web app (Diagnosis & Safe Autofix tab).")
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
        for config_factory in AUTOFIX_DEMO_SETUPS:
            render_cli_autofix(run_autofix_demo(DEFAULT_DB_PATH, config_factory))
        print("\n[Notice] To launch interactive UI, run: streamlit run app.py")
        return

    # -------------------------------------------------------------------------
    # Streamlit Interactive Web Application
    # -------------------------------------------------------------------------
    import streamlit as st

    import app_ui as ui

    st.set_page_config(
        page_title="AgentOps: Evaluation, Observability & Safe Self-Repair",
        page_icon="◼",
        layout="wide",
    )
    st.markdown(ui.CSS, unsafe_allow_html=True)

    def html(fragment: str) -> None:
        st.markdown(fragment, unsafe_allow_html=True)

    # Sidebar configuration
    st.sidebar.markdown("### AgentOps")
    db_path = st.sidebar.text_input("SQLite Database Path", value=DEFAULT_DB_PATH)
    init_db(db_path)

    def store_snapshot() -> Dict[str, Any]:
        """One pass over the trace store: runs, latest evaluation per run, decisions."""
        runs = list_runs(db_path)
        latest_eval: Dict[str, Any] = {}
        evals = list_evaluations(db_path)
        for record in evals:
            latest_eval[record.run_id] = record
        failed = [
            (r, latest_eval[r.run_id].failure_category or "UNKNOWN")
            for r in runs
            if r.run_id in latest_eval and latest_eval[r.run_id].verdict == "FAIL"
        ]
        return {
            "runs": runs,
            "failed": failed,
            "stats": {
                "runs": len(runs),
                "evaluations": len(evals),
                "failed": len(failed),
                "decisions": len(list_human_decisions(db_path)),
            },
        }

    snapshot = store_snapshot()

    st.title("AgentOps")
    tagline_slot = st.empty()
    pipeline_slot = st.empty()
    sidebar_slot = st.sidebar.empty()
    case_descriptions = {c.case_id: c.description or "" for c in build_canonical_case_list()}

    # Navigation Tabs
    tab_eval, tab_traces, tab_autofix, tab_baseline = st.tabs([
        "Run & Evaluate",
        "Traces",
        "Diagnose & Autofix",
        "Compare",
    ])

    # -------------------------------------------------------------------------
    # TAB 1: RUN EVALUATION
    # -------------------------------------------------------------------------
    with tab_eval:
        html(ui.section("Step 1", "Choose a setup and run the six cases"))

        col_cfg, col_btn = st.columns([3, 1.1], vertical_alignment="bottom")
        with col_cfg:
            selected_agent_type = st.selectbox(
                "Choose Agent Configuration",
                options=list(AGENT_SETUPS),
            )
        with col_btn:
            run_btn = st.button("Run 6 Cases", type="primary", width="stretch")

        if run_btn:
            cfg: AgentConfig = AGENT_SETUPS[selected_agent_type]()
            with st.spinner(f"Running 6 test cases for {cfg.version}..."):
                agent = SupportAgent(config=cfg)
                report = run_suite_evaluation(agent=agent, db_path=db_path)
                st.session_state["latest_suite_report"] = report
            st.toast(f"{cfg.version}: {report.passed_cases}/{report.total_cases} cases passed")
            snapshot = store_snapshot()

        rep: Optional[SuiteReport] = st.session_state.get("latest_suite_report")
        if rep:
            all_passed = rep.passed_cases == rep.total_cases
            html(ui.verdict_banner(
                all_passed,
                f"{rep.agent_version} · {rep.passed_cases}/{rep.total_cases} cases passed",
                "Every case met its expected outcome." if all_passed
                else "Some cases failed. Open “Diagnose & Autofix” to find the failing step and test a fix.",
            ))
            html(ui.section("Step 2", "Measures"))
            html(ui.metric_rings(rep.metrics))
            html(ui.section("Step 3", "Cases"))
            html(ui.case_grid(rep.evaluations, case_descriptions))
            with st.expander("Table view"):
                st.dataframe(
                    [
                        {
                            "Case ID": ev.case_id,
                            "Run ID": ev.run_id,
                            "Verdict": "PASS" if ev.passed else "FAIL",
                            "Score": round(ev.score, 2),
                            "Failure Category": ev.failure_category.value if ev.failure_category else "None",
                            "Tool Calls": ev.details.get("observed_tool_calls", 0),
                            "Evidence Events": len(ev.evidence_event_ids),
                        }
                        for ev in rep.evaluations
                    ],
                    width="stretch",
                    hide_index=True,
                )
        else:
            st.info("Choose a setup and press **Run 6 Cases**. Try a “fixable by autofix” setup to see the whole loop.")

    # -------------------------------------------------------------------------
    # TAB 2: RESULTS & TRACES
    # -------------------------------------------------------------------------
    with tab_traces:
        html(ui.section("Observability", "Run traces"))
        runs = snapshot["runs"]
        if not runs:
            st.info("No runs found in the trace database yet. Run an evaluation first.")
        else:
            run_labels = {
                r.run_id: f"{r.run_id} · {r.agent_version} · {r.status}" for r in reversed(runs)
            }
            selected_run_id = st.selectbox(
                "Select Run to Inspect", list(run_labels), format_func=run_labels.get
            )

            run_trace = get_run_trace(db_path, selected_run_id)
            if run_trace and run_trace.run:
                r_info = run_trace.run
                meta = st.columns(4)
                meta[0].metric("Case", r_info.case_id)
                meta[1].metric("Agent Version", r_info.agent_version)
                meta[2].metric("Config Role", r_info.config_role or "original")
                meta[3].metric("Status", r_info.status or "-")
                if r_info.baseline_run_id:
                    st.caption(f"Linked baseline run: `{r_info.baseline_run_id}`")

                html(ui.output_bubble(r_info.final_output, r_info.status))
                html(ui.section("Event log", f"{len(run_trace.events)} events"))
                html(ui.trace_timeline(run_trace.events))

                with st.expander("Table view & raw payloads"):
                    st.dataframe(
                        [
                            {
                                "Seq": ev.sequence_no,
                                "Type": ev.event_type,
                                "Tool": ev.tool_name or "-",
                                "Stage": ev.stage or "-",
                                "Status": ev.status or "-",
                                "Duration (ms)": round(ev.duration_ms, 1) if ev.duration_ms is not None else None,
                                "Error Code": ev.error_code or "-",
                                "Event ID": ev.event_id,
                            }
                            for ev in run_trace.events
                        ],
                        width="stretch",
                        hide_index=True,
                    )
                    for ev in run_trace.events:
                        st.markdown(f"**#{ev.sequence_no} {ev.event_type}** · `{ev.event_id}`")
                        if ev.input:
                            st.code(ev.input, language="json")
                        if ev.output:
                            st.code(ev.output, language="json")

    # -------------------------------------------------------------------------
    # TAB 3: DIAGNOSIS & SAFE AUTOFIX (Human Approval Gate)
    # -------------------------------------------------------------------------
    with tab_autofix:
        html(ui.section("Diagnosis", "Find the failing step"))

        coordinator = AutofixCoordinator(db_path=db_path)
        failed_run_items = snapshot["failed"]

        if not failed_run_items:
            st.info("No failed evaluations currently found in the trace database. Run an evaluation with the 'Vague Clarification Prompt' or 'Vague Tool Description' setup to generate a failure autofix can repair.")
        else:
            failed_labels = {
                r.run_id: f"{r.run_id} | Case: {r.case_id} | Version: {r.agent_version} | Category: {cat}"
                for r, cat in reversed(failed_run_items)
            }
            # A trial records new runs, which changes this list. Keep the reviewer's run
            # selected across reruns so its trial and the approval buttons stay in place.
            if st.session_state.get("selected_failed_run") not in failed_labels:
                st.session_state["selected_failed_run"] = next(iter(failed_labels))
            col_sel, col_diag_btn = st.columns([2.6, 1.4], vertical_alignment="bottom")
            with col_sel:
                target_run_id = st.selectbox(
                    "Select Failed Run to Diagnose",
                    list(failed_labels),
                    format_func=failed_labels.get,
                    key="selected_failed_run",
                )
            with col_diag_btn:
                do_diag = st.button("Run Diagnosis", width="stretch")

            if do_diag or "current_diagnosis" not in st.session_state or st.session_state.get("diag_run_id") != target_run_id:
                try:
                    diag_result = coordinator.diagnose_run(target_run_id)
                    st.session_state["current_diagnosis"] = diag_result
                    st.session_state["diag_run_id"] = target_run_id
                    st.session_state["current_trial_result"] = None
                    st.session_state.pop("decision_record", None)
                except Exception as e:
                    st.error(f"Diagnosis failed: {e}")

            diag = st.session_state.get("current_diagnosis")
            if diag:
                st.info(f"**Likely Cause:** {diag.likely_cause}")
                html(ui.hypothesis_card(
                    f"Evidence from the trace · {len(diag.cited_evidence_event_ids)} event(s) cited",
                    diag.recommended_next_step,
                    diag.uncertainty,
                    diag.observed_facts,
                ))

                if st.button("Generate & Test Allowlisted Candidate on Copy", type="primary"):
                    with st.spinner("Proposing a fix and re-running all six cases on a copy..."):
                        try:
                            candidate = coordinator.propose_candidate_from_diagnosis(target_run_id, diag)
                            trial = coordinator.execute_repair_trial(candidate)
                            st.session_state["current_trial_result"] = trial
                            st.session_state.pop("decision_record", None)
                            snapshot = store_snapshot()
                        except ValueError as ex:
                            if "No allowlisted repair" in str(ex):
                                st.warning(
                                    f"{ex} Autofix only changes allowlisted settings, so this failure "
                                    "needs a manual review. Follow the recommended next step above."
                                )
                            else:
                                st.error(f"Candidate generation or trial execution failed: {ex}")
                        except Exception as ex:
                            st.error(f"Candidate generation or trial execution failed: {ex}")

            trial: Optional[AutofixTrialResult] = st.session_state.get("current_trial_result")
            if trial:
                cand = trial.candidate
                html(ui.section("Proposed fix", f"Candidate {cand.repair_id}"))
                html(ui.diff_card(cand.setting_path, cand.old_value, cand.new_value, cand.rationale))

                html(ui.section("Re-test on the same six cases", "Trial gates"))
                g1, g2 = st.columns(2)
                g3, g4 = st.columns(2)
                g1.metric("Failed Case Retest", "PASS" if trial.retest_passed else "FAIL")
                g2.metric("Safety Gate Status", "PASS" if trial.safety_passed else "FAIL")
                g3.metric("Regression Gate Status", trial.comparison_report.verdict)
                g4.metric(
                    "Fix Success",
                    format_rate(trial.comparison_report.repair_success, "repair_success_rate", "repaired_count", "targeted_failing_count"),
                )
                html(ui.verdict_banner(
                    trial.is_acceptable,
                    "Trial passed — ready for your decision" if trial.is_acceptable else "Trial blocked",
                    trial.decision_reason,
                ))
                with st.expander("Before vs after, case by case"):
                    st.dataframe(trial.comparison_report.case_comparisons, width="stretch", hide_index=True)

                # Human Approval Gate
                html(ui.section("Your decision", "Approve or reject"))
                st.caption("Approval records your sign-off. The original agent configuration is never changed automatically.")

                h_col1, h_col2 = st.columns(2)
                with h_col1:
                    if st.button("Approve Candidate", type="primary", width="stretch", disabled=not trial.is_acceptable):
                        approved_cand = coordinator.record_human_decision(cand, ApprovalStatus.APPROVED)
                        st.session_state["decision_record"] = ("APPROVED", approved_cand.repair_id)
                        snapshot = store_snapshot()
                with h_col2:
                    if st.button("Reject Candidate", width="stretch"):
                        rejected_cand = coordinator.record_human_decision(cand, ApprovalStatus.REJECTED)
                        st.session_state["decision_record"] = ("REJECTED", rejected_cand.repair_id)
                        snapshot = store_snapshot()

                if "decision_record" in st.session_state:
                    dec, c_id = st.session_state["decision_record"]
                    st.info(f"Recorded Human Decision: **{dec}** for candidate `{c_id}`.")

            # Show existing persisted decision if any
            persisted_dec = coordinator.get_latest_decision_for_run(target_run_id)
            if persisted_dec:
                st.success(
                    f"Stored Human Sign-Off in Database: **{persisted_dec.decision.upper()}** "
                    f"(Repair ID: `{persisted_dec.repair_id}`, Recorded at: `{persisted_dec.timestamp}`)"
                )

    # -------------------------------------------------------------------------
    # TAB 4: FAST-FAIL COMPARISON
    # -------------------------------------------------------------------------
    with tab_baseline:
        html(ui.section("Baseline comparison", "v1.0.0 vs v0.9.0-fastfail"))
        st.caption("The standard agent against a version with zero retries and a two-step budget, on the same six cases.")

        if st.button("Run Side-by-Side Comparison", type="primary"):
            with st.spinner("Running both agents on all six cases..."):
                b_rep, c_rep, comp = run_evaluation_data(db_path=db_path)
            st.session_state["cached_baseline_comp"] = (b_rep, c_rep, comp)
            snapshot = store_snapshot()

        if "cached_baseline_comp" in st.session_state:
            b_rep, c_rep, comp = st.session_state["cached_baseline_comp"]
            m1, m2, m3 = st.columns(3)
            m1.metric("Gate Status", comp.verdict)
            m2.metric("Safety Gate", comp.safety_status)
            m3.metric("Regressions", f"{comp.regression_rate.get('regressed_count', 0)}/{comp.regression_rate.get('baseline_passed_count', 0)}")
            left, right = st.columns(2)
            with left:
                html(ui.section("Baseline", b_rep.agent_version))
                html(ui.case_grid(b_rep.evaluations, case_descriptions))
            with right:
                html(ui.section("Candidate", c_rep.agent_version))
                html(ui.case_grid(c_rep.evaluations, case_descriptions))
            with st.expander("Comparison table"):
                st.dataframe(comp.case_comparisons, width="stretch", hide_index=True)

    # ── Header widgets filled last, so they reflect everything this run did ──
    tagline_slot.markdown(ui.tagline(snapshot["stats"]), unsafe_allow_html=True)
    sidebar_slot.markdown(ui.sidebar_status(snapshot["stats"]), unsafe_allow_html=True)
    trial_state = st.session_state.get("current_trial_result")
    pipeline_slot.markdown(
        ui.pipeline(ui.pipeline_states(
            has_runs=bool(snapshot["runs"]),
            has_evals=snapshot["stats"]["evaluations"] > 0,
            has_failures=bool(snapshot["failed"]),
            diagnosed=bool(st.session_state.get("current_diagnosis")),
            trial_ok=None if not trial_state else trial_state.is_acceptable,
            decided="decision_record" in st.session_state,
        )),
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
