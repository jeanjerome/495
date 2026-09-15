"""The configuration a run works under: agents, roles, budget, isolation and project criteria.

``HarnessConfig`` is the whole of it, as ``495 schema config`` publishes it; ``ProjectConfig``
is the part the requester declares in ``.495/project.toml``, and ``Budget`` the caps every
phase is measured against.
"""

from __future__ import annotations

from pydantic import Field

from harness495.core.models.base import StrictModel
from harness495.core.models.enums import AgentKind, VerificationKind
from harness495.core.models.specification import Spec


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
