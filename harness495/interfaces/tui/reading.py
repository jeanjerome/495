"""What every view reads off a run.

These are the questions more than one surface asks — which check carries which requirement,
what the latest result was, who is holding the worktree — kept in one place so the pipeline
strip, the headlines and the stage views cannot answer them differently.

Everything here is a pure function of a :class:`~harness495.core.models.Run`. Nothing consults
the event log: a log replayed from disk, truncated or arriving out of order would make a
reading built on it disagree with the run itself.
"""

from __future__ import annotations

from collections.abc import Sequence

from harness495.core.models import (
    Evidence,
    EvidenceKind,
    Finding,
    Intervention,
    InterventionStatus,
    RequirementStatus,
    ReviewVerdict,
    Run,
    Verification,
)


def running_intervention(run: Run) -> Intervention | None:
    """The agent holding the worktree right now, if one is."""
    live = [i for i in run.interventions if i.status is InterventionStatus.running]
    return live[-1] if live else None


def latest_results(run: Run) -> dict[str, Evidence | None]:
    """The last command result per verification, in spec order.

    Stable by construction: V3 keeps its place whether its evidence has arrived, failed, or
    not been produced, so a result landing mid-run never moves the line you were reading.
    """
    out: dict[str, Evidence | None] = {}
    for v in run.spec.verifications:
        found = [
            e
            for e in run.evidence
            if e.verification_id == v.id and e.kind is EvidenceKind.command_result
        ]
        out[v.id] = found[-1] if found else None
    return out


def requirement_counts(run: Run) -> dict[RequirementStatus, int]:
    counts = dict.fromkeys(RequirementStatus, 0)
    for r in run.spec.requirements:
        counts[r.status] += 1
    return counts


def verification_state(run: Run, v: Verification) -> tuple[str, str, str]:
    """Glyph, style and one-line note for a check, from its latest evidence."""
    it = run.current_iteration
    if it and v.id in it.instrument_faults:
        return "◐", "suf.faulty", "fails without the change too"
    results = [
        e
        for e in run.evidence
        if e.verification_id == v.id and e.kind is EvidenceKind.command_result
    ]
    if not results:
        return "○", "req.pending", "not run yet"
    latest = results[-1]
    if latest.passed:
        return "✓", "req.satisfied", latest.summary
    return "✕", "req.violated", latest.summary


def allowing_glob(globs: Sequence[str], path: str) -> str | None:
    """The allowed-path pattern a changed file falls under, or ``None`` if it falls outside."""
    for g in globs:
        head = g.split("*", 1)[0]
        if path == g or (head and path.startswith(head)):
            return g
    return None


def findings_on(run: Run, path: str) -> list[tuple[ReviewVerdict, Finding]]:
    """Everything a kept reviewer raised against one file."""
    return [
        (rv, f) for rv in run.reviews if not rv.discarded for f in rv.findings if f.file == path
    ]


def instrument_faults(run: Run) -> set[str]:
    """Checks that fail identically with and without the change, so they measure something else."""
    it = run.current_iteration
    return set(it.instrument_faults) if it else set()


def evidence_for(run: Run, verification_id: str) -> list[Evidence]:
    return [e for e in run.evidence if e.verification_id == verification_id]


def kept_findings(run: Run) -> list[tuple[ReviewVerdict, Finding]]:
    return [(rv, f) for rv in run.reviews if not rv.discarded for f in rv.findings]


def scope_checks(run: Run) -> list[Evidence]:
    return [e for e in run.evidence if e.kind is EvidenceKind.scope_check]
