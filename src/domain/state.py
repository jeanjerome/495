"""Agrégat immuable d'un incrément."""

from dataclasses import dataclass, replace

from .attempts import AttemptState
from .references import ApprovalRegistry, ArtifactRef
from .revisions import RevisionHistory
from .sealing import SealRegistry
from .vocabulary import Gate, GateVerdict, OperationalStatus, Phase


@dataclass(frozen=True, slots=True)
class DecisionReason:
    code: str
    obligation: str
    evidence: tuple[ArtifactRef, ...] = ()


@dataclass(frozen=True, slots=True)
class IntegrationIntent:
    candidate: ArtifactRef
    destination: str
    reconciled: bool = False


@dataclass(frozen=True, slots=True)
class IntegrationReconciliation:
    candidate: ArtifactRef
    destination: str
    receipt: ArtifactRef


@dataclass(frozen=True, slots=True)
class GateDecision:
    decision_id: str
    gate: Gate
    verdict: GateVerdict
    engine_version: str
    policy_digest: str
    input_bundle_digest: str
    expected_state_version: int
    candidate: ArtifactRef | None = None
    reasons: tuple[DecisionReason, ...] = ()
    reconciliation: IntegrationReconciliation | None = None


@dataclass(frozen=True, slots=True)
class IncrementState:
    increment_id: str
    revision: int
    phase: Phase
    status: OperationalStatus
    profile: str
    attempts: tuple[AttemptState, ...] = ()
    other_unreconciled_external_effect: bool = False
    expected_destination: str | None = None
    current_candidate: ArtifactRef | None = None
    current_gate_decision: GateDecision | None = None
    integration_intent: IntegrationIntent | None = None
    sealed: SealRegistry = SealRegistry()
    revisions: RevisionHistory = RevisionHistory()
    approvals: ApprovalRegistry = ApprovalRegistry()


def with_status(state: IncrementState, status: OperationalStatus) -> IncrementState:
    return replace(state, status=status)


def has_unreconciled_external_effect(state: IncrementState) -> bool:
    return state.other_unreconciled_external_effect or (
        state.integration_intent is not None and not state.integration_intent.reconciled
    )
