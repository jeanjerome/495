"""What a run showed about the tools that measured its catalogue roles.

Read from the run document and nothing else, so that it can be written again at any time and
reads the same; ``catalogue_row`` is the row the catalogue takes when the run proved or
rejected a tool.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import Field

from harness495.core.models.base import SCHEMA_VERSION, StrictModel, utcnow
from harness495.core.models.enums import CatalogueRole, RunStatus


class ToolVerdict(StrEnum):
    """What a run showed about a tool that measured a catalogue role (``ToolObservation``)."""

    proven = "proven"
    """Every run of it reported something the change decided: a report that differed with and
    without the change, a failure that contradicted the agent, or a pass on a base the tool had
    passed before."""
    faulty = "faulty"
    """At least one run of it failed for a reason no edit of the change could fix: it was not
    executable, timed out, failed identically on both versions, or the requester replaced its
    command."""
    inconclusive = "inconclusive"
    """It ran, and nothing shows whether it observed the change: it reported the same success
    on both versions, or a failure with no base measurement to read it against."""


class ToolObservation(StrictModel):
    """What one run showed about the tools that measure one catalogue role, for one technology.

    Derived from the run document alone: the verifications that name the role, the evidence
    each produced on the change and on the base version, the readiness checks. ``runs`` counts
    the measurements read, ``verdicts`` those whose report the change decided, ``contradictions``
    those in which the tool reported a failure on the change, ``faults`` those that failed for a
    reason outside the change; ``detail`` states each measurement in words, with its
    verification and iteration, so that the reader can check the verdict against the evidence.
    ``catalogue_row`` is the Markdown row the catalogue takes, with the run as source: a
    ``recommended`` entry for a proven tool, a ``Rejected`` row for a faulty one, empty when the
    run showed nothing; ``in_catalogue`` says whether the catalogue already recommends the tool
    for the cell, in which case the row is a further source for an entry that exists.
    """

    technology: str
    role: CatalogueRole
    tools: list[str] = Field(default_factory=list)
    verdict: ToolVerdict
    verification_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    runs: int = 0
    verdicts: int = 0
    contradictions: int = 0
    faults: int = 0
    detail: list[str] = Field(default_factory=list)
    in_catalogue: bool = False
    catalogue_row: str = ""


class Retrospective(StrictModel):
    """What a run showed about the tools of the project: ``runs/<run_id>/retrospective.json``.

    Written by ``495 retro`` from the run document and nothing else, so that it can be written
    again at any time and reads the same. ``source`` is the words the catalogue's Source column
    takes for a row that comes from this run.
    """

    schema_version: int = SCHEMA_VERSION
    run_id: str
    project: str
    run_status: RunStatus
    created_at: dt.datetime = Field(default_factory=utcnow)
    source: str
    tool_observations: list[ToolObservation] = Field(default_factory=list)

    def observation(self, technology: str, role: CatalogueRole) -> ToolObservation | None:
        for o in self.tool_observations:
            if o.technology == technology and o.role is role:
                return o
        return None
