"""Journal JSONL append-only, chaîné et vérifié sous verrou exclusif."""

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .canonical import (
    FrozenJson,
    InvalidJsonValue,
    canonical_digest,
    canonical_line,
    freeze_json,
    thaw_json,
)
from .filesystem import ensure_directory, refuse_symlink, sync_directory
from .model import (
    EventDraft,
    JournalEvent,
    JournalState,
    Persisted,
    PersistenceErrorCode,
    PersistenceOutcome,
    PersistenceRefusal,
)


_EVENT_FIELDS = frozenset(
    (
        "command_digest",
        "command_id",
        "event_hash",
        "event_type",
        "expected_state_version",
        "object_digests",
        "payload",
        "previous_hash",
        "result",
        "sequence",
        "state_version_after",
    )
)


def _event_body_document(event: JournalEvent) -> dict[str, object]:
    return {
        "command_digest": event.command_digest,
        "command_id": event.command_id,
        "event_type": event.event_type,
        "expected_state_version": event.expected_state_version,
        "object_digests": list(event.object_digests),
        "payload": thaw_json(event.payload),
        "previous_hash": event.previous_hash,
        "result": thaw_json(event.result),
        "sequence": event.sequence,
        "state_version_after": event.state_version_after,
    }


def _event_document(event: JournalEvent) -> dict[str, object]:
    return _event_body_document(event) | {"event_hash": event.event_hash}


def _valid_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    suffix = value[7:]
    return len(suffix) == 64 and all(character in "0123456789abcdef" for character in suffix)


def _event_from_document(
    document: object,
    *,
    line_number: int,
    expected_sequence: int,
    expected_previous_hash: str | None,
    expected_state_version: int,
) -> JournalEvent | PersistenceRefusal:
    if not isinstance(document, dict) or set(document) != _EVENT_FIELDS:
        return PersistenceRefusal(
            PersistenceErrorCode.JOURNAL_CORRUPT,
            f"line:{line_number}",
            ("event_fields",),
        )
    integer_fields = ("sequence", "expected_state_version", "state_version_after")
    if any(
        isinstance(document[field], bool) or not isinstance(document[field], int)
        for field in integer_fields
    ):
        return PersistenceRefusal(
            PersistenceErrorCode.JOURNAL_CORRUPT,
            f"line:{line_number}",
            ("integer_fields",),
        )
    if document["sequence"] != expected_sequence:
        return PersistenceRefusal(
            PersistenceErrorCode.SEQUENCE_MISMATCH,
            f"line:{line_number}",
            (str(expected_sequence), str(document["sequence"])),
        )
    if document["previous_hash"] != expected_previous_hash:
        return PersistenceRefusal(
            PersistenceErrorCode.HASH_MISMATCH,
            f"line:{line_number}",
            ("previous_hash",),
        )
    if document["expected_state_version"] != expected_state_version:
        return PersistenceRefusal(
            PersistenceErrorCode.STATE_VERSION_MISMATCH,
            f"line:{line_number}",
            (str(expected_state_version), str(document["expected_state_version"])),
        )
    if document["state_version_after"] != expected_state_version + 1:
        return PersistenceRefusal(
            PersistenceErrorCode.STATE_VERSION_MISMATCH,
            f"line:{line_number}",
            ("state_version_after",),
        )
    for field in ("command_id", "event_type"):
        if not isinstance(document[field], str) or not document[field]:
            return PersistenceRefusal(
                PersistenceErrorCode.JOURNAL_CORRUPT,
                f"line:{line_number}",
                (field,),
            )
    if not _valid_digest(document["command_digest"]) or not _valid_digest(
        document["event_hash"]
    ):
        return PersistenceRefusal(
            PersistenceErrorCode.JOURNAL_CORRUPT,
            f"line:{line_number}",
            ("digest",),
        )
    object_digests = document["object_digests"]
    if not isinstance(object_digests, list) or any(
        not _valid_digest(item) for item in object_digests
    ):
        return PersistenceRefusal(
            PersistenceErrorCode.JOURNAL_CORRUPT,
            f"line:{line_number}",
            ("object_digests",),
        )
    try:
        payload = freeze_json(document["payload"])
        result = freeze_json(document["result"])
    except InvalidJsonValue:
        return PersistenceRefusal(
            PersistenceErrorCode.JOURNAL_CORRUPT,
            f"line:{line_number}",
            ("json_value",),
        )
    event = JournalEvent(
        sequence=document["sequence"],
        previous_hash=document["previous_hash"],
        command_id=document["command_id"],
        command_digest=document["command_digest"],
        expected_state_version=document["expected_state_version"],
        state_version_after=document["state_version_after"],
        event_type=document["event_type"],
        payload=payload,
        result=result,
        object_digests=tuple(object_digests),
        event_hash=document["event_hash"],
    )
    calculated = canonical_digest(freeze_json(_event_body_document(event)))
    if calculated != event.event_hash:
        return PersistenceRefusal(
            PersistenceErrorCode.HASH_MISMATCH,
            f"line:{line_number}",
            ("event_hash",),
        )
    return event


