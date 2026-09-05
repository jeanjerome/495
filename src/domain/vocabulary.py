"""Ensembles finis qui définissent le vocabulaire du domaine."""

from enum import StrEnum


class Phase(StrEnum):
    CLARIFYING = "clarifying"
    SPECIFYING = "specifying"
    DESIGNING = "designing"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    ACCEPTED = "accepted"
    INTEGRATING = "integrating"
    INTEGRATED = "integrated"
    CLOSED = "closed"


class OperationalStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    BLOCKED = "blocked"
    PAUSED = "paused"
    RECONCILING = "reconciling"


class CommandName(StrEnum):
    APPLY_GATE_DECISION = "ApplyGateDecision"
    CANCEL_OPERATION = "CancelOperation"
    CLOSE_INCREMENT = "CloseIncrement"
    CREATE_INCREMENT = "CreateIncrement"
    EVALUATE_GATE = "EvaluateGate"
    PROPOSE_ARTIFACT = "ProposeArtifact"
    RECORD_APPROVAL = "RecordApproval"
    REVISE_INCREMENT = "ReviseIncrement"
    SEAL_ARTIFACT = "SealArtifact"
    START_ATTEMPT = "StartAttempt"
    START_INTEGRATION = "StartIntegration"
    SUBMIT_CANDIDATE = "SubmitCandidate"


class ArtifactKind(StrEnum):
    PROPOSAL = "proposal"
    REQUIREMENT_SET = "requirement_set"
    SCENARIO_SET = "scenario_set"
    DESIGN = "design"
    DECISION = "decision"
    INTERFACE_CONTRACT = "interface_contract"
    TASK_PLAN = "task_plan"
    CHECK_PLAN = "check_plan"
    EXECUTION_CONTRACT = "execution_contract"
    CANDIDATE = "candidate"
    OBSERVATION = "observation"
    APPROVAL = "approval"
    GATE_DECISION = "gate_decision"


class CloseReason(StrEnum):
    ABANDONED = "abandoned"
    SUPERSEDED = "superseded"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EXPLORATION_COMPLETE = "exploration_complete"
    INVALID_PROTOCOL = "invalid_protocol"


class LinkType(StrEnum):
    DEPENDS_ON = "depends_on"
    VERIFIES = "verifies"
    IMPLEMENTS = "implements"
    APPROVES = "approves"
    SUPERSEDES = "supersedes"
    RELATED_TO = "related_to"

    @property
    def executory(self) -> bool:
        return self is not LinkType.RELATED_TO


class AttemptPhase(StrEnum):
    CLARIFICATION = "clarification"
    SPECIFICATION = "specification"
    CONCEPTION = "conception"
    IMPLEMENTATION = "implementation"
    REVUE = "revue"


class AttemptStateName(StrEnum):
    RUNNING = "running"
    SUSPENDED = "suspended"
    FINISHED = "finished"


class FinishReason(StrEnum):
    PHASE_COMPLETED = "phase_completed"
    INTEGRATION_SUCCEEDED = "integration_succeeded"
    REVISION_REQUESTED = "revision_requested"
    INCREMENT_CLOSED = "increment_closed"
    DEFINITIVE_FAILURE = "definitive_failure"
    BUDGET_EXHAUSTED = "budget_exhausted"


class AttemptTrigger(StrEnum):
    START_ATTEMPT = "start_attempt"
    G3_PASS = "g3_pass"
    EXPLICIT_SUSPENSION = "explicit_suspension"
    START_ATTEMPT_AFTER_G4_FAIL = "start_attempt_after_g4_fail"
    EXPLICIT_RESUME = "explicit_resume"
    PHASE_EXIT = "phase_exit"
    G5_PASS = "g5_pass"
    REVISE_INCREMENT = "revise_increment"
    CLOSE_INCREMENT = "close_increment"
    DEFINITIVE_FAILURE = "definitive_failure"
    BUDGET_EXHAUSTED = "budget_exhausted"


class EdgeKind(StrEnum):
    FORWARD = "forward"
    CORRECTION = "correction"
    RETURN = "return"
    CLOSURE = "closure"
    REVISION = "revision"


class ChangeKind(StrEnum):
    MANDATORY_REQUIREMENT_OR_SCENARIO = "mandatory_requirement_or_scenario"
    DECISION_OR_INTERFACE_CONTRACT = "decision_or_interface_contract"
    POLICY_VERIFIER_ENVIRONMENT_OR_BASELINE = "policy_verifier_environment_or_baseline"
    CANDIDATE = "candidate"
    DESTINATION_BRANCH_ADVANCED = "destination_branch_advanced"
    UNCONSUMED_RELATED_TO_NOTE = "unconsumed_related_to_note"


class Gate(StrEnum):
    G0 = "G0"
    G1 = "G1"
    G2 = "G2"
    G3 = "G3"
    G4 = "G4"
    G5 = "G5"


class GateVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    NOT_APPROVED = "not_approved"


ARTIFACT_KINDS = frozenset(ArtifactKind)
EXECUTORY_LINK_TYPES = frozenset(kind for kind in LinkType if kind.executory)
TERMINAL_PHASES = frozenset((Phase.INTEGRATED, Phase.CLOSED))
