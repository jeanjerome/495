"""Enveloppes et résultats immuables du protocole."""

from dataclasses import dataclass
from typing import Generic, TypeAlias, TypeVar

from domain.references import ArtifactRef

from .canonical import FrozenJson
from .vocabulary import ErrorCode, Operation, OperationStatus, PortName


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ProtocolError:
    code: ErrorCode
    subject: str
    retryable: bool = False
    details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProtocolAccepted(Generic[T]):
    value: T


@dataclass(frozen=True, slots=True)
class ProtocolRejected:
    error: ProtocolError


ProtocolOutcome: TypeAlias = ProtocolAccepted[T] | ProtocolRejected


@dataclass(frozen=True, slots=True)
class Extension:
    name: str
    required: bool
    value: FrozenJson


@dataclass(frozen=True, slots=True)
class Request:
    protocol_version: str
    request_id: str
    idempotency_key: str
    operation: Operation
    increment_id: str | None
    attempt_id: str | None
    contract_ref: ArtifactRef | None
    payload: FrozenJson
    extensions: tuple[Extension, ...]


@dataclass(frozen=True, slots=True)
class AdapterDescription:
    identity: str
    adapter_version: str
    protocol_versions: tuple[str, ...]
    ports: tuple[PortName, ...]
    operations: tuple[Operation, ...]
    platforms: tuple[str, ...] = ()
    toolchains: tuple[str, ...] = ()
    limits: tuple[tuple[str, int], ...] = ()
    isolation_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OperationEvent:
    cursor: int
    status: OperationStatus
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class OperationAccepted:
    operation_id: str
    status: OperationStatus
    replayed: bool


@dataclass(frozen=True, slots=True)
class OperationSnapshot:
    operation_id: str
    status: OperationStatus
    events: tuple[OperationEvent, ...]
    next_cursor: int
    result: FrozenJson | None
    error: ProtocolError | None


@dataclass(frozen=True, slots=True)
class CancellationAck:
    operation_id: str
    status: OperationStatus
    cancel_requested: bool


@dataclass(frozen=True, slots=True)
class ImmediateResult:
    operation: Operation
    result: FrozenJson
    replayed: bool


@dataclass(frozen=True, slots=True)
class ConformanceCase:
    case_id: str
    passed: bool
    details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    adapter_identity: str
    protocol_version: str | None
    cases: tuple[ConformanceCase, ...]
    syntax_conformant: bool
    security_qualified: bool = False
