"""Résultats explicites des opérations du domaine."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeAlias, TypeVar


class RefusalCode(StrEnum):
    MISSING_FIELD = "MISSING_FIELD"
    UNKNOWN_KIND = "UNKNOWN_KIND"
    SYMBOLIC_REVISION = "SYMBOLIC_REVISION"
    NON_CONSECUTIVE_REVISION = "NON_CONSECUTIVE_REVISION"
    SEALED_ARTIFACT = "SEALED_ARTIFACT"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    UNKNOWN_LINK_TYPE = "UNKNOWN_LINK_TYPE"
    DEPENDENCY_CYCLE = "DEPENDENCY_CYCLE"
    STATE_VERSION_MISMATCH = "STATE_VERSION_MISMATCH"
    UNKNOWN_TRANSITION = "UNKNOWN_TRANSITION"
    PRECONDITION_UNSATISFIED = "PRECONDITION_UNSATISFIED"
    INTEGRATED_REQUIRES_NEW_INCREMENT = "INTEGRATED_REQUIRES_NEW_INCREMENT"
    PROFILE_IMMUTABLE = "PROFILE_IMMUTABLE"
    UNKNOWN_ATTEMPT_TRANSITION = "UNKNOWN_ATTEMPT_TRANSITION"
    MISSING_FINISH_REASON = "MISSING_FINISH_REASON"
    RUNNING_ATTEMPT_CONFLICT = "RUNNING_ATTEMPT_CONFLICT"
    MALFORMED_COMMAND = "MALFORMED_COMMAND"
    INVALID_APPROVAL_TARGET = "INVALID_APPROVAL_TARGET"


T = TypeVar("T")
S = TypeVar("S")


@dataclass(frozen=True, slots=True)
class Accepted(Generic[T]):
    value: T


@dataclass(frozen=True, slots=True)
class Refused(Generic[S]):
    code: RefusalCode
    subject: str
    state: S
    details: tuple[str, ...] = ()


Outcome: TypeAlias = Accepted[T] | Refused[S]
