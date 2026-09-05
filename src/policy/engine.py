"""Évaluation pure d'une politique bornée en décision de gate."""

from dataclasses import dataclass

from domain.references import ApprovalRegistry, ArtifactRef, approvals_for
from domain.state import DecisionReason, GateDecision, IncrementState
from domain.vocabulary import ApprovalDecision, Gate, GateVerdict
from validation.facts import Fact, FactBundle, FactState

from .model import Policy, PolicyNode, PolicyOperator


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    decision_id: str
    engine_version: str
    expected_state_version: int
    input_bundle_digest: str


@dataclass(frozen=True, slots=True)
class _NodeResult:
    state: FactState
    reasons: tuple[DecisionReason, ...] = ()


def _reason(
    code: str, node: PolicyNode, evidence: tuple[ArtifactRef, ...] = ()
) -> DecisionReason:
    return DecisionReason(code, node.obligation, evidence)


def _lookup_check(bundle: FactBundle, key: str) -> Fact | None:
    return next((fact for fact in bundle.checks if fact.fact_id == key), None)


def _evaluate_atom(
    node: PolicyNode, bundle: FactBundle, approvals: ApprovalRegistry
) -> _NodeResult:
    if node.operator is PolicyOperator.CHECK_PASSED:
        fact = _lookup_check(bundle, node.key or "")
        if fact is None or fact.state is FactState.UNRESOLVED:
            evidence = () if fact is None else fact.evidence
            return _NodeResult(
                FactState.UNRESOLVED, (_reason("MISSING_EVIDENCE", node, evidence),)
            )
        if fact.state is FactState.VIOLATED:
            code = "DIGEST_MISMATCH" if fact.detail == "digest_mismatch" else "CHECK_FAILED"
            return _NodeResult(FactState.VIOLATED, (_reason(code, node, fact.evidence),))
        return _NodeResult(FactState.SATISFIED)

    if node.operator is PolicyOperator.APPROVAL_PRESENT:
        matches = approvals_for(approvals, node.target)
        if any(item.decision is ApprovalDecision.APPROVED for item in matches):
            return _NodeResult(FactState.SATISFIED)
        if matches:
            return _NodeResult(
                FactState.VIOLATED,
                (_reason("APPROVAL_REFUSED", node, (node.target,)),),
            )
        return _NodeResult(
            FactState.UNRESOLVED,
            (_reason("APPROVAL_REQUIRED", node, (node.target,)),),
        )

    if node.operator is PolicyOperator.ARTIFACT_PRESENT:
        if node.target in bundle.artifacts:
            return _NodeResult(FactState.SATISFIED)
        return _NodeResult(
            FactState.UNRESOLVED,
            (_reason("ARTIFACT_MISSING", node, (node.target,)),),
        )

    if node.operator is PolicyOperator.DIGEST_MATCHES:
        observed = dict(bundle.digests).get(node.key or "")
        if observed is None:
            return _NodeResult(
                FactState.UNRESOLVED, (_reason("MISSING_EVIDENCE", node),)
            )
        if observed != node.expected_digest:
            return _NodeResult(
                FactState.VIOLATED, (_reason("DIGEST_MISMATCH", node),)
            )
        return _NodeResult(FactState.SATISFIED)

    if node.operator is PolicyOperator.CAPABILITY_SATISFIED:
        if node.key in bundle.capabilities:
            return _NodeResult(FactState.SATISFIED)
        return _NodeResult(
            FactState.UNRESOLVED, (_reason("CAPABILITY_MISSING", node),)
        )

    if node.operator is PolicyOperator.WITHIN_BUDGET:
        budget = next(
            (item for item in bundle.budgets if item.budget_id == node.key), None
        )
        if budget is None:
            return _NodeResult(
                FactState.UNRESOLVED, (_reason("BUDGET_MISSING", node),)
            )
        if budget.consumed > budget.limit:
            return _NodeResult(
                FactState.VIOLATED, (_reason("BUDGET_EXCEEDED", node),)
            )
        return _NodeResult(FactState.SATISFIED)

    raise AssertionError(f"opérateur atomique non traité : {node.operator}")


def _evaluate_node(
    node: PolicyNode, bundle: FactBundle, approvals: ApprovalRegistry
) -> _NodeResult:
    if node.operator not in (PolicyOperator.ALL_OF, PolicyOperator.ANY_OF):
        return _evaluate_atom(node, bundle, approvals)
    results = tuple(_evaluate_node(child, bundle, approvals) for child in node.children)
    if node.operator is PolicyOperator.ALL_OF:
        if any(result.state is FactState.VIOLATED for result in results):
            state = FactState.VIOLATED
        elif any(result.state is FactState.UNRESOLVED for result in results):
            state = FactState.UNRESOLVED
        else:
            state = FactState.SATISFIED
        return _NodeResult(state, tuple(reason for result in results for reason in result.reasons))

    if any(result.state is FactState.SATISFIED for result in results):
        return _NodeResult(FactState.SATISFIED)
    if all(result.state is FactState.VIOLATED for result in results):
        return _NodeResult(
            FactState.VIOLATED,
            tuple(reason for result in results for reason in result.reasons),
        )
    return _NodeResult(
        FactState.UNRESOLVED,
        tuple(reason for result in results for reason in result.reasons),
    )


def _reason_key(reason: DecisionReason) -> tuple[object, ...]:
    return (
        reason.obligation,
        reason.code,
        tuple(
            (
                item.artifact_id,
                item.revision,
                item.kind.value,
                item.schema_version,
                item.digest,
            )
            for item in reason.evidence
        ),
    )


def evaluate_gate(
    state: IncrementState,
    gate: Gate,
    policy: Policy,
    facts: FactBundle,
    approvals: ApprovalRegistry,
    context: EvaluationContext,
) -> GateDecision:
    if policy.gate is not gate:
        result = _NodeResult(
            FactState.UNRESOLVED,
            (DecisionReason("POLICY_GATE_MISMATCH", "policy_gate", ()),),
        )
    else:
        result = _evaluate_node(policy.root, facts, approvals)
    verdict = {
        FactState.SATISFIED: GateVerdict.PASS,
        FactState.VIOLATED: GateVerdict.FAIL,
        FactState.UNRESOLVED: GateVerdict.INDETERMINATE,
    }[result.state]
    candidate = state.current_candidate if gate in (Gate.G3, Gate.G4, Gate.G5) else None
    return GateDecision(
        decision_id=context.decision_id,
        gate=gate,
        verdict=verdict,
        engine_version=context.engine_version,
        policy_digest=policy.digest,
        input_bundle_digest=context.input_bundle_digest,
        expected_state_version=context.expected_state_version,
        candidate=candidate,
        reasons=tuple(sorted(result.reasons, key=_reason_key)),
        reconciliation=None,
    )
