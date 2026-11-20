import os
import tempfile
import unittest

from agentops.autofix_runner import AutofixCoordinator
from agentops.repair import ApprovalStatus, CandidateTestStatus, CandidateValidationError, RepairCandidate
from src.agent import SupportAgent
from src.evaluation import build_canonical_cases
from src.models import AgentConfig, AgentInput, get_baseline_fast_fail_config, get_default_config
from src.trace_recorder import load_run_for_evaluation, run_and_record
from src.tracer import CONFIG_ROLE_ORIGINAL, get_run_trace, list_runs


class TestAutofixCoordinator(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "agentops.db")
        self.cases = build_canonical_cases()
        self.coordinator = AutofixCoordinator(self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _create_failed_timeout_run(self, run_id="RUN-TIMEOUT-FAIL"):
        # fast_fail agent has retry_count=0 so ORD-TIMEOUT-TRANSIENT times out
        agent = SupportAgent(config=get_baseline_fast_fail_config())
        case = self.cases["CASE-005-TOOL-TIMEOUT"]
        inp = AgentInput(
            case_id="CASE-005-TOOL-TIMEOUT",
            run_id=run_id,
            agent_version="v0.9.0-fastfail",
            user_message="Status of ORD-TIMEOUT-TRANSIENT please.",
        )
        run_and_record(agent, inp, self.db_path, config_role=CONFIG_ROLE_ORIGINAL)
        return run_id

    def test_diagnosis_and_candidate_proposal(self):
        run_id = self._create_failed_timeout_run()
        diagnosis = self.coordinator.diagnose_run(run_id)

        self.assertIn("timeout", diagnosis.likely_cause.lower())
        self.assertTrue(diagnosis.cited_evidence_event_ids)

        candidate = self.coordinator.propose_candidate_from_diagnosis(run_id, diagnosis)
        self.assertEqual(candidate.setting_path, "tools.lookup_order_details.retry_count")
        self.assertEqual(candidate.old_value, 0)
        self.assertEqual(candidate.new_value, 1)
        self.assertEqual(candidate.source_run_ids, (run_id,))
        self.assertEqual(candidate.evidence_event_ids, diagnosis.cited_evidence_event_ids)

    def test_trial_execution_and_isolation(self):
        run_id = self._create_failed_timeout_run()
        diagnosis = self.coordinator.diagnose_run(run_id)
        candidate = self.coordinator.propose_candidate_from_diagnosis(run_id, diagnosis)

        base_cfg = get_baseline_fast_fail_config()
        base_settings = {
            "tools": {"lookup_order_details": {"retry_count": 0}},
            "agent": {"clarification_instruction": "Clarify missing info."},
        }

        trial_res = self.coordinator.execute_repair_trial(
            candidate,
            base_config=base_cfg,
            base_settings=base_settings,
        )

        # 1. Base settings must remain completely unmutated
        self.assertEqual(base_settings["tools"]["lookup_order_details"]["retry_count"], 0)
        # 2. Applied copy must have the new value
        self.assertEqual(trial_res.applied_config_dict["tools"]["lookup_order_details"]["retry_count"], 1)

        # 3. Retest of the failed case
        self.assertTrue(trial_res.retest_passed)
        self.assertTrue(trial_res.safety_passed)

        # 4. Traces of candidate runs must be stored and linked to baseline_run_id
        runs = list_runs(self.db_path)
        candidate_runs = [r for r in runs if r.config_role == "candidate"]
        self.assertGreater(len(candidate_runs), 0)
        for cr in candidate_runs:
            self.assertEqual(cr.baseline_run_id, run_id)

    def test_rejection_of_unallowlisted_or_fake_evidence(self):
        fake_candidate = RepairCandidate(
            repair_id="fake-001",
            source_run_ids=("RUN-UNKNOWN",),
            setting_path="agent.unsupported_param",
            old_value=1,
            new_value=2,
            rationale="Fake fix",
            evidence_event_ids=("fake-event-id",),
        )
        with self.assertRaises(Exception):
            self.coordinator.execute_repair_trial(fake_candidate)

    def test_human_approval_recording(self):
        run_id = self._create_failed_timeout_run()
        diagnosis = self.coordinator.diagnose_run(run_id)
        candidate = self.coordinator.propose_candidate_from_diagnosis(run_id, diagnosis)

        # Record approval
        approved = self.coordinator.record_human_decision(candidate, ApprovalStatus.APPROVED)
        self.assertEqual(approved.approval_status, ApprovalStatus.APPROVED)

        # Record rejection
        rejected = self.coordinator.record_human_decision(candidate, ApprovalStatus.REJECTED)
        self.assertEqual(rejected.approval_status, ApprovalStatus.REJECTED)


if __name__ == "__main__":
    unittest.main()
