"""Construction sanctionnée et validation stricte des enveloppes CSAP."""

import re
from collections.abc import Mapping

from domain.outcomes import Refused
from domain.references import ArtifactRef, build_ref

from .canonical import FrozenJson, InvalidJsonValue, freeze_json, thaw_json
from .model import (
    AdapterDescription,
    Extension,
    ProtocolAccepted,
    ProtocolOutcome,
    ProtocolRejected,
    Request,
)
from .vocabulary import CheckOutcome, ErrorCode, Operation, PORT_OPERATIONS, PortName


_VERSION = re.compile(r"[0-9]+\.[0-9]+")
_QUALIFIED_NAME = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_REQUEST_BASE = frozenset(
    ("protocol_version", "request_id", "idempotency_key", "operation", "payload", "extensions")
)
_REQUEST_OPTIONAL = frozenset(("increment_id", "attempt_id", "contract_ref"))
_DESCRIPTION_REQUIRED = frozenset(
    ("identity", "adapter_version", "protocol_versions", "ports", "operations")
)
_DESCRIPTION_OPTIONAL = frozenset(
    ("platforms", "toolchains", "limits", "isolation_capabilities")
)
_REFERENCE_FIELDS = frozenset(
    ("artifact_id", "revision", "kind", "schema_version", "digest")
)
_WORK_OPERATIONS = frozenset(
    (
        Operation.PREPARE,
        Operation.START_AGENT,
        Operation.CAPTURE_CANDIDATE,
        Operation.RUN_CHECK,
        Operation.INTEGRATE,
        Operation.REQUEST_APPROVAL,
    )
)
_ATTEMPT_OPERATIONS = frozenset(
    (Operation.START_AGENT, Operation.CAPTURE_CANDIDATE, Operation.RUN_CHECK)
)


def _reject(
    code: ErrorCode, subject: str, *details: str, retryable: bool = False
) -> ProtocolRejected:
    from .model import ProtocolError

    return ProtocolRejected(ProtocolError(code, subject, retryable, tuple(details)))


def _artifact_ref(value: object, subject: str) -> ProtocolOutcome[ArtifactRef]:
    if isinstance(value, ArtifactRef):
        fields = {
            "artifact_id": value.artifact_id,
            "revision": value.revision,
            "kind": value.kind,
            "schema_version": value.schema_version,
            "digest": value.digest,
        }
    elif isinstance(value, Mapping) and set(value) == _REFERENCE_FIELDS:
        fields = dict(value)
    else:
        return _reject(ErrorCode.INVALID_INPUT, subject, "complete_artifact_reference")
    built = build_ref(**fields)
    if isinstance(built, Refused):
        return _reject(ErrorCode.INVALID_INPUT, f"{subject}.{built.subject}", built.code.value)
    return ProtocolAccepted(built.value)


