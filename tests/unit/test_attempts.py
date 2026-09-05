import unittest

from domain.attempts import allowed_attempt_transitions, finish_reason_triggers, start_attempt, transition
from domain.outcomes import Accepted, RefusalCode
from domain.vocabulary import AttemptPhase, AttemptStateName, AttemptTrigger, FinishReason
from tests.unit.support import attempt, ref


class AttemptsTest(unittest.TestCase):
    def test_creation_requires_contract_entry_condition_and_budget(self):
        arguments = dict(
            attempt_id="A", increment_id="INC", increment_revision=7,
            attempt_phase=AttemptPhase.CLARIFICATION, contract_ref=ref("contract"),
            contract_sealed=True, entry_gate_satisfied=True, budget_available=True,
        )
        created = start_attempt((), **arguments)
        self.assertIsInstance(created, Accepted)
        self.assertEqual((created.value.state, created.value.increment_revision), (AttemptStateName.RUNNING, 7))
        for field in ("contract_sealed", "entry_gate_satisfied", "budget_available"):
            refused = start_attempt((), **(arguments | {field: False}))
            self.assertEqual((refused.code, refused.subject), (RefusalCode.PRECONDITION_UNSATISFIED, field))

    def test_running_conflict_only_applies_to_distinct_phases(self):
        existing = attempt(AttemptPhase.IMPLEMENTATION)
        common = dict(
            attempt_id="next", increment_id="INC", increment_revision=1,
            contract_ref=ref("contract-2"), contract_sealed=True,
            entry_gate_satisfied=True, budget_available=True,
        )
        same = start_attempt((existing,), attempt_phase=AttemptPhase.IMPLEMENTATION, **common)
        different = start_attempt((existing,), attempt_phase=AttemptPhase.REVUE, **common)
        self.assertIsInstance(same, Accepted)
        self.assertEqual(different.code, RefusalCode.RUNNING_ATTEMPT_CONFLICT)
        suspended = transition(existing, AttemptStateName.SUSPENDED, AttemptTrigger.G3_PASS).value
        self.assertIsInstance(start_attempt((suspended,), attempt_phase=AttemptPhase.REVUE, **common), Accepted)

    def test_only_declared_state_pairs_and_triggers_are_accepted(self):
        self.assertEqual(len(allowed_attempt_transitions()), 4)
        running = attempt(AttemptPhase.IMPLEMENTATION)
        suspended = transition(running, AttemptStateName.SUSPENDED, AttemptTrigger.G3_PASS)
        self.assertIsInstance(suspended, Accepted)
        resumed = transition(suspended.value, AttemptStateName.RUNNING, AttemptTrigger.EXPLICIT_RESUME)
        self.assertIsInstance(resumed, Accepted)
        self.assertEqual(
            transition(running, AttemptStateName.FINISHED, AttemptTrigger.PHASE_EXIT).code,
            RefusalCode.MISSING_FINISH_REASON,
        )
        wrong = transition(
            running, AttemptStateName.FINISHED, AttemptTrigger.G5_PASS, FinishReason.PHASE_COMPLETED
        )
        self.assertEqual(wrong.code, RefusalCode.UNKNOWN_ATTEMPT_TRANSITION)

    def test_finish_reasons_have_unique_triggers_and_identity_is_stable(self):
        self.assertEqual(len(finish_reason_triggers()), 6)
        original = attempt(AttemptPhase.CONCEPTION, identifier="stable")
        finished = transition(
            original, AttemptStateName.FINISHED,
            AttemptTrigger.PHASE_EXIT, FinishReason.PHASE_COMPLETED,
        ).value
        self.assertEqual(finished.contract_ref, original.contract_ref)
        self.assertTrue(all(event.attempt_id == "stable" for event in finished.history))
