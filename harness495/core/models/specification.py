"""What the change must make true, and what would show it.

A ``Requirement`` states the claim, a ``Verification`` the command or review that measures it
and how much that measurement is worth, and a ``BehaviourScenario`` the text a test to create
is written from and the requester approves.
"""

from __future__ import annotations

from pydantic import Field

from harness495.core.models.base import StrictModel
from harness495.core.models.clarification import DecisionTaken
from harness495.core.models.enums import (
    CatalogueRole,
    DecisionMaker,
    RequirementKind,
    RequirementStatus,
    Sufficiency,
    VerificationKind,
)


class BehaviourScenario(StrictModel):
    """A test stated as a scenario: what is given, what is done, what is then observed.

    Each list holds one step per entry, in the words of the domain; the first step of a list
    takes its keyword (Given, When, Then) and the following ones read as ``And``. ``given`` may
    be empty; ``when`` and ``then`` are not, or the scenario says nothing a reader can check.
    The producer writes the test from this text and the requester approves it, so the scenario
    says what the behaviour is through the interface a caller uses, never how it is implemented.
    """

    given: list[str] = Field(default_factory=list)
    when: list[str] = Field(default_factory=list)
    then: list[str] = Field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(self.when) and bool(self.then)

    def lines(self) -> list[str]:
        """The scenario as Gherkin steps, one per line, ready to paste into a feature file."""
        out: list[str] = []
        for keyword, steps in (("Given", self.given), ("When", self.when), ("Then", self.then)):
            for i, step in enumerate(steps):
                out.append(f"{keyword if i == 0 else 'And'} {step}")
        return out


class Verification(StrictModel):
    id: str
    kind: VerificationKind
    description: str
    command: str | None = None
    expected_exit_code: int = 0
    to_create: bool = False
    """The verification (typically a test) must be created as part of the change."""
    scenario: BehaviourScenario | None = None
    """For a ``test``, the scenario the test enacts: the text the requester approves and the
    producer writes the test from. A test to create without one is insufficient, since the only
    thing the requester could then approve is the description of a test nobody has written."""
    role: CatalogueRole | None = None
    """The catalogue role the verification measures, when it is one (a property-based test, a
    mutation run, a coverage report); None for a plain command, a review or a manual check.
    A role the project does not measure makes the verification insufficient: the tool is the
    requester's to put in place, through a conformance proposal, not the producer's."""
    sufficiency: Sufficiency = Sufficiency.sufficient
    rationale: str = ""
    discriminates: bool | None = None
    """Whether running it with and without the change gave different outcomes. None: not measured."""
    stable: bool | None = None
    """Whether two runs of the command on the evaluated version reported the same thing. None:
    not measured in this iteration. A command that reports one thing and then another decides
    nothing, in either direction."""
    timeout_s: int | None = None


class Requirement(StrictModel):
    id: str
    statement: str
    kind: RequirementKind = RequirementKind.behaviour
    rationale: str = ""
    verification_ids: list[str] = Field(default_factory=list)
    status: RequirementStatus = RequirementStatus.pending
    status_reason: str = ""


class Spec(StrictModel):
    requirements: list[Requirement] = Field(default_factory=list)
    verifications: list[Verification] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    """What the specifier could not verify and nobody was asked about. A question that was put
    to the requester is a ``decisions_taken`` entry, not an assumption."""
    decisions_taken: list[DecisionTaken] = Field(default_factory=list)
    """The requester's decisions the specification was written under, from the clarification."""
    allowed_paths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    """Human-readable list of verification gaps detected by the harness."""
    approved: bool = False
    approved_by: DecisionMaker | None = None
    source: str = "agent"
    artifact_ref: str | None = None
    """Where the proposed specification was written, so it can be read before approving it."""

    def verification(self, vid: str) -> Verification | None:
        for v in self.verifications:
            if v.id == vid:
                return v
        return None

    def requirement(self, rid: str) -> Requirement | None:
        for r in self.requirements:
            if r.id == rid:
                return r
        return None
