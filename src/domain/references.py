"""Références complètes d'artefacts et approbations ciblées."""

from dataclasses import dataclass
from typing import Any

from .outcomes import Accepted, Outcome, RefusalCode, Refused
from .vocabulary import ApprovalDecision, ArtifactKind


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    revision: int
    kind: ArtifactKind
    schema_version: str
    digest: str


@dataclass(frozen=True, slots=True)
class Approval:
    approval_id: str
    actor: str
    role: str
    target: ArtifactRef
    scope: str
    decision: ApprovalDecision


@dataclass(frozen=True, slots=True)
class ApprovalRegistry:
    entries: tuple[Approval, ...] = ()


_REFERENCE_FIELDS = ("artifact_id", "revision", "kind", "schema_version", "digest")
_APPROVAL_FIELDS = ("approval_id", "actor", "role", "target", "scope", "decision")


def build_ref(**fields: Any) -> Outcome[ArtifactRef, None]:
    for name in _REFERENCE_FIELDS:
        if name not in fields:
            return Refused(RefusalCode.MISSING_FIELD, name, None)
    revision = fields["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int):
        return Refused(RefusalCode.SYMBOLIC_REVISION, "revision", None)
    try:
        kind = ArtifactKind(fields["kind"])
    except (TypeError, ValueError):
        return Refused(RefusalCode.UNKNOWN_KIND, "kind", None)
    return Accepted(
        ArtifactRef(
            artifact_id=fields["artifact_id"],
            revision=revision,
            kind=kind,
            schema_version=fields["schema_version"],
            digest=fields["digest"],
        )
    )


def build_approval(**fields: Any) -> Outcome[Approval, None]:
    for name in _APPROVAL_FIELDS:
        if name not in fields:
            return Refused(RefusalCode.MISSING_FIELD, name, None)
    target = fields["target"]
    if not isinstance(target, ArtifactRef):
        return Refused(RefusalCode.INVALID_APPROVAL_TARGET, "target", None)
    checked = build_ref(
        artifact_id=target.artifact_id,
        revision=target.revision,
        kind=target.kind,
        schema_version=target.schema_version,
        digest=target.digest,
    )
    if isinstance(checked, Refused):
        return Refused(checked.code, f"target.{checked.subject}", None, checked.details)
    try:
        decision = ApprovalDecision(fields["decision"])
    except (TypeError, ValueError):
        return Refused(RefusalCode.MALFORMED_COMMAND, "decision", None)
    return Accepted(
        Approval(
            approval_id=fields["approval_id"],
            actor=fields["actor"],
            role=fields["role"],
            target=checked.value,
            scope=fields["scope"],
            decision=decision,
        )
    )


def approval_applies(approval: Approval, target: ArtifactRef) -> bool:
    return approval.target == target


def record(
    registry: ApprovalRegistry, approval: Approval
) -> Outcome[ApprovalRegistry, ApprovalRegistry]:
    return Accepted(ApprovalRegistry(registry.entries + (approval,)))


def approvals_for(
    registry: ApprovalRegistry, target: ArtifactRef
) -> tuple[Approval, ...]:
    return tuple(entry for entry in registry.entries if approval_applies(entry, target))
