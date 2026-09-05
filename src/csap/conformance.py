"""Kit local de conformité syntaxique et comportementale CSAP 1.0."""

from .adapter import InProcessAdapter
from .model import (
    CancellationAck,
    ConformanceCase,
    ConformanceReport,
    OperationAccepted,
    OperationSnapshot,
    ProtocolAccepted,
    ProtocolRejected,
)
from .negotiation import negotiate
from .validation import build_request
from .vocabulary import (
    PORT_OPERATIONS,
    ErrorCode,
    LONG_OPERATIONS,
    Operation,
    OperationStatus,
    PortName,
)


_HEX_A = "a" * 64
_HEX_B = "b" * 64


def _reference(identifier: str, kind: str = "execution_contract") -> dict[str, object]:
    return {
        "artifact_id": identifier,
        "revision": 1,
        "kind": kind,
        "schema_version": "1",
        "digest": f"sha256:{_HEX_A}",
    }


def _request_document(
    operation: Operation,
    *,
    request_id: str,
    key: str,
    payload: object,
    version: str = "1.0",
    extensions: object | None = None,
) -> dict[str, object]:
    document: dict[str, object] = {
        "protocol_version": version,
        "request_id": request_id,
        "idempotency_key": key,
        "operation": operation.value,
        "payload": payload,
        "extensions": {} if extensions is None else extensions,
    }
    if operation in {
        Operation.PREPARE,
        Operation.START_AGENT,
        Operation.CAPTURE_CANDIDATE,
        Operation.RUN_CHECK,
        Operation.INTEGRATE,
        Operation.REQUEST_APPROVAL,
    }:
        document["increment_id"] = "INC-CONFORMANCE"
        document["contract_ref"] = _reference("contract")
    if operation in {
        Operation.START_AGENT,
        Operation.CAPTURE_CANDIDATE,
        Operation.RUN_CHECK,
    }:
        document["attempt_id"] = "ATT-CONFORMANCE"
    return document


def _check_result(outcome: str) -> dict[str, object]:
    return {
        "check_id": "conformance",
        "check_ref": _reference("check", "check_plan"),
        "contract_ref": _reference("contract"),
        "candidate_ref": _reference("candidate", "candidate"),
        "environment_ref": _reference("environment", "observation"),
        "outcome": outcome,
        "requirements": [{"id": "REQ-CSAP", "outcome": outcome}],
        "process": {"exit_code": 0 if outcome == "PASS" else 1, "timed_out": False},
        "evidence_refs": [f"sha256:{_HEX_B}"],
        "feedback_ref": f"sha256:{_HEX_B}",
    }


def _case(case_id: str, passed: bool, *details: str) -> ConformanceCase:
    return ConformanceCase(case_id, passed, tuple(details))


def _dispatch(
    adapter: InProcessAdapter, document: dict[str, object]
) -> ProtocolAccepted[object] | ProtocolRejected:
    request = build_request(document)
    if isinstance(request, ProtocolRejected):
        return request
    return adapter.dispatch(request.value)


def _start_long_operation(
    adapter: InProcessAdapter,
    operation: Operation,
    *,
    key: str,
) -> OperationAccepted | None:
    outcome = _dispatch(
        adapter,
        _request_document(
            operation,
            request_id=f"{key}-request",
            key=key,
            payload={"case": key},
        ),
    )
    if isinstance(outcome, ProtocolAccepted) and isinstance(
        outcome.value, OperationAccepted
    ):
        return outcome.value
    return None


