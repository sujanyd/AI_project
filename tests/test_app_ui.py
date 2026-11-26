"""The visual layer: pipeline state logic and HTML builders that must escape trace data."""

import unittest
from types import SimpleNamespace

import app_ui as ui


class TestPipelineStates(unittest.TestCase):

    def test_empty_store_starts_at_run(self):
        states = ui.pipeline_states(False, False, False, False, None, False)
        self.assertEqual(states["run"], "active")
        self.assertEqual(states["approve"], "idle")

    def test_all_passing_stops_after_evaluate(self):
        states = ui.pipeline_states(True, True, False, False, None, False)
        self.assertEqual([states[k] for k in ("run", "trace", "evaluate", "diagnose")], ["done", "done", "done", "idle"])

    def test_blocked_trial_marks_autofix_and_never_approve(self):
        states = ui.pipeline_states(True, True, True, True, False, False)
        self.assertEqual(states["autofix"], "blocked")
        self.assertEqual(states["approve"], "idle")

    def test_full_loop(self):
        states = ui.pipeline_states(True, True, True, True, True, True)
        self.assertTrue(all(state == "done" for state in states.values()))


class TestBuildersEscapeData(unittest.TestCase):

    HOSTILE = '<script>alert("x")</script>'

    def test_trace_timeline_escapes_event_text(self):
        event = SimpleNamespace(
            event_type="TOOL_RESULT", sequence_no=3, stage="tool_failure", tool_name="order_lookup",
            input=None, output='{"error": "%s"}' % self.HOSTILE.replace('"', "'"),
            status="ERROR", duration_ms=0.4, error_code="INVALID_INPUT",
        )
        out = ui.trace_timeline([event])
        self.assertNotIn("<script>", out)
        self.assertIn("ao-ev err", out)
        self.assertIn("INVALID_INPUT", out)

    def test_diff_and_bubble_escape(self):
        self.assertNotIn("<script>", ui.diff_card("a.b", self.HOSTILE, "new", self.HOSTILE))
        self.assertNotIn("<script>", ui.output_bubble(self.HOSTILE, "ERROR"))
        self.assertNotIn("<script>", ui.hypothesis_card(self.HOSTILE, "x", "y", [self.HOSTILE]))

    def test_metric_rings_handle_missing_rates(self):
        out = ui.metric_rings({"task_success": {"task_success_rate": 0.5, "passed_count": 3, "total_cases": 6}})
        self.assertIn("50%", out)
        self.assertIn("N/A", out)  # metrics with no data render as N/A, not 0%

    def test_case_grid_marks_pass_and_fail(self):
        evs = [
            SimpleNamespace(case_id="CASE-1", passed=True, failure_category=None, details={"observed_tool_calls": 1}, score=1.0),
            SimpleNamespace(case_id="CASE-2", passed=False, failure_category=SimpleNamespace(value="TIMEOUT"), details={}, score=0.4),
        ]
        out = ui.case_grid(evs, {"CASE-1": "ordinary"})
        self.assertIn("ao-badge pass", out)
        self.assertIn("ao-badge fail", out)
        self.assertIn("TIMEOUT", out)


if __name__ == "__main__":
    unittest.main()
