"""What profiling measured a project as: its commands run, its catalogue roles covered.

``RoleCoverage`` says which tool measures one role for one technology and what the tool was
recognised from; ``CatalogueGap`` states a role measured otherwise than the catalogue
recommends; ``DeclinedRole`` one whose conformance proposal the requester refused.
"""

from __future__ import annotations

from pydantic import Field

from harness495.core.models.base import StrictModel
from harness495.core.models.enums import CatalogueRole, GapKind


class ReadinessCheck(StrictModel):
    command_name: str
    command: str
    executable: bool
    exit_code: int | None = None
    detail: str = ""
    duration_s: float = 0.0


class RoleCoverage(StrictModel):
    """Which tool a project measures one catalogue role with, for one of its technologies.

    ``tools`` is empty when nothing in the project measures the role; ``markers`` names what
    the tool was recognised from (a dependency, a configuration section, a file, an import
    in a test), one entry per tool, so the requester can check the claim.
    """

    technology: str
    role: CatalogueRole
    tools: list[str] = Field(default_factory=list)
    markers: list[str] = Field(default_factory=list)

    @property
    def measured(self) -> bool:
        return bool(self.tools)


class CatalogueGap(StrictModel):
    """One role a project measures otherwise than the catalogue recommends, for one technology.

    Stated only for a role whose measure can contradict the agent's implementation (the
    catalogue's Roles table says which) and only where the catalogue has an entry for the
    technology; a technology whose section is empty has no gaps. ``recommended`` is the entry
    that applies to the project, ``condition`` the words under which it applies when the cell
    holds several entries (empty for the default one), ``missing`` the recommended tools not
    in place.
    """

    technology: str
    role: CatalogueRole
    kind: GapKind
    in_place: list[str] = Field(default_factory=list)
    recommended: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    condition: str = ""

    @property
    def statement(self) -> str:
        """The gap in words, without the technology and role."""
        recommended = ", ".join(self.recommended)
        if self.condition:
            recommended += f" ({self.condition})"
        if self.kind is GapKind.unmeasured:
            return f"nothing measures it; the catalogue recommends {recommended}"
        measured = f"measured with {', '.join(self.in_place)}"
        if self.kind is GapKind.other_tool:
            return f"{measured}; the catalogue recommends {recommended}"
        return (
            f"{measured}; the catalogue recommends {recommended}: {', '.join(self.missing)} missing"
        )


class DeclinedRole(StrictModel):
    """A catalogue role whose conformance proposal the requester declined, with the reason.

    Read from the project's proposals when a run is profiled and kept on the run's profile, so
    that the run records the answer it knew of: the specifier is told not to call for the
    role, and a verification that names it anyway cites the refusal, not a proposal to answer.
    """

    technology: str
    role: CatalogueRole
    reason: str = ""
