"""Fabriques de valeurs lisibles pour les contrôles unitaires."""

from domain.attempts import AttemptState, start_attempt
from domain.outcomes import Accepted
from domain.references import ArtifactRef
from domain.sealing import digest_bytes
from domain.state import GateDecision, IncrementState
from domain.vocabulary import (
    ArtifactKind,
    AttemptPhase,
    Gate,
    GateVerdict,
    OperationalStatus,
    Phase,
)


def ref(
    identifier: str = "artifact",
    revision: int = 1,
    raw: bytes = b"content",
    kind: ArtifactKind = ArtifactKind.DESIGN,
) -> ArtifactRef:
    return ArtifactRef(
        identifier,
        revision,
        kind,
        "1",
        digest_bytes(raw),
    )


def attempt(
    phase: AttemptPhase,
    *,
    identifier: str = "attempt",
    contract: ArtifactRef | None = None,
) -> AttemptState:
    result = start_attempt(
        (),
        attempt_id=identifier,
        increment_id="INC",
        increment_revision=1,
        attempt_phase=phase,
        contract_ref=contract or ref("contract"),
        contract_sealed=True,
        entry_gate_satisfied=True,
        budget_available=True,
    )
    assert isinstance(result, Accepted)
    return result.value


def state(
    phase: Phase = Phase.CLARIFYING,
    *,
    attempts: tuple[AttemptState, ...] = (),
    candidate: ArtifactRef | None = None,
    decision: GateDecision | None = None,
    destination: str | None = "main",
) -> IncrementState:
    return IncrementState(
        "INC",
        1,
        phase,
        OperationalStatus.IDLE,
        "default",
        attempts=attempts,
        current_candidate=candidate,
        current_gate_decision=decision,
        expected_destination=destination,
    )


def gate_decision(
    gate: Gate,
    verdict: GateVerdict,
    *,
    candidate: ArtifactRef | None = None,
    version: int = 1,
) -> GateDecision:
    return GateDecision(
        f"decision-{gate}",
        gate,
        verdict,
        "engine-1",
        "sha256:policy",
        "sha256:inputs",
        version,
        candidate,
    )
