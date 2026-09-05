"""Table fermée des transitions de phase."""

from dataclasses import dataclass

from .vocabulary import CommandName, EdgeKind, FinishReason, Gate, Phase


@dataclass(frozen=True, slots=True)
class TransitionEdge:
    origin: Phase
    target: Phase
    command: CommandName
    gate: Gate | None
    kind: EdgeKind
    terminates_current_attempt: FinishReason | None = None
    extra_precondition: str | None = None


def _edge(
    origin: Phase,
    target: Phase,
    command: CommandName,
    kind: EdgeKind,
    gate: Gate | None = None,
    *,
    terminates: FinishReason | None = None,
    precondition: str | None = None,
) -> TransitionEdge:
    return TransitionEdge(origin, target, command, gate, kind, terminates, precondition)


TRANSITIONS = (
    _edge(Phase.CLARIFYING, Phase.SPECIFYING, CommandName.APPLY_GATE_DECISION, EdgeKind.FORWARD, Gate.G0),
    _edge(Phase.SPECIFYING, Phase.DESIGNING, CommandName.APPLY_GATE_DECISION, EdgeKind.FORWARD, Gate.G1),
    _edge(Phase.DESIGNING, Phase.IMPLEMENTING, CommandName.APPLY_GATE_DECISION, EdgeKind.FORWARD, Gate.G2),
    _edge(Phase.IMPLEMENTING, Phase.VERIFYING, CommandName.APPLY_GATE_DECISION, EdgeKind.FORWARD, Gate.G3),
    _edge(Phase.VERIFYING, Phase.ACCEPTED, CommandName.APPLY_GATE_DECISION, EdgeKind.FORWARD, Gate.G4),
    _edge(Phase.ACCEPTED, Phase.INTEGRATING, CommandName.START_INTEGRATION, EdgeKind.FORWARD),
    _edge(Phase.INTEGRATING, Phase.INTEGRATED, CommandName.APPLY_GATE_DECISION, EdgeKind.FORWARD, Gate.G5),
    _edge(Phase.VERIFYING, Phase.IMPLEMENTING, CommandName.START_ATTEMPT, EdgeKind.CORRECTION),
    _edge(Phase.SPECIFYING, Phase.CLARIFYING, CommandName.REVISE_INCREMENT, EdgeKind.RETURN, terminates=FinishReason.REVISION_REQUESTED),
    _edge(Phase.DESIGNING, Phase.SPECIFYING, CommandName.REVISE_INCREMENT, EdgeKind.RETURN, terminates=FinishReason.REVISION_REQUESTED),
    *(
        _edge(origin, Phase.CLOSED, CommandName.CLOSE_INCREMENT, EdgeKind.CLOSURE)
        for origin in (
            Phase.CLARIFYING,
            Phase.SPECIFYING,
            Phase.DESIGNING,
            Phase.IMPLEMENTING,
            Phase.VERIFYING,
            Phase.ACCEPTED,
            Phase.INTEGRATING,
        )
    ),
    *(
        _edge(
            origin,
            target,
            CommandName.REVISE_INCREMENT,
            EdgeKind.REVISION,
            terminates=FinishReason.REVISION_REQUESTED,
            precondition=(
                "no_unreconciled_external_effect" if origin is Phase.INTEGRATING else None
            ),
        )
        for origin in (Phase.IMPLEMENTING, Phase.VERIFYING, Phase.ACCEPTED, Phase.INTEGRATING)
        for target in (Phase.SPECIFYING, Phase.DESIGNING)
    ),
)


def edge_between(origin: Phase, target: Phase) -> TransitionEdge | None:
    for edge in TRANSITIONS:
        if (edge.origin, edge.target) == (origin, target):
            return edge
    return None