def _contains_url(value: object) -> bool:
    if isinstance(value, str):
        return value.startswith(("http://", "https://"))
    if isinstance(value, Mapping):
        return any(_contains_url(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_url(child) for child in value)
    return False


def _extensions(
    value: object, understood: frozenset[str]
) -> ProtocolOutcome[tuple[Extension, ...]]:
    if not isinstance(value, Mapping):
        return _reject(ErrorCode.INVALID_INPUT, "extensions", "object")
    if any(not isinstance(name, str) for name in value):
        return _reject(ErrorCode.INVALID_INPUT, "extensions.name")
    extensions: list[Extension] = []
    for name in sorted(value):
        entry = value[name]
        if _QUALIFIED_NAME.fullmatch(name) is None:
            return _reject(ErrorCode.INVALID_INPUT, "extensions.name", str(name))
        if not isinstance(entry, Mapping) or set(entry) != {"required", "value"}:
            return _reject(ErrorCode.INVALID_INPUT, f"extensions.{name}", "fields")
        if not isinstance(entry["required"], bool):
            return _reject(ErrorCode.INVALID_INPUT, f"extensions.{name}.required")
        if entry["required"] and name not in understood:
            return _reject(ErrorCode.UNSUPPORTED_CAPABILITY, name)
        try:
            frozen = freeze_json(entry["value"])
        except InvalidJsonValue as error:
            return _reject(ErrorCode.INVALID_INPUT, f"extensions.{name}.value", str(error))
        extensions.append(Extension(name, entry["required"], frozen))
    return ProtocolAccepted(tuple(extensions))


def build_request(
    document: object, *, understood_extensions: frozenset[str] = frozenset()
) -> ProtocolOutcome[Request]:
    if not isinstance(document, Mapping):
        return _reject(ErrorCode.INVALID_INPUT, "request", "object")
    missing = _REQUEST_BASE - set(document)
    if missing:
        return _reject(ErrorCode.INVALID_INPUT, sorted(missing)[0], "missing")
    unknown = set(document) - _REQUEST_BASE - _REQUEST_OPTIONAL
    if unknown:
        return _reject(ErrorCode.INVALID_INPUT, "request.fields", *sorted(unknown))
    for field in ("protocol_version", "request_id", "idempotency_key"):
        if not isinstance(document[field], str) or not document[field]:
            return _reject(ErrorCode.INVALID_INPUT, field)
    if _VERSION.fullmatch(document["protocol_version"]) is None:
        return _reject(ErrorCode.UNSUPPORTED_VERSION, "protocol_version")
    try:
        operation = Operation(document["operation"])
    except (TypeError, ValueError):
        return _reject(ErrorCode.UNSUPPORTED_CAPABILITY, "operation")
    if _contains_url(document["payload"]):
        return _reject(ErrorCode.INVALID_INPUT, "payload", "arbitrary_url")
    try:
        payload = freeze_json(document["payload"])
    except InvalidJsonValue as error:
        return _reject(ErrorCode.INVALID_INPUT, "payload", str(error))
    extensions = _extensions(document["extensions"], understood_extensions)
    if isinstance(extensions, ProtocolRejected):
        return extensions

    increment_id = document.get("increment_id")
    attempt_id = document.get("attempt_id")
    contract_value = document.get("contract_ref")
    if operation in _WORK_OPERATIONS:
        if not isinstance(increment_id, str) or not increment_id:
            return _reject(ErrorCode.INVALID_INPUT, "increment_id")
        contract = _artifact_ref(contract_value, "contract_ref")
        if isinstance(contract, ProtocolRejected):
            return contract
        contract_ref = contract.value
    else:
        if increment_id is not None or contract_value is not None:
            return _reject(ErrorCode.INVALID_INPUT, "work_context")
        contract_ref = None
    if operation in _ATTEMPT_OPERATIONS:
        if not isinstance(attempt_id, str) or not attempt_id:
            return _reject(ErrorCode.INVALID_INPUT, "attempt_id")
    elif attempt_id is not None:
        return _reject(ErrorCode.INVALID_INPUT, "attempt_id")
    return ProtocolAccepted(
        Request(
            document["protocol_version"],
            document["request_id"],
            document["idempotency_key"],
            operation,
            increment_id,
            attempt_id,
            contract_ref,
            payload,
            extensions.value,
        )
    )


def build_description(document: object) -> ProtocolOutcome[AdapterDescription]:
    if not isinstance(document, Mapping):
        return _reject(ErrorCode.INVALID_INPUT, "description", "object")
    missing = _DESCRIPTION_REQUIRED - set(document)
    if missing:
        return _reject(ErrorCode.INVALID_INPUT, sorted(missing)[0], "missing")
    unknown = set(document) - _DESCRIPTION_REQUIRED - _DESCRIPTION_OPTIONAL
    if unknown:
        return _reject(ErrorCode.INVALID_INPUT, "description.fields", *sorted(unknown))
    for field in ("identity", "adapter_version"):
        if not isinstance(document[field], str) or not document[field]:
            return _reject(ErrorCode.INVALID_INPUT, field)
    versions = document["protocol_versions"]
    if not isinstance(versions, (list, tuple)) or not versions or any(
        not isinstance(item, str) or _VERSION.fullmatch(item) is None for item in versions
    ):
        return _reject(ErrorCode.INVALID_INPUT, "protocol_versions")
    try:
        ports = tuple(sorted({PortName(item) for item in document["ports"]}, key=lambda item: item.value))
        operations = tuple(
            sorted({Operation(item) for item in document["operations"]}, key=lambda item: item.value)
        )
    except (TypeError, ValueError):
        return _reject(ErrorCode.UNSUPPORTED_CAPABILITY, "ports_or_operations")
    permitted = frozenset(operation for port in ports for operation in PORT_OPERATIONS[port])
    if any(operation not in permitted for operation in operations):
        return _reject(ErrorCode.AUTHORIZATION_DENIED, "operation_port_separation")
    sequence_fields: dict[str, tuple[str, ...]] = {}
    for field in ("platforms", "toolchains", "isolation_capabilities"):
        value = document.get(field, ())
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(item, str) or not item for item in value
        ):
            return _reject(ErrorCode.INVALID_INPUT, field)
        sequence_fields[field] = tuple(sorted(set(value)))
    limits_value = document.get("limits", {})
    if not isinstance(limits_value, Mapping) or any(
        not isinstance(key, str)
        or not key
        or isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        for key, value in limits_value.items()
    ):
        return _reject(ErrorCode.INVALID_INPUT, "limits")
    return ProtocolAccepted(
        AdapterDescription(
            identity=document["identity"],
            adapter_version=document["adapter_version"],
            protocol_versions=tuple(
                sorted(set(versions), key=lambda item: tuple(map(int, item.split("."))), reverse=True)
            ),
            ports=ports,
            operations=operations,
            platforms=sequence_fields["platforms"],
            toolchains=sequence_fields["toolchains"],
            limits=tuple(sorted(limits_value.items())),
            isolation_capabilities=sequence_fields["isolation_capabilities"],
        )
    )


