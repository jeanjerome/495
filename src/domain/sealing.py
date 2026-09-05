"""Scellement immuable sur le digest des octets exacts."""

from dataclasses import dataclass
from hashlib import sha256

from .outcomes import Accepted, Outcome, RefusalCode, Refused
from .references import ArtifactRef


@dataclass(frozen=True, slots=True)
class SealRegistry:
    entries: tuple[tuple[str, int, ArtifactRef], ...] = ()


def digest_bytes(raw: bytes) -> str:
    return "sha256:" + sha256(raw).hexdigest()


def seal(
    registry: SealRegistry, ref: ArtifactRef, raw: bytes
) -> Outcome[SealRegistry, SealRegistry]:
    key = (ref.artifact_id, ref.revision)
    if any((artifact_id, revision) == key for artifact_id, revision, _ in registry.entries):
        return Refused(RefusalCode.SEALED_ARTIFACT, ref.artifact_id, registry)
    if digest_bytes(raw) != ref.digest:
        return Refused(RefusalCode.DIGEST_MISMATCH, ref.artifact_id, registry)
    entries = registry.entries + ((ref.artifact_id, ref.revision, ref),)
    return Accepted(SealRegistry(tuple(sorted(entries, key=lambda item: item[:2]))))


def digest_of(registry: SealRegistry, artifact_id: str, revision: int) -> str | None:
    for current_id, current_revision, ref in registry.entries:
        if (current_id, current_revision) == (artifact_id, revision):
            return ref.digest
    return None
