"""Idempotence des commandes et reconstruction depuis le journal local."""

import os
from pathlib import Path

from .canonical import InvalidJsonValue, canonical_digest, freeze_json
from .journal import Journal
from .model import (
    CommandRecord,
    EventDraft,
    ExecutionRecord,
    JournalState,
    Persisted,
    PersistenceErrorCode,
    PersistenceOutcome,
    PersistenceRefusal,
    Projection,
)
from .objects import ObjectStore


def _projection(state: JournalState) -> PersistenceOutcome[Projection]:
    commands: list[CommandRecord] = []
    identifiers: set[str] = set()
    object_digests: set[str] = set()
    for event in state.events:
        if event.command_id in identifiers:
            return PersistenceRefusal(
                PersistenceErrorCode.JOURNAL_CORRUPT,
                event.command_id,
                ("duplicate_command_id",),
            )
        identifiers.add(event.command_id)
        commands.append(
            CommandRecord(
                event.command_id,
                event.command_digest,
                event.result,
                event.sequence,
                event.state_version_after,
            )
        )
        object_digests.update(event.object_digests)
    return Persisted(
        Projection(
            sequence=state.events[-1].sequence if state.events else 0,
            state_version=(
                state.events[-1].state_version_after if state.events else 0
            ),
            head_hash=state.events[-1].event_hash if state.events else None,
            commands=tuple(commands),
            object_digests=tuple(sorted(object_digests)),
        )
    )


class LocalRepository:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.objects = ObjectStore(self.root)
        self.journal = Journal(self.root)

    def reconstruct(self, *, verify_objects: bool = True) -> PersistenceOutcome[Projection]:
        journal_state = self.journal.read()
        if isinstance(journal_state, PersistenceRefusal):
            return journal_state
        projection = _projection(journal_state.value)
        if isinstance(projection, PersistenceRefusal):
            return projection
        if verify_objects:
            for digest in projection.value.object_digests:
                verified = self.objects.get(digest)
                if isinstance(verified, PersistenceRefusal):
                    return verified
        return projection

    def execute(
        self,
        *,
        command_id: str,
        expected_state_version: int,
        command: object,
        result: object,
        event_type: str = "CommandApplied",
        object_writes: tuple[bytes, ...] = (),
    ) -> PersistenceOutcome[ExecutionRecord]:
        if (
            not isinstance(command_id, str)
            or not command_id
            or isinstance(expected_state_version, bool)
            or not isinstance(expected_state_version, int)
            or expected_state_version < 0
            or not isinstance(event_type, str)
            or not event_type
        ):
            return PersistenceRefusal(PersistenceErrorCode.INVALID_INPUT, "command")
        try:
            frozen_command = freeze_json(command)
            frozen_result = freeze_json(result)
        except InvalidJsonValue as error:
            return PersistenceRefusal(
                PersistenceErrorCode.INVALID_INPUT,
                "json_value",
                (str(error),),
            )
        command_digest = canonical_digest(frozen_command)
        preparation = self.journal._prepare()
        if preparation is not None:
            return preparation
        try:
            with self.journal._exclusive():
                journal_state = self.journal._read_locked()
                if isinstance(journal_state, PersistenceRefusal):
                    return journal_state
                projection = _projection(journal_state.value)
                if isinstance(projection, PersistenceRefusal):
                    return projection
                existing = next(
                    (
                        record
                        for record in projection.value.commands
                        if record.command_id == command_id
                    ),
                    None,
                )
                if existing is not None:
                    if existing.command_digest != command_digest:
                        return PersistenceRefusal(
                            PersistenceErrorCode.COMMAND_CONFLICT,
                            command_id,
                            (existing.command_digest, command_digest),
                        )
                    return Persisted(
                        ExecutionRecord(existing, projection.value, replayed=True)
                    )
                if expected_state_version != projection.value.state_version:
                    return PersistenceRefusal(
                        PersistenceErrorCode.STATE_VERSION_MISMATCH,
                        "expected_state_version",
                        (
                            str(projection.value.state_version),
                            str(expected_state_version),
                        ),
                    )
                stored_digests: list[str] = []
                for raw in object_writes:
                    stored = self.objects.put(raw)
                    if isinstance(stored, PersistenceRefusal):
                        return stored
                    stored_digests.append(stored.value.digest)
                draft = EventDraft(
                    command_id=command_id,
                    command_digest=command_digest,
                    expected_state_version=expected_state_version,
                    event_type=event_type,
                    payload=frozen_command,
                    result=frozen_result,
                    object_digests=tuple(stored_digests),
                )
                appended = self.journal._append_locked(journal_state.value, draft)
                if isinstance(appended, PersistenceRefusal):
                    return appended
                updated = _projection(appended.value)
                if isinstance(updated, PersistenceRefusal):
                    return updated
                record = updated.value.commands[-1]
                return Persisted(
                    ExecutionRecord(record, updated.value, replayed=False)
                )
        except OSError as error:
            return PersistenceRefusal(
                PersistenceErrorCode.IO_ERROR,
                str(self.journal.lock_path),
                (type(error).__name__, os.strerror(error.errno) if error.errno else ""),
            )
