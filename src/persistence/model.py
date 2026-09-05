"""Valeurs immuables exposées par la persistance locale."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeAlias, TypeVar

from .canonical import FrozenJson


class PersistenceErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_DIGEST = "INVALID_DIGEST"
    SYMLINK_REFUSED = "SYMLINK_REFUSED"
    OBJECT_MISSING = "OBJECT_MISSING"
    OBJECT_CORRUPT = "OBJECT_CORRUPT"
    OBJECT_COLLISION = "OBJECT_COLLISION"
    JOURNAL_CORRUPT = "JOURNAL_CORRUPT"
    SEQUENCE_MISMATCH = "SEQUENCE_MISMATCH"
    HASH_MISMATCH = "HASH_MISMATCH"
    COMMAND_CONFLICT = "COMMAND_CONFLICT"
    STATE_VERSION_MISMATCH = "STATE_VERSION_MISMATCH"
    IO_ERROR = "IO_ERROR"


@dataclass(frozen=True, slots=True)
class PersistenceRefusal:
    code: PersistenceErrorCode
    subject: str
    details: tuple[str, ...] = ()


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Persisted(Generic[T]):
    value: T


PersistenceOutcome: TypeAlias = Persisted[T] | PersistenceRefusal


@dataclass(frozen=True, slots=True)
class StoredObject:
    digest: str
    size: int
    relative_path: str
    already_present: bool


@dataclass(frozen=True, slots=True)
class EventDraft:
    command_id: str
    command_digest: str
    expected_state_version: int
    event_type: str
    payload: FrozenJson
    result: FrozenJson
    object_digests: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class JournalEvent:
    sequence: int
    previous_hash: str | None
    command_id: str
    command_digest: str
    expected_state_version: int
    state_version_after: int
    event_type: str
    payload: FrozenJson
    result: FrozenJson
    object_digests: tuple[str, ...]
    event_hash: str


@dataclass(frozen=True, slots=True)
class JournalState:
    events: tuple[JournalEvent, ...]
    quarantined_tail: str | None = None


@dataclass(frozen=True, slots=True)
class CommandRecord:
    command_id: str
    command_digest: str
    result: FrozenJson
    sequence: int
    state_version: int


@dataclass(frozen=True, slots=True)
class Projection:
    sequence: int
    state_version: int
    head_hash: str | None
    commands: tuple[CommandRecord, ...]
    object_digests: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    command: CommandRecord
    projection: Projection
    replayed: bool
