"""The order the verification stages run in, and the gate the two last ones wait on.

Eight stages measure the version under review, each producing :class:`Evidence` and none
calling another. Three of them are stated here because they belong to no check group: the
scope of the files the change touched, the test files the designer wrote and the change may
not edit (``docs/decisions/0020``), and the verifications of the specification themselves. The
five that follow are the check groups of this package, each paired with a pure reader of
``core/``.

The order is not a convenience. The reach and the mutation checks run last and only if the
calibration found every instrument readable: measuring what a blind command executes and what
it lets through would describe that command, not the tests (``docs/decisions/0022``, ``0023``).
Declaring the sequence as data is what lets that rule be read and asserted rather than
reconstructed from the order of statements.
"""

from __future__ import annotations

from harness495.core import git
from harness495.core.engine.checks import calibration, coverage, mutation, stability, suite
from harness495.core.engine.checks.stage import Reading, Stage
from harness495.core.engine.running import run_verification
from harness495.core.engine.services import RunServices
from harness495.core.models import (
    Evidence,
    EvidenceKind,
    Iteration,
    PendingDecision,
    Run,
    RunStatus,
    new_id,
)
from harness495.core.scope import check_scope, effective_allowed


def scope_check(
    services: RunServices, run: Run, it: Iteration, evidence: list[Evidence]
) -> Reading:
    """The files the change touched, against the paths it was allowed to touch."""
    assert it.version is not None
    allowed = effective_allowed(run)
    report = check_scope(
        it.version.files_changed, allowed, run.config.project.scope.forbidden_paths
    )
    scope_ev = Evidence(
        id=new_id("ev"),
        kind=EvidenceKind.scope_check,
        iteration=it.n,
        subject_version=it.version.head_commit,
        passed=report.ok,
        summary=report.summary(),
    )
    services.emit(
        run,
        "evidence",
        f"scope: {'ok' if report.ok else 'VIOLATION'} - {report.summary()}",
        {"id": scope_ev.id},
    )
    return Reading([scope_ev])


def protected_tests(
    services: RunServices, run: Run, it: Iteration, evidence: list[Evidence]
) -> Reading:
    """The test files the designer wrote, as the designer wrote them.

    The tests the designer wrote are the instrument; the change is what they measure. A version
    that edits one has moved the instrument, and what the instrument then reports is about the
    edit, not about the behaviour: that version is out of scope.
    """
    assert it.version is not None and it.version.head_commit
    design = run.test_design
    if design is None or not design.files:
        return Reading([])
    wt = services.worktree(run)
    touched = [
        f for f in git.diff_names(wt, design.commit, it.version.head_commit) if f in design.files
    ]
    protected_ev = Evidence(
        id=new_id("ev"),
        kind=EvidenceKind.scope_check,
        iteration=it.n,
        subject_version=it.version.head_commit,
        passed=not touched,
        summary=(
            f"{len(touched)} test file(s) written by the test designer modified by the "
            "change: " + ", ".join(touched)
            if touched
            else f"the {len(design.files)} test file(s) written by the test designer are as written"
        ),
    )
    services.emit(
        run,
        "evidence",
        f"protected tests: {'ok' if not touched else 'VIOLATION'} - {protected_ev.summary}",
        {"id": protected_ev.id},
    )
    return Reading([protected_ev])


def verifications(
    services: RunServices, run: Run, it: Iteration, evidence: list[Evidence]
) -> Reading:
    """Every verification of the specification, run once on the evaluated commit."""
    assert it.version is not None and it.version.head_commit
    wt = services.worktree(run)
    produced: list[Evidence] = []
    req_by_verification: dict[str, list[str]] = {}
    for r in run.spec.requirements:
        for vid in r.verification_ids:
            req_by_verification.setdefault(vid, []).append(r.id)
    for v in run.spec.verifications:
        if v.command is None:
            ev = run_verification(
                v,
                wt,
                it.version.head_commit,
                services.sandbox,
                it.n,
                run.budget.command_timeout_s,
                lambda _e, _t: "",
                None,
                req_by_verification.get(v.id, []),
                network=run.config.sandbox.allow_network,
            )
            produced.append(ev)
            continue
        services.emit(run, "verification.started", f"{v.id}: {v.command}", {"verification": v.id})

        def sink(eid: str, text: str) -> str:
            return services.store.write_text(
                run.id, str(services.store.evidence_dir(run.id, eid) / "output.txt"), text
            )

        ev = run_verification(
            v,
            wt,
            it.version.head_commit,
            services.sandbox,
            it.n,
            run.budget.command_timeout_s,
            sink,
            services.stop_check(run),
            req_by_verification.get(v.id, []),
            network=run.config.sandbox.allow_network,
        )
        produced.append(ev)
        services.emit(
            run,
            "evidence",
            f"{v.id}: {'PASS' if ev.passed else 'FAIL' if ev.passed is False else 'NOT RUN'} ({ev.summary})",
            {"id": ev.id, "verification": v.id},
        )
        if ev.summary == "interrupted":
            raise KeyboardInterrupt
    return Reading(produced)


def instrument_is_readable(run: Run, it: Iteration) -> bool:
    """Whether the calibration left every command it measured able to observe the change."""
    return not it.instrument_faults


BLIND_INSTRUMENT = (
    "an instrument the calibration found blind is about to stop the run; measuring what it "
    "reaches and what it lets through would describe that instrument, not the tests"
)

SEQUENCE: tuple[Stage, ...] = (
    Stage("scope", scope_check),
    Stage("protected_tests", protected_tests),
    Stage("verifications", verifications),
    Stage("stability", stability.repeat),
    Stage("suite", suite.check_suite),
    Stage("calibration", calibration.calibrate),
    Stage("coverage", coverage.reach, instrument_is_readable, BLIND_INSTRUMENT),
    Stage("mutation", mutation.mutate, instrument_is_readable, BLIND_INSTRUMENT),
)


def verify(services: RunServices, run: Run) -> tuple[list[Evidence], PendingDecision | None]:
    """Walk :data:`SEQUENCE` over the version under review and record what it measured.

    The evidence is appended to the run and returned, so that whoever measures the pass reads
    it without opening the run. The pending decision is returned rather than raised: a blind
    instrument is the one fault nothing downstream recovers from — reviewers would be handed a
    failure that is not the change's, or a success that is not the change's either, and would
    spend a full round reasoning about the wrong object — but which stop the run takes and how
    the answer comes back is the state machine's, not this package's.
    """
    it = run.current_iteration
    assert it is not None and it.version is not None and it.version.head_commit
    wt = services.worktree(run)
    services.set_status(run, RunStatus.verifying)
    git.reset_hard_clean(wt, it.version.head_commit)
    evidence: list[Evidence] = []
    proposals: dict[str, str] = {}
    for stage in SEQUENCE:
        if stage.gate is not None and not stage.gate(run, it):
            continue
        reading = stage.measure(services, run, it, evidence)
        evidence.extend(reading.evidence)
        proposals.update(reading.proposals)
    # Verification runs may write caches; restore the exact version for the reviewers.
    git.reset_hard_clean(wt, it.version.head_commit)
    run.evidence.extend(evidence)
    it.evidence_ids.extend(e.id for e in evidence)
    services.set_status(run, RunStatus.verified)
    if it.instrument_faults and not calibration.instrument_fault_settled(run):
        return evidence, calibration.instrument_decision(it, proposals)
    return evidence, None
