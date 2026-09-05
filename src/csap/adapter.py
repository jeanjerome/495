"""Adaptateur CSAP simulé, sans transport ni effet externe."""

from dataclasses import dataclass

from .canonical import FrozenJson, InvalidJsonValue, canonical_digest, freeze_json, thaw_json
from .model import (
    AdapterDescription,
    CancellationAck,
    ImmediateResult,
    OperationAccepted,
    OperationEvent,
    OperationSnapshot,
    ProtocolAccepted,
    ProtocolError,
    ProtocolOutcome,
    ProtocolRejected,
    Request,
)
from .validation import _reject, build_check_result, request_document
from .vocabulary import (
    LONG_OPERATIONS,
    TERMINAL_STATUSES,
    ErrorCode,
    Operation,
    OperationStatus,
)


@dataclass(frozen=True, slots=True)
class _OperationRecord:
    operation_id: str
    operation: Operation
    status: OperationStatus
    events: tuple[OperationEvent, ...]
    result: FrozenJson | None = None
    error: ProtocolError | None = None


class InProcessAdapter:
    def __init__(
        self,
        description: AdapterDescription,
        *,
        understood_extensions: frozenset[str] = frozenset(),
    ) -> None:
        self.description = description
        self.understood_extensions = understood_extensions
        self._idempotency: dict[str, tuple[str, object]] = {}
        self._operations: dict[str, _OperationRecord] = {}
        self._next_operation = 1

    def _fingerprint(self, request: Request) -> str:
        return canonical_digest(
            freeze_json(request_document(request, include_request_id=False))
        )

    def _remember(
        self, request: Request, fingerprint: str, response: object
    ) -> ProtocolAccepted[object]:
        self._idempotency[request.idempotency_key] = (fingerprint, response)
        return ProtocolAccepted(response)

    def _operation_payload(self, request: Request) -> dict[str, object] | None:
        payload = thaw_json(request.payload)
        return payload if isinstance(payload, dict) else None

    def _snapshot(self, operation_id: str, cursor: object) -> ProtocolOutcome[OperationSnapshot]:
        record = self._operations.get(operation_id)
        if record is None:
            return _reject(ErrorCode.OPERATION_UNKNOWN, operation_id)
        if isinstance(cursor, bool) or not isinstance(cursor, int) or not 0 <= cursor <= len(record.events):
            return _reject(ErrorCode.OPERATION_UNKNOWN, "cursor")
        return ProtocolAccepted(
            OperationSnapshot(
                operation_id,
                record.status,
                record.events[cursor:],
                len(record.events),
                record.result,
                record.error,
            )
        )

    def dispatch(self, request: Request) -> ProtocolOutcome[object]:
        if request.protocol_version not in self.description.protocol_versions:
            return _reject(ErrorCode.UNSUPPORTED_VERSION, "protocol_version")
        if request.operation not in self.description.operations:
            return _reject(ErrorCode.AUTHORIZATION_DENIED, request.operation.value)
        unknown_required = tuple(
            extension.name
            for extension in request.extensions
            if extension.required and extension.name not in self.understood_extensions
        )
        if unknown_required:
            return _reject(ErrorCode.UNSUPPORTED_CAPABILITY, unknown_required[0])
        try:
            fingerprint = self._fingerprint(request)
        except InvalidJsonValue:
            return _reject(ErrorCode.INVALID_INPUT, "request")
        existing = self._idempotency.get(request.idempotency_key)
        if existing is not None:
            if existing[0] != fingerprint:
                return _reject(ErrorCode.CONFLICT, "idempotency_key")
            response = existing[1]
            if isinstance(response, OperationAccepted):
                response = OperationAccepted(response.operation_id, response.status, True)
            elif isinstance(response, ImmediateResult):
                response = ImmediateResult(response.operation, response.result, True)
            return ProtocolAccepted(response)

        if request.operation is Operation.DESCRIBE:
            return self._remember(request, fingerprint, self.description)

        payload = self._operation_payload(request)
        if payload is None:
            return _reject(ErrorCode.INVALID_INPUT, "payload", "object")

        if request.operation is Operation.GET_OPERATION:
            if set(payload) != {"operation_id", "cursor"}:
                return _reject(ErrorCode.INVALID_INPUT, "payload.fields")
            snapshot = self._snapshot(payload["operation_id"], payload["cursor"])
            if isinstance(snapshot, ProtocolRejected):
                return snapshot
            return self._remember(request, fingerprint, snapshot.value)

        if request.operation is Operation.CANCEL_OPERATION:
            if set(payload) != {"operation_id", "reason"}:
                return _reject(ErrorCode.INVALID_INPUT, "payload.fields")
            operation_id = payload["operation_id"]
            reason = payload["reason"]
            if not isinstance(operation_id, str) or not isinstance(reason, str) or not reason:
                return _reject(ErrorCode.INVALID_INPUT, "cancel_operation")
            record = self._operations.get(operation_id)
            if record is None:
                return _reject(ErrorCode.OPERATION_UNKNOWN, operation_id)
            ack = CancellationAck(operation_id, record.status, True)
            return self._remember(request, fingerprint, ack)

        if request.operation in LONG_OPERATIONS:
            operation_id = f"OP-{self._next_operation:06d}"
            self._next_operation += 1
            initial = OperationEvent(1, OperationStatus.QUEUED)
            self._operations[operation_id] = _OperationRecord(
                operation_id, request.operation, OperationStatus.QUEUED, (initial,)
            )
            accepted = OperationAccepted(operation_id, OperationStatus.QUEUED, False)
            return self._remember(request, fingerprint, accepted)

        immediate = ImmediateResult(
            request.operation,
            freeze_json({"accepted": True, "operation": request.operation.value}),
            False,
        )
        return self._remember(request, fingerprint, immediate)

    def advance(
        self,
        operation_id: str,
        status: OperationStatus,
        *,
        result: object = None,
        error: ProtocolError | None = None,
    ) -> ProtocolOutcome[OperationSnapshot]:
        record = self._operations.get(operation_id)
        if record is None:
            return _reject(ErrorCode.OPERATION_UNKNOWN, operation_id)
        if record.status in TERMINAL_STATUSES:
            return _reject(ErrorCode.CONFLICT, "terminal_operation")
        allowed = {
            OperationStatus.QUEUED: frozenset(
                (OperationStatus.RUNNING, OperationStatus.FAILED, OperationStatus.CANCELLED)
            ),
            OperationStatus.RUNNING: frozenset(
                (OperationStatus.SUCCEEDED, OperationStatus.FAILED, OperationStatus.CANCELLED)
            ),
        }
        if status not in allowed[record.status]:
            return _reject(ErrorCode.CONFLICT, "operation_transition")
        frozen_result: FrozenJson | None = None
        terminal_error = error
        if status is OperationStatus.SUCCEEDED:
            if record.operation is Operation.RUN_CHECK:
                checked = build_check_result(result)
                if isinstance(checked, ProtocolRejected):
                    status = OperationStatus.FAILED
                    terminal_error = checked.error
                else:
                    frozen_result = checked.value
            else:
                try:
                    frozen_result = freeze_json(result)
                except InvalidJsonValue:
                    status = OperationStatus.FAILED
                    terminal_error = ProtocolError(ErrorCode.OUTPUT_INVALID, "result")
        elif status is OperationStatus.FAILED and terminal_error is None:
            terminal_error = ProtocolError(ErrorCode.OUTPUT_INVALID, "operation")
        event = OperationEvent(len(record.events) + 1, status)
        updated = _OperationRecord(
            operation_id,
            record.operation,
            status,
            record.events + (event,),
            frozen_result,
            terminal_error,
        )
        self._operations[operation_id] = updated
        return self._snapshot(operation_id, 0)
