"""Domain model of a 495 run.

Every object that the harness persists is a pydantic model so that the on-disk state can be
validated against the JSON schema published by ``495 schema``. The model links, by identifier,
the intent, the requirements, the verifications, the interventions, the evidence, the decisions
and the delivered result.
"""

from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --------------------------------------------------------------------------- enumerations


class RunMode(StrEnum):
    change = "change"
    """Produce a change from an intent, then verify and review it."""
    evaluate = "evaluate"
    """Verify and review an existing change without mobilising a production agent."""


class RunStatus(StrEnum):
    created = "created"
    profiled = "profiled"
    clarifying = "clarifying"
    clarified = "clarified"
    specified = "specified"
    ready = "ready"
    producing = "producing"
    produced = "produced"
    verifying = "verifying"
    verified = "verified"
    reviewing = "reviewing"
    reviewed = "reviewed"
    awaiting_decision = "awaiting_decision"
    accepted = "accepted"
    rejected = "rejected"
    undetermined = "undetermined"
    delivered = "delivered"
    paused = "paused"
    aborted = "aborted"
    failed = "failed"


TERMINAL_STATUSES = frozenset(
    {RunStatus.delivered, RunStatus.aborted, RunStatus.failed, RunStatus.rejected}
)
BLOCKING_STATUSES = TERMINAL_STATUSES | {RunStatus.awaiting_decision, RunStatus.paused}


class AgentKind(StrEnum):
    claude_code = "claude_code"
    codex = "codex"
    openai_compat = "openai_compat"


class Role(StrEnum):
    clarifier = "clarifier"
    """Asks the requester the decisions the intent leaves open, before anything is specified;
    reads the repository, decides nothing itself."""
    specifier = "specifier"
    test_designer = "test_designer"
    """Writes the tests the specification says to create, before the producer, in an
    intervention of its own; the producer may not touch them."""
    producer = "producer"
    reviewer = "reviewer"


class Capability(StrEnum):
    read = "read"
    """Read the working tree and run read-only commands."""
    write = "write"
    """Edit files inside the worktree and run commands."""


class VerificationKind(StrEnum):
    command = "command"
    test = "test"
    lint = "lint"
    build = "build"
    typecheck = "typecheck"
    review = "review"
    manual = "manual"


class CatalogueRole(StrEnum):
    """The roles of the test-library catalogue (``docs/test-libraries.md``, section Roles).

    A role names one contract a test can measure; the catalogue recommends a library per role
    and per technology, and the profile reports which tool a host project measures each role
    with (``RoleCoverage``).
    """

    runner = "runner"
    bdd = "bdd"
    property = "property"
    fuzzing = "fuzzing"
    mutation = "mutation"
    coverage = "coverage"
    architecture = "architecture"
    static = "static"
    types = "types"
    security = "security"
    contract = "contract"
    performance = "performance"
    doubles = "doubles"


class GapKind(StrEnum):
    """How a role's coverage differs from the catalogue's recommendation (``CatalogueGap``)."""

    unmeasured = "unmeasured"
    """Nothing in the project measures the role."""
    other_tool = "other_tool"
    """The role is measured, with none of the tools the catalogue recommends."""
    incomplete = "incomplete"
    """Some of the recommended tools are in place, not all (coverage.py without diff-cover)."""


class Sufficiency(StrEnum):
    sufficient = "sufficient"
    insufficient = "insufficient"
    missing = "missing"
    broken = "broken"
    """The command fails with and without the change: nothing inside the change makes it pass."""
    vacuous = "vacuous"
    """The command passes with and without the change: it reports success either way."""
    faulty = "faulty"
    """Both of the above, before they were told apart; kept so that earlier runs still load."""
    unconfirmed = "unconfirmed"
    """The command reports something else without the change, but what it reports there is an
    execution error (an import that fails, a name that does not exist), not an assertion: the
    test was seen missing its target, never observing the behaviour. It still counts as proof,
    and the reviewer is told."""


