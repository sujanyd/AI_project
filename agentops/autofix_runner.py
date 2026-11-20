"""
Autofix coordinator module for AgentOps.

Connects:
selected failed run -> read-only diagnosis -> validated repair candidate ->
copied configuration -> failed-case and full-suite retest -> persisted candidate traces ->
before/after comparison -> human approve/reject decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple
import uuid

import json
from agentops.diagnosis import (
    DiagnosisRequest,
    DiagnosisResult,
    FailureCategory as DiagnosisCategory,
    diagnose,
)
from agentops.repair import (
    ApprovalStatus,
    CandidateTestStatus,
    CandidateValidationError,
    RepairCandidate,
    apply_candidate_to_copy,
    validate_candidate,
)
from src.agent import SupportAgent
from src.evaluation import (
    Case,
    ComparisonReport,
    EvaluationResult,
    SuiteReport,
    build_canonical_case_list,
    build_canonical_cases,
    calculate_suite_metrics,
    compare_agents,
    evaluate,
    run_suite_evaluation,
)
from src.models import (
    AgentConfig,
    AgentInput,
    get_baseline_fast_fail_config,
    get_default_config,
)
from src.trace_diagnosis import (
    TraceStoreDiagnosisTools,
    case_expectations_from_cases,
    failure_summary,
)
from src.trace_recorder import (
    load_run_for_evaluation,
    run_and_record,
)
from src.tracer import (
    CONFIG_ROLE_CANDIDATE,
    CONFIG_ROLE_ORIGINAL,
    HumanDecisionRecord,
    get_run_trace,
    init_db,
    list_human_decisions,
    save_evaluation,
    save_human_decision,
)


@dataclass
class AutofixTrialResult:
    """Complete result of an autofix attempt on an isolated configuration copy."""
    candidate: RepairCandidate
    diagnosis: DiagnosisResult
    applied_config_dict: Dict[str, Any]
    failed_case_retest: EvaluationResult
    regression_suite_report: SuiteReport
    comparison_report: ComparisonReport
    safety_passed: bool
    retest_passed: bool
    is_acceptable: bool
    decision_reason: str
    decision_timestamp: Optional[str] = None


class AutofixCoordinator:
    """
    Coordinates trace diagnosis, repair candidate generation, isolated trial testing,
    and recording human approval/rejection decisions without mutating the live agent.
    """

    def __init__(self, db_path: str, cases: Optional[List[Case]] = None):
        self.db_path = db_path
        self.cases_list = cases or build_canonical_case_list()
        self.cases_dict = {c.case_id: c for c in self.cases_list}
        init_db(self.db_path)
        self.diagnosis_tools = TraceStoreDiagnosisTools(
            self.db_path,
            case_expectations_from_cases(self.cases_list),
        )

    def diagnose_run(self, run_id: str, goal: Optional[str] = None) -> DiagnosisResult:
        """Run read-only trace diagnosis on a persisted run."""
        req = DiagnosisRequest(
            run_ids=(run_id,),
            goal=goal or f"Diagnose failure in run {run_id}",
        )
        return diagnose(req, self.diagnosis_tools)

    def get_source_run_config(self, run_id: str) -> Tuple[AgentConfig, Dict[str, Any]]:
        """
        Reconstructs the actual saved AgentConfig and settings dictionary used by run_id
        from its persisted config_snapshot.
        """
        stored = get_run_trace(self.db_path, run_id)
        if not stored or not stored.run:
            raise ValueError(f"Run {run_id} not found in trace store.")
        snapshot_str = stored.run.config_snapshot
        snapshot = json.loads(snapshot_str) if snapshot_str else {}

        # Reconstruct AgentConfig
        version = stored.run.agent_version or snapshot.get("version", "v1.0.0")
        if "fastfail" in version or snapshot.get("version") == "v0.9.0-fastfail":
            base_ref = get_baseline_fast_fail_config()
        else:
            base_ref = get_default_config()

        cfg = AgentConfig(
            version=version,
            max_steps=snapshot.get("max_steps", base_ref.max_steps),
            max_tool_calls=snapshot.get("max_tool_calls", base_ref.max_tool_calls),
            tool_timeout_ms=snapshot.get("tool_timeout_ms", base_ref.tool_timeout_ms),
            run_timeout_ms=snapshot.get("run_timeout_ms", base_ref.run_timeout_ms),
            retry_count=snapshot.get("retry_count", base_ref.retry_count),
            clarification_prompt=snapshot.get("clarification_prompt", base_ref.clarification_prompt),
            strict_policy_verification=snapshot.get("strict_policy_verification", base_ref.strict_policy_verification),
            validate_response=snapshot.get("validate_response", base_ref.validate_response),
        )

        settings = {
            "tools": {
                "lookup_order_details": {"retry_count": cfg.retry_count},
            },
            "agent": {
                "clarification_instruction": cfg.clarification_prompt,
            },
        }
        return cfg, settings

    def propose_candidate_from_diagnosis(
        self,
        run_id: str,
        diagnosis: DiagnosisResult,
        current_settings: Optional[Mapping[str, Any]] = None,
    ) -> RepairCandidate:
        """
        Derive an allowlisted RepairCandidate from verified trace evidence,
        using the actual saved configuration of the failed run.
        """
        if current_settings is None:
            _, current_settings = self.get_source_run_config(run_id)

        summary = self.diagnosis_tools.get_failure_summary(run_id)
        evidence_ids = diagnosis.cited_evidence_event_ids
        if not evidence_ids:
            raise ValueError("Cannot propose candidate: diagnosis has no cited trace evidence.")

        cat = summary.category
        repair_id = f"repair-{uuid.uuid4().hex[:8]}"

        if cat in (DiagnosisCategory.TOOL_TIMEOUT, "tool_timeout"):
            curr_retries = current_settings.get("tools", {}).get("lookup_order_details", {}).get("retry_count", 0)
            new_retries = curr_retries + 1 if curr_retries < 2 else 2
            return RepairCandidate(
                repair_id=repair_id,
                source_run_ids=(run_id,),
                setting_path="tools.lookup_order_details.retry_count",
                old_value=curr_retries,
                new_value=new_retries,
                rationale=f"Trace evidence shows read-only lookup tool timeout ({evidence_ids[0]}). Bounded retry from {curr_retries} to {new_retries}.",
                evidence_event_ids=evidence_ids,
            )

        elif cat in (DiagnosisCategory.MISSING_ORDER_ID, "missing_order_id"):
            old_inst = current_settings.get("agent", {}).get("clarification_instruction", "")
            return RepairCandidate(
                repair_id=repair_id,
                source_run_ids=(run_id,),
                setting_path="agent.clarification_instruction",
                old_value=old_inst,
                new_value="Ask the user for the order ID when it is missing, before calling order lookup tools.",
                rationale=f"Trace evidence shows missing order ID before lookup ({evidence_ids[0]}). Standardize clarification instruction.",
                evidence_event_ids=evidence_ids,
            )

        else:
            raise ValueError(f"No allowlisted repair setting available for failure category {cat}.")

    def execute_repair_trial(
        self,
        candidate: RepairCandidate,
        base_config: Optional[AgentConfig] = None,
        base_settings: Optional[Mapping[str, Any]] = None,
    ) -> AutofixTrialResult:
        """
        Applies candidate to an isolated configuration copy, tests the failed case,
        runs the regression suite, compares against baseline, and determines acceptability.
        Uses the source run's actual saved configuration by default.
        The live/base configuration is never mutated.
        """
        source_run_id = candidate.source_run_ids[0]
        if base_config is None or base_settings is None:
            actual_cfg, actual_settings = self.get_source_run_config(source_run_id)
            if base_config is None:
                base_config = actual_cfg
            if base_settings is None:
                base_settings = actual_settings

        base_cfg = base_config

        # 1. Validate candidate provenance and allowlist
        stored_trace = get_run_trace(self.db_path, candidate.source_run_ids[0])
        avail_runs = {candidate.source_run_ids[0]}
        avail_events = {e.event_id for e in stored_trace.events}

        validation = validate_candidate(candidate, base_settings, avail_runs, avail_events)
        if not validation.valid:
            raise CandidateValidationError(validation.rejection_reasons)

        # 2. Apply to copy only
        copied_settings = apply_candidate_to_copy(
            candidate, base_settings, avail_runs, avail_events
        )

        # 3. Construct candidate AgentConfig from copy
        new_retry_count = base_cfg.retry_count
        new_clarification = base_cfg.clarification_prompt

        if candidate.setting_path == "tools.lookup_order_details.retry_count":
            new_retry_count = int(candidate.new_value)
        elif candidate.setting_path == "agent.clarification_instruction":
            new_clarification = str(candidate.new_value)

        candidate_version = f"{base_cfg.version}-repaired-{candidate.repair_id[:6]}"
        candidate_config = AgentConfig(
            version=candidate_version,
            max_steps=base_cfg.max_steps,
            max_tool_calls=base_cfg.max_tool_calls,
            tool_timeout_ms=base_cfg.tool_timeout_ms,
            run_timeout_ms=base_cfg.run_timeout_ms,
            retry_count=new_retry_count,
            clarification_prompt=new_clarification,
            strict_policy_verification=base_cfg.strict_policy_verification,
            validate_response=base_cfg.validate_response,
        )

        # 4. Retest the specific failed source case
        source_case_id = stored_trace.run.case_id
        target_case = self.cases_dict.get(source_case_id)
        if not target_case:
            raise ValueError(f"Source case {source_case_id} not in canonical cases.")

        retest_run_id = f"RUN-CAND-RETEST-{uuid.uuid4().hex[:6]}"
        retest_input = AgentInput(
            case_id=target_case.case_id,
            run_id=retest_run_id,
            agent_version=candidate_version,
            user_message=target_case.input.user_message,
            customer_id=target_case.input.customer_id,
            context=target_case.input.context,
        )

        candidate_agent = SupportAgent(config=candidate_config)
        run_and_record(
            candidate_agent,
            retest_input,
            self.db_path,
            config_role=CONFIG_ROLE_CANDIDATE,
            baseline_run_id=candidate.source_run_ids[0],
        )

        retest_res, retest_events = load_run_for_evaluation(self.db_path, retest_run_id)
        retest_eval = evaluate(target_case, retest_res, retest_events)
        save_evaluation(self.db_path, retest_eval.to_record())

        cand_suite_report = run_suite_evaluation(
            agent=candidate_agent,
            cases=self.cases_list,
            db_path=self.db_path,
            config_role=CONFIG_ROLE_CANDIDATE,
            baseline_run_id_map={c.case_id: candidate.source_run_ids[0] for c in self.cases_list},
        )

        # 6. Run or gather baseline comparison
        base_agent = SupportAgent(config=base_cfg)
        base_suite_report = run_suite_evaluation(
            agent=base_agent,
            cases=self.cases_list,
            db_path=self.db_path,
            config_role=CONFIG_ROLE_ORIGINAL,
        )

        comp = compare_agents(base_suite_report, cand_suite_report)

        safety_ok = comp.safety_status == "PASS"
        retest_ok = retest_eval.passed
        no_regressions = comp.verdict in ("ACCEPTED", "NEUTRAL") and comp.regression_rate.get("regressed_count", 0) == 0

        is_acceptable = safety_ok and retest_ok and no_regressions
        if not retest_ok:
            reason = "Candidate failed to resolve the target failed case."
        elif not safety_ok:
            reason = "Candidate triggered safety policy violations."
        elif not no_regressions:
            reason = f"Candidate introduced {comp.regression_rate.get('regressed_count', 0)} regression(s) on previously passing cases."
        else:
            reason = "Candidate resolved target failure without regressions or safety violations."

        diag = self.diagnose_run(candidate.source_run_ids[0])

        return AutofixTrialResult(
            candidate=candidate,
            diagnosis=diag,
            applied_config_dict=copied_settings,
            failed_case_retest=retest_eval,
            regression_suite_report=cand_suite_report,
            comparison_report=comp,
            safety_passed=safety_ok,
            retest_passed=retest_ok,
            is_acceptable=is_acceptable,
            decision_reason=reason,
        )

    def record_human_decision(
        self,
        candidate: RepairCandidate,
        decision: ApprovalStatus,
    ) -> RepairCandidate:
        """
        Records human approval or rejection of a candidate in memory and persists it to SQLite.
        Does NOT automatically mutate or overwrite the live agent configuration.
        """
        now = datetime.now(timezone.utc).isoformat()
        decision_val = decision.value if hasattr(decision, "value") else str(decision)
        record = HumanDecisionRecord(
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            repair_id=candidate.repair_id,
            source_run_id=candidate.source_run_ids[0],
            decision=decision_val,
            setting_path=candidate.setting_path,
            old_value=str(candidate.old_value),
            new_value=str(candidate.new_value),
            timestamp=now,
            rationale=candidate.rationale,
        )
        save_human_decision(self.db_path, record)

        return RepairCandidate(
            repair_id=candidate.repair_id,
            source_run_ids=candidate.source_run_ids,
            setting_path=candidate.setting_path,
            old_value=candidate.old_value,
            new_value=candidate.new_value,
            rationale=candidate.rationale,
            test_status=CandidateTestStatus.PASSED if candidate.test_status != CandidateTestStatus.FAILED else CandidateTestStatus.FAILED,
            approval_status=decision,
            evidence_event_ids=candidate.evidence_event_ids,
        )

    def get_latest_decision_for_run(self, run_id: str) -> Optional[HumanDecisionRecord]:
        """Fetch the most recent persisted human decision for a given source run."""
        decisions = list_human_decisions(self.db_path, source_run_id=run_id)
        return decisions[0] if decisions else None
