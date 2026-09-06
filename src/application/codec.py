"""Codec fermé des commandes et états persistés par l’application."""

import types
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import StrEnum
from typing import Any, Union, get_args, get_origin, get_type_hints

from domain.attempts import AttemptEvent, AttemptState
from domain.commands import (
    ApplyGateDecisionPayload,
    CancelOperationPayload,
    CloseIncrementPayload,
    Command,
    CreateIncrementPayload,
    EvaluateGatePayload,
    ProposeArtifactPayload,
    RecordApprovalPayload,
    ReviseIncrementPayload,
    SealArtifactPayload,
    StartAttemptPayload,
    StartIntegrationPayload,
    SubmitCandidatePayload,
)
from domain.references import Approval, ApprovalRegistry, ArtifactRef
from domain.revisions import RevisionHistory
from domain.sealing import SealRegistry
from domain.state import (
    DecisionReason,
    GateDecision,
    IncrementState,
    IntegrationIntent,
    IntegrationReconciliation,
)
from domain.vocabulary import (
    ApprovalDecision,
    ArtifactKind,
    AttemptPhase,
    AttemptStateName,
    AttemptTrigger,
    ChangeKind,
    CloseReason,
    CommandName,
    FinishReason,
    Gate,
    GateVerdict,
    OperationalStatus,
    Phase,
)
from persistence import canonical_bytes, freeze_json

from .model import CommandEnvelope


class CodecError(ValueError):
    """Le document ne représente pas une valeur du domaine autorisée."""


_DATACLASS_CLASSES = (
    ApplyGateDecisionPayload,
    Approval,
    ApprovalRegistry,
    ArtifactRef,
    AttemptEvent,
    AttemptState,
    CancelOperationPayload,
    CloseIncrementPayload,
    Command,
    CreateIncrementPayload,
    DecisionReason,
    EvaluateGatePayload,
    GateDecision,
    IncrementState,
    IntegrationIntent,
    IntegrationReconciliation,
    ProposeArtifactPayload,
    RecordApprovalPayload,
    RevisionHistory,
    ReviseIncrementPayload,
    SealArtifactPayload,
    SealRegistry,
    StartAttemptPayload,
    StartIntegrationPayload,
    SubmitCandidatePayload,
)
_DATACLASSES = {item.__name__: item for item in _DATACLASS_CLASSES}

_ENUM_CLASSES = (
    ApprovalDecision,
    ArtifactKind,
    AttemptPhase,
    AttemptStateName,
    AttemptTrigger,
    ChangeKind,
    CloseReason,
    CommandName,
    FinishReason,
    Gate,
    GateVerdict,
    OperationalStatus,
    Phase,
)
_ENUMS = {item.__name__: item for item in _ENUM_CLASSES}


def _encode(value: object) -> object:
    if isinstance(value, StrEnum):
        enum_type = type(value)
        if enum_type.__name__ not in _ENUMS or _ENUMS[enum_type.__name__] is not enum_type:
            raise CodecError(f"enum inconnue : {enum_type.__name__}")
        return {"$enum": enum_type.__name__, "value": value.value}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    value_type = type(value)
    if is_dataclass(value) and value_type.__name__ in _DATACLASSES:
        if _DATACLASSES[value_type.__name__] is not value_type:
            raise CodecError(f"type ambigu : {value_type.__name__}")
        return {
            "$type": value_type.__name__,
            **{field.name: _encode(getattr(value, field.name)) for field in fields(value)},
        }
    raise CodecError(f"type non pris en charge : {value_type.__name__}")


def _matches(value: object, annotation: object) -> bool:
    if annotation is Any:
        return True
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in (types.UnionType, Union):
        return any(_matches(value, item) for item in arguments)
    if origin is tuple:
        if not isinstance(value, tuple):
            return False
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return all(_matches(item, arguments[0]) for item in value)
        return len(value) == len(arguments) and all(
            _matches(item, expected) for item, expected in zip(value, arguments)
        )
    if annotation is None or annotation is type(None):
        return value is None
    if annotation is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if annotation is float:
        return isinstance(value, float)
    if isinstance(annotation, type):
        return isinstance(value, annotation)
    return False


