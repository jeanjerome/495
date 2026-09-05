"""Vocabulaire fermé du protocole CSAP 1.0."""

from enum import StrEnum


class PortName(StrEnum):
    AGENT = "agent"
    EXECUTION = "execution"
    REPOSITORY = "repository"
    APPROVAL = "approval"


class Operation(StrEnum):
    DESCRIBE = "describe"
    PREPARE = "prepare"
    START_AGENT = "start_agent"
    CAPTURE_CANDIDATE = "capture_candidate"
    RUN_CHECK = "run_check"
    GET_OPERATION = "get_operation"
    CANCEL_OPERATION = "cancel_operation"
    RELEASE = "release"
    INTEGRATE = "integrate"
    REQUEST_APPROVAL = "request_approval"


class OperationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class CheckOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    NOT_RUN = "NOT_RUN"


class ErrorCode(StrEnum):
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    UNSUPPORTED_PARAMETER = "UNSUPPORTED_PARAMETER"
    INVALID_INPUT = "INVALID_INPUT"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    ENVIRONMENT_UNAVAILABLE = "ENVIRONMENT_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    OUTPUT_INVALID = "OUTPUT_INVALID"
    INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"
    CONFLICT = "CONFLICT"
    OPERATION_UNKNOWN = "OPERATION_UNKNOWN"


LONG_OPERATIONS = frozenset(
    (
        Operation.START_AGENT,
        Operation.RUN_CHECK,
        Operation.INTEGRATE,
        Operation.REQUEST_APPROVAL,
    )
)

TERMINAL_STATUSES = frozenset(
    (OperationStatus.SUCCEEDED, OperationStatus.FAILED, OperationStatus.CANCELLED)
)

PORT_OPERATIONS = {
    PortName.AGENT: frozenset(
        (
            Operation.DESCRIBE,
            Operation.START_AGENT,
            Operation.GET_OPERATION,
            Operation.CANCEL_OPERATION,
        )
    ),
    PortName.EXECUTION: frozenset(
        (
            Operation.DESCRIBE,
            Operation.PREPARE,
            Operation.CAPTURE_CANDIDATE,
            Operation.RUN_CHECK,
            Operation.GET_OPERATION,
            Operation.CANCEL_OPERATION,
            Operation.RELEASE,
        )
    ),
    PortName.REPOSITORY: frozenset(
        (Operation.DESCRIBE, Operation.INTEGRATE, Operation.GET_OPERATION)
    ),
    PortName.APPROVAL: frozenset(
        (Operation.DESCRIBE, Operation.REQUEST_APPROVAL, Operation.GET_OPERATION)
    ),
}
