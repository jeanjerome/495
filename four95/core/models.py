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
    specifier = "specifier"
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


class Sufficiency(StrEnum):
    sufficient = "sufficient"
    insufficient = "insufficient"
    missing = "missing"
    faulty = "faulty"
    """The command fails identically with and without the change: it measures something else."""


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
    specifier: str = "default"
    producer: str = "default"
    reviewers: list[ReviewerSpec] = Field(
        default_factory=lambda: [
            ReviewerSpec(perspective="spec_compliance"),
            ReviewerSpec(perspective="correctness"),
            ReviewerSpec(perspective="security"),
        ]
    )


class Budget(StrictModel):
    max_cost_usd: float | None = 10.0
    max_total_tokens: int | None = None
    max_interventions: int = 40
    max_iterations: int = 3
    intervention_timeout_s: int = 1800
    command_timeout_s: int = 600
    context_warn_ratio: float = 0.75
    context_abort_ratio: float = 0.95
    local_max_steps: int = 60


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


class ProjectProfile(StrictModel):
    root: str
    languages: list[str] = Field(default_factory=list)
    tooling: list[str] = Field(default_factory=list)
    commands: list[ProjectCommand] = Field(default_factory=list)
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

    @property
    def ready(self) -> bool:
        return all(r.executable for r in self.readiness)


# --------------------------------------------------------------------------- specification


class Verification(StrictModel):
    id: str
    kind: VerificationKind
    description: str
    command: str | None = None
    expected_exit_code: int = 0
    to_create: bool = False
    """The verification (typically a test) must be created as part of the change."""
    sufficiency: Sufficiency = Sufficiency.sufficient
    rationale: str = ""
    timeout_s: int | None = None


class Requirement(StrictModel):
    id: str
    statement: str
    rationale: str = ""
    verification_ids: list[str] = Field(default_factory=list)
    status: RequirementStatus = RequirementStatus.pending
    status_reason: str = ""


class Spec(StrictModel):
    requirements: list[Requirement] = Field(default_factory=list)
    verifications: list[Verification] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
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
    diff = "diff"
    integrity = "integrity"
    agent_output = "agent_output"
    instrument_check = "instrument_check"
    """Control run of a failing verification on the base version, to tell instrument from defect."""
    baseline = "baseline"
    """Readiness run of a project command on the base version, before any change exists."""


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
    instrument_faults: list[str] = Field(default_factory=list)
    """Verifications that failed identically on the base version; the spec is at fault, not the change."""
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
    spec: Spec = Field(default_factory=Spec)
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
