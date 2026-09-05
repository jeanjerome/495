"""Gates rendues obsolètes par un changement."""

from .vocabulary import ChangeKind, Gate


_RULES = {
    ChangeKind.MANDATORY_REQUIREMENT_OR_SCENARIO: frozenset(Gate),
    ChangeKind.DECISION_OR_INTERFACE_CONTRACT: frozenset(
        (Gate.G2, Gate.G3, Gate.G4, Gate.G5)
    ),
    ChangeKind.POLICY_VERIFIER_ENVIRONMENT_OR_BASELINE: frozenset(
        (Gate.G2, Gate.G3, Gate.G4, Gate.G5)
    ),
    ChangeKind.CANDIDATE: frozenset((Gate.G3, Gate.G4)),
    ChangeKind.DESTINATION_BRANCH_ADVANCED: frozenset((Gate.G5,)),
    ChangeKind.UNCONSUMED_RELATED_TO_NOTE: frozenset(),
}


def invalidated_by(change: ChangeKind) -> frozenset[Gate]:
    return _RULES[change]