NON_DISCRIMINATING = frozenset({Sufficiency.broken, Sufficiency.vacuous, Sufficiency.faulty})
"""Verifications whose outcome does not depend on the change, whatever they report."""

ADMISSIBLE = frozenset({Sufficiency.sufficient, Sufficiency.unconfirmed})
"""Verifications whose report on the change may credit or charge a requirement."""


class RequirementKind(StrEnum):
    behaviour = "behaviour"
    """Something the change must make true. Proving it needs a command that fails without it."""
    non_regression = "non_regression"
    """Something that was already true and must stay true. A command that already passes shows it."""


class RequirementStatus(StrEnum):
    pending = "pending"
    satisfied = "satisfied"
    violated = "violated"
    undetermined = "undetermined"


class Verdict(StrEnum):
    accept = "accept"
    reject = "reject"
    undetermined = "undetermined"


class Severity(StrEnum):
    blocker = "blocker"
    major = "major"
    minor = "minor"
    info = "info"


class CostBasis(StrEnum):
    reported = "reported"
    estimated = "estimated"
    unknown = "unknown"


class InterventionStatus(StrEnum):
    running = "running"
    completed = "completed"
    failed = "failed"
    timed_out = "timed_out"
    interrupted = "interrupted"
    budget_exceeded = "budget_exceeded"
    tampered = "tampered"
    """The intervention altered a tree it was only allowed to read; its output is discarded."""


class DecisionKind(StrEnum):
    clarify = "clarify"
    """One round of the clarification: every question of the frontier, answered in one stop."""
    approve_spec = "approve_spec"
    readiness = "readiness"
    acceptance = "acceptance"
    undetermined = "undetermined"
    iteration_limit = "iteration_limit"
    budget = "budget"
    scope = "scope"
    no_progress = "no_progress"
    instrument_fault = "instrument_fault"


class DecisionMaker(StrEnum):
    harness = "harness"
    human = "human"


# --------------------------------------------------------------------------- configuration


class AgentSpec(StrictModel):
    name: str = "default"
    kind: AgentKind = AgentKind.claude_code
    model: str | None = None
    effort: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    context_window: int | None = None
    max_budget_usd: float | None = None
    extra_args: list[str] = Field(default_factory=list)


class ReviewerSpec(StrictModel):
    perspective: str
    agent: str = "default"
    instructions: str | None = None


class RolesConfig(StrictModel):
    clarifier: str = "default"
    """The agent that asks the requester what the intent leaves open, before the specifier."""
    specifier: str = "default"
    test_designer: str | None = "default"
    """The agent that writes the tests to create before the producer runs; None hands them to
    the producer, which then writes the tests that judge its own change."""
    producer: str = "default"
    reviewers: list[ReviewerSpec] = Field(
        default_factory=lambda: [
            ReviewerSpec(perspective="spec_compliance"),
            ReviewerSpec(perspective="correctness"),
            ReviewerSpec(perspective="security"),
        ]
    )

    def reviewers_for(self, spec: Spec) -> list[ReviewerSpec]:
        """The reviewers a specification calls for: the configured ones, and ``test_quality``
        whenever a verification is a test to create.

        A test written as part of the change is judged by the same run that judges the change,
        and the control run only shows that it fails without the change, not that it observes
        the behaviour; the perspective that reads the test against its requirement is therefore
        not optional there. It runs with the agent of the first configured reviewer (the
        producer's when none is configured), and a configured ``test_quality`` entry is kept
        as it is.
        """
        reviewers = list(self.reviewers)
        if any(v.to_create for v in spec.verifications) and not any(
            r.perspective == "test_quality" for r in reviewers
        ):
            agent = reviewers[0].agent if reviewers else self.producer
            reviewers.append(ReviewerSpec(perspective="test_quality", agent=agent))
        return reviewers


