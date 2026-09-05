"""Automate immuable des tentatives d'un incrément."""

from dataclasses import dataclass

from .outcomes import Accepted, Outcome, RefusalCode, Refused
from .references import ArtifactRef
from .vocabulary import AttemptPhase, AttemptStateName, AttemptTrigger, FinishReason


@dataclass(frozen=True, slots=True)
class AttemptEvent:
    attempt_id: str
    source: AttemptStateName | None
    target: AttemptStateName
    trigger: AttemptTrigger
    reason: FinishReason | None = None


@dataclass(frozen=True, slots=True)
class AttemptState:
    attempt_id: str
    increment_id: str
    increment_revision: int
    attempt_phase: AttemptPhase
    contract_ref: ArtifactRef
    state: AttemptStateName
    finish_reason: FinishReason | None
    history: tuple[AttemptEvent, ...]


_ALLOWED_TRANSITIONS = frozenset(
    (
        (AttemptStateName.RUNNING, AttemptStateName.SUSPENDED),
        (AttemptStateName.RUNNING, AttemptStateName.FINISHED),
        (AttemptStateName.SUSPENDED, AttemptStateName.RUNNING),
        (AttemptStateName.SUSPENDED, AttemptStateName.FINISHED),
    )
)

_PAIR_TRIGGERS = {
    (AttemptStateName.RUNNING, AttemptStateName.SUSPENDED): frozenset(
        (AttemptTrigger.G3_PASS, AttemptTrigger.EXPLICIT_SUSPENSION)
    ),
    (AttemptStateName.SUSPENDED, AttemptStateName.RUNNING): frozenset(
        (AttemptTrigger.START_ATTEMPT_AFTER_G4_FAIL, AttemptTrigger.EXPLICIT_RESUME)
    ),
}

_FINISH_TRIGGER_BY_REASON = {
    FinishReason.PHASE_COMPLETED: AttemptTrigger.PHASE_EXIT,
    FinishReason.INTEGRATION_SUCCEEDED: AttemptTrigger.G5_PASS,
    FinishReason.REVISION_REQUESTED: AttemptTrigger.REVISE_INCREMENT,
    FinishReason.INCREMENT_CLOSED: AttemptTrigger.CLOSE_INCREMENT,
    FinishReason.DEFINITIVE_FAILURE: AttemptTrigger.DEFINITIVE_FAILURE,
    FinishReason.BUDGET_EXHAUSTED: AttemptTrigger.BUDGET_EXHAUSTED,
}


def start_attempt(
    existing: tuple[AttemptState, ...],
    *,
    attempt_id: str,
    increment_id: str,
    increment_revision: int,
    attempt_phase: AttemptPhase,
    contract_ref: ArtifactRef,
    contract_sealed: bool,
    entry_gate_satisfied: bool,
    budget_available: bool,
) -> Outcome[AttemptState, tuple[AttemptState, ...]]:
    for subject, satisfied in (
        ("contract_sealed", contract_sealed),
        ("entry_gate_satisfied", entry_gate_satisfied),
        ("budget_available", budget_available),
    ):
        if not satisfied:
            return Refused(RefusalCode.PRECONDITION_UNSATISFIED, subject, existing)
    conflict = any(
        attempt.increment_revision == increment_revision
        and attempt.state is AttemptStateName.RUNNING
        and attempt.attempt_phase is not attempt_phase
        for attempt in existing
    )
    if conflict:
        return Refused(RefusalCode.RUNNING_ATTEMPT_CONFLICT, attempt_id, existing)
    event = AttemptEvent(
        attempt_id,
        None,
        AttemptStateName.RUNNING,
        AttemptTrigger.START_ATTEMPT,
    )
    return Accepted(
        AttemptState(
            attempt_id,
            increment_id,
            increment_revision,
            attempt_phase,
            contract_ref,
            AttemptStateName.RUNNING,
            None,
            (event,),
        )
    )


def transition(
    attempt: AttemptState,
    target: AttemptStateName,
    trigger: AttemptTrigger,
    reason: FinishReason | None = None,
) -> Outcome[AttemptState, AttemptState]:
    pair = (attempt.state, target)
    if pair not in _ALLOWED_TRANSITIONS:
        return Refused(RefusalCode.UNKNOWN_ATTEMPT_TRANSITION, attempt.attempt_id, attempt)
    if target is AttemptStateName.FINISHED:
        if reason is None:
            return Refused(RefusalCode.MISSING_FINISH_REASON, attempt.attempt_id, attempt)
        if _FINISH_TRIGGER_BY_REASON.get(reason) is not trigger:
            return Refused(RefusalCode.UNKNOWN_ATTEMPT_TRANSITION, attempt.attempt_id, attempt)
    elif reason is not None or trigger not in _PAIR_TRIGGERS[pair]:
        return Refused(RefusalCode.UNKNOWN_ATTEMPT_TRANSITION, attempt.attempt_id, attempt)
    event = AttemptEvent(attempt.attempt_id, attempt.state, target, trigger, reason)
    return Accepted(
        AttemptState(
            attempt.attempt_id,
            attempt.increment_id,
            attempt.increment_revision,
            attempt.attempt_phase,
            attempt.contract_ref,
            target,
            reason if target is AttemptStateName.FINISHED else None,
            attempt.history + (event,),
        )
    )


def finish_reason_triggers() -> tuple[tuple[FinishReason, AttemptTrigger], ...]:
    return tuple(_FINISH_TRIGGER_BY_REASON.items())


def allowed_attempt_transitions() -> frozenset[tuple[AttemptStateName, AttemptStateName]]:
    return _ALLOWED_TRANSITIONS
