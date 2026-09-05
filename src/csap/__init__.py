"""CSAP 1.0 et kit de conformité en processus."""

from .adapter import InProcessAdapter
from .conformance import run_conformance
from .model import (
    AdapterDescription,
    CancellationAck,
    ConformanceCase,
    ConformanceReport,
    Extension,
    ImmediateResult,
    OperationAccepted,
    OperationEvent,
    OperationSnapshot,
    ProtocolAccepted,
    ProtocolError,
    ProtocolRejected,
    Request,
)
from .negotiation import negotiate
from .validation import build_check_result, build_description, build_request
from .vocabulary import CheckOutcome, ErrorCode, Operation, OperationStatus, PortName

__all__ = (
    "AdapterDescription",
    "CancellationAck",
    "CheckOutcome",
    "ConformanceCase",
    "ConformanceReport",
    "ErrorCode",
    "Extension",
    "ImmediateResult",
    "InProcessAdapter",
    "Operation",
    "OperationAccepted",
    "OperationEvent",
    "OperationSnapshot",
    "OperationStatus",
    "PortName",
    "ProtocolAccepted",
    "ProtocolError",
    "ProtocolRejected",
    "Request",
    "build_check_result",
    "build_description",
    "build_request",
    "negotiate",
    "run_conformance",
)
