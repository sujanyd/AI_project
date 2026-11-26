"""AgentOps: deterministic read-only diagnosis, allowlisted repair, and autofix coordination."""

from .diagnosis import (
    CaseExpectation,
    DiagnosisEvidence,
    DiagnosisLimitExceeded,
    DiagnosisRequest,
    DiagnosisResult,
    FailureCategory,
    FailureSummary,
    RunInspection,
    TraceEvent,
    diagnose,
    get_case_expectation,
    get_failure_summary,
    get_run_trace,
)
from .repair import (
    ApprovalStatus,
    CandidateEvaluator,
    CandidateTestStatus,
    EvaluationResult,
    RepairCandidate,
    RepairEvaluationError,
    RepairReview,
    RepairReviewStatus,
    apply_candidate_to_copy,
    decide_repair_review,
    review_candidate,
    validate_candidate,
)

# autofix_runner imports src.trace_diagnosis, which imports agentops.diagnosis.
# Loading it lazily keeps `import src.trace_diagnosis` working on its own.
_LAZY_AUTOFIX = {"AutofixCoordinator", "AutofixTrialResult"}


def __getattr__(name):
    if name in _LAZY_AUTOFIX:
        from . import autofix_runner

        return getattr(autofix_runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ApprovalStatus",
    "AutofixCoordinator",
    "AutofixTrialResult",
    "CandidateEvaluator",
    "CandidateTestStatus",
    "CaseExpectation",
    "DiagnosisEvidence",
    "DiagnosisLimitExceeded",
    "DiagnosisRequest",
    "DiagnosisResult",
    "EvaluationResult",
    "FailureCategory",
    "FailureSummary",
    "RepairCandidate",
    "RepairEvaluationError",
    "RepairReview",
    "RepairReviewStatus",
    "RunInspection",
    "TraceEvent",
    "apply_candidate_to_copy",
    "decide_repair_review",
    "diagnose",
    "get_case_expectation",
    "get_failure_summary",
    "get_run_trace",
    "review_candidate",
    "validate_candidate",
]
