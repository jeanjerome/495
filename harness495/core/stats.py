"""What the runs of a project say when they are read together.

One run answers one question: was this change accepted, and on what evidence. The store holds
every run, and nobody read them as a series — how often an instrument is at fault, how many
iterations a change costs here, what a requirement costs, which perspective finds something and
which kind of verification is most often unable to tell the change from its absence. All of it
is in the run documents; ``summarise`` reads them and states it, so that the work of closing a
gap can be aimed at the thing that keeps costing (``core/lessons.py`` is the other half: what
one run showed about the project, put to the requester).

Nothing here is persisted and nothing here decides: the numbers are read again from the runs on
every call, and what is done about them is the requester's.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter

from pydantic import Field

from harness495.core.models import (
    NON_DISCRIMINATING,
    REPLACED_PREFIX,
    Lessons,
    RequirementStatus,
    Run,
    Severity,
    StrictModel,
    Sufficiency,
    Verdict,
    VerificationKind,
    utcnow,
)

RECURRING_SHOWN = 5
"""Recurring findings kept per perspective: the ones worth a convention, not a log."""


class InstrumentStat(StrictModel):
    """One command the verifications of the project leaned on, and how it behaved."""

    command: str
    runs: int = 0
    """Runs whose specification named the command."""
    faults: int = 0
    """Times the harness recorded it unable to tell the change from its absence."""
    replaced: int = 0
    """Times the requester put another command in its place."""


class KindStat(StrictModel):
    """One kind of verification, and how often it could not decide anything."""

    kind: VerificationKind
    verifications: int = 0
    non_discriminating: int = 0
    """Reported the same thing with and without the change, or failed on both."""
    insufficient: int = 0
    """Stated insufficient or missing by the gate, before anything ran."""


class PerspectiveStat(StrictModel):
    """One reviewer perspective, and what it found across the runs."""

    perspective: str
    reviews: int = 0
    rejected: int = 0
    discarded: int = 0
    findings: int = 0
    blockers: int = 0
    recurring: list[str] = Field(default_factory=list)
    """Findings whose title came back in more than one run, most frequent first."""


class Stats(StrictModel):
    """The runs of one project read as a series: the shape of ``495 stats --json``."""

    project: str
    created_at: dt.datetime = Field(default_factory=utcnow)
    runs: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    by_outcome: dict[str, int] = Field(default_factory=dict)
    iterations: int = 0
    iterations_mean: float = 0.0
    """Iterations per run that produced at least one; a change accepted first time counts 1."""
    corrections: int = 0
    requirements: int = 0
    requirements_by_status: dict[str, int] = Field(default_factory=dict)
    cost_usd: float = 0.0
    cost_unknown_interventions: int = 0
    """Interventions whose cost neither the CLI reported nor the price table could estimate."""
    cost_per_requirement: float | None = None
    interventions: int = 0
    instrument_faults: int = 0
    instruments: list[InstrumentStat] = Field(default_factory=list)
    kinds: list[KindStat] = Field(default_factory=list)
    perspectives: list[PerspectiveStat] = Field(default_factory=list)
    clarify_rounds: int = 0
    decisions_taken: int = 0
    questions_left_open: int = 0
    lessons_by_status: dict[str, int] = Field(default_factory=dict)


def _counted(values: list[str]) -> dict[str, int]:
    return dict(Counter(values).most_common())


def _flat(text: str) -> str:
    return " ".join(text.split())


def summarise(project: str, runs: list[Run], lessons: Lessons | None = None) -> Stats:
    """Read every run of the store as one series. A pure function of the documents given."""
    stats = Stats(project=project, runs=len(runs))
    stats.by_status = _counted([r.status.value for r in runs])
    stats.by_outcome = _counted([r.result.outcome.value for r in runs if r.result.outcome])
    iterated = [r for r in runs if r.iterations]
    stats.iterations = sum(len(r.iterations) for r in runs)
    stats.iterations_mean = round(stats.iterations / len(iterated), 2) if iterated else 0.0
    stats.corrections = sum(len(it.correction_requests) for r in runs for it in r.iterations)
    stats.requirements = sum(len(r.spec.requirements) for r in runs)
    stats.requirements_by_status = _counted(
        [req.status.value for r in runs for req in r.spec.requirements]
    )
    stats.cost_usd = round(sum(r.consumption.cost_usd for r in runs), 4)
    stats.cost_unknown_interventions = sum(r.consumption.cost_unknown_interventions for r in runs)
    stats.interventions = sum(r.consumption.interventions for r in runs)
    assessed = sum(
        1
        for r in runs
        for req in r.spec.requirements
        if req.status is not RequirementStatus.pending
    )
    if assessed and stats.cost_usd:
        stats.cost_per_requirement = round(stats.cost_usd / assessed, 4)
    stats.instrument_faults = sum(len(it.instrument_faults) for r in runs for it in r.iterations)
    stats.instruments = _instruments(runs)
    stats.kinds = _kinds(runs)
    stats.perspectives = _perspectives(runs)
    stats.clarify_rounds = sum(len(r.clarification.rounds) for r in runs)
    stats.decisions_taken = sum(len(r.clarification.answers) for r in runs)
    stats.questions_left_open = sum(len(r.clarification.open_questions) for r in runs)
    if lessons is not None:
        stats.lessons_by_status = _counted([x.status.value for x in lessons.lessons])
    return stats


def _instruments(runs: list[Run]) -> list[InstrumentStat]:
    """A row per command a specification named, ordered by what it cost the runs."""
    rows: dict[str, InstrumentStat] = {}

    def row(command: str) -> InstrumentStat:
        if command not in rows:
            rows[command] = InstrumentStat(command=command)
        return rows[command]

    for run in runs:
        for v in run.spec.verifications:
            if not v.command:
                continue
            row(v.command).runs += 1
            if v.rationale.startswith(REPLACED_PREFIX):
                # The command in force is the replacement; what it replaced is what was at fault.
                row(v.rationale[len(REPLACED_PREFIX) :].partition("`")[0]).replaced += 1
        for it in run.iterations:
            for fault in it.instrument_faults:
                faulty = run.spec.verification(fault.partition(":")[0])
                if faulty is not None and faulty.command:
                    row(faulty.command).faults += 1
    return sorted(rows.values(), key=lambda s: (-s.faults - s.replaced, -s.runs, s.command))


def _kinds(runs: list[Run]) -> list[KindStat]:
    """A row per kind of verification: how often a verification of it decided nothing."""
    rows: dict[VerificationKind, KindStat] = {}
    for run in runs:
        for v in run.spec.verifications:
            stat = rows.setdefault(v.kind, KindStat(kind=v.kind))
            stat.verifications += 1
            if v.sufficiency in NON_DISCRIMINATING:
                stat.non_discriminating += 1
            elif v.sufficiency in (Sufficiency.insufficient, Sufficiency.missing):
                stat.insufficient += 1
    return sorted(
        rows.values(),
        key=lambda s: (-(s.non_discriminating + s.insufficient), -s.verifications, s.kind.value),
    )


def _perspectives(runs: list[Run]) -> list[PerspectiveStat]:
    """A row per reviewer perspective: what it reviewed, what it found, what came back."""
    rows: dict[str, PerspectiveStat] = {}
    titles: dict[str, Counter[str]] = {}
    for run in runs:
        seen: dict[str, set[str]] = {}
        for review in run.reviews:
            stat = rows.setdefault(
                review.perspective, PerspectiveStat(perspective=review.perspective)
            )
            stat.reviews += 1
            if review.discarded:
                stat.discarded += 1
                continue
            if review.verdict is Verdict.reject:
                stat.rejected += 1
            for f in review.findings:
                stat.findings += 1
                if f.severity is Severity.blocker:
                    stat.blockers += 1
                seen.setdefault(review.perspective, set()).add(_flat(f.title).casefold())
        for perspective, found in seen.items():
            # Counted once per run: a finding a reviewer repeats over three iterations of the
            # same run is one thing the project keeps doing, not three.
            titles.setdefault(perspective, Counter()).update(found)
    for perspective, counter in titles.items():
        rows[perspective].recurring = [
            f"{n}× {title}" for title, n in counter.most_common(RECURRING_SHOWN) if n > 1
        ]
    return sorted(rows.values(), key=lambda s: (-s.findings, s.perspective))
