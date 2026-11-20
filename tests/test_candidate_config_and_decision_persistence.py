import os
import tempfile
import unittest

from agentops.autofix_runner import AutofixCoordinator
from agentops.repair import ApprovalStatus
from src.agent import SupportAgent
from src.evaluation import build_canonical_cases, evaluate
from src.models import (
    AgentConfig,
    AgentInput,
    get_baseline_fast_fail_config,
    get_default_config,
)
from src.trace_recorder import load_run_for_evaluation, run_and_record
from src.tracer import (
    CONFIG_ROLE_ORIGINAL,
    get_run_trace,
    init_db,
    list_evaluations,
    list_human_decisions,
    list_runs,
    save_evaluation,
)


class TestAutofixConfigurationMismatchAndPersistence(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "agentops.db")
        self.cases = build_canonical_cases()
        self.coordinator = AutofixCoordinator(self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_candidate_matches_source_run_actual_config(self):
        """
        Verify Item 1:
        When a failed run used fast-fail config (retry_count=0),
        the candidate proposal must recognize old_value=0 and new_value=1.
        It must not fail validation with an old-value mismatch against get_default_config() (retry_count=1).
        """
        fast_fail_cfg = get_baseline_fast_fail_config()
        self.assertEqual(fast_fail_cfg.retry_count, 0)

        run_id = "RUN-FASTFAIL-TIMEOUT"
        case = self.cases["CASE-005-TOOL-TIMEOUT"]
        inp = AgentInput(
            case_id="CASE-005-TOOL-TIMEOUT",
            run_id=run_id,
            agent_version=fast_fail_cfg.version,
            user_message="Status of ORD-TIMEOUT-TRANSIENT please.",
        )
        agent = SupportAgent(config=fast_fail_cfg)
        run_and_record(agent, inp, self.db_path, config_role=CONFIG_ROLE_ORIGINAL)

        # Record evaluation failure
        res, evs = load_run_for_evaluation(self.db_path, run_id)
        ev_record = evaluate(case, res, evs)
        save_evaluation(self.db_path, ev_record.to_record())

        # Diagnose
        diag = self.coordinator.diagnose_run(run_id)
        self.assertIn("timeout", diag.likely_cause.lower())

        # Propose candidate without passing explicit settings:
        # must automatically reconstruct settings from the saved run's config_snapshot!
        candidate = self.coordinator.propose_candidate_from_diagnosis(run_id, diag)
        self.assertEqual(candidate.setting_path, "tools.lookup_order_details.retry_count")
        self.assertEqual(candidate.old_value, 0)
        self.assertEqual(candidate.new_value, 1)

        # Trial execution must execute without old-value mismatch!
        trial = self.coordinator.execute_repair_trial(candidate)
        self.assertEqual(trial.candidate.old_value, 0)
        self.assertEqual(trial.applied_config_dict["tools"]["lookup_order_details"]["retry_count"], 1)
        self.assertTrue(trial.retest_passed)

    def test_human_decision_persists_in_sqlite(self):
        """
        Verify Item 3:
        Approval and rejection decisions are stored in SQLite and can be retrieved across reloads.
        """
        fast_fail_cfg = get_baseline_fast_fail_config()
        run_id = "RUN-PERSIST-TEST"
        case = self.cases["CASE-005-TOOL-TIMEOUT"]
        inp = AgentInput(
            case_id="CASE-005-TOOL-TIMEOUT",
            run_id=run_id,
            agent_version=fast_fail_cfg.version,
            user_message="Status of ORD-TIMEOUT-TRANSIENT please.",
        )
        agent = SupportAgent(config=fast_fail_cfg)
        run_and_record(agent, inp, self.db_path, config_role=CONFIG_ROLE_ORIGINAL)

        diag = self.coordinator.diagnose_run(run_id)
        cand = self.coordinator.propose_candidate_from_diagnosis(run_id, diag)

        # Record approval
        self.coordinator.record_human_decision(cand, ApprovalStatus.APPROVED)

        # Fetch directly from fresh connection/function
        decisions = list_human_decisions(self.db_path, source_run_id=run_id)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].decision, "approved")
        self.assertEqual(decisions[0].repair_id, cand.repair_id)
        self.assertEqual(decisions[0].source_run_id, run_id)
        self.assertIsNotNone(decisions[0].timestamp)

        # Check coordinator helper
        latest = self.coordinator.get_latest_decision_for_run(run_id)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.decision, "approved")


if __name__ == "__main__":
    unittest.main()
