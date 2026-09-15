"""The run document itself: what was asked, what was done, and what came of it.

``Run`` is the root the store persists and ``495 schema run`` publishes: it links by identifier
the intent, the configuration, the profile, the clarification, the specification, the
iterations, the interventions, the evidence, the reviews and the decisions. ``Version`` names a
produced state of the tree, ``RunResult`` what was delivered, and ``Event`` one line of the
run's log.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import Field

from harness495.core.models.base import SCHEMA_VERSION, StrictModel, utcnow
from harness495.core.models.clarification import Clarification
from harness495.core.models.config import Budget, HarnessConfig
from harness495.core.models.decisions import Decision, PendingDecision
from harness495.core.models.enums import (
    BLOCKING_STATUSES,
    TERMINAL_STATUSES,
    CostBasis,
    RunMode,
    RunStatus,
    Verdict,
)
from harness495.core.models.evidence import Evidence, ReviewVerdict
from harness495.core.models.interventions import Intervention, Usage
from harness495.core.models.lessons import ProjectProfile
from harness495.core.models.specification import Spec


class Version(StrictModel):
    base_commit: str
    head_commit: str | None = None
    branch: str | None = None
    worktree: str | None = None
    patch_ref: str | None = None
    patch_sha256: str | None = None
    files_changed: list[str] = Field(default_factory=list)


class ReportedCommand(StrictModel):
    command: str
    exit_code: int


class DesignedTest(StrictModel):
    """Which file the test designer says holds the test of one verification. A claim."""

    verification_id: str
    file: str


class TestDesign(StrictModel):
    """The tests to create, written before the producer by an intervention of their own.

    ``files`` are the test files the harness found written after the intervention, committed
    as ``commit`` on top of ``base_commit``; they are protected: a version of the change that
    modifies or deletes one is rejected on scope. ``discarded`` are the files the designer
    wrote that are not test files by the naming convention (``looks_like_a_test``), reverted
    before the commit. ``reported`` and ``not_done`` are what the designer said: which file
    holds which verification's test, and what it could not write; claims, never facts.
    """

    intervention_id: str
    base_commit: str
    commit: str
    files: list[str] = Field(default_factory=list)
    discarded: list[str] = Field(default_factory=list)
    reported: list[DesignedTest] = Field(default_factory=list)
    not_done: list[str] = Field(default_factory=list)


class Iteration(StrictModel):
    n: int
    version: Version | None = None
    production_intervention_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    review_ids: list[str] = Field(default_factory=list)
    decision_id: str | None = None
    correction_requests: list[str] = Field(default_factory=list)
    blocked_claims: list[str] = Field(default_factory=list)
    """What the producer reported it could not do. A claim to surface, never a fact."""
    commands_reported: list[ReportedCommand] = Field(default_factory=list)
    """Commands the producer says it ran. Claims too, but ones the harness can re-run itself."""
    instrument_faults: list[str] = Field(default_factory=list)
    """Verifications whose outcome did not change with the change; the spec is at fault, not the change."""
    outcome: Verdict | None = None
    started_at: dt.datetime = Field(default_factory=utcnow)
    ended_at: dt.datetime | None = None


class Consumption(StrictModel):
    usage: Usage = Field(default_factory=Usage)
    cost_usd: float = 0.0
    cost_basis: CostBasis = CostBasis.unknown
    cost_unknown_interventions: int = 0
    interventions: int = 0
    by_agent: dict[str, Usage] = Field(default_factory=dict)
    cost_by_agent: dict[str, float] = Field(default_factory=dict)


class IntegrationCheck(StrictModel):
    target_ref: str
    target_commit: str
    contains_commit: bool
    files_identical: bool
    verifications_rerun: bool = False
    verifications_passed: bool | None = None
    detail: str = ""
    checked_at: dt.datetime = Field(default_factory=utcnow)


class RunResult(StrictModel):
    integrated_as: str | None = None
    """How 495 brought the change into the working tree, when 495 is what brought it in —
    ``fast-forward``, ``rebase``, ``squash`` or ``merge``. ``None`` means it was integrated by
    hand, by something else, or not yet. ``rebase`` and ``squash`` copy the change rather than
    move it, so the delivered commit is then not in the branch and only the file contents say
    the right thing landed; without this the check could not tell that from a stranger's merge."""
    outcome: Verdict | None = None
    summary: str = ""
    patch_ref: str | None = None
    branch: str | None = None
    head_commit: str | None = None
    report_ref: str | None = None
    integration: IntegrationCheck | None = None