class Budget(StrictModel):
    max_cost_usd: float | None = 10.0
    max_total_tokens: int | None = None
    max_interventions: int = 40
    max_iterations: int = 3
    max_clarify_rounds: int = 2
    """Rounds of the clarification the requester is asked to answer. One further round runs
    after the last answered one to see whether the frontier is empty; if it is not, its
    questions are recorded unanswered. 0 leaves the clarification out, agent and stop alike."""
    intervention_timeout_s: int = 1800
    command_timeout_s: int = 600
    context_warn_ratio: float = 0.75
    context_abort_ratio: float = 0.95
    local_max_steps: int = 60
    max_mutants: int = 5
    """Wrong versions of the change measured per iteration, each one line of the diff altered
    in one way; 0 leaves the mutation check out."""
    mutant_command_max_s: int = 60
    """A verification that took longer than this on the change is not run against a mutant: the
    mutation check is bounded by what it costs, and a slow command spends the whole budget."""
    max_coverage_commands: int = 2
    """Test commands run again under the project's coverage tool per iteration, to see which
    lines of the change they execute; 0 leaves the coverage check out."""
    max_repeated_commands: int = 4
    """Commands run a second time on the evaluated version per iteration, to see whether they
    report the same thing twice; 0 leaves the stability check out."""
    repeat_command_max_s: int = 120
    """A verification that took longer than this on the change is not run a second time: the
    stability check costs one more run of the command, and a slow one doubles the iteration."""


class SandboxConfig(StrictModel):
    backend: str = "auto"
    """auto | host | seatbelt | docker"""
    docker_image: str = "python:3.12-slim"
    allow_network: bool = False
    worktrees_dir: str | None = None
    """Where run worktrees are created; must be outside the project. Default: ~/.cache/495."""


class ScopeConfig(StrictModel):
    allowed_paths: list[str] = Field(default_factory=list)
    """Glob patterns the change may touch; empty means any path except forbidden ones."""
    forbidden_paths: list[str] = Field(
        default_factory=lambda: [".495/**", ".git/**", ".github/**", ".gitlab-ci.yml"]
    )


class ProjectCommand(StrictModel):
    name: str
    command: str
    kind: VerificationKind = VerificationKind.command
    source: str = "config"
    timeout_s: int | None = None


class ProjectConfig(StrictModel):
    """User-provided project criteria (``.495/project.toml``)."""

    commands: list[ProjectCommand] = Field(default_factory=list)
    conventions: list[str] = Field(default_factory=list)
    docs: list[str] = Field(default_factory=list)
    scope: ScopeConfig = Field(default_factory=ScopeConfig)


class HarnessConfig(StrictModel):
    agents: dict[str, AgentSpec] = Field(
        default_factory=lambda: {"default": AgentSpec(name="default")}
    )
    roles: RolesConfig = Field(default_factory=RolesConfig)
    budget: Budget = Field(default_factory=Budget)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    auto_approve: bool = False

    def agent(self, name: str) -> AgentSpec:
        if name in self.agents:
            return self.agents[name]
        if ":" in name:
            kind, _, model = name.partition(":")
            return AgentSpec(name=name, kind=AgentKind(kind), model=model or None)
        if name in AgentKind.__members__:
            return AgentSpec(name=name, kind=AgentKind(name))
        raise KeyError(f"unknown agent '{name}'")


# --------------------------------------------------------------------------- project profile


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


# --------------------------------------------------------------------------- lessons


REPLACED_PREFIX = "replaced `"
"""Opening of the rationale a verification carries once the requester replaced its command."""


class LessonKind(StrEnum):
    """What a lesson of a run bears on: a criterion of the project, or what a later role is
    told about it (``Lesson``)."""

    command = "command"
    """A command the requester put in the place of the one the specification named, which
    ``.495/project.toml`` would declare under ``[[commands]]``."""
    convention = "convention"
    """A rule a correction stated, which the producer had no way of reading before it wrote:
    a line of ``conventions``."""
    allowed_path = "allowed_path"
    """A path the change was allowed to touch that the project's criteria do not declare:
    a glob of ``[scope] allowed_paths``."""
    note = "note"
    """Something the next specification is better written knowing. It declares nothing and
    reaches the specifier as a fact."""
    false_positive = "false_positive"
    """A claim a reviewer made that does not hold in this project. It declares nothing and
    reaches the next reviewer of that perspective as a fact, so that a claim the requester has
    already weighed is not raised against every change."""


