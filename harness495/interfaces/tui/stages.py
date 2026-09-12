"""The stage model: one structure drives navigation, progress and the badges.

The engine's own phases, collapsed to the eight a user has a question about. A stop is both
"where the run is", "the tab that shows what that stage produced" and "where the controls that
act on it live", so there is no menu to learn: you look for a fact, or act on it, at the stage
it belongs to.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text

from harness495.core.models import (
    DecisionKind,
    RequirementStatus,
    Role,
    Run,
    RunStatus,
    Severity,
)
from harness495.interfaces.tui.reading import (
    allowing_glob,
    latest_results,
    requirement_counts,
)


@dataclass(frozen=True)
class Stage:
    """One stop of the run, which is also one tab.

    ``question`` is the reason the stop exists. It is what the tab promises to answer, and it
    is printed as the panel's subtitle, so the promise is visible where it has to be kept.
    """

    key: str
    name: str
    short: str
    question: str
    statuses: frozenset[RunStatus]


# "specify" and "gate" are one stop because approving a specification is reading it; "decide"
# and the decision it may raise are one stop because answering is reading the ledger.
STAGES: tuple[Stage, ...] = (
    Stage(
        "1",
        "profile",
        "prof",
        "what 495 understood about this project, and what it can actually run",
        frozenset({RunStatus.created}),
    ),
    Stage(
        "2",
        "spec",
        "spec",
        "what must hold after the change, and what checks it",
        frozenset({RunStatus.profiled, RunStatus.specified}),
    ),
    Stage(
        "3",
        "change",
        "chg",
        "what the producer did, in which sandbox, at what cost",
        frozenset({RunStatus.ready, RunStatus.producing}),
    ),
    Stage(
        "4",
        "checks",
        "chk",
        "what the verification commands observed on the candidate",
        frozenset({RunStatus.produced, RunStatus.verifying}),
    ),
    Stage(
        "5",
        "review",
        "rev",
        "what independent reviewers said, and what was discarded",
        frozenset({RunStatus.verified, RunStatus.reviewing}),
    ),
    Stage(
        "6",
        "verdict",
        "vrd",
        "where each requirement stands, why, and what happens next",
        frozenset({RunStatus.reviewed, RunStatus.awaiting_decision}),
    ),
    Stage(
        "7",
        "deliver",
        "dlv",
        "what you got, and the commands that act on it",
        frozenset({RunStatus.accepted}),
    ),
    # The run ends where the harness stops being able to observe anything: it delivers a patch
    # and a branch, you integrate them, and only then can anyone ask whether what landed is
    # what was verified. A delivered run therefore stands *here*, waiting on a merge that is
    # yours to make.
    Stage(
        "8",
        "integration",
        "int",
        "whether what you merged is what was verified",
        frozenset({RunStatus.delivered}),
    ),
)
STAGE_INDEX = {s.name: i for i, s in enumerate(STAGES)}
STAGE_BY_KEY = {s.key: s.name for s in STAGES}

# A run that stopped is still somewhere: it stopped at the stage that could not go on.
TERMINAL_STAGE = {
    RunStatus.accepted: "deliver",
    RunStatus.rejected: "verdict",
    RunStatus.undetermined: "verdict",
    RunStatus.aborted: "verdict",
    RunStatus.failed: "verdict",
}

# ``awaiting_decision`` says the run is stopped, not where. The question does: a readiness
# question is asked at the profile, a spec question at the gate. Without this the "waiting on
# you" marker would always land on the last tab, and send the user to the wrong screen.
DECISION_STAGE = {
    DecisionKind.readiness: "profile",
    DecisionKind.approve_spec: "spec",
    DecisionKind.scope: "change",
    DecisionKind.no_progress: "change",
    DecisionKind.instrument_fault: "checks",
    DecisionKind.acceptance: "verdict",
    DecisionKind.undetermined: "verdict",
    DecisionKind.iteration_limit: "verdict",
    DecisionKind.budget: "verdict",
}

STATE_GLYPH = {"done": "●", "here": "◉", "todo": "○", "blocked": "◆", "failed": "✕"}


def stage_of(run: Run) -> str:
    """The stop the run is at right now."""
    status = run.status
    if status is RunStatus.paused and run.resume_status is not None:
        status = run.resume_status
    if status is RunStatus.awaiting_decision and run.pending_decision is not None:
        return DECISION_STAGE.get(run.pending_decision.kind, "verdict")
    for stage in STAGES:
        if status in stage.statuses:
            return stage.name
    if status in {RunStatus.failed, RunStatus.aborted}:
        # A run that broke did not reach the verdict; it stopped where it was. Reading that
        # from what exists on disk is the only way to say so without inventing a phase.
        return furthest_stage(run)
    return TERMINAL_STAGE.get(status, "profile")


def furthest_stage(run: Run) -> str:
    """The last stage that left something behind."""
    if run.result.integration is not None:
        return "integration"
    if run.result.report_ref:
        return "deliver"
    if any(r.status is not RequirementStatus.pending for r in run.spec.requirements):
        return "verdict"
    if run.reviews:
        return "review"
    if run.evidence:
        return "checks"
    it = run.current_iteration
    if (it and it.version and it.version.head_commit) or any(
        i.role is Role.producer for i in run.interventions
    ):
        return "change"
    if run.spec.requirements:
        return "spec"
    return "profile"


def stage_state(run: Run, name: str) -> str:
    """``done``, ``here``, ``todo``, ``blocked`` or ``failed`` for one stop.

    Read from ``run.status`` and nothing else. The event log is a record of what happened, not
    a statement of where the run is.
    """
    here = STAGE_INDEX[stage_of(run)]
    index = STAGE_INDEX[name]
    if name == "integration":
        # The only stop whose state is not the run's: the harness cannot walk it, it can only
        # report what it found when you asked it to look at the ref you merged into.
        g = run.result.integration
        state = run.integration_state()
        if state == "landed":
            return "done" if g is None or g.verifications_passed is not False else "failed"
        if state == "differs":
            return "failed"
        if run.status is RunStatus.delivered:
            # Delivered and not merged into is the run standing still, not the run broken: it
            # has done everything it can, and the merge it is waiting for is a human act. A
            # ref nobody merged into says that same thing back, so asking about one leaves the
            # stop where it was — a question must not turn a stop red by being asked.
            return "blocked"
    if index < here:
        return "done"
    if index > here:
        return "todo"
    if run.status is RunStatus.awaiting_decision:
        return "blocked"
    if run.status is RunStatus.paused:
        return "blocked"
    if run.status in {RunStatus.failed, RunStatus.aborted, RunStatus.rejected}:
        return "failed"
    return "here"


def stage_badge(run: Run, name: str) -> Text | None:
    """The count a stop carries, in the colour of its health.

    A badge is for scanning: it says *where* to look. The headline inside the view says what
    happened, in words. Splitting the two is what keeps the bar readable at 8 stops.
    """
    count, bad = stage_count(run, name)
    if count is None:
        return None
    return Text(count, style="tab.count.bad" if bad else "tab.count")


def stage_count(run: Run, name: str) -> tuple[str | None, bool]:
    """The count a stop carries, and whether it is bad news.

    Bad means *this stop holds something that blocks the run or misleads it* — a command that
    cannot run, a check that fails, a blocker, a violated requirement. A warning is not bad
    news here: the headline inside the view states it in words, and painting it red as well
    would leave the strip with no way to say which stop actually needs opening.
    """
    if name == "profile":
        if not run.profile or not run.profile.readiness:
            return None, False
        ready = sum(1 for r in run.profile.readiness if r.executable)
        total = len(run.profile.readiness)
        return f"{ready}/{total}", ready < total
    if name == "spec":
        if not run.spec.requirements:
            return None, False
        orphans = any(not r.verification_ids for r in run.spec.requirements)
        return f"{len(run.spec.requirements)}R", orphans
    if name == "change":
        it = run.current_iteration
        if not it or not it.version or not it.version.head_commit:
            return None, False
        outside = any(
            allowing_glob(run.spec.allowed_paths, f) is None for f in it.version.files_changed
        )
        return f"{len(it.version.files_changed)}f", outside
    if name == "checks":
        results = latest_results(run)
        if not any(results.values()):
            return None, False
        passed = sum(1 for e in results.values() if e and e.passed)
        total = len(run.spec.verifications)
        return f"{passed}/{total}", passed < total
    if name == "review":
        if not run.reviews:
            return None, False
        kept = [r for r in run.reviews if not r.discarded]
        blockers = sum(1 for r in kept for f in r.findings if f.severity is Severity.blocker)
        if blockers:
            return f"{blockers}✕", True
        return f"{len(kept)}/{len(run.reviews)}", False
    if name == "verdict":
        counts = requirement_counts(run)
        if counts[RequirementStatus.violated]:
            return f"{counts[RequirementStatus.violated]}✕", True
        if counts[RequirementStatus.undetermined]:
            return f"{counts[RequirementStatus.undetermined]}◐", False
        if counts[RequirementStatus.satisfied]:
            return f"{counts[RequirementStatus.satisfied]}●", False
        return None, False
    if name == "deliver":
        return ("✓", False) if run.status is RunStatus.delivered else (None, False)
    if name == "integration":
        state = run.integration_state()
        if state == "landed":
            g = run.result.integration
            passed = g is None or g.verifications_passed is not False
            return ("✓", False) if passed else ("✕", True)
        # ``unmerged`` wears no badge, for the reason it takes no red: the stop stands where it
        # stood before the question, and a mark there would say the question found something.
        return ("✕", True) if state == "differs" else (None, False)
    return None, False


def status_style(status: RunStatus) -> str:
    if status in {RunStatus.failed, RunStatus.aborted, RunStatus.rejected}:
        return "attn.dead"
    if status in {RunStatus.awaiting_decision, RunStatus.paused, RunStatus.undetermined}:
        return "attn.you"
    if status is RunStatus.delivered:
        return "attn.done"
    return "attn.work"
