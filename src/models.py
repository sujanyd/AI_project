from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class AgentStatus(str, Enum):
    SUCCESS = "SUCCESS"
    CLARIFICATION_NEEDED = "CLARIFICATION_NEEDED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"


class StopReason(str, Enum):
    GOAL_REACHED = "GOAL_REACHED"
    NEED_USER_INPUT = "NEED_USER_INPUT"
    UNRESOLVABLE_CONFLICT = "UNRESOLVABLE_CONFLICT"
    ERROR_ABORT = "ERROR_ABORT"
    MAX_STEPS = "MAX_STEPS"
    MAX_TOOL_CALLS = "MAX_TOOL_CALLS"
    TIME_EXCEEDED = "TIME_EXCEEDED"
    UNSUPPORTED_REQUEST = "UNSUPPORTED_REQUEST"


# Description the planner reads to build order_lookup arguments. It names the input
# parameter ("Input: order_id"), so the planner sends the order ID under that key.
ORDER_LOOKUP_DESCRIPTION = (
    "Read-only lookup of a single order. Input: order_id (format ORD-XXXXX). "
    "Returns status, items, total and shipping_method."
)


class EventType(str, Enum):
    PLANNING = "PLANNING"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    OBSERVATION = "OBSERVATION"
    VALIDATION = "VALIDATION"
    ERROR = "ERROR"
    SAFE_STOP = "SAFE_STOP"
    FINAL_STATUS = "FINAL_STATUS"


@dataclass
class AgentConfig:
    version: str = "v1.0.0"
    max_steps: int = 4
    max_tool_calls: int = 3
    tool_timeout_ms: float = 2000.0
    run_timeout_ms: float = 10000.0
    retry_count: int = 1
    clarification_prompt: str = "Please provide your Order ID (format ORD-XXXXX) so I can assist you."
    strict_policy_verification: bool = True
    validate_response: bool = True
    order_lookup_description: str = ORDER_LOOKUP_DESCRIPTION


def get_default_config() -> AgentConfig:
    """Standard baseline agent configuration (v1.0.0): resilient retries and validation."""
    return AgentConfig(
        version="v1.0.0",
        max_steps=4,
        max_tool_calls=3,
        tool_timeout_ms=2000.0,
        run_timeout_ms=10000.0,
        retry_count=1,
        clarification_prompt="Please provide your Order ID (format ORD-XXXXX) so I can assist you.",
        strict_policy_verification=True,
        validate_response=True,
    )


def get_vague_clarification_config() -> AgentConfig:
    """
    Controlled demo configuration (v0.9.1-vague-prompt) that autofix can repair:
    identical to v1.0.0 except its clarification prompt never asks for the Order ID,
    so CASE-002 fails. The fix lies inside the autofix allowlist
    (agent.clarification_instruction).
    """
    cfg = get_default_config()
    cfg.version = "v0.9.1-vague-prompt"
    cfg.clarification_prompt = "Thanks for reaching out! Could you tell me a bit more?"
    return cfg


def get_vague_tool_description_config() -> AgentConfig:
    """
    Controlled demo configuration (v0.9.2-vague-tool-description) that autofix can repair:
    identical to v1.0.0 except the order_lookup tool description never names its input
    parameter, so the planner sends the wrong argument and every lookup is rejected with
    INVALID_INPUT. The fix lies inside the autofix allowlist
    (tools.lookup_order_details.description).
    """
    cfg = get_default_config()
    cfg.version = "v0.9.2-vague-tool-description"
    cfg.order_lookup_description = "Looks up an order."
    return cfg


def get_baseline_fast_fail_config() -> AgentConfig:
    """
    Controlled second agent configuration (v0.9.0-fastfail) for baseline comparison:
    - Zero tool retries (fails fast on transient timeouts).
    - Reduced max steps (2).
    - Skips optional downstream validation tool calls to minimize latency.
    """
    return AgentConfig(
        version="v0.9.0-fastfail",
        max_steps=2,
        max_tool_calls=2,
        tool_timeout_ms=1000.0,
        run_timeout_ms=5000.0,
        retry_count=0,
        clarification_prompt="Please provide your Order ID (format ORD-XXXXX) so I can assist you.",
        strict_policy_verification=False,
        validate_response=False,
    )


@dataclass
class AgentInput:
    case_id: str
    run_id: str
    agent_version: str
    user_message: str
    customer_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class ToolCallResult:
    tool_name: str
    call_id: str
    status: str  # "SUCCESS" | "ERROR"
    data: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, str]] = None  # {"error_code": ..., "message": ...}
    latency_ms: float = 0.0


@dataclass
class AgentResult:
    case_id: str
    run_id: str
    agent_version: str
    status: AgentStatus
    answer: str
    stop_reason: StopReason
    metrics: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    error: Optional[Dict[str, Any]] = None


@dataclass
class ObservableEvent:
    case_id: str
    run_id: str
    agent_version: str
    event_type: EventType
    step_index: int
    payload: Dict[str, Any]
    tool_name: Optional[str] = None
    timestamp: Optional[str] = None


EventCallback = Callable[[ObservableEvent], None]