class LessonStatus(StrEnum):
    """Where a lesson stands (``Lesson``)."""

    open = "open"
    """Read from a run and put to the requester, not answered yet."""
    accepted = "accepted"
    """In force: it is part of the project's criteria and reaches the next run."""
    declined = "declined"
    """Refused, with the requester's reason; the same lesson is not proposed again."""
    deferred = "deferred"
    """Set aside; stays listed, and can be accepted or declined at any time."""


class Lesson(StrictModel):
    """One thing a run showed about the project itself, put to the requester.

    A lesson is identified by its kind and by what it would declare, so that the same lesson
    read from several runs is one record: ``run_ids`` then names every run that showed it, and
    a lesson three runs in a row have shown is one line with three runs behind it. ``value`` is
    what enters the criteria — the command, the text of the convention, the glob — and is empty
    for a ``note``, which declares nothing; ``statement`` is the lesson in one sentence, as the
    requester and the next specifier read it; ``observed`` is what the runs recorded, in words,
    so that the requester can weigh the lesson against the evidence rather than against a claim.
    """

    id: str
    kind: LessonKind
    statement: str
    value: str = ""
    name: str = ""
    """For a ``command`` lesson, the name its ``[[commands]]`` entry takes."""
    command_kind: VerificationKind | None = None
    perspective: str = ""
    """For a ``false_positive`` lesson, the reviewer whose claim it answers."""
    declared: str = ""
    """What the requester chose to declare in the place of ``value`` when accepting the lesson.
    Kept apart from it so that what the runs showed stays what the runs showed."""
    observed: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    status: LessonStatus = LessonStatus.open
    reason: str = ""
    """The requester's words on a decline or a deferral."""
    created_at: dt.datetime = Field(default_factory=utcnow)
    updated_at: dt.datetime = Field(default_factory=utcnow)
    decided_at: dt.datetime | None = None
    """When the requester last answered; None while the lesson has only been stated."""

    @property
    def key(self) -> str:
        """What tells one lesson from another: its kind, the reviewer it answers when it
        answers one, and what it would declare."""
        head = f"{self.kind.value}:{self.perspective}" if self.perspective else self.kind.value
        return f"{head}:{self.value or self.statement}"

    @property
    def declares(self) -> bool:
        """Whether accepting it adds something to the project's criteria."""
        return self.kind not in (LessonKind.note, LessonKind.false_positive)

    @property
    def answerable(self) -> bool:
        return self.status in (LessonStatus.open, LessonStatus.deferred)


class Lessons(StrictModel):
    """What the runs of one project have shown about it: ``<state_dir>/lessons.json``."""

    schema_version: int = SCHEMA_VERSION
    lessons: list[Lesson] = Field(default_factory=list)

    def get(self, lesson_id: str) -> Lesson | None:
        for lesson in self.lessons:
            if lesson.id == lesson_id:
                return lesson
        return None

    def find(self, key: str) -> Lesson | None:
        for lesson in self.lessons:
            if lesson.key == key:
                return lesson
        return None

    @property
    def in_force(self) -> list[Lesson]:
        """The lessons the requester accepted: the ones a run is given."""
        return [x for x in self.lessons if x.status is LessonStatus.accepted]