def _decode(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return tuple(_decode(item) for item in value)
    if not isinstance(value, Mapping):
        raise CodecError("valeur JSON non prise en charge")
    if set(value) == {"$bytes"}:
        encoded = value["$bytes"]
        if not isinstance(encoded, str):
            raise CodecError("octets invalides")
        try:
            return bytes.fromhex(encoded)
        except ValueError as error:
            raise CodecError("octets invalides") from error
    if set(value) == {"$enum", "value"}:
        enum_name = value["$enum"]
        enum_type = _ENUMS.get(enum_name) if isinstance(enum_name, str) else None
        if enum_type is None:
            raise CodecError(f"enum inconnue : {enum_name}")
        try:
            return enum_type(value["value"])
        except (TypeError, ValueError) as error:
            raise CodecError(f"valeur d’enum invalide : {enum_name}") from error
    type_name = value.get("$type")
    value_type = _DATACLASSES.get(type_name) if isinstance(type_name, str) else None
    if value_type is None:
        raise CodecError(f"type inconnu : {type_name}")
    expected_fields = {field.name for field in fields(value_type)}
    if set(value) != expected_fields | {"$type"}:
        raise CodecError(f"champs invalides : {type_name}")
    decoded = {name: _decode(value[name]) for name in expected_fields}
    hints = get_type_hints(value_type)
    if any(not _matches(decoded[name], hints[name]) for name in expected_fields):
        raise CodecError(f"types de champs invalides : {type_name}")
    try:
        return value_type(**decoded)
    except (TypeError, ValueError) as error:
        raise CodecError(f"valeur invalide : {type_name}") from error


def encode_domain_value(value: object) -> dict[str, object]:
    return {"schema_version": "application-codec-1", "value": _encode(value)}


def decode_domain_value(document: object) -> object:
    if not isinstance(document, Mapping) or set(document) != {"schema_version", "value"}:
        raise CodecError("enveloppe de codec invalide")
    if document["schema_version"] != "application-codec-1":
        raise CodecError("version de codec inconnue")
    return _decode(document["value"])


def command_document(envelope: CommandEnvelope) -> dict[str, object]:
    return {
        "command": encode_domain_value(envelope.command),
        "increment_id": envelope.increment_id,
        "schema_version": "application-command-1",
    }


def decode_command_document(document: object) -> CommandEnvelope:
    if not isinstance(document, Mapping) or set(document) != {
        "command",
        "increment_id",
        "schema_version",
    }:
        raise CodecError("document de commande invalide")
    if document["schema_version"] != "application-command-1":
        raise CodecError("version de commande inconnue")
    increment_id = document["increment_id"]
    command = decode_domain_value(document["command"])
    if not isinstance(increment_id, str) or not increment_id or not isinstance(command, Command):
        raise CodecError("commande invalide")
    return CommandEnvelope(increment_id, command)


def state_document(state: IncrementState) -> dict[str, object]:
    return {
        "increment_id": state.increment_id,
        "schema_version": "application-state-1",
        "state": encode_domain_value(state),
    }


def decode_state_document(document: object) -> IncrementState:
    if not isinstance(document, Mapping) or set(document) != {
        "increment_id",
        "schema_version",
        "state",
    }:
        raise CodecError("snapshot invalide")
    if document["schema_version"] != "application-state-1":
        raise CodecError("version de snapshot inconnue")
    increment_id = document["increment_id"]
    state = decode_domain_value(document["state"])
    if (
        not isinstance(increment_id, str)
        or not isinstance(state, IncrementState)
        or state.increment_id != increment_id
    ):
        raise CodecError("identifiant de snapshot incohérent")
    return state


def canonical_domain_bytes(value: object) -> bytes:
    return canonical_bytes(freeze_json(encode_domain_value(value)))