class Journal:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.directory = self.root / "journal"
        self.path = self.directory / "events.jsonl"
        self.lock_path = self.directory / "write.lock"
        self.quarantine = self.root / "quarantine"

    def _prepare(self) -> PersistenceRefusal | None:
        for directory in (self.directory, self.quarantine):
            error = ensure_directory(directory)
            if error is not None:
                return error
        for path in (self.path, self.lock_path):
            error = refuse_symlink(path)
            if error is not None:
                return error
        return None

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        with self.lock_path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _quarantine_tail(self, tail: bytes) -> str | PersistenceRefusal:
        suffix = hashlib.sha256(tail).hexdigest()
        counter = 0
        while True:
            extra = "" if counter == 0 else f"-{counter}"
            path = self.quarantine / f"journal-tail-{suffix}{extra}.bin"
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                counter += 1
                continue
            except OSError as error:
                return PersistenceRefusal(
                    PersistenceErrorCode.IO_ERROR,
                    str(path),
                    (type(error).__name__,),
                )
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(tail)
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as error:
                return PersistenceRefusal(
                    PersistenceErrorCode.IO_ERROR,
                    str(path),
                    (type(error).__name__,),
                )
            sync_error = sync_directory(self.quarantine)
            if sync_error is not None:
                return sync_error
            return path.relative_to(self.root).as_posix()

    def _read_locked(self) -> PersistenceOutcome[JournalState]:
        if not self.path.exists():
            return Persisted(JournalState(()))
        symlink_error = refuse_symlink(self.path)
        if symlink_error is not None:
            return symlink_error
        try:
            raw = self.path.read_bytes()
        except OSError as error:
            return PersistenceRefusal(
                PersistenceErrorCode.IO_ERROR,
                str(self.path),
                (type(error).__name__,),
            )
        quarantined_tail: str | None = None
        if raw and not raw.endswith(b"\n"):
            boundary = raw.rfind(b"\n") + 1
            tail = raw[boundary:]
            quarantine_result = self._quarantine_tail(tail)
            if isinstance(quarantine_result, PersistenceRefusal):
                return quarantine_result
            quarantined_tail = quarantine_result
            raw = raw[:boundary]
            try:
                with self.path.open("r+b") as stream:
                    stream.truncate(boundary)
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as error:
                return PersistenceRefusal(
                    PersistenceErrorCode.IO_ERROR,
                    str(self.path),
                    ("truncate", type(error).__name__),
                )
            sync_error = sync_directory(self.directory)
            if sync_error is not None:
                return sync_error

        events: list[JournalEvent] = []
        previous_hash: str | None = None
        state_version = 0
        for line_number, line in enumerate(raw.splitlines(keepends=True), 1):
            try:
                document = json.loads(line[:-1])
                frozen = freeze_json(document)
            except (json.JSONDecodeError, UnicodeDecodeError, InvalidJsonValue):
                return PersistenceRefusal(
                    PersistenceErrorCode.JOURNAL_CORRUPT,
                    f"line:{line_number}",
                    ("invalid_json",),
                )
            if canonical_line(frozen) != line:
                return PersistenceRefusal(
                    PersistenceErrorCode.JOURNAL_CORRUPT,
                    f"line:{line_number}",
                    ("non_canonical_json",),
                )
            event = _event_from_document(
                document,
                line_number=line_number,
                expected_sequence=line_number,
                expected_previous_hash=previous_hash,
                expected_state_version=state_version,
            )
            if isinstance(event, PersistenceRefusal):
                return event
            events.append(event)
            previous_hash = event.event_hash
            state_version = event.state_version_after
        return Persisted(JournalState(tuple(events), quarantined_tail))

    def read(self) -> PersistenceOutcome[JournalState]:
        preparation = self._prepare()
        if preparation is not None:
            return preparation
        try:
            with self._exclusive():
                return self._read_locked()
        except OSError as error:
            return PersistenceRefusal(
                PersistenceErrorCode.IO_ERROR,
                str(self.lock_path),
                (type(error).__name__,),
            )

    def _append_locked(
        self, state: JournalState, draft: EventDraft
    ) -> PersistenceOutcome[JournalState]:
        if (
            not draft.command_id
            or not draft.event_type
            or not _valid_digest(draft.command_digest)
        ):
            return PersistenceRefusal(PersistenceErrorCode.INVALID_INPUT, "event")
        current_version = state.events[-1].state_version_after if state.events else 0
        if draft.expected_state_version != current_version:
            return PersistenceRefusal(
                PersistenceErrorCode.STATE_VERSION_MISMATCH,
                "expected_state_version",
                (str(current_version), str(draft.expected_state_version)),
            )
        if any(not _valid_digest(digest) for digest in draft.object_digests):
            return PersistenceRefusal(
                PersistenceErrorCode.INVALID_DIGEST, "object_digests"
            )
        sequence = len(state.events) + 1
        previous_hash = state.events[-1].event_hash if state.events else None
        provisional = JournalEvent(
            sequence=sequence,
            previous_hash=previous_hash,
            command_id=draft.command_id,
            command_digest=draft.command_digest,
            expected_state_version=draft.expected_state_version,
            state_version_after=current_version + 1,
            event_type=draft.event_type,
            payload=draft.payload,
            result=draft.result,
            object_digests=tuple(sorted(set(draft.object_digests))),
            event_hash="",
        )
        try:
            event_hash = canonical_digest(freeze_json(_event_body_document(provisional)))
            event = JournalEvent(
                provisional.sequence,
                provisional.previous_hash,
                provisional.command_id,
                provisional.command_digest,
                provisional.expected_state_version,
                provisional.state_version_after,
                provisional.event_type,
                provisional.payload,
                provisional.result,
                provisional.object_digests,
                event_hash,
            )
            line = canonical_line(freeze_json(_event_document(event)))
        except InvalidJsonValue:
            return PersistenceRefusal(PersistenceErrorCode.INVALID_INPUT, "json_value")
        symlink_error = refuse_symlink(self.path)
        if symlink_error is not None:
            return symlink_error
        try:
            with self.path.open("ab") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            return PersistenceRefusal(
                PersistenceErrorCode.IO_ERROR,
                str(self.path),
                (type(error).__name__,),
            )
        sync_error = sync_directory(self.directory)
        if sync_error is not None:
            return sync_error
        return Persisted(JournalState(state.events + (event,), state.quarantined_tail))

    def append(self, draft: EventDraft) -> PersistenceOutcome[JournalState]:
        preparation = self._prepare()
        if preparation is not None:
            return preparation
        try:
            with self._exclusive():
                state = self._read_locked()
                if isinstance(state, PersistenceRefusal):
                    return state
                return self._append_locked(state.value, draft)
        except OSError as error:
            return PersistenceRefusal(
                PersistenceErrorCode.IO_ERROR,
                str(self.lock_path),
                (type(error).__name__,),
            )
