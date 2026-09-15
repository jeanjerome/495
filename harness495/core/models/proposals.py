"""A gap against the test-library catalogue as it is put to the requester, and their answer.

A proposal is identified by the technology and the role of its gap, so that the profile states
the gap once and the answer stays with it across profilings.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import Field

from harness495.core.models.base import SCHEMA_VERSION, StrictModel, utcnow
from harness495.core.models.enums import CatalogueRole
from harness495.core.models.profile import CatalogueGap


class ProposalStatus(StrEnum):
    """Where a conformance proposal stands (``Proposal``)."""

    open = "open"
    """Stated to the requester, not answered yet."""
    accepted = "accepted"
    """Turned into a change run whose intent puts the recommended tool in place."""
    declined = "declined"
    """Refused, with the requester's reason; the gap is not proposed again."""
    deferred = "deferred"
    """Set aside for later; stays listed, and can be accepted or declined at any time."""
    resolved = "resolved"
    """The profile no longer states the gap: the project measures the role as recommended."""


class Proposal(StrictModel):
    """One conformance proposal: a gap against the catalogue, put to the requester.

    A proposal is identified by the technology and the role of its gap; the profile states
    a gap once, and the requester's answer stays with it across profilings. ``gap`` is the
    gap as last stated; ``intent`` the text of the change run an acceptance creates;
    ``reason`` the requester's words on a decline or a deferral; ``run_id`` the run an
    acceptance created.
    """

    id: str
    gap: CatalogueGap
    status: ProposalStatus = ProposalStatus.open
    intent: str
    reason: str = ""
    run_id: str | None = None
    created_at: dt.datetime = Field(default_factory=utcnow)
    updated_at: dt.datetime = Field(default_factory=utcnow)
    decided_at: dt.datetime | None = None
    """When the requester last answered; None while the proposal has only been stated."""

    @property
    def technology(self) -> str:
        return self.gap.technology

    @property
    def role(self) -> CatalogueRole:
        return self.gap.role

    @property
    def answerable(self) -> bool:
        """Whether the proposal still awaits an answer from the requester."""
        return self.status in (ProposalStatus.open, ProposalStatus.deferred)


class Proposals(StrictModel):
    """The conformance proposals of one project: ``<state_dir>/proposals.json``."""

    schema_version: int = SCHEMA_VERSION
    proposals: list[Proposal] = Field(default_factory=list)

    def find(self, technology: str, role: CatalogueRole) -> Proposal | None:
        for p in self.proposals:
            if p.gap.technology == technology and p.gap.role is role:
                return p
        return None

    def get(self, proposal_id: str) -> Proposal | None:
        for p in self.proposals:
            if p.id == proposal_id:
                return p
        return None
