"""The closed sets of the vocabulary: what a run, a role, a verification or a decision may be.

Each is a ``StrEnum``, so the member persisted is the string read back and ``495 schema``
publishes it. The frozen sets name the groups the engine tests membership of, rather than
spelling the members out at each call site.
"""

from __future__ import annotations

from enum import StrEnum


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