class ProjectProfile(StrictModel):
    root: str
    languages: list[str] = Field(default_factory=list)
    tooling: list[str] = Field(default_factory=list)
    commands: list[ProjectCommand] = Field(default_factory=list)
    role_coverage: list[RoleCoverage] = Field(default_factory=list)
    catalogue_gaps: list[CatalogueGap] = Field(default_factory=list)
    declined_roles: list[DeclinedRole] = Field(default_factory=list)
    lessons: list[Lesson] = Field(default_factory=list)
    """What earlier runs on this project showed and the requester accepted (``Lesson``)."""
    conventions: list[str] = Field(default_factory=list)
    doc_files: list[str] = Field(default_factory=list)
    detected_from: list[str] = Field(default_factory=list)
    readiness: list[ReadinessCheck] = Field(default_factory=list)
    base_commit: str | None = None
    default_branch: str | None = None

    def command(self, name: str) -> ProjectCommand | None:
        for c in self.commands:
            if c.name == name:
                return c
        return None

    def coverage(self, technology: str, role: CatalogueRole) -> RoleCoverage | None:
        for r in self.role_coverage:
            if r.technology == technology and r.role is role:
                return r
        return None

    def declined(self, technology: str, role: CatalogueRole) -> DeclinedRole | None:
        for d in self.declined_roles:
            if d.technology == technology and d.role is role:
                return d
        return None

    @property
    def ready(self) -> bool:
        return all(r.executable for r in self.readiness)


# --------------------------------------------------------------------------- conformance proposals


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


# --------------------------------------------------------------------------- retrospective


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


# --------------------------------------------------------------------------- clarification


class ClarifyOption(StrictModel):
    """One answer a question offers, and what taking it does to the specification.

    ``consequence`` is the whole point of the option: which requirement appears or disappears,
    which verification changes kind. An option that states none says nothing about what is
    being decided, and its question is dropped rather than put to the requester.
    """

    key: str
    label: str
    consequence: str = ""


class ClarifyQuestion(StrictModel):
    """One decision the intent leaves open, as the clarifier puts it.

    ``checked`` is what the clarifier read or ran to reach ``recommended``: a question whose
    answer is in the repository then shows as one, in front of the requester, instead of
    resting on the prompt. The harness completes ``options`` with ``other``, which takes a
    note, so that the tree never forces a false choice.
    """

    id: str
    title: str
    body: str = ""
    options: list[ClarifyOption] = Field(default_factory=list)
    recommended: str = ""
    checked: list[str] = Field(default_factory=list)

    def option(self, key: str) -> ClarifyOption | None:
        for o in self.options:
            if o.key == key:
                return o
        return None


class ClarifyAnswer(StrictModel):
    """What was decided on one question, and by whom.

    ``recommended`` says whether the answer is the one the clarifier advised, and ``taken_by``
    whether the requester chose it or the harness took it on their behalf under
    ``--auto-approve``; the report shows both, because they are not the same record.
    """

    question_id: str
    question: str
    option: str
    label: str = ""
    note: str = ""
    recommended: bool = False
    taken_by: DecisionMaker = DecisionMaker.human
    answered_at: dt.datetime = Field(default_factory=utcnow)

    @property
    def statement(self) -> str:
        """The decision in one sentence, as the later roles read it."""
        chosen = self.label or self.option
        return f"{self.question} — {chosen}" + (f": {self.note}" if self.note else "")


class ClarifyRound(StrictModel):
    """One intervention of the clarification: the frontier it returned, and the answers.

    ``dropped`` names what the harness took out of the round and why — a question already
    settled, one with fewer than two options, one whose option states no consequence. The
    round holds only what was actually put to the requester.
    """

    n: int
    intervention_id: str
    questions: list[ClarifyQuestion] = Field(default_factory=list)
    answers: list[ClarifyAnswer] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)
    asked_at: dt.datetime = Field(default_factory=utcnow)

    def question(self, qid: str) -> ClarifyQuestion | None:
        for q in self.questions:
            if q.id == qid:
                return q
        return None


