"""Conformance proposals: the gaps against the catalogue, put to the requester and kept.

A gap the profile states (``core/catalogue.py::compare``) is a fact; a proposal is that fact
put to the requester, with an answer that outlives the profiling that stated it. The
proposals of a project live in ``<state_dir>/proposals.json`` (``RunStore.load_proposals``).
``reconcile`` brings the file in step with a profile: a new gap opens a proposal, a gap that
is no longer stated resolves its proposal, a declined proposal is left declined so that the
gap is not proposed again. ``accept``, ``decline`` and ``defer`` record the requester's
answer; the run an acceptance creates carries ``intent_for`` the gap: the recommended tool
put in place and a first test of the role (``docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md``).
"""

from __future__ import annotations

from harness495.core.models import (
    CatalogueGap,
    CatalogueRole,
    DeclinedRole,
    GapKind,
    ProjectProfile,
    Proposal,
    Proposals,
    ProposalStatus,
    new_id,
    utcnow,
)


class ProposalError(ValueError):
    """An answer the proposal's status does not admit."""


FIRST_TEST: dict[CatalogueRole, str] = {
    CatalogueRole.runner: "write a first test of one existing function, run by it",
    CatalogueRole.bdd: (
        "write a first scenario in a .feature file bound to steps, stating one behaviour the "
        "project already has"
    ),
    CatalogueRole.property: (
        "write a first property-based test over one existing function, its inputs generated "
        "rather than chosen"
    ),
    CatalogueRole.fuzzing: (
        "write a first fuzz target over one existing parser or input boundary, with a bounded "
        "run wired as a command"
    ),
    CatalogueRole.mutation: (
        "wire a first mutation run over one existing module as a command that reports the "
        "surviving mutants"
    ),
    CatalogueRole.coverage: (
        "wire a first measurement of the existing suite as a command that reports the coverage "
        "of the lines a change touches"
    ),
    CatalogueRole.architecture: (
        "write a first contract stating one dependency rule the project already follows, wired "
        "as a command"
    ),
    CatalogueRole.static: (
        "wire a first run over the project as a command, with the rules the project already "
        "follows selected"
    ),
    CatalogueRole.types: "wire a first run over the project's packages as a command",
    CatalogueRole.security: (
        "wire a first audit of the project's code and dependencies as a command"
    ),
    CatalogueRole.contract: (
        "write a first contract test over one existing endpoint, generated from its schema and "
        "wired as a command"
    ),
    CatalogueRole.performance: "wire a first bound on one existing operation as a command",
    CatalogueRole.doubles: "write a first test that replaces one collaborator with a double",
}
"""The first test of each role, as the intent of an accepted proposal asks for it."""


def intent_for(gap: CatalogueGap) -> str:
    """The intent of the change run that puts the recommended tool in place.

    It states the gap as the profile did, names the tool to add and the catalogue that
    recommends it, and asks for a first test of the role, so that the specifier derives a
    specification whose verification is that test run by the tool.
    """
    tools = ", ".join(gap.recommended)
    role = gap.role.value
    where = f" for {gap.technology}"
    condition = f" ({gap.condition})" if gap.condition else ""
    first_test = FIRST_TEST[gap.role]
    if gap.kind is GapKind.unmeasured:
        head = (
            f"Nothing in the project measures the {role} role{where}. Put {tools} in place, "
            f"as docs/test-libraries.md recommends{condition}"
        )
    elif gap.kind is GapKind.other_tool:
        in_place = ", ".join(gap.in_place)
        head = (
            f"The project measures the {role} role{where} with {in_place}; docs/test-libraries.md "
            f"recommends {tools}{condition}. Put {tools} in place, and keep {in_place} unless "
            f"the change makes it redundant"
        )
    else:
        in_place = ", ".join(gap.in_place)
        missing = ", ".join(gap.missing)
        head = (
            f"The project measures the {role} role{where} with {in_place}; docs/test-libraries.md "
            f"recommends {tools}{condition}, and {missing} is missing. Add {missing} next to "
            f"{in_place}"
        )
    them = "them" if len(gap.missing) > 1 else "it"
    return (
        f"{head}: add {them} to the project's development dependencies and configuration, "
        f"declare the command that runs {them} so that the harness can measure the role, and "
        f"{first_test}."
    )


