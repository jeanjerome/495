"""Running a command a second time on the version it already reported on.

Every other control the harness runs compares two trees; this one compares two runs of the same
command on the same tree, where nothing changed in between. The pure reader of the pair is
``core/verification.py::reports_the_same_twice``; this module is what runs the second command
and writes the ``stability_check`` evidence (``docs/decisions/0024``).
"""

from __future__ import annotations

from harness495.core import git
from harness495.core.engine.checks.stage import Reading
from harness495.core.engine.services import RunServices
from harness495.core.models import (
    ADMISSIBLE,
    Evidence,
    EvidenceKind,
    Iteration,
    Run,
    Verification,
    new_id,
)
from harness495.core.verification import reports_the_same_twice
from harness495.sandbox.base import ExecRequest


def flipped_since(run: Run, it: Iteration, evidence: list[Evidence]) -> set[str]:
    """The verifications that report something else than they did on the previous iteration.

    A flip is where an unstable command does its damage: it is the moment the harness
    either credits a requirement it refused before, or charges one it credited, and it
    cannot tell the producer's work from the command's own weather. Both readings ask for
    the same thing — run it again — so a flipped command is repeated before any other.
    """
    if it.n < 2 or len(run.iterations) < it.n:
        return set()
    before: dict[str, bool | None] = {}
    for e in (run.evidence_by_id(x) for x in run.iterations[it.n - 2].evidence_ids):
        if e is not None and e.kind is EvidenceKind.command_result and e.verification_id:
            before[e.verification_id] = e.passed
    return {
        e.verification_id
        for e in evidence
        if e.kind is EvidenceKind.command_result
        and e.verification_id
        and e.passed is not None
        and before.get(e.verification_id) is not None
        and before[e.verification_id] != e.passed
    }


def repeat_watchers(
    services: RunServices, run: Run, it: Iteration, evidence: list[Evidence]
) -> list[Verification]:
    """The commands worth running a second time on the version under review.

    Every command a requirement leans on and that reported something: what it reported is
    about to credit that requirement or charge it, and a reading taken once says nothing
    about whether it repeats. A command that did not run has nothing to compare, and one
    slower on the change than the budget allows is left out with a warning, since the
    check costs one more run of it. What comes first is the command whose result flipped
    since the previous iteration, then the cheapest, so that a cap spends itself where a
    difference has already been seen.
    """
    durations = {
        e.verification_id: e.duration_s or 0.0
        for e in evidence
        if e.kind is EvidenceKind.command_result and e.verification_id and e.passed is not None
    }
    carried = {vid for r in run.spec.requirements for vid in r.verification_ids}
    flipped = flipped_since(run, it, evidence)
    watchers: list[Verification] = []
    slow: set[str] = set()
    for v in run.spec.verifications:
        if v.command is None or v.sufficiency not in ADMISSIBLE or v.id not in durations:
            continue
        if v.id not in carried:
            continue
        if durations[v.id] > run.budget.repeat_command_max_s:
            slow.add(v.id)
            continue
        watchers.append(v)
    for vid in sorted(slow):
        services.warn(
            run,
            f"{vid} took {durations[vid]:.0f}s on the change, over the "
            f"{run.budget.repeat_command_max_s}s a second run is given: whether it reports "
            "the same thing twice is not measured",
        )
    return sorted(watchers, key=lambda v: (v.id not in flipped, durations[v.id]))


def repeat(services: RunServices, run: Run, it: Iteration, evidence: list[Evidence]) -> Reading:
    """Run the commands the requirements lean on a second time on the same version.

    Every other control the harness runs compares two trees; this one compares two runs of
    the same command on the same tree, where nothing changed between them. A command that
    reports success once and failure once is not an instrument: what it happened to report
    first would credit a requirement no one could reproduce, or send the producer after a
    defect that is not in the change. Either reading is withdrawn and the requirement waits
    for the requester (``docs/decisions/0024``).

    The second run follows the first in the worktree the verifications left, in the order
    they ran in, so that a command finding what an earlier one built still finds it.
    """
    assert it.version is not None and it.version.head_commit
    for v in run.spec.verifications:
        v.stable = None
    limit = run.budget.max_repeated_commands
    watchers = repeat_watchers(services, run, it, evidence)[:limit] if limit > 0 else []
    if not watchers:
        return Reading([])
    first_run = {
        e.verification_id: e
        for e in evidence
        if e.kind is EvidenceKind.command_result and e.verification_id
    }
    req_by_verification: dict[str, list[str]] = {}
    for r in run.spec.requirements:
        for vid in r.verification_ids:
            req_by_verification.setdefault(vid, []).append(r.id)
    wt = services.worktree(run)
    produced: list[Evidence] = []
    for v in watchers:
        assert v.command is not None
        first = first_run[v.id]
        req = ExecRequest(
            command=v.command,
            cwd=wt,
            timeout_s=v.timeout_s or run.budget.command_timeout_s,
            writable=True,
            network=run.config.sandbox.allow_network,
            stop_check=services.stop_check(run),
        )
        res = services.sandbox.run(req)
        if res.interrupted:
            raise KeyboardInterrupt
        stable, summary = reports_the_same_twice(
            v.expected_exit_code,
            first.exit_code,
            services.store.read_text(run.id, first.output_ref or ""),
            first.summary == "timed out",
            res,
        )
        v.stable = stable
        eid = new_id("ev")
        ev = Evidence(
            id=eid,
            kind=EvidenceKind.stability_check,
            iteration=it.n,
            subject_version=it.version.head_commit,
            verification_id=v.id,
            requirement_ids=[] if stable else req_by_verification.get(v.id, []),
            command=v.command,
            exit_code=res.exit_code,
            expected_exit_code=v.expected_exit_code,
            passed=stable,
            summary=f"{v.id} {summary}",
            output_ref=services.store.write_text(
                run.id,
                str(services.store.evidence_dir(run.id, eid) / "output.txt"),
                res.output,
            ),
            output_sha256=git.sha256_text(res.output),
            duration_s=res.duration_s,
            sandbox=services.sandbox.describe(req),
        )
        produced.append(ev)
        services.emit(
            run,
            "evidence",
            f"stability: {'ok' if stable else 'UNSTABLE'} - {ev.summary}",
            {"id": ev.id, "verification": v.id},
        )
    return Reading(produced)
