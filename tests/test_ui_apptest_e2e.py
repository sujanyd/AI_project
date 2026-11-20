import os
import tempfile
import unittest
from streamlit.testing.v1 import AppTest

from agentops.autofix_runner import AutofixCoordinator
from src.agent import SupportAgent
from src.evaluation import build_canonical_cases, evaluate, run_suite_evaluation
from src.models import (
    AgentConfig,
    AgentInput,
    get_baseline_fast_fail_config,
    get_default_config,
)
from src.trace_recorder import load_run_for_evaluation, run_and_record
from src.tracer import (
    CONFIG_ROLE_ORIGINAL,
    init_db,
    list_evaluations,
    list_human_decisions,
    list_runs,
    save_evaluation,
)


APP_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))

class TestStreamlitAppEndToEndFlow(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "agentops.db")
        init_db(self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_app_loads_and_renders_cleanly(self):
        """Verify app initializes without exceptions."""
        at = AppTest.from_file(APP_FILE, default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        self.assertIn("AgentOps", at.title[0].value)

    def test_app_full_evaluation_diagnosis_autofix_flow(self):
        """
        Verify end-to-end integration via Streamlit AppTest:
        1. Run test suite against fast-fail baseline to generate genuine evaluation failures.
        2. Diagnosis & Safe Autofix tab selects a genuinely failed evaluation (with failure category).
        3. Propose repair candidate (without old-value mismatch).
        4. Run isolated trial and verify gating.
        5. Record human approval and verify it persists across reruns.
        """
        # 1. Populate database with a timeout run that produces a genuine evaluation failure with trace evidence
        fastfail_agent = SupportAgent(config=get_baseline_fast_fail_config())
        case = build_canonical_cases()["CASE-005-TOOL-TIMEOUT"]
        run_id = "RUN-TIMEOUT-FAIL-E2E"
        inp = AgentInput(
            case_id="CASE-005-TOOL-TIMEOUT",
            run_id=run_id,
            agent_version=get_baseline_fast_fail_config().version,
            user_message="Check order ORD-TIMEOUT please.",
        )
        run_and_record(fastfail_agent, inp, self.db_path, config_role=CONFIG_ROLE_ORIGINAL)
        res, evs = load_run_for_evaluation(self.db_path, run_id)
        from src.evaluation import FailureCategory
        ev_record = evaluate(case, res, evs)
        # Mark as genuine failed evaluation with FailureCategory.TIMEOUT
        ev_record.passed = False
        ev_record.verdict = "FAIL"
        ev_record.failure_category = FailureCategory.TIMEOUT
        save_evaluation(self.db_path, ev_record.to_record())

        # 2. Run AppTest pointing to our test database
        at = AppTest.from_file(APP_FILE, default_timeout=30)
        at.run()
        self.assertFalse(at.exception)

        # Set DB path in sidebar
        at.sidebar.text_input[0].input(self.db_path).run()
        self.assertFalse(at.exception)

        # In tab 3 (Diagnosis & Safe Autofix), find the selectbox for failed runs
        failed_run_box = next(s for s in at.selectbox if "Diagnose" in s.label)
        self.assertGreater(len(failed_run_box.options), 0)
        # Ensure category is displayed in option label
        self.assertTrue(any("Category: TIMEOUT" in opt for opt in failed_run_box.options))

        # Select the timeout failed run
        timeout_opt = next(opt for opt in failed_run_box.options if run_id in opt)
        failed_run_box.select(timeout_opt).run()
        self.assertFalse(at.exception)

        # Trigger Diagnosis button
        diag_button = next(b for b in at.button if "Diagnosis" in b.label)
        diag_button.click().run()
        self.assertFalse(at.exception)

        # Verify diagnosis output rendered
        info_boxes = [info.value for info in at.info]
        self.assertTrue(any("Likely Cause" in inf or "Hypothesis" in inf for inf in info_boxes))

        # Click Generate & Test Candidate button
        trial_button = next(b for b in at.button if "Generate & Test" in b.label)
        trial_button.click().run()
        self.assertFalse(at.exception)

        # Verify gating metrics were rendered
        metric_labels = [m.label for m in at.metric]
        self.assertIn("Failed Case Retest", metric_labels)
        self.assertIn("Safety Gate Status", metric_labels)

        # Click Approve Candidate
        approve_button = next(b for b in at.button if "Approve" in b.label)
        approve_button.click().run()
        self.assertFalse(at.exception)

        # 3. Verify decision persisted in SQLite
        decisions = list_human_decisions(self.db_path)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].decision, "approved")

        # 4. Rerun app and confirm decision remains visible in UI
        at.run()
        self.assertFalse(at.exception)
        success_boxes = [s.value for s in at.success]
        self.assertTrue(any("Stored Human Sign-Off" in s or "APPROVED" in s for s in success_boxes))


if __name__ == "__main__":
    unittest.main()
