"""The full loop: run -> trace -> evaluate -> diagnose -> autofix on a copy ->
re-test -> human decision, on the fixable vague-prompt demo setup."""

import importlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from agentops.autofix_runner import AutofixCoordinator
from agentops.repair import CLARIFICATION_VALUE, ApprovalStatus
from src.agent import SupportAgent
from src.evaluation import FailureCategory, run_suite_evaluation
from src.models import get_default_config, get_vague_clarification_config
from src.tracer import list_human_decisions

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestAutofixEndToEnd(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "agentops.db")
        self.config = get_vague_clarification_config()
        self.report = run_suite_evaluation(SupportAgent(config=self.config), db_path=self.db_path)
        self.coordinator = AutofixCoordinator(self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _failed(self):
        return [e for e in self.report.evaluations if not e.passed]

    def test_vague_prompt_fails_only_missing_id_case(self):
        failed = self._failed()
        self.assertEqual([e.case_id for e in failed], ["CASE-002-MISSING-ID"])
        self.assertEqual(failed[0].failure_category, FailureCategory.MISSING_INFORMATION)

    def test_diagnosis_cites_missing_order_id_events(self):
        diagnosis = self.coordinator.diagnose_run(self._failed()[0].run_id)
        self.assertIn("missing order ID", diagnosis.likely_cause)
        self.assertTrue(diagnosis.cited_evidence_event_ids)
        self.assertTrue(any("MISSING_ORDER_ID" in fact for fact in diagnosis.observed_facts))

    def test_fix_is_tested_on_copy_and_passes_all_gates(self):
        run_id = self._failed()[0].run_id
        diagnosis = self.coordinator.diagnose_run(run_id)
        candidate = self.coordinator.propose_candidate_from_diagnosis(run_id, diagnosis)

        self.assertEqual(candidate.setting_path, "agent.clarification_instruction")
        self.assertEqual(candidate.old_value, self.config.clarification_prompt)
        self.assertEqual(candidate.new_value, CLARIFICATION_VALUE)

        trial = self.coordinator.execute_repair_trial(candidate)
        self.assertTrue(trial.retest_passed)
        self.assertTrue(trial.safety_passed)
        self.assertTrue(trial.is_acceptable)
        self.assertEqual(trial.comparison_report.repair_success["repaired_count"], 1)
        self.assertEqual(trial.comparison_report.repair_success["targeted_failing_count"], 1)
        self.assertEqual(trial.comparison_report.regression_rate["regressed_count"], 0)
        self.assertEqual(trial.regression_suite_report.passed_cases, 6)

        # The source setup is untouched: the fix only lived on the copy.
        self.assertEqual(get_vague_clarification_config().clarification_prompt, self.config.clarification_prompt)

    def test_human_approval_is_recorded(self):
        run_id = self._failed()[0].run_id
        diagnosis = self.coordinator.diagnose_run(run_id)
        candidate = self.coordinator.propose_candidate_from_diagnosis(run_id, diagnosis)
        self.coordinator.execute_repair_trial(candidate)

        self.coordinator.record_human_decision(candidate, ApprovalStatus.APPROVED)
        decisions = list_human_decisions(self.db_path, source_run_id=run_id)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].decision, ApprovalStatus.APPROVED.value)
        self.assertEqual(decisions[0].new_value, CLARIFICATION_VALUE)

    def test_standard_agent_already_uses_the_allowlisted_prompt(self):
        self.assertEqual(get_default_config().clarification_prompt, CLARIFICATION_VALUE)


class TestCliAutofixDemo(unittest.TestCase):

    def test_cli_demo_reports_fix_ready_for_approval(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            demo = app.run_autofix_demo(os.path.join(tmp, "agentops.db"))
            buf = io.StringIO()
            with redirect_stdout(buf):
                app.render_cli_autofix(demo)
        out = buf.getvalue()
        self.assertIn("CASE-002-MISSING-ID", out)
        self.assertIn("Fix Success             : 1/1 (100.0%)", out)
        self.assertIn("READY FOR HUMAN APPROVAL", out)


class TestImportOrder(unittest.TestCase):

    def test_trace_diagnosis_imports_on_its_own(self):
        # Fresh interpreter: importing src.trace_diagnosis first used to hit a circular import.
        proc = subprocess.run(
            [sys.executable, "-c", "import src.trace_diagnosis"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_lazy_autofix_exports(self):
        agentops = importlib.import_module("agentops")
        self.assertIs(agentops.AutofixCoordinator, AutofixCoordinator)


if __name__ == "__main__":
    unittest.main()
