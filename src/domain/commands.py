"""Validation et application atomique des commandes du domaine."""

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TypeAlias

from .attempts import AttemptState, start_attempt, transition
from .invalidation import invalidated_by
from .outcomes import Accepted, Outcome, RefusalCode, Refused
from .phases import TransitionEdge, edge_between
from .references import Approval, ArtifactRef, build_approval, build_ref, record
from .revisions import record_revision
from .sealing import seal
from .state import GateDecision, IncrementState, IntegrationIntent, has_unreconciled_external_effect
from .vocabulary import (
    ArtifactKind,
    AttemptPhase,
    AttemptStateName,
    AttemptTrigger,
    ChangeKind,
    CloseReason,
    CommandName,
    FinishReason,
    Gate,
    GateVerdict,
    OperationalStatus,
    Phase,
)


class TransitionArity(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    FORBIDDEN = "forbidden"


TRANSITION_ARITY = (
    (CommandName.APPLY_GATE_DECISION, TransitionArity.OPTIONAL),
    (CommandName.CANCEL_OPERATION, TransitionArity.FORBIDDEN),
    (CommandName.CLOSE_INCREMENT, TransitionArity.REQUIRED),
    (CommandName.CREATE_INCREMENT, TransitionArity.FORBIDDEN),
    (CommandName.EVALUATE_GATE, TransitionArity.FORBIDDEN),
    (CommandName.PROPOSE_ARTIFACT, TransitionArity.FORBIDDEN),
    (CommandName.RECORD_APPROVAL, TransitionArity.FORBIDDEN),
    (CommandName.REVISE_INCREMENT, TransitionArity.REQUIRED),
    (CommandName.SEAL_ARTIFACT, TransitionArity.FORBIDDEN),
    (CommandName.START_ATTEMPT, TransitionArity.OPTIONAL),
    (CommandName.START_INTEGRATION, TransitionArity.REQUIRED),
    (CommandName.SUBMIT_CANDIDATE, TransitionArity.FORBIDDEN),
)

PRECONDITIONS = (
    (CommandName.APPLY_GATE_DECISION, ("current_report", "decision_version", "candidate", "gate_attempt", "reconciliation")),
    (CommandName.CANCEL_OPERATION, ("operation_active",)),
    (CommandName.CLOSE_INCREMENT, ("close_reason", "no_unreconciled_external_effect")),
    (CommandName.CREATE_INCREMENT, ("project_known", "profile_known")),
    (CommandName.EVALUATE_GATE, ("inputs_available",)),
    (CommandName.PROPOSE_ARTIFACT, ("revision_open", "kind_allowed")),
    (CommandName.RECORD_APPROVAL, ("actor_authorized", "complete_target")),
    (CommandName.REVISE_INCREMENT, ("profile_immutable", "no_unreconciled_external_effect")),
    (CommandName.SEAL_ARTIFACT, ("dependencies_resolved", "consecutive_revision", "exact_digest")),
    (CommandName.START_ATTEMPT, ("contract_sealed", "entry_gate_satisfied", "budget_available")),
    (CommandName.START_INTEGRATION, ("current_g4_pass", "expected_destination", "no_unreconciled_external_effect")),
    (CommandName.SUBMIT_CANDIDATE, ("attempt_known", "complete_candidate")),
)


@dataclass(frozen=True, slots=True)
class ApplyGateDecisionPayload:
    decision: GateDecision
    target_phase: Phase | None
    report_current: bool = True


@dataclass(frozen=True, slots=True)
class CancelOperationPayload:
    operation_active: bool
    target_phase: Phase | None = None


@dataclass(frozen=True, slots=True)
class CloseIncrementPayload:
    reason: CloseReason | str | None
    target_phase: Phase | None


@dataclass(frozen=True, slots=True)
class CreateIncrementPayload:
    increment_id: str
    profile: str
    project_known: bool = True
    profile_known: bool = True
    expected_destination: str | None = None
    target_phase: Phase | None = None


@dataclass(frozen=True, slots=True)
class EvaluateGatePayload:
    inputs_available: bool
    target_phase: Phase | None = None


@dataclass(frozen=True, slots=True)
class ProposeArtifactPayload:
    revision_open: bool
    kind_allowed: bool
    target_phase: Phase | None = None


@dataclass(frozen=True, slots=True)
class RecordApprovalPayload:
    approval: Approval
    actor_authorized: bool
    target_phase: Phase | None = None


@dataclass(frozen=True, slots=True)
class ReviseIncrementPayload:
    target_phase: Phase | None
    requested_profile: str | None = None


@dataclass(frozen=True, slots=True)
class SealArtifactPayload:
    ref: ArtifactRef
    raw: bytes
    dependencies_resolved: bool
    change_kind: ChangeKind | None = None
    review_attempt_id: str | None = None
    declared_review_output: ArtifactRef | None = None
    review_contract_ref: ArtifactRef | None = None
    target_phase: Phase | None = None


@dataclass(frozen=True, slots=True)
class StartAttemptPayload:
    attempt_id: str
    attempt_phase: AttemptPhase
    contract_ref: ArtifactRef
    contract_sealed: bool
    entry_gate_satisfied: bool
    budget_available: bool
    candidate: ArtifactRef | None = None
    target_phase: Phase | None = None


@dataclass(frozen=True, slots=True)
class StartIntegrationPayload:
    candidate: ArtifactRef
    destination: str
    target_phase: Phase | None


@dataclass(frozen=True, slots=True)
class SubmitCandidatePayload:
    candidate: ArtifactRef
    attempt_known: bool
    target_phase: Phase | None = None


CommandPayload: TypeAlias = (
    ApplyGateDecisionPayload
    | CancelOperationPayload
    | CloseIncrementPayload
    | CreateIncrementPayload
    | EvaluateGatePayload
    | ProposeArtifactPayload
    | RecordApprovalPayload
    | ReviseIncrementPayload
    | SealArtifactPayload
    | StartAttemptPayload
    | StartIntegrationPayload
    | SubmitCandidatePayload
)


@dataclass(frozen=True, slots=True)
class Command:
    command_id: str
    name: CommandName
    expected_state_version: int
    payload: CommandPayload


_PAYLOAD_TYPES = {
    CommandName.APPLY_GATE_DECISION: ApplyGateDecisionPayload,
    CommandName.CANCEL_OPERATION: CancelOperationPayload,
    CommandName.CLOSE_INCREMENT: CloseIncrementPayload,
    CommandName.CREATE_INCREMENT: CreateIncrementPayload,
    CommandName.EVALUATE_GATE: EvaluateGatePayload,
    CommandName.PROPOSE_ARTIFACT: ProposeArtifactPayload,
    CommandName.RECORD_APPROVAL: RecordApprovalPayload,
    CommandName.REVISE_INCREMENT: ReviseIncrementPayload,
    CommandName.SEAL_ARTIFACT: SealArtifactPayload,
    CommandName.START_ATTEMPT: StartAttemptPayload,
    CommandName.START_INTEGRATION: StartIntegrationPayload,
    CommandName.SUBMIT_CANDIDATE: SubmitCandidatePayload,
}
_ARITY = dict(TRANSITION_ARITY)


def _malformed(subject: str, *details: str) -> Refused[None]:
    return Refused(RefusalCode.MALFORMED_COMMAND, subject, None, tuple(details))


def well_formed(command: Command) -> Outcome[Command, None]:
    try:
        name = CommandName(command.name)
    except (TypeError, ValueError):
        return _malformed("name")
    expected_type = _PAYLOAD_TYPES[name]
    if not isinstance(command.payload, expected_type):
        return _malformed("payload", expected_type.__name__)
    target = command.payload.target_phase
    arity = _ARITY[name]
    if arity is TransitionArity.REQUIRED and target is None:
        return _malformed("target_phase", arity.value)
    if arity is TransitionArity.FORBIDDEN and target is not None:
        return _malformed("target_phase", arity.value)
    if arity is TransitionArity.FORBIDDEN and getattr(command.payload, "gate", None) is not None:
        return _malformed("gate")
    if isinstance(command.payload, StartAttemptPayload):
        if command.payload.attempt_phase is not AttemptPhase.IMPLEMENTATION and target is not None:
            return _malformed("attempt_form")
    if isinstance(command.payload, ApplyGateDecisionPayload):
        passing = command.payload.decision.verdict is GateVerdict.PASS
        if passing != (target is not None):
            return _malformed("decision_form")
    return Accepted(command)


def intended_edge(
    state: IncrementState, command: Command
) -> Outcome[TransitionEdge | None, IncrementState]:
    target = command.payload.target_phase
    if target is None:
        return Accepted(None)
    edge = edge_between(state.phase, target)
    if edge is None or edge.command is not command.name:
        code = (
            RefusalCode.INTEGRATED_REQUIRES_NEW_INCREMENT
            if state.phase is Phase.INTEGRATED
            else RefusalCode.UNKNOWN_TRANSITION
        )
        return Refused(code, "target_phase", state)
    if edge.gate is not None:
        decision = getattr(command.payload, "decision", None)
        if decision is None or decision.gate is not edge.gate:
            return Refused(RefusalCode.UNKNOWN_TRANSITION, "gate", state)
    return Accepted(edge)


def _precondition(state: IncrementState | None, subject: str) -> Refused[IncrementState | None]:
    return Refused(RefusalCode.PRECONDITION_UNSATISFIED, subject, state)


def _attempt_index(
    state: IncrementState,
    phase: AttemptPhase,
    expected_state: AttemptStateName | None = None,
) -> int | None:
    for index in range(len(state.attempts) - 1, -1, -1):
        attempt = state.attempts[index]
        if attempt.attempt_phase is phase and (
            expected_state is None or attempt.state is expected_state
        ):
            return index
    return None


def _validate_gate_attempt(state: IncrementState, decision: GateDecision) -> str | None:
    phase_by_gate = {
        Gate.G0: AttemptPhase.CLARIFICATION,
        Gate.G1: AttemptPhase.SPECIFICATION,
        Gate.G2: AttemptPhase.CONCEPTION,
        Gate.G3: AttemptPhase.IMPLEMENTATION,
    }
    if decision.gate in phase_by_gate:
        required = phase_by_gate[decision.gate]
        if _attempt_index(state, required, AttemptStateName.RUNNING) is None:
            return "running_attempt"
    elif decision.gate is Gate.G4 and decision.verdict is GateVerdict.PASS:
        if _attempt_index(state, AttemptPhase.IMPLEMENTATION, AttemptStateName.SUSPENDED) is None:
            return "suspended_implementation_attempt"
        review = _attempt_index(state, AttemptPhase.REVUE, AttemptStateName.FINISHED)
        if review is None:
            return "finished_review_attempt"
    elif decision.gate is Gate.G5 and decision.verdict is GateVerdict.PASS:
        if _attempt_index(state, AttemptPhase.IMPLEMENTATION, AttemptStateName.SUSPENDED) is None:
            return "suspended_implementation_attempt"
    return None


def _validate_preconditions(state: IncrementState | None, command: Command) -> Outcome[Command, IncrementState | None]:
    payload = command.payload
    if isinstance(payload, CreateIncrementPayload):
        if state is not None:
            return _precondition(state, "new_increment")
        if not payload.project_known:
            return _precondition(None, "project_known")
        if not payload.profile_known:
            return _precondition(None, "profile_known")
        return Accepted(command)
    if state is None:
        return _precondition(None, "increment_exists")

    if isinstance(payload, ApplyGateDecisionPayload):
        decision = payload.decision
        if not payload.report_current:
            return _precondition(state, "current_report")
        if decision.expected_state_version != command.expected_state_version:
            return _precondition(state, "decision_version")
        expected_gate = {
            Phase.CLARIFYING: Gate.G0,
            Phase.SPECIFYING: Gate.G1,
            Phase.DESIGNING: Gate.G2,
            Phase.IMPLEMENTING: Gate.G3,
            Phase.VERIFYING: Gate.G4,
            Phase.INTEGRATING: Gate.G5,
        }.get(state.phase)
        if decision.gate is not expected_gate:
            return _precondition(state, "gate")
        if decision.gate in (Gate.G3, Gate.G4, Gate.G5) and decision.candidate != state.current_candidate:
            return _precondition(state, "candidate")
        missing = _validate_gate_attempt(state, decision)
        if missing is not None:
            return _precondition(state, missing)
        reconciliation = decision.reconciliation
        if reconciliation is not None:
            intent = state.integration_intent
            if (
                decision.gate is not Gate.G5
                or intent is None
                or reconciliation.candidate != intent.candidate
                or reconciliation.destination != intent.destination
            ):
                return _precondition(state, "reconciliation")
        if decision.gate is Gate.G5 and decision.verdict is GateVerdict.PASS:
            if reconciliation is None:
                return _precondition(state, "reconciliation")

    elif isinstance(payload, CloseIncrementPayload):
        if payload.reason is None:
            return _precondition(state, "close_reason")
        try:
            CloseReason(payload.reason)
        except (TypeError, ValueError):
            return _precondition(state, "close_reason")
        if has_unreconciled_external_effect(state):
            return _precondition(state, "no_unreconciled_external_effect")

    elif isinstance(payload, ReviseIncrementPayload):
        if payload.requested_profile is not None and payload.requested_profile != state.profile:
            return Refused(RefusalCode.PROFILE_IMMUTABLE, "profile", state)
        if state.phase is Phase.INTEGRATING and has_unreconciled_external_effect(state):
            return _precondition(state, "no_unreconciled_external_effect")

    elif isinstance(payload, StartIntegrationPayload):
        if not isinstance(payload.candidate, ArtifactRef) or payload.candidate.kind is not ArtifactKind.CANDIDATE:
            return _precondition(state, "complete_candidate")
        decision = state.current_gate_decision
        if (
            state.phase is not Phase.ACCEPTED
            or decision is None
            or decision.gate is not Gate.G4
            or decision.verdict is not GateVerdict.PASS
            or decision.candidate != payload.candidate
            or state.current_candidate != payload.candidate
        ):
            return _precondition(state, "current_g4_pass")
        if state.expected_destination is None or payload.destination != state.expected_destination:
            return _precondition(state, "expected_destination")
        if has_unreconciled_external_effect(state):
            return _precondition(state, "no_unreconciled_external_effect")

    elif isinstance(payload, StartAttemptPayload):
        if payload.target_phase is None:
            expected_phase = {
                AttemptPhase.CLARIFICATION: Phase.CLARIFYING,
                AttemptPhase.SPECIFICATION: Phase.SPECIFYING,
                AttemptPhase.CONCEPTION: Phase.DESIGNING,
                AttemptPhase.IMPLEMENTATION: Phase.IMPLEMENTING,
                AttemptPhase.REVUE: Phase.VERIFYING,
            }[payload.attempt_phase]
            if state.phase is not expected_phase:
                return _precondition(state, "attempt_phase")
            result = start_attempt(
                state.attempts,
                attempt_id=payload.attempt_id,
                increment_id=state.increment_id,
                increment_revision=state.revision,
                attempt_phase=payload.attempt_phase,
                contract_ref=payload.contract_ref,
                contract_sealed=payload.contract_sealed,
                entry_gate_satisfied=payload.entry_gate_satisfied,
                budget_available=payload.budget_available,
            )
            if isinstance(result, Refused):
                return Refused(result.code, result.subject, state, result.details)
        else:
            decision = state.current_gate_decision
            index = _attempt_index(state, AttemptPhase.IMPLEMENTATION, AttemptStateName.SUSPENDED)
            if (
                decision is None
                or decision.gate is not Gate.G4
                or decision.verdict is not GateVerdict.FAIL
                or decision.candidate != payload.candidate
                or decision.candidate != state.current_candidate
            ):
                return _precondition(state, "current_g4_fail")
            if index is None:
                return _precondition(state, "suspended_implementation_attempt")
            if state.attempts[index].contract_ref != payload.contract_ref:
                return _precondition(state, "unchanged_contract")

    elif isinstance(payload, SealArtifactPayload):
        if not payload.dependencies_resolved:
            return _precondition(state, "dependencies_resolved")
        checked_ref = build_ref(
            artifact_id=payload.ref.artifact_id,
            revision=payload.ref.revision,
            kind=payload.ref.kind,
            schema_version=payload.ref.schema_version,
            digest=payload.ref.digest,
        )
        if isinstance(checked_ref, Refused):
            return Refused(checked_ref.code, checked_ref.subject, state, checked_ref.details)
        if not isinstance(payload.raw, bytes):
            return _precondition(state, "exact_bytes")
        revision_result = record_revision(state.revisions, payload.ref.artifact_id, payload.ref.revision)
        if isinstance(revision_result, Refused):
            return Refused(revision_result.code, revision_result.subject, state)
        seal_result = seal(state.sealed, payload.ref, payload.raw)
        if isinstance(seal_result, Refused):
            return Refused(seal_result.code, seal_result.subject, state)
        review_fields = (
            payload.review_attempt_id,
            payload.declared_review_output,
            payload.review_contract_ref,
        )
        if any(item is not None for item in review_fields):
            if any(item is None for item in review_fields):
                return _precondition(state, "review_output_declaration")
            index = next(
                (
                    i
                    for i, attempt in enumerate(state.attempts)
                    if attempt.attempt_id == payload.review_attempt_id
                ),
                None,
            )
            if (
                index is None
                or state.attempts[index].attempt_phase is not AttemptPhase.REVUE
                or state.attempts[index].state is not AttemptStateName.RUNNING
                or state.attempts[index].contract_ref != payload.review_contract_ref
                or payload.ref != payload.declared_review_output
            ):
                return _precondition(state, "review_output_declaration")

    elif isinstance(payload, RecordApprovalPayload):
        if not payload.actor_authorized:
            return _precondition(state, "actor_authorized")
        if not isinstance(payload.approval, Approval):
            return _precondition(state, "complete_target")
        checked = build_approval(
            approval_id=payload.approval.approval_id,
            actor=payload.approval.actor,
            role=payload.approval.role,
            target=payload.approval.target,
            scope=payload.approval.scope,
            decision=payload.approval.decision,
        )
        if isinstance(checked, Refused):
            return Refused(checked.code, checked.subject, state, checked.details)

    elif isinstance(payload, ProposeArtifactPayload):
        if not payload.revision_open:
            return _precondition(state, "revision_open")
        if not payload.kind_allowed:
            return _precondition(state, "kind_allowed")
    elif isinstance(payload, EvaluateGatePayload):
        if not payload.inputs_available:
            return _precondition(state, "inputs_available")
    elif isinstance(payload, SubmitCandidatePayload):
        if not payload.attempt_known:
            return _precondition(state, "attempt_known")
        if (
            not isinstance(payload.candidate, ArtifactRef)
            or payload.candidate.kind is not ArtifactKind.CANDIDATE
        ):
            return _precondition(state, "complete_candidate")
    elif isinstance(payload, CancelOperationPayload):
        if not payload.operation_active:
            return _precondition(state, "operation_active")
    return Accepted(command)


def validate(
    state: IncrementState | None, command: Command, project_state_version: int
) -> Outcome[Command, IncrementState | None]:
    formed = well_formed(command)
    if isinstance(formed, Refused):
        return formed
    if command.expected_state_version != project_state_version:
        return Refused(RefusalCode.STATE_VERSION_MISMATCH, "state_version", state)
    if state is not None and isinstance(command.payload, ReviseIncrementPayload):
        if command.payload.requested_profile is not None and command.payload.requested_profile != state.profile:
            return Refused(RefusalCode.PROFILE_IMMUTABLE, "profile", state)
    if state is None:
        edge_result: Outcome[TransitionEdge | None, IncrementState | None] = Accepted(None)
    elif command.name is CommandName.CREATE_INCREMENT:
        edge_result = Accepted(None)
    else:
        edge_result = intended_edge(state, command)
    if isinstance(edge_result, Refused):
        return edge_result
    return _validate_preconditions(state, command)


def create_increment(
    command: Command, project_state_version: int
) -> Outcome[IncrementState, None]:
    checked = validate(None, command, project_state_version)
    if isinstance(checked, Refused):
        return Refused(checked.code, checked.subject, None, checked.details)
    if not isinstance(command.payload, CreateIncrementPayload):
        return _malformed("payload", CreateIncrementPayload.__name__)
    return Accepted(
        IncrementState(
            increment_id=command.payload.increment_id,
            revision=1,
            phase=Phase.CLARIFYING,
            status=OperationalStatus.IDLE,
            profile=command.payload.profile,
            expected_destination=command.payload.expected_destination,
        )
    )


def _replace_attempt(
    attempts: tuple[AttemptState, ...], index: int, updated: AttemptState
) -> tuple[AttemptState, ...]:
    return attempts[:index] + (updated,) + attempts[index + 1 :]


def _finish_current(
    state: IncrementState, reason: FinishReason, trigger: AttemptTrigger
) -> tuple[AttemptState, ...]:
    for index in range(len(state.attempts) - 1, -1, -1):
        attempt = state.attempts[index]
        if attempt.state is not AttemptStateName.FINISHED:
            result = transition(attempt, AttemptStateName.FINISHED, trigger, reason)
            if isinstance(result, Accepted):
                return _replace_attempt(state.attempts, index, result.value)
    return state.attempts


def apply_command(
    state: IncrementState, command: Command, project_state_version: int
) -> Outcome[IncrementState, IncrementState]:
    checked = validate(state, command, project_state_version)
    if isinstance(checked, Refused):
        return Refused(checked.code, checked.subject, state, checked.details)
    edge_result = intended_edge(state, command)
    if isinstance(edge_result, Refused):
        return edge_result
    edge = edge_result.value
    payload = command.payload

    if isinstance(payload, ApplyGateDecisionPayload):
        decision = payload.decision
        attempts = state.attempts
        intent = state.integration_intent
        if decision.reconciliation is not None and intent is not None:
            intent = replace(intent, reconciled=True)
        if decision.verdict is GateVerdict.PASS:
            if decision.gate in (Gate.G0, Gate.G1, Gate.G2):
                phase = {
                    Gate.G0: AttemptPhase.CLARIFICATION,
                    Gate.G1: AttemptPhase.SPECIFICATION,
                    Gate.G2: AttemptPhase.CONCEPTION,
                }[decision.gate]
                index = _attempt_index(state, phase, AttemptStateName.RUNNING)
                result = transition(
                    attempts[index],
                    AttemptStateName.FINISHED,
                    AttemptTrigger.PHASE_EXIT,
                    FinishReason.PHASE_COMPLETED,
                )
                attempts = _replace_attempt(attempts, index, result.value)
            elif decision.gate is Gate.G3:
                index = _attempt_index(state, AttemptPhase.IMPLEMENTATION, AttemptStateName.RUNNING)
                result = transition(attempts[index], AttemptStateName.SUSPENDED, AttemptTrigger.G3_PASS)
                attempts = _replace_attempt(attempts, index, result.value)
            elif decision.gate is Gate.G5:
                index = _attempt_index(state, AttemptPhase.IMPLEMENTATION, AttemptStateName.SUSPENDED)
                result = transition(
                    attempts[index],
                    AttemptStateName.FINISHED,
                    AttemptTrigger.G5_PASS,
                    FinishReason.INTEGRATION_SUCCEEDED,
                )
                attempts = _replace_attempt(attempts, index, result.value)
        return Accepted(
            replace(
                state,
                phase=edge.target if edge is not None else state.phase,
                attempts=attempts,
                current_gate_decision=decision,
                integration_intent=intent,
            )
        )

    if isinstance(payload, CloseIncrementPayload):
        attempts = _finish_current(
            state, FinishReason.INCREMENT_CLOSED, AttemptTrigger.CLOSE_INCREMENT
        )
        return Accepted(replace(state, phase=edge.target, attempts=attempts))

    if isinstance(payload, ReviseIncrementPayload):
        attempts = _finish_current(
            state, FinishReason.REVISION_REQUESTED, AttemptTrigger.REVISE_INCREMENT
        )
        return Accepted(
            replace(
                state,
                revision=state.revision + 1,
                phase=edge.target,
                attempts=attempts,
                current_candidate=None,
                current_gate_decision=None,
                integration_intent=None,
            )
        )

    if isinstance(payload, StartIntegrationPayload):
        return Accepted(
            replace(
                state,
                phase=edge.target,
                integration_intent=IntegrationIntent(payload.candidate, payload.destination),
            )
        )

    if isinstance(payload, StartAttemptPayload):
        if edge is None:
            result = start_attempt(
                state.attempts,
                attempt_id=payload.attempt_id,
                increment_id=state.increment_id,
                increment_revision=state.revision,
                attempt_phase=payload.attempt_phase,
                contract_ref=payload.contract_ref,
                contract_sealed=payload.contract_sealed,
                entry_gate_satisfied=payload.entry_gate_satisfied,
                budget_available=payload.budget_available,
            )
            return Accepted(replace(state, attempts=state.attempts + (result.value,)))
        index = _attempt_index(state, AttemptPhase.IMPLEMENTATION, AttemptStateName.SUSPENDED)
        result = transition(
            state.attempts[index],
            AttemptStateName.RUNNING,
            AttemptTrigger.START_ATTEMPT_AFTER_G4_FAIL,
        )
        return Accepted(
            replace(
                state,
                phase=edge.target,
                attempts=_replace_attempt(state.attempts, index, result.value),
                current_gate_decision=None,
            )
        )

    if isinstance(payload, SealArtifactPayload):
        revision_result = record_revision(state.revisions, payload.ref.artifact_id, payload.ref.revision)
        seal_result = seal(state.sealed, payload.ref, payload.raw)
        attempts = state.attempts
        if payload.review_attempt_id is not None:
            index = next(i for i, item in enumerate(attempts) if item.attempt_id == payload.review_attempt_id)
            result = transition(
                attempts[index],
                AttemptStateName.FINISHED,
                AttemptTrigger.PHASE_EXIT,
                FinishReason.PHASE_COMPLETED,
            )
            attempts = _replace_attempt(attempts, index, result.value)
        current_decision = state.current_gate_decision
        if (
            current_decision is not None
            and payload.change_kind is not None
            and current_decision.gate in invalidated_by(payload.change_kind)
        ):
            current_decision = None
        return Accepted(
            replace(
                state,
                attempts=attempts,
                sealed=seal_result.value,
                revisions=revision_result.value,
                current_gate_decision=current_decision,
            )
        )

    if isinstance(payload, RecordApprovalPayload):
        result = record(state.approvals, payload.approval)
        return Accepted(replace(state, approvals=result.value))

    if isinstance(payload, SubmitCandidatePayload):
        return Accepted(
            replace(
                state,
                current_candidate=payload.candidate,
                current_gate_decision=None,
            )
        )

    return Accepted(state)