_CHECK_FIELDS = frozenset(
    (
        "check_id",
        "check_ref",
        "contract_ref",
        "candidate_ref",
        "environment_ref",
        "outcome",
        "requirements",
        "process",
        "evidence_refs",
        "feedback_ref",
    )
)


def build_check_result(document: object) -> ProtocolOutcome[FrozenJson]:
    if not isinstance(document, Mapping) or set(document) != _CHECK_FIELDS:
        return _reject(ErrorCode.OUTPUT_INVALID, "check_result.fields")
    if not isinstance(document["check_id"], str) or not document["check_id"]:
        return _reject(ErrorCode.OUTPUT_INVALID, "check_id")
    for field in ("check_ref", "contract_ref", "candidate_ref", "environment_ref"):
        reference = _artifact_ref(document[field], field)
        if isinstance(reference, ProtocolRejected):
            return _reject(ErrorCode.OUTPUT_INVALID, field)
    try:
        outcome = CheckOutcome(document["outcome"])
    except (TypeError, ValueError):
        return _reject(ErrorCode.OUTPUT_INVALID, "outcome")
    requirements = document["requirements"]
    if not isinstance(requirements, list):
        return _reject(ErrorCode.OUTPUT_INVALID, "requirements")
    requirement_outcomes: list[CheckOutcome] = []
    for entry in requirements:
        if not isinstance(entry, Mapping) or set(entry) != {"id", "outcome"}:
            return _reject(ErrorCode.OUTPUT_INVALID, "requirements.fields")
        if not isinstance(entry["id"], str) or not entry["id"]:
            return _reject(ErrorCode.OUTPUT_INVALID, "requirements.id")
        try:
            requirement_outcomes.append(CheckOutcome(entry["outcome"]))
        except (TypeError, ValueError):
            return _reject(ErrorCode.OUTPUT_INVALID, "requirements.outcome")
    process = document["process"]
    if (
        not isinstance(process, Mapping)
        or set(process) != {"exit_code", "timed_out"}
        or isinstance(process["exit_code"], bool)
        or not isinstance(process["exit_code"], int)
        or not isinstance(process["timed_out"], bool)
    ):
        return _reject(ErrorCode.OUTPUT_INVALID, "process")
    evidence = document["evidence_refs"]
    if not isinstance(evidence, list) or any(
        not isinstance(item, str) or _DIGEST.fullmatch(item) is None for item in evidence
    ):
        return _reject(ErrorCode.OUTPUT_INVALID, "evidence_refs")
    if not isinstance(document["feedback_ref"], str) or _DIGEST.fullmatch(
        document["feedback_ref"]
    ) is None:
        return _reject(ErrorCode.OUTPUT_INVALID, "feedback_ref")
    if outcome is CheckOutcome.PASS and (
        not requirements
        or any(item is not CheckOutcome.PASS for item in requirement_outcomes)
        or process["exit_code"] != 0
        or process["timed_out"]
        or not evidence
    ):
        return _reject(ErrorCode.OUTPUT_INVALID, "incomplete_pass")
    try:
        return ProtocolAccepted(freeze_json(dict(document)))
    except InvalidJsonValue as error:
        return _reject(ErrorCode.OUTPUT_INVALID, "check_result", str(error))


def request_document(request: Request, *, include_request_id: bool = True) -> dict[str, object]:
    document: dict[str, object] = {
        "protocol_version": request.protocol_version,
        "idempotency_key": request.idempotency_key,
        "operation": request.operation.value,
        "payload": thaw_json(request.payload),
        "extensions": {
            extension.name: {
                "required": extension.required,
                "value": thaw_json(extension.value),
            }
            for extension in request.extensions
        },
    }
    if include_request_id:
        document["request_id"] = request.request_id
    if request.increment_id is not None:
        document["increment_id"] = request.increment_id
    if request.attempt_id is not None:
        document["attempt_id"] = request.attempt_id
    if request.contract_ref is not None:
        reference = request.contract_ref
        document["contract_ref"] = {
            "artifact_id": reference.artifact_id,
            "revision": reference.revision,
            "kind": reference.kind.value,
            "schema_version": reference.schema_version,
            "digest": reference.digest,
        }
    return document
