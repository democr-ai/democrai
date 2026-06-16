from __future__ import annotations

import re


ENGINE_NODE_CAPACITY_UNAVAILABLE = "engine_orchestrator_node_capacity_unavailable"
ENGINE_NODE_UNREACHABLE = "engine_orchestrator_node_unreachable"


def is_node_capacity_error(error: BaseException | str) -> bool:
    """Recognize the capacity-unavailable marker on an error message.

    The marker crosses job.fail/result-future as a plain string, so both the
    raiser (resolver) and the consumer (claim worker) must go through this
    single helper instead of ad-hoc string matching.
    """
    return ENGINE_NODE_CAPACITY_UNAVAILABLE in str(error or "")


class EngineInvocationError(RuntimeError):
    """Engine error with an explicit retry classification.

    Engines/providers raise this to state whether the failure is transient
    (quota, rate limit, upstream outage) or permanent (bad request, auth).
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = bool(retryable)
        self.retry_after_seconds = (
            None if retry_after_seconds is None else max(0.0, float(retry_after_seconds))
        )


_RETRYABLE_MARKERS = (
    "429",
    "rate limit",
    "rate_limit",
    "quota",
    "overloaded",
    "too many requests",
    "500",
    "502",
    "503",
    "504",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "timeout",
    "timed out",
    "temporarily",
    "connection reset",
    "connection refused",
    "connection error",
    "unavailable",
)

_TERMINAL_MARKERS = (
    "400",
    "401",
    "403",
    "404",
    "405",
    "409",
    "413",
    "422",
    "invalid_request",
    "invalid request",
    "unauthorized",
    "authentication",
    "forbidden",
    "not found",
    "not_found",
    "permission",
    "api key",
    "api_key",
    "context_length",
    "context length",
)

_RETRY_AFTER_PATTERN = re.compile(r"retry[-_ ]after[:= ]+(\d+(?:\.\d+)?)", re.IGNORECASE)


def classify_error_retryable(error: BaseException | str) -> bool | None:
    """Classify whether an engine error is worth retrying.

    Returns True (transient), False (permanent) or None when the message
    carries no recognizable signal — the caller picks its own default.
    Typed EngineInvocationError always wins over message sniffing.
    """
    if isinstance(error, EngineInvocationError):
        return error.retryable
    message = str(error).lower()
    if not message:
        return None
    for marker in _TERMINAL_MARKERS:
        if marker in message:
            return False
    for marker in _RETRYABLE_MARKERS:
        if marker in message:
            return True
    return None


def error_retry_after_seconds(error: BaseException | str) -> float | None:
    if isinstance(error, EngineInvocationError):
        return error.retry_after_seconds
    match = _RETRY_AFTER_PATTERN.search(str(error))
    if match:
        return float(match.group(1))
    return None


def retry_delay_seconds(attempts: int, *, retry_after: float | None = None) -> float:
    backoff = float(min(300, 2 ** max(1, int(attempts))))
    if retry_after is not None:
        return max(backoff, float(retry_after))
    return backoff
