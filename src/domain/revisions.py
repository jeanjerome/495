"""Suites consécutives de révisions par identifiant d'artefact."""

from dataclasses import dataclass

from .outcomes import Accepted, Outcome, RefusalCode, Refused


@dataclass(frozen=True, slots=True)
class RevisionHistory:
    entries: tuple[tuple[str, int], ...] = ()


def next_revision(history: RevisionHistory, artifact_id: str) -> int:
    return dict(history.entries).get(artifact_id, 0) + 1


def record_revision(
    history: RevisionHistory, artifact_id: str, revision: int
) -> Outcome[RevisionHistory, RevisionHistory]:
    if revision != next_revision(history, artifact_id):
        return Refused(RefusalCode.NON_CONSECUTIVE_REVISION, artifact_id, history)
    entries = dict(history.entries)
    entries[artifact_id] = revision
    return Accepted(RevisionHistory(tuple(sorted(entries.items()))))
