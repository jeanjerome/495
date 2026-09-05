import unittest

from domain.outcomes import Accepted, RefusalCode
from validation import (
    BudgetFact,
    Fact,
    FactState,
    Observation,
    build_fact_bundle,
    qualify_observation,
)
from tests.unit.support import ref


class ValidationTest(unittest.TestCase):
    def test_observation_qualification_distinguishes_three_states(self):
        evidence = (ref("evidence"),)
        satisfied = qualify_observation(Observation("O1", "check", True, evidence))
        violated = qualify_observation(Observation("O2", "check", False, evidence))
        unresolved = qualify_observation(Observation("O3", "check", None, evidence))
        self.assertEqual(satisfied.state, FactState.SATISFIED)
        self.assertEqual(violated.state, FactState.VIOLATED)
        self.assertEqual(unresolved.state, FactState.UNRESOLVED)
        self.assertEqual(violated.evidence, evidence)

    def test_stale_malformed_or_inapplicable_observation_is_unresolved(self):
        target = ref("target")
        cases = (
            Observation("O1", "check", True, fresh=False),
            Observation("O2", "check", True, well_formed=False),
            Observation("O3", "check", True, target=target, expected_target=ref("other")),
            Observation("O4", "check", True, expected_digest="sha256:expected"),
        )
        for observation in cases:
            self.assertEqual(qualify_observation(observation).state, FactState.UNRESOLVED)

    def test_digest_mismatch_is_a_demonstrated_violation(self):
        fact = qualify_observation(
            Observation(
                "O",
                "digest",
                True,
                observed_digest="sha256:observed",
                expected_digest="sha256:expected",
            )
        )
        self.assertEqual((fact.state, fact.detail), (FactState.VIOLATED, "digest_mismatch"))

    def test_fact_bundle_is_canonical_and_refuses_duplicate_keys(self):
        first = Fact("b", FactState.SATISFIED)
        second = Fact("a", FactState.VIOLATED)
        bundle = build_fact_bundle(
            checks=(first, second),
            artifacts=(ref("B"), ref("A")),
            digests=(("b", "2"), ("a", "1")),
            capabilities=("python", "git", "python"),
            budgets=(BudgetFact("models", 1, 2), BudgetFact("checks", 2, 2)),
        )
        self.assertIsInstance(bundle, Accepted)
        self.assertEqual(tuple(item.fact_id for item in bundle.value.checks), ("a", "b"))
        self.assertEqual(bundle.value.capabilities, ("git", "python"))
        duplicate = build_fact_bundle(checks=(first, first))
        self.assertEqual(
            (duplicate.code, duplicate.subject),
            (RefusalCode.PRECONDITION_UNSATISFIED, "unique_checks"),
        )