def reconcile(proposals: Proposals, profile: ProjectProfile) -> list[Proposal]:
    """Bring the proposals in step with the gaps a profile states; returns the ones opened.

    A gap without a proposal opens one. A proposal whose gap is still stated keeps its
    status and takes the gap as now stated, its intent with it. A proposal whose gap is no
    longer stated is resolved, unless it was declined: the decline is the requester's
    record and stays. A resolved proposal whose gap comes back opens again.
    """
    stated = {(g.technology, g.role): g for g in profile.catalogue_gaps}
    now = utcnow()
    for p in proposals.proposals:
        gap = stated.pop((p.technology, p.role), None)
        if gap is None:
            if p.status is not ProposalStatus.declined and p.status is not ProposalStatus.resolved:
                p.status = ProposalStatus.resolved
                p.updated_at = now
            continue
        if p.status is ProposalStatus.resolved:
            p.status = ProposalStatus.open
            p.reason = ""
            p.run_id = None
            p.decided_at = None
            p.updated_at = now
        if p.gap != gap:
            p.gap = gap
            p.intent = intent_for(gap)
            p.updated_at = now
    opened = [
        Proposal(id=new_id("prop"), gap=gap, intent=intent_for(gap), created_at=now, updated_at=now)
        for gap in stated.values()
    ]
    proposals.proposals.extend(opened)
    return opened


def _answerable(proposal: Proposal, answer: str) -> None:
    if proposal.status is ProposalStatus.resolved:
        raise ProposalError(
            f"{proposal.id} is resolved: the project measures {proposal.technology} "
            f"{proposal.role.value} as the catalogue recommends; nothing to {answer}"
        )


def accept(proposal: Proposal, run_id: str) -> None:
    """Record that the requester accepted the proposal and which run carries it."""
    _answerable(proposal, "accept")
    if proposal.status is ProposalStatus.accepted:
        raise ProposalError(
            f"{proposal.id} is already accepted and carried by run {proposal.run_id}; "
            "defer or decline it before accepting it again"
        )
    now = utcnow()
    proposal.status = ProposalStatus.accepted
    proposal.run_id = run_id
    proposal.reason = ""
    proposal.decided_at = now
    proposal.updated_at = now


def decline(proposal: Proposal, reason: str) -> None:
    """Record that the requester declined the proposal, and why; it is not proposed again."""
    _answerable(proposal, "decline")
    if not reason.strip():
        raise ProposalError(f"declining {proposal.id} needs a reason; it is kept with it")
    now = utcnow()
    proposal.status = ProposalStatus.declined
    proposal.reason = reason.strip()
    proposal.decided_at = now
    proposal.updated_at = now


def defer(proposal: Proposal, note: str = "") -> None:
    """Record that the requester set the proposal aside; it stays listed."""
    _answerable(proposal, "defer")
    now = utcnow()
    proposal.status = ProposalStatus.deferred
    proposal.reason = note.strip()
    proposal.decided_at = now
    proposal.updated_at = now


def declined_roles(proposals: Proposals) -> list[DeclinedRole]:
    """The roles the requester declined, with their reasons, for a run's profile to carry.

    The only thing a run reads from the proposals: an answer already given, stated as a fact
    about the project. The run never writes the document, and a run created from a proposal
    stays an ordinary run.
    """
    return [
        DeclinedRole(technology=p.technology, role=p.role, reason=p.reason)
        for p in proposals.proposals
        if p.status is ProposalStatus.declined
    ]
