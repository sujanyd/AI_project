"""Execution-limit failures: evaluator classification, localization accuracy,
trace-backed diagnosis, and the autofix allowlist refusing to touch budgets."""

import os
import tempfile
import unittest

from agentops.autofix_runner import AutofixCoordinator
from src.agent import SupportAgent
from src.evaluation import (
    FAST_FAIL_GROUND_TRUTH,
    Evaluator,
    FailureCategory,
    build_canonical_cases,
    run_baseline_comparison,
)
from src.models import AgentInput, AgentResult, AgentStatus, StopReason, get_baseline_fast_fail_config
from src.trace_recorder import run_and_record
from src.tracer import CONFIG_ROLE_ORIGINAL


class TestLimitExceededClassification(unittest.TestCase):

    def setUp(self):
        self.cases = build_canonical_cases()
        self.evaluator = Evaluator()

    def _limit_result(self, case_id, error_code="MAX_STEPS_EXCEEDED"):
        return AgentResult(
            case_id=case_id,
            run_id=f"RUN-LIMIT-{case_id}",
            agent_version="v0.9.0-fastfail",
            status=AgentStatus.LIMIT_EXCEEDED,
            answer="Step limit exceeded.",
            stop_reason=StopReason.MAX_STEPS,
            error_code=error_code,
        )

    def test_step_limit_on_ordinary_case_is_limit_exceeded(self):
        case = self.cases["CASE-001-ORDINARY"]
        res = self.evaluator.evaluate(case, self._limit_result(case.case_id))
        self.assertFalse(res.passed)
        self.assertEqual(res.failure_category, FailureCategory.LIMIT_EXCEEDED)

    def test_step_limit_beats_injected_fault_mode(self):
        # CASE-006 injects conflicting records, but a run stopped by its step budget
        # never reached the conflict check, so the fault mode must not be blamed.
        case = self.cases["CASE-006-CONFLICTING-INFO"]
        res = self.evaluator.evaluate(case, self._limit_result(case.case_id))
        self.assertEqual(res.failure_category, FailureCategory.LIMIT_EXCEEDED)

    def test_tool_call_limit_is_limit_exceeded(self):
        case = self.cases["CASE-001-ORDINARY"]
        res = self.evaluator.evaluate(case, self._limit_result(case.case_id, "MAX_TOOL_CALLS_EXCEEDED"))
        self.assertEqual(res.failure_category, FailureCategory.LIMIT_EXCEEDED)


class TestFastFailLocalizationAccuracy(unittest.TestCase):

    def test_fast_fail_failures_match_ground_truth(self):
        baseline, candidate, _ = run_baseline_comparison()

        failed = {e.case_id: e.failure_category for e in candidate.evaluations if not e.passed}
        self.assertEqual(set(failed), set(FAST_FAIL_GROUND_TRUTH))
        for case_id, category in failed.items():
            self.assertEqual(category, FAST_FAIL_GROUND_TRUTH[case_id])

        fla = candidate.metrics["failure_localization"]
        self.assertEqual(fla["matched_count"], 2)
        self.assertEqual(fla["failed_cases_total"], 2)
        self.assertEqual(fla["localization_accuracy"], 1.0)

        # Baseline has no failures, so its FLA stays N/A rather than 0%.
        self.assertIsNone(baseline.metrics["failure_localization"]["localization_accuracy"])


class TestExecutionLimitDiagnosis(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "agentops.db")
        self.coordinator = AutofixCoordinator(self.db_path)
        agent = SupportAgent(config=get_baseline_fast_fail_config())
        self.run_id = "RUN-STEP-LIMIT"
        run_and_record(
            agent,
            AgentInput(
                case_id="CASE-001-ORDINARY",
                run_id=self.run_id,
                agent_version="v0.9.0-fastfail",
                customer_id="CUST-101",
                user_message="Hello, can you check the status of my order ORD-10001?",
            ),
            self.db_path,
            config_role=CONFIG_ROLE_ORIGINAL,
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_diagnosis_cites_limit_events(self):
        diagnosis = self.coordinator.diagnose_run(self.run_id)
        self.assertIn("budget", diagnosis.likely_cause.lower())
        self.assertTrue(diagnosis.cited_evidence_event_ids)
        self.assertTrue(any("MAX_STEPS_EXCEEDED" in fact for fact in diagnosis.observed_facts))

    def test_autofix_refuses_non_allowlisted_budget_change(self):
        diagnosis = self.coordinator.diagnose_run(self.run_id)
        with self.assertRaisesRegex(ValueError, "No allowlisted repair"):
            self.coordinator.propose_candidate_from_diagnosis(self.run_id, diagnosis)


if __name__ == "__main__":
    unittest.main()
