"""Valeurs immuables exposées par la couche d’application."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeAlias, TypeVar

from domain.commands import Command
from domain.outcomes import RefusalCode
from domain.state import GateDecision, IncrementState


class ApplicationErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    COMMAND_CONFLICT = "COMMAND_CONFLICT"
    STATE_VERSION_MISMATCH = "STATE_VERSION_MISMATCH"
    DOMAIN_REFUSED = "DOMAIN_REFUSED"
    PERSISTENCE_REFUSED = "PERSISTENCE_REFUSED"
    SNAPSHOT_INVALID = "SNAPSHOT_INVALID"


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    increment_id: str
    command: Command


@dataclass(frozen=True, slots=True)
class ApplicationSnapshot:
    state_version: int
    increments: tuple[tuple[str, IncrementState], ...]

    def state_for(self, increment_id: str) -> IncrementState | None:
        return dict(self.increments).get(increment_id)


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    increment_id: str
    state: IncrementState
    state_version_after: int
    current_state_version: int
    replayed: bool


@dataclass(frozen=True, slots=True)
class GateEvaluation:
    increment_id: str
    state_version: int
    decision: GateDecision


@dataclass(frozen=True, slots=True)
class ApplicationRefusal:
    code: ApplicationErrorCode
    subject: str
    current_state_version: int | None = None
    source_code: str | RefusalCode | None = None
    details: tuple[str, ...] = ()


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ApplicationAccepted(Generic[T]):
    value: T


ApplicationOutcome: TypeAlias = ApplicationAccepted[T] | ApplicationRefusal
