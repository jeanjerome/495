import itertools
import unittest

from domain.outcomes import Accepted, RefusalCode
from domain.references import Approval, ApprovalRegistry
from domain.vocabulary import ApprovalDecision, ArtifactKind, Gate, GateVerdict, Phase
from policy import EvaluationContext, PolicyOperator, build_policy, evaluate_gate
from validation import BudgetFact, Fact, FactState, build_fact_bundle
from tests.unit.support import ref, state


class PolicyTest(unittest.TestCase):
    def atom(self, operator, obligation="obligation", **fields):
        return {"operator": operator, "obligation": obligation, **fields}

    def document(self, root, gate="G2"):
        return {"schema_version": "policy-1", "gate": gate, "root": root}

    def context(self):
        return EvaluationContext("decision", "engine-1", 7, "sha256:bundle")

    def decision(self, root, bundle=None, approvals=ApprovalRegistry(), gate=Gate.G2):
        policy = build_policy(self.document(root, gate.value)).value
        return evaluate_gate(
            state(Phase.DESIGNING),
            gate,
            policy,
            bundle or build_fact_bundle().value,
            approvals,
            self.context(),
        )

    def target_document(self, target):
        return {
            "artifact_id": target.artifact_id,
            "revision": target.revision,
            "kind": target.kind.value,
            "schema_version": target.schema_version,
            "digest": target.digest,
        }

    def test_builder_accepts_only_closed_operators_and_fields(self):
        root = self.atom("check_passed", key="unit")
        built = build_policy(self.document(root))
        self.assertIsInstance(built, Accepted)
        self.assertEqual(built.value.root.operator, PolicyOperator.CHECK_PASSED)
        unknown = build_policy(self.document(self.atom("python", expression="True")))
        self.assertEqual(unknown.code, RefusalCode.UNKNOWN_KIND)
        extra = build_policy(self.document(root | {"expression": "True"}))
        self.assertEqual(extra.subject, "root.fields")
        missing = build_policy(self.document({"operator": "check_passed", "obligation": "x"}))
        self.assertEqual(missing.code, RefusalCode.MISSING_FIELD)

    def test_policy_digest_is_canonical(self):
        first = self.document(self.atom("check_passed", key="unit"))
        second = {
            "root": {"key": "unit", "obligation": "obligation", "operator": "check_passed"},
            "gate": "G2",
            "schema_version": "policy-1",
        }
        self.assertEqual(build_policy(first).value.digest, build_policy(second).value.digest)

    def test_all_atomic_operators_have_positive_and_negative_results(self):
        target = ref("target")
        approved = Approval("approval", "actor", "owner", target, "all", ApprovalDecision.APPROVED)
        refused = Approval("refusal", "actor", "owner", target, "all", ApprovalDecision.NOT_APPROVED)
        target_field = self.target_document(target)
        cases = (
            (
                self.atom("check_passed", key="unit"),
                build_fact_bundle(checks=(Fact("unit", FactState.SATISFIED),)).value,
                ApprovalRegistry(),
                GateVerdict.PASS,
            ),
            (
                self.atom("check_passed", key="unit"),
                build_fact_bundle(checks=(Fact("unit", FactState.VIOLATED),)).value,
                ApprovalRegistry(),
                GateVerdict.FAIL,
            ),
            (
                self.atom("approval_present", target=target_field),
                build_fact_bundle().value,
                ApprovalRegistry((approved,)),
                GateVerdict.PASS,
            ),
            (
                self.atom("approval_present", target=target_field),
                build_fact_bundle().value,
                ApprovalRegistry((refused,)),
                GateVerdict.FAIL,
            ),
            (
                self.atom("artifact_present", target=target_field),
                build_fact_bundle(artifacts=(target,)).value,
                ApprovalRegistry(),
                GateVerdict.PASS,
            ),
            (
                self.atom("artifact_present", target=target_field),
                build_fact_bundle().value,
                ApprovalRegistry(),
                GateVerdict.INDETERMINATE,
            ),
            (
                self.atom("digest_matches", key="candidate", expected_digest="sha256:a"),
                build_fact_bundle(digests=(("candidate", "sha256:a"),)).value,
                ApprovalRegistry(),
                GateVerdict.PASS,
            ),
            (
                self.atom("digest_matches", key="candidate", expected_digest="sha256:a"),
                build_fact_bundle(digests=(("candidate", "sha256:b"),)).value,
                ApprovalRegistry(),
                GateVerdict.FAIL,
            ),
            (
                self.atom("capability_satisfied", key="python"),
                build_fact_bundle(capabilities=("python",)).value,
                ApprovalRegistry(),
                GateVerdict.PASS,
            ),
            (
                self.atom("capability_satisfied", key="python"),
                build_fact_bundle().value,
                ApprovalRegistry(),
                GateVerdict.INDETERMINATE,
            ),
            (
                self.atom("within_budget", key="models"),
                build_fact_bundle(budgets=(BudgetFact("models", 2, 2),)).value,
                ApprovalRegistry(),
                GateVerdict.PASS,
            ),
            (
                self.atom("within_budget", key="models"),
                build_fact_bundle(budgets=(BudgetFact("models", 3, 2),)).value,
                ApprovalRegistry(),
                GateVerdict.FAIL,
            ),
        )
        for root, bundle, approvals, verdict in cases:
            with self.subTest(operator=root["operator"], verdict=verdict):
                self.assertEqual(self.decision(root, bundle, approvals).verdict, verdict)

    def test_all_of_truth_table_prioritizes_valid_violation(self):
        root = self.atom(
            "all_of",
            children=(
                self.atom("check_passed", "first", key="a"),
                self.atom("check_passed", "second", key="b"),
            ),
        )
        for left, right in itertools.product(FactState, repeat=2):
            if FactState.VIOLATED in (left, right):
                verdict = GateVerdict.FAIL
            elif FactState.UNRESOLVED in (left, right):
                verdict = GateVerdict.INDETERMINATE
            else:
                verdict = GateVerdict.PASS
            bundle = build_fact_bundle(checks=(Fact("a", left), Fact("b", right))).value
            decision = self.decision(root, bundle)
            self.assertEqual(decision.verdict, verdict)
            if {left, right} == {FactState.VIOLATED, FactState.UNRESOLVED}:
                self.assertEqual({reason.code for reason in decision.reasons}, {"CHECK_FAILED", "MISSING_EVIDENCE"})

    def test_any_of_truth_table_requires_all_branches_to_be_violated_for_fail(self):
        root = self.atom(
            "any_of",
            children=(
                self.atom("check_passed", "first", key="a"),
                self.atom("check_passed", "second", key="b"),
            ),
        )
        for left, right in itertools.product(FactState, repeat=2):
            if FactState.SATISFIED in (left, right):
                expected = GateVerdict.PASS
            elif left is FactState.VIOLATED and right is FactState.VIOLATED:
                expected = GateVerdict.FAIL
            else:
                expected = GateVerdict.INDETERMINATE
            bundle = build_fact_bundle(checks=(Fact("a", left), Fact("b", right))).value
            self.assertEqual(self.decision(root, bundle).verdict, expected)

    def test_decision_binds_inputs_candidate_and_orders_reasons_deterministically(self):
        candidate = ref("candidate", kind=ArtifactKind.CANDIDATE)
        root = self.atom(
            "all_of",
            children=(
                self.atom("check_passed", "z-obligation", key="z"),
                self.atom("check_passed", "a-obligation", key="a"),
            ),
        )
        policy = build_policy(self.document(root, "G4")).value
        checks = (Fact("z", FactState.VIOLATED), Fact("a", FactState.UNRESOLVED))
        first = build_fact_bundle(checks=checks).value
        second = build_fact_bundle(checks=tuple(reversed(checks))).value
        current = state(Phase.VERIFYING, candidate=candidate)
        decision_a = evaluate_gate(current, Gate.G4, policy, first, ApprovalRegistry(), self.context())
        decision_b = evaluate_gate(current, Gate.G4, policy, second, ApprovalRegistry(), self.context())
        self.assertEqual(decision_a, decision_b)
        self.assertEqual(decision_a.candidate, candidate)
        self.assertEqual(decision_a.policy_digest, policy.digest)
        self.assertEqual(decision_a.input_bundle_digest, "sha256:bundle")
        self.assertEqual(tuple(reason.obligation for reason in decision_a.reasons), ("a-obligation", "z-obligation"))

    def test_policy_gate_mismatch_is_indeterminate(self):
        policy = build_policy(self.document(self.atom("check_passed", key="unit"), "G1")).value
        decision = evaluate_gate(
            state(Phase.DESIGNING), Gate.G2, policy, build_fact_bundle().value,
            ApprovalRegistry(), self.context(),
        )
        self.assertEqual(decision.verdict, GateVerdict.INDETERMINATE)
        self.assertEqual(decision.reasons[0].code, "POLICY_GATE_MISMATCH")