def run_conformance(adapter: InProcessAdapter) -> ConformanceReport:
    cases: list[ConformanceCase] = []
    permitted_operations = frozenset(
        operation
        for port in adapter.description.ports
        for operation in PORT_OPERATIONS[port]
    )
    cases.append(
        _case(
            "separation_ports",
            all(
                operation in permitted_operations
                for operation in adapter.description.operations
            )
            and (
                Operation.REQUEST_APPROVAL not in adapter.description.operations
                or PortName.APPROVAL in adapter.description.ports
            ),
        )
    )
    cases.append(
        _case(
            "vocabulaire_etats",
            {item.value for item in OperationStatus}
            == {"queued", "running", "succeeded", "failed", "cancelled", "unknown"},
        )
    )
    cases.append(
        _case(
            "vocabulaire_erreurs",
            {item.value for item in ErrorCode}
            == {
                "UNSUPPORTED_VERSION",
                "UNSUPPORTED_CAPABILITY",
                "UNSUPPORTED_PARAMETER",
                "INVALID_INPUT",
                "AUTHORIZATION_DENIED",
                "ENVIRONMENT_UNAVAILABLE",
                "TIMEOUT",
                "RESOURCE_LIMIT",
                "OUTPUT_INVALID",
                "INTEGRITY_MISMATCH",
                "CONFLICT",
                "OPERATION_UNKNOWN",
            },
        )
    )
    negotiated = negotiate(("1.0",), adapter.description)
    selected = negotiated.value if isinstance(negotiated, ProtocolAccepted) else None
    cases.append(_case("version_commune", selected == "1.0"))
    incompatible = negotiate(("99.0",), adapter.description)
    cases.append(
        _case(
            "version_incompatible",
            isinstance(incompatible, ProtocolRejected)
            and incompatible.error.code is ErrorCode.UNSUPPORTED_VERSION,
        )
    )

    unknown = _request_document(
        Operation.DESCRIBE, request_id="unknown", key="unknown", payload={}
    ) | {"unexpected": True}
    rejected_unknown = build_request(unknown)
    cases.append(
        _case(
            "champ_inconnu",
            isinstance(rejected_unknown, ProtocolRejected)
            and rejected_unknown.error.code is ErrorCode.INVALID_INPUT,
        )
    )
    optional = build_request(
        _request_document(
            Operation.DESCRIBE,
            request_id="optional",
            key="optional",
            payload={},
            extensions={"org.example.trace": {"required": False, "value": True}},
        )
    )
    cases.append(_case("extension_optionnelle", isinstance(optional, ProtocolAccepted)))
    required = build_request(
        _request_document(
            Operation.DESCRIBE,
            request_id="required",
            key="required",
            payload={},
            extensions={"org.example.required": {"required": True, "value": True}},
        )
    )
    cases.append(
        _case(
            "extension_obligatoire_inconnue",
            isinstance(required, ProtocolRejected)
            and required.error.code is ErrorCode.UNSUPPORTED_CAPABILITY,
        )
    )
    complete_reference = build_request(
        _request_document(
            Operation.RUN_CHECK,
            request_id="complete-reference",
            key="complete-reference",
            payload={},
        )
    )
    symbolic_reference_document = _request_document(
        Operation.RUN_CHECK,
        request_id="symbolic-reference",
        key="symbolic-reference",
        payload={},
    )
    symbolic_reference_document["contract_ref"] = {
        **symbolic_reference_document["contract_ref"],
        "revision": "latest",
    }
    symbolic_reference = build_request(symbolic_reference_document)
    cases.append(
        _case(
            "references_completes",
            isinstance(complete_reference, ProtocolAccepted)
            and isinstance(symbolic_reference, ProtocolRejected)
            and symbolic_reference.error.code is ErrorCode.INVALID_INPUT,
        )
    )
    arbitrary_url = build_request(
        _request_document(
            Operation.DESCRIBE,
            request_id="arbitrary-url",
            key="arbitrary-url",
            payload={"blob": "https://example.invalid/object"},
        )
    )
    cases.append(
        _case(
            "refus_url_blob",
            isinstance(arbitrary_url, ProtocolRejected)
            and arbitrary_url.error.code is ErrorCode.INVALID_INPUT,
        )
    )

    long_operation = next(
        (item for item in adapter.description.operations if item in LONG_OPERATIONS), None
    )
    if selected is None or long_operation is None:
        cases.append(_case("operation_longue_disponible", False))
        return ConformanceReport(
            adapter.description.identity,
            selected,
            tuple(cases),
            syntax_conformant=False,
            security_qualified=False,
        )

    start_document = _request_document(
        long_operation,
        request_id="start-1",
        key="stable-key",
        payload={"value": 1},
    )
    start = build_request(start_document)
    started = adapter.dispatch(start.value) if isinstance(start, ProtocolAccepted) else start
    accepted = started.value if isinstance(started, ProtocolAccepted) else None
    cases.append(
        _case(
            "retour_non_bloquant",
            isinstance(accepted, OperationAccepted)
            and accepted.status is OperationStatus.QUEUED,
        )
    )
    operation_id = accepted.operation_id if isinstance(accepted, OperationAccepted) else "missing"

    replay_document = dict(start_document)
    replay_document["request_id"] = "start-2"
    replay = build_request(replay_document)
    replayed = adapter.dispatch(replay.value) if isinstance(replay, ProtocolAccepted) else replay
    replay_value = replayed.value if isinstance(replayed, ProtocolAccepted) else None
    cases.append(
        _case(
            "idempotence",
            isinstance(replay_value, OperationAccepted)
            and replay_value.operation_id == operation_id
            and replay_value.replayed,
        )
    )

    conflict_document = dict(start_document)
    conflict_document["request_id"] = "start-3"
    conflict_document["payload"] = {"value": 2}
    conflict = build_request(conflict_document)
    conflicted = adapter.dispatch(conflict.value) if isinstance(conflict, ProtocolAccepted) else conflict
    cases.append(
        _case(
            "conflit_idempotence",
            isinstance(conflicted, ProtocolRejected)
            and conflicted.error.code is ErrorCode.CONFLICT,
        )
    )

    running = adapter.advance(operation_id, OperationStatus.RUNNING)
    cases.append(
        _case(
            "transition_running",
            isinstance(running, ProtocolAccepted)
            and running.value.status is OperationStatus.RUNNING,
        )
    )
    terminal_result: object = (
        _check_result("FAIL") if long_operation is Operation.RUN_CHECK else {"done": True}
    )
    terminal = adapter.advance(
        operation_id, OperationStatus.SUCCEEDED, result=terminal_result
    )
    terminal_value = terminal.value if isinstance(terminal, ProtocolAccepted) else None
    cases.append(
        _case(
            "resultat_terminal",
            isinstance(terminal_value, OperationSnapshot)
            and terminal_value.status is OperationStatus.SUCCEEDED,
        )
    )
    second_terminal = adapter.advance(operation_id, OperationStatus.FAILED)
    cases.append(
        _case(
            "terminalite",
            isinstance(second_terminal, ProtocolRejected)
            and second_terminal.error.code is ErrorCode.CONFLICT,
        )
    )
    if isinstance(terminal_value, OperationSnapshot):
        cursor_request = build_request(
            _request_document(
                Operation.GET_OPERATION,
                request_id="cursor",
                key="cursor",
                payload={"operation_id": operation_id, "cursor": 1},
            )
        )
        cursor_response = (
            adapter.dispatch(cursor_request.value)
            if isinstance(cursor_request, ProtocolAccepted)
            else cursor_request
        )
        snapshot = cursor_response.value if isinstance(cursor_response, ProtocolAccepted) else None
        cases.append(
            _case(
                "curseur",
                isinstance(snapshot, OperationSnapshot)
                and all(event.cursor > 1 for event in snapshot.events),
            )
        )
    else:
        cases.append(_case("curseur", False))

    cancellation_target = _start_long_operation(
        adapter, long_operation, key="cancellation-target"
    )
    cancellation_ack: object = None
    cancelled: object = None
    if cancellation_target is not None:
        cancellation_response = _dispatch(
            adapter,
            _request_document(
                Operation.CANCEL_OPERATION,
                request_id="cancel-request",
                key="cancel-request",
                payload={
                    "operation_id": cancellation_target.operation_id,
                    "reason": "conformance",
                },
            ),
        )
        cancellation_ack = (
            cancellation_response.value
            if isinstance(cancellation_response, ProtocolAccepted)
            else None
        )
        cancelled_response = adapter.advance(
            cancellation_target.operation_id, OperationStatus.CANCELLED
        )
        cancelled = (
            cancelled_response.value
            if isinstance(cancelled_response, ProtocolAccepted)
            else None
        )
    cases.append(
        _case(
            "accuse_annulation_non_terminal",
            isinstance(cancellation_ack, CancellationAck)
            and cancellation_ack.cancel_requested
            and cancellation_ack.status is OperationStatus.QUEUED,
        )
    )
    cases.append(
        _case(
            "transition_cancelled",
            isinstance(cancelled, OperationSnapshot)
            and cancelled.status is OperationStatus.CANCELLED,
        )
    )

    failed_target = _start_long_operation(adapter, long_operation, key="failed-target")
    failed: object = None
    if failed_target is not None:
        failed_response = adapter.advance(
            failed_target.operation_id, OperationStatus.FAILED
        )
        failed = (
            failed_response.value
            if isinstance(failed_response, ProtocolAccepted)
            else None
        )
    cases.append(
        _case(
            "transition_failed",
            isinstance(failed, OperationSnapshot)
            and failed.status is OperationStatus.FAILED,
        )
    )

    if Operation.RUN_CHECK in adapter.description.operations:
        failed_check = _start_long_operation(
            adapter, Operation.RUN_CHECK, key="check-fail"
        )
        incomplete_check = _start_long_operation(
            adapter, Operation.RUN_CHECK, key="check-incomplete"
        )
        failed_check_result: object = None
        incomplete_check_result: object = None
        if failed_check is not None:
            adapter.advance(failed_check.operation_id, OperationStatus.RUNNING)
            outcome = adapter.advance(
                failed_check.operation_id,
                OperationStatus.SUCCEEDED,
                result=_check_result("FAIL"),
            )
            failed_check_result = (
                outcome.value if isinstance(outcome, ProtocolAccepted) else None
            )
        if incomplete_check is not None:
            adapter.advance(incomplete_check.operation_id, OperationStatus.RUNNING)
            outcome = adapter.advance(
                incomplete_check.operation_id,
                OperationStatus.SUCCEEDED,
                result={**_check_result("PASS"), "evidence_refs": []},
            )
            incomplete_check_result = (
                outcome.value if isinstance(outcome, ProtocolAccepted) else None
            )
        cases.append(
            _case(
                "controle_fail_transporte",
                isinstance(failed_check_result, OperationSnapshot)
                and failed_check_result.status is OperationStatus.SUCCEEDED,
            )
        )
        cases.append(
            _case(
                "pass_incomplet_refuse",
                isinstance(incomplete_check_result, OperationSnapshot)
                and incomplete_check_result.status is OperationStatus.FAILED
                and incomplete_check_result.error is not None
                and incomplete_check_result.error.code is ErrorCode.OUTPUT_INVALID,
            )
        )
    else:
        cases.append(_case("controle_fail_transporte", True, "non_applicable"))
        cases.append(_case("pass_incomplet_refuse", True, "non_applicable"))

    syntax_conformant = all(case.passed for case in cases)
    return ConformanceReport(
        adapter.description.identity,
        selected,
        tuple(cases),
        syntax_conformant,
        security_qualified=False,
    )
