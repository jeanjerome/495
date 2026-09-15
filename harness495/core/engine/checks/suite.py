"""What the change did to the test suite that passed on the base version.

The pure reader is ``core/suite.py`` — the diff over the test files that existed on the base,
and the runner's tally on each version; this module is what gathers the two texts it compares
and writes the ``suite_check`` evidence (``docs/decisions/0021``).
"""

from __future__ import annotations

from harness495.core import git
from harness495.core.engine.checks.stage import Reading
from harness495.core.engine.services import RunServices
from harness495.core.models import (
    Evidence,
    EvidenceKind,
    Iteration,
    RequirementKind,
    Run,
    Spec,
    VerificationKind,
    new_id,
)
from harness495.core.reading.suite import (
    CountComparison,
    SuiteReading,
    compare_counts,
    read_suite_changes,
)


def non_regression_verifications(spec: Spec) -> list[str]:
    """The verifications a non-regression requirement leans on, in specification order."""
    return list(
        dict.fromkeys(
            vid
            for r in spec.requirements
            if r.kind is RequirementKind.non_regression
            for vid in r.verification_ids
        )
    )


def suite_reading(
    services: RunServices, run: Run, it: Iteration, evidence: list[Evidence]
) -> SuiteReading:
    """What the change did to the suite that passed on the base: the diff over the test
    files that existed there, and the runner's tally on both versions for each command a
    non-regression requirement leans on (the base's from the baseline run of the same
    command, the change's from this iteration)."""
    assert it.version is not None and it.version.head_commit
    wt = services.worktree(run)
    changes = read_suite_changes(git.diff(wt, it.version.base_commit, it.version.head_commit))
    baseline_by_command = {
        e.command: e
        for e in run.evidence
        if e.kind is EvidenceKind.baseline and e.command and e.output_ref
    }
    counts: list[CountComparison] = []
    for vid in non_regression_verifications(run.spec):
        v = run.spec.verification(vid)
        result = next(
            (
                e
                for e in reversed(evidence)
                if e.kind is EvidenceKind.command_result
                and e.verification_id == vid
                and e.output_ref
            ),
            None,
        )
        base = baseline_by_command.get(v.command or "") if v else None
        if v is None or result is None or base is None:
            continue
        comparison = compare_counts(
            vid,
            services.store.read_text(run.id, base.output_ref or ""),
            services.store.read_text(run.id, result.output_ref or ""),
        )
        if comparison is not None:
            counts.append(comparison)
    return SuiteReading(changes=changes, counts=counts)


def check_suite(
    services: RunServices, run: Run, it: Iteration, evidence: list[Evidence]
) -> Reading:
    """One evidence saying whether the existing suite is, on the change, the suite the base
    passed. It names the non-regression requirements that lean on a test command, since
    those are the ones a passing command would otherwise credit."""
    assert it.version is not None
    reading = suite_reading(services, run, it, evidence)
    named = [
        r.id
        for r in run.spec.requirements
        if r.kind is RequirementKind.non_regression
        and any(
            v.command and v.kind is VerificationKind.test
            for v in map(run.spec.verification, r.verification_ids)
            if v is not None
        )
    ]
    ev = Evidence(
        id=new_id("ev"),
        kind=EvidenceKind.suite_check,
        iteration=it.n,
        subject_version=it.version.head_commit,
        requirement_ids=named,
        passed=not reading.weakened,
        summary=reading.summary(),
    )
    services.emit(
        run,
        "evidence",
        f"suite: {'ok' if ev.passed else 'WEAKENED'} - {ev.summary}",
        {"id": ev.id},
    )
    return Reading([ev])
