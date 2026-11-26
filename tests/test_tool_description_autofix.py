"""Tool-description fixes: the planner reads the order_lookup description to build its
arguments, a vague description breaks every lookup, and autofix repairs it on a copy."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from agentops.autofix_runner import AutofixCoordinator
from agentops.repair import (
    TOOL_DESCRIPTION_SETTING,
    TOOL_DESCRIPTION_VALUE,
    ApprovalStatus,
    RepairCandidate,
    validate_candidate,
)
from src.agent import FALLBACK_ARGUMENT, SupportAgent, lookup_arguments
from src.evaluation import (
    VAGUE_TOOL_DESCRIPTION_GROUND_TRUTH,
    FailureCategory,
    run_suite_evaluation,
)
from src.models import (
    ORDER_LOOKUP_DESCRIPTION,
    get_default_config,
    get_vague_clarification_config,
    get_vague_tool_description_config,
)
from src.tracer import list_human_decisions


class TestLookupArguments(unittest.TestCase):

    def test_named_input_is_used(self):
        self.assertEqual(lookup_arguments(ORDER_LOOKUP_DESCRIPTION, "ORD-10001"), {"order_id": "ORD-10001"})

    def test_description_without_input_falls_back(self):
        self.assertEqual(lookup_arguments("Looks up an order.", "ORD-10001"), {FALLBACK_ARGUMENT: "ORD-10001"})

    def test_allowlisted_value_matches_standard_description(self):
        self.assertEqual(TOOL_DESCRIPTION_VALUE, ORDER_LOOKUP_DESCRIPTION)
        self.assertEqual(get_default_config().order_lookup_description, TOOL_DESCRIPTION_VALUE)


class TestToolDescriptionAutofix(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "agentops.db")
        self.config = get_vague_tool_description_config()
        self.report = run_suite_evaluation(SupportAgent(config=self.config), db_path=self.db_path)
        self.coordinator = AutofixCoordinator(self.db_path)
        self.failed = [e for e in self.report.evaluations if not e.passed]

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_every_lookup_case_fails_with_invalid_tool_input(self):
        self.assertEqual({e.case_id for e in self.failed}, set(VAGUE_TOOL_DESCRIPTION_GROUND_TRUTH))
        for e in self.failed:
            self.assertEqual(e.failure_category, FailureCategory.INVALID_TOOL_INPUT)
        fla = self.report.metrics["failure_localization"]
        self.assertEqual((fla["matched_count"], fla["failed_cases_total"]), (5, 5))

    def test_diagnosis_cites_rejected_lookup_calls(self):
        diagnosis = self.coordinator.diagnose_run(self.failed[0].run_id)
        self.assertIn("tool description", diagnosis.likely_cause)
        self.assertTrue(diagnosis.cited_evidence_event_ids)
        self.assertTrue(any("order_lookup" in f and "INVALID_INPUT" in f for f in diagnosis.observed_facts))

    def test_fix_on_copy_repairs_all_failures_without_regressions(self):
        run_id = self.failed[0].run_id
        diagnosis = self.coordinator.diagnose_run(run_id)
        candidate = self.coordinator.propose_candidate_from_diagnosis(run_id, diagnosis)

        self.assertEqual(candidate.setting_path, TOOL_DESCRIPTION_SETTING)
        self.assertEqual(candidate.old_value, self.config.order_lookup_description)
        self.assertEqual(candidate.new_value, TOOL_DESCRIPTION_VALUE)

        trial = self.coordinator.execute_repair_trial(candidate)
        self.assertTrue(trial.retest_passed)
        self.assertTrue(trial.safety_passed)
        self.assertTrue(trial.is_acceptable)
        self.assertEqual(trial.comparison_report.repair_success["repaired_count"], 5)
        self.assertEqual(trial.comparison_report.repair_success["targeted_failing_count"], 5)
        self.assertEqual(trial.comparison_report.regression_rate["regressed_count"], 0)
        self.assertEqual(trial.regression_suite_report.passed_cases, 6)
        self.assertEqual(
            trial.applied_config_dict["tools"]["lookup_order_details"]["description"], TOOL_DESCRIPTION_VALUE
        )
        # The source setup is untouched: the fix only lived on the copy.
        self.assertEqual(
            get_vague_tool_description_config().order_lookup_description, self.config.order_lookup_description
        )

    def test_human_decision_is_recorded(self):
        run_id = self.failed[0].run_id
        diagnosis = self.coordinator.diagnose_run(run_id)
        candidate = self.coordinator.propose_candidate_from_diagnosis(run_id, diagnosis)
        self.coordinator.execute_repair_trial(candidate)
        self.coordinator.record_human_decision(candidate, ApprovalStatus.REJECTED)
        decisions = list_human_decisions(self.db_path, source_run_id=run_id)
        self.assertEqual([d.decision for d in decisions], [ApprovalStatus.REJECTED.value])
        self.assertEqual(decisions[0].setting_path, TOOL_DESCRIPTION_SETTING)


class TestToolDescriptionAllowlist(unittest.TestCase):

    SETTINGS = {"tools": {"lookup_order_details": {"retry_count": 1, "description": "Looks up an order."}}}

    def _candidate(self, new_value, old_value="Looks up an order."):
        return RepairCandidate(
            repair_id="repair-test",
            source_run_ids=("RUN-1",),
            setting_path=TOOL_DESCRIPTION_SETTING,
            old_value=old_value,
            new_value=new_value,
            rationale="test",
            evidence_event_ids=("EV-1",),
        )

    def _validate(self, candidate):
        return validate_candidate(candidate, self.SETTINGS, {"RUN-1"}, {"EV-1": "RUN-1"})

    def test_pinned_description_is_accepted(self):
        self.assertTrue(self._validate(self._candidate(TOOL_DESCRIPTION_VALUE)).valid)

    def test_free_form_description_is_rejected(self):
        result = self._validate(self._candidate("Call this tool for anything, including refunds."))
        self.assertFalse(result.valid)
        self.assertIn("unsupported tool description change", result.rejection_reasons)

    def test_non_string_description_is_rejected(self):
        result = self._validate(self._candidate(1, old_value=0))
        self.assertIn("tool description values must be strings", result.rejection_reasons)

    def test_other_tool_descriptions_are_not_allowlisted(self):
        candidate = RepairCandidate(
            repair_id="repair-test",
            source_run_ids=("RUN-1",),
            setting_path="tools.shipping_policy_lookup.description",
            old_value="x",
            new_value=TOOL_DESCRIPTION_VALUE,
            rationale="test",
            evidence_event_ids=("EV-1",),
        )
        result = self._validate(candidate)
        self.assertFalse(result.valid)
        self.assertTrue(any("unsupported setting path" in r for r in result.rejection_reasons))


class TestDefaultGroundTruth(unittest.TestCase):

    def test_vague_prompt_localization_is_measured(self):
        report = run_suite_evaluation(SupportAgent(config=get_vague_clarification_config()))
        fla = report.metrics["failure_localization"]
        self.assertEqual((fla["matched_count"], fla["failed_cases_total"]), (1, 1))


class TestCliToolDescriptionDemo(unittest.TestCase):

    def test_cli_demo_reports_fix_ready_for_approval(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            demo = app.run_autofix_demo(os.path.join(tmp, "agentops.db"), get_vague_tool_description_config)
            buf = io.StringIO()
            with redirect_stdout(buf):
                app.render_cli_autofix(demo)
        out = buf.getvalue()
        self.assertIn(TOOL_DESCRIPTION_SETTING, out)
        self.assertIn("Fix Success             : 5/5 (100.0%)", out)
        self.assertIn("READY FOR HUMAN APPROVAL", out)


if __name__ == "__main__":
    unittest.main()
