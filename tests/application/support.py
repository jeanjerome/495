"""Valeurs partagées par les contrôles de l’orchestrateur."""

from application import CommandEnvelope
from domain.commands import (
    CloseIncrementPayload,
    Command,
    CreateIncrementPayload,
    StartAttemptPayload,
)
from domain.references import ArtifactRef
from domain.sealing import digest_bytes
from domain.vocabulary import (
    ArtifactKind,
    AttemptPhase,
    CloseReason,
    CommandName,
    Phase,
)


def reference(identifier: str = "contract") -> ArtifactRef:
    return ArtifactRef(
        identifier,
        1,
        ArtifactKind.EXECUTION_CONTRACT,
        "1",
        digest_bytes(identifier.encode()),
    )


def create_envelope(
    increment_id: str = "INC-A",
    *,
    command_id: str = "create-a",
    version: int = 0,
    profile: str = "default",
) -> CommandEnvelope:
    return CommandEnvelope(
        increment_id,
        Command(
            command_id,
            CommandName.CREATE_INCREMENT,
            version,
            CreateIncrementPayload(
                increment_id,
                profile,
                expected_destination="main",
            ),
        ),
    )


def close_envelope(
    increment_id: str = "INC-A",
    *,
    command_id: str = "close-a",
    version: int = 1,
    target: Phase = Phase.CLOSED,
) -> CommandEnvelope:
    return CommandEnvelope(
        increment_id,
        Command(
            command_id,
            CommandName.CLOSE_INCREMENT,
            version,
            CloseIncrementPayload(CloseReason.ABANDONED, target),
        ),
    )


def start_attempt_envelope(
    increment_id: str = "INC-A",
    *,
    command_id: str = "attempt-a",
    version: int = 1,
) -> CommandEnvelope:
    return CommandEnvelope(
        increment_id,
        Command(
            command_id,
            CommandName.START_ATTEMPT,
            version,
            StartAttemptPayload(
                "ATT-A",
                AttemptPhase.CLARIFICATION,
                reference(),
                True,
                True,
                True,
            ),
        ),
    )