class Clarification(StrictModel):
    """The decisions taken before the specification, round by round.

    ``open_questions`` are the ones the last round returned and nobody was asked: the round cap
    was reached, so the frontier was not empty when the phase ended. They are recorded rather
    than dropped, so that the specifier states an assumption knowing it stands on a question
    that was never put.
    """

    rounds: list[ClarifyRound] = Field(default_factory=list)
    open_questions: list[ClarifyQuestion] = Field(default_factory=list)
    complete: bool = False
    stopped_at_cap: bool = False

    @property
    def answers(self) -> list[ClarifyAnswer]:
        return [a for r in self.rounds for a in r.answers]

    def answered(self, question: ClarifyQuestion) -> ClarifyAnswer | None:
        """The answer a question already has, matched on its id or on its words.

        Both, because the clarifier chooses the ids: the same decision can come back under a
        new id, and a fresh decision can reuse one. Either match settles it.
        """
        title = normalise_question(question.title)
        for a in self.answers:
            if a.question_id == question.id or normalise_question(a.question) == title:
                return a
        return None

    @property
    def rounds_answered(self) -> int:
        return sum(1 for r in self.rounds if r.answers)

    @property
    def says_anything(self) -> bool:
        """Whether the phase left the later roles something to read.

        A round that came back with an empty frontier settled nothing and left nothing: telling
        the specifier that no decision was taken is not a fact, it is a blank section.
        """
        return bool(self.answers or self.open_questions)


def normalise_question(text: str) -> str:
    """A question reduced to its words, for telling one already answered from a new one."""
    return " ".join(text.lower().split()).strip(" ?.:;!")


class DecisionTaken(StrictModel):
    """One requester's decision as the specification carries it: what was asked, what was
    chosen among what was offered, and who chose.

    Kept on the specification rather than read back from the run, so that the artifact the
    requester approves and the reviewers are given states the decisions it was written under.
    """

    question: str
    options: list[str] = Field(default_factory=list)
    choice: str
    note: str = ""
    taken_by: DecisionMaker = DecisionMaker.human


class ClarifyReply(StrictModel):
    """One answer as the requester gives it: which option, and the note an ``other`` needs."""

    question_id: str
    option: str
    note: str = ""


class DecisionAnswer(StrictModel):
    """What an interface hands back when it has put a pending decision to the requester.

    ``answers`` is empty for every decision that is one question; a ``clarify`` round carries
    one reply per question of the round.
    """

    choice: str
    note: str = ""
    answers: list[ClarifyReply] = Field(default_factory=list)


# --------------------------------------------------------------------------- specification


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


# --------------------------------------------------------------------------- interventions


class Usage(StrictModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    requests: int = 0
    context_window: int | None = None
    context_peak_tokens: int | None = None
    context_peak_is_upper_bound: bool = False

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    @property
    def context_utilization(self) -> float | None:
        if not self.context_window or self.context_peak_tokens is None:
            return None
        return self.context_peak_tokens / self.context_window

    def add(self, other: Usage) -> Usage:
        peak = max(self.context_peak_tokens or 0, other.context_peak_tokens or 0) or None
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            requests=self.requests + other.requests,
            context_window=other.context_window or self.context_window,
            context_peak_tokens=peak,
            context_peak_is_upper_bound=self.context_peak_is_upper_bound
            or other.context_peak_is_upper_bound,
        )


class Cost(StrictModel):
    usd: float | None = None
    basis: CostBasis = CostBasis.unknown
    source: str = ""


class SandboxInfo(StrictModel):
    backend: str
    network: str = "denied"
    writable_paths: list[str] = Field(default_factory=list)
    detail: str = ""


class AgentIdentity(StrictModel):
    kind: AgentKind
    name: str
    model: str | None = None
    cli_version: str | None = None
    session_id: str | None = None
    effort: str | None = None


