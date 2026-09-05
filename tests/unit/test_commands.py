import unittest
from dataclasses import replace

from domain.attempts import transition
from domain.commands import (
    PRECONDITIONS,
    TRANSITION_ARITY,
    ApplyGateDecisionPayload,
    CancelOperationPayload,
    CloseIncrementPayload,
    Command,
    CreateIncrementPayload,
    EvaluateGatePayload,
    ProposeArtifactPayload,
    RecordApprovalPayload,
    ReviseIncrementPayload,
    SealArtifactPayload,
    StartAttemptPayload,
    StartIntegrationPayload,
    SubmitCandidatePayload,
    apply_command,
    create_increment,
    intended_edge,
    validate,
    well_formed,
)
from domain.outcomes import Accepted, RefusalCode
from domain.phases import TRANSITIONS
from domain.references import Approval
from domain.state import IntegrationIntent, IntegrationReconciliation
from domain.vocabulary import (
    ApprovalDecision,
    ArtifactKind,
    AttemptPhase,
    AttemptStateName,
    AttemptTrigger,
    ChangeKind,
    CloseReason,
    CommandName,
    Gate,
    GateVerdict,
    OperationalStatus,
    Phase,
)
from tests.unit.support import attempt, gate_decision, ref, state


class CommandsTest(unittest.TestCase):
    def command(self, name, payload, version=1):
        return Command("command", name, version, payload)

    def test_all_commands_declare_arity_preconditions_and_payload_shape(self):
        self.assertEqual({name for name, _ in TRANSITION_ARITY}, set(CommandName))
        self.assertEqual({name for name, _ in PRECONDITIONS}, set(CommandName))
        malformed = self.command(
            CommandName.CLOSE_INCREMENT,
            CloseIncrementPayload(CloseReason.ABANDONED, None),
        )
        self.assertEqual((well_formed(malformed).code, well_formed(malformed).subject), (RefusalCode.MALFORMED_COMMAND, "target_phase"))
        wrong_payload = self.command(CommandName.CLOSE_INCREMENT, EvaluateGatePayload(True))
        self.assertEqual(well_formed(wrong_payload).subject, "payload")

    def test_gate_decision_form_is_bound_to_verdict(self):
        passing = gate_decision(Gate.G0, GateVerdict.PASS)
        failing = gate_decision(Gate.G0, GateVerdict.FAIL)
        self.assertEqual(
            well_formed(self.command(CommandName.APPLY_GATE_DECISION, ApplyGateDecisionPayload(passing, None))).subject,
            "decision_form",
        )
        self.assertEqual(
            well_formed(self.command(CommandName.APPLY_GATE_DECISION, ApplyGateDecisionPayload(failing, Phase.SPECIFYING))).subject,
            "decision_form",
        )
        wrong_phase = state(Phase.DESIGNING, attempts=(attempt(AttemptPhase.CONCEPTION),))
        refusal = validate(
            wrong_phase,
            self.command(
                CommandName.APPLY_GATE_DECISION,
                ApplyGateDecisionPayload(gate_decision(Gate.G4, GateVerdict.FAIL), None),
            ),
            1,
        )
        self.assertEqual(refusal.subject, "gate")

    def test_envelope_precedes_transition_and_refusal_preserves_identity(self):
        command = self.command(
            CommandName.CLOSE_INCREMENT,
            CloseIncrementPayload(CloseReason.ABANDONED, Phase.CLOSED),
            version=2,
        )
        original = state()
        refused = apply_command(original, command, 1)
        self.assertEqual(refused.code, RefusalCode.STATE_VERSION_MISMATCH)
        self.assertIs(refused.state, original)

    def test_create_increment_fixes_profile_and_initial_state(self):
        command = self.command(
            CommandName.CREATE_INCREMENT,
            CreateIncrementPayload("INC-2", "strict", expected_destination="main"),
        )
        created = create_increment(command, 1)
        self.assertIsInstance(created, Accepted)
        self.assertEqual(
            (created.value.revision, created.value.phase, created.value.profile),
            (1, Phase.CLARIFYING, "strict"),
        )

    def test_edges_require_pair_command_and_gate(self):
        original = state(Phase.CLARIFYING)
        wrong_command = self.command(
            CommandName.CLOSE_INCREMENT,
            CloseIncrementPayload(CloseReason.ABANDONED, Phase.SPECIFYING),
        )
        self.assertEqual(intended_edge(original, wrong_command).code, RefusalCode.UNKNOWN_TRANSITION)
        wrong_gate = self.command(
            CommandName.APPLY_GATE_DECISION,
            ApplyGateDecisionPayload(gate_decision(Gate.G1, GateVerdict.PASS), Phase.SPECIFYING),
        )
        self.assertEqual(intended_edge(original, wrong_gate).code, RefusalCode.UNKNOWN_TRANSITION)
        integrated = replace(original, phase=Phase.INTEGRATED)
        revise = self.command(CommandName.REVISE_INCREMENT, ReviseIncrementPayload(Phase.DESIGNING))
        self.assertEqual(
            intended_edge(integrated, revise).code,
            RefusalCode.INTEGRATED_REQUIRES_NEW_INCREMENT,
        )

    def test_close_accepts_each_reason_from_each_nonterminal_phase(self):
        for phase in Phase:
            if phase in (Phase.INTEGRATED, Phase.CLOSED):
                continue
            for reason in CloseReason:
                original = state(phase)
                command = self.command(
                    CommandName.CLOSE_INCREMENT,
                    CloseIncrementPayload(reason, Phase.CLOSED),
                )
                result = apply_command(original, command, 1)
                self.assertIsInstance(result, Accepted, (phase, reason, result))
                self.assertEqual(result.value.phase, Phase.CLOSED)
        original = state()
        missing = self.command(CommandName.CLOSE_INCREMENT, CloseIncrementPayload(None, Phase.CLOSED))
        self.assertEqual(validate(original, missing, 1).subject, "close_reason")
        blocked = replace(original, other_unreconciled_external_effect=True)
        valid = self.command(CommandName.CLOSE_INCREMENT, CloseIncrementPayload(CloseReason.ABANDONED, Phase.CLOSED))
        refusal = apply_command(blocked, valid, 1)
        self.assertEqual(refusal.subject, "no_unreconciled_external_effect")
        self.assertIs(refusal.state, blocked)

    def test_revise_opens_revision_finishes_current_attempt_and_preserves_seals(self):
        running = attempt(AttemptPhase.CONCEPTION)
        original = state(Phase.DESIGNING, attempts=(running,))
        command = self.command(CommandName.REVISE_INCREMENT, ReviseIncrementPayload(Phase.SPECIFYING))
        result = apply_command(original, command, 1)
        self.assertEqual((result.value.phase, result.value.revision), (Phase.SPECIFYING, 2))
        self.assertEqual(result.value.attempts[0].finish_reason.value, "revision_requested")
        self.assertIs(result.value.sealed, original.sealed)
        profile_change = self.command(CommandName.REVISE_INCREMENT, ReviseIncrementPayload(Phase.SPECIFYING, "exploration"))
        refusal = apply_command(original, profile_change, 1)
        self.assertEqual(refusal.code, RefusalCode.PROFILE_IMMUTABLE)
        self.assertIs(refusal.state, original)

    def test_open_suspend_and_resume_implementation_attempt(self):
        contract = ref("contract")
        open_command = self.command(
            CommandName.START_ATTEMPT,
            StartAttemptPayload("impl", AttemptPhase.IMPLEMENTATION, contract, True, True, True),
        )
        implementing = state(Phase.IMPLEMENTING)
        opened = apply_command(implementing, open_command, 1).value
        candidate = ref("candidate", kind=ArtifactKind.CANDIDATE)
        opened = replace(opened, current_candidate=candidate)
        g3 = self.command(
            CommandName.APPLY_GATE_DECISION,
            ApplyGateDecisionPayload(gate_decision(Gate.G3, GateVerdict.PASS, candidate=candidate), Phase.VERIFYING),
        )
        suspended = apply_command(opened, g3, 1).value
        self.assertEqual(suspended.attempts[0].state, AttemptStateName.SUSPENDED)
        failed = replace(suspended, current_gate_decision=gate_decision(Gate.G4, GateVerdict.FAIL, candidate=candidate))
        resume = self.command(
            CommandName.START_ATTEMPT,
            StartAttemptPayload("ignored", AttemptPhase.IMPLEMENTATION, contract, True, True, True, candidate, Phase.IMPLEMENTING),
        )
        resumed = apply_command(failed, resume, 1).value
        self.assertEqual((len(resumed.attempts), resumed.attempts[0].state), (1, AttemptStateName.RUNNING))
        self.assertIsNone(resumed.current_gate_decision)

    def test_start_integration_requires_exact_current_g4_pass_and_records_intent(self):
        candidate = ref("candidate", kind=ArtifactKind.CANDIDATE)
        decision = gate_decision(Gate.G4, GateVerdict.PASS, candidate=candidate)
        accepted = state(Phase.ACCEPTED, candidate=candidate, decision=decision)
        command = self.command(
            CommandName.START_INTEGRATION,
            StartIntegrationPayload(candidate, "main", Phase.INTEGRATING),
        )
        result = apply_command(accepted, command, 1)
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.value.phase, Phase.INTEGRATING)
        self.assertEqual(result.value.integration_intent.candidate, candidate)
        self.assertFalse(result.value.integration_intent.reconciled)
        wrong = replace(accepted, current_candidate=ref("other", kind=ArtifactKind.CANDIDATE))
        refusal = apply_command(wrong, command, 1)
        self.assertEqual(refusal.subject, "current_g4_pass")
        self.assertIs(refusal.state, wrong)

    def test_submit_seal_and_approval_update_only_their_registries(self):
        candidate = ref("candidate", raw=b"candidate", kind=ArtifactKind.CANDIDATE)
        original = state(decision=gate_decision(Gate.G1, GateVerdict.FAIL))
        submit = self.command(CommandName.SUBMIT_CANDIDATE, SubmitCandidatePayload(candidate, True))
        submitted = apply_command(original, submit, 1).value
        self.assertEqual(submitted.current_candidate, candidate)
        self.assertIsNone(submitted.current_gate_decision)

        raw = b"candidate"
        seal_command = self.command(
            CommandName.SEAL_ARTIFACT,
            SealArtifactPayload(candidate, raw, True, ChangeKind.CANDIDATE),
        )
        sealed = apply_command(submitted, seal_command, 1).value
        self.assertEqual(len(sealed.sealed.entries), 1)
        self.assertEqual(len(sealed.revisions.entries), 1)

        approval = Approval("approval", "actor", "owner", candidate, "all", ApprovalDecision.APPROVED)
        approve = self.command(CommandName.RECORD_APPROVAL, RecordApprovalPayload(approval, True))
        approved = apply_command(sealed, approve, 1).value
        self.assertEqual(approved.approvals.entries, (approval,))

        wrong_kind = self.command(
            CommandName.SUBMIT_CANDIDATE,
            SubmitCandidatePayload(ref("not-a-candidate"), True),
        )
        self.assertEqual(validate(original, wrong_kind, 1).subject, "complete_candidate")

    def test_review_report_and_g5_complete_attempt_lifecycle(self):
        candidate = ref("candidate", kind=ArtifactKind.CANDIDATE)
        contract = ref("review-contract")
        review = attempt(AttemptPhase.REVUE, identifier="review", contract=contract)
        implementation = attempt(AttemptPhase.IMPLEMENTATION, identifier="impl")
        implementation = transition(implementation, AttemptStateName.SUSPENDED, AttemptTrigger.G3_PASS).value
        reviewing = state(Phase.VERIFYING, attempts=(implementation, review), candidate=candidate)
        report_raw = b"review"
        report = ref("review-report", raw=report_raw)
        seal_report = self.command(
            CommandName.SEAL_ARTIFACT,
            SealArtifactPayload(report, report_raw, True, review_attempt_id="review", declared_review_output=report, review_contract_ref=contract),
        )
        reviewed = apply_command(reviewing, seal_report, 1).value
        self.assertEqual(reviewed.attempts[1].finish_reason.value, "phase_completed")

        intent_state = replace(
            reviewed,
            phase=Phase.INTEGRATING,
            integration_intent=IntegrationIntent(candidate, "main"),
        )
        receipt = ref("receipt")
        decision = gate_decision(Gate.G5, GateVerdict.PASS, candidate=candidate)
        decision = replace(decision, reconciliation=IntegrationReconciliation(candidate, "main", receipt))
        command = self.command(
            CommandName.APPLY_GATE_DECISION,
            ApplyGateDecisionPayload(decision, Phase.INTEGRATED),
        )
        integrated = apply_command(intent_state, command, 1).value
        self.assertEqual(integrated.phase, Phase.INTEGRATED)
        self.assertTrue(integrated.integration_intent.reconciled)
        self.assertEqual(integrated.attempts[0].finish_reason.value, "integration_succeeded")

    def test_validation_only_commands_name_failed_preconditions(self):
        cases = (
            (CommandName.PROPOSE_ARTIFACT, ProposeArtifactPayload(False, True), "revision_open"),
            (CommandName.EVALUATE_GATE, EvaluateGatePayload(False), "inputs_available"),
            (CommandName.CANCEL_OPERATION, CancelOperationPayload(False), "operation_active"),
        )
        for name, payload, subject in cases:
            refusal = validate(state(), self.command(name, payload), 1)
            self.assertEqual((refusal.code, refusal.subject), (RefusalCode.PRECONDITION_UNSATISFIED, subject))

    def test_transition_table_has_expected_partition(self):
        returns = [edge for edge in TRANSITIONS if edge.command in (CommandName.REVISE_INCREMENT, CommandName.START_ATTEMPT)]
        self.assertEqual(len(returns), 11)
        self.assertEqual(sum(edge.command is CommandName.REVISE_INCREMENT for edge in returns), 10)
        self.assertFalse(any(edge.origin in (Phase.INTEGRATED, Phase.CLOSED) for edge in TRANSITIONS))