class Intent(StrictModel):
    text: str
    source: str = "cli"
    created_at: dt.datetime = Field(default_factory=utcnow)


class Run(StrictModel):
    schema_version: int = SCHEMA_VERSION
    harness_version: str = "0.1.0"
    id: str
    mode: RunMode = RunMode.change
    status: RunStatus = RunStatus.created
    created_at: dt.datetime = Field(default_factory=utcnow)
    updated_at: dt.datetime = Field(default_factory=utcnow)
    intent: Intent
    project_root: str
    config: HarnessConfig = Field(default_factory=HarnessConfig)
    profile: ProjectProfile | None = None
    clarification: Clarification = Field(default_factory=Clarification)
    """The decisions the requester took before the specification, and the questions left open."""
    spec: Spec = Field(default_factory=Spec)
    test_design: TestDesign | None = None
    """The tests to create as written by the test designer for the approved specification;
    None until it has run, and again whenever the specification is replaced."""
    budget: Budget = Field(default_factory=Budget)
    consumption: Consumption = Field(default_factory=Consumption)
    iterations: list[Iteration] = Field(default_factory=list)
    interventions: list[Intervention] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    reviews: list[ReviewVerdict] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    pending_decision: PendingDecision | None = None
    resume_status: RunStatus | None = None
    """Status to return to after a pause or a decision."""
    evaluate_ref: str | None = None
    worktree: str | None = None
    """Absolute path of the run's git worktree (outside the project directory)."""
    result: RunResult = Field(default_factory=RunResult)
    warnings: list[str] = Field(default_factory=list)
    stop_reason: str | None = None

    # ---- helpers

    @property
    def current_iteration(self) -> Iteration | None:
        return self.iterations[-1] if self.iterations else None

    @property
    def iteration_number(self) -> int:
        return self.iterations[-1].n if self.iterations else 0

    def intervention(self, iid: str) -> Intervention | None:
        for i in self.interventions:
            if i.id == iid:
                return i
        return None

    def evidence_by_id(self, eid: str) -> Evidence | None:
        for e in self.evidence:
            if e.id == eid:
                return e
        return None

    def integration_state(self) -> str:
        """What the last look at a ref found there.

        Four answers, where :class:`IntegrationCheck` records two booleans. Those two cannot
        tell "you have not merged yet" from "what you merged is not what was verified": both
        are the same pair of ``False`` values and they are opposite facts — one is the stop
        standing exactly where it always stands, the other is the single thing this stop
        exists to catch. The commit the run branched from separates them, which is why this is
        read off the run rather than stored: a ref still sitting on that commit was never
        merged into.

        ``unchecked`` nothing has been asked · ``unmerged`` the ref is still where the run
        started · ``landed`` it carries the verified change · ``differs`` it carries something
        else.
        """
        g = self.result.integration
        if g is None:
            return "unchecked"
        if g.contains_commit or g.files_identical:
            return "landed"
        it = self.current_iteration
        base = it.version.base_commit if it is not None and it.version is not None else None
        return "unmerged" if base and g.target_commit == base else "differs"

    def is_blocked(self) -> bool:
        return self.status in BLOCKING_STATUSES

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class Event(StrictModel):
    ts: dt.datetime = Field(default_factory=utcnow)
    run_id: str
    type: str
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