class Intervention(StrictModel):
    id: str
    iteration: int
    role: Role
    perspective: str | None = None
    agent: AgentIdentity
    capability: Capability
    allowed_tools: list[str] = Field(default_factory=list)
    sandbox: SandboxInfo
    cwd: str
    timeout_s: int
    status: InterventionStatus = InterventionStatus.running
    started_at: dt.datetime = Field(default_factory=utcnow)
    ended_at: dt.datetime | None = None
    duration_s: float | None = None
    usage: Usage = Field(default_factory=Usage)
    cost: Cost = Field(default_factory=Cost)
    context_ref: str = ""
    transcript_ref: str = ""
    output_ref: str = ""
    exit_code: int | None = None
    error: str | None = None
    version_before: str | None = None
    version_after: str | None = None
    activity: dict[str, int] = Field(default_factory=dict)
    """Tool or command usage counts observed in the transcript (e.g. {"Bash": 5, "Edit": 2})."""


# --------------------------------------------------------------------------- evidence


class EvidenceKind(StrEnum):
    command_result = "command_result"
    scope_check = "scope_check"
    review_verdict = "review_verdict"
    integrity = "integrity"
    instrument_check = "instrument_check"
    """Control run of a failing verification on the base version, to tell instrument from defect."""
    baseline = "baseline"
    """Readiness run of a project command on the base version, before any change exists."""
    suite_check = "suite_check"
    """Whether the existing test suite is, on the change, the suite that passed on the base:
    no test file deleted, no test removed or skipped, no smaller tally printed by the runner."""
    mutation_check = "mutation_check"
    """Whether the verifications that observe the change also constrain it: one mutant, a line
    the change added altered in one stated way, and what the commands reported on it."""
    coverage_check = "coverage_check"
    """Which lines the change adds the verifications execute: the test commands run again under
    the project's coverage tool, and their report crossed with the diff."""
    stability_check = "stability_check"
    """Whether a command reports the same thing twice on the same version: the second run of a
    command a requirement leans on, read against the first."""


class Evidence(StrictModel):
    id: str
    kind: EvidenceKind
    iteration: int
    subject_version: str | None = None
    verification_id: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    produced_by: str = "harness"
    command: str | None = None
    exit_code: int | None = None
    expected_exit_code: int | None = None
    passed: bool | None = None
    summary: str = ""
    output_ref: str | None = None
    output_sha256: str | None = None
    duration_s: float | None = None
    sandbox: SandboxInfo | None = None
    created_at: dt.datetime = Field(default_factory=utcnow)


class Finding(StrictModel):
    severity: Severity
    title: str
    detail: str = ""
    file: str | None = None
    line: int | None = None
    requirement_id: str | None = None
    verification_id: str | None = None
    """Set when the finding is about how something is measured rather than about the change."""
    evidence: str = ""
    """What the reviewer observed that supports the finding (file, command output...)."""


class ReviewVerdict(StrictModel):
    intervention_id: str
    perspective: str
    verdict: Verdict
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    requirement_assessment: dict[str, RequirementStatus] = Field(default_factory=dict)
    confidence: float | None = None
    discarded: bool = False
    discard_reason: str = ""


# --------------------------------------------------------------------------- decisions


class DecisionOption(StrictModel):
    key: str
    label: str
    needs_note: bool = False
    consequence: str = ""
    """What happens to the run if this option is taken. Shown with the option, never guessed."""


class PendingDecision(StrictModel):
    kind: DecisionKind
    question: str
    options: list[DecisionOption]
    questions: list[ClarifyQuestion] = Field(default_factory=list)
    """The questions of a ``clarify`` round, answered one by one under the option that says so.
    Empty for every decision that is itself one question."""
    context: dict[str, Any] = Field(default_factory=dict)
    raised_at: dt.datetime = Field(default_factory=utcnow)


class Decision(StrictModel):
    id: str
    kind: DecisionKind
    made_by: DecisionMaker
    outcome: str
    rationale: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    iteration: int = 0
    question: str | None = None
    answers: list[ClarifyAnswer] = Field(default_factory=list)
    """What was answered question by question, when the decision carried several."""
    created_at: dt.datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- version & result


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
